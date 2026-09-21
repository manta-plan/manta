"""The two Prefect flows every playbook run is made of.

`run-playbook` walks a playbook document with manta-blocks' engine and dispatches
each step to `run-block`. Every `run-block` flow run is picked up by the docker
work pool, so each step executes in its own throwaway container from that
environment's execution image.

Both flows are deployed once, statically (see `deploy.py`). Playbooks are data
passed in as parameters, so nothing is ever deployed per playbook or per block.

Everything passed in has crossed a process boundary, so records arrive as plain
`{"url": ...}` data. A loaded model could never travel this way, which is exactly
why blocks pass pointers to data rather than the data itself.

Tracking: one flow run per playbook run (named `run-<run uuid>` by the backend),
one child flow run per executed step (named `<step>[<block>]`), queryable by the
playbook flow run's id — see RunService.get_run_steps.
"""

import logging

from blocks import BlockSpec, DataRecord
from blocks.library import library_catalogue
from blocks.registry import get_block
from playbooks import execute_playbook, parse_doc, playbook_from_doc
from prefect import flow
from prefect.deployments import run_deployment

logger = logging.getLogger(__name__)

BLOCK_FLOW_NAME = "run-block"
BLOCK_DEPLOYMENT = f"{BLOCK_FLOW_NAME}/{BLOCK_FLOW_NAME}"

PLAYBOOK_FLOW_NAME = "run-playbook"
PLAYBOOK_DEPLOYMENT = f"{PLAYBOOK_FLOW_NAME}/{PLAYBOOK_FLOW_NAME}"
"""Created by `manta_runtime.deploy`; RunService dispatches runs at it by name."""


class BlockRunFailedError(Exception):
    """Raised when a step's flow run did not complete."""


@flow(
    name=BLOCK_FLOW_NAME,
    flow_run_name="{step_name}[{block}]",
    # The step's output record, read back by the orchestrator from the object
    # store. The data itself never travels this way — only the pointer to it.
    persist_result=True,
    # A block's own print()s are part of its log, and solvers are talkative.
    log_prints=True,
)
def run_block(
    block: str,
    step_name: str,
    config: dict,
    record: dict,
    inputs: dict[str, dict] | None,
    output_base: str,
) -> dict:
    """Run one block by name, in this container, and report where its result went.

    There is one deployment of this flow, shared by every block: the block to run
    arrives as a parameter and the flow run is named after the step, so per-step
    visibility survives without a deployment per block.

    This is the only Manta code that runs inside a block's environment, and it
    does not import a block until asked for one by name.
    """
    block_cls = get_block(block)
    wired = {name: DataRecord.from_dict(value) for name, value in (inputs or {}).items()}
    result = block_cls(block_cls.merge_config(config, wired)).run(
        DataRecord.from_dict(record), output_base
    )
    return result.to_dict()


class PrefectStepRunner:
    """manta-blocks' StepRunner seam, implemented as one flow run per step.

    The engine hands over one fully spelled-out block invocation at a time; each
    becomes a `run-block` flow run on the docker work pool, which the worker turns
    into a fresh container. Moving execution to Kubernetes later means changing
    the work pool's type, not this class.
    """

    def run_block(
        self,
        block: BlockSpec,
        *,
        step_name: str,
        config: dict,
        record: DataRecord,
        inputs: dict[str, DataRecord],
        output_base: str,
    ) -> DataRecord:
        # Dispatching from inside a flow makes the block run a child of the
        # playbook run, which is what groups a run's steps under it in Prefect.
        flow_run = run_deployment(
            name=BLOCK_DEPLOYMENT,
            parameters={
                "block": block.name,
                "step_name": step_name,
                "config": config,
                "record": record.to_dict(),
                "inputs": {name: value.to_dict() for name, value in inputs.items()},
                "output_base": output_base,
            },
        )
        state = flow_run.state
        if state is None or not state.is_completed():
            raise BlockRunFailedError(
                f"step {step_name!r} ({block.name}) ended in state "
                f"{state.type.value if state else 'UNKNOWN'}; "
                f"its log is on flow run {flow_run.id}"
            )
        return DataRecord.from_dict(state.result())


@flow(name=PLAYBOOK_FLOW_NAME)
def run_playbook(playbook: dict, config: dict, record: dict, output_prefix: str) -> dict:
    """Run a whole playbook, given its document rather than the playbook itself.

    This is what the backend dispatches when a user presses Run. Blocks are
    resolved from the committed catalogue — this process never imports them (they
    need their own environment, which only the execution images have) — and the
    document is validated again here before any step is dispatched.
    """
    built = playbook_from_doc(parse_doc(playbook), catalogue=library_catalogue())
    result = execute_playbook(
        built,
        DataRecord.from_dict(record),
        config,
        output_prefix=output_prefix,
        runner=PrefectStepRunner(),
    )
    return result.to_dict()
