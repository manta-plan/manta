from pydantic import BaseModel


class ValidatePlaybookConfigRequest(BaseModel):
    config: dict | None = None
    """The config to check, exactly as it would be sent to POST /v1/runs: values filed
    by step name, plus an `inputs` section with the input values of the run. Omitted means the
    playbook's own default_config, which is what a run created without a config
    uses."""
