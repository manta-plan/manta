from typing import Self
from uuid import UUID

from pydantic import BaseModel

from manta.entities import DatarecordSessionRegistration


class QuackConnectionResult(BaseModel):
    uri: str
    token: str


class OpenDatarecordSessionResult(BaseModel):
    status: str
    generation: int
    quack: QuackConnectionResult
    skipped_registrations: list[str]


class DatarecordSessionRegistrationResult(BaseModel):
    name: str
    prefix: str
    kind: str
    store: str
    revision: UUID
    packs: list[str]

    @classmethod
    def from_registration(cls, registration: DatarecordSessionRegistration, prefix: str) -> Self:
        return cls(
            name=registration.name,
            prefix=prefix,
            kind=registration.kind,
            store=registration.store,
            revision=registration.revision_uuid,
            packs=registration.packs,
        )
