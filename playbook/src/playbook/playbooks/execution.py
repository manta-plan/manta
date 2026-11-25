# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Running a playbook.

Each step gets the revision the step above it produced. Each block writes its result
into the input revision's own store, so the engine never decides where outputs go.

How a single block actually runs is behind `BlockRunner`. The default runner executes
blocks in this process, which is what tests and plain local use want. An orchestrator
(Manta) plugs in a runner that hands each block to whatever isolated environment it
manages - a container, a cluster job - and this package never learns which
orchestration tool that is.

What runs is decided once, up front, by the planner (see `planner`), and nothing runs
unless the playbook passes every check against its inputs (see `validation`), so a run
that cannot work stops before its first step rather than partway through.
"""

from contextlib import closing
from typing import Protocol

from playbook.blocks import BlockSpec, RevisionRef
from playbook.playbooks.planner import Planned, PlannedBlock, plan
from playbook.playbooks.playbook import Playbook
from playbook.playbooks.validation import raise_for_playbook_issues


class BlockRunner(Protocol):
    """Runs one block, wherever blocks happen to run.

    `execute_playbook` does all the walking, so a runner never sees a playbook or a
    step: it is handed one block at a time with everything already spelled out.
    `step_path` comes along only as a label, for naming the work in whatever system
    the runner drives.
    """

    def run_block(
        self,
        block: BlockSpec,
        *,
        step_path: tuple[str, ...],
        config: dict,
        revision: RevisionRef,
    ) -> RevisionRef:
        """Run `block` on `revision` and return the revision it produced."""
        ...


class LocalBlockRunner:
    """Runs each block in this process. The block must be importable here."""

    def run_block(
        self,
        block: BlockSpec,
        *,
        step_path: tuple[str, ...],
        config: dict,
        revision: RevisionRef,
    ) -> RevisionRef:
        # Imported here: only running a block in this process opens stores, which
        # needs the `playbook[run]` extra; driving one elsewhere does not.
        from datarecord import Workspace

        from playbook.blocks.run import open_revision

        instance = block.block_class()(config)
        with closing(Workspace()) as workspace:
            return RevisionRef.from_revision(instance.run(open_revision(workspace, revision)))


def execute_playbook(
    playbook: Playbook,
    revision: RevisionRef,
    inputs: dict,
    *,
    runner: BlockRunner | None = None,
) -> RevisionRef:
    """Run `playbook` with `inputs`, returning the last step's revision.

    Nothing runs unless the playbook passes every check against `inputs` first:
    `PlaybookHasIssuesError` lists everything wrong at once.
    """
    raise_for_playbook_issues(playbook, inputs)
    return _run(plan(playbook, inputs), revision, runner or LocalBlockRunner())


def _run(step: Planned, revision: RevisionRef, runner: BlockRunner) -> RevisionRef:
    if isinstance(step, PlannedBlock):
        return runner.run_block(
            step.block, step_path=step.path, config=step.settings, revision=revision
        )
    for inner in step.steps:
        revision = _run(inner, revision, runner)
    return revision
