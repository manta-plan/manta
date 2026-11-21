# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Access to the datarecord stores that playbook records point at."""

from collections.abc import Iterable

from datarecord import Revision, Workspace
from playbook.blocks import RecordContents
from playbook.blocks.core import DataRecord, DataRecordError


def revision(record: DataRecord) -> tuple[Workspace, Revision]:
    """Return a new workspace and the revision in it that `record` points at."""
    ws = Workspace()
    try:
        return ws, ws.store(record.url).revision(record.uuid)
    except KeyError as exc:
        raise DataRecordError(exc.args[0]) from exc


def record_contents(record: DataRecord, coordinate_dims: Iterable[str]) -> RecordContents:
    """Read the names in a record that block settings can refer to.

    Property names come from the record schema alone (i.e., the revision manifest).
    Coordinates are read from the record data, so only those of `coordinate_dims` are read.

    Args:
        record (DataRecord): record revision to read.
        coordinate_dims (Iterable[str]):
            dimensions whose coordinates to read (e.g., `carrier`).
            Use `playbook.blocks.record_refs.referenced_dims` to find those a block needs.

    Raises:
        DataRecordError: the store at `record.url` has no revision `record.uuid`.

    Returns:
        RecordContents: property names of every dimension and coordinates of `coordinate_dims`.
    """
    base = revision(record)[1].record
    return RecordContents(
        coordinates={
            dim: frozenset(coord for (coord,) in base.dims[dim].fetchall())
            for dim in coordinate_dims
        },
        properties={dim: frozenset(names) for dim, names in base.schema.properties.items()},
    )
