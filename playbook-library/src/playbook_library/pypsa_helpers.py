# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Shared PyPSA work for the blocks in this library.

This is also where the blocks meet their data. A record points at a PyPSA netCDF
file, locally or in S3: `to_network` reads one, and `write_network` writes a new one
at the place the caller asked for. A block writes a whole new file rather than only
what it changed, because PyPSA cannot yet compare two networks or store a difference.
Both are confined to this module, so richer record storage only ever changes it.
"""

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pypsa
from datarecord import Workspace
from datarecord.tools.pypsa import PyPSA
from playbook.blocks.core import DataRecord

CAPACITY_COMPONENTS = ["Generator", "Link", "StorageUnit", "Store"]
"""The components whose capacity a capacity-expansion block can change."""

NETWORK_SUFFIX = ".nc"
"""The format the library's blocks exchange: PyPSA netCDF."""


def nominal_attr(component_name: str) -> str:
    """The name of a component's nominal capacity: stores hold energy, the rest power."""
    return "e_nom" if component_name == "Store" else "p_nom"


def capacity_components(n: pypsa.Network) -> Iterator:
    """Each component of `n` that has a nominal capacity."""
    yield from n.components[CAPACITY_COMPONENTS]


def to_network(record: DataRecord) -> pypsa.Network:
    """Read the network a record points at.

    Every call reads the file again, so a block gets a network of its own and never
    has to copy one. That is worth knowing: copying a network with several investment
    periods is not currently safe in PyPSA.
    """
    ws = Workspace()
    store = ws.store(record.url)
    rev = store.revision(UUID(record.uuid))
    missing = PyPSA.verify(rev.record)
    if missing:
        raise RuntimeError(missing.describe())
    n = PyPSA.build(rev.record)
    return n


def write_network(n: pypsa.Network, record: DataRecord, results_only: bool = False) -> DataRecord:
    """Write `n` where the caller asked, and point a new record at it."""

    ws = Workspace()
    store = ws.store(record.url)
    rev = store.revision(UUID(record.uuid))

    kwargs: dict[str, Any] = {"results_only": results_only}
    if results_only:
        kwargs["base"] = rev.record
    ws = Workspace()
    solved = rev.child(PyPSA.to_datarecord(n, ws.con, **kwargs))
    return DataRecord(url=record.url, uuid=str(solved.id))


def optimize_network(n: pypsa.Network, config, **overrides: object) -> pypsa.Network:
    """Optimise `n` with the given settings, overriding individual ones if asked.

    Overrides are passed straight through rather than folded into `config`, so values
    that only make sense to PyPSA - a slice of snapshots, say - never have to survive
    a round trip through the settings model.
    """
    n.optimize(**{**config.model_dump(), **overrides})
    return n


def freeze_period(n: pypsa.Network, period: int) -> None:
    """Keep what was built in `period` from being changed by a later period.

    The optimised capacities become the fixed ones, and anything built in this period
    is no longer extendable.
    """
    for c in capacity_components(n):
        attr = nominal_attr(c.name)
        c.static[attr] = c.static[attr + "_opt"]
        c.static.loc[c.static.build_year == period, attr + "_extendable"] = False


def apply_optimised_capacities(n: pypsa.Network, source: pypsa.Network) -> None:
    """Take the capacities decided in `source` and fix them in `n`.

    This is how a dispatch block runs against capacities an expansion block chose:
    the capacities come across as given, and dispatch cannot change them.
    """
    for c in capacity_components(n):
        attr = nominal_attr(c.name)
        c.static[attr] = source.c[c.name].static[attr + "_opt"]
        c.static[attr + "_extendable"] = False
