# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Running a playbook.

Each step gets the record the previous step produced, plus anything wired to it from
further back. A step whose block belongs to another environment is handed off to that
environment's deployment instead of being run here, which is what lets one playbook
span environments that could never be installed together.

Which steps run is decided once, when the flow is built, using the same question the
rest of the system asks. A playbook can therefore never run something that was not
checked, or skip something that was.
"""

from prefect import Flow, flow
from prefect.deployments import run_deployment

from manta_blocks import Catalogue, DataRecord, current_env, deployment_path
from manta_playbooks.playbook import BlockStep, Playbook, child_config

ORCHESTRATOR_FLOW = "run_playbook"
"""The Prefect flow that runs a whole playbook."""


def orchestrator_path(env: str) -> str:
    """The full name Prefect needs to start a playbook running in `env`."""
    return f"{ORCHESTRATOR_FLOW}/{env}"


def dispatch_block(
    block: str,
    env: str,
    config: dict,
    record: DataRecord,
    inputs: "dict[str, DataRecord] | None" = None,
) -> DataRecord:
    """Run a block in another environment, and bring its result back.

    Records cross as plain data, because the two sides are different processes with
    different packages installed.
    """
    flow_run = run_deployment(
        name=deployment_path(block, env),
        parameters={
            "block": block,
            "config": config,
            "record": record.to_dict(),
            "inputs": {name: value.to_dict() for name, value in (inputs or {}).items()},
        },
    )
    return DataRecord.from_dict(flow_run.state.result())


def build_flow(playbook: Playbook, config: dict, dispatch: bool = False) -> Flow:
    """Build the Prefect flow that runs `playbook` with `config`.

    With `dispatch` on, a step whose block needs a different environment is handed to
    that block's deployment rather than run here. It is off by default so that tests
    and local runs stay in one process.
    """
    active = playbook.active(config)
    steps = list(active.steps)

    # Built once, here, rather than each time the playbook runs.
    nested_flows = {
        step.name: build_flow(
            step.playbook, child_config(config, step.name), dispatch=dispatch
        )
        for step in steps
        if not isinstance(step, BlockStep)
    }

    def _playbook(
        record: DataRecord, external_inputs: "dict[str, DataRecord] | None" = None
    ) -> DataRecord:
        external_inputs = external_inputs or {}
        # Each step's results, by step name then result name.
        results: dict[str, dict[str, DataRecord]] = {}

        for step in steps:
            wired = _wire_up(step, results, external_inputs)

            if isinstance(step, BlockStep):
                record = _run_block_step(step, config, record, wired, dispatch)
            else:
                record = nested_flows[step.name](record, wired)

            results[step.name] = {"output": record}

        return record

    return flow(name=playbook.name)(_playbook)


def _wire_up(
    step, results: dict[str, dict[str, DataRecord]], external: dict[str, DataRecord]
) -> dict[str, DataRecord]:
    """The records to feed into this step's wired-in settings."""
    wired = {
        input_name: results[ref.step][ref.output]
        for input_name, ref in step.inputs.items()
    }
    # Anything this step still needs may be fed from outside, when this playbook is
    # itself a step in a longer one.
    for input_name in step.declared_inputs() - wired.keys():
        offered = external.get(f"{step.name}.{input_name}")
        if offered is not None:
            wired[input_name] = offered
    return wired


def _run_block_step(
    step: BlockStep,
    config: dict,
    record: DataRecord,
    wired: dict[str, DataRecord],
    dispatch: bool,
) -> DataRecord:
    # A block sees only its own step's settings. `globals` is read by `when`
    # conditions and inherited by nested playbooks, but is not merged into block
    # settings yet - a playbook-wide default (say, one solver choice for every
    # solving block) still has to be repeated per step. When that lands, this is
    # the one place to fold `config["globals"]` into `step_config`.
    step_config = config.get(step.name, {})
    if dispatch and step.block.env != current_env():
        return dispatch_block(
            step.block.name, step.block.env, step_config, record, wired
        )
    block_flow = step.block.block_class().as_flow(
        step_config, name=step.name, input_names=wired.keys()
    )
    return block_flow(record, **wired)


def run_playbook_locally(
    playbook: Playbook, record: DataRecord, config: dict, dispatch: bool = False
) -> DataRecord:
    """Check a playbook and run it in this process."""
    playbook.validate_playbook(config)
    return build_flow(playbook, config, dispatch=dispatch)(record)


# Persisted for the same reason as `run_block`'s result: whoever started this run
# via a deployment lives in another process and may want the final record back.
@flow(name=ORCHESTRATOR_FLOW, persist_result=True)
def run_playbook(
    playbook: dict, config: dict, record: dict, catalogue: str | None = None
) -> dict:
    """Run a whole playbook, given its document rather than the playbook itself.

    This is what a deployment runs when someone presses Run. The playbook travels as
    the same document it is written and edited as, and its steps are handed off to
    whichever environment each one needs.

    The catalogue travels as a JSON *string*, not a dict: Prefect walks dict
    parameters and treats every `{"$ref": ...}` inside as one of its own
    block-document references, and the JSON schemas in a catalogue are full of
    `$ref`s. A string is opaque to that walk. Use `catalogue_parameter` to build it.
    """
    import json

    from manta_playbooks.yaml_io import parse_doc, playbook_from_doc

    known_blocks = (
        Catalogue.model_validate(json.loads(catalogue)) if catalogue else None
    )
    built = playbook_from_doc(parse_doc(playbook), catalogue=known_blocks)
    result = run_playbook_locally(
        built, DataRecord.from_dict(record), config, dispatch=True
    )
    return result.to_dict()


def catalogue_parameter(catalogue: "Catalogue | None") -> str | None:
    """A catalogue in the form `run_playbook` accepts it (see its docstring)."""
    return catalogue.model_dump_json() if catalogue else None
