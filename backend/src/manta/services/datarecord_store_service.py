import json
import re
from datetime import datetime
from functools import cache
from uuid import UUID

from datarecord import Store, Workspace
from fastapi import Depends, HTTPException
from pydantic import BaseModel

from manta.config.datarecord_config import datarecord_root, get_datarecord_workspace
from manta.entities import User
from manta.services.errors import BackendError
from manta.services.results.datarecord_store_result import (
    DatarecordReferenceResult,
    DatarecordRevisionResult,
    DatarecordStoreResult,
    ListDatarecordRevisionsResult,
    ListDatarecordStoresResult,
)
from manta.services.user_service import UserService

STORE_FILE = "store.json"

STORE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class _StoreReference(BaseModel):
    revision: UUID
    label: str
    base: str | None = None
    description: str | None = None


class _StoreFile(BaseModel):
    label: str
    description: str | None = None
    references: dict[str, _StoreReference]


class DatarecordStoreService:
    def __init__(
        self,
        workspace: Workspace = Depends(get_datarecord_workspace),
        root: str = Depends(datarecord_root),
        user_service: UserService = Depends(),
    ) -> None:
        self.workspace = workspace
        self.root = root
        self.user_service = user_service

    def list_stores(self, project_uuid: UUID, user: User) -> ListDatarecordStoresResult:
        self.user_service.get_owned_project(project_uuid, user)
        prefix = f"{self.root}/{project_uuid}"
        files = self.workspace.files(prefix)
        found = {
            name: self._store_file(project_uuid, name)
            for name in files.list(f"{prefix}/")
            if STORE_NAME.fullmatch(name)
        }
        return ListDatarecordStoresResult(
            items=[
                DatarecordStoreResult(name=name, label=file.label, description=file.description)
                for name, file in sorted(found.items())
                if file is not None
            ]
        )

    def list_revisions(
        self, project_uuid: UUID, store: str, user: User
    ) -> ListDatarecordRevisionsResult:
        self.user_service.get_owned_project(project_uuid, user)
        file = self._store_file(project_uuid, store)
        if file is None:
            raise HTTPException(
                status_code=404, detail=f"Store {store!r} not found in project {project_uuid}"
            )
        dr_store = self.workspace.store(f"{self.root}/{project_uuid}/{store}")
        committed = [
            DatarecordRevisionResult.from_revision(revision, _claimed_at(dr_store, revision.id))
            for revision in dr_store.revisions()
        ]
        claimed = [DatarecordRevisionResult.from_claim(claim) for claim in dr_store.claims()]
        revisions = sorted(committed + claimed, key=lambda revision: revision.created_at)
        kinds = {revision.id: revision.kind for revision in revisions}
        dangling = [name for name, ref in file.references.items() if ref.revision not in kinds]
        if dangling:
            raise BackendError(
                detail=f"Store {store!r} in project {project_uuid} references missing "
                f"revisions in {dangling}"
            )
        return ListDatarecordRevisionsResult(
            store=store,
            revisions=revisions,
            references=[
                DatarecordReferenceResult(
                    name=name,
                    kind=kinds[reference.revision],
                    revision=reference.revision,
                    base=reference.base,
                    label=reference.label,
                    description=reference.description,
                )
                for name, reference in file.references.items()
            ],
        )

    def _store_file(self, project_uuid: UUID, store: str) -> _StoreFile | None:
        uri = f"{self.root}/{project_uuid}/{store}/{STORE_FILE}"
        text = self.workspace.files(uri).read_text(uri)
        return None if text is None else _StoreFile.model_validate_json(text)


@cache
def _claimed_at(store: Store, revision_id: UUID) -> datetime:
    return store.claim_from(json.dumps({"id": str(revision_id), "store": store.uri})).created
