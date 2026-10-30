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
from playbook.blocks.core import DataRecord

from playbook_library.examples import build_example_network
from playbook_library.myopic_capacity_expansion import MyopicCapacityExpansion
from playbook_library.overnight_capacity_expansion import OvernightCapacityExpansion
from playbook_library.pypsa_helpers import nominal_attr, remove_unbuilt_cohorts, to_network
from playbook_library.rolling_horizon_dispatch import RollingHorizonDispatch
from playbook_library.time_cluster import ClusterTime

pytestmark = pytest.mark.pypsa


def _run(block_cls, config: dict, record: DataRecord) -> DataRecord:
    """Run a block the way a playbook's step runner would."""
    return block_cls(block_cls.merge_config(config, {})).run(record)


@pytest.fixture
def single_period_record(store_record) -> DataRecord:
    """One bus, one generator that can be built, and a day of demand."""
    return store_record(build_example_network(), "base")


def _multi_period_network() -> pypsa.Network:
    """Three investment periods: a cheap generator, dearer ones later, demand doubling last."""
    n = pypsa.Network()
    periods = [2030, 2040, 2050]
    snapshots = pd.MultiIndex.from_product(
        [periods, pd.date_range("2030-01-01", periods=4, freq="h")],
        names=["period", "timestep"],
    )
    n.set_snapshots(snapshots)
    n.investment_periods = periods
    n.add("Bus", "bus")
    for period in periods:
        n.add(
            "Generator",
            f"gen-{period}",
            bus="bus",
            p_nom_extendable=True,
            build_year=period,
            lifetime=30,
            capital_cost=1.0 if period == 2030 else 100.0,
            marginal_cost=10.0,
        )
    n.add("Load", "load", bus="bus", p_set=pd.Series([50.0] * 8 + [100.0] * 4, index=snapshots))
    return n


@pytest.fixture
def multi_period_record(store_record) -> DataRecord:
    return store_record(_multi_period_network(), "periods")


def test_a_block_writes_a_new_revision_into_the_store_it_read(single_period_record, ancestry):
    result = _run(ClusterTime, {"n_hours": 3}, single_period_record)

    assert result.url == single_period_record.url
    assert ancestry(result) == [single_period_record.uuid, result.uuid]
    to_network(result)


def test_clustering_by_hours_shortens_the_time_series(single_period_record):
    before = len(to_network(single_period_record).snapshots)
    result = _run(ClusterTime, {"n_hours": 3}, single_period_record)
    after = len(to_network(result).snapshots)

    assert before == 24
    assert after == 8


def test_clustering_leaves_the_network_it_read_alone(single_period_record):
    _run(ClusterTime, {"n_hours": 3}, single_period_record)
    assert len(to_network(single_period_record).snapshots) == 24


def test_overnight_expansion_decides_what_to_build(single_period_record):
    result = _run(OvernightCapacityExpansion, {}, single_period_record)
    n = to_network(result)

    # Enough generation to meet a demand of 50 at every hour.
    assert n.generators.p_nom_opt["gen"] == pytest.approx(50.0, rel=1e-3)


def test_myopic_expansion_writes_each_period_as_a_revision_of_its_own(
    multi_period_record, ancestry
):
    result = _run(MyopicCapacityExpansion, {}, multi_period_record)
    root, *revisions = ancestry(result)
    dispatch = pd.DataFrame(
        {
            2030: {"gen-2030": 200.0, "gen-2040": 0.0, "gen-2050": 0.0},
            2040: {"gen-2030": 200.0, "gen-2040": 0.0, "gen-2050": 0.0},
            2050: {"gen-2030": 200.0, "gen-2040": 0.0, "gen-2050": 200.0},
        }
    ).T

    assert root == multi_period_record.uuid
    assert revisions[-1] == result.uuid
    for solved, uuid in enumerate(revisions, start=1):
        p = to_network(DataRecord(url=result.url, uuid=uuid)).generators_t.p
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
def test_overnight_expansion_builds_one_period_from_what_exists(
    period, built, multi_period_record, ancestry
):
    result = _run(OvernightCapacityExpansion, {"period": period}, multi_period_record)
    solved = 2050 if period is None else period
    n = to_network(result, select={"period": [solved]})

    assert ancestry(result) == [multi_period_record.uuid, result.uuid]
    assert n.generators.p_nom_opt.to_dict() == pytest.approx(built, abs=1e-3)


def test_overnight_expansion_needs_the_period_it_is_given(multi_period_record):
    with pytest.raises(ValueError, match="no investment period 2045"):
        _run(OvernightCapacityExpansion, {"period": 2045}, multi_period_record)


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


def test_myopic_expansion_never_builds_a_cohort_before_the_first_period(store_record):
    n = _multi_period_network()
    n.add("Generator", "gen-2020", bus="bus", p_nom_extendable=True, build_year=2020, lifetime=40)
    record = store_record(n, "early-cohort")

    result = _run(MyopicCapacityExpansion, {}, record)

    dispatch = to_network(result, select={"period": [2050]}).generators_t.p.sum().to_dict()
    expected = {"gen-2020": 0.0, "gen-2030": 200.0, "gen-2040": 0.0, "gen-2050": 200.0}
    assert dispatch == pytest.approx(expected, abs=1e-3)


def test_dispatch_can_run_against_capacities_another_block_chose(single_period_record):
    expanded = _run(OvernightCapacityExpansion, {}, single_period_record)

    result = _run(
        RollingHorizonDispatch,
        {"capacity_source": expanded, "optimize_config": {"horizon": 12}},
        single_period_record,
    )
    n = to_network(result)

    # Capacities came across as given, so dispatch could not change them.
    assert not n.generators.p_nom_extendable["gen"]
    assert n.generators.p_nom["gen"] == pytest.approx(50.0, rel=1e-3)


@pytest.mark.parametrize("component", ["Generator", "Line", "Transformer"])
def test_dispatch_fixes_the_capacities_its_source_decided(component):
    attr = nominal_attr(component)
    n = _assets(2030, 30.0, component)
    source = _assets(2030, 30.0, component)
    source.c[component].static[attr + "_opt"] = [40.0, 10.0]

    RollingHorizonDispatch.apply_optimised_capacities(n, source)

    static = n.c[component].static
    assert static[attr].to_dict() == {"built": 40.0, "new": 10.0}
    assert not static[attr + "_extendable"].any()


def test_dispatch_can_run_on_its_own(single_period_record, store_record):
    n = to_network(single_period_record)
    n.generators.loc["gen", "p_nom_extendable"] = False
    n.generators.loc["gen", "p_nom"] = 100.0
    record = store_record(n, "fixed")

    result = _run(
        RollingHorizonDispatch,
        {"optimize_config": {"horizon": 12}},
        record,
    )
    assert to_network(result).generators.p_nom["gen"] == pytest.approx(100.0)


def test_a_rolling_horizon_must_move_forward():
    with pytest.raises(Exception, match="overlap"):
        RollingHorizonDispatch.merge_config({"optimize_config": {"horizon": 4, "overlap": 4}}, {})


def test_a_wired_capacity_source_is_checked_like_any_other_setting():
    with pytest.raises(Exception, match="capacity_source"):
        RollingHorizonDispatch.merge_config({}, {"capacity_source": "not-a-record"})


def test_a_capacity_source_can_be_given_by_its_field_name():
    # It also has a friendlier name for display, which must not stop the field itself
    # being set the ordinary way.
    source = {"url": "somewhere", "uuid": "00000000-0000-0000-0000-000000000000"}
    config = RollingHorizonDispatch.merge_config({"capacity_source": source}, {})
    assert config.capacity_source.url == "somewhere"
