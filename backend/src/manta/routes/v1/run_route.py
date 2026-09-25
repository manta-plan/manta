from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security, status

from manta.entities import User
from manta.routes.v1.requests.list_runs_request import ListRunsRequest
from manta.routes.v1.requests.run_request import CreateRunRequest
from manta.services.auth_service import authenticated_user
from manta.services.results.run_result import (
    CreateRunResult,
    GetRunLogsResult,
    GetRunResult,
    GetRunSummaryResult,
    ListRunsResult,
)
from manta.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=CreateRunResult, status_code=status.HTTP_201_CREATED)
def create_run(
    request: CreateRunRequest,
    user: User = Security(authenticated_user),
    service: RunService = Depends(),
) -> CreateRunResult:
    return service.create_run(
        project_uuid=request.project_uuid, num_pi_digits=request.num_pi_digits, user=user
    )


@router.get("", response_model=ListRunsResult)
def list_runs(
    request: Annotated[ListRunsRequest, Query()],
    user: User = Security(authenticated_user),
    service: RunService = Depends(),
) -> ListRunsResult:
    return service.list_runs(
        project_uuid=request.project_uuid,
        limit=request.limit,
        offset=request.offset,
        status_filters=request.statuses,
        user=user,
    )


@router.get("/summary", response_model=GetRunSummaryResult)
def get_run_summary(
    project_uuid: UUID,
    user: User = Security(authenticated_user),
    service: RunService = Depends(),
) -> GetRunSummaryResult:
    return service.get_run_summary(project_uuid, user=user)


@router.get("/{run_uuid}", response_model=GetRunResult)
def get_run(
    run_uuid: UUID,
    user: User = Security(authenticated_user),
    service: RunService = Depends(),
) -> GetRunResult:
    return service.get_run(run_uuid, user=user)


@router.get("/{run_uuid}/logs", response_model=GetRunLogsResult)
def get_run_logs(
    run_uuid: UUID,
    user: User = Security(authenticated_user),
    service: RunService = Depends(),
) -> GetRunLogsResult:
    return service.get_run_logs(run_uuid, user=user)
