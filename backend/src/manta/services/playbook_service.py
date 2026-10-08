from fastapi import Depends, HTTPException
from playbook.blocks import Catalogue
from playbook.playbooks import PlaybookIssue, find_playbook_issues, playbook_from_doc
from playbook.playbooks.yaml_io import StepDoc

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
)


def _build_issue_result(issue: PlaybookIssue) -> PlaybookIssueResult:
    return PlaybookIssueResult(
        kind=issue.kind,
        message=issue.message,
        step_path=list(issue.step_path),
        config_path=list(issue.config_path) if issue.config_path is not None else None,
        input=issue.input,
    )


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
                    PlaybookStepSummaryResult(name=step.name, block=step.block)
                    for step in library_playbook.doc.steps
                ],
            )
            for name, library_playbook in self.playbooks.items()
        ]
        return ListPlaybooksResult(items=items, total=len(items))

    def get_playbook(self, playbook_name: str) -> GetPlaybookResult:
        library_playbook = self._get_library_playbook(playbook_name)
        return GetPlaybookResult(
            name=playbook_name,
            default_config=library_playbook.default_config,
            steps=[self._build_step_result(step) for step in library_playbook.doc.steps],
        )

    def find_config_issues(self, playbook_name: str, config: dict) -> list[PlaybookIssueResult]:
        """Every reason `playbook_name` cannot run with exactly `config`.

        The blocks are known here only from the catalogue, so their settings are
        checked against its JSON schemas: wrong types, missing and unknown settings are
        caught, but a rule a block only expresses in code is not, and still fails when
        that block runs.
        """
        library_playbook = self._get_library_playbook(playbook_name)
        playbook = playbook_from_doc(library_playbook.doc, catalogue=self.catalogue)
        return [_build_issue_result(issue) for issue in find_playbook_issues(playbook, config)]

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

    def _get_library_playbook(self, playbook_name: str) -> LibraryPlaybook:
        library_playbook = self.playbooks.get(playbook_name)
        if library_playbook is None:
            raise HTTPException(status_code=404, detail=f"Playbook {playbook_name!r} not found")
        return library_playbook

    def _build_step_result(self, step: StepDoc) -> PlaybookStepResult:
        # A step running a nested playbook has no block of its own to describe. No
        # library playbook nests another yet, so it is listed but not expanded.
        block = self.catalogue.blocks[step.block] if step.block is not None else None
        return PlaybookStepResult(
            name=step.name,
            block=step.block,
            block_summary=block.doc if block is not None else None,
            block_config_schema=block.config_schema if block is not None else None,
            when=(
                PlaybookStepConditionResult(config=step.when.config, equals=step.when.equals)
                if step.when is not None
                else None
            ),
            inputs=step.inputs,
        )
