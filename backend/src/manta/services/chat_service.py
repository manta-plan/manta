import json
import logging
import threading
import time
from collections.abc import Iterator
from functools import lru_cache

import httpx2
from fastapi import Depends, HTTPException, status

from manta.config.chat_config import (
    chat_api_key,
    chat_docs_dir,
    chat_docs_max_chars,
    chat_docs_pages,
    chat_enabled,
    chat_max_history_chars,
    chat_max_message_chars,
    chat_max_messages,
    chat_max_output_tokens,
    chat_max_record_chars,
    chat_model,
    chat_sql_enabled,
    chat_timeout_seconds,
    get_chat_client,
    get_chat_slots,
)
from manta.services.chat_prompts import DATA_INSTRUCTIONS, DATA_REFERENCE, DOCS_INSTRUCTIONS
from manta.services.results.chat_result import ChatEventResult, GetChatStatusResult

logger = logging.getLogger(__name__)

# A pymdownx.snippets include line. The file it pulls in is not part of the page's text.
_SNIPPET_MARKER = "--8<--"
_BUSY_RETRY_SECONDS = 10


@lru_cache
def system_prompt(with_data: bool = False) -> str:
    """The model's instructions followed by the configured documentation pages and, with
    `with_data`, by how to answer a question about a project's data. Built once, and the
    same for every request, so that a model server can reuse its work on it."""
    pages = []
    for page in chat_docs_pages():
        path = chat_docs_dir() / page
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise RuntimeError(f"Chat documentation page not found: {path}") from e
        lines = [line for line in text.splitlines() if _SNIPPET_MARKER not in line]
        # Replies are shown as plain text, and a model repeats the emphasis it reads.
        body = "\n".join(lines).replace("**", "").strip()
        pages.append(f"===== {page} =====\n{body}")
    docs = "\n\n".join(pages)
    if len(docs) > chat_docs_max_chars():
        raise RuntimeError(
            f"The chat documentation pages hold {len(docs)} characters, more than "
            f"CHAT_DOCS_MAX_CHARS ({chat_docs_max_chars()}). List fewer pages in "
            "CHAT_DOCS_PAGES, or raise the limit if the model's context has room."
        )
    if with_data:
        return f"{DATA_INSTRUCTIONS}\n\n{docs}\n\n{DATA_REFERENCE}"
    return f"{DOCS_INSTRUCTIONS}\n\n{docs}"


def describe_record(components: list[dict], attributes: list[dict]) -> str | None:
    """What a project's data contains, as the end of the model's instructions, or None
    where questions about data are off. The request model has checked every name. Lines
    beyond CHAT_MAX_RECORD_CHARS are left out, so a large project costs the model
    attributes, not the whole reply."""
    if not chat_sql_enabled():
        return None
    limit = chat_max_record_chars()
    lines = ["This project's component types, each with its carriers:"]
    lines += [
        f"- {component['ctype']}: {', '.join(component['carriers']) or 'no carrier'}"
        for component in components
    ]
    lines.append("")
    lines.append("This project's attributes, each a view attributes.NAME:")
    for attribute in attributes:
        details = [attribute["unit"] or "no unit", f"per {attribute['subject']}"]
        if attribute["series"]:
            details.append("series")
        lines.append(f"- {attribute['name']} ({', '.join(details)})")
    kept: list[str] = []
    for line in lines:
        if sum(len(kept_line) + 1 for kept_line in kept) + len(line) > limit:
            break
        kept.append(line)
    return "\n".join(kept)


def require_chat_enabled() -> None:
    if not chat_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chat is not enabled in this deployment"
        )


def chat_status() -> GetChatStatusResult:
    return GetChatStatusResult(
        enabled=chat_enabled(),
        sql_enabled=chat_enabled() and chat_sql_enabled(),
        max_messages=chat_max_messages(),
        max_message_chars=chat_max_message_chars(),
        max_history_chars=chat_max_history_chars(),
    )


def check_message_limits(messages: list[dict[str, str]]) -> None:
    """Refuses messages beyond the configured limits with a 422. Called before
    stream_reply(): by then the response has started and can no longer become one."""
    if len(messages) > chat_max_messages():
        _refuse(f"Too many messages: at most {chat_max_messages()} are allowed")
    if any(len(message["content"]) > chat_max_message_chars() for message in messages):
        _refuse(f"Message too long: at most {chat_max_message_chars()} characters are allowed")
    if sum(len(message["content"]) for message in messages) > chat_max_history_chars():
        _refuse(
            f"Conversation too long: at most {chat_max_history_chars()} characters "
            "are allowed in total"
        )


def _refuse(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def chat_slot(slots: threading.BoundedSemaphore = Depends(get_chat_slots)) -> Iterator[None]:
    """Holds one of the reply slots for as long as the request lasts, or refuses the
    request when all are taken. Each reply also occupies a worker thread until it ends."""
    if not slots.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rai is busy answering other questions. Try again in a moment.",
            headers={"Retry-After": str(_BUSY_RETRY_SECONDS)},
        )
    try:
        yield
    finally:
        slots.release()


class ChatService:
    def __init__(self, client: httpx2.Client = Depends(get_chat_client)) -> None:
        self.client = client

    def stream_reply(
        self, messages: list[dict[str, str]], record: str | None = None
    ) -> Iterator[ChatEventResult]:
        """The model's reply to a conversation of `{"role": ..., "content": ...}` messages,
        oldest first, as it is written. `record` is describe_record()'s text for the
        project the question is asked in. Ends with a `done`
        event, or with an `error` event when the model fails: raising instead would cut
        the already started response short without telling the client why."""
        deadline = time.monotonic() + chat_timeout_seconds()
        finish_reason = None
        try:
            with self.client.stream(
                "POST",
                "chat/completions",
                json={
                    "model": chat_model(),
                    "messages": [
                        {"role": "system", "content": _instructions(record)},
                        *messages,
                    ],
                    "stream": True,
                    "max_tokens": chat_max_output_tokens(),
                },
                headers=_authorization(),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if time.monotonic() > deadline:
                        raise httpx2.ReadTimeout("The reply took too long")
                    # Each chunk is a `data: {...}` line; `data: [DONE]` ends the stream.
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    choices = json.loads(data).get("choices")
                    if not choices:
                        continue
                    text = (choices[0].get("delta") or {}).get("content")
                    if text:
                        yield ChatEventResult(event="delta", data={"text": text})
                    finish_reason = choices[0].get("finish_reason") or finish_reason
        except httpx2.TimeoutException:
            logger.warning("The chat model timed out", exc_info=True)
            yield _error("timeout", "The model took too long to answer. Try again.")
            return
        except httpx2.HTTPError, ValueError:
            logger.warning("The chat model failed", exc_info=True)
            yield _error("model_unavailable", "The model is not available right now.")
            return

        if finish_reason is None:
            logger.warning("The chat model's reply ended without a finish reason")
            yield _error("model_unavailable", "The model stopped answering part-way.")
            return
        yield ChatEventResult(
            event="done",
            data={"finish_reason": "length" if finish_reason == "length" else "stop"},
        )


def _instructions(record: str | None) -> str:
    # One system message, with what changes between projects last: some APIs accept
    # only one, and a model server reuses its work on the part that stays the same.
    if record is None:
        return system_prompt()
    return f"{system_prompt(with_data=True)}\n\n{record}"


def _authorization() -> dict[str, str]:
    key = chat_api_key()
    return {"Authorization": f"Bearer {key}"} if key else {}


def _error(code: str, message: str) -> ChatEventResult:
    return ChatEventResult(event="error", data={"code": code, "message": message})
