# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Running a playbook.

Each step gets the record the previous step produced, plus anything wired to it from
further back. Each block writes its result into the input record's own store, so
the engine never decides where outputs go.

How a single block actually runs is behind `BlockRunner`. The default runner executes
blocks in this process, which is what tests and plain local use want. An orchestrator
(Manta) plugs in a runner that hands each block to whatever isolated environment it
manages - a container, a cluster job - and this package never learns which
orchestration tool that is.

Which steps run is decided once, up front, by `Playbook.active`: the same question
everything else asks, so what a playbook is understood to do and what it actually
does can never drift apart.
"""

from typing import Protocol

from playbook.blocks import BlockSpec, DataRecord
from playbook.playbooks.playbook import BlockStep, Playbook, Step, child_config


class BlockRunner(Protocol):
    """Runs one block, wherever blocks happen to run.

    `execute_playbook` does all the walking and wiring, so a runner never sees a
    playbook or a step: it is handed one block at a time with everything already
    spelled out. `step_name` is the step's qualified path from the outermost
    playbook, its enclosing nested-playbook steps joined by `/` (e.g.
    `stage_2030/cluster`), so it is unique within one run. It comes along only as a
    label, for naming and finding the work in whatever system the runner drives.
    """

    def run_block(
        self,
        block: BlockSpec,
        *,
        step_name: str,
        config: dict,
        record: DataRecord,
        inputs: dict[str, DataRecord],
    ) -> DataRecord:
        """Run `block` on `record` and return the record it produced."""
        ...


class LocalBlockRunner:
    """Runs each block in this process. The block must be importable here."""

    def run_block(
        self,
        block: BlockSpec,
        *,
        step_name: str,
        config: dict,
        record: DataRecord,
        inputs: dict[str, DataRecord],
    ) -> DataRecord:
        block_cls = block.block_class()
        # A fresh instance per step: a block never carries state between runs.
        return block_cls(block_cls.merge_config(config, inputs)).run(record)


def execute_playbook(
    playbook: Playbook,
    record: DataRecord,
    config: dict,
    *,
    runner: BlockRunner | None = None,
) -> DataRecord:
    """Run `playbook`, returning the final step's record.

    A playbook is taken as given here. Checking one up front - that its steps are
    wired to results that exist, and that each block finds the data it needs - is a
    separate concern, and not yet part of this package.
    """
    return _execute(playbook, record, config, runner or LocalBlockRunner(), {}, "")


def _execute(
    playbook: Playbook,
    record: DataRecord,
    config: dict,
    runner: BlockRunner,
    external_inputs: dict[str, DataRecord],
    prefix: str,
) -> DataRecord:
    results: dict[str, dict[str, DataRecord]] = {}

    for step in playbook.active(config).steps:
        wired = _wire_up(step, results, external_inputs)

        if isinstance(step, BlockStep):
            record = runner.run_block(
                step.block,
                step_name=f"{prefix}{step.name}",
                config=config.get(step.name, {}),
                record=record,
                inputs=wired,
            )
        else:
            record = _execute(
                step.playbook,
                record,
                child_config(config, step.name),
                runner,
                wired,
                f"{prefix}{step.name}/",
            )

        results[step.name] = {"output": record}

    return record


def _wire_up(
    step: Step,
    results: dict[str, dict[str, DataRecord]],
    external: dict[str, DataRecord],
) -> dict[str, DataRecord]:
    """The records to feed into this step's wired-in settings."""
    wired = {input_name: results[ref.step][ref.output] for input_name, ref in step.inputs.items()}
    # Anything this step still needs may be fed from outside, when this playbook is
    # itself a step in a longer one.
    for input_name in step.declared_inputs() - wired.keys():
        offered = external.get(f"{step.name}.{input_name}")
        if offered is not None:
            wired[input_name] = offered
    return wired
