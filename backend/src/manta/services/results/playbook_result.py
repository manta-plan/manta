from typing import Any

from pydantic import BaseModel


class PlaybookStepSummaryResult(BaseModel):
    name: str
    """The step's own name within its playbook, e.g. `dispatch`. Settings are filed
    under this name in a run's config, since the same block can be used by more than
    one step."""

    block: str | None
    """The name of the block this step runs, e.g. `rolling_horizon_dispatch`. None
    for a step that runs a nested playbook instead of a block."""


class PlaybookSummaryResult(BaseModel):
    name: str
    """The playbook's own name — what a run is created with (see
    CreateRunRequest.playbook)."""

    steps: list[PlaybookStepSummaryResult]


class ListPlaybooksResult(BaseModel):
    items: list[PlaybookSummaryResult]
    total: int


class PlaybookStepConditionResult(BaseModel):
    """A step only runs when the config value at `config` (a dotted path, e.g.
    `globals.expansion_mode`) equals `equals`."""

    config: str
    equals: Any


class PlaybookStepResult(BaseModel):
    name: str
    """The step's own name within its playbook — see PlaybookStepSummaryResult.name."""

    block: str | None
    """The name of the block this step runs — see PlaybookStepSummaryResult.block."""

    block_summary: str | None
    """The block's one-line description (the first line of its docstring)."""

    block_config_schema: dict | None
    """The block's settings, as a JSON schema. The values themselves go in a run's
    config under this step's `name`. Settings tagged `x-manta-input` are filled in by
    another step (see `inputs`), not typed by a user."""

    when: PlaybookStepConditionResult | None
    """None means the step always runs."""

    inputs: dict[str, str]
    """Each wired-in setting, and the `${steps.<step>.<output>}` reference feeding it."""


class GetPlaybookResult(BaseModel):
    name: str
    default_config: dict
    """The config a run uses when it is created without one: values filed by step
    name, plus a `globals` section every step can see."""

    steps: list[PlaybookStepResult]
