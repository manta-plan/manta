# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Running a playbook.

Each step gets the record the previous step produced, plus anything wired to it from
further back, and is told where to put its output: every step's result lands under
one `output_prefix`, named after the step, so a finished run reads as a folder of
outputs a user can browse.

How a single block actually runs is behind `BlockRunner`. The default runner executes
blocks in this process, which is what tests and plain local use want. An orchestrator
(Manta) plugs in a runner that hands each block to whatever isolated environment it
manages - a container, a cluster job - and this package never learns which
orchestration tool that is.

Which steps run is decided once, up front, by `Playbook.active`: the same question
everything else asks, so what a playbook is understood to do and what it actually
does can never drift apart.

Before anything runs, the playbook is checked against its settings (see
`validation`), so a run that cannot work stops before its first step rather than
partway through.
"""

from typing import Protocol

from playbook.blocks import BlockSpec, DataRecord
from playbook.playbooks.playbook import BlockStep, Playbook, Step, child_config
from playbook.playbooks.validation import raise_for_playbook_issues


class BlockRunner(Protocol):
    """Runs one block, wherever blocks happen to run.

    `execute_playbook` does all the walking and wiring, so a runner never sees a
    playbook or a step: it is handed one block at a time with everything already
    spelled out. `step_name` comes along only as a label, for naming the work in
    whatever system the runner drives.
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
        output_base: str,
    ) -> DataRecord:
        block_cls = block.block_class()
        # A fresh instance per step: a block never carries state between runs.
        return block_cls(block_cls.merge_config(config, inputs)).run(record, output_base)


def execute_playbook(
    playbook: Playbook,
    record: DataRecord,
    config: dict,
    *,
    output_prefix: str,
    runner: BlockRunner | None = None,
) -> DataRecord:
    """Run `playbook`, returning the final step's record.

    `output_prefix` is the URL under which every step's output is produced:
    step `cluster` writes to `<output_prefix>/cluster.<suffix>`, and a step of a
    nested playbook to `<output_prefix>/<nesting step>/<step>.<suffix>`.

    Nothing runs unless the playbook passes every check against `config` first:
    `PlaybookHasIssuesError` lists everything wrong at once, rather than one problem
    surfacing at a time, steps into the run.
    """
    raise_for_playbook_issues(playbook, config)
    return _execute(playbook, record, config, output_prefix, runner or LocalBlockRunner(), {})


def _execute(
    playbook: Playbook,
    record: DataRecord,
    config: dict,
    output_prefix: str,
    runner: BlockRunner,
    external_inputs: dict[str, DataRecord],
) -> DataRecord:
    results: dict[str, dict[str, DataRecord]] = {}

    for step in playbook.active(config).steps:
        wired = _wire_up(step, results, external_inputs)
        output_base = f"{output_prefix}/{step.name}"

        if isinstance(step, BlockStep):
            record = runner.run_block(
                step.block,
                step_name=step.name,
                config=config.get(step.name, {}),
                record=record,
                inputs=wired,
                output_base=output_base,
            )
        else:
            record = _execute(
                step.playbook,
                record,
                child_config(config, step.name),
                output_base,
                runner,
                wired,
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
