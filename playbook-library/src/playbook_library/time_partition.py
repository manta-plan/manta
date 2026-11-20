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
from datarecord import PropertySpec, RecordLike, Schema
from duckdb import ColumnExpression as col
from duckdb import ConstantExpression as lit
from duckdb import DuckDBPyConnection, DuckDBPyRelation
from duckdb import FunctionExpression as fn
from playbook.blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from pydantic import field_validator, model_validator
from scipy.sparse import diags
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import MinMaxScaler

from playbook_library.datarecord_helpers import revision
from playbook_library.pypsa_time_aggregation import (
    pypsa_time,
    snapshot_axis,
    snapshot_frame,
    snapshot_rows,
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


def add_snapshot_property(record: DataRecord, name: str, values: pd.Series) -> DataRecord:
    """Add `snapshot.<name>` as a child revision of `record`, mapping each snapshot to another.

    `values` has one snapshot per snapshot of `record`, indexed by them, all labelled as
    by `snapshot_labels`. The child declares the property in its schema, and restates the
    `snapshot` axis in the order of `record`. A name that the store declares, but this
    revision leaves unset, can be set again. Raises `ValueError` if `name` is reserved or
    already set, if `values` has the wrong length, or maps a snapshot to one outside its
    investment period.
    """
    ws, rev = revision(record)
    base = rev.record
    frame = snapshot_frame(base)
    if name in RESERVED or (name in frame and frame[name].notna().any()):
        raise ValueError(f"snapshot.{name} is reserved or already declared")
    if len(values) != len(frame):
        raise ValueError(f"snapshot.{name} needs {len(frame)} values, got {len(values)}")
    representatives = values.loc[frame["snapshot"]].to_numpy()
    positions = pd.Index(frame["snapshot"]).get_indexer(representatives)
    periods = frame["period"].to_numpy()
    if ((positions < 0) | (periods[positions] != periods)).any():
        raise ValueError(f"snapshot.{name} maps a snapshot to one outside its investment period")
    axis = pypsa_time(base.schema)
    stored = frame[time_relation(base, axis).columns].assign(**{name: representatives})
    schema = widened(base.schema, axis, {name: PropertySpec(one_of=axis.step)})
    snapshots = snapshot_axis(schema, ws.con, stored)
    child = rev.store.commit(_SnapshotAxis(schema, snapshots), parent=rev)
    return DataRecord(url=record.url, uuid=child.id)


def resample_map(record: DataRecord, n_hours: int) -> pd.Series:
    """Map each snapshot to the first snapshot of its block of `n_hours` hours.

    Blocks count from midnight of the first day of each investment period, and none
    crosses from one period into the next.
    """
    frame = snapshot_frame(revision(record)[1].record)
    origin = frame["timestep"].groupby(frame["period"]).transform("min").dt.normalize()
    blocks = [frame["period"], (frame["timestep"] - origin) // pd.Timedelta(hours=n_hours)]
    first = frame["snapshot"].groupby(blocks).transform("first")
    return pd.Series(first.to_numpy(), index=frame["snapshot"])


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
    return rel.select(
        series,
        col("snapshot"),
        col("value").cast("DOUBLE").alias("value"),
    )


def _period_matrices(
    base: RecordLike, frame: pd.DataFrame, con: DuckDBPyConnection, attributes: Sequence[str]
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield, per investment period, the positions of its rows in `frame` and its series matrix.

    The matrix has one column per distinct series of `attributes`, ordered by series
    label. Only a series with rows at snapshots can vary. Its row without a snapshot
    gives its value at every other snapshot, as by the broadcast rule. Only series that
    vary over the snapshots count. Of series identical within the period, only the one
    with the first label is kept. Raises `ValueError` if a series has no value at a
    snapshot, or if no series varies.
    """
    positions = frame[["snapshot"]].assign(row=range(len(frame)))
    rows = snapshot_rows(base.schema, con, positions, ["snapshot"]).set_alias("s")
    rels = [_labelled(base.attributes[name], name) for name in attributes]
    labelled = reduce(DuckDBPyRelation.union, rels)
    timed = labelled.filter(col("snapshot").isnotnull()).set_alias("a")
    rank = (fn("row_number").over(order_by=[col("series")]) - lit(1)).alias("col")
    ids = timed.select(col("series")).distinct().select(col("series"), rank).set_alias("i")
    cells = (
        timed.join(rows, col("a", "snapshot") == col("s", "snapshot"))
        .join(ids, col("a", "series") == col("i", "series"))
        .select(col("s", "row"), col("i", "col"), col("a", "value"))
        .fetchnumpy()
    )
    fallback = (
        labelled.filter(col("snapshot").isnull())
        .set_alias("a")
        .join(ids, col("a", "series") == col("i", "series"))
        .select(col("i", "col"), col("a", "value"))
        .fetchnumpy()
    )
    wide = np.full((len(frame), len(ids)), np.nan)
    wide[:, fallback["col"]] = fallback["value"]
    wide[cells["row"], cells["col"]] = cells["value"]
    if np.isnan(wide).any():
        raise ValueError("An input series has no value at some snapshots")
    wide = wide[:, wide.min(axis=0) < wide.max(axis=0)]
    if not wide.shape[1]:
        raise ValueError("The record has no input series that vary over its snapshots")
    for at in frame.groupby("period").indices.values():
        block = wide[at]
        _, first = np.unique(block, axis=1, return_index=True)
        yield at, block[:, np.sort(first)]


def _segment_starts(matrix: np.ndarray, n_segments: int) -> np.ndarray:
    """Split `matrix` into `n_segments` segments, and return where each row's starts.

    A segment is a contiguous stretch of rows with similar values. Rows are merged by
    Ward clustering over min-max scaled columns, each row linked only to its neighbours,
    as tsam segments a single period.
    """
    n = len(matrix)
    chain = diags([np.ones(n - 1), np.ones(n - 1)], [-1, 1])
    clustering = AgglomerativeClustering(n_segments, linkage="ward", connectivity=chain)
    labels = clustering.fit_predict(MinMaxScaler().fit_transform(matrix))
    starts = np.r_[True, labels[1:] != labels[:-1]]
    return np.maximum.accumulate(np.where(starts, np.arange(n), 0))


def segment_map(record: DataRecord, n_segments: int) -> pd.Series:
    """Map each snapshot to the first snapshot of its segment, `n_segments` in each period.

    The segments are placed by the PyPSA input series of `record` that vary over its
    snapshots. Within a period, a series that duplicates another is dropped first, so
    each profile counts once. The profiles of cohorts of one technology are such
    duplicates. Raises `ValueError` if `record` has no such series, or if a series has
    no value at a snapshot.
    """
    ws, rev = revision(record)
    frame = snapshot_frame(rev.record)
    labels = frame["snapshot"].to_numpy()
    representatives = labels.copy()
    inputs = _period_matrices(rev.record, frame, ws.con, input_series(rev.record))
    for positions, matrix in inputs:
        starts = _segment_starts(matrix, n_segments)
        representatives[positions] = labels[positions][starts]
    return pd.Series(representatives, index=frame["snapshot"])


class TimePartitionConfig(ConfigSchema):
    name: str
    """What to call the time aggregation, so later blocks can choose to solve by it.

    A record can have several time aggregations, each under its own name. The name cannot
    be `period` or `timestep`, which describe the snapshots themselves.
    """

    segments: int | None = None
    """Group the time series into this many stretches of similar conditions.

    Stretches can be of different lengths, so a few hours of unusual weather are kept
    apart from a long stretch of ordinary weather.
    """

    n_hours: int | None = None
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
    Only the blocks whose `time_aggregation` names it solve by it, and their results
    cover every snapshot.
    """

    ENV = "pypsa"
    CONFIG = TimePartitionConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def run(self, record: DataRecord) -> DataRecord:
        if self.config.segments is not None:
            mapping = segment_map(record, self.config.segments)
        else:
            mapping = resample_map(record, self.config.n_hours)
        return add_snapshot_property(record, self.config.name, mapping)
