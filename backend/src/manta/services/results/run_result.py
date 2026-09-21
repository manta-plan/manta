from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from manta.services.results.s3_file_result import GetS3FileResult


class CreateRunResult(BaseModel):
    uuid: UUID
    project_uuid: UUID
    created_at: datetime
    playbook_name: str | None = None


class GetRunResult(BaseModel):
    uuid: UUID
    project_uuid: UUID
    status: str
    created_at: datetime
    playbook_name: str | None = None


class GetRunSummaryResult(BaseModel):
    total: int
    statuses: dict[str, int]


class ListRunsResult(BaseModel):
    items: list[GetRunResult]
    total: int
    limit: int
    offset: int
    summary: GetRunSummaryResult


class GetRunLogsResult(BaseModel):
    uuid: UUID
    logs: list[str]
    run_status: str


class GetRunStepResult(BaseModel):
    name: str
    """The step's flow-run name, `<step>[<block>]`."""
    status: str


class GetRunStepsResult(BaseModel):
    uuid: UUID
    run_status: str
    steps: list[GetRunStepResult]


class GetRunStepLogsResult(BaseModel):
    uuid: UUID
    step: str
    step_status: str
    logs: list[str]


class ListRunOutputsResult(BaseModel):
    uuid: UUID
    items: list[GetS3FileResult]
