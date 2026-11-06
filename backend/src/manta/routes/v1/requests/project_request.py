from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=3, max_length=128)
    description: str | None = None


class UpdateProjectRequest(BaseModel):
    """A partial update: only the fields sent are changed. Sending
    `"description": null` clears the description; `name` can't be cleared."""

    name: str | None = Field(default=None, min_length=3, max_length=128)
    description: str | None = None

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one of name or description is required")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class ListProjectsRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, min_length=1)
    created_from: datetime | None = None
    created_to: datetime | None = None
    updated_from: datetime | None = None
    updated_to: datetime | None = None
    order_by: Literal["name", "created_at", "updated_at"] = "created_at"
    order: Literal["asc", "desc"] = "desc"

    @model_validator(mode="after")
    def _check_ranges(self) -> Self:
        if self.created_from and self.created_to and self.created_from > self.created_to:
            raise ValueError("created_from must be before created_to")
        if self.updated_from and self.updated_to and self.updated_from > self.updated_to:
            raise ValueError("updated_from must be before updated_to")
        return self
