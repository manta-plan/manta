from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ListRunsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_uuid: UUID
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    statuses: list[str] | None = Field(default=None, alias="status")
