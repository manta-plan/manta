from pydantic import BaseModel


class GetPlaybookResult(BaseModel):
    name: str
    doc: dict
    """The playbook document (steps, wiring, conditions), as submitted to a run."""
    default_config: dict
    """Sensible default settings, ready to be edited and sent back with a run."""


class ListPlaybooksResult(BaseModel):
    items: list[GetPlaybookResult]


class PlaybookIssueResult(BaseModel):
    """One problem found when validating a playbook against a config.

    Mirrors manta-blocks' PlaybookIssue: `step` is the step path the problem is
    about (None means the playbook itself), `field` the exact setting where that
    applies — enough for a UI to mark the right box and the right field.
    """

    kind: str
    message: str
    step: str | None = None
    field: list[str | int] | None = None
    input: str | None = None
