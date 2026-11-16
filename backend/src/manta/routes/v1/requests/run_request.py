from uuid import UUID

from pydantic import BaseModel


class PlaybookRequest(BaseModel):
    name: str
    """A library playbook's own name (playbook_library.playbooks.library_playbooks()
    keys by this), not a file path or deployment name."""

    config: dict | None = None
    """The playbook's settings (globals + per-step), filed exactly as
    playbook.playbooks.execution expects them. Omitted means the library's own
    default_config is used. Either way it is checked before anything is dispatched,
    and a config the playbook cannot run with is refused with a 422 listing every
    issue (see PlaybookIssueResult).

    TODO: accepted fresh on every request for now. Once playbooks/configs are
    persisted in the database, a run should reference a stored, versioned
    config instead of the caller resupplying one inline each time.
    """


class DataRecordRequest(BaseModel):
    store_url: str
    """The datarecord store the run starts from and writes its revisions into, e.g.
    s3://<bucket>/<project uuid>/<store>. Must be within the project's own storage."""

    revision_uuid: UUID
    """The revision of that store the run starts from. Must exist."""


class CreateRunRequest(BaseModel):
    project_uuid: UUID
    playbook: PlaybookRequest
    data_record: DataRecordRequest
