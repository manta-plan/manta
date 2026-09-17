from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CreateRunRequest(BaseModel):
    project_uuid: UUID

    # Legacy demo workflow (the current Runs page): pi digit statistics.
    num_pi_digits: int = Field(default=100_000, gt=0)

    # Playbook runs. `playbook_name` is one of GET /playbooks; `config` replaces the
    # playbook's default settings when given; `input_file` names a file already in
    # the project's storage that the run starts from.
    playbook_name: str | None = None
    config: dict | None = None
    input_file: str | None = None

    @model_validator(mode="after")
    def _playbook_fields_belong_together(self) -> CreateRunRequest:
        if self.playbook_name is None and (self.config is not None or self.input_file is not None):
            raise ValueError("config and input_file only apply to playbook runs: set playbook_name")
        if self.playbook_name is not None and self.input_file is None:
            raise ValueError("a playbook run needs an input_file to start from")
        return self
