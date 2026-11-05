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
import pyarrow.compute as pc
import pypsa
import tsam
from datarecord import PropertySpec, RecordLike, Schema
from duckdb import DuckDBPyConnection, DuckDBPyRelation
from playbook.blocks.core import BlockDims, ConfigSchema, DataRecord, MantaBlock
from pydantic import field_validator, model_validator

from playbook_library.time_aggregation import revision, snapshot_frame, snapshot_relation, widened


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

    `values` has one snapshot label per snapshot label of `record`, indexed by them. The
    child declares the property in its schema, and restates the `snapshot` axis in the
    order of `record`. A name that the store declares, but this revision leaves unset, can
    be set again. Raises `ValueError` if `name` is reserved or already set, or if `values`
    has the wrong length.
    """
    ws, rev = revision(record)
    base = rev.record
    frame = snapshot_relation(base).df()
    if name in RESERVED or (name in frame and frame[name].notna().any()):
        raise ValueError(f"snapshot.{name} is reserved or already declared")
    if len(values) != len(frame):
        raise ValueError(f"snapshot.{name} needs {len(frame)} values, got {len(values)}")
    frame[name] = values.loc[frame["snapshot"]].to_numpy()
    schema = widened(base.schema, {name: PropertySpec(one_of="snapshot")})
    child = rev.child(_SnapshotAxis(schema, ws.con.from_df(frame)))
    return DataRecord(url=record.url, uuid=child.id)


def resample_map(record: DataRecord, n_hours: int) -> pd.Series:
    """Map each snapshot to the first snapshot of its block of `n_hours` hours.

    Blocks count from midnight of the first day of each investment period, and none
    crosses from one period into the next.
    """
    frame = snapshot_frame(revision(record)[1].record)
    timestep = frame.get("timestep", frame["snapshot"])
    origin = timestep.groupby(frame["period"]).transform("min").dt.normalize()
    blocks = [frame["period"], (timestep - origin) // pd.Timedelta(hours=n_hours)]
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


def _profiles(rel: DuckDBPyRelation, name: str, rows: DuckDBPyRelation) -> DuckDBPyRelation:
    """Return each series of attribute `name` that varies over the snapshots, as values per period.

    A series is labelled by `name` and its other keys. A series constant over every
    period is dropped.
    """
    keys = [f'a."{c}"' for c in rel.columns if c not in {"snapshot", "value"}]
    label = ", ".join([f"'{name}'", *(f"CAST({k} AS VARCHAR)" for k in keys)])
    joined = rel.set_alias("a").join(rows.set_alias("s"), "a.snapshot = s.snapshot")
    profiles = joined.aggregate(
        f"concat_ws('|', {label}) AS series, s.period AS period, "
        "list(CAST(a.value AS DOUBLE) ORDER BY s.row) AS profile, "
        "min(a.value) AS low, max(a.value) AS high",
        ", ".join([*keys, "s.period"]),
    )
    window = "OVER (PARTITION BY series)"
    varies = f"min(low) {window} < max(high) {window} AS varies"
    return profiles.project(f"series, period, profile, {varies}").filter("varies")


def _period_matrices(
    base: RecordLike, frame: pd.DataFrame, con: DuckDBPyConnection, attributes: Sequence[str]
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield, per investment period, the positions of its rows in `frame` and its series matrix.

    The matrix has one column per distinct series of `attributes`, ordered by series
    label. Only series that vary over the snapshots count. Of series identical within the
    period, only the one with the first label is kept. Raises `ValueError` for a period
    without such a series.
    """
    rows = con.from_df(frame[["snapshot", "period"]].assign(row=range(len(frame))))
    profiles = [_profiles(base.attributes[name], name, rows) for name in attributes]
    distinct = reduce(DuckDBPyRelation.union, profiles).aggregate(
        "period, min(series) AS series, profile", "period, profile"
    )
    table = distinct.order("period, series").to_arrow_table()
    for period, positions in frame.groupby("period").indices.items():
        chosen = table.filter(pc.equal(table["period"], period))["profile"]
        if not len(chosen):
            raise ValueError(
                f"The record has no input series that vary over its snapshots in period {period}"
            )
        values = chosen.combine_chunks().flatten().to_numpy()
        yield positions, values.reshape(len(chosen), len(positions)).T


def _segment_starts(matrix: pd.DataFrame, n_segments: int) -> np.ndarray:
    """Split `matrix` into `n_segments` segments with tsam, and return where each row's starts.

    A segment is a contiguous stretch of rows with similar values. tsam is a time series
    aggregation package.
    """
    result = tsam.aggregate(
        matrix.reset_index(drop=True),
        n_clusters=1,
        period_duration=len(matrix),
        temporal_resolution=1.0,
        segments=tsam.SegmentConfig(n_segments=n_segments),
    )
    durations = result.cluster_representatives.index.get_level_values("Segment Duration")
    return np.repeat(np.cumsum(durations) - durations, durations)


def segment_map(record: DataRecord, n_segments: int) -> pd.Series:
    """Map each snapshot to the first snapshot of its segment, `n_segments` in each period.

    tsam places the segments by the PyPSA input series of `record` that vary over its
    snapshots. Within a period, a series that duplicates another is dropped first, so
    each profile counts once. The profiles of cohorts of one technology are such
    duplicates. Raises `ValueError` if `record` has no such series, overall or in a period.
    """
    ws, rev = revision(record)
    frame = snapshot_frame(rev.record)
    labels = frame["snapshot"].to_numpy()
    representatives = labels.copy()
    inputs = _period_matrices(rev.record, frame, ws.con, input_series(rev.record))
    for positions, matrix in inputs:
        starts = _segment_starts(pd.DataFrame(matrix), n_segments)
        representatives[positions] = labels[positions][starts]
    return pd.Series(representatives, index=frame["snapshot"])


class ClusterTimeConfig(ConfigSchema):
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


class ClusterTime(MantaBlock[ClusterTimeConfig]):
    """Group a model's snapshots into clusters, so later blocks can solve a smaller model.

    A cluster is a contiguous stretch of snapshots within one investment period. The
    record keeps this time aggregation under its `name`, alongside the full time series.
    Only the blocks whose `time_aggregation` names it solve by it, and their results
    cover every snapshot.
    """

    ENV = "pypsa"
    CONFIG = ClusterTimeConfig
    DIMS = BlockDims(requires=frozenset({"snapshot"}))

    def run(self, record: DataRecord) -> DataRecord:
        if self.config.segments is not None:
            mapping = segment_map(record, self.config.segments)
        else:
            mapping = resample_map(record, self.config.n_hours)
        return add_snapshot_property(record, self.config.name, mapping)
