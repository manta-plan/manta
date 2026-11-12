from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProjectResult(BaseModel):
    uuid: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class ListProjectsResult(BaseModel):
    items: list[ProjectResult]
    total: int
    limit: int
    offset: int
