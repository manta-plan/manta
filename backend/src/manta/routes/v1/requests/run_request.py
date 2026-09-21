from uuid import UUID

from pydantic import BaseModel


class CreateRunRequest(BaseModel):
    project_uuid: UUID

    # `playbook_name` is one of GET /playbooks; `config` replaces the playbook's
    # default settings when given; `input_file` names a file already in the
    # project's storage that the run starts from.
    playbook_name: str
    config: dict | None = None
    input_file: str
