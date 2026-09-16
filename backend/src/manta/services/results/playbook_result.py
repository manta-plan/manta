from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PlaybookSummaryResult(BaseModel):
    uuid: UUID
    name: str
    description: str | None
    created_at: datetime


class GetPlaybookResult(BaseModel):
    uuid: UUID
    name: str
    description: str | None
    doc: dict
    default_config: dict
    created_at: datetime


class ListPlaybooksResult(BaseModel):
    items: list[PlaybookSummaryResult]
    total: int


class PlaybookIssueResult(BaseModel):
    """One problem found in a playbook + config combination.

    Mirrors manta_playbooks' PlaybookIssue, flattened for the API: `step` and
    `field` become readable dotted paths a UI can point at directly.
    """

    kind: str
    message: str
    step: str | None = None
    field: str | None = None
    input: str | None = None


class ValidatePlaybookResult(BaseModel):
    valid: bool
    issues: list[PlaybookIssueResult]


class CreatePlaybookRunResult(BaseModel):
    uuid: UUID
    project_uuid: UUID
    playbook_uuid: UUID
    input_key: str
    created_at: datetime


class RunOutputFileResult(BaseModel):
    key: str
    size: int
    last_modified: datetime
    url: str
    """The record url a block would know this file by (s3://bucket/key)."""


class GetRunOutputsResult(BaseModel):
    uuid: UUID
    items: list[RunOutputFileResult]
