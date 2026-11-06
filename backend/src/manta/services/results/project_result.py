from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreateProjectResult(BaseModel):
    uuid: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class GetProjectResult(BaseModel):
    uuid: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class UpdateProjectResult(BaseModel):
    uuid: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class ListProjectsResult(BaseModel):
    items: list[GetProjectResult]
    total: int
    limit: int
    offset: int
