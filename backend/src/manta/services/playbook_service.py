from fastapi import Depends, HTTPException
from playbook.blocks import Catalogue
from playbook.playbooks import (
    BlockStepDoc,
    Playbook,
    PlaybookDoc,
    PlaybookHasIssuesError,
    PlaybookIssue,
    StepDoc,
    apply_settings,
    effective_inputs,
    find_playbook_issues,
    playbook_from_doc,
    resolve_inputs,
)
from playbook.playbooks.expressions import Compare, Const, Ref, parse, substitute

# TODO(post-MVP): a direct dependency on one concrete block library here is an
# MVP corner-cut, not the intended shape — see the TODO on these two
# dependencies in backend/pyproject.toml.
from playbook_library import library_catalogue
from playbook_library.playbooks import LibraryPlaybook, library_playbooks

from manta.services.results.playbook_result import (
    GetPlaybookResult,
    ListPlaybooksResult,
    PlaybookIssueResult,
    PlaybookStepConditionResult,
    PlaybookStepResult,
    PlaybookStepSummaryResult,
    PlaybookSummaryResult,
    ValidatePlaybookConfigResult,
)


def _config_path(issue: PlaybookIssue) -> list[str | int] | None:
    if issue.setting_path is not None:
        return [*issue.step_path, *issue.setting_path]
    if issue.input_path is not None:
        return [*(issue.step_path or ("inputs",)), *issue.input_path]
    return None


def _build_issue_result(issue: PlaybookIssue) -> PlaybookIssueResult:
    return PlaybookIssueResult(
        kind=issue.kind,
        message=issue.message,
        step_path=list(issue.step_path),
        config_path=_config_path(issue),
        input=None,
    )


def _when(playbook_name: str, step: StepDoc) -> PlaybookStepConditionResult | None:
    if step.if_ is None:
        return None
    match parse(step.if_):
        case Compare("==", Ref("inputs", (name,)), Const(value)):
            return PlaybookStepConditionResult(config=f"inputs.{name}", equals=value)
    raise HTTPException(
        status_code=501,
        detail=(
            f"Playbook {playbook_name!r}, step {step.id!r}: the web app cannot show the "
            f"condition {step.if_!r}. Write the condition in the form "
            "`${{ inputs.<name> == <value> }}`."
        ),
    )


def run_inputs(config: dict) -> object:
    """Return the inputs of a run with `config` (see `PlaybookService.run_playbook`)."""
    return config.get("inputs", {})


def config_of_run(playbook: Playbook, inputs: dict) -> dict:
    """Return the config a run started with, from its playbook and the inputs of its dispatch.

    The inputs are given with their defaults filled in, and each step under its id
    with its `with`, every expression in it evaluated against those inputs.

    Raises:
        PlaybookHasIssuesError: If `inputs` do not fit the inputs of `playbook`.
    """
    resolved = resolve_inputs(effective_inputs(playbook), inputs)
    settings = {step.id: substitute(step.with_, {"inputs": resolved}) for step in playbook.steps}
    return {"inputs": resolved, **settings}


class PlaybookService:
    def __init__(
        self,
        playbooks: dict[str, LibraryPlaybook] = Depends(library_playbooks),
        catalogue: Catalogue = Depends(library_catalogue),
    ) -> None:
        self.playbooks = playbooks
        self.catalogue = catalogue

    def list_playbooks(self) -> ListPlaybooksResult:
        items = [
            PlaybookSummaryResult(
                name=name,
                steps=[
                    PlaybookStepSummaryResult(name=step.id, block=_block_name(step))
                    for step in playbook.doc.steps
                ],
            )
            for name, playbook in self.playbooks.items()
        ]
        return ListPlaybooksResult(items=items, total=len(items))

    def get_playbook(self, playbook_name: str) -> GetPlaybookResult:
        doc = self._get_doc(playbook_name)
        return GetPlaybookResult(
            name=playbook_name,
            default_config=self.default_config(playbook_name),
            steps=[self._build_step_result(playbook_name, step) for step in doc.steps],
        )

    def default_config(self, playbook_name: str) -> dict:
        """Return the config of a run that is created without one.

        The config has the default of each input that is not required under `inputs`,
        and the default settings of each step under its id.
        """
        doc = self._get_doc(playbook_name)
        inputs = effective_inputs(playbook_from_doc(doc, catalogue=self.catalogue))
        defaults = {name: spec.default for name, spec in inputs.items() if not spec.required}
        settings = self.playbooks[playbook_name].default_settings
        return {"inputs": defaults, **{step.id: settings.get(step.id, {}) for step in doc.steps}}

    def run_playbook(self, playbook_name: str, config: dict) -> Playbook:
        """Return the playbook a run of `playbook_name` with `config` uses.

        Every key of `config` but `inputs` gives the settings of a step, applied to the
        playbook with `apply_settings`.

        Raises:
            PlaybookHasIssuesError: If a setting cannot be applied.
        """
        doc = self._get_doc(playbook_name)
        settings = {key: value for key, value in config.items() if key != "inputs"}
        return apply_settings(playbook_from_doc(doc, catalogue=self.catalogue), settings)

    def find_config_issues(self, playbook_name: str, config: dict) -> list[PlaybookIssueResult]:
        """Every reason `playbook_name` cannot run with exactly `config`.

        The blocks are known here only from the catalogue, so their settings are
        checked against its JSON schemas: wrong types, missing and unknown settings are
        caught, but a rule a block only expresses in code is not, and still fails when
        that block runs.
        """
        inputs = run_inputs(config)
        if not isinstance(inputs, dict):
            message = (
                f"the inputs are a mapping of input name to value, not {inputs!r}. "
                "Write them as a mapping"
            )
            return [
                PlaybookIssueResult(
                    kind="inputs", message=message, step_path=[], config_path=["inputs"], input=None
                )
            ]
        try:
            playbook = self.run_playbook(playbook_name, config)
        except PlaybookHasIssuesError as exc:
            return list(map(_build_issue_result, exc.issues))
        return list(map(_build_issue_result, find_playbook_issues(playbook, inputs)))

    def raise_for_config_issues(self, playbook_name: str, config: dict) -> None:
        """Refuse with a 422, listing every issue, if `playbook_name` cannot run with
        `config`."""
        issues = self.find_config_issues(playbook_name, config)
        if issues:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Playbook {playbook_name!r} cannot run with this config",
                    "issues": [issue.model_dump(mode="json") for issue in issues],
                },
            )

    def validate_playbook_config(
        self, playbook_name: str, config: dict | None
    ) -> ValidatePlaybookConfigResult:
        """Whether `playbook_name` can run with `config`, and every reason it cannot.

        The same check a run is refused by (see RunService.create_run), answered as
        data rather than an error, so an editor can show problems next to the form as
        the user edits. A missing config means the playbook's default, as for a run.
        """
        run_config = config if config is not None else self.default_config(playbook_name)
        issues = self.find_config_issues(playbook_name, run_config)
        return ValidatePlaybookConfigResult(valid=not issues, issues=issues)

    def _get_doc(self, playbook_name: str) -> PlaybookDoc:
        playbook = self.playbooks.get(playbook_name)
        if playbook is None:
            raise HTTPException(status_code=404, detail=f"Playbook {playbook_name!r} not found")
        for step in playbook.doc.steps:
            if step.id == "inputs":
                raise HTTPException(
                    status_code=501,
                    detail=(
                        f"Playbook {playbook_name!r} has a step called 'inputs', which the web "
                        "app cannot tell apart from the inputs of a run. Rename the step."
                    ),
                )
            _when(playbook_name, step)
        return playbook.doc

    def _build_step_result(self, playbook_name: str, step: StepDoc) -> PlaybookStepResult:
        # A step running a nested playbook has no block of its own to describe. No
        # library playbook nests another yet, so it is listed but not expanded.
        name = _block_name(step)
        block = self.catalogue.blocks[name] if name is not None else None
        return PlaybookStepResult(
            name=step.id,
            block=name,
            block_summary=block.doc if block is not None else None,
            block_config_schema=block.config_schema if block is not None else None,
            when=_when(playbook_name, step),
            inputs={},
        )


def _block_name(step: StepDoc) -> str | None:
    return step.block if isinstance(step, BlockStepDoc) else None
