# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Access to the datarecord stores that playbook records point at."""

from datarecord import Revision, Workspace
from playbook.blocks.core import DataRecord, DataRecordError


def revision(record: DataRecord) -> tuple[Workspace, Revision]:
    """Return a new workspace and the revision in it that `record` points at."""
    ws = Workspace()
    try:
        return ws, ws.store(record.url).revision(record.uuid)
    except KeyError as exc:
        raise DataRecordError(exc.args[0]) from exc
