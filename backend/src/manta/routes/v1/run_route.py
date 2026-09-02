from uuid import UUID

from fastapi import APIRouter, Depends, status

from manta.routes.v1.requests.run_request import CreateRunRequest
from manta.services.results.run_result import (
    CreateRunResult,
    GetRunLogsResult,
    GetRunResult,
)
from manta.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=CreateRunResult, status_code=status.HTTP_201_CREATED)
def create_run(request: CreateRunRequest, service: RunService = Depends()) -> CreateRunResult:
    return service.create_run(
        project_uuid=request.project_uuid, num_pi_digits=request.num_pi_digits
    )


@router.get("/{run_uuid}", response_model=GetRunResult)
def get_run(run_uuid: UUID, service: RunService = Depends()) -> GetRunResult:
    return service.get_run(run_uuid)


@router.get("/{run_uuid}/logs", response_model=GetRunLogsResult)
def get_run_logs(run_uuid: UUID, service: RunService = Depends()) -> GetRunLogsResult:
    return service.get_run_logs(run_uuid)
