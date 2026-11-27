# SPDX-FileCopyrightText: Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

"""The two Prefect flows every playbook run is made of.

`run-playbook` walks a playbook document with `playbook`'s engine and dispatches
each step to `run-block`. Every `run-block` flow run is picked up by the docker
work pool, so each step executes in its own throwaway container from that
environment's execution image.

Both flows are deployed once, statically (see `deploy.py`). Playbooks are data
passed in as parameters, so nothing is ever deployed per playbook or per block.

Everything passed in has crossed a process boundary, so revisions arrive as plain
`{"store": ..., "id": ...}` data (`RevisionRef.to_dict()`): a store and one of its
revisions. A loaded model could never travel this way, which is exactly why blocks
pass pointers to data rather than the data itself.
"""

import json
import logging
import time
from contextlib import closing
from uuid import UUID

from playbook.blocks import BlockSpec, Catalogue, RevisionRef
from playbook.blocks.registry import get_block, load_block_sources
from playbook.playbooks import execute_playbook, parse_doc, playbook_from_doc
from prefect import flow
from prefect.artifacts import create_table_artifact
from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import (
    ArtifactFilter,
    ArtifactFilterFlowRunId,
    ArtifactFilterKey,
)
from prefect.client.schemas.objects import FlowRun
from prefect.deployments import run_deployment
from prefect.states import Cancelling

from runner.config import block_timeout_seconds, exec_image, playbook_timeout_seconds

logger = logging.getLogger(__name__)

BLOCK_FLOW_NAME = "run-block"
PLAYBOOK_FLOW_NAME = "run-playbook"

OUTPUT_ARTIFACT_KEY = "block-output"
"""The key of the one-row table artifact `run-block` publishes its output revision as.
It is how that revision travels back out of the block's container: to the orchestrator,
which hands it to the next step, and to Manta's backend, which reports it."""

TIMED_OUT_STATE_NAME = "TimedOut"
"""The name Prefect gives the `FAILED` state of a flow run that exceeded its timeout,
or that raised a `TimeoutError`. Nothing else tells a timeout from another failure:
`PrefectBlockRunner` reads it off a step, and Manta's backend off a run."""

BLOCK_POLL_SECONDS = 5
"""How often `PrefectBlockRunner` asks whether a step has finished. The same interval
`run_deployment` polls at when it does the waiting itself."""


def deployment_name(flow_name: str) -> str:
    """A flow's deployment, in Prefect's own `"<flow>/<deployment>"` form.

    Every flow here has exactly one deployment (see `deploy.py`), and that
    deployment's own name is simply the flow's name — so this is the one place
    that turns a flow name into the string `run_deployment`/`to_deployment` need,
    rather than writing `f"{name}/{name}"` at each call site.
    """
    return f"{flow_name}/{flow_name}"


BLOCK_DEPLOYMENT = deployment_name(BLOCK_FLOW_NAME)
PLAYBOOK_DEPLOYMENT = deployment_name(PLAYBOOK_FLOW_NAME)
"""What a caller dispatches a playbook run at, once `deploy.py` has run."""


class BlockRunFailedError(Exception):
    """Raised when a step's flow run did not complete."""


class BlockTimedOutError(BlockRunFailedError, TimeoutError):
    """Raised when a step's flow run exceeded the block timeout.

    A `TimeoutError` on purpose: Prefect ends a flow run that raises one as timed
    out, so the playbook run reports the timeout as well, not a failure of some
    other kind.
    """


def catalogue_parameter(catalogue: Catalogue) -> str:
    """Encode a catalogue for crossing Prefect as a `run-playbook` parameter.

    Must be a JSON **string**, never a dict: Prefect walks dict flow parameters
    and resolves any `{"$ref": ...}` inside them as its own block-document
    reference. A catalogue of JSON schemas is full of `$ref`s, so passing one as
    a dict crashes the flow run with "Block document ID '#/$defs/...' is not a
    valid UUID". `run_playbook` decodes it with `parse_catalogue_parameter`.
    """
    return catalogue.model_dump_json()


def parse_catalogue_parameter(raw: str) -> Catalogue:
    """The inverse of `catalogue_parameter`."""
    return Catalogue.model_validate_json(raw)


@flow(
    name=BLOCK_FLOW_NAME,
    # Fills in from this flow's own call parameters below, not from anything
    # read in the function body — this is the only place `step_name` is used.
    flow_run_name="{step_name}[{block}]",
    # A block's own print()s are part of its log, and solvers are talkative.
    log_prints=True,
    # Read when this module is imported, so in the block's own container (see
    # config.job_environment). Once it passes, Prefect raises inside the block: the
    # flow run ends as timed out, and its container exits and is removed.
    timeout_seconds=block_timeout_seconds(),
)
def run_block(
    block: str,
    step_name: str,
    config: dict,
    revision: dict,
    inputs: dict[str, dict] | None,
) -> dict:
    """Run one block by name, in this container, and report where its result went.

    There is one deployment of this flow, shared by every block: the block to run
    arrives as a parameter, and `step_name` — the name of the step using this
    block within its own playbook, distinct from the block itself since the same
    block can be used by more than one step — only names the flow run above; it
    plays no part in running the block.

    This is the only code in this runtime that runs inside a block's own
    environment, and it does not import a block until asked for one by name.
    """
    # Imported here: only a block's own image installs `playbook[run]`, and the
    # control image imports this module to dispatch at this flow.
    from datarecord import Workspace
    from playbook.blocks.run import open_revision

    # Nothing has imported this container's block library yet until this call
    # does: MANTA_BLOCK_SOURCES (see config.block_sources) names it, but only
    # importing it registers its blocks. Skipping this leaves every run failing
    # with BlockNotRegisteredError.
    load_block_sources()
    block_cls = get_block(block)
    wired = {name: RevisionRef.from_dict(value) for name, value in (inputs or {}).items()}
    instance = block_cls(block_cls.merge_config(config, wired))
    with closing(Workspace()) as workspace:
        result = instance.run(open_revision(workspace, RevisionRef.from_dict(revision)))
        output = RevisionRef.from_revision(result).to_dict()
    create_table_artifact(table=[output], key=OUTPUT_ARTIFACT_KEY)
    return output


class PrefectBlockRunner:
    """`playbook`'s BlockRunner seam, implemented as one flow run per block.

    The engine hands over one fully spelled-out block invocation at a time; each
    becomes a `run-block` flow run on the docker work pool, which the worker turns
    into a fresh container. Moving execution to Kubernetes later means changing
    the work pool's type, not this class.

    A block declares the environment it needs as a name, and that name picks the
    container image for that block alone. Two frameworks that could never share a
    virtualenv can therefore appear in one playbook: `block.env` is on the spec
    the catalogue provides, so this works in a process that cannot import a block.
    """

    def run_block(
        self,
        block: BlockSpec,
        *,
        step_name: str,
        config: dict,
        revision: RevisionRef,
        inputs: dict[str, RevisionRef],
    ) -> RevisionRef:
        # Dispatching from inside a flow makes the block run a child of the
        # playbook run, which is what groups a run's steps under it in Prefect.
        # Prefect records job_variables on the flow run, so which image ran a
        # given step stays answerable after the fact.
        flow_run = run_deployment(
            name=BLOCK_DEPLOYMENT,
            job_variables={"image": exec_image(block.env)},
            parameters={
                "block": block.name,
                "step_name": step_name,
                "config": config,
                "revision": revision.to_dict(),
                "inputs": {name: value.to_dict() for name, value in inputs.items()},
            },
            # Only create the flow run: `_wait_for_block_run` does the waiting, so
            # that the step can be cancelled if this playbook run stops waiting.
            timeout=0,
        )
        flow_run = _wait_for_block_run(flow_run)
        state = flow_run.state
        if state is not None and state.name == TIMED_OUT_STATE_NAME:
            raise BlockTimedOutError(
                f"step {step_name!r} ({block.name}) exceeded the block timeout; "
                f"its log is on flow run {flow_run.id}"
            )
        if state is None or not state.is_completed():
            raise BlockRunFailedError(
                f"step {step_name!r} ({block.name}) ended in state "
                f"{state.type.value if state else 'UNKNOWN'}; "
                f"its log is on flow run {flow_run.id}"
            )
        return _block_output(flow_run.id, step_name)


def _wait_for_block_run(flow_run: FlowRun) -> FlowRun:
    """Wait until a step's flow run is final, and cancel it if the wait is cut short.

    The wait is cut short when the playbook run itself is ending: by its own
    timeout, which Prefect raises in here, by a cancellation, or because its worker
    is shutting down. The step would then run on with nothing waiting for its
    result, so it is cancelled, which stops its container.
    """
    try:
        with get_client(sync_client=True) as client:
            while flow_run.state is not None and not flow_run.state.is_final():
                time.sleep(BLOCK_POLL_SECONDS)
                flow_run = client.read_flow_run(flow_run.id)
    except BaseException:
        _cancel_block_run(flow_run.id)
        raise
    return flow_run


def _cancel_block_run(flow_run_id: UUID) -> None:
    """Ask Prefect to cancel a step's flow run, which stops and removes its container.

    The process Prefect runs beside the block in that container acts on this: it
    kills the block from outside, whatever the block is doing. Best effort, as the
    playbook run is already ending for a reason of its own that must not be masked.
    """
    try:
        with get_client(sync_client=True) as client:
            client.set_flow_run_state(
                flow_run_id,
                Cancelling(message="The playbook run ended before this step finished."),
            )
    except Exception:
        logger.exception(
            "Could not cancel flow run %s; its container may still be running", flow_run_id
        )


def _block_output(flow_run_id: UUID, step_name: str) -> RevisionRef:
    """The output revision a completed `run-block` flow run published (see `run_block`)."""
    # TODO(post-MVP): like the backend's reading of a run's outputs, this only finds a
    # step's output through the artifact its block run publishes to Prefect. Once data
    # records are tracked in Manta's own database, consider reading it from there.
    with get_client(sync_client=True) as client:
        artifacts = client.read_artifacts(
            artifact_filter=ArtifactFilter(
                flow_run_id=ArtifactFilterFlowRunId(any_=[flow_run_id]),
                key=ArtifactFilterKey(any_=[OUTPUT_ARTIFACT_KEY]),
            )
        )
    if not artifacts:
        raise BlockRunFailedError(
            f"step {step_name!r} completed without publishing its output revision; "
            f"its log is on flow run {flow_run_id}"
        )
    [row] = json.loads(artifacts[0].data)
    return RevisionRef.from_dict(row)


@flow(
    name=PLAYBOOK_FLOW_NAME,
    # Read when this module is imported, so in the playbook worker. It covers the
    # whole playbook. A step still running when it passes is cancelled (see
    # `_wait_for_block_run`), and the run ends as timed out, which frees its slot.
    timeout_seconds=playbook_timeout_seconds(),
)
def run_playbook(playbook: dict, config: dict, revision: dict, catalogue: str) -> dict:
    """Run a whole playbook, given its document rather than the playbook itself.

    `catalogue` is what `playbook`'s blocks are resolved against — this process
    never imports a block library itself (see runner/tests/test_isolation.py), so the
    caller has to describe every block the playbook could use, encoded with
    `catalogue_parameter`.
    """
    resolved_catalogue = parse_catalogue_parameter(catalogue)
    built = playbook_from_doc(parse_doc(playbook), catalogue=resolved_catalogue)
    result = execute_playbook(
        built,
        RevisionRef.from_dict(revision),
        config,
        runner=PrefectBlockRunner(),
    )
    return result.to_dict()
