# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""The blocks that ship with Manta, run against a real but tiny network.

Each test builds a network small enough to solve in a moment, writes it out, and runs
a block on it. A block reads a network file and writes a new one, so what is checked
is that a usable network comes out the other side.
"""

import pytest

pypsa = pytest.importorskip("pypsa", reason="the PyPSA blocks need PyPSA installed")

import pandas as pd
from manta_blocks.core import DataRecord

from manta_batteries.myopic_capacity_expansion import MyopicCapacityExpansion
from manta_batteries.overnight_capacity_expansion import OvernightCapacityExpansion
from manta_batteries.pypsa_helpers import to_network
from manta_batteries.rolling_horizon_dispatch import RollingHorizonDispatch
from manta_batteries.time_cluster import ClusterTime

pytestmark = [pytest.mark.pypsa, pytest.mark.slow]


def _write(n: pypsa.Network, path) -> DataRecord:
    n.export_to_netcdf(str(path))
    return DataRecord(url=str(path))


def _run(block_cls, config: dict, record: DataRecord) -> DataRecord:
    """Run a block the way a playbook would, as a Prefect flow."""
    return block_cls.as_flow(config)(record)


@pytest.fixture
def single_period_record(tmp_path) -> DataRecord:
    """One bus, one generator that can be built, and a day of demand."""
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2030-01-01", periods=24, freq="h"))
    n.add("Bus", "bus")
    n.add(
        "Generator",
        "gen",
        bus="bus",
        p_nom_extendable=True,
        capital_cost=100.0,
        marginal_cost=10.0,
    )
    n.add("Load", "load", bus="bus", p_set=50.0)
    return _write(n, tmp_path / "base.nc")


@pytest.fixture
def multi_period_record(tmp_path) -> DataRecord:
    """The same idea, but split into two investment periods."""
    n = pypsa.Network()
    periods = [2030, 2040]
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
            capital_cost=100.0,
            marginal_cost=10.0,
        )
    n.add("Load", "load", bus="bus", p_set=50.0)
    return _write(n, tmp_path / "periods.nc")


def test_a_block_writes_a_new_network_beside_the_one_it_read(single_period_record):
    result = _run(ClusterTime, {"n_hours": 3}, single_period_record)

    assert result.url != single_period_record.url
    assert result.url.endswith("base-cluster_time.nc")
    to_network(result)  # raises if what was written is not a network


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


def test_myopic_expansion_decides_one_period_at_a_time(multi_period_record):
    result = _run(MyopicCapacityExpansion, {}, multi_period_record)
    n = to_network(result)

    assert result.url.endswith("periods-myopic_capacity_expansion.nc")
    # Each period's own generator has been sized, and fixed once its period was done.
    assert n.generators.p_nom["gen-2030"] > 0
    assert not n.generators.p_nom_extendable["gen-2030"]


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


def test_dispatch_can_run_on_its_own(single_period_record, tmp_path):
    n = to_network(single_period_record)
    n.generators.loc["gen", "p_nom_extendable"] = False
    n.generators.loc["gen", "p_nom"] = 100.0
    record = _write(n, tmp_path / "fixed.nc")

    result = _run(RollingHorizonDispatch, {"optimize_config": {"horizon": 12}}, record)
    assert to_network(result).generators.p_nom["gen"] == pytest.approx(100.0)


def test_a_wired_capacity_source_is_checked_like_any_other_setting():
    with pytest.raises(Exception, match="capacity_source"):
        RollingHorizonDispatch.merge_config({}, {"capacity_source": "not-a-record"})


def test_a_capacity_source_can_be_given_by_its_field_name():
    # It also has a friendlier name for display, which must not stop the field itself
    # being set the ordinary way.
    config = RollingHorizonDispatch.merge_config(
        {"capacity_source": {"url": "somewhere.nc"}}, {}
    )
    assert config.capacity_source.url == "somewhere.nc"
