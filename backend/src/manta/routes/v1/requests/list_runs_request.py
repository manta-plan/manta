from uuid import UUID

from pydantic import BaseModel, Field


class ListRunsRequest(BaseModel):
    project_uuid: UUID
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    statuses: list[str] | None = None
