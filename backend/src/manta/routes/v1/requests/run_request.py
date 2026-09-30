from uuid import UUID

from pydantic import BaseModel


class CreateRunRequest(BaseModel):
    project_uuid: UUID
    playbook: str
    """A library playbook's own name (playbook_library.playbooks.library_playbooks()
    keys by this), not a file path or deployment name."""

    config: dict | None = None
    """The playbook's settings (globals + per-step), filed exactly as
    playbook.playbooks.execution expects them. Omitted means the library's own
    default_config is used.

    TODO: accepted fresh on every request for now. Once playbooks/configs are
    persisted in the database, a run should reference a stored, versioned
    config instead of the caller resupplying one inline each time.
    """

    data_record_url: str
    """Where the starting DataRecord's data lives, e.g. an s3://bucket/key URL."""
