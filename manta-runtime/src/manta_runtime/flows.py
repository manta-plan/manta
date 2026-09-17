"""The two Prefect flows every playbook run is made of.

`run-playbook` walks a playbook document and dispatches each step to `run-block`;
each `run-block` flow run is picked up by the docker work pool, so every block runs
in its own container from the blocks runner image (see docker/blocks-runner.Dockerfile
in the manta repo). Both flows are deployed once, statically, by `manta_runtime.deploy`
- playbooks are data passed in as parameters, so no deployment ever has to be created
or updated when a playbook changes.

Everything passed in has crossed a process boundary, so records arrive as plain
`{"url": ...}` data. A loaded model could never travel this way, which is exactly why
blocks pass pointers to data rather than the data itself.
"""

import json

from blocks import BlockSpec, DataRecord, get_block
from blocks.storage import get_text, put_text
from playbooks import execute_playbook, parse_doc, playbook_from_doc
from prefect import flow
from prefect.deployments import run_deployment

BLOCK_FLOW_NAME = "run-block"
PLAYBOOK_FLOW_NAME = "run-playbook"

# The deployment names `manta_runtime.deploy` creates. The Manta backend starts runs
# by these names through the Prefect API (see backend's run_service.py, which
# duplicates the playbook one on purpose: the backend does not import this package,
# since this package only exists inside the blocks runner image).
BLOCK_DEPLOYMENT = f"{BLOCK_FLOW_NAME}/{BLOCK_FLOW_NAME}"
PLAYBOOK_DEPLOYMENT = f"{PLAYBOOK_FLOW_NAME}/{PLAYBOOK_FLOW_NAME}"


class BlockRunFailedError(Exception):
    """Raised in the playbook flow when a dispatched block flow run did not complete."""


def result_record_url(output_base: str) -> str:
    """Where a block flow run leaves the record describing its output.

    The playbook flow and the block flow run in different containers, and Prefect
    return values are not persisted anywhere both sides can read without configuring
    a result-storage backend. The result record is tiny, and the same object store
    the data itself lives in is already at hand - so it travels as
    `<output_base>.record.json`, right next to the output it describes.
    TODO(post-MVP): consider Prefect's own result persistence (an S3 result storage
    block) so `state.result()` works and this side channel can go.
    """
    return f"{output_base}.record.json"


@flow(name=BLOCK_FLOW_NAME, flow_run_name="{step_name}[{block}]")
def run_block(
    block: str,
    step_name: str,
    config: dict,
    record: dict,
    inputs: dict[str, dict] | None,
    output_base: str,
) -> dict:
    """Run one block by name, in this process, and return where its result went.

    There is one deployment of this flow, shared by every block; the block to run
    arrives as a parameter and the flow run is named after the step, so per-step
    visibility in Prefect survives without per-block deployments.
    """
    block_cls = get_block(block)
    wired = {
        name: DataRecord.from_dict(value) for name, value in (inputs or {}).items()
    }
    result = block_cls(block_cls.merge_config(config, wired)).run(
        DataRecord.from_dict(record), output_base
    )
    put_text(result_record_url(output_base), json.dumps(result.to_dict()))
    return result.to_dict()


class PrefectStepRunner:
    """Runs every step of a playbook as its own `run-block` flow run.

    This is Manta's implementation of the `StepRunner` seam that `manta-blocks`
    exposes: the docker work pool turns each dispatched flow run into its own
    container, which is the per-block isolation the playbook proposal asks for.
    Swapping docker for k8s later means changing the work pool, not this code.
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
        # `run_deployment` inside a flow creates the block run as a child of the
        # playbook run, so a run's steps show up nested under it in Prefect.
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
                f"see flow run {flow_run.id} for its logs"
            )
        return DataRecord.from_dict(
            json.loads(get_text(result_record_url(output_base)))
        )


@flow(name=PLAYBOOK_FLOW_NAME)
def run_playbook(
    playbook: dict, config: dict, record: dict, output_prefix: str
) -> dict:
    """Run a whole playbook, given its document rather than the playbook itself.

    This is what the Manta backend starts when a user presses Run. The playbook
    travels as the same document it is written and edited as, so what runs is exactly
    what was submitted, and it is validated here (against the real, importable
    blocks) before any step is dispatched.
    """
    built = playbook_from_doc(parse_doc(playbook))
    result = execute_playbook(
        built,
        DataRecord.from_dict(record),
        config,
        output_prefix=output_prefix,
        runner=PrefectStepRunner(),
    )
    return result.to_dict()
