from uuid import UUID

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    project_uuid: UUID
    # Accepted but not persisted yet — there's no `name` column on `runs`.
    # Dropped at the service layer until named runs are actually supported.
    name: str = Field(min_length=1)
    playbook_id: str
    # One entry per playbook node, in the same order as the playbook's own
    # `nodes` list (see GET /v1/playbooks/:id) — not keyed by node id.
    playbook_config: list[dict[str, int]] = Field(default_factory=list)
