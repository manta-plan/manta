# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Running one block on its data, inside the process that runs it.

The only module of `playbook` that opens datarecord stores, and so the only one that
needs the `playbook[run]` extra. Whatever merely passes revisions along, such as an
orchestrator or a web backend, imports `RevisionRef` from `playbook.blocks` instead
and never installs datarecord.

One block run gets one `Workspace`: every revision it reads or writes shares its
database, so manifests are read and owner maps folded once per run rather than once
per helper call.
"""

from contextlib import closing

from datarecord import Revision, Workspace

from playbook.blocks.core import DataRecordError, MantaBlock, RevisionRef


def open_revision(workspace: Workspace, ref: RevisionRef) -> Revision:
    """The revision `ref` points at, opened on `workspace`."""
    try:
        return workspace.store(ref.store).revision(ref.id)
    except KeyError as exc:
        raise DataRecordError(exc.args[0]) from exc


def run_block(
    block_cls: type[MantaBlock],
    config: dict,
    *,
    revision: RevisionRef,
    inputs: dict[str, RevisionRef],
) -> RevisionRef:
    """Run `block_cls` on `revision`, in a workspace of its own.

    A fresh block instance per call: a block never carries state between runs.
    """
    block = block_cls(block_cls.merge_config(config, inputs))
    with closing(Workspace()) as workspace:
        return RevisionRef.from_revision(block.run(open_revision(workspace, revision)))
