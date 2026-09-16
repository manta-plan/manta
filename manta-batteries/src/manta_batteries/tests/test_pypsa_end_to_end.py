# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""A whole playbook of real blocks, run against a real but tiny network.

This is the end-to-end check: a network file goes in, each block writes a new one,
and the last record points at the finished result.
"""

import pytest

pypsa = pytest.importorskip("pypsa", reason="the PyPSA blocks need PyPSA installed")

import pandas as pd
from manta_blocks.core import DataRecord

from manta_batteries.examples.cluster_expand_dispatch import build_playbook
from manta_batteries.pypsa_helpers import to_network

pytestmark = [pytest.mark.pypsa, pytest.mark.slow]


@pytest.fixture
def network_record(tmp_path) -> DataRecord:
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
    path = tmp_path / "start.nc"
    n.export_to_netcdf(str(path))
    return DataRecord(url=str(path))


CONFIG = {
    "globals": {"expansion_mode": "overnight"},
    "cluster": {"n_hours": 3},
    "expansion_overnight": {},
    "expansion_myopic": {},
    "dispatch": {"optimize_config": {"horizon": 4}},
}


def test_the_example_playbook_is_valid_for_real_blocks():
    build_playbook().validate_playbook(CONFIG)


def test_a_playbook_of_real_blocks_runs_from_one_network_to_another(network_record):
    result = build_playbook().run(network_record, CONFIG)

    # Each block wrote a new file and named it after the one it read, so the final
    # record's name reads as a record of what ran.
    assert result.url.endswith(
        "start-cluster_time-overnight_capacity_expansion-rolling_horizon_dispatch.nc"
    )

    n = to_network(result)
    assert len(n.snapshots) == 8  # clustered down from 24
    # Capacity was chosen by the expansion block and dispatch could not change it.
    assert not n.generators.p_nom_extendable["gen"]
    assert n.generators.p_nom["gen"] == pytest.approx(50.0, rel=1e-3)


def test_the_network_the_playbook_started_from_is_left_alone(network_record):
    build_playbook().run(network_record, CONFIG)
    n = to_network(network_record)
    assert len(n.snapshots) == 24
    assert n.generators.p_nom_extendable["gen"]


def test_the_myopic_branch_needs_investment_periods(network_record):
    from manta_playbooks.validation import PlaybookValidationError

    config = {**CONFIG, "globals": {"expansion_mode": "myopic"}}
    # The myopic block needs investment periods, which this playbook does not start
    # with, so it is refused before anything runs.
    with pytest.raises(PlaybookValidationError, match="investment_period"):
        build_playbook().validate_playbook(config)
