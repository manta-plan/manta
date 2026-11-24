from typing import Annotated, Literal
from uuid import UUID

from fastapi import Path
from pydantic import BaseModel

RegistrationName = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")]


class PutDatarecordSessionRegistrationRequest(BaseModel):
    kind: Literal["view"]
    store: str
    revision: UUID
    packs: list[str] = []
