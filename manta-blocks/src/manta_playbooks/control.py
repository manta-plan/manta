# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""The front door for anything driving playbooks from outside - the Manta interface.

A user picks blocks, wires them up, fills in settings, and presses Run. That comes
down to three things, and this module is all three:

- `deploy`, which makes sure everything the playbook needs is ready to run,
- `start_run`, which starts it and returns straight away,
- `run_status`, which says how it is getting on.

A run outlives the request that started it, so it is handed to Prefect rather than run
here: the answer to "is it finished?" then survives a restart of whatever asked.
"""

from uuid import UUID

from prefect.deployments import run_deployment
from pydantic import BaseModel, ConfigDict, Field

from manta_blocks import Catalogue, DataRecord, current_env
from manta_playbooks.deploy import ProcessPixiRenderer, Renderer, deployment_plan
from manta_playbooks.execution import (
    catalogue_parameter,
    orchestrator_path,
    run_playbook,
)
from manta_playbooks.playbook import Playbook
from manta_playbooks.yaml_io import PlaybookDoc, playbook_from_doc


class WorkPoolMissingError(Exception):
    """Raised when a playbook cannot be deployed because its work pools do not exist."""


class RunInfo(BaseModel):
    """A run that has just been started."""

    model_config = ConfigDict(frozen=True)

    flow_run_id: str
    name: str
    dashboard_url: str | None = None
    """Where to watch the run in the Prefect interface, if it has one."""


class RunStatus(BaseModel):
    """How a run is getting on."""

    model_config = ConfigDict(frozen=True)

    flow_run_id: str
    state: str
    """Prefect's own word for it: RUNNING, COMPLETED, FAILED, and so on."""

    steps: dict[str, str] = Field(default_factory=dict)
    """Each step that has started, and the state it is in."""

    result: dict | None = None
    """Where the finished playbook wrote its result, once it has."""


def deploy(
    playbook: Playbook,
    config: dict,
    renderer: Renderer | None = None,
    orchestrator_env: str | None = None,
) -> None:
    """Make everything `playbook` needs ready to run.

    The playbook is checked first, so a playbook that could not run is never
    half-deployed. Deploying the same playbook again is harmless: each deployment is
    created or updated, never duplicated.
    """
    playbook.validate_playbook(config)
    renderer = renderer or ProcessPixiRenderer()
    plan = deployment_plan(playbook, config)

    try:
        renderer.apply(plan)
        _deploy_orchestrator(orchestrator_env or current_env())
    except Exception as exc:
        raise _explain_deploy_failure(exc, renderer, plan) from exc


def _deploy_orchestrator(env: str) -> None:
    """Deploy the flow that runs whole playbooks, so a run can be started remotely."""
    run_playbook.to_deployment(name=env, work_pool_name=f"manta-{env}").apply()


def _explain_deploy_failure(exc: Exception, renderer: Renderer, plan) -> Exception:
    """Turn a work-pool complaint from Prefect into something actionable."""
    if "work pool" not in str(exc).lower():
        return exc
    commands = "\n".join(
        f"  {command}" for command in renderer.work_pool_commands(plan)
    )
    return WorkPoolMissingError(
        f"{exc}\n\nThe work pools this playbook needs do not exist yet. Create them "
        f"and start a worker for each:\n{commands}"
    )


def start_run(
    doc: PlaybookDoc,
    config: dict,
    record: DataRecord,
    deploy_first: bool = True,
    catalogue: Catalogue | None = None,
    orchestrator_env: str | None = None,
) -> RunInfo:
    """Start a playbook running, and return as soon as it has been accepted.

    This is what pressing Run comes down to. The playbook is sent as the document it
    was edited as, so what runs is exactly what was on screen.
    """
    env = orchestrator_env or current_env()
    if deploy_first:
        deploy(
            playbook_from_doc(doc, catalogue=catalogue), config, orchestrator_env=env
        )

    flow_run = run_deployment(
        name=orchestrator_path(env),
        parameters={
            "playbook": doc.model_dump(mode="json"),
            "config": config,
            "record": record.to_dict(),
            "catalogue": catalogue_parameter(catalogue),
        },
        timeout=0,
    )
    return RunInfo(
        flow_run_id=str(flow_run.id),
        name=flow_run.name or "",
        dashboard_url=_dashboard_url(flow_run.id),
    )


def _dashboard_url(flow_run_id: UUID) -> str | None:
    from prefect.settings import PREFECT_UI_URL

    base = PREFECT_UI_URL.value()
    return f"{base}/flow-runs/flow-run/{flow_run_id}" if base else None


def run_status(flow_run_id: str) -> RunStatus:
    """How the run with this id is getting on.

    Per-step detail is reported where Prefect can supply it and left out where it
    cannot, so this stays useful rather than failing over a missing detail.
    """
    from prefect.client.orchestration import get_client

    run_uuid = UUID(flow_run_id)
    client = get_client(sync_client=True)
    flow_run = client.read_flow_run(run_uuid)
    state = flow_run.state.type.value if flow_run.state else "UNKNOWN"

    result = None
    if flow_run.state is not None and flow_run.state.is_completed():
        try:
            result = flow_run.state.result(raise_on_failure=False)
        except Exception:
            result = None

    return RunStatus(
        flow_run_id=flow_run_id,
        state=state,
        steps=_step_states(client, run_uuid),
        result=result if isinstance(result, dict) else None,
    )


def _step_states(client, run_uuid: UUID) -> dict[str, str]:
    """Each step of a run and the state it is in, as far as Prefect can tell us.

    Every step runs as its own flow named after the step, so the names line up.
    """
    from prefect.client.schemas.filters import (
        FlowRunFilter,
        FlowRunFilterParentFlowRunId,
    )

    try:
        children = client.read_flow_runs(
            flow_run_filter=FlowRunFilter(
                parent_flow_run_id=FlowRunFilterParentFlowRunId(any_=[run_uuid])
            )
        )
    except Exception:
        return {}

    states: dict[str, str] = {}
    for child in children:
        try:
            name = client.read_flow(child.flow_id).name
        except Exception:
            continue
        states[name] = child.state.type.value if child.state else "UNKNOWN"
        states.update(
            {
                f"{name}/{inner}": inner_state
                for inner, inner_state in _step_states(client, child.id).items()
            }
        )
    return states
