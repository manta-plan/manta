from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreateRunResult(BaseModel):
    uuid: UUID
    project_uuid: UUID
    created_at: datetime


class GetRunResult(BaseModel):
    uuid: UUID
    # `None` when the run's project has since been deleted (`Run.project_id`
    # is set to NULL rather than cascade-deleting the run).
    project_uuid: UUID | None
    status: str
    created_at: datetime


class GetRunLogsResult(BaseModel):
    uuid: UUID
    logs: list[str]
    run_status: str
