# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""What block settings can name in a datarecord revision."""

from collections.abc import Iterable

from datarecord import Revision
from playbook.blocks import RecordContents


def record_contents(rev: Revision, coordinate_dims: Iterable[str]) -> RecordContents:
    """Read the names in `rev` that block settings can refer to.

    Property names come from the record schema alone (i.e., the revision manifest).
    Coordinates are read from the record data, so only those of `coordinate_dims` are read.

    Args:
        rev (Revision): revision to read.
        coordinate_dims (Iterable[str]):
            dimensions whose coordinates to read (e.g., `carrier`).
            Use `playbook.blocks.record_refs.referenced_dims` to find those a block needs.

    Returns:
        RecordContents: property names of every dimension and coordinates of `coordinate_dims`.
    """
    base = rev.record
    return RecordContents(
        coordinates={
            dim: frozenset(coord for (coord,) in base.dims[dim].fetchall())
            for dim in coordinate_dims
        },
        properties={dim: frozenset(names) for dim, names in base.schema.properties.items()},
    )
