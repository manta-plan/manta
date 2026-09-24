# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The two Prefect flows every playbook run is made of.

`run-playbook` walks a playbook document with `playbook`'s engine and dispatches
each step to `run-block`. Every `run-block` flow run is picked up by the docker
work pool, so each step executes in its own throwaway container from that
environment's execution image.

Both flows are deployed once, statically (see `deploy.py`). Playbooks are data
passed in as parameters, so nothing is ever deployed per playbook or per block.

Everything passed in has crossed a process boundary, so records arrive as plain
`{"url": ...}` data. A loaded model could never travel this way, which is exactly
why blocks pass pointers to data rather than the data itself.
"""

import logging

from playbook.blocks import BlockSpec, Catalogue, DataRecord
from playbook.blocks.registry import get_block, load_block_sources
from playbook.playbooks import execute_playbook, parse_doc, playbook_from_doc
from prefect import flow
from prefect.deployments import run_deployment

from runner.config import exec_image

logger = logging.getLogger(__name__)

BLOCK_FLOW_NAME = "run-block"
PLAYBOOK_FLOW_NAME = "run-playbook"


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
    arrives as a parameter, and `step_name` — the name of the step using this
    block within its own playbook, distinct from the block itself since the same
    block can be used by more than one step — only names the flow run above; it
    plays no part in running the block.

    This is the only code in this runtime that runs inside a block's own
    environment, and it does not import a block until asked for one by name.
    """
    # Nothing has imported this container's block library yet until this call
    # does: MANTA_BLOCK_SOURCES (see config.block_sources) names it, but only
    # importing it registers its blocks. Skipping this leaves every run failing
    # with BlockNotRegisteredError.
    load_block_sources()
    block_cls = get_block(block)
    wired = {name: DataRecord.from_dict(value) for name, value in (inputs or {}).items()}
    result = block_cls(block_cls.merge_config(config, wired)).run(
        DataRecord.from_dict(record), output_base
    )
    return result.to_dict()


class PrefectStepRunner:
    """`playbook`'s StepRunner seam, implemented as one flow run per step.

    The engine hands over one fully spelled-out block invocation at a time; each
    becomes a `run-block` flow run on the docker work pool, which the worker turns
    into a fresh container. Moving execution to Kubernetes later means changing
    the work pool's type, not this class.

    A block declares the environment it needs as a name, and that name picks the
    container image for its step alone. Two frameworks that could never share a
    virtualenv can therefore appear in one playbook: `block.env` is on the spec
    the catalogue provides, so this works in a process that cannot import a block.
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
        # Prefect records job_variables on the flow run, so which image ran a
        # given step stays answerable after the fact.
        flow_run = run_deployment(
            name=BLOCK_DEPLOYMENT,
            job_variables={"image": exec_image(block.env)},
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
def run_playbook(
    playbook: dict, config: dict, record: dict, output_prefix: str, catalogue: str
) -> dict:
    """Run a whole playbook, given its document rather than the playbook itself.

    `catalogue` is what `playbook`'s blocks are resolved against — this process
    never imports a block library itself (see tests/test_isolation.py), so the
    caller has to describe every block the playbook could use, encoded with
    `catalogue_parameter`.
    """
    resolved_catalogue = parse_catalogue_parameter(catalogue)
    built = playbook_from_doc(parse_doc(playbook), catalogue=resolved_catalogue)
    result = execute_playbook(
        built,
        DataRecord.from_dict(record),
        config,
        output_prefix=output_prefix,
        runner=PrefectStepRunner(),
    )
    return result.to_dict()
