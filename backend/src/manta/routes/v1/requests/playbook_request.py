from uuid import UUID

from pydantic import BaseModel, Field


class ValidatePlaybookRequest(BaseModel):
    config: dict = Field(default_factory=dict)


class CreatePlaybookRunRequest(BaseModel):
    project_uuid: UUID
    # The input data's key in the app bucket. A stopgap until data records are
    # first-class (uploads, catalogue of datasets): for now something else must
    # have put the file there, e.g. manta_batteries.examples.seed_network.
    input_key: str = Field(min_length=1)
    # Settings for this run; the playbook's default_config when omitted.
    config: dict | None = None
