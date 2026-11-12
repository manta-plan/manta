# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Shared PyPSA work for the blocks in this library.

This is also where the blocks meet their data. A record points at a revision in a
datarecord store, locally or in S3: `to_network` builds a network from a revision,
and `write_network` adds the network a block produced as a child revision of it.
Both are confined to this module, so richer record storage only ever changes it.
"""

from collections.abc import Callable
from typing import Any

import numpy as np
import pypsa
from datarecord.tools.base import UnsupportedRecordError
from datarecord.tools.pypsa import PyPSA
from playbook.blocks.core import DataRecord, DataRecordError, SolveError

from playbook_library.datarecord_helpers import revision
from playbook_library.pypsa_configs import Aggregation, PyPSAOptimizeSchema
from playbook_library.pypsa_spatial_aggregation import (
    aggregate_network,
    dropped_assets,
    expand_network,
)
from playbook_library.pypsa_time_aggregation import PYPSA_LABELS, write_expanded_results
from playbook_library.time_aggregation import carry_time_properties

BUILT_COMPONENTS = ["Generator", "Link", "StorageUnit", "Store", "Line", "Transformer"]
"""The components whose capacity is built in one investment period and lasts into later ones."""


def nominal_attr(component_name: str) -> str:
    """The name of a component's nominal capacity: stores hold energy, the rest power."""
    return {"Store": "e_nom", "Line": "s_nom", "Transformer": "s_nom"}.get(component_name, "p_nom")


def to_network(record: DataRecord, select: dict[str, Any] | None = None) -> pypsa.Network:
    """Build the network stored in the revision a record points at.

    Every call builds the network from the store again, so a block gets a network of
    its own and never has to copy one. `select` narrows what is built, such as a
    single investment period.
    """
    _, rev = revision(record)
    try:
        return PyPSA.build(rev.record.select(**select) if select else rev.record)
    except UnsupportedRecordError as exc:
        raise DataRecordError(str(exc)) from exc


def investment_periods(record: DataRecord) -> list[int]:
    """The investment periods of the network a record points at, read without building it.

    A network without investment periods has none.
    """
    _, rev = revision(record)
    if "period" not in rev.record.dims:
        return []
    return [period for (period,) in rev.record.dims["period"].fetchall()]


def write_network(
    n: pypsa.Network, parent_record: DataRecord, results_only: bool = False
) -> DataRecord:
    """Store `n` as a child revision of `parent_record`, and point a new record at it.

    Over a network with investment periods, `n` may have one period of it, and its
    results are written to that period alone. The child keeps the snapshot properties of
    `parent_record` that `n` does not declare, such as time aggregations.
    """
    ws, rev = revision(parent_record)
    source = PyPSA.to_datarecord(n, ws.con, results_only=results_only, base=rev.record)
    source = carry_time_properties(source, rev.record, ws.con, PYPSA_LABELS)
    return DataRecord(url=parent_record.url, uuid=rev.store.commit(source, parent=rev).id)


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


def write_aggregated_results(
    n_c: pypsa.Network,
    n: pypsa.Network,
    record: DataRecord,
    aggregation: Aggregation,
    multi_investment_periods: bool,
) -> tuple[pypsa.Network, DataRecord]:
    """Store the results of `n_c` at every label of `record`, as one child revision of it.

    `n_c` is `n`, built from `record`, merged by `aggregation` and solved. It was solved
    over investment periods if `multi_investment_periods`. Buses and assets are expanded
    first, by `expand_network`, then snapshots, by `write_expanded_results`, which holds the
    results of the assets the aggregation left out. Returns `n_c`
    with its buses and assets expanded, and the new record.
    """
    expanded = expand_network(n_c, n, record, aggregation)
    if aggregation.snapshot is None:
        return expanded, write_network(expanded, record, results_only=True)
    left_out = dropped_assets(n, record, aggregation)
    written = write_expanded_results(
        expanded, n, record, aggregation.snapshot, multi_investment_periods, left_out
    )
    return expanded, written


def solve_and_write(
    n: pypsa.Network,
    record: DataRecord,
    optimize: Callable[[pypsa.Network], pypsa.Network],
    aggregation: Aggregation,
    multi_investment_periods: bool,
) -> tuple[pypsa.Network, DataRecord]:
    """Solve `n`, built from `record`, with `optimize`, and store its results under `record`.

    The results form a child revision of `record`. Only the results are written, so the
    inputs of `record` stay as they are. `optimize` solves `n` merged by `aggregation`, and
    the results are expanded to every bus, asset and snapshot of `record`.
    `multi_investment_periods` sets whether the expansion treats the solve as one over
    investment periods. Without any aggregation, `optimize` solves `n` as it is. Returns
    the solved network, with its buses and assets expanded, and the new record.
    """
    solved = optimize(aggregate_network(n, record, aggregation))
    return write_aggregated_results(solved, n, record, aggregation, multi_investment_periods)
