from uuid import UUID

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    project_uuid: UUID
    num_pi_digits: int = Field(default=100_000, gt=0)
