# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Running a playbook.

Each step gets the revision the previous step produced, plus anything wired to it from
further back. Each block writes its result into the input revision's own store, so
the engine never decides where outputs go.

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

from playbook.blocks import BlockSpec, RevisionRef
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
        revision: RevisionRef,
        inputs: dict[str, RevisionRef],
    ) -> RevisionRef:
        """Run `block` on `revision` and return the revision it produced."""
        ...


class LocalBlockRunner:
    """Runs each block in this process. The block must be importable here."""

    def run_block(
        self,
        block: BlockSpec,
        *,
        step_name: str,
        config: dict,
        revision: RevisionRef,
        inputs: dict[str, RevisionRef],
    ) -> RevisionRef:
        # Imported here: only running a block in this process opens stores, which
        # needs the `playbook[run]` extra; driving one elsewhere does not.
        from playbook.blocks.run import run_block

        return run_block(block.block_class(), config, inputs, revision)


def execute_playbook(
    playbook: Playbook,
    revision: RevisionRef,
    config: dict,
    *,
    runner: BlockRunner | None = None,
) -> RevisionRef:
    """Run `playbook`, returning the final step's revision.

    Nothing runs unless the playbook passes every check against `config` first:
    `PlaybookHasIssuesError` lists everything wrong at once, rather than one problem
    surfacing at a time, steps into the run.
    """
    raise_for_playbook_issues(playbook, config)
    return _execute(playbook, revision, config, runner or LocalBlockRunner(), {})


def _execute(
    playbook: Playbook,
    revision: RevisionRef,
    config: dict,
    runner: BlockRunner,
    external_inputs: dict[str, RevisionRef],
) -> RevisionRef:
    results: dict[str, dict[str, RevisionRef]] = {}

    for step in playbook.active(config).steps:
        wired = _wire_up(step, results, external_inputs)

        if isinstance(step, BlockStep):
            revision = runner.run_block(
                step.block,
                step_name=step.name,
                config=config.get(step.name, {}),
                revision=revision,
                inputs=wired,
            )
        else:
            revision = _execute(
                step.playbook,
                revision,
                child_config(config, step.name),
                runner,
                wired,
            )

        results[step.name] = {"output": revision}

    return revision


def _wire_up(
    step: Step,
    results: dict[str, dict[str, RevisionRef]],
    external: dict[str, RevisionRef],
) -> dict[str, RevisionRef]:
    """The revisions to feed into this step's wired-in settings."""
    wired = {input_name: results[ref.step][ref.output] for input_name, ref in step.inputs.items()}
    # Anything this step still needs may be fed from outside, when this playbook is
    # itself a step in a longer one.
    for input_name in step.declared_inputs() - wired.keys():
        offered = external.get(f"{step.name}.{input_name}")
        if offered is not None:
            wired[input_name] = offered
    return wired
