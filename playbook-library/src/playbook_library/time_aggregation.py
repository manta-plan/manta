# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Time aggregations of a datarecord, and the rules that expand series over them.

A time aggregation maps each snapshot to a representative snapshot, so a model solves fewer
snapshots. The snapshots that share a representative form a cluster. A cluster is a
contiguous stretch within one investment period, one of the years a model builds capacity
in. Its first snapshot is its representative. A record keeps each time aggregation as a
`snapshot.<name>` property, the timestep of each snapshot's representative. The functions
here expand series over the representative snapshots back to every snapshot of their
clusters.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd
from datarecord import Flags, PropertySpec, RecordLike, Relations, Schema
from duckdb import DuckDBPyConnection, DuckDBPyRelation
from duckdb.sqltypes import DuckDBPyType


def snapshot_relation(record: RecordLike) -> DuckDBPyRelation:
    """Return the `snapshot` axis of `record`, with its properties where it has any."""
    relations = record.properties if "snapshot" in record.properties else record.dims
    return relations["snapshot"]


def has_periods(schema: Schema) -> bool:
    """Whether a record of `schema` has investment periods, so `snapshot` is a multi-dim."""
    return "snapshot" in schema.multi_dims


def timestep_dim(schema: Schema) -> str:
    """Return the dim of the timesteps of `schema`, `timestep` with investment periods."""
    return "timestep" if has_periods(schema) else "snapshot"


def time_aggregations(schema: Schema) -> list[str]:
    """Return the time aggregations of `schema`, the snapshot properties that refer to timesteps.

    A record cannot refer to a snapshot of a multi-dim `snapshot`. So a time aggregation
    stores the timestep of each representative, which is in the period of its snapshot.
    """
    properties = schema.properties.get("snapshot", {})
    return [name for name, spec in properties.items() if spec.one_of == timestep_dim(schema)]


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
    aggregations = time_aggregations(schema)
    if has_periods(schema):
        frame = frame.assign(
            **{n: frame[n].map(lambda s: s[1], na_action="ignore") for n in aggregations}
        )
    timestep = schema.duck_type(schema.dimensions[timestep_dim(schema)])
    types = {"snapshot": schema.duck_type(schema.dimensions["snapshot"])}
    return _typed(
        con, _packed(schema, frame, ["snapshot"]), types | dict.fromkeys(aggregations, timestep)
    )


def snapshot_frame(record: RecordLike) -> pd.DataFrame:
    """Return every snapshot of `record` with its properties, in axis order.

    Snapshots, and the representatives of time aggregations, are labelled as by
    `snapshot_labels`. Each snapshot also has its `period` and `timestep`. Without
    investment periods, every snapshot has `period` 0 and is its own timestep.
    """
    schema = record.schema
    frame = snapshot_relation(record).df()
    if not has_periods(schema):
        return frame.assign(period=0, timestep=frame["snapshot"])
    frame = frame.assign(**pd.DataFrame(frame["snapshot"].tolist()))
    frame["snapshot"] = snapshot_labels(schema, frame["snapshot"])
    for name in time_aggregations(schema):
        pairs = zip(frame["period"], frame[name], strict=True)
        frame[name] = pd.Series(list(pairs), dtype=object).where(frame[name].notna())
    return frame


def series_frame(record: RecordLike, attribute: str) -> pd.DataFrame:
    """Return the rows of `attribute` of `record`, labelled as by `snapshot_labels`."""
    frame = record.attributes[attribute].df()
    if "snapshot" not in frame:
        return frame
    return frame.assign(snapshot=snapshot_labels(record.schema, frame["snapshot"]))


def widened(schema: Schema, properties: dict[str, PropertySpec]) -> Schema:
    """Return a copy of `schema` that also declares `properties` of `snapshot`."""
    snapshot = {**schema.properties.get("snapshot", {}), **properties}
    widened = {**schema.properties, "snapshot": snapshot}
    return schema.model_validate({**schema.model_dump(), "properties": widened})


class Overlay:
    """A record-like view of `source`, with its schema, properties or attributes replaced.

    Each part left as None is that of `source`, and nothing is copied.
    """

    def __init__(
        self,
        source: RecordLike,
        schema: Schema | None = None,
        properties: Relations | None = None,
        attributes: Relations | None = None,
    ) -> None:
        self.source = source
        self.dims = source.dims
        self.schema = source.schema if schema is None else schema
        self.properties = source.properties if properties is None else properties
        self.attributes = source.attributes if attributes is None else attributes

    def flags(self, **categories: str | Sequence[str]) -> dict[str, Flags]:
        return self.source.flags(**categories)


def carry_snapshot_properties(
    source: RecordLike, base: RecordLike, con: DuckDBPyConnection
) -> RecordLike:
    """Add to `source` the snapshot properties that only `base` declares, at their values in `base`.

    A snapshot property that `source` declares keeps its value in `source`. Without any to
    add, `source` is returned as it is.
    """
    own = source.schema.properties.get("snapshot", {})
    declared = base.schema.properties.get("snapshot", {})
    carried = {name: spec for name, spec in declared.items() if name not in own}
    if not carried:
        return source
    kept = snapshot_frame(base)[["snapshot", *carried]]
    own_axis = snapshot_frame(source)[snapshot_relation(source).columns]
    frame = own_axis.merge(kept, on="snapshot", how="left")
    schema = widened(source.schema, carried)
    properties = {**source.properties, "snapshot": snapshot_axis(schema, con, frame)}
    return Overlay(source, schema, properties=properties)


def cluster_starts(frame: pd.DataFrame, name: str) -> np.ndarray:
    """Mark each row of `frame` that starts a run of equal values in column `name`.

    The first row always starts one. Over a time aggregation the runs are its clusters, and
    over `period` they are the investment periods.
    """
    representatives = frame[name].to_numpy()
    return np.r_[True, representatives[1:] != representatives[:-1]]


def checked_clusters(frame: pd.DataFrame, name: str) -> pd.Series:
    """Return the time aggregation `snapshot.<name>` of `frame`, after checking its clusters.

    Raises `ValueError` if `frame` has no such column, or a snapshot without a
    representative. It also raises if a cluster crosses an investment period, is split
    into separate runs, or does not start at its representative.
    """
    if name not in frame or frame[name].isna().any():
        raise ValueError(
            f"The record has no time aggregation snapshot.{name}: add one with a cluster_time "
            f"step named {name!r} before this one"
        )
    representatives = frame[name].to_numpy()
    starts = cluster_starts(frame, name)
    opens = cluster_starts(frame, "period")
    led = (representatives[starts] == frame["snapshot"].to_numpy()[starts]).all()
    if not (led and starts[opens].all() and pd.Series(representatives[starts]).is_unique):
        raise ValueError(
            f"snapshot.{name} is not contiguous clusters within a period, each led by its "
            "representative"
        )
    return frame[name]


def cluster_members(base: RecordLike, name: str, weight: str, progress: str) -> pd.DataFrame:
    """Return each snapshot with its representative `rep` under `snapshot.<name>`.

    Each row also has the snapshot's `weight` and `progress`. The arguments `weight` and
    `progress` name snapshot weightings of `base`. A snapshot's `progress` is the share of
    its cluster's total `progress` weighting reached by the end of that snapshot. Snapshots
    are labelled as by `snapshot_labels`.
    """
    frame = snapshot_frame(base)[["snapshot", name]].set_axis(["snapshot", "rep"], axis=1)
    for column, attribute in {"weight": weight, "progress": progress}.items():
        weightings = series_frame(base, attribute).set_index("snapshot")["value"]
        frame[column] = frame["snapshot"].map(weightings)
    clusters = frame.groupby("rep")["progress"]
    return frame.assign(progress=clusters.cumsum() / clusters.transform("sum"))


def _restated(expanded: DuckDBPyRelation, rel: DuckDBPyRelation) -> DuckDBPyRelation:
    """Return `expanded` in the columns of `rel`, with `snapshot` and `value` cast to its types."""
    types = dict(zip(rel.columns, rel.types, strict=True))
    casts = {c: f'CAST("{c}" AS {types[c]}) AS "{c}"' for c in ("snapshot", "value")}
    return expanded.project(", ".join(casts.get(c, f'"{c}"') for c in rel.columns))


def _paired(rel: DuckDBPyRelation, members: DuckDBPyRelation) -> DuckDBPyRelation:
    """Join each row `r` of `rel` at a representative to each member `m` of its cluster."""
    return rel.set_alias("r").join(members.set_alias("m"), "m.rep = r.snapshot")


def held(rel: DuckDBPyRelation, members: DuckDBPyRelation) -> DuckDBPyRelation:
    """Repeat each row of `rel` at a representative at every snapshot of its cluster."""
    return _restated(_paired(rel, members).project("r.* REPLACE (m.snapshot AS snapshot)"), rel)


def interpolated(
    rel: DuckDBPyRelation, members: DuckDBPyRelation, starts: DuckDBPyRelation
) -> DuckDBPyRelation:
    """Spread each state of `rel` at a representative over its cluster.

    A state is a value at the end of a snapshot, such as a state of charge. `starts` has
    the `previous` state of each `entity` at each representative `snapshot`. Over the
    cluster, the state runs from that previous state to the value in `rel`, in step with
    each member's `progress`. So the last member of the cluster has the value in `rel`.
    """
    on = "s.entity = r.entity AND s.snapshot = r.snapshot"
    paired = _paired(rel, members).join(starts.set_alias("s"), on)
    value = "s.previous + (r.value - s.previous) * m.progress"
    return _restated(paired.project(f"r.* REPLACE (m.snapshot AS snapshot, {value} AS value)"), rel)


SHAPED = """
CASE
    WHEN demand IS NOT NULL THEN demand
    WHEN coalesce(mean, 0) = 0 THEN value
    ELSE least(value * profile / mean, capacity * profile)
END
"""


def _by_cluster(series: DuckDBPyRelation, members: DuckDBPyRelation) -> DuckDBPyRelation:
    """Return `series` per entity, scenario and representative `rep`, as a map over the members.

    Each row also has `weighted`, the sum of each member's `weight` times its value.
    """
    keys = "s.entity, s.scenario, m.rep"
    values = "map_from_entries(list((m.snapshot, s.value))) AS members"
    weighted = "sum(m.weight * s.value) AS weighted"
    paired = series.set_alias("s").join(members.set_alias("m"), "m.snapshot = s.snapshot")
    return paired.aggregate(f"{keys}, {values}, {weighted}", keys)


def shaped(
    rel: DuckDBPyRelation,
    members: DuckDBPyRelation,
    demand: DuckDBPyRelation,
    profile: DuckDBPyRelation,
    capacity: DuckDBPyRelation,
) -> DuckDBPyRelation:
    """Spread each flow of `rel` at a representative over its cluster, by the inputs given.

    A series of an entity with a `demand` takes that demand at each member. A series of an
    entity with a `profile` follows it. Its value is scaled by the profile over the
    profile's mean across the cluster, weighted by each member's `weight`. It is capped at
    `capacity * profile`, and held where that mean is 0. Any other series is held.
    """
    totals = members.aggregate("rep, sum(weight) AS total", "rep").set_alias("t")
    keyed = rel.project("*, connection.entity AS entity").set_alias("r")
    spread = keyed.join(capacity.set_alias("c"), "c.entity = r.entity", "left")
    spread = spread.join(totals, "t.rep = r.snapshot", "left")
    for alias, series in {"d": demand, "p": profile}.items():
        on = f"{alias}.entity = r.entity AND {alias}.rep = r.snapshot"
        scenario = f"{alias}.scenario IS NOT DISTINCT FROM r.scenario"
        clustered = _by_cluster(series, members).set_alias(alias)
        spread = spread.join(clustered, f"{on} AND {scenario}", "left")
    inputs = "d.members AS demand, p.members AS profile, p.weighted / t.total AS mean"
    gathered = spread.project(f"r.*, c.value AS capacity, {inputs}")
    found = ", ".join(f"map_extract_value(r.{c}, m.snapshot) AS {c}" for c in ("demand", "profile"))
    expanded = _paired(gathered, members).project(
        f"r.* EXCLUDE (demand, profile), m.snapshot AS member, {found}"
    )
    return _restated(expanded.project(f"* REPLACE (member AS snapshot, {SHAPED} AS value)"), rel)
