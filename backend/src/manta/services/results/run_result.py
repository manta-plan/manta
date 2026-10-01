from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreateRunResult(BaseModel):
    uuid: UUID
    project_uuid: UUID
    playbook: str
    created_at: datetime


class GetRunResult(BaseModel):
    uuid: UUID
    project_uuid: UUID
    playbook: str
    status: str
    created_at: datetime


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
