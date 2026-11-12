# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Time aggregations of a datarecord, and the rules that expand series over them.

A time aggregation maps each step of a time axis to a representative step, so a model
solves fewer steps. The steps that share a representative form a cluster. A cluster is a
contiguous stretch within one period, if the axis has periods, and its first step is its
representative. A record keeps each time aggregation as a property of the time dim. The
functions here work on a frame with one row per step, keyed by the time dim. They expand
series over the representatives back to every step of their clusters.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from datarecord import Flags, PropertySpec, RecordLike, Relations, Schema, settle
from duckdb import DuckDBPyConnection, DuckDBPyRelation


@dataclass(frozen=True)
class TimeAxis:
    """The names of the time axis of a record.

    `dim` is the time dim, and keys each step. A time aggregation refers to the dim `step`.
    `period` is the column of each step's period, or None if the axis has no periods.
    """

    dim: str
    step: str
    period: str | None


@dataclass(frozen=True)
class TimeLabels:
    """How a framework reads the time axis of a record as a frame, and stores it back.

    `axis` gives the time axis of a schema. `frame` gives every step of a record with its
    properties, in axis order. `stored` reverses `frame` for a schema.
    """

    axis: Callable[[Schema], TimeAxis]
    frame: Callable[[RecordLike], pd.DataFrame]
    stored: Callable[[Schema, DuckDBPyConnection, pd.DataFrame], DuckDBPyRelation]


def time_relation(record: RecordLike, axis: TimeAxis) -> DuckDBPyRelation:
    """Return the time dim of `record`, with its properties where it has any."""
    relations = record.properties if axis.dim in record.properties else record.dims
    return relations[axis.dim]


def time_aggregations(schema: Schema, axis: TimeAxis) -> list[str]:
    """Return the time aggregations of `schema`, the time dim properties that refer to steps."""
    properties = schema.properties.get(axis.dim, {})
    return [name for name, spec in properties.items() if spec.one_of == axis.step]


def settled(record: RecordLike, attribute: str, axis: TimeAxis) -> DuckDBPyRelation:
    """Return the rows of `attribute` of `record`, one per step each reaches by the broadcast rule.

    A row without a step reaches every step that no row of its own coordinates names.
    """
    over = frozenset({axis.dim})
    return settle(
        record.attributes[attribute], {axis.dim: record.dims[axis.dim]}, Flags(over, over)
    )


def widened(schema: Schema, axis: TimeAxis, properties: dict[str, PropertySpec]) -> Schema:
    """Return a copy of `schema` that also declares `properties` of the time dim."""
    declared = {**schema.properties.get(axis.dim, {}), **properties}
    widened = {**schema.properties, axis.dim: declared}
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


def carry_time_properties(
    source: RecordLike, base: RecordLike, con: DuckDBPyConnection, labels: TimeLabels
) -> RecordLike:
    """Add to `source` the time dim properties that only `base` declares, at their values there.

    A property that `source` declares keeps its value in `source`. Without any to add,
    `source` is returned as it is.
    """
    axis = labels.axis(source.schema)
    own = source.schema.properties.get(axis.dim, {})
    declared = base.schema.properties.get(axis.dim, {})
    carried = {name: spec for name, spec in declared.items() if name not in own}
    if not carried:
        return source
    kept = labels.frame(base)[[axis.dim, *carried]]
    own_axis = labels.frame(source)[time_relation(source, axis).columns]
    frame = own_axis.merge(kept, on=axis.dim, how="left")
    schema = widened(source.schema, axis, carried)
    properties = {**source.properties, axis.dim: labels.stored(schema, con, frame)}
    return Overlay(source, schema, properties=properties)


def cluster_starts(frame: pd.DataFrame, name: str) -> np.ndarray:
    """Mark each row of `frame` that starts a run of equal values in column `name`.

    The first row always starts one. Over a time aggregation the runs are its clusters, and
    over the periods they are the periods.
    """
    representatives = frame[name].to_numpy()
    return np.r_[True, representatives[1:] != representatives[:-1]]


def checked_clusters(frame: pd.DataFrame, name: str, axis: TimeAxis) -> pd.Series:
    """Return the time aggregation `name` of `frame`, after checking its clusters.

    Raises `ValueError` if `frame` has no such column, or a step without a representative.
    It also raises if a cluster crosses a period, is split into separate runs, or does not
    start at its representative.
    """
    if name not in frame or frame[name].isna().any():
        raise ValueError(
            f"The record has no time aggregation {axis.dim}.{name}: add one with a "
            f"time_partition step named {name!r} before this one"
        )
    representatives = frame[name].to_numpy()
    starts = cluster_starts(frame, name)
    led = (representatives[starts] == frame[axis.dim].to_numpy()[starts]).all()
    within = axis.period is None or starts[cluster_starts(frame, axis.period)].all()
    if not (led and within and pd.Series(representatives[starts]).is_unique):
        raise ValueError(
            f"{axis.dim}.{name} is not contiguous clusters within a period, each led by its "
            "representative"
        )
    return frame[name]


def cluster_members(
    frame: pd.DataFrame, name: str, weight: np.ndarray, progress: np.ndarray, axis: TimeAxis
) -> pd.DataFrame:
    """Return each step of `frame` with its representative `rep` under time aggregation `name`.

    Each row also has the step's `weight` and `progress`, two weightings in the order of
    `frame`. A step's `progress` is the share of its cluster's total `progress` weighting
    reached by the end of that step.
    """
    members = frame[[axis.dim, name]].set_axis([axis.dim, "rep"], axis=1)
    members = members.assign(weight=weight, progress=progress)
    clusters = members.groupby("rep")["progress"]
    return members.assign(progress=clusters.cumsum() / clusters.transform("sum"))


def _restated(
    expanded: DuckDBPyRelation, rel: DuckDBPyRelation, axis: TimeAxis
) -> DuckDBPyRelation:
    """Return `expanded` in the columns of `rel`, with the time dim and `value` cast as there."""
    types = dict(zip(rel.columns, rel.types, strict=True))
    casts = {c: f'CAST("{c}" AS {types[c]}) AS "{c}"' for c in (axis.dim, "value")}
    return expanded.project(", ".join(casts.get(c, f'"{c}"') for c in rel.columns))


def _paired(rel: DuckDBPyRelation, members: DuckDBPyRelation, axis: TimeAxis) -> DuckDBPyRelation:
    """Join each row `r` of `rel` at a representative to each member `m` of its cluster."""
    return rel.set_alias("r").join(members.set_alias("m"), f"m.rep = r.{axis.dim}")


def held(rel: DuckDBPyRelation, members: DuckDBPyRelation, axis: TimeAxis) -> DuckDBPyRelation:
    """Repeat each row of `rel` at a representative at every step of its cluster."""
    dim = axis.dim
    return _restated(
        _paired(rel, members, axis).project(f"r.* REPLACE (m.{dim} AS {dim})"), rel, axis
    )


def interpolated(
    rel: DuckDBPyRelation, members: DuckDBPyRelation, starts: DuckDBPyRelation, axis: TimeAxis
) -> DuckDBPyRelation:
    """Spread each state of `rel` at a representative over its cluster.

    A state is a value at the end of a step, such as a state of charge. `starts` has the
    `previous` state of each `entity` at each representative step. Over the cluster, the
    state runs from that previous state to the value in `rel`, in step with each member's
    `progress`. So the last member of the cluster has the value in `rel`.
    """
    dim = axis.dim
    paired = _paired(rel, members, axis).join(
        starts.set_alias("s"), f"s.entity = r.entity AND s.{dim} = r.{dim}"
    )
    value = "s.previous + (r.value - s.previous) * m.progress"
    expanded = paired.project(f"r.* REPLACE (m.{dim} AS {dim}, {value} AS value)")
    return _restated(expanded, rel, axis)


SHAPED = """
CASE
    WHEN demand IS NOT NULL THEN demand
    WHEN coalesce(mean, 0) = 0 THEN value
    ELSE least(value * profile / mean, capacity * profile)
END
"""


def _by_cluster(
    series: DuckDBPyRelation, members: DuckDBPyRelation, axis: TimeAxis
) -> DuckDBPyRelation:
    """Return `series` per entity, scenario and representative `rep`, as a map over the members.

    Each row also has `weighted`, the sum of each member's `weight` times its value.
    """
    dim = axis.dim
    keys = "s.entity, s.scenario, m.rep"
    values = f"map_from_entries(list((m.{dim}, s.value))) AS members"
    weighted = "sum(m.weight * s.value) AS weighted"
    paired = series.set_alias("s").join(members.set_alias("m"), f"m.{dim} = s.{dim}")
    return paired.aggregate(f"{keys}, {values}, {weighted}", keys)


def shaped(
    rel: DuckDBPyRelation,
    members: DuckDBPyRelation,
    demand: DuckDBPyRelation,
    profile: DuckDBPyRelation,
    capacity: DuckDBPyRelation,
    axis: TimeAxis,
) -> DuckDBPyRelation:
    """Spread each flow of `rel` at a representative over its cluster, by the inputs given.

    A series of an entity with a `demand` takes that demand at each member. A series of an
    entity with a `profile` follows it. Its value is scaled by the profile over the
    profile's mean across the cluster, weighted by each member's `weight`. It is capped at
    `capacity * profile`, and held where that mean is 0. Any other series is held.
    """
    dim = axis.dim
    totals = members.aggregate("rep, sum(weight) AS total", "rep").set_alias("t")
    keyed = rel.project("*, connection.entity AS entity").set_alias("r")
    spread = keyed.join(capacity.set_alias("c"), "c.entity = r.entity", "left")
    spread = spread.join(totals, f"t.rep = r.{dim}", "left")
    for alias, series in {"d": demand, "p": profile}.items():
        on = f"{alias}.entity = r.entity AND {alias}.rep = r.{dim}"
        scenario = f"{alias}.scenario IS NOT DISTINCT FROM r.scenario"
        clustered = _by_cluster(series, members, axis).set_alias(alias)
        spread = spread.join(clustered, f"{on} AND {scenario}", "left")
    inputs = "d.members AS demand, p.members AS profile, p.weighted / t.total AS mean"
    gathered = spread.project(f"r.*, c.value AS capacity, {inputs}")
    found = ", ".join(f"map_extract_value(r.{c}, m.{dim}) AS {c}" for c in ("demand", "profile"))
    expanded = _paired(gathered, members, axis).project(
        f"r.* EXCLUDE (demand, profile), m.{dim} AS member, {found}"
    )
    return _restated(expanded.project(f"* REPLACE (member AS {dim}, {SHAPED} AS value)"), rel, axis)
