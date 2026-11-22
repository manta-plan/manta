# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Shared PyPSA work for the blocks in this library.

This is also where the blocks meet their data, revisions of a datarecord store, locally
or in S3: `store_network` starts a store with a network, `to_network` builds a network
from a revision, and `write_network` adds the network a block produced as a child
revision of it, through the same store and so the same workspace.
All three are confined to this module, so a change in how networks are stored only ever
changes it.
"""

from typing import Any

import numpy as np
import pypsa
from datarecord import Revision, Store
from datarecord.tools.base import UnsupportedRecordError
from datarecord.tools.pypsa import PyPSA
from playbook.blocks.core import DataRecordError, SolveError

from playbook_library.pypsa_configs import PyPSAOptimizeSchema

BUILT_COMPONENTS = ["Generator", "Link", "StorageUnit", "Store", "Line", "Transformer"]
"""The components whose capacity is built in one investment period and lasts into later ones."""


def nominal_attr(component_name: str) -> str:
    """The name of a component's nominal capacity: stores hold energy, the rest power."""
    return {"Store": "e_nom", "Line": "s_nom", "Transformer": "s_nom"}.get(component_name, "p_nom")


def store_network(n: pypsa.Network, store: Store) -> Revision:
    """Store `n` as the root revision of `store`."""
    return store.commit(PyPSA.to_datarecord(n, store.workspace.con), parent=None)


def to_network(rev: Revision, select: dict[str, Any] | None = None) -> pypsa.Network:
    """Build the network stored in `rev`.

    Every call builds the network from the store again, so a block gets a network of
    its own and never has to copy one. `select` narrows what is built, such as a
    single investment period.
    """
    try:
        return PyPSA.build(rev.record.select(**select) if select else rev.record)
    except UnsupportedRecordError as exc:
        raise DataRecordError(str(exc)) from exc


def investment_periods(rev: Revision) -> list[int]:
    """The investment periods of the network in `rev`, read without building it.

    A network without investment periods has none.
    """
    if "period" not in rev.record.dims:
        return []
    return [period for (period,) in rev.record.dims["period"].fetchall()]


def write_network(n: pypsa.Network, parent: Revision, results_only: bool = False) -> Revision:
    """Store `n` as a child revision of `parent`.

    Over a multi-period network, `n` may hold one investment period of it, its results
    written to that period alone.
    """
    source = PyPSA.to_datarecord(
        n, parent.store.workspace.con, results_only=results_only, base=parent.record
    )
    return parent.store.commit(source, parent=parent)


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
        raise SolveError(f"PyPSA could not solve the network: {status} ({condition})")
    return n
