from uuid import UUID

from fastapi import APIRouter, Depends, Security

from manta.entities import User
from manta.routes.v1.requests.datarecord_store_request import StoreName
from manta.services.auth_service import authenticated_user
from manta.services.datarecord_store_service import DatarecordStoreService
from manta.services.results.datarecord_store_result import (
    ListDatarecordRevisionsResult,
    ListDatarecordStoresResult,
)

router = APIRouter(prefix="/projects", tags=["datarecord-stores"])


@router.get("/{project_uuid}/datarecord-stores", response_model=ListDatarecordStoresResult)
def list_datarecord_stores(
    project_uuid: UUID,
    service: DatarecordStoreService = Depends(),
    current_user: User = Security(authenticated_user),
) -> ListDatarecordStoresResult:
    return service.list_stores(project_uuid, user=current_user)


@router.get(
    "/{project_uuid}/datarecord-stores/{store}/datarecord-revisions",
    response_model=ListDatarecordRevisionsResult,
)
def list_datarecord_revisions(
    project_uuid: UUID,
    store: StoreName,
    service: DatarecordStoreService = Depends(),
    current_user: User = Security(authenticated_user),
) -> ListDatarecordRevisionsResult:
    return service.list_revisions(project_uuid, store, user=current_user)
