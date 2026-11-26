"""The read-only tools the chat model may call, and the one way to call them.

A tool name and its arguments come from the model, so they are untrusted: only a
tool in the registry runs, its arguments are checked against a typed shape, and
the user is always the signed-in one, never one the model names. What goes back
to the model is capped, stripped of storage paths and secrets, and wrapped as
quoted data.
"""

import json
import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import AfterValidator, BaseModel, Field, ValidationError

from manta.config.chat_config import chat_rag_min_score, chat_rag_top_k
from manta.config.s3_config import s3_bucket_name
from manta.entities import User
from manta.services.doc_ingest_service import DocIngestService
from manta.services.playbook_service import PlaybookService
from manta.services.results.chat_result import ChatCitationResult, ChatToolResult
from manta.services.results.doc_ingest_result import DocSearchHit
from manta.services.run_service import RunService

logger = logging.getLogger(__name__)

RUN_NOT_FOUND_MESSAGE = "Run not found"
"""The answer for a run that does not exist and for one that is not the user's, so
a guessed ID does not show whether a run exists."""

_MAX_LISTED_RUNS = 20
_MAX_LOG_LINES = 200
_MAX_DOC_QUERY_CHARS = 300
_MAX_DOC_HITS = 8
_TRUNCATED = "\n[truncated]"
# Below this, a result is too short to be of use to the model.
_MIN_OUTPUT_CHARS = 200

_REDACTED = "[redacted]"
_STORAGE_PATH = "[storage path]"
_SENSITIVE_NAME = (
    r"[\w-]*(?:password|passwd|secret[_-]?key|private[_-]?key|access[_-]?key|api[_-]?key"
    r"|secret|token|credentials?)(?:[_-]id)?"
)
# Applied in order to every string a tool returns.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bs3a?://[^\s\"'<>)\]]+", re.IGNORECASE), _STORAGE_PATH),
    # `scheme://user:password@host`
    (re.compile(r"\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@", re.IGNORECASE), rf"\1{_REDACTED}@"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), _REDACTED),
    # A JSON web token: three base64url parts, the first starting with `{"`.
    (re.compile(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"), _REDACTED),
    (re.compile(r"\b(bearer|basic)\s+[\w.~+/=-]{8,}", re.IGNORECASE), rf"\1 {_REDACTED}"),
    # `password=...`, `"api_key": "..."`, `S3_SECRET_KEY: ...`
    (
        re.compile(rf"\b({_SENSITIVE_NAME})([\"']?\s*[=:]\s*[\"']?)([^\s\"',;&]+)", re.IGNORECASE),
        rf"\1\2{_REDACTED}",
    ),
)


def _clamp(low: int, high: int) -> Callable[[int], int]:
    return lambda value: max(low, min(high, value))


class _ListMyRunsArguments(BaseModel):
    status: str | None = Field(
        default=None,
        description="Only runs in this state, e.g. FAILED, RUNNING or COMPLETED.",
    )
    # Clamped, not refused: a small model that asks for 50 still gets its answer.
    limit: Annotated[int, AfterValidator(_clamp(1, _MAX_LISTED_RUNS))] = Field(
        default=10,
        description="How many runs, newest first.",
        json_schema_extra={"minimum": 1, "maximum": _MAX_LISTED_RUNS},
    )


class _RunArguments(BaseModel):
    run_id: UUID | None = Field(
        default=None,
        description="The run's ID. Leave out to use the run the user is looking at.",
    )


class _RunLogsArguments(_RunArguments):
    tail: Annotated[int, AfterValidator(_clamp(1, _MAX_LOG_LINES))] = Field(
        default=50,
        description="How many of the last log lines.",
        json_schema_extra={"minimum": 1, "maximum": _MAX_LOG_LINES},
    )


class _ConfigSchemaArguments(BaseModel):
    playbook: str = Field(description="The playbook's name, e.g. the `playbook` of a run.")
    step: str | None = Field(
        default=None,
        description="A step of the playbook, to get the settings of that step.",
    )


class _SearchDocsArguments(BaseModel):
    query: str = Field(
        description="What to look for, in a few words or as a question.",
        min_length=1,
        max_length=_MAX_DOC_QUERY_CHARS,
    )
    k: Annotated[int, AfterValidator(_clamp(1, _MAX_DOC_HITS))] | None = Field(
        default=None,
        description="How many passages.",
        json_schema_extra={"minimum": 1, "maximum": _MAX_DOC_HITS},
    )


@dataclass(frozen=True)
class _ToolCall:
    arguments: BaseModel
    user: User
    run_uuid: UUID | None
    """The run the user is looking at, already checked to be theirs."""

    max_chars: int
    citation_offset: int


@dataclass(frozen=True)
class _ToolOutput:
    payload: object
    """Anything `json.dumps` takes."""

    citations: list[ChatCitationResult] = field(default_factory=list)


class _ToolFailedError(Exception):
    """A tool's expected "no": the message goes to the model as the result."""


@dataclass(frozen=True)
class ChatTool:
    name: str
    label: str
    """Shown to the user while the tool runs."""

    description: str
    """Shown to the model."""

    arguments: type[BaseModel]
    max_chars: int
    failure_message: str
    """The result when the tool breaks, e.g. because Prefect cannot be reached."""

    handler: Callable[[_ToolCall], _ToolOutput]
    redact: bool = True


def _parameters(arguments: type[BaseModel]) -> dict:
    """The arguments as the JSON schema sent to the model, without what a small
    model does not need: titles, defaults and the `null` half of an optional."""
    schema = arguments.model_json_schema()
    properties = {}
    for name, original in schema.get("properties", {}).items():
        prop = {key: value for key, value in original.items() if key not in ("title", "default")}
        if "anyOf" in prop:
            [value_schema] = [option for option in prop.pop("anyOf") if option != {"type": "null"}]
            prop = {**value_schema, **prop}
        properties[name] = prop
    return {"type": "object", "properties": properties, "required": schema.get("required", [])}


def _redact(value: object, patterns: tuple[tuple[re.Pattern[str], str], ...]) -> object:
    """A copy of a tool's payload with every string in it redacted."""
    if isinstance(value, str):
        for pattern, replacement in patterns:
            value = pattern.sub(replacement, value)
        return value
    if isinstance(value, dict):
        return {key: _redact(item, patterns) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, patterns) for item in value]
    return value


def _dump(payload: object) -> str:
    # `</` is escaped so no text in a result can close the tag it is quoted in.
    return json.dumps(payload, ensure_ascii=False, default=str).replace("</", "<\\/")


def _quote(name: str, text: str) -> str:
    return f'<tool_result name="{name}">\n{text}\n</tool_result>'


@contextmanager
def _run_not_found() -> Iterator[None]:
    """Turns the 404 of a missing run and the 403 of someone else's into one answer."""
    try:
        yield
    except HTTPException as error:
        if error.status_code in (403, 404):
            raise _ToolFailedError(RUN_NOT_FOUND_MESSAGE) from None
        raise


class ChatToolService:
    def __init__(
        self,
        run_service: RunService = Depends(),
        playbook_service: PlaybookService = Depends(),
        doc_ingest_service: DocIngestService = Depends(),
        bucket: str = Depends(s3_bucket_name),
        rag_top_k: int = Depends(chat_rag_top_k),
        rag_min_score: float = Depends(chat_rag_min_score),
    ) -> None:
        self.run_service = run_service
        self.playbook_service = playbook_service
        self.doc_ingest_service = doc_ingest_service
        self.rag_top_k = rag_top_k
        self.rag_min_score = rag_min_score
        # An object's HTTP address on the object store, which names the bucket first.
        self._redactions = (
            *_REDACTIONS,
            (
                re.compile(rf"https?://[^\s/\"']+/{re.escape(bucket)}/[^\s\"'<>)\]]*"),
                _STORAGE_PATH,
            ),
        )
        # search_docs comes first: a small model leans towards the first tool, and
        # the tools about runs are only right when the user asks about their own runs.
        tools = [
            ChatTool(
                name="search_docs",
                label="Searching the documentation",
                description=(
                    "Searches the Manta documentation and returns numbered passages. "
                    "Use it for every question about how Manta works or how to do "
                    "something in it, e.g. 'How do I start a run?' or 'What is a playbook?'."
                ),
                arguments=_SearchDocsArguments,
                max_chars=12_000,
                failure_message="Docs search unavailable",
                handler=self._search_docs,
                # Public documentation, which shows example paths and dev defaults.
                redact=False,
            ),
            ChatTool(
                name="list_my_runs",
                label="Listing your runs",
                description=(
                    "Lists the runs the user has already started, newest first: ID, "
                    "project, playbook, status and when it was created. Only for "
                    "questions about the user's own existing runs."
                ),
                arguments=_ListMyRunsArguments,
                max_chars=4_000,
                failure_message="Runs unavailable",
                handler=self._list_my_runs,
            ),
            ChatTool(
                name="get_run_status",
                label="Checking run status",
                description=(
                    "Gets one run's status, its playbook, its timings, the step it is "
                    "at and the message of any failed step."
                ),
                arguments=_RunArguments,
                max_chars=2_000,
                failure_message="Run status unavailable",
                handler=self._get_run_status,
            ),
            ChatTool(
                name="get_run_steps",
                label="Checking run steps",
                description=(
                    "Gets every step of one run in order: its block, status, timings "
                    "and, for a failed step, the error message."
                ),
                arguments=_RunArguments,
                max_chars=8_000,
                failure_message="Run steps unavailable",
                handler=self._get_run_steps,
            ),
            ChatTool(
                name="get_run_logs",
                label="Checking run logs",
                description="Gets the last lines of one run's log.",
                arguments=_RunLogsArguments,
                max_chars=16_000,
                failure_message="Logs unavailable",
                handler=self._get_run_logs,
            ),
            ChatTool(
                name="get_config_schema",
                label="Looking up playbook settings",
                description=(
                    "Describes what can be set in a playbook's config: its steps and "
                    "default config, or with `step` the settings of that step."
                ),
                arguments=_ConfigSchemaArguments,
                max_chars=12_000,
                failure_message="Schema unavailable",
                handler=self._get_config_schema,
            ),
        ]
        self.tools = {tool.name: tool for tool in tools}

    def definitions(self) -> list[dict]:
        """Every tool as the chat-completions API wants it in `tools`."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": _parameters(tool.arguments),
                },
            }
            for tool in self.tools.values()
        ]

    def label(self, name: str) -> str | None:
        """What to show the user while the tool runs. None for a name that is not a
        tool, which the model can make up."""
        tool = self.tools.get(name)
        return tool.label if tool is not None else None

    def run_tool(
        self,
        name: str,
        arguments_json: str,
        user: User,
        run_uuid: UUID | None,
        max_chars: int,
        citation_offset: int = 0,
    ) -> ChatToolResult:
        """Runs one tool as `user` and returns what the model may read.

        `max_chars` is what is left of the answer's budget for tool output; the
        tool's own cap applies as well. `citation_offset` is how many documentation
        passages this answer has numbered so far. Never raises: a tool that fails
        answers with its failure message.
        """
        tool = self.tools.get(name)
        if tool is None:
            return self._failed(name, f"Unknown tool. The tools are: {', '.join(self.tools)}.")
        max_chars = min(tool.max_chars, max_chars)
        if max_chars < _MIN_OUTPUT_CHARS:
            return self._failed(
                name, "No room is left for tool results in this answer. Answer with what you have."
            )
        try:
            arguments = tool.arguments.model_validate_json(arguments_json or "{}")
        except ValidationError as error:
            issues = "; ".join(
                f"{'.'.join(str(part) for part in issue['loc']) or 'arguments'}: {issue['msg']}"
                for issue in error.errors()
            )
            return self._failed(name, f"The arguments are not valid. {issues}"[:max_chars])

        try:
            output = tool.handler(_ToolCall(arguments, user, run_uuid, max_chars, citation_offset))
        except _ToolFailedError as failure:
            return self._failed(name, str(failure))
        except Exception as error:
            # The error's own text can quote a config value or a path, so only its
            # type is logged.
            logger.warning("Chat tool %s failed with %s", name, type(error).__name__)
            return self._failed(name, tool.failure_message)

        payload = _redact(output.payload, self._redactions) if tool.redact else output.payload
        text = _dump(payload)
        if len(text) > max_chars:
            text = text[: max_chars - len(_TRUNCATED)] + _TRUNCATED
        return ChatToolResult(
            name=name, ok=True, content=_quote(name, text), citations=output.citations
        )

    def _failed(self, name: str, message: str) -> ChatToolResult:
        return ChatToolResult(name=name, ok=False, content=_quote(name, _dump({"error": message})))

    def _run_uuid(self, call: _ToolCall) -> UUID:
        run_uuid = call.arguments.run_id or call.run_uuid
        if run_uuid is None:
            raise _ToolFailedError(
                "No run was given. Ask the user which run they mean, or call list_my_runs."
            )
        return run_uuid

    def _list_my_runs(self, call: _ToolCall) -> _ToolOutput:
        arguments = call.arguments
        result = self.run_service.list_user_runs(
            user=call.user,
            limit=arguments.limit,
            status_filters=[arguments.status] if arguments.status else None,
        )
        if not result.items:
            # A bare empty list reads to a small model as "nothing came back".
            return _ToolOutput({"runs": [], "note": "The user has no runs that match."})
        return _ToolOutput(
            {
                "runs": [
                    {
                        "run_id": run.uuid,
                        "project": run.project_name,
                        "playbook": run.playbook,
                        "status": run.status,
                        "created_at": run.created_at,
                    }
                    for run in result.items
                ]
            }
        )

    def _get_run_status(self, call: _ToolCall) -> _ToolOutput:
        run_uuid = self._run_uuid(call)
        with _run_not_found():
            run = self.run_service.get_run(run_uuid, user=call.user)
            steps = self.run_service.get_run_steps(run_uuid, user=call.user).steps
        starts = [step.start_time for step in steps if step.start_time is not None]
        ends = [step.end_time for step in steps if step.end_time is not None]
        return _ToolOutput(
            {
                "run_id": run.uuid,
                "playbook": run.playbook,
                "status": run.status,
                "created_at": run.created_at,
                "first_step_started_at": min(starts, default=None),
                "last_step_ended_at": max(ends, default=None),
                "running_steps": [step.name for step in steps if step.status == "RUNNING"],
                "failed_steps": [
                    {"step": step.name, "status": step.status, "message": step.message}
                    for step in steps
                    if step.status in ("FAILED", "CRASHED")
                ],
            }
        )

    def _get_run_steps(self, call: _ToolCall) -> _ToolOutput:
        run_uuid = self._run_uuid(call)
        with _run_not_found():
            result = self.run_service.get_run_steps(run_uuid, user=call.user)
        return _ToolOutput(
            {
                "run_id": result.uuid,
                "run_status": result.run_status,
                # A step's output is a storage address, so it is left out.
                "steps": [
                    {
                        "step": step.name,
                        "block": step.block,
                        "status": step.status,
                        "started_at": step.start_time,
                        "ended_at": step.end_time,
                        "seconds": (
                            round((step.end_time - step.start_time).total_seconds())
                            if step.start_time is not None and step.end_time is not None
                            else None
                        ),
                        "message": step.message,
                    }
                    for step in result.steps
                ],
            }
        )

    def _get_run_logs(self, call: _ToolCall) -> _ToolOutput:
        run_uuid = self._run_uuid(call)
        with _run_not_found():
            result = self.run_service.get_run_logs(run_uuid, user=call.user)
        # The end of a log says why a run stopped, so when the cap is hit it is the
        # oldest lines that go. Counted after redaction, which is what gets sent.
        lines: list[str] = []
        room = call.max_chars - _MIN_OUTPUT_CHARS
        for line in reversed(result.logs[-call.arguments.tail :]):
            room -= len(_dump(_redact(line, self._redactions))) + 2
            if room < 0:
                break
            lines.append(line)
        lines.reverse()
        return _ToolOutput(
            {"run_id": result.uuid, "run_status": result.run_status, "last_lines": lines}
        )

    def _get_config_schema(self, call: _ToolCall) -> _ToolOutput:
        arguments = call.arguments
        try:
            playbook = self.playbook_service.get_playbook(arguments.playbook)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            names = ", ".join(item.name for item in self.playbook_service.list_playbooks().items)
            raise _ToolFailedError(f"Playbook not found. The playbooks are: {names}.") from None

        if arguments.step is None:
            return _ToolOutput(
                {
                    "playbook": playbook.name,
                    "default_config": playbook.default_config,
                    "steps": [
                        {
                            "step": step.name,
                            "block": step.block,
                            "summary": step.block_summary,
                            "runs_when": (
                                f"{step.when.config} is {step.when.equals!r}"
                                if step.when is not None
                                else "always"
                            ),
                        }
                        for step in playbook.steps
                    ],
                    "note": "Call again with `step` for the settings of one step.",
                }
            )

        steps = {step.name: step for step in playbook.steps}
        step = steps.get(arguments.step)
        if step is None:
            raise _ToolFailedError(f"Step not found. The steps are: {', '.join(steps)}.")
        return _ToolOutput(
            {
                "playbook": playbook.name,
                "step": step.name,
                "block": step.block,
                "summary": step.block_summary,
                "default_config": playbook.default_config.get(step.name),
                "settings_schema": step.block_config_schema,
            }
        )

    def _search_docs(self, call: _ToolCall) -> _ToolOutput:
        arguments = call.arguments
        hits = self.doc_ingest_service.search(arguments.query, top_k=arguments.k or self.rag_top_k)
        passages: list[dict] = []
        citations: list[ChatCitationResult] = []
        room = call.max_chars - _MIN_OUTPUT_CHARS
        # Vector search always returns its nearest chunks, however far away they
        # are, so an off-topic question still has hits. Those score too low.
        for hit in [hit for hit in hits if hit.score >= self.rag_min_score]:
            citation = self._citation(call.citation_offset + len(citations) + 1, hit)
            passage = {**citation.model_dump(), "content": hit.content}
            room -= len(_dump(passage)) + 2
            if room < 0:
                # A passage that does not fit is not sent, and so not cited either.
                # Only the best one is cut short instead, so there is an answer.
                kept_chars = len(hit.content) + room
                if passages or kept_chars <= 0:
                    break
                passage["content"] = hit.content[:kept_chars]
            passages.append(passage)
            citations.append(citation)
        if not passages:
            return _ToolOutput(
                {"passages": [], "note": "The documentation has nothing on this. Say so."}
            )
        return _ToolOutput({"passages": passages}, citations)

    def _citation(self, index: int, hit: DocSearchHit) -> ChatCitationResult:
        return ChatCitationResult(
            index=index,
            # The page's own title is the outermost heading of every chunk on it.
            title=hit.heading_path.split(" > ")[0] or hit.doc_path,
            heading_path=hit.heading_path,
            url=hit.url,
        )
