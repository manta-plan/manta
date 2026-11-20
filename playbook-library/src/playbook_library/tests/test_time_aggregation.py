# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Tests of time aggregations, computed from a record and kept on it as snapshot properties.

A time aggregation maps each snapshot to the first snapshot of its cluster, a contiguous
stretch within one investment period. A record can have any number of them, and PyPSA
ignores them all.
"""

from collections.abc import Callable

import pytest

pypsa = pytest.importorskip("pypsa", reason="the PyPSA blocks need PyPSA installed")

import duckdb
import numpy as np
import pandas as pd
from datarecord import PropertySpec, RecordLike, Revision
from datarecord.tools.pypsa import PyPSA
from duckdb import DuckDBPyRelation
from playbook.blocks.core import DataRecord

from playbook_library.datarecord_helpers import revision
from playbook_library.pypsa_configs import PyPSAOptimizeSchema
from playbook_library.pypsa_helpers import (
    optimize_network,
    to_network,
    write_network,
)
from playbook_library.pypsa_time_aggregation import (
    PYPSA_TIME,
    STATES,
    cluster_network,
    series_frame,
    snapshot_axis,
    snapshot_frame,
    write_expanded_results,
)
from playbook_library.time_aggregation import Overlay, cluster_starts, shaped, widened
from playbook_library.time_partition import (
    _segment_starts,
    _SnapshotAxis,
    add_time_aggregation,
    resample_starts,
    segment_starts,
)

pytestmark = pytest.mark.pypsa

BEL_HOURLY = pytest.param("bel_hourly_record", marks=pytest.mark.slow)
RECORDS = ["single_period_record", "multi_period_record", BEL_HOURLY]


def _dynamic_data(n: pypsa.Network) -> dict[tuple[str, str], pd.DataFrame]:
    return {
        (c.name, attr): df for c in n.components for attr, df in c.dynamic.items() if not df.empty
    }


def _positions(starts: DuckDBPyRelation) -> np.ndarray:
    return starts.order("_position").fetchnumpy()["_position"]


def _aggregated(
    record: DataRecord, name: str, starts: Callable[[Revision, int], DuckDBPyRelation], n: int
) -> DataRecord:
    """Add the time aggregation `name` to `record`, its clusters starting where `starts` says."""
    _, rev = revision(record)
    child = add_time_aggregation(rev, name, starts(rev, n))
    return DataRecord(url=record.url, uuid=child.id)


def _clusters_per_period(record: DataRecord, name: str) -> pd.DataFrame:
    """Assert `name` aggregates `record` in time, and count clusters and snapshots per period."""
    frame = snapshot_frame(revision(record)[1].record)
    labels = frame["snapshot"].to_numpy()
    representatives = frame[name].to_numpy()
    starts = cluster_starts(frame, name)

    assert (representatives[starts] == labels[starts]).all()
    assert pd.Series(representatives[starts]).is_unique
    assert starts[cluster_starts(frame, "period")].all()
    counts = frame.assign(start=starts).groupby("period")["start"]
    return counts.agg(clusters="sum", snapshots="size")


def _sparse(record: DataRecord, attribute: str, fallback: bool = True) -> DataRecord:
    """Store `attribute` of `record` again, as each series' most common value and the rows apart.

    The most common value is a row without a snapshot, which every other snapshot takes.
    Without `fallback`, it is left out, so those snapshots have no value.
    """
    ws, rev = revision(record)
    rel = rev.record.attributes[attribute]
    keys = ", ".join(f'"{c}"' for c in rel.columns if c not in {"snapshot", "value"})
    ranked = rel.project(f"*, mode(value) OVER (PARTITION BY {keys}) AS common")
    unset = "CASE WHEN false THEN snapshot END AS snapshot, common AS value"
    scalars = ranked.project(f"* EXCLUDE (common) REPLACE ({unset})").distinct()
    apart = ranked.filter("value <> common").project("* EXCLUDE (common)")
    stored = scalars.union(apart) if fallback else apart
    attributes = {**rev.record.attributes, attribute: stored}
    child = rev.store.commit(Overlay(rev.record, attributes=attributes), parent=rev)
    return DataRecord(url=record.url, uuid=child.id)


@pytest.mark.parametrize("record_name", RECORDS)
@pytest.mark.parametrize("n_hours", [1, 3, 5, 24])
def test_resampling_makes_even_blocks_within_each_period(record_name, n_hours, request):
    record = request.getfixturevalue(record_name)
    widened = _aggregated(record, "agg", resample_starts, n_hours)

    counts = _clusters_per_period(widened, "agg")
    assert (counts.clusters == np.ceil(counts.snapshots / n_hours)).all()
    frame = snapshot_frame(revision(widened)[1].record)
    assert (frame["agg"] == frame["snapshot"]).all() == (n_hours == 1)


def test_resampling_groups_snapshots_as_pypsa_does(single_period_record):
    starts = _positions(resample_starts(revision(single_period_record)[1], 3))
    pypsa_map = to_network(single_period_record).cluster.temporal.get_resample_result("3h")

    expected = pd.factorize(pypsa_map.snapshot_map.to_numpy())[0]
    assert (np.flatnonzero(np.r_[True, np.diff(expected) != 0]) == starts).all()


def test_segmenting_makes_as_many_segments_in_each_period(storage_record):
    widened = _aggregated(storage_record, "seg", segment_starts, 2)
    counts = _clusters_per_period(widened, "seg")
    assert (counts.clusters == 2).all()


@pytest.mark.slow
def test_segmenting_hourly_bel_makes_the_segments_of_pypsa_eur(bel_hourly_record, bel_record):
    """Segmenting hourly BEL into 730 segments gives the network PyPSA-Eur segments with tsam.

    PyPSA-Eur sets `p_max_pu` and similar series to 0 up to 0.01 when solving, so the test
    does too. Averaging a constant cost or efficiency can be one unit in the last place off.
    """
    record = _aggregated(bel_hourly_record, "seg", segment_starts, 730)
    clustered = cluster_network(to_network(record), record, "seg")
    for df in (
        clustered.generators_t.p_max_pu,
        clustered.generators_t.p_min_pu,
        clustered.links_t.p_max_pu,
        clustered.links_t.p_min_pu,
        clustered.storage_units_t.inflow,
    ):
        df.where(df.abs() > 0.01, other=0.0, inplace=True)
    expected = to_network(bel_record)
    aggregated = _dynamic_data(clustered)
    reference = _dynamic_data(expected)

    assert clustered.snapshots.equals(expected.snapshots)
    assert clustered.snapshot_weightings.equals(expected.snapshot_weightings)
    assert aggregated.keys() == reference.keys()
    for (name, attr), series in reference.items():
        rtol = 1e-15 if attr in {"marginal_cost", "efficiency"} else 0.0
        pd.testing.assert_frame_equal(
            aggregated[name, attr], series, check_like=True, check_exact=False, rtol=rtol, atol=0
        )


@pytest.mark.parametrize("attribute", ["p_set", "p_max_pu"])
def test_segmenting_reads_sparse_series_as_the_dense_ones(attribute, storage_record):
    sparse = _sparse(storage_record, attribute)
    dense = _positions(segment_starts(revision(storage_record)[1], 4))
    assert (_positions(segment_starts(revision(sparse)[1], 4)) == dense).all()


def _tsam_starts(matrix: np.ndarray, n_segments: int) -> np.ndarray:
    """Segment `matrix` as one period with tsam, and return the row each segment starts at."""
    tsam = pytest.importorskip("tsam")
    result = tsam.aggregate(
        pd.DataFrame(matrix),
        n_clusters=1,
        period_duration=len(matrix),
        temporal_resolution=1.0,
        segments=tsam.SegmentConfig(n_segments=n_segments),
    )
    durations = result.cluster_representatives.index.get_level_values("Segment Duration")
    return np.cumsum(durations) - durations


@pytest.mark.parametrize(("seed", "n_segments"), [(0, 2), (1, 10), (2, 50)])
def test_segment_starts_are_those_of_tsam(seed, n_segments):
    matrix = np.random.default_rng(seed).random((200, 5))
    assert (_segment_starts(matrix, n_segments) == _tsam_starts(matrix, n_segments)).all()


def test_segmenting_refuses_a_series_without_a_value_at_some_snapshots(storage_record):
    gaps = _sparse(storage_record, "p_max_pu", fallback=False)
    with pytest.raises(ValueError, match="no value at some snapshots"):
        segment_starts(revision(gaps)[1], 4)


@pytest.mark.parametrize(
    ("record_name", "period"), [("single_period_record", 0), ("multi_period_record", 2030)]
)
def test_segmenting_needs_a_series_that_varies_in_each_period(record_name, period, request):
    """Neither record has an input series that varies within a period; the load of
    `multi_period_record` only steps up from one period to the next."""
    record = request.getfixturevalue(record_name)
    with pytest.raises(ValueError, match=f"vary over its snapshots in period {period}$"):
        segment_starts(revision(record)[1], 2)


@pytest.mark.parametrize("record_name", ["single_period_record", "multi_period_record"])
def test_snapshot_properties_coexist_and_pypsa_ignores_them(record_name, request):
    record = request.getfixturevalue(record_name)
    hours = {"agg_3h": 3, "agg_24h": 24}
    widened = record
    for name, n_hours in hours.items():
        widened = _aggregated(widened, name, resample_starts, n_hours)

    frame = snapshot_frame(revision(widened)[1].record)
    for name, n_hours in hours.items():
        alone = _aggregated(record, name, resample_starts, n_hours)
        assert frame[name].equals(snapshot_frame(revision(alone)[1].record)[name])
    assert to_network(widened).snapshots.equals(to_network(record).snapshots)


@pytest.mark.parametrize("record_name", ["single_period_record", "multi_period_record"])
@pytest.mark.parametrize("results_only", [True, False])
def test_a_network_written_over_a_widened_record_keeps_its_properties(
    record_name, results_only, request
):
    record = request.getfixturevalue(record_name)
    widened = _aggregated(record, "agg_3h", resample_starts, 3)

    written = write_network(to_network(widened), widened, results_only=results_only)

    assert snapshot_frame(revision(written)[1].record)["agg_3h"].equals(
        snapshot_frame(revision(widened)[1].record)["agg_3h"]
    )


@pytest.mark.parametrize("name", ["period", "timestep", "agg_3h"])
def test_a_snapshot_property_is_declared_once_and_never_shadows_pypsa(name, single_period_record):
    widened = _aggregated(single_period_record, "agg_3h", resample_starts, 3)
    with pytest.raises(ValueError, match="reserved or already declared"):
        _aggregated(widened, name, resample_starts, 3)


CYCLIC = {"cyclic_state_of_charge": True, "cyclic_state_of_charge_per_period": True}
COHORT = {"build_year": 2040, "lifetime": 10}
STORAGE = {
    "single": ("single", CYCLIC, {}),
    "multi": ("multi", CYCLIC, {}),
    "single-initial": ("single", {"state_of_charge_initial": 5.0}, {"e_initial": 5.0}),
    "multi-initial-per-period": (
        "multi",
        {"state_of_charge_initial": 5.0, "state_of_charge_initial_per_period": True},
        {"e_initial": 5.0, "e_initial_per_period": True},
    ),
    "multi-cohort": (
        "multi",
        {"cyclic_state_of_charge": True, **COHORT},
        {"e_initial": 5.0, "e_nom_min": 20.0, "e_min_pu": 0.5, **COHORT},
    ),
}
"""Per case, the network and how its battery and store start.

They cycle, start at an initial state, start afresh each period, or form a cohort active in
2040 only.
"""


def _with_solar(n: pypsa.Network, weightings: list[float]) -> pd.Series:
    """Weight the snapshots of `n` cyclically by `weightings`, add solar, and return its profile."""
    profile = pd.Series(np.resize([0.0, 0.5, 1.0, 0.25, 0.0, 0.75], len(n.snapshots)), n.snapshots)
    n.snapshot_weightings.loc[:, :] = np.resize(weightings, len(n.snapshots))[:, None]
    n.add(
        "Generator", "solar", bus="bus", p_nom_extendable=True, capital_cost=10.0, p_max_pu=profile
    )
    return profile


@pytest.fixture(scope="module", params=list(STORAGE))
def storage_record(
    request, tmp_path_factory, store_network, new_multi_period_network, new_single_period_network
) -> DataRecord:
    """Store solar, a battery, a store and a load that follows the sun, aggregated as `agg_3h`.

    Weightings are heaviest where the sun is, so expanded solar is never capped below
    what it dispatched when clustered.
    """
    network, battery, store = STORAGE[request.param]
    n = new_multi_period_network() if network == "multi" else new_single_period_network()
    profile = _with_solar(n, [1.0, 1.0, 2.0])
    n.add(
        "StorageUnit",
        "bat",
        bus="bus",
        p_nom_extendable=True,
        capital_cost=5.0,
        max_hours=4,
        **battery,
    )
    n.add(
        "Store",
        "st",
        bus="bus",
        e_nom_extendable=True,
        e_nom_max=20.0,
        capital_cost=1.0,
        **store,
    )
    n.loads_t.p_set["load"] = 50.0 + 20.0 * profile
    record = store_network(n, str(tmp_path_factory.mktemp(request.param)))
    return _aggregated(record, "agg_3h", resample_starts, 3)


def _solved(record: DataRecord, name: str) -> pypsa.Network:
    n = cluster_network(to_network(record), record, name)
    return optimize_network(n, PyPSAOptimizeSchema(), multi_investment_periods=n.has_periods)


def _frame(record: RecordLike, name: str) -> pd.DataFrame:
    frame = series_frame(record, name)
    if "connection" in frame:
        frame["entity"] = frame["connection"].str.get("entity")
        frame["bus"] = frame["connection"].str.get("bus")
    return frame


def _stored(record: DataRecord, name: str) -> pd.DataFrame:
    """Return an attribute of the revision `record` points at."""
    return _frame(revision(record)[1].record, name)


def _clustered(n_c: pypsa.Network, record: DataRecord, name: str) -> pd.DataFrame:
    """Return a result of `n_c` at its representative snapshots, labelled as in `record`."""
    ws, rev = revision(record)
    return _frame(PyPSA.to_datarecord(n_c, ws.con, results_only=True, base=rev.record), name)


def _by_cluster(record: DataRecord, frame: pd.DataFrame) -> pd.DataFrame:
    """Return `frame` in axis order, with each snapshot's period, representative and weighting.

    Each row also has the snapshot's position in its cluster and the cluster's size.
    """
    clusters = snapshot_frame(revision(record)[1].record)
    clusters["pos"] = clusters.groupby("agg_3h").cumcount()
    clusters["size"] = clusters.groupby("agg_3h")["snapshot"].transform("size")
    weights = _stored(record, "snapshot_weighting_stores").set_index("snapshot")["value"]
    clusters["weight"] = clusters["snapshot"].map(weights)
    return clusters.merge(frame, on="snapshot")


@pytest.fixture(scope="module")
def expanded(storage_record) -> tuple[DataRecord, pypsa.Network, DataRecord]:
    """Return the aggregated record, its network clustered and solved, and the expanded results."""
    n_c = _solved(storage_record, "agg_3h")
    result = write_expanded_results(n_c, n_c, storage_record, "agg_3h", n_c.has_periods)
    return storage_record, n_c, result


def test_clustering_by_hours_matches_pypsa_resampling(storage_record):
    n = to_network(storage_record)

    clustered = cluster_network(n, storage_record, "agg_3h")
    resampled = n.cluster.temporal.resample("3h")

    assert clustered.snapshots.equals(resampled.snapshots)
    assert clustered.snapshot_weightings.equals(resampled.snapshot_weightings)
    for c in resampled.components:
        for attr, series in c.dynamic.items():
            aggregated = clustered.components[c.name].dynamic[attr]
            pd.testing.assert_frame_equal(aggregated, series, check_freq=False)


def _broken(record: DataRecord, name: str, broken: str) -> DataRecord:
    """Store a time aggregation `name` of `record` that `add_time_aggregation` cannot write.

    Its clusters are `split` into separate runs, or `unled` by their representative.
    """
    ws, rev = revision(record)
    frame = snapshot_frame(rev.record)
    labels = frame["snapshot"].to_numpy()
    representatives = labels.copy()
    if broken == "split":
        representatives[[0, 2]] = [labels[0], labels[0]]
    else:
        representatives[0:3] = [labels[1]] * 3
    schema = widened(rev.record.schema, PYPSA_TIME, {name: PropertySpec(one_of="timestep")})
    stored = frame[["snapshot"]].assign(**{name: representatives})
    child = rev.store.commit(
        _SnapshotAxis(schema, snapshot_axis(schema, ws.con, stored)), parent=rev
    )
    return DataRecord(url=record.url, uuid=child.id)


@pytest.mark.parametrize("broken", ["split", "unled"])
def test_clustering_refuses_clusters_that_are_not_contiguous_runs(broken, multi_period_record):
    record = _broken(multi_period_record, "bad", broken)
    with pytest.raises(ValueError, match="not contiguous clusters within a period"):
        cluster_network(to_network(record), record, "bad")


@pytest.mark.parametrize("name", ["p", "state_of_charge", "e", "marginal_price"])
def test_expanded_results_stand_at_every_snapshot_once(name, expanded):
    record, _, result = expanded
    frame = _stored(result, name)
    counts = frame.groupby([c for c in ["entity", "bus"] if c in frame])["snapshot"].nunique()

    assert len(frame) == counts.sum()
    assert (counts == len(snapshot_frame(revision(record)[1].record))).all()


@pytest.mark.parametrize("entity", ["solar", "bat", "st"])
def test_expanded_flows_keep_the_energy_of_each_cluster(entity, expanded):
    record, n_c, result = expanded
    flows = _by_cluster(record, _stored(result, "p").query("entity == @entity"))
    clustered = _clustered(n_c, record, "p").query("entity == @entity").set_index("snapshot")

    clusters = flows.assign(energy=flows["value"] * flows["weight"]).groupby("agg_3h")
    energy = clusters["energy"].sum()
    assert flows["value"].abs().max() > 1
    assert np.allclose(energy, clustered["value"].reindex(energy.index) * clusters["weight"].sum())


def test_expanded_variable_generation_follows_its_profile_within_its_capacity(expanded):
    record, n_c, result = expanded
    solar = _stored(result, "p").query("entity == 'solar'").set_index("snapshot")["value"]
    profile = _stored(record, "p_max_pu").query("entity == 'solar'").set_index("snapshot")["value"]
    capacity = _clustered(n_c, record, "p_nom_opt").set_index("entity").loc["solar", "value"]

    available = capacity * profile.reindex(solar.index)
    assert (solar <= available + 1e-6).all()
    assert (solar[available == 0] == 0).all()


def test_expanded_variable_generation_is_capped_where_its_weighted_mean_falls_short(
    store_record, new_single_period_network
):
    """Weightings heaviest where the sun is weakest would, uncapped, push solar past capacity."""
    n = new_single_period_network()
    _with_solar(n, [2.0, 1.0, 1.0])
    record = store_record(n, "capped")
    record = _aggregated(record, "agg_3h", resample_starts, 3)
    n_c = _solved(record, "agg_3h")
    result = write_expanded_results(n_c, n_c, record, "agg_3h", n_c.has_periods)

    solar = _by_cluster(record, _stored(result, "p").query("entity == 'solar'"))
    profile = _stored(record, "p_max_pu").query("entity == 'solar'").set_index("snapshot")["value"]
    clustered = _clustered(n_c, record, "p").query("entity == 'solar'").set_index("snapshot")
    capacity = _clustered(n_c, record, "p_nom_opt").set_index("entity").loc["solar", "value"]
    available = capacity * solar["snapshot"].map(profile)
    weighted = (available * solar["weight"]).groupby(solar["agg_3h"]).transform("sum")
    reachable = weighted / solar["weight"].groupby(solar["agg_3h"]).transform("sum")
    capped = solar["agg_3h"].map(clustered["value"]) > reachable + 1e-6

    assert capped.any()
    assert np.allclose(solar["value"][capped], available[capped])


def test_expanded_loads_draw_their_original_demand(expanded):
    record, _, result = expanded
    loads = _stored(result, "p").query("entity == 'load'")
    demand = _stored(record, "p_set").query("entity == 'load'")

    merged = loads.merge(demand, on="snapshot", suffixes=("", "_set"))
    assert len(merged) == len(snapshot_frame(revision(record)[1].record))
    assert np.allclose(merged["value"], merged["value_set"])


STORED = [("state_of_charge", "bat"), ("e", "st")]


@pytest.mark.parametrize(("name", "entity"), STORED)
def test_expanded_states_end_each_cluster_at_its_clustered_value(name, entity, expanded):
    record, n_c, result = expanded
    states = _by_cluster(record, _stored(result, name).query("entity == @entity"))
    clustered = _clustered(n_c, record, name).query("entity == @entity")

    ends = states[states["pos"] == states["size"] - 1].set_index("agg_3h")["value"]
    assert ends.abs().max() > 1
    assert np.allclose(ends, clustered.set_index("snapshot")["value"].reindex(ends.index))


@pytest.mark.parametrize(("name", "entity"), STORED)
def test_expanded_states_balance_the_clustered_flows_in_each_active_cluster(name, entity, expanded):
    record, n_c, result = expanded
    states = _by_cluster(record, _stored(result, name).query("entity == @entity"))
    flows = _clustered(n_c, record, "p").query("entity == @entity").set_index("snapshot")["value"]
    mask = n_c.components[STATES[name][0]].get_activity_mask()[entity].to_numpy()
    active = states["agg_3h"].map(dict(zip(states["agg_3h"].unique(), mask, strict=True)))

    clusters = states.groupby("agg_3h")
    remaining = clusters["weight"].transform("sum") - clusters["weight"].cumsum()
    balanced = clusters["value"].transform("last") + remaining * states["agg_3h"].map(flows)
    assert np.allclose(states["value"][active], balanced[active])
    assert (states["value"][~active] == 0).all()


def test_expanded_duals_are_held_over_each_cluster(expanded):
    record, n_c, result = expanded
    prices = _by_cluster(record, _stored(result, "marginal_price"))
    clustered = _clustered(n_c, record, "marginal_price").set_index(["bus", "snapshot"])["value"]

    assert np.allclose(prices["value"], clustered.reindex(prices[["bus", "agg_3h"]]))


@pytest.mark.parametrize("name", ["p_nom_opt", "e_nom_opt"])
def test_expanded_static_results_are_the_clustered_ones(name, expanded):
    record, n_c, result = expanded
    static = _stored(result, name).set_index("entity")["value"]
    clustered = _clustered(n_c, record, name).set_index("entity")["value"]

    assert static.sort_index().equals(clustered.sort_index())


def test_expanding_refuses_a_network_clustered_otherwise(expanded):
    record, n_c, _ = expanded
    other = _aggregated(record, "agg_6h", resample_starts, 6)
    with pytest.raises(ValueError, match="not clustered by snapshot.agg_6h"):
        write_expanded_results(n_c, n_c, other, "agg_6h", n_c.has_periods)


@pytest.mark.parametrize("duplicated", ["demand", "profile"])
def test_shaping_refuses_a_series_with_duplicate_rows(duplicated):
    con = duckdb.connect()
    series = {
        name: con.sql("SELECT 'g' AS entity, 0 AS snapshot, NULL AS scenario, 1.0 AS value")
        for name in ("demand", "profile")
    }
    series[duplicated] = series[duplicated].union(series[duplicated])
    rel = con.sql(
        "SELECT {'entity': 'g'} AS connection, 0 AS snapshot, NULL AS scenario, 1.0 AS value"
    )
    members = con.sql("SELECT 0 AS rep, 0 AS snapshot, 1.0 AS weight")
    capacity = con.sql("SELECT 'g' AS entity, 1.0 AS value")
    with pytest.raises(duckdb.InvalidInputException, match="Map keys must be unique"):
        shaped(rel, members, capacity=capacity, axis=PYPSA_TIME, **series).fetchall()


def test_expansion_writes_one_layer(expanded, ancestry):
    record, _, result = expanded
    assert ancestry(result) == [*ancestry(record), result.uuid]


def test_expanding_over_expanded_results_replaces_them(expanded):
    record, n_c, result = expanded
    again = write_expanded_results(n_c, n_c, result, "agg_3h", n_c.has_periods)

    keys = ["entity", "bus", "snapshot"]
    before = _stored(result, "p").drop(columns="connection").sort_values(keys, ignore_index=True)
    after = _stored(again, "p").drop(columns="connection").sort_values(keys, ignore_index=True)
    pd.testing.assert_frame_equal(after, before)


@pytest.mark.parametrize(
    "attribute",
    ["p_set", "p_max_pu", "snapshot_weighting_stores", "snapshot_weighting_generators"],
)
def test_expanding_reads_sparse_inputs_as_the_dense_ones(attribute, expanded):
    record, n_c, result = expanded
    sparse = write_expanded_results(n_c, n_c, _sparse(record, attribute), "agg_3h", n_c.has_periods)

    for name in ("p", "e", "state_of_charge"):
        dense, read = (
            _stored(r, name)[["entity", "snapshot", "value"]].sort_values(["entity", "snapshot"])
            for r in (result, sparse)
        )
        pd.testing.assert_frame_equal(read.reset_index(drop=True), dense.reset_index(drop=True))


@pytest.mark.parametrize("n_hours", [3, 24])
def test_expanded_prices_are_per_hour_whatever_the_weighting(
    n_hours, store_record, new_single_period_network
):
    n = new_single_period_network()
    n.remove("Generator", "gen")
    n.add("Generator", "gen", bus="bus", p_nom=100.0, marginal_cost=10.0)
    record = store_record(n, "fixed")
    record = _aggregated(record, "agg", resample_starts, n_hours)

    n_c = _solved(record, "agg")
    prices = _stored(
        write_expanded_results(n_c, n_c, record, "agg", n_c.has_periods), "marginal_price"
    )

    assert (n_c.snapshot_weightings.objective == n_hours).all()
    assert np.allclose(prices["value"], 10.0)


@pytest.mark.slow
def test_expanding_bel_covers_every_hour_and_keeps_the_energy_of_each_cluster(bel_hourly_record):
    record = _aggregated(bel_hourly_record, "agg", resample_starts, 168)
    n_c = _solved(record, "agg")
    result = write_expanded_results(n_c, n_c, record, "agg", n_c.has_periods)

    ws, rev = revision(result)
    expanded = rev.record
    clustered = PyPSA.to_datarecord(n_c, ws.con, results_only=True, base=expanded)
    flows = expanded.attributes["p"].join(expanded.properties["snapshot"], "snapshot")
    per_cluster = flows.aggregate(
        "connection, snapshot.period AS period, agg, sum(value) AS energy, count(*) AS size, "
        "count(DISTINCT snapshot) AS n",
        "connection, snapshot.period, agg",
    ).set_alias("e")
    at = per_cluster.join(
        clustered.attributes["p"].set_alias("c"),
        "e.connection = c.connection AND e.period = c.snapshot.period "
        "AND e.agg = c.snapshot.timestep",
    )
    keys = "e.connection.entity AS entity, e.connection.bus AS bus"
    frame = at.project(f"{keys}, energy, size, n, c.value").df()

    assert len(frame) == len(_clustered(n_c, record, "p"))
    assert (frame["size"] == frame["n"]).all()
    assert (
        frame.groupby(["entity", "bus"])["size"].sum()
        == len(snapshot_frame(revision(record)[1].record))
    ).all()
    assert np.allclose(frame["energy"], frame["value"] * frame["size"], rtol=1e-6, atol=1e-3)
