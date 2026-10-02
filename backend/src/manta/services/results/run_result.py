from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreateRunResult(BaseModel):
    uuid: UUID
    project_uuid: UUID
    playbook: str
    created_at: datetime


class GetRunResult(BaseModel):
    uuid: UUID
    project_uuid: UUID
    playbook: str
    config: dict
    """The config this run was started with, exactly as dispatched: the caller's own,
    or the playbook's default_config when none was given (see GET /v1/playbooks/{name}
    for those defaults)."""

    status: str
    created_at: datetime


class GetRunSummaryResult(BaseModel):
    total: int
    statuses: dict[str, int]


class ListRunsResult(BaseModel):
    items: list[GetRunResult]
    total: int
    limit: int
    offset: int
    summary: GetRunSummaryResult


class RunStepResult(BaseModel):
    name: str
    """The step's own name within its playbook, e.g. `dispatch` (see
    PlaybookStepResult.name)."""

    block: str | None
    """The name of the block this step runs, e.g. `rolling_horizon_dispatch`. None
    for a step that runs a nested playbook instead of a block."""

    status: str
    """Prefect's own state for the step's block run (COMPLETED, RUNNING, FAILED, ...),
    or, for a step with no block run:

    - SKIPPED: its `when` condition is false for this run's config, so it never runs.
    - NOT_STARTED: it should run, but hasn't started yet — or never will, if an
      earlier step failed.
    - UNKNOWN: it runs a nested playbook, whose own steps aren't tracked here yet.
    """

    start_time: datetime | None
    end_time: datetime | None


class GetRunStepsResult(BaseModel):
    uuid: UUID
    steps: list[RunStepResult]
    """Every step of the run's playbook, in playbook order."""

    run_status: str


class GetRunLogsResult(BaseModel):
    uuid: UUID
    logs: list[str]
    run_status: str
