# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The blocks that ship with Manta, run against a real but tiny network.

Each test builds a network small enough to solve in a moment, stores it as the root
revision of a datarecord store, and runs a block on it. A block reads one revision and
writes a new one into the same store, so what is checked is that a usable network
comes out as a descendant of the revision it read.
"""

import pytest

pypsa = pytest.importorskip("pypsa", reason="the PyPSA blocks need PyPSA installed")

import pandas as pd
from datarecord import Revision
from playbook.blocks.core import RevisionRef, SolveError

from playbook_library.myopic_capacity_expansion import MyopicCapacityExpansion
from playbook_library.overnight_capacity_expansion import OvernightCapacityExpansion
from playbook_library.perfect_capacity_expansion import PerfectCapacityExpansion
from playbook_library.pypsa_helpers import nominal_attr, remove_unbuilt_cohorts, to_network
from playbook_library.rolling_horizon_dispatch import RollingHorizonDispatch
from playbook_library.time_aggregation import snapshot_frame
from playbook_library.time_cluster import ClusterTime

pytestmark = pytest.mark.pypsa


def _run(block_cls, config: dict, base: Revision) -> Revision:
    """Run a block on `base`, inside the test's own workspace."""
    return block_cls(block_cls.merge_config(config, {})).run(base)


CLUSTER = {"name": "agg_3h", "n_hours": 3}


def _snapshots(rev: Revision) -> pd.DataFrame:
    return snapshot_frame(rev.record)


def _stored(rev: Revision, name: str) -> pd.DataFrame:
    """Return an attribute of `rev`, with each row's entity."""
    frame = rev.record.attributes[name].df()
    if "connection" in frame:
        frame["entity"] = frame.pop("connection").str.get("entity")
    return frame


def test_a_block_writes_a_new_revision_into_the_store_it_read(single_period):
    result = _run(ClusterTime, CLUSTER, single_period)

    assert result.store is single_period.store
    assert result.ancestry() == [single_period.id, result.id]
    to_network(result)


@pytest.mark.parametrize(
    ("config", "base_name", "stretches"),
    [
        ({"n_hours": 3}, "single_period", 8),
        ({"n_hours": 24}, "single_period", 1),
        ({"segments": 2}, "multi_period", 6),
    ],
)
def test_clustering_names_stretches_of_time_and_keeps_every_snapshot(
    config, base_name, stretches, request
):
    rev = request.getfixturevalue(base_name)
    result = _run(ClusterTime, {"name": "agg", **config}, rev)
    frame = _snapshots(result)

    assert to_network(result).snapshots.equals(to_network(rev).snapshots)
    assert frame["agg"].nunique() == stretches


def test_a_record_can_be_clustered_again_by_a_name_its_store_holds(single_period):
    first = _run(ClusterTime, CLUSTER, single_period)
    again = _run(ClusterTime, {"name": "agg_3h", "n_hours": 6}, single_period)

    frames = [_snapshots(r) for r in (first, again)]
    assert [f["agg_3h"].nunique() for f in frames] == [8, 4]


def test_clustering_leaves_the_network_it_read_alone(single_period):
    before = _snapshots(single_period)
    _run(ClusterTime, CLUSTER, single_period)
    after = _snapshots(single_period)

    assert after["agg_3h"].isna().all()
    pd.testing.assert_frame_equal(after.drop(columns="agg_3h"), before)


@pytest.mark.parametrize(
    ("config", "match"),
    [
        ({"name": "period", "n_hours": 3}, "cannot be named 'period'"),
        ({"name": "timestep", "n_hours": 3}, "cannot be named 'timestep'"),
        ({"name": "agg", "n_hours": 3, "segments": 2}, "Exactly one"),
        ({"name": "agg"}, "Exactly one"),
        ({"n_hours": 3}, "name"),
    ],
)
def test_a_time_aggregation_is_named_and_made_one_way(config, match):
    with pytest.raises(Exception, match=match):
        ClusterTime.merge_config(config, {})


AGGREGATED = [
    pytest.param(OvernightCapacityExpansion, {}, "single_period", [0], id="overnight"),
    pytest.param(OvernightCapacityExpansion, {}, "multi_period", [2050], id="overnight-last"),
    pytest.param(
        OvernightCapacityExpansion,
        {"period": 2030},
        "multi_period",
        [2030],
        id="overnight-2030",
    ),
    pytest.param(MyopicCapacityExpansion, {}, "multi_period", [2030, 2040, 2050], id="myopic"),
    pytest.param(PerfectCapacityExpansion, {}, "multi_period", [2030, 2040, 2050], id="perfect"),
    pytest.param(
        RollingHorizonDispatch,
        {"optimize_config": {"horizon": 4}},
        "single_period",
        [0],
        id="dispatch",
    ),
]


@pytest.mark.parametrize(("block_cls", "config", "base_name", "solved"), AGGREGATED)
def test_a_block_solving_by_a_time_aggregation_writes_results_at_every_snapshot(
    block_cls, config, base_name, solved, request
):
    rev = _run(ClusterTime, CLUSTER, request.getfixturevalue(base_name))

    result = _run(block_cls, {**config, "time_aggregation": "agg_3h"}, rev)

    frame = _snapshots(result)
    snapshots = frame["snapshot"][frame["period"].isin(solved)]
    p = _stored(result, "p")
    assert to_network(result).snapshots.equals(to_network(rev).snapshots)
    assert not p.duplicated(["entity", "snapshot"]).any()
    assert set(p["snapshot"]) == set(snapshots)
    assert sorted(p.query("entity == 'load'")["snapshot"]) == sorted(snapshots)


@pytest.mark.parametrize(("block_cls", "config", "base_name", "_"), AGGREGATED)
def test_a_block_needs_the_time_aggregation_it_is_given(block_cls, config, base_name, _, request):
    rev = request.getfixturevalue(base_name)
    with pytest.raises(ValueError, match="no time aggregation snapshot.agg_3h"):
        _run(block_cls, {**config, "time_aggregation": "agg_3h"}, rev)


@pytest.mark.parametrize("name", ["p", "marginal_price"])
def test_expanding_one_period_leaves_the_others_as_solving_it_in_full_does(name, multi_period):
    rev = _run(ClusterTime, CLUSTER, multi_period)
    solved = _run(PerfectCapacityExpansion, {}, rev)
    configs = [{"period": 2030}, {"period": 2030, "time_aggregation": "agg_3h"}]
    full, aggregated = (_run(OvernightCapacityExpansion, c, solved) for c in configs)

    frame = _snapshots(solved)
    elsewhere = frame["snapshot"][frame["period"] != 2030]
    rows = [_stored(r, name) for r in (full, aggregated)]
    rows = [r[r["snapshot"].isin(elsewhere)] for r in rows]
    keys = [c for c in ["entity", "bus", "snapshot"] if c in rows[0]]
    assert len(rows[0]) > 0
    pd.testing.assert_frame_equal(
        rows[1].sort_values(keys, ignore_index=True), rows[0].sort_values(keys, ignore_index=True)
    )


def test_myopic_expansion_by_a_time_aggregation_keeps_each_period_it_expanded(multi_period):
    rev = _run(ClusterTime, CLUSTER, multi_period)
    result = _run(MyopicCapacityExpansion, {"time_aggregation": "agg_3h"}, rev)
    *_, first, _, last = result.ancestry()

    expanded = [_stored(result.store.revision(u), "p") for u in (first, last)]
    in_2030 = [p[p["snapshot"].isin(expanded[0]["snapshot"])] for p in expanded]
    keys = ["entity", "snapshot"]
    assert result.ancestry()[:-3] == rev.ancestry()
    pd.testing.assert_frame_equal(
        in_2030[1].sort_values(keys, ignore_index=True),
        in_2030[0].sort_values(keys, ignore_index=True),
    )


def test_overnight_expansion_decides_what_to_build(single_period):
    result = _run(OvernightCapacityExpansion, {}, single_period)
    n = to_network(result)

    # Enough generation to meet a demand of 50 at every hour.
    assert n.generators.p_nom_opt["gen"] == pytest.approx(50.0, rel=1e-3)


def test_myopic_expansion_writes_each_period_as_a_revision_of_its_own(multi_period):
    result = _run(MyopicCapacityExpansion, {}, multi_period)
    root, *revisions = result.ancestry()
    dispatch = pd.DataFrame(
        {
            2030: {"gen-2030": 200.0, "gen-2040": 0.0, "gen-2050": 0.0},
            2040: {"gen-2030": 200.0, "gen-2040": 0.0, "gen-2050": 0.0},
            2050: {"gen-2030": 200.0, "gen-2040": 0.0, "gen-2050": 200.0},
        }
    ).T

    assert root == multi_period.id
    assert revisions[-1] == result.id
    for solved, uuid in enumerate(revisions, start=1):
        p = to_network(result.store.revision(uuid)).generators_t.p
        expected = dispatch.iloc[:solved]
        totals = p.groupby(level="period").sum().loc[expected.index, expected.columns]
        assert totals.to_numpy() == pytest.approx(expected.to_numpy(), abs=1e-3)
    built = to_network(result).generators.p_nom_opt.to_dict()
    assert built == pytest.approx({"gen-2030": 50.0, "gen-2040": 0.0, "gen-2050": 50.0}, abs=1e-3)


@pytest.mark.parametrize(
    ("period", "built"),
    [
        (None, {"gen-2030": 0.0, "gen-2040": 0.0, "gen-2050": 100.0}),
        (2030, {"gen-2030": 50.0}),
    ],
)
def test_overnight_expansion_builds_one_period_from_what_exists(period, built, multi_period):
    result = _run(OvernightCapacityExpansion, {"period": period}, multi_period)
    solved = 2050 if period is None else period
    n = to_network(result, select={"period": [solved]})

    assert result.ancestry() == [multi_period.id, result.id]
    assert n.generators.p_nom_opt.to_dict() == pytest.approx(built, abs=1e-3)


def test_overnight_expansion_needs_the_period_it_is_given(multi_period):
    with pytest.raises(ValueError, match="no investment period 2045"):
        _run(OvernightCapacityExpansion, {"period": 2045}, multi_period)


def test_a_failed_solve_raises_a_solve_error(store_revision, new_single_period_network):
    n = new_single_period_network()
    n.generators.p_nom_max = 0.0
    with pytest.raises(SolveError, match="infeasible"):
        _run(OvernightCapacityExpansion, {}, store_revision(n, "infeasible"))


def _assets(period: int, lifetime: float, component: str = "Generator") -> pypsa.Network:
    n = pypsa.Network()
    n.investment_periods = [period]
    n.add("Bus", ["a", "b"])
    buses = {"bus": "a"} if component == "Generator" else {"bus0": "a", "bus1": "b", "x": 0.1}
    extendable = {nominal_attr(component) + "_extendable": True}
    n.add(
        component,
        ["built", "new"],
        **buses,
        **extendable,
        build_year=[2030, 2040],
        lifetime=lifetime,
    )
    return n


@pytest.mark.parametrize("component", ["Generator", "Transformer"])
@pytest.mark.parametrize("lifetime", [30.0, float("inf")])
def test_brownfield_fixes_what_the_previous_period_built(lifetime, component):
    attr = nominal_attr(component)
    n = _assets(2040, lifetime, component)
    previous = _assets(2030, lifetime, component)
    previous.c[component].static.loc["built", attr + "_opt"] = 40.0

    MyopicCapacityExpansion.add_brownfield(n, previous)

    static = n.c[component].static
    assert static[attr].to_dict() == {"built": 40.0, "new": 0.0}
    assert static[attr + "_extendable"].to_dict() == {"built": False, "new": True}


@pytest.mark.parametrize(("lifetime", "kept"), [(30.0, ["new"]), (float("inf"), ["built", "new"])])
def test_cohorts_built_before_the_period_are_removed(lifetime, kept):
    n = _assets(2040, lifetime)
    remove_unbuilt_cohorts(n)
    assert n.generators.index.tolist() == kept


def test_myopic_expansion_never_builds_a_cohort_before_the_first_period(
    store_revision, multi_period_network
):
    n = multi_period_network
    n.add("Generator", "gen-2020", bus="bus", p_nom_extendable=True, build_year=2020, lifetime=40)
    rev = store_revision(n, "early-cohort")

    result = _run(MyopicCapacityExpansion, {}, rev)

    dispatch = to_network(result, select={"period": [2050]}).generators_t.p.sum().to_dict()
    expected = {"gen-2020": 0.0, "gen-2030": 200.0, "gen-2040": 0.0, "gen-2050": 200.0}
    assert dispatch == pytest.approx(expected, abs=1e-3)


def test_dispatch_can_run_against_capacities_another_block_chose(single_period):
    expanded = _run(OvernightCapacityExpansion, {}, single_period)

    result = _run(
        RollingHorizonDispatch,
        {
            "capacity_source": RevisionRef.from_revision(expanded),
            "optimize_config": {"horizon": 12},
        },
        single_period,
    )
    n = to_network(result)

    assert n.generators.p_nom_opt["gen"] == pytest.approx(50.0, rel=1e-3)


@pytest.mark.parametrize("component", ["Generator", "Line", "Transformer"])
def test_dispatch_fixes_the_capacities_its_source_decided(component):
    attr = nominal_attr(component)
    n = _assets(2030, 30.0, component)

    RollingHorizonDispatch.apply_decided_capacities(n, pd.Series({"built": 40.0, "new": 10.0}))

    static = n.c[component].static
    assert static[attr].to_dict() == {"built": 40.0, "new": 10.0}
    assert not static[attr + "_extendable"].any()


def test_dispatch_can_run_on_its_own(single_period, store_revision):
    n = to_network(single_period)
    n.generators.loc["gen", "p_nom_extendable"] = False
    n.generators.loc["gen", "p_nom"] = 100.0
    rev = store_revision(n, "fixed")

    result = _run(
        RollingHorizonDispatch,
        {"optimize_config": {"horizon": 12}},
        rev,
    )
    assert to_network(result).generators.p_nom["gen"] == pytest.approx(100.0)


def _dispatch(rev: Revision, **config) -> Revision:
    return _run(RollingHorizonDispatch, {"optimize_config": {"horizon": 4}, **config}, rev)


def _periods(rev: Revision) -> list[int]:
    frame = _snapshots(rev)
    solved = frame["snapshot"].isin(_stored(rev, "p")["snapshot"])
    return sorted(frame["period"][solved].unique())


@pytest.mark.parametrize("periods", [[2040], [2030, 2050]])
def test_dispatch_writes_the_periods_it_is_given_and_leaves_the_others(periods, multi_period):
    solved = _run(PerfectCapacityExpansion, {}, multi_period)

    fresh = _dispatch(
        multi_period, capacity_source=RevisionRef.from_revision(solved), periods=periods
    )
    again = _dispatch(solved, capacity_source=RevisionRef.from_revision(solved), periods=periods)

    frame = _snapshots(solved)
    elsewhere = frame["snapshot"][~frame["period"].isin(periods)]
    keys = ["entity", "snapshot"]
    rows = [_stored(r, "p") for r in (solved, again)]
    rows = [r[r["snapshot"].isin(elsewhere)].sort_values(keys, ignore_index=True) for r in rows]
    assert _periods(fresh) == periods
    assert to_network(again).snapshots.equals(to_network(solved).snapshots)
    pd.testing.assert_frame_equal(rows[1], rows[0])


@pytest.mark.parametrize(
    ("periods", "match"),
    [
        ([2045], "no investment periods \\[2045\\]"),
        (None, "no results of the periods \\[2030, 2040\\]"),
    ],
)
def test_dispatch_refuses_periods_its_model_or_source_lacks(periods, match, multi_period):
    expanded = _run(OvernightCapacityExpansion, {}, multi_period)
    with pytest.raises(ValueError, match=match):
        _dispatch(
            multi_period, capacity_source=RevisionRef.from_revision(expanded), periods=periods
        )


def test_dispatch_refuses_periods_of_a_model_without_them(single_period):
    with pytest.raises(ValueError, match="no investment periods to dispatch"):
        _dispatch(single_period, periods=[2030])


@pytest.mark.parametrize("period", [2030, 2050])
def test_dispatch_runs_the_period_overnight_expansion_built_for(period, multi_period):
    expanded = _run(OvernightCapacityExpansion, {"period": period}, multi_period)

    result = _dispatch(
        multi_period, capacity_source=RevisionRef.from_revision(expanded), periods=[period]
    )

    n = to_network(result, select={"period": [period]})
    assert _periods(result) == [period]
    assert n.generators_t.p.sum(axis=1).to_numpy() == pytest.approx(n.loads_t.p.sum(axis=1))


def test_dispatch_of_one_period_keeps_the_cohorts_myopic_expansion_built(
    store_revision, multi_period_network
):
    n = multi_period_network
    n.add("Generator", "gen-2020", bus="bus", p_nom_extendable=True, build_year=2020, lifetime=40)
    rev = store_revision(n, "early-cohort")
    expanded = _run(MyopicCapacityExpansion, {}, rev)

    result = _dispatch(rev, capacity_source=RevisionRef.from_revision(expanded), periods=[2050])

    dispatch = _stored(result, "p").groupby("entity")["value"].sum().to_dict()
    expected = {"gen-2030": 200.0, "gen-2040": 0.0, "gen-2050": 200.0, "load": 400.0}
    assert dispatch == pytest.approx(expected, abs=1e-3)


def test_dispatch_refuses_an_asset_its_source_decided_no_capacity_of(single_period, store_revision):
    expanded = _run(OvernightCapacityExpansion, {}, single_period)
    n = to_network(single_period)
    n.add("Generator", "unplanned", bus="bus", p_nom_extendable=True)
    with pytest.raises(ValueError, match="decided no capacity of {'Generator': \\['unplanned'\\]}"):
        _dispatch(
            store_revision(n, "unplanned"), capacity_source=RevisionRef.from_revision(expanded)
        )


@pytest.mark.parametrize(
    ("base_name", "config", "shed"),
    [
        ("single_period", {}, 720.0),
        ("single_period", {"time_aggregation": "agg_3h"}, 720.0),
        ("multi_period", {"periods": [2050]}, 320.0),
    ],
)
def test_load_shedding_meets_the_demand_fixed_capacities_cannot(
    base_name, config, shed, store_revision, request
):
    n = to_network(request.getfixturevalue(base_name))
    n.generators["p_nom_extendable"] = False
    n.generators.loc[n.generators.index[0], "p_nom"] = 20.0
    rev = _run(ClusterTime, CLUSTER, store_revision(n, "short"))
    with pytest.raises(SolveError, match="could not solve every window"):
        _dispatch(rev, **config)

    result = _dispatch(rev, load_shedding={}, **config)

    p = _stored(result, "p").query("entity == 'bus load shedding'")
    assert p["value"].sum() * 1e-3 == pytest.approx(shed)


def _with_storage(rev: Revision, store_revision, component: str, **storage) -> Revision:
    """Add `storage` of a `component` to the network of `rev`, and cluster it by `agg_3h`."""
    n = to_network(rev)
    n.add(component, "storage", bus="bus", **storage)
    return _run(ClusterTime, CLUSTER, store_revision(n, "storage"))


def test_dispatch_by_a_time_aggregation_starts_its_storage_at_its_initial_state(
    single_period, store_revision
):
    rev = _with_storage(single_period, store_revision, "Store", e_nom=100.0, e_initial=60.0)
    config = {"optimize_config": {"horizon": 4}, "time_aggregation": "agg_3h"}

    result = _run(RollingHorizonDispatch, config, rev)

    first = _snapshots(rev)["snapshot"].min()
    e, p = (_stored(result, name).query("entity == 'storage'") for name in ("e", "p"))
    merged = e.merge(p, on="snapshot", suffixes=("", "_p"))
    frame = merged[merged["snapshot"] == first]
    assert (frame["value"] + frame["value_p"]).item() == pytest.approx(60.0)
    assert frame["value"].item() < 60.0


def test_dispatch_by_a_time_aggregation_not_over_investment_periods_carries_storage_across_them(
    multi_period, store_revision
):
    storage = {"e_nom": 100.0, "e_initial": 60.0, "e_initial_per_period": True}
    rev = _with_storage(multi_period, store_revision, "Store", **storage)
    config = {"optimize_config": {"horizon": 2}, "time_aggregation": "agg_3h"}

    result = _run(RollingHorizonDispatch, config, rev)

    frame = _snapshots(rev)
    e, p = (_stored(result, name).query("entity == 'storage'") for name in ("e", "p"))
    states = frame.merge(e, on="snapshot").merge(p, on="snapshot", suffixes=("", "_p"))
    opening = states[states["period"] == 2040].iloc[0]
    ending = states[states["period"] == 2030].iloc[-1]
    assert opening["value"] + opening["value_p"] == pytest.approx(ending["value"], abs=1e-6)


@pytest.mark.parametrize(
    ("component", "storage"),
    [
        ("Store", {"e_nom": 100.0, "e_cyclic": True}),
        ("StorageUnit", {"p_nom": 50.0, "cyclic_state_of_charge": True}),
    ],
)
def test_dispatch_by_a_time_aggregation_refuses_storage_each_window_cycles(
    component, storage, single_period, store_revision
):
    rev = _with_storage(single_period, store_revision, component, **storage)
    config = {"optimize_config": {"horizon": 4}, "time_aggregation": "agg_3h"}
    with pytest.raises(NotImplementedError, match="each window restarts"):
        _run(RollingHorizonDispatch, config, rev)


def test_a_rolling_horizon_must_move_forward():
    with pytest.raises(Exception, match="overlap"):
        RollingHorizonDispatch.merge_config({"optimize_config": {"horizon": 4, "overlap": 4}}, {})


def test_a_wired_capacity_source_is_checked_like_any_other_setting():
    with pytest.raises(Exception, match="capacity_source"):
        RollingHorizonDispatch.merge_config({}, {"capacity_source": "not-a-revision"})


def test_a_capacity_source_can_be_given_by_its_field_name():
    # It also has a friendlier name for display, which must not stop the field itself
    # being set the ordinary way.
    source = {"store": "somewhere", "id": "00000000-0000-0000-0000-000000000000"}
    config = RollingHorizonDispatch.merge_config({"capacity_source": source}, {})
    assert config.capacity_source.store == "somewhere"
