from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreateRunResult(BaseModel):
    uuid: UUID
    project_uuid: UUID
    created_at: datetime


class GetRunResult(BaseModel):
    uuid: UUID
    project_uuid: UUID
    status: str
    created_at: datetime


class GetRunLogsResult(BaseModel):
    logs: list[str]
    run_status: str
