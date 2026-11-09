from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security, status
from fastapi.responses import StreamingResponse

from manta.entities import User
from manta.routes.v1.requests.list_runs_request import ListRunsRequest
from manta.routes.v1.requests.run_request import CreateRunRequest
from manta.services.auth_service import authenticated_user
from manta.services.results.run_result import (
    CreateRunResult,
    GetRunLogsResult,
    GetRunResult,
    GetRunStepsResult,
    GetRunSummaryResult,
    ListRunOutputsResult,
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
        project_uuid=request.project_uuid,
        playbook=request.playbook,
        config=request.config,
        data_record_url=request.data_record_url,
        user=user,
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


@router.get("/{run_uuid}/steps", response_model=GetRunStepsResult)
def get_run_steps(
    run_uuid: UUID,
    user: User = Security(authenticated_user),
    service: RunService = Depends(),
) -> GetRunStepsResult:
    return service.get_run_steps(run_uuid, user=user)


@router.get("/{run_uuid}/outputs", response_model=ListRunOutputsResult)
def list_run_outputs(
    run_uuid: UUID,
    user: User = Security(authenticated_user),
    service: RunService = Depends(),
) -> ListRunOutputsResult:
    return service.list_run_outputs(run_uuid, user=user)


# `:path`, so an output in a subfolder (a nested playbook's) can be named too.
@router.get("/{run_uuid}/outputs/{name:path}", response_class=StreamingResponse)
def get_run_output(
    run_uuid: UUID,
    name: str,
    user: User = Security(authenticated_user),
    service: RunService = Depends(),
) -> StreamingResponse:
    # TODO: moves to data_record_route.py once data records exist — see
    # the TODO on RunService._list_run_output_files.
    output = service.get_run_output(run_uuid, name, user=user)
    # Always the percent-encoded `filename*` form of Content-Disposition, which
    # stays valid whatever characters a step name contains.
    filename = quote(PurePosixPath(name).name)
    # Streamed through the backend chunk by chunk, so the client never talks to
    # S3 itself and the file is never held in memory whole.
    return StreamingResponse(
        output.content,
        media_type=output.content_type,
        headers={
            "Content-Length": str(output.size),
            "Content-Disposition": f"attachment; filename*=utf-8''{filename}",
        },
    )


@router.get("/{run_uuid}/logs", response_model=GetRunLogsResult)
def get_run_logs(
    run_uuid: UUID,
    user: User = Security(authenticated_user),
    service: RunService = Depends(),
) -> GetRunLogsResult:
    return service.get_run_logs(run_uuid, user=user)
