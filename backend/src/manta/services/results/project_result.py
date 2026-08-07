from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreateProjectResult(BaseModel):
    uuid: UUID
    name: str
    description: str | None
    created_at: datetime
