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

import numpy as np
import pandas as pd
from datarecord import Revision
from playbook.blocks.core import SolveError
from pydantic import ValidationError

from playbook_library.myopic_capacity_expansion import MyopicCapacityExpansion
from playbook_library.overnight_capacity_expansion import OvernightCapacityExpansion
from playbook_library.perfect_capacity_expansion import PerfectCapacityExpansion
from playbook_library.pypsa_helpers import (
    BUILT_COMPONENTS,
    apply_decided_capacities,
    fix_capacities,
    nominal_attr,
    remove_unbuilt_cohorts,
    to_network,
    write_network,
)
from playbook_library.pypsa_spatial_aggregation import ENTITY_COMPONENTS
from playbook_library.pypsa_time_aggregation import series_frame, snapshot_frame
from playbook_library.rolling_horizon_dispatch import RollingHorizonDispatch
from playbook_library.tests.networks import ZONES_AND_CARRIERS, new_zoned_network, set_status
from playbook_library.time_partition import TimePartition
from playbook_library.water_value_calculation import WaterValueCalculation

pytestmark = pytest.mark.pypsa


def _run(block_cls, config: dict, base: Revision) -> Revision:
    """Run a block on `base`, inside the test's own workspace."""
    return block_cls(block_cls.merge_config(config, {})).run(base)


CLUSTER = {"name": "agg_3h", "n_hours": 3}


def _fixed(n: pypsa.Network) -> pypsa.Network:
    """Fix the capacity of each generator of `n` at 100, so it is dispatched as it is."""
    n.generators["p_nom_extendable"] = False
    n.generators["p_nom"] = 100.0
    return n


@pytest.fixture
def fixed_single_period_record(store_revision, new_single_period_network) -> Revision:
    return store_revision(_fixed(new_single_period_network()), "fixed")


def _snapshots(rev: Revision) -> pd.DataFrame:
    return snapshot_frame(rev.record)


def _stored(rev: Revision, name: str) -> pd.DataFrame:
    """Return an attribute of `rev`, with each row's entity."""
    frame = series_frame(rev.record, name)
    if "connection" in frame:
        frame["entity"] = frame.pop("connection").str.get("entity")
    return frame


def test_a_block_writes_a_new_revision_into_the_store_it_read(single_period):
    result = _run(TimePartition, CLUSTER, single_period)

    assert result.store is single_period.store
    assert result.ancestry() == [single_period.id, result.id]
    to_network(result)


@pytest.mark.parametrize(
    ("config", "base_name", "stretches"),
    [
        ({"n_hours": 3}, "single_period", 8),
        ({"n_hours": 24}, "single_period", 1),
        ({"n_hours": 2}, "multi_period", 6),
    ],
)
def test_clustering_names_stretches_of_time_and_keeps_every_snapshot(
    config, base_name, stretches, request
):
    rev = request.getfixturevalue(base_name)
    result = _run(TimePartition, {"name": "agg", **config}, rev)
    frame = _snapshots(result)

    assert to_network(result).snapshots.equals(to_network(rev).snapshots)
    assert frame["agg"].nunique() == stretches


def test_a_record_can_be_clustered_again_by_a_name_its_store_holds(single_period):
    first = _run(TimePartition, CLUSTER, single_period)
    again = _run(TimePartition, {"name": "agg_3h", "n_hours": 6}, single_period)

    frames = [_snapshots(r) for r in (first, again)]
    assert [f["agg_3h"].nunique() for f in frames] == [8, 4]


def test_clustering_leaves_the_network_it_read_alone(single_period):
    before = _snapshots(single_period)
    _run(TimePartition, CLUSTER, single_period)
    after = _snapshots(single_period)

    pd.testing.assert_frame_equal(after, before)


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
        TimePartition.merge_config(config, {})


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
        "fixed_single_period_record",
        [0],
        id="dispatch",
    ),
]


@pytest.mark.parametrize(
    "aggregation",
    [{"snapshot": "agg_3h"}, {"snapshot": "agg_3h", "bus": "carrier", "entity": "ctype"}],
    ids=["time", "time-buses-assets"],
)
@pytest.mark.parametrize(("block_cls", "config", "base_name", "solved"), AGGREGATED)
def test_a_block_solving_by_an_aggregation_writes_results_at_every_snapshot(
    block_cls, config, base_name, solved, aggregation, request
):
    rev = _run(TimePartition, CLUSTER, request.getfixturevalue(base_name))

    result = _run(block_cls, {**config, "aggregation": aggregation}, rev)

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
        _run(block_cls, {**config, "aggregation": {"snapshot": "agg_3h"}}, rev)


@pytest.mark.parametrize("name", ["p", "marginal_price"])
def test_expanding_one_period_leaves_the_others_as_solving_it_in_full_does(name, multi_period):
    rev = _run(TimePartition, CLUSTER, multi_period)
    solved = _run(PerfectCapacityExpansion, {}, rev)
    configs = [{"period": 2030}, {"period": 2030, "aggregation": {"snapshot": "agg_3h"}}]
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
    rev = _run(TimePartition, CLUSTER, multi_period)
    result = _run(MyopicCapacityExpansion, {"aggregation": {"snapshot": "agg_3h"}}, rev)
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


def test_dispatch_runs_against_the_capacities_an_expansion_decided(single_period):
    expanded = _run(OvernightCapacityExpansion, {}, single_period)

    result = _run(RollingHorizonDispatch, {"optimize_config": {"horizon": 12}}, expanded)
    n = to_network(result)

    assert n.generators.p_nom_opt["gen"] == pytest.approx(50.0, rel=1e-3)


@pytest.mark.parametrize("component", ["Generator", "Line", "Transformer"])
def test_dispatch_fixes_the_capacities_an_expansion_decided(component):
    attr = nominal_attr(component)
    n = _assets(2030, 30.0, component)

    apply_decided_capacities(n, pd.Series({"built": 40.0, "new": 10.0}))

    static = n.c[component].static
    assert static[attr].to_dict() == {"built": 40.0, "new": 10.0}
    assert not static[attr + "_extendable"].any()


def test_dispatch_can_run_on_its_own(fixed_single_period_record):
    result = _run(
        RollingHorizonDispatch, {"optimize_config": {"horizon": 12}}, fixed_single_period_record
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

    again = _dispatch(solved, periods=periods)

    frame = _snapshots(solved)
    elsewhere = frame["snapshot"][~frame["period"].isin(periods)]
    keys = ["entity", "snapshot"]
    rows = [_stored(r, "p") for r in (solved, again)]
    rows = [r[r["snapshot"].isin(elsewhere)].sort_values(keys, ignore_index=True) for r in rows]
    assert to_network(again).snapshots.equals(to_network(solved).snapshots)
    pd.testing.assert_frame_equal(rows[1], rows[0])


@pytest.mark.parametrize(
    ("periods", "match"),
    [
        ([2045], "no investment periods \\[2045\\]"),
        (None, "no results of the periods \\[2030, 2040\\]"),
    ],
)
def test_dispatch_refuses_periods_its_model_or_expansion_lacks(periods, match, multi_period):
    expanded = _run(OvernightCapacityExpansion, {}, multi_period)
    with pytest.raises(ValueError, match=match):
        _dispatch(expanded, periods=periods)


def test_dispatch_refuses_periods_of_a_model_without_them(single_period):
    with pytest.raises(ValueError, match="no investment periods to select"):
        _dispatch(single_period, periods=[2030])


@pytest.mark.parametrize("period", [2030, 2050])
def test_dispatch_runs_the_period_overnight_expansion_built_for(period, multi_period):
    expanded = _run(OvernightCapacityExpansion, {"period": period}, multi_period)

    result = _dispatch(expanded, periods=[period])

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

    result = _dispatch(expanded, periods=[2050])

    dispatch = to_network(result, select={"period": [2050]}).generators_t.p.sum().to_dict()
    expected = {"gen-2020": 0.0, "gen-2030": 200.0, "gen-2040": 0.0, "gen-2050": 200.0}
    assert dispatch == pytest.approx(expected, abs=1e-3)


@pytest.mark.parametrize(
    ("asset", "capacity"), [("gen", 0.0), ("brownfield", 20.0), ("fixed", 30.0)]
)
def test_fixing_capacities_takes_the_decided_capacity_of_extendable_assets_alone(
    asset, capacity, store_revision, new_single_period_network
):
    n = new_single_period_network()
    n.add("Generator", "fixed", bus="bus", p_nom=30.0, marginal_cost=1.0)
    brownfield = {"p_nom": 10.0, "p_nom_min": 10.0, "p_nom_extendable": True}
    n.add("Generator", "brownfield", bus="bus", capital_cost=1.0, marginal_cost=10.0, **brownfield)
    expanded = _run(OvernightCapacityExpansion, {}, store_revision(n, "brownfield"))
    fixed = to_network(expanded)

    fix_capacities(fixed, expanded, [])

    assert fixed.generators.p_nom[asset] == pytest.approx(capacity, abs=1e-3)
    assert not fixed.generators.p_nom_extendable.any()


def test_dispatch_refuses_an_extendable_asset_no_expansion_decided(single_period):
    with pytest.raises(ValueError, match="decided no capacity of {'Generator': \\['gen'\\]}"):
        _dispatch(single_period)


TECHNOLOGY_GROUPS = {"entity": "technology_group", "ungrouped": "drop"}


@pytest.mark.parametrize(
    ("base_name", "config", "shed"),
    [
        ("single_period", {}, 720.0),
        ("single_period", {"aggregation": {"snapshot": "agg_3h"}}, 720.0),
        ("single_period", {"aggregation": TECHNOLOGY_GROUPS}, 720.0),
        ("multi_period", {"periods": [2050]}, 320.0),
    ],
)
def test_load_shedding_meets_the_demand_fixed_capacities_cannot(
    base_name, config, shed, store_revision, request
):
    n = to_network(request.getfixturevalue(base_name))
    n.generators["p_nom_extendable"] = False
    n.generators.loc[n.generators.index[0], "p_nom"] = 20.0
    n.generators["technology_group"] = "supply"
    n.loads["technology_group"] = "demand"
    rev = _run(TimePartition, CLUSTER, store_revision(n, "short"))
    with pytest.raises(SolveError, match="could not solve a window"):
        _dispatch(rev, **config)

    result = _dispatch(rev, load_shedding={}, **config)

    p = _stored(result, "p").query("entity == 'bus load shedding'")
    assert p["value"].sum() * 1e-3 == pytest.approx(shed)


def _with_storage(rev: Revision, store_revision, component: str, **storage) -> Revision:
    """Add `storage` of a `component` to the fixed network of `rev`, clustered by `agg_3h`."""
    n = _fixed(to_network(rev))
    n.add(component, "storage", bus="bus", **storage)
    return _run(TimePartition, CLUSTER, store_revision(n, "storage"))


def test_dispatch_by_a_time_aggregation_starts_its_storage_at_its_initial_state(
    single_period, store_revision
):
    rev = _with_storage(single_period, store_revision, "Store", e_nom=100.0, e_initial=60.0)
    config = {"optimize_config": {"horizon": 4}, "aggregation": {"snapshot": "agg_3h"}}

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
    config = {"optimize_config": {"horizon": 2}, "aggregation": {"snapshot": "agg_3h"}}

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
    config = {"optimize_config": {"horizon": 4}, "aggregation": {"snapshot": "agg_3h"}}
    with pytest.raises(NotImplementedError, match="each window restarts"):
        _run(RollingHorizonDispatch, config, rev)


def test_a_rolling_horizon_must_move_forward():
    with pytest.raises(Exception, match="overlap"):
        RollingHorizonDispatch.merge_config({"optimize_config": {"horizon": 4, "overlap": 4}}, {})


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("optimize_config.solver_options.primal_feasibility_tolerance", 1e-12),
        ("optimize_config.solver_options.dual_feasibility_tolerance", 1e-12),
        ("optimize_config.solver_options.random_seed", -1),
        ("optimize_config.solver_options.random_seed", 2**31),
        ("optimize_config.transmission_losses.atol", 0.0),
        ("optimize_config.transmission_losses.rtol", -0.1),
        ("optimize_config.transmission_losses.max_segments", 0),
        ("optimize_config.transmission_losses.segments", 0),
        ("optimize_config.committable_big_m", 0.0),
        ("optimize_config.horizon", 0),
        ("optimize_config.overlap", -1),
        ("load_shedding.marginal_cost", -1.0),
        ("load_shedding.p_nom", -1.0),
        ("load_shedding.sign", 0.0),
    ],
)
def test_a_setting_the_solve_would_refuse_is_refused_as_config(setting, value):
    config = value
    for key in reversed(setting.split(".")):
        config = {key: config}
    with pytest.raises(ValidationError, match=setting):
        RollingHorizonDispatch.merge_config(config, {})


@pytest.mark.parametrize(
    ("block_cls", "config"),
    [
        (RollingHorizonDispatch, {"periods": []}),
        (WaterValueCalculation, {"carriers": ["battery"], "periods": []}),
        (WaterValueCalculation, {"carriers": []}),
    ],
)
def test_an_empty_list_of_periods_or_carriers_is_refused(block_cls, config):
    with pytest.raises(Exception, match="at least 1 item"):
        block_cls.merge_config(config, {})


FIXED = {
    "solar_a": 100.0,
    "solar_b": 140.0,
    "gas_c": 80.0,
    "gas_d": 10.0,
    "st_c": 60.0,
    "st_d": 100.0,
    "bat_a": 1.0,
    "bat_b": 0.5,
}
SHORT = {**FIXED, "solar_a": 10.0, "solar_b": 30.0, "gas_c": 0.0, "gas_d": 0.0}


def _fixed_zoned(store_revision, capacities: dict[str, float]) -> Revision:
    """Store the zoned network of `capacities`, partitioned into two-hour stretches `agg_2h`.

    Each asset has its carrier as its `group` too.
    """
    n = new_zoned_network()
    apply_decided_capacities(n, pd.Series(capacities))
    for c in n.components[ENTITY_COMPONENTS]:
        c.static["group"] = c.static.carrier
    rev = store_revision(set_status(n), "fixed")
    return _run(TimePartition, {"name": "agg_2h", "n_hours": 2}, rev)


@pytest.fixture
def fixed_zoned_record(store_revision) -> Revision:
    return _fixed_zoned(store_revision, FIXED)


def _water_value(rev: Revision, **config) -> Revision:
    return _run(WaterValueCalculation, {"carriers": ["battery"], **config}, rev)


def _foresight(rev: Revision, horizon: int) -> pypsa.Network:
    return to_network(_dispatch(rev, optimize_config={"horizon": horizon}))


def test_a_water_value_is_the_price_a_solve_of_the_whole_period_cycling_stores_finds_at_their_bus(
    fixed_zoned_record,
):
    n = to_network(_water_value(fixed_zoned_record))

    whole = to_network(fixed_zoned_record)
    whole.stores["e_cyclic"] = True
    whole.optimize()
    expected = whole.buses_t.marginal_price[["c", "d"]].set_axis(["st_c", "st_d"], axis=1)
    pd.testing.assert_frame_equal(
        n.stores_t.marginal_cost, expected, check_names=False, check_column_type=False
    )
    assert n.stores.marginal_cost.eq(0).all()


@pytest.mark.parametrize(
    ("aggregation", "load_shedding"),
    [({"snapshot": "agg_2h"}, None), ({"snapshot": "agg_2h", **ZONES_AND_CARRIERS}, {})],
)
def test_a_water_value_solved_by_a_time_aggregation_holds_over_each_stretch(
    aggregation, load_shedding, fixed_zoned_record
):
    result = _water_value(fixed_zoned_record, aggregation=aggregation, load_shedding=load_shedding)

    values = to_network(result).stores_t.marginal_cost
    assert values.notna().all().all()
    assert values.groupby(np.arange(len(values)) // 2).nunique().eq(1).all().all()


@pytest.mark.parametrize(
    ("carriers", "cyclic", "match"),
    [
        (["battery", "H2"], False, "no stores of the carriers \\['H2'\\]"),
        (["solar"], False, "no stores of the carriers \\['solar'\\]"),
        (["battery"], True, "\\['st_c'\\] restart: a rolling horizon dispatch restarts"),
    ],
)
def test_a_water_value_needs_stores_a_rolling_horizon_can_carry_energy_in(
    carriers, cyclic, match, store_revision
):
    n = new_zoned_network()
    apply_decided_capacities(n, pd.Series(FIXED))
    n.stores.loc["st_c", "e_cyclic"] = cyclic
    with pytest.raises(ValueError, match=match):
        _water_value(store_revision(n, "cyclic"), carriers=carriers)


def test_a_water_value_refuses_a_solve_over_investment_periods():
    config = {"carriers": ["battery"], "optimize_config": {"multi_investment_periods": True}}
    with pytest.raises(Exception, match="one investment period at a time"):
        WaterValueCalculation.merge_config(config, {})


def test_a_water_value_of_one_period_leaves_the_others_alone(store_revision, multi_period_network):
    multi_period_network.add(
        "Store", "tank", bus="bus", carrier="battery", e_nom=10.0, marginal_cost=7.0
    )
    expanded = _run(PerfectCapacityExpansion, {}, store_revision(multi_period_network, "one"))
    first = _water_value(expanded, periods=[2040])

    values = to_network(_water_value(first, periods=[2030])).stores_t.marginal_cost["tank"]

    first_values = to_network(first).stores_t.marginal_cost["tank"]
    pd.testing.assert_series_equal(values.loc[2040], first_values.loc[2040])
    assert values.drop(2050).gt(0).all()
    assert values.loc[2050].eq(7.0).all()


def test_a_water_value_leaves_the_capacities_of_its_input_alone(
    store_revision, multi_period_network
):
    multi_period_network.add("Store", "tank", bus="bus", carrier="battery", e_nom=10.0)
    rev = store_revision(multi_period_network, "extendable")
    expanded = _run(PerfectCapacityExpansion, {}, rev)

    result = to_network(_water_value(expanded, load_shedding={}))

    n = to_network(expanded)
    for c in n.components[BUILT_COMPONENTS]:
        columns = [nominal_attr(c.name), nominal_attr(c.name) + "_extendable"]
        pd.testing.assert_frame_equal(result.components[c.name].static[columns], c.static[columns])


@pytest.mark.parametrize("aggregation", [{}, {"snapshot": "agg_2h"}])
def test_water_values_let_a_rolling_horizon_store_energy_for_a_later_window(
    aggregation, store_revision
):
    """Store `st_c` charges through a costly link while solar is spilt, for the evening."""
    n = new_zoned_network()
    apply_decided_capacities(n, pd.Series({**FIXED, "st_c": 100.0, "st_d": 0.0}))
    n.add("Bus", "h", carrier="battery")
    n.add(
        "Link",
        ["charge", "discharge"],
        bus0=["c", "h"],
        bus1=["h", "c"],
        carrier="battery",
        p_nom=30.0,
        efficiency=0.9,
        marginal_cost=[0.5, 0.0],
    )
    n.stores.loc["st_c", "bus"] = "h"
    rev = _run(
        TimePartition,
        {"name": "agg_2h", "n_hours": 2},
        store_revision(set_status(n), "behind_links"),
    )
    valued = _water_value(rev, aggregation=aggregation)

    perfect = _foresight(rev, 6).stores_t.e["st_c"]
    myopic, foresighted = (_foresight(r, 3).stores_t.e["st_c"] for r in (rev, valued))

    assert foresighted.iloc[:4].to_numpy() == pytest.approx(perfect.iloc[:4], abs=1e-3)
    assert perfect.iloc[2] > 0
    assert myopic.iloc[2] == pytest.approx(0.0, abs=1e-3)


@pytest.mark.parametrize(
    "aggregation",
    [
        {},
        ZONES_AND_CARRIERS,
        {"snapshot": "agg_2h", **ZONES_AND_CARRIERS},
        {"entity": "group", "ungrouped": "drop"},
    ],
)
def test_a_water_value_prices_the_load_fixed_capacities_cannot_meet_at_its_shedding_cost(
    aggregation, store_revision
):
    rev = _fixed_zoned(store_revision, SHORT)
    with pytest.raises(SolveError):
        _water_value(rev, aggregation=aggregation)

    result = _water_value(rev, aggregation=aggregation, load_shedding={})

    assert to_network(result).stores_t.marginal_cost.to_numpy() == pytest.approx(1e5)


@pytest.mark.parametrize(
    ("cap", "period", "error", "match"),
    [
        (0.0, 2050, SolveError, None),
        (400.0, 2050, ValueError, "\\['co2-2050'\\] limit their snapshots as a whole"),
        (400.0, np.nan, ValueError, "\\['co2-2050'\\] limit their snapshots as a whole"),
    ],
)
def test_one_period_solves_under_the_global_constraints_of_that_period(
    cap, period, error, match, store_revision, multi_period_network
):
    """The 2050 demand of 400 emits 400, so a cap below it cannot be met.

    A rolling horizon would hold a cap other than 0 in full within each window, whether
    it is of the period or of no period.
    """
    n = multi_period_network
    n.add("Carrier", "gas", co2_emissions=1.0)
    n.generators["carrier"] = "gas"
    expanded = _run(OvernightCapacityExpansion, {}, store_revision(n, "uncapped"))
    capped = to_network(expanded)
    capped.add(
        "GlobalConstraint",
        ["co2-2030", "co2-2050"],
        type="primary_energy",
        carrier_attribute="co2_emissions",
        sense="<=",
        constant=[0.0, cap],
        investment_period=[2030, period],
    )
    config = {"periods": [2050], "optimize_config": {"horizon": 4}}

    with pytest.raises(error, match=match):
        _run(RollingHorizonDispatch, config, write_network(capped, expanded))


def test_a_rolling_horizon_refuses_a_cap_on_a_model_without_investment_periods(
    store_revision, new_single_period_network
):
    n = _fixed(new_single_period_network())
    n.add("GlobalConstraint", "co2", type="primary_energy", sense="<=", constant=2000.0)
    with pytest.raises(ValueError, match="\\['co2'\\] limit their snapshots as a whole"):
        _dispatch(store_revision(n, "capped"))
