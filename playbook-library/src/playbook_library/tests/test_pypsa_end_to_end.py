# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A whole playbook of real blocks, run against a real but tiny network.

This is the end-to-end check: a network file goes in, each block writes a new one
under the run's output prefix, and the last record points at the finished result. The
playbook is the one this library ships, and the network is the one `examples.py`
seeds, so what a contributor runs by hand is what is tested here.
"""

import pytest

pytest.importorskip("pypsa", reason="the PyPSA blocks need PyPSA installed")

from playbook.blocks.core import DataRecord
from playbook.playbooks.yaml_io import playbook_from_doc

from playbook_library.examples import build_example_network
from playbook_library.playbooks import library_playbooks
from playbook_library.pypsa_helpers import to_network

pytestmark = pytest.mark.pypsa


def build_playbook():
    return playbook_from_doc(library_playbooks()["cluster-expand-dispatch"].doc)


@pytest.fixture
def network_record(tmp_path) -> DataRecord:
    path = tmp_path / "start.nc"
    build_example_network().export_to_netcdf(str(path))
    return DataRecord(url=str(path))


CONFIG = {
    "globals": {"expansion_mode": "overnight"},
    "cluster": {"n_hours": 3},
    "expansion_overnight": {},
    "expansion_myopic": {},
    "dispatch": {"optimize_config": {"horizon": 4}},
}


def test_a_playbook_of_real_blocks_runs_from_one_network_to_another(network_record, tmp_path):
    result = build_playbook().run(network_record, CONFIG, output_prefix=str(tmp_path / "run"))

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
