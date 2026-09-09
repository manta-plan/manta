from uuid import UUID

from fastapi import APIRouter, Depends, status

from manta.routes.v1.requests.list_runs_request import ListRunsRequest
from manta.routes.v1.requests.run_request import CreateRunRequest
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
def create_run(request: CreateRunRequest, service: RunService = Depends()) -> CreateRunResult:
    return service.create_run(
        project_uuid=request.project_uuid, num_pi_digits=request.num_pi_digits
    )


@router.get("", response_model=ListRunsResult)
def list_runs(
    request: ListRunsRequest = Depends(),
    service: RunService = Depends(),
) -> ListRunsResult:
    return service.list_runs(
        project_uuid=request.project_uuid,
        limit=request.limit,
        offset=request.offset,
        status_filters=request.statuses,
    )


@router.get("/summary", response_model=GetRunSummaryResult)
def get_run_summary(project_uuid: UUID, service: RunService = Depends()) -> GetRunSummaryResult:
    return service.get_run_summary(project_uuid)


@router.get("/{run_uuid}", response_model=GetRunResult)
def get_run(run_uuid: UUID, service: RunService = Depends()) -> GetRunResult:
    return service.get_run(run_uuid)


@router.get("/{run_uuid}/logs", response_model=GetRunLogsResult)
def get_run_logs(run_uuid: UUID, service: RunService = Depends()) -> GetRunLogsResult:
    return service.get_run_logs(run_uuid)
