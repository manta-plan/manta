import logging
from functools import lru_cache

from blocks import Catalogue
from blocks.library import library_catalogue
from fastapi import HTTPException
from playbooks import Playbook, PlaybookDoc, playbook_from_doc
from playbooks.library import library_playbooks

from manta.services.results.playbook_result import (
    GetPlaybookResult,
    ListPlaybooksResult,
    PlaybookIssueResult,
)

logger = logging.getLogger(__name__)


@lru_cache
def _catalogue() -> Catalogue:
    """The committed description of the library blocks.

    This is what lets the backend resolve and validate playbooks without being able
    to import a single block (they need PyPSA, which the backend deliberately does
    not have — blocks only ever run inside the blocks runner image).
    """
    return library_catalogue()


class PlaybookService:
    """The playbooks Manta offers, and the checks a run must pass before starting.

    For the MVP these are the playbooks shipped with manta-blocks
    (playbooks.library). User-authored/ephemeral playbooks are a post-MVP concern:
    when they arrive, this service grows a store for their documents, and
    everything else — validation, runs — already works on documents.
    """

    def list_playbooks(self) -> ListPlaybooksResult:
        return ListPlaybooksResult(
            items=[self._to_result(name) for name in sorted(library_playbooks().keys())]
        )

    def get_playbook(self, name: str) -> GetPlaybookResult:
        if name not in library_playbooks():
            raise HTTPException(status_code=404, detail=f"Playbook {name!r} not found")
        return self._to_result(name)

    def resolve(self, name: str) -> tuple[PlaybookDoc, dict]:
        """The named playbook's document and default settings, or 404."""
        entry = library_playbooks().get(name)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Playbook {name!r} not found")
        return entry.doc, entry.default_config

    def build(self, doc: PlaybookDoc) -> Playbook:
        """Turn a document into a playbook, resolving blocks from the catalogue."""
        return playbook_from_doc(doc, catalogue=_catalogue())

    def validate(self, playbook: Playbook, config: dict) -> list[PlaybookIssueResult]:
        """Everything wrong with running `playbook` with `config`, without raising.

        This is the proposal's catch-errors-early requirement: a run with a missing
        dimension, an unknown setting, or a broken wire is refused here, before
        anything is dispatched.
        """
        return [
            PlaybookIssueResult(
                kind=issue.kind,
                message=issue.message,
                step=issue.step,
                field=list(issue.field) if issue.field is not None else None,
                input=issue.input,
            )
            for issue in playbook.issues(config)
        ]

    def _to_result(self, name: str) -> GetPlaybookResult:
        entry = library_playbooks()[name]
        return GetPlaybookResult(
            name=name,
            doc=entry.doc.model_dump(mode="json"),
            default_config=entry.default_config,
        )
