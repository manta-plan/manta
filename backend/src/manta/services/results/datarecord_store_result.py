from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from datarecord import Claim, Revision
from pydantic import BaseModel

_MANTA = "manta."


class DatarecordStoreResult(BaseModel):
    name: str
    label: str
    description: str | None


class ListDatarecordStoresResult(BaseModel):
    items: list[DatarecordStoreResult]


class DatarecordRevisionResult(BaseModel):
    id: UUID
    parent: UUID | None
    status: Literal["claimed", "committed"]
    kind: str | None
    created_by: str | None
    run: UUID | None
    step: str | None
    created_at: datetime
    committed_at: datetime | None
    meta: dict[str, Any]

    @classmethod
    def from_revision(cls, revision: Revision, created_at: datetime) -> Self:
        return cls._from_entry(revision, "committed", created_at)

    @classmethod
    def from_claim(cls, claim: Claim) -> Self:
        return cls._from_entry(claim, "claimed", claim.created)

    @classmethod
    def _from_entry(
        cls,
        entry: Revision | Claim,
        status: Literal["claimed", "committed"],
        created_at: datetime,
    ) -> Self:
        manta = {
            key.removeprefix(_MANTA): value
            for key, value in entry.meta.items()
            if key.startswith(_MANTA)
        }
        return cls(
            id=entry.id,
            parent=entry.parent,
            status=status,
            kind=manta.get("kind"),
            created_by=manta.get("created_by"),
            run=manta.get("run"),
            step=manta.get("step"),
            created_at=created_at,
            committed_at=manta.get("committed_at") if status == "committed" else None,
            meta={key: value for key, value in entry.meta.items() if not key.startswith(_MANTA)},
        )


class DatarecordReferenceResult(BaseModel):
    name: str
    kind: str | None
    revision: UUID
    base: str | None
    label: str
    description: str | None


class ListDatarecordRevisionsResult(BaseModel):
    store: str
    revisions: list[DatarecordRevisionResult]
    references: list[DatarecordReferenceResult]
