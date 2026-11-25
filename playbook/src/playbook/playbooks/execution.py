# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Running a playbook.

Each step receives the revision of the last step above it that ran. Each block writes
its result into the store of the revision it receives, so the engine never decides
where a result goes.

How a single block actually runs is behind `BlockRunner`. The default runner executes
blocks in this process, which is what tests and plain local use want. An orchestrator
(Manta) plugs in a runner that hands each block to whatever isolated environment it
manages - a container, a cluster job - and this package never learns which
orchestration tool that is.

`plan` decides once, before the first step, which steps run (see `planner`). No step
runs unless the playbook passes every check against its inputs (see `validation`). A
run that cannot work therefore stops before its first step.
"""

from contextlib import closing
from typing import Protocol

from playbook.blocks import BlockSpec, RevisionRef
from playbook.playbooks.planner import Planned, PlannedBlock, plan
from playbook.playbooks.playbook import Playbook
from playbook.playbooks.validation import raise_for_playbook_issues


class BlockRunner(Protocol):
    """Runs one block, wherever blocks happen to run.

    `execute_playbook` walks the steps, so a runner never receives a playbook or a
    step. It receives one block at a time, with the settings of the block evaluated.
    `step_path` is a label only, which the runner can use to name the work in the
    system it drives.
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
    """Run `playbook` with `inputs`, and return the revision of the last step.

    Raises:
        PlaybookHasIssuesError: If the playbook fails a check against `inputs`. No step
            runs, and the error lists every issue.
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
