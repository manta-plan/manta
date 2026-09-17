# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""A whole playbook of real blocks, run against a real but tiny network.

This is the end-to-end check: a network file goes in, each block writes a new one
under the run's output prefix, and the last record points at the finished result.
The playbook is the same document Manta ships in `playbooks.library`.
"""

import pytest

pypsa = pytest.importorskip("pypsa", reason="the PyPSA blocks need PyPSA installed")

import pandas as pd

from blocks.core import DataRecord
from blocks.library.pypsa_helpers import to_network
from playbooks.library import library_playbooks
from playbooks.yaml_io import playbook_from_doc

pytestmark = pytest.mark.pypsa


def build_playbook():
    return playbook_from_doc(library_playbooks()["cluster-expand-dispatch"].doc)


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


def test_the_library_playbook_is_valid_for_real_blocks():
    build_playbook().validate_playbook(CONFIG)


def test_a_playbook_of_real_blocks_runs_from_one_network_to_another(
    network_record, tmp_path
):
    result = build_playbook().run(
        network_record, CONFIG, output_prefix=str(tmp_path / "run")
    )

    # Each block wrote a new file under the run prefix, named after its step, so a
    # finished run reads as a folder of the steps that ran.
    assert result.url == str(tmp_path / "run" / "dispatch.nc")
    assert (tmp_path / "run" / "cluster.nc").exists()
    assert (tmp_path / "run" / "expansion_overnight.nc").exists()

    n = to_network(result)
    assert len(n.snapshots) == 8  # clustered down from 24
    # Capacity was chosen by the expansion block and dispatch could not change it.
    assert not n.generators.p_nom_extendable["gen"]
    assert n.generators.p_nom["gen"] == pytest.approx(50.0, rel=1e-3)


def test_the_network_the_playbook_started_from_is_left_alone(network_record, tmp_path):
    build_playbook().run(network_record, CONFIG, output_prefix=str(tmp_path / "run"))
    n = to_network(network_record)
    assert len(n.snapshots) == 24
    assert n.generators.p_nom_extendable["gen"]


def test_the_myopic_branch_needs_investment_periods(network_record):
    from playbooks.validation import PlaybookValidationError

    config = {**CONFIG, "globals": {"expansion_mode": "myopic"}}
    # The myopic block needs investment periods, which this playbook does not start
    # with, so it is refused before anything runs.
    with pytest.raises(PlaybookValidationError, match="investment_period"):
        build_playbook().validate_playbook(config)
