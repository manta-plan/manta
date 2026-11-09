from fastapi import Depends, HTTPException
from playbook.blocks import Catalogue
from playbook.playbooks.yaml_io import StepDoc

# TODO(post-MVP): a direct dependency on one concrete block library here is an
# MVP corner-cut, not the intended shape — see the TODO on these two
# dependencies in backend/pyproject.toml.
from playbook_library import library_catalogue
from playbook_library.playbooks import LibraryPlaybook, library_playbooks

from manta.services.results.playbook_result import (
    GetPlaybookResult,
    ListPlaybooksResult,
    PlaybookStepConditionResult,
    PlaybookStepResult,
    PlaybookStepSummaryResult,
    PlaybookSummaryResult,
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
        library_playbook = self.playbooks.get(playbook_name)
        if library_playbook is None:
            raise HTTPException(status_code=404, detail=f"Playbook {playbook_name!r} not found")

        return GetPlaybookResult(
            name=playbook_name,
            default_config=library_playbook.default_config,
            steps=[self._build_step_result(step) for step in library_playbook.doc.steps],
        )

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
