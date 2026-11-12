from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security, status

from manta.entities import User
from manta.routes.v1.requests.project_request import (
    CreateProjectRequest,
    ListProjectsRequest,
    UpdateProjectRequest,
)
from manta.services.auth_service import authenticated_user
from manta.services.project_changes import UpdateProjectChanges
from manta.services.project_service import ProjectService
from manta.services.results.project_result import ListProjectsResult, ProjectResult

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectResult,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    request: CreateProjectRequest,
    service: ProjectService = Depends(),
    current_user: User = Security(authenticated_user),
) -> ProjectResult:
    return service.create_project(
        name=request.name, description=request.description, owner=current_user
    )


@router.get("", response_model=ListProjectsResult)
def list_projects(
    request: Annotated[ListProjectsRequest, Query()],
    service: ProjectService = Depends(),
    current_user: User = Security(authenticated_user),
) -> ListProjectsResult:
    return service.list_projects(
        limit=request.limit,
        offset=request.offset,
        user=current_user,
        name=request.name,
        description=request.description,
        created_from=request.created_from,
        created_to=request.created_to,
        updated_from=request.updated_from,
        updated_to=request.updated_to,
        order_by=request.order_by,
        order=request.order,
    )


@router.get("/{project_uuid}", response_model=ProjectResult)
def get_project(
    project_uuid: UUID,
    service: ProjectService = Depends(),
    current_user: User = Security(authenticated_user),
) -> ProjectResult:
    return service.get_project(project_uuid, user=current_user)


@router.patch("/{project_uuid}", response_model=ProjectResult)
def update_project(
    project_uuid: UUID,
    request: UpdateProjectRequest,
    service: ProjectService = Depends(),
    current_user: User = Security(authenticated_user),
) -> ProjectResult:
    return service.update_project(
        project_uuid,
        changes=UpdateProjectChanges(**request.model_dump(exclude_unset=True)),
        user=current_user,
    )


@router.delete("/{project_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_uuid: UUID,
    service: ProjectService = Depends(),
    current_user: User = Security(authenticated_user),
) -> None:
    service.delete_project(project_uuid, user=current_user)
