# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Shared PyPSA work for the blocks in this library.

This is also where the blocks meet their data, revisions of a datarecord store, locally
or in S3: `to_network` builds a network from a revision, and `write_network` adds the
network a block produced as a child revision of it, through the same store and so the
same workspace. Both are confined to this module, so a change in how networks are stored
only ever changes it.
"""

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pypsa
from datarecord import Revision, WorkingRecord
from datarecord.tools.base import UnsupportedRecordError
from datarecord.tools.pypsa import PyPSA
from playbook.blocks.core import DataRecordError, SolveError

from playbook_library.pypsa_configs import (
    Aggregation,
    LoadSheddingConfig,
    PyPSAFixedCapacityBlockConfig,
    PyPSAOptimizeSchema,
)
from playbook_library.pypsa_spatial_aggregation import (
    LAND_USE,
    aggregate_network,
    dropped_assets,
    expand_network,
)
from playbook_library.pypsa_time_aggregation import (
    PYPSA_LABELS,
    STATES,
    snapshot_rows,
    write_expanded_results,
)
from playbook_library.time_aggregation import carry_time_properties

BUILT_COMPONENTS = ["Generator", "Link", "StorageUnit", "Store", "Line", "Transformer"]
"""The components whose capacity is built in one investment period and lasts into later ones."""


def nominal_attr(component_name: str) -> str:
    """The name of a component's nominal capacity: stores hold energy, the rest power."""
    return {"Store": "e_nom", "Line": "s_nom", "Transformer": "s_nom"}.get(component_name, "p_nom")


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

    Over a network with investment periods, `n` may have one period of it, and its
    results are written to that period alone. The child keeps the snapshot properties of
    `parent` that `n` does not declare, such as time aggregations.
    """
    con = parent.store.workspace.con
    source = PyPSA.to_datarecord(n, con, results_only=results_only, base=parent.record)
    source = carry_time_properties(source, parent.record, con, PYPSA_LABELS)
    return parent.store.commit(source, parent=parent)


def with_load_shedding(
    rev: Revision, config: LoadSheddingConfig | None, entity: str | None
) -> Revision:
    """Add load shedding by `config` to the network of `rev`, stored as a child revision.

    The load-shedding generators are then part of the stored model, so a later
    results-only write includes their results. They are `existing` assets with their
    carrier as the value of the `entity` property, so that an entity aggregation merges
    them. Without `config`, `rev` is returned as it is.
    """
    if config is None:
        return rev
    n = to_network(rev)
    before = n.c.generators.static.index
    n.optimize.add_load_shedding(**config.model_dump())
    added = n.c.generators.static.index.difference(before)
    n.c.generators.static.loc[added, "asset_status"] = "existing"
    if entity is not None:
        n.c.generators.static.loc[added, entity] = n.c.generators.static.loc[added, "carrier"]
    return write_network(n, rev)


def write_series(rev: Revision, attribute: str, values: pd.DataFrame) -> Revision:
    """Store `values` as input `attribute` in a child revision of `rev`.

    `values` has a column per entity and a row per snapshot of a network built from
    `rev`. The child holds these rows alone, so everything else reads as in `rev`.
    """
    con = rev.store.workspace.con
    rows = values.melt(var_name="entity").assign(snapshot=list(values.index) * values.shape[1])
    edits = WorkingRecord(rev.record)
    edits.set(attribute, snapshot_rows(rev.record.schema, con, rows, ["snapshot"]))
    return rev.store.commit(edits)


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


def solved_periods(rev: Revision) -> list[int]:
    """Return the investment periods that `rev` has results for, without building a network.

    A revision without the result `p` or without investment periods has none.
    """
    if "p" not in rev.record.attributes or "period" not in rev.record.dims:
        return []
    solved = rev.record.attributes["p"].filter("snapshot IS NOT NULL")
    held = solved.project("snapshot.period").distinct()
    return sorted(period for (period,) in held.fetchall())


def selected_periods(rev: Revision, periods: list[int] | None) -> list[int]:
    """Return the investment periods of `rev` that `periods` selects, in model order.

    None selects all of them. Raises `ValueError` if `periods` is set and the model has no
    investment periods, or lacks one of those set.
    """
    held = investment_periods(rev)
    if periods is None:
        return held
    if not held:
        raise ValueError("The model has no investment periods to select some of.")
    missing = sorted(set(periods) - set(held))
    if missing:
        raise ValueError(f"The model has no investment periods {missing}: {held}.")
    return [period for period in held if period in periods]


def decided_capacities(rev: Revision) -> pd.Series:
    """Return the optimised capacity of each asset that `rev` has one for, by asset name.

    It reads the revision, not a network built from it, because a network fills an
    undecided capacity with 0.
    """
    names = {nominal_attr(c) + "_opt" for c in BUILT_COMPONENTS} & set(rev.record.attributes)
    frames = [rev.record.attributes[name].df().set_index("entity")["value"] for name in names]
    return pd.concat(frames) if frames else pd.Series(dtype=float)


def extendable_assets(n: pypsa.Network) -> dict[str, pd.Index]:
    """Return the extendable assets of each built component of `n` that has some, by name."""
    assets = {}
    for c in n.components[BUILT_COMPONENTS]:
        static = c.static
        extendable = static.index[static[nominal_attr(c.name) + "_extendable"]]
        if not extendable.empty:
            assets[c.name] = extendable
    return assets


def apply_decided_capacities(n: pypsa.Network, decided: pd.Series) -> None:
    """Fix the capacity of each extendable asset of `n` that `decided` has one for, by name.

    Such an asset takes its decided capacity and stops being extendable, so a solve cannot
    change it. An asset that is not extendable keeps its own capacity.
    """
    for name, extendable in extendable_assets(n).items():
        attr = nominal_attr(name)
        static = n.components[name].static
        fixed = extendable.intersection(decided.index)
        static.loc[fixed, attr] = decided[fixed]
        static.loc[fixed, attr + "_extendable"] = False


def refuse_undecided_capacities(n: pypsa.Network) -> None:
    """Raise `ValueError` if an asset of `n` is still extendable, its capacity undecided."""
    undecided = {name: assets.tolist() for name, assets in extendable_assets(n).items()}
    if undecided:
        raise ValueError(f"The record decided no capacity of {undecided}")


def restarting_storage(
    static: pd.DataFrame, state: str, multi_investment_periods: bool
) -> pd.Series:
    """Mark each asset of `static` whose `state` a rolling horizon window starts afresh.

    `state` is a key of `STATES`. Cyclic storage cycles within each window. Over investment
    periods, storage that cycles or starts afresh per period does so within each window too.
    """
    _, cyclic, cycles_per_period, starts_per_period, _ = STATES[state]
    per_period = static[cycles_per_period] | static[starts_per_period]
    return static[cyclic] | (multi_investment_periods & per_period)


def fix_capacities(n: pypsa.Network, rev: Revision, periods: list[int]) -> None:
    """Fix in `n` the capacities that `rev` decided, `n` being built from it over `periods`.

    Each extendable asset takes the capacity a solve of `rev` decided, and every other
    asset keeps its own. Over a single period, overnight expansion removes the cohorts only
    an earlier period could have built. So this removes them too, where `rev` decided no
    capacity for them. With nothing left to build, the limits on capacity expansion, such
    as land use, limit nothing, so they are removed too. Raises `ValueError` if `n` has an
    extendable asset and `rev` has no results for one of `periods`, or if an extendable
    asset is left without a decided capacity.
    """
    limits = n.c.global_constraints.static
    n.remove("GlobalConstraint", limits.index[limits["type"] == LAND_USE])
    if not extendable_assets(n):
        return
    unsolved = sorted(set(periods).difference(solved_periods(rev))) if periods else []
    if unsolved:
        raise ValueError(f"The record holds no results of the periods {unsolved}.")
    apply_decided_capacities(n, decided_capacities(rev))
    if len(periods) == 1:
        remove_unbuilt_cohorts(n)
    refuse_undecided_capacities(n)


def unscope_global_constraints(n: pypsa.Network, windowed: bool) -> None:
    """Let the global constraints of the one investment period of `n` hold over every snapshot.

    PyPSA solves a network without investment periods only with global constraints of no
    period. Over one period, those of it hold over every snapshot, and those of another
    hold over none, so they are removed. A network of several periods is left as it is.

    A `windowed` solve, such as a rolling horizon, holds each such constraint within each
    window in full. That is the limit of the period only if it is 0, so raises `ValueError`
    for a constraint of the period with another limit.
    """
    if len(n.investment_periods) != 1:
        return
    (period,) = n.investment_periods
    scoped = n.c.global_constraints.static["investment_period"]
    n.remove("GlobalConstraint", scoped.index[scoped.notna() & (scoped != period)])
    static = n.c.global_constraints.static
    own = static["investment_period"] == period
    split = static.index[own & (static["constant"] != 0)]
    if windowed and not split.empty:
        raise ValueError(
            f"The global constraints {split.tolist()} limit the period {period} as a whole, "
            "which a rolling horizon would apply to each window in full."
        )
    static.loc[own, "investment_period"] = np.nan


def fixed_capacity_model(
    rev: Revision, config: PyPSAFixedCapacityBlockConfig, windowed: bool
) -> tuple[Revision, pypsa.Network]:
    """Return `rev` with the load shedding of `config`, and its network to solve.

    The network covers the `periods` of `config`, with the capacities a solve of `rev`
    decided. Not solved over investment periods, the global constraints of its one period
    hold over every snapshot, as `unscope_global_constraints` sets out for `windowed`.
    """
    periods = selected_periods(rev, config.periods)
    model = with_load_shedding(rev, config.load_shedding, config.aggregation.entity)
    n = to_network(model, select={"period": periods}) if periods else to_network(model)
    fix_capacities(n, rev, periods)
    if not config.optimize_config.multi_investment_periods:
        unscope_global_constraints(n, windowed)
    return model, n


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
    rev: Revision,
    aggregation: Aggregation,
    multi_investment_periods: bool,
) -> tuple[pypsa.Network, Revision]:
    """Store the results of `n_c` at every label of `rev`, as one child revision of it.

    `n_c` is `n`, built from `rev`, merged by `aggregation` and solved. It was solved
    over investment periods if `multi_investment_periods`. Buses and assets are expanded
    first, by `expand_network`, then snapshots, by `write_expanded_results`, which holds the
    results of the assets the aggregation left out. Returns `n_c`
    with its buses and assets expanded, and the new revision.
    """
    expanded = expand_network(n_c, n, rev, aggregation)
    if aggregation.snapshot is None:
        return expanded, write_network(expanded, rev, results_only=True)
    left_out = dropped_assets(n, rev, aggregation)
    written = write_expanded_results(
        expanded, n, rev, aggregation.snapshot, multi_investment_periods, left_out
    )
    return expanded, written


def solve_and_write(
    n: pypsa.Network,
    rev: Revision,
    optimize: Callable[[pypsa.Network], pypsa.Network],
    aggregation: Aggregation,
    multi_investment_periods: bool,
) -> tuple[pypsa.Network, Revision]:
    """Solve `n`, built from `rev`, with `optimize`, and store its results under `rev`.

    The results form a child revision of `rev`. Only the results are written, so the
    inputs of `rev` stay as they are. `optimize` solves `n` merged by `aggregation`, and
    the results are expanded to every bus, asset and snapshot of `rev`.
    `multi_investment_periods` sets whether the expansion treats the solve as one over
    investment periods. Without any aggregation, `optimize` solves `n` as it is. Returns
    the solved network, with its buses and assets expanded, and the new revision.
    """
    solved = optimize(aggregate_network(n, rev, aggregation))
    return write_aggregated_results(solved, n, rev, aggregation, multi_investment_periods)
