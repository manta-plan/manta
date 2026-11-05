# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Shared PyPSA work for the blocks in this library.

This is also where the blocks meet their data. A record points at a revision in a
datarecord store, locally or in S3: `store_network` starts a store with a network,
`to_network` builds a network from a revision, and `write_network` adds the network
a block produced as a child revision of it.
Both are confined to this module, so richer record storage only ever changes it.
"""

from typing import Any

import numpy as np
import pypsa
from datarecord import Revision, Workspace
from datarecord.tools.pypsa import PyPSA
from playbook.blocks.core import DataRecord

from playbook_library.pypsa_configs import PyPSAOptimizeSchema

BUILT_COMPONENTS = ["Generator", "Link", "StorageUnit", "Store", "Line", "Transformer"]
"""The components whose capacity is built in one investment period and lasts into later ones."""


def nominal_attr(component_name: str) -> str:
    """The name of a component's nominal capacity: stores hold energy, the rest power."""
    return {"Store": "e_nom", "Line": "s_nom", "Transformer": "s_nom"}.get(component_name, "p_nom")


def _revision(record: DataRecord) -> tuple[Workspace, Revision]:
    ws = Workspace()
    return ws, ws.store(record.url).revision(record.uuid)


def store_network(n: pypsa.Network, url: str) -> DataRecord:
    """Store `n` as the root revision of a new store at `url`, and point a record at it."""
    ws = Workspace()
    rev = ws.store(url).root(PyPSA.to_datarecord(n, ws.con))
    return DataRecord(url=url, uuid=rev.id)


def to_network(record: DataRecord, select: dict[str, Any] | None = None) -> pypsa.Network:
    """Build the network stored in the revision a record points at.

    Every call builds the network from the store again, so a block gets a network of
    its own and never has to copy one. `select` narrows what is built, such as a
    single investment period.
    """
    _, rev = _revision(record)
    missing = PyPSA.verify(rev.record, select=select)
    if missing:
        raise RuntimeError(missing.describe())
    return PyPSA.build(rev.record, select=select)


def investment_periods(record: DataRecord) -> list[int]:
    """The investment periods of the network a record points at, read without building it.

    A network without investment periods has none.
    """
    _, rev = _revision(record)
    if "period" not in rev.record.dims:
        return []
    return [period for (period,) in rev.record.dims["period"].fetchall()]


def write_network(
    n: pypsa.Network, parent_record: DataRecord, results_only: bool = False
) -> DataRecord:
    """Store `n` as a child revision of `parent_record`, and point a new record at it.

    Over a multi-period network, `n` may hold one investment period of it, its results
    written to that period alone.
    """
    ws, rev = _revision(parent_record)
    source = PyPSA.to_datarecord(n, ws.con, results_only=results_only, base=rev.record)
    return DataRecord(url=parent_record.url, uuid=rev.child(source).id)


def remove_unbuilt_cohorts(n: pypsa.Network) -> None:
    """Remove the cohorts `n` could only have built before its one investment period.

    A cohort is an extendable asset of a finite lifetime. One of an earlier build year
    that is active in the period but still extendable was not built in an earlier period
    solved, if there was one, so it has no capacity to bring. An asset of an infinite
    lifetime, such as a line, is not a cohort: it stays, and can still be built.
    """
    (period,) = n.investment_periods
    for c in n.components[BUILT_COMPONENTS]:
        static = c.static
        earlier = static[nominal_attr(c.name) + "_extendable"] & (static.build_year < period)
        n.remove(c.name, static.index[earlier & np.isfinite(static.lifetime)])


def optimize_network(
    n: pypsa.Network, config: PyPSAOptimizeSchema, **overrides: object
) -> pypsa.Network:
    """Optimise `n` with the given settings, overriding individual ones if asked.

    Overrides are passed straight through rather than folded into `config`, so a block
    can set what only makes sense to PyPSA for that block - solving across investment
    periods, say - without it having to be a setting a user could change.

    A solve that does not end optimal raises, so no block writes the results of one.
    """
    status, condition = n.optimize(**{**config.model_dump(), **overrides})
    if condition != "optimal":
        raise RuntimeError(f"PyPSA could not solve the network: {status} ({condition})")
    return n
