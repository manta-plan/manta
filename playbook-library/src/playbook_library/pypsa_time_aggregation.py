# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Time aggregation of PyPSA networks built from a datarecord.

A time aggregation maps each snapshot to a representative snapshot, the first of its
cluster. A record keeps it as a `snapshot.<name>` property. A network built from the record
is clustered to the representative snapshots and solved. Its results are then expanded back
to every snapshot of the record by the rules in `time_aggregation`.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd
import pypsa
from datarecord import LazyRelations, RecordLike, Schema
from datarecord.tools.pypsa import PyPSA
from duckdb import DuckDBPyConnection, DuckDBPyRelation
from duckdb.sqltypes import DuckDBPyType
from playbook.blocks.core import DataRecord

from playbook_library.datarecord_helpers import revision
from playbook_library.time_aggregation import (
    Overlay,
    TimeAxis,
    TimeLabels,
    checked_clusters,
    cluster_members,
    cluster_starts,
    held,
    interpolated,
    settled,
    shaped,
    time_aggregations,
    time_relation,
)

PYPSA_TIME = TimeAxis("snapshot", "timestep", "period")
"""The time axis of a record with investment periods, whose snapshots are structs."""


def has_periods(schema: Schema) -> bool:
    """Whether a record of `schema` has investment periods, so `snapshot` is a multi-dim."""
    return PYPSA_TIME.dim in schema.multi_dims


def pypsa_time(schema: Schema) -> TimeAxis:
    """Return the time axis of a record of `schema`.

    Without investment periods, a time aggregation refers to `snapshot` itself.
    """
    if has_periods(schema):
        return PYPSA_TIME
    return TimeAxis(PYPSA_TIME.dim, PYPSA_TIME.dim, None)


def snapshot_labels(schema: Schema, column: pd.Series) -> pd.Series:
    """Return the snapshots in `column`, read from a record of `schema`, as PyPSA labels them.

    A record with investment periods stores a snapshot as a struct, which PyPSA labels by
    the tuple `(period, timestep)`. Any other snapshot is its timestep already.
    """
    if not has_periods(schema):
        return column
    return column.map(lambda s: (s["period"], s["timestep"]), na_action="ignore")


def _typed(
    con: DuckDBPyConnection, frame: pd.DataFrame, types: dict[str, DuckDBPyType]
) -> DuckDBPyRelation:
    """Return `frame` as a relation, with each column in `types` cast to its type."""
    rel = con.from_df(frame)
    casts = {c: f'CAST("{c}" AS {t}) AS "{c}"' for c, t in types.items()}
    return rel.project(", ".join(casts.get(c, f'"{c}"') for c in rel.columns))


def _packed(schema: Schema, frame: pd.DataFrame, labels: Sequence[str]) -> pd.DataFrame:
    """Return `frame` with the snapshots in columns `labels` as structs, if `schema` has periods."""
    if not has_periods(schema):
        return frame
    structs = {
        c: frame[c].map(lambda s: {"period": s[0], "timestep": s[1]}, na_action="ignore")
        for c in labels
    }
    return frame.assign(**structs)


def snapshot_rows(
    schema: Schema, con: DuckDBPyConnection, frame: pd.DataFrame, labels: Sequence[str]
) -> DuckDBPyRelation:
    """Return `frame` as a relation, with the snapshots in columns `labels` as `schema` has them.

    It reverses `snapshot_labels`.
    """
    snapshot = schema.duck_type(schema.dimensions["snapshot"])
    return _typed(con, _packed(schema, frame, labels), dict.fromkeys(labels, snapshot))


def snapshot_axis(schema: Schema, con: DuckDBPyConnection, frame: pd.DataFrame) -> DuckDBPyRelation:
    """Return `frame`, the snapshots and properties as `snapshot_frame` gives them, as stored.

    It reverses `snapshot_frame` over the columns of the `snapshot` axis of `schema`.
    """
    axis = pypsa_time(schema)
    aggregations = time_aggregations(schema, axis)
    if has_periods(schema):
        frame = frame.assign(
            **{n: frame[n].map(lambda s: s[1], na_action="ignore") for n in aggregations}
        )
    step = schema.duck_type(schema.dimensions[axis.step])
    types = {"snapshot": schema.duck_type(schema.dimensions["snapshot"])}
    return _typed(
        con, _packed(schema, frame, ["snapshot"]), types | dict.fromkeys(aggregations, step)
    )


def snapshot_frame(record: RecordLike) -> pd.DataFrame:
    """Return every snapshot of `record` with its properties, in axis order.

    Snapshots, and the representatives of time aggregations, are labelled as by
    `snapshot_labels`. Each snapshot also has its `period` and `timestep`. Without
    investment periods, every snapshot has `period` 0 and is its own timestep.
    """
    schema = record.schema
    frame = time_relation(record, PYPSA_TIME).df()
    if not has_periods(schema):
        return frame.assign(period=0, timestep=frame["snapshot"])
    frame = frame.assign(**pd.DataFrame(frame["snapshot"].tolist()))
    frame["snapshot"] = snapshot_labels(schema, frame["snapshot"])
    for name in time_aggregations(schema, PYPSA_TIME):
        pairs = zip(frame["period"], frame[name], strict=True)
        frame[name] = pd.Series(list(pairs), dtype=object).where(frame[name].notna())
    return frame


def series_frame(record: RecordLike, attribute: str) -> pd.DataFrame:
    """Return the rows of `attribute` of `record`, labelled as by `snapshot_labels`."""
    frame = record.attributes[attribute].df()
    if "snapshot" not in frame:
        return frame
    return frame.assign(snapshot=snapshot_labels(record.schema, frame["snapshot"]))


PYPSA_LABELS = TimeLabels(pypsa_time, snapshot_frame, snapshot_axis)
"""How PyPSA labels the snapshots of a record, read as a frame and stored back."""


def _network_snapshots(base: RecordLike, frame: pd.DataFrame) -> pd.Index:
    """Return the snapshots in `frame` as PyPSA indexes them in a network built from `base`.

    With investment periods, the index has the levels `period` and `timestep`.
    """
    if not has_periods(base.schema):
        return pd.Index(frame["timestep"], name="snapshot")
    return pd.MultiIndex.from_frame(frame[["period", "timestep"]])


def _held_frame(n: pypsa.Network, base: RecordLike) -> pd.DataFrame:
    """Return the snapshots of `base` in the investment periods `n` has, as `snapshot_frame` does.

    A network built from a `base` with investment periods may have only some of them.
    """
    frame = snapshot_frame(base)
    if not has_periods(base.schema):
        return frame
    return frame[frame["period"].isin(n.snapshots.unique(level="period"))]


def cluster_network(n: pypsa.Network, record: DataRecord, name: str) -> pypsa.Network:
    """Cluster `n`, built from `record`, by the time aggregation `snapshot.<name>` of `record`.

    `n` may have only some investment periods of `record`. Each cluster becomes one
    snapshot at its representative, weighted by the sum of its snapshots' weightings.
    Series are aggregated as PyPSA's `from_snapshot_map` aggregates them. Raises
    `ValueError` if `record` has no valid `snapshot.<name>`.
    """
    base = revision(record)[1].record
    frame = _held_frame(n, base)
    representatives = checked_clusters(frame, name, pypsa_time(base.schema))
    snapshots = _network_snapshots(base, frame)
    positions = pd.Index(frame["snapshot"]).get_indexer(representatives)
    snapshot_map = pd.Series(list(snapshots[positions]), index=snapshots)
    return n.cluster.temporal.from_snapshot_map(snapshot_map)


STATES = {
    "state_of_charge": (
        "StorageUnit",
        "cyclic_state_of_charge",
        "cyclic_state_of_charge_per_period",
        "state_of_charge_initial_per_period",
        "state_of_charge_initial",
    ),
    "e": ("Store", "e_cyclic", "e_cyclic_per_period", "e_initial_per_period", "e_initial"),
}
"""The results that are a state at the end of a snapshot, with the attributes that set its start.

Each maps to its component, its flags for cycling over the horizon, cycling per period and
starting afresh per period, and its initial state.
"""


def _starts(
    n_c: pypsa.Network,
    unsolved: pypsa.Network,
    name: str,
    leads: pd.DataFrame,
    multi_investment_periods: bool,
) -> pd.DataFrame:
    """Return the state `name` of each entity of `n_c` before each of its snapshots.

    `leads` has the row of the record for each snapshot of `n_c`, and labels the result.
    A cluster starts where PyPSA starts it. Storage that cycles ends where it starts.
    Solved over investment periods, storage that cycles per period opens each period at
    that period's last state. Storage that starts afresh per period opens it at its
    initial state. Within a period, both carry over the state of the snapshot before.
    Any other storage opens its first active cluster at its last active state if it
    cycles, or at its initial state if not. Each later cluster carries over the last
    active state. An inactive cluster keeps its own state. Initial states come from
    `unsolved`, because a solve may overwrite them.
    """
    ctype, *flags, initial_state = STATES[name]
    c = n_c.components[ctype]
    states = c.dynamic[name]
    active = c.get_activity_mask(index=states.columns).to_numpy(bool)
    cyclic, cycles_per_period, starts_per_period = (
        c.static.loc[states.columns, flags].to_numpy(bool).T
    )
    initial = unsolved.components[ctype].static.loc[states.columns, initial_state].to_numpy(float)
    values = states.to_numpy()
    carried = np.roll(states.where(active).ffill().to_numpy(), 1, axis=0)
    lagged = pd.DataFrame(carried).ffill().to_numpy()
    first = active & (active.cumsum(axis=0) == 1)
    overall = np.where(first & ~cyclic, initial, lagged)
    opens = cluster_starts(leads, "period")[:, None]
    ends = states.groupby(leads["period"].to_numpy()).transform("last").to_numpy()
    wrapped = np.where(cycles_per_period, ends, initial)
    per_period = np.where(opens, wrapped, np.roll(values, 1, axis=0))
    by_period = multi_investment_periods & (cycles_per_period | starts_per_period)
    opening = np.where(by_period, per_period, overall)
    previous = pd.DataFrame(np.where(active, opening, values), columns=states.columns)
    previous["snapshot"] = leads["snapshot"].to_numpy()
    return previous.melt(id_vars="snapshot", var_name="entity", value_name="previous")


def _weighting(base: RecordLike, frame: pd.DataFrame, attribute: str) -> np.ndarray:
    """Return the snapshot weighting `attribute` of `base` at each snapshot of `frame`.

    It is read as PyPSA builds it: rows reach snapshots by the broadcast rule, and a
    snapshot that none reaches weighs 1, PyPSA's default.
    """
    if attribute not in base.attributes:
        return np.ones(len(frame))
    rows = settled(base, attribute, PYPSA_TIME).df()
    labelled = rows.assign(snapshot=snapshot_labels(base.schema, rows["snapshot"]))
    return frame["snapshot"].map(labelled.set_index("snapshot")["value"]).fillna(1.0).to_numpy()


def _series_of(base: RecordLike, attribute: str, ctype: str) -> DuckDBPyRelation:
    """Return the rows of input `attribute` over snapshots for the entities of component `ctype`.

    Without `attribute` in `base`, the relation is empty with the same columns.
    """
    entities = base.properties["entity"].filter(f"ctype = '{ctype}'").project("entity")
    if attribute not in base.attributes:
        return entities.filter("false").project(
            "entity, NULL AS snapshot, NULL AS scenario, NULL::DOUBLE AS value"
        )
    rows = settled(base, attribute, PYPSA_TIME)
    return rows.join(entities, "entity").project("entity, snapshot, scenario, value")


def write_expanded_results(
    n_c: pypsa.Network,
    unsolved: pypsa.Network,
    record: DataRecord,
    name: str,
    multi_investment_periods: bool,
    left_out: Sequence[str] = (),
) -> DataRecord:
    """Store the results of `n_c` at every snapshot of `record`, as one child revision of it.

    `n_c` is the network of `record`, or some investment periods of it, clustered by
    `snapshot.<name>` and solved. It was solved over investment periods if
    `multi_investment_periods`. `unsolved` is that network before the solve, with the
    initial states it started from. Rows of the periods `n_c` lacks are those that a
    results-only write of `n_c` gives. Rows at the representative snapshots are kept and
    spread over their clusters by these rules:

    - A load draws its original `p_set`.
    - A generator with a `p_max_pu` series follows that series within a cluster. Its
      dispatch is scaled by `p_max_pu` over its cluster mean, weighted by the generator
      weightings. It is capped at `p_nom_opt * p_max_pu`, and held where that mean is 0.
    - A state (`state_of_charge`, `e`) runs from the state its cluster starts at to its
      own at the cluster's end. It moves in step with the store weightings. A cluster starts where
      PyPSA starts it: wrapped, at the initial state or carried over. An inactive cluster
      keeps the state PyPSA reports there.
    - Any other series, flows and duals alike, is held over its cluster.
    - An asset in `left_out`, which the solve left out, draws no demand and starts each
      cluster empty, so it keeps the zero flows and states `n_c` gives it.

    Held flows and uncapped generation keep the weighted energy of each cluster. PyPSA
    averages `p_set` and `p_max_pu` unweighted. So only with uniform weightings within a
    cluster does the cap never bind and the expanded dispatch balance per cluster. The
    expanded dispatch never balances at each snapshot.

    Raises `NotImplementedError` for a stochastic network. Raises `ValueError` if `record`
    has no valid `snapshot.<name>`, or `n_c` is not clustered by it.
    """
    if n_c.has_scenarios:
        raise NotImplementedError("Expanding the results of a stochastic network")
    ws, rev = revision(record)
    base = rev.record
    frame = _held_frame(n_c, base)
    axis = pypsa_time(base.schema)
    checked_clusters(frame, name, axis)
    leads = frame[cluster_starts(frame, name)]
    if not n_c.snapshots.equals(_network_snapshots(base, leads)):
        raise ValueError(f"The network is not clustered by snapshot.{name}")
    results = PyPSA.to_datarecord(n_c, ws.con, results_only=True, base=base)
    weightings = ("snapshot_weighting_generators", "snapshot_weighting_stores")
    snapshots = snapshot_frame(base)
    weight, progress = (_weighting(base, snapshots, attribute) for attribute in weightings)
    clusters = cluster_members(snapshots, name, weight, progress, axis)
    members = snapshot_rows(base.schema, ws.con, clusters, ["snapshot", "rep"])
    dropped = ws.con.from_df(pd.DataFrame({"entity": list(left_out)}, dtype=str))
    demand = _series_of(base, "p_set", "Load").join(dropped, "entity", how="anti")
    profile = _series_of(base, "p_max_pu", "Generator")
    capacities = n_c.generators["p_nom_opt"].rename("value").rename_axis("entity")
    capacity = ws.con.from_df(capacities.reset_index())
    held_snapshots = snapshot_rows(base.schema, ws.con, frame[["snapshot"]], ["snapshot"])

    def expanded(attribute: str) -> DuckDBPyRelation:
        rel = results.attributes[attribute]
        if "snapshot" not in rel.columns:
            return rel
        inside = rel.join(held_snapshots, "snapshot", how="semi")
        elsewhere = rel.join(held_snapshots, "snapshot", how="anti")
        return spread(attribute, inside).union(elsewhere)

    def spread(attribute: str, rel: DuckDBPyRelation) -> DuckDBPyRelation:
        if attribute in STATES:
            previous = _starts(n_c, unsolved, attribute, leads, multi_investment_periods)
            previous.loc[previous["entity"].isin(left_out), "previous"] = 0.0
            starts = snapshot_rows(base.schema, ws.con, previous, ["snapshot"])
            return interpolated(rel, members, starts, axis)
        if attribute == "p":
            return shaped(rel, members, demand, profile, capacity, axis)
        return held(rel, members, axis)

    attributes = LazyRelations(tuple(results.attributes), expanded)
    child = rev.store.commit(Overlay(results, attributes=attributes), parent=rev)
    return DataRecord(url=record.url, uuid=child.id)
