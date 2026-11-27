# SPDX-FileCopyrightText: Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

"""Opening a revision, inside the process that runs a block on it.

The only module of `playbook` that imports datarecord, and so the only one that
needs the `playbook[run]` extra. Whatever merely passes revisions along, such as an
orchestrator or a web backend, imports `RevisionRef` from `playbook.blocks` instead
and never installs datarecord.

Whatever runs a block opens one `Workspace` for that run: every revision the block
reads or writes shares its database, so manifests are read and owner maps folded once
per run rather than once per helper call.
"""

from datarecord import Revision, Workspace

from playbook.blocks.core import DataRecordError, RevisionRef


def open_revision(workspace: Workspace, ref: RevisionRef) -> Revision:
    """The revision `ref` points at, opened on `workspace`."""
    try:
        return workspace.store(ref.store).revision(ref.id)
    except KeyError as exc:
        raise DataRecordError(exc.args[0]) from exc
