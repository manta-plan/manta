# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Time aggregations of a record, computed without building its network.

A time aggregation maps each snapshot to the first snapshot of its cluster. A cluster is a
contiguous stretch of snapshots within one investment period, one of the years a model
builds capacity in. The record keeps each time aggregation as a `snapshot.<name>` property.
The time series stay at full resolution, and an optimisation block names the time
aggregation to solve by.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cache, reduce

import numpy as np
import pandas as pd
import pypsa
from datarecord import PropertySpec, RecordLike, Revision, Schema
from duckdb import ColumnExpression as col
from duckdb import ConstantExpression as lit
from duckdb import DuckDBPyRelation
from duckdb import FunctionExpression as fn
from playbook.blocks.core import BlockDims, ConfigSchema, MantaBlock
from pydantic import Field, field_validator, model_validator
from scipy.sparse import diags
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import MinMaxScaler

from playbook_library.pypsa_time_aggregation import (
    PYPSA_TIME,
    has_periods,
    pypsa_time,
)
from playbook_library.time_aggregation import time_relation, widened


@dataclass(frozen=True)
class _SnapshotAxis:
    """A revision layer that restates the `snapshot` axis and nothing else."""

    schema: Schema
    snapshots: DuckDBPyRelation

    def axes(self) -> set[str]:
        return {"snapshot"}

    def axis(self, dim: str) -> DuckDBPyRelation | None:
        return self.snapshots if dim == "snapshot" else None

    def attributes(self) -> set[str]:
        return set()

    def attribute(self, name: str) -> DuckDBPyRelation | None:
        return None


RESERVED = frozenset({"period", "timestep"})
"""The snapshot properties that PyPSA reads, so no time aggregation may take their names."""


def _snapshot_positions(base: RecordLike) -> DuckDBPyRelation:
    """Return the snapshots of `base` with their properties and their positions.

    It adds each snapshot's `_period` (0 without investment periods), its `_step`, the
    label a time aggregation refers to, and its `_position` in axis order.
    """
    rel = time_relation(base, PYPSA_TIME)
    snapshot = col("snapshot")
    period, step = (
        (snapshot["period"], snapshot["timestep"])
        if has_periods(base.schema)
        else (lit(0), snapshot)
    )
    position = fn("row_number").over() - lit(1)
    return rel.select(
        *map(col, rel.columns),
        period.alias("_period"),
        step.alias("_step"),
        position.alias("_position"),
    )


def add_time_aggregation(rev: Revision, name: str, starts: DuckDBPyRelation) -> Revision:
    """Commit the time aggregation `snapshot.<name>` as a child revision of `rev`.

    A cluster starts at each `_position` in `starts`, counting snapshots in axis order,
    and at the first snapshot of each investment period. Each snapshot maps to the first
    of its cluster. The child declares the property in its schema, and restates the
    `snapshot` axis in the order of `rev`. A name that the store declares, but this
    revision leaves unset, can be set again. Raises `ValueError` if `name` is reserved or
    already set.
    """
    base = rev.record
    axis = pypsa_time(base.schema)
    own = time_relation(base, axis)
    if name in RESERVED or (
        name in own.columns and own.filter(col(name).isnotnull()).limit(1).fetchall()
    ):
        raise ValueError(f"snapshot.{name} is reserved or already declared")
    snapshots = _snapshot_positions(base)
    marked = starts.select(col("_position").alias("_start")).set_alias("t")
    joined = snapshots.join(marked, col("_position") == col("_start"), how="left")
    by_period = {"partition_by": [col("_period")], "order_by": [col("_position")]}
    runs = fn("count", col("_start")).over(**by_period).alias("_run")
    counted = joined.select(*map(col, snapshots.columns), runs)
    first = fn("first", col("_step")).over(
        partition_by=[col("_period"), col("_run")], order_by=[col("_position")]
    )
    kept = [col(c) for c in own.columns if c != name]
    stored = (
        counted.select(*kept, first.alias(name), col("_position"))
        .order("_position")
        .select(*kept, col(name))
    )
    schema = widened(base.schema, axis, {name: PropertySpec(one_of=axis.step)})
    return rev.store.commit(_SnapshotAxis(schema, stored), parent=rev)


def resample_starts(rev: Revision, n_hours: int) -> DuckDBPyRelation:
    """Return the `_position` of each snapshot of `rev` that starts a block of `n_hours` hours.

    Blocks count from midnight of the first day of each investment period, and none
    crosses from one period into the next.
    """
    day = fn("date_trunc", lit("day"), fn("min", col("_step")).over(partition_by=[col("_period")]))
    hours = (fn("epoch", col("_step")) - fn("epoch", day)) / lit(3600 * n_hours)
    blocks = _snapshot_positions(rev.record).select(
        col("_period"), col("_position"), fn("floor", hours).alias("_block")
    )
    first = fn("min", col("_position")).over(partition_by=[col("_period"), col("_block")])
    firsts = blocks.select(col("_position"), first.alias("_first"))
    return firsts.filter(col("_position") == col("_first"))


@cache
def _pypsa_inputs() -> frozenset[str]:
    """Return the names of the attributes that PyPSA reads as inputs, across all components."""
    status = pd.concat([c.defaults.status for c in pypsa.Network().components.values()])
    return frozenset(status.index[status.astype(str).str.startswith("Input")])


def input_series(base: RecordLike) -> list[str]:
    """Return the attributes of `base` that PyPSA reads as input series of floats over snapshots.

    Raises `ValueError` if `base` has none.
    """
    floats = [
        name
        for name in base.attributes
        if name in _pypsa_inputs()
        and "snapshot" in base.schema.coordinates_of(name)
        and base.schema.attributes[name].dtype == "float"
    ]
    if not floats:
        raise ValueError("The record has no float input series over its snapshots")
    return floats


def _labelled(rel: DuckDBPyRelation, name: str) -> DuckDBPyRelation:
    """Return the rows of attribute `name`, each tagged with the name of its time series.

    The name is `name` and the row's other keys, joined by `|`.
    """
    keys = [col(c).cast("VARCHAR") for c in rel.columns if c not in {"snapshot", "value"}]
    series = fn("concat_ws", lit("|"), lit(name), *keys).alias("series")
    return rel.select(series, col("snapshot"), col("value").cast("DOUBLE").alias("value"))


def _distinct_varying(matrix: np.ndarray, period: int) -> np.ndarray:
    """Return the columns of `matrix`, the series of `period`, that vary and are distinct.

    Of identical columns only the first is kept. Raises `ValueError` if a series has no
    value at a snapshot, or if none varies.
    """
    if np.isnan(matrix).any():
        raise ValueError(f"An input series has no value at some snapshots in period {period}")
    matrix = matrix[:, matrix.min(axis=0) < matrix.max(axis=0)]
    if not matrix.shape[1]:
        raise ValueError(
            f"The record has no input series that vary over its snapshots in period {period}"
        )
    _, first = np.unique(matrix, axis=1, return_index=True)
    return matrix[:, np.sort(first)]


def _period_matrices(
    base: RecordLike, attributes: Sequence[str]
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield, per investment period, the positions of its snapshots and its series matrix.

    Positions count the snapshots of `base` in axis order. The matrix has one column per
    series of `attributes` with rows at snapshots, ordered by series label, as
    `_distinct_varying` keeps them. A series' row without a snapshot gives its value at
    every other snapshot, as by the broadcast rule.
    """
    rels = [_labelled(base.attributes[name], name) for name in attributes]
    labelled = reduce(DuckDBPyRelation.union, rels)
    snapshots = _snapshot_positions(base)
    timed = labelled.filter(col("snapshot").isnotnull()).set_alias("a")
    placed = timed.join(snapshots.set_alias("s"), col("a", "snapshot") == col("s", "snapshot"))
    rank = fn("dense_rank").over(order_by=[col("series")]) - lit(1)
    ranked = placed.select(col("series"), col("_position"), col("value"), rank.alias("col"))
    cells = ranked.fetchnumpy()
    ids = ranked.select(col("series"), col("col")).distinct().set_alias("i")
    fallback = (
        labelled.filter(col("snapshot").isnull())
        .set_alias("a")
        .join(ids, col("a", "series") == col("i", "series"))
        .select(col("i", "col"), col("a", "value"))
        .fetchnumpy()
    )
    wide = np.full((len(snapshots), len(np.unique(cells["col"]))), np.nan)
    wide[:, fallback["col"]] = fallback["value"]
    wide[cells["_position"], cells["col"]] = cells["value"]
    spans = snapshots.aggregate("_period, min(_position) AS start, count(*) AS n", "_period")
    for period, start, n in spans.order("start").fetchall():
        yield np.arange(start, start + n), _distinct_varying(wide[start : start + n], period)


def _segment_starts(matrix: np.ndarray, n_segments: int) -> np.ndarray:
    """Split `matrix` into `n_segments` segments, and return the row each starts at.

    A segment is a contiguous stretch of rows with similar values. Rows are merged by
    Ward clustering over min-max scaled columns, each row linked only to its neighbours,
    as tsam segments a single period.
    """
    n = len(matrix)
    chain = diags([np.ones(n - 1), np.ones(n - 1)], [-1, 1])
    clustering = AgglomerativeClustering(n_segments, linkage="ward", connectivity=chain)
    labels = clustering.fit_predict(MinMaxScaler().fit_transform(matrix))
    return np.flatnonzero(np.r_[True, labels[1:] != labels[:-1]])


def segment_starts(rev: Revision, n_segments: int) -> DuckDBPyRelation:
    """Return the `_position` of each snapshot of `rev` that starts one of `n_segments` segments.

    Each period has `n_segments` segments. They are placed by the PyPSA input series of
    `rev` that vary over the period's snapshots. Within a period, a series that
    duplicates another is dropped first, so each profile counts once. The profiles of
    cohorts of one technology are such duplicates. Raises `ValueError` if a period has
    no such series, or if a series has no value at a snapshot.
    """
    base = rev.record
    inputs = _period_matrices(base, input_series(base))
    positions = np.concatenate([at[_segment_starts(m, n_segments)] for at, m in inputs])
    return rev.store.workspace.con.from_df(pd.DataFrame({"_position": positions}))


class TimePartitionConfig(ConfigSchema):
    name: str
    """What to call the time aggregation, so later blocks can choose to solve by it.

    A record can have several time aggregations, each under its own name. The name cannot
    be `period` or `timestep`, which describe the snapshots themselves.
    """

    segments: int | None = Field(default=None, gt=0)
    """Group the time series into this many stretches of similar conditions.

    Stretches can be of different lengths, so a few hours of unusual weather are kept
    apart from a long stretch of ordinary weather.
    """

    n_hours: int | None = Field(default=None, gt=0)
    """Group the time series into even blocks of this many hours."""

    @field_validator("name")
    @classmethod
    def name_is_not_reserved(cls, name: str) -> str:
        if name in RESERVED:
            raise ValueError(f"A time aggregation cannot be named {name!r}")
        return name

    @model_validator(mode="after")
    def exactly_one_way_to_cluster(self):
        if (self.segments is None) == (self.n_hours is None):
            raise ValueError("Exactly one of segments or n_hours must be set")
        return self


class TimePartition(MantaBlock[TimePartitionConfig]):
    """Group a model's snapshots into clusters, so later blocks can solve a smaller model.

    A cluster is a contiguous stretch of snapshots within one investment period. The
    record keeps this time aggregation under its `name`, alongside the full time series.
    Only the blocks whose `aggregation.snapshot` names it solve by it, and their results
    cover every snapshot.
    """

    ENV = "pypsa"
    CONFIG = TimePartitionConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def run(self, base: Revision) -> Revision:
        if self.config.segments is not None:
            starts = segment_starts(base, self.config.segments)
        else:
            starts = resample_starts(base, self.config.n_hours)
        return add_time_aggregation(base, self.config.name, starts)
