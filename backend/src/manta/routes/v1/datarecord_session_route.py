from uuid import UUID

from fastapi import APIRouter, Depends, Response, Security, status

from manta.entities import User
from manta.routes.v1.requests.datarecord_session_request import (
    PutDatarecordSessionRegistrationRequest,
    RegistrationName,
)
from manta.services.auth_service import authenticated_user
from manta.services.datarecord_session_service import DatarecordSessionService
from manta.services.results.datarecord_session_result import (
    DatarecordSessionRegistrationResult,
    OpenDatarecordSessionResult,
)

router = APIRouter(
    prefix="/projects/{project_uuid}/datarecord-session", tags=["datarecord-session"]
)


@router.post(
    "",
    response_model=OpenDatarecordSessionResult,
    responses={
        status.HTTP_207_MULTI_STATUS: {
            "model": OpenDatarecordSessionResult,
            "description": "The session is open, but the replay skipped the registrations "
            "in `skipped_registrations`",
        },
    },
)
def open_datarecord_session(
    project_uuid: UUID,
    response: Response,
    service: DatarecordSessionService = Depends(),
    current_user: User = Security(authenticated_user),
) -> OpenDatarecordSessionResult:
    result = service.open(project_uuid, user=current_user)
    if result.skipped_registrations:
        response.status_code = status.HTTP_207_MULTI_STATUS
    return result


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def suspend_datarecord_session(
    project_uuid: UUID,
    service: DatarecordSessionService = Depends(),
    current_user: User = Security(authenticated_user),
) -> None:
    service.suspend(project_uuid, user=current_user)


@router.get("/registrations/{name}", response_model=DatarecordSessionRegistrationResult)
def get_datarecord_session_registration(
    project_uuid: UUID,
    name: RegistrationName,
    service: DatarecordSessionService = Depends(),
    current_user: User = Security(authenticated_user),
) -> DatarecordSessionRegistrationResult:
    return service.get_registration(project_uuid, user=current_user, name=name)


@router.put("/registrations/{name}", response_model=DatarecordSessionRegistrationResult)
def put_datarecord_session_registration(
    project_uuid: UUID,
    name: RegistrationName,
    request: PutDatarecordSessionRegistrationRequest,
    service: DatarecordSessionService = Depends(),
    current_user: User = Security(authenticated_user),
) -> DatarecordSessionRegistrationResult:
    return service.put_registration(
        project_uuid,
        user=current_user,
        name=name,
        kind=request.kind,
        store=request.store,
        revision=request.revision,
        packs=request.packs,
    )


@router.delete("/registrations/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_datarecord_session_registration(
    project_uuid: UUID,
    name: RegistrationName,
    service: DatarecordSessionService = Depends(),
    current_user: User = Security(authenticated_user),
) -> None:
    service.delete_registration(project_uuid, user=current_user, name=name)
