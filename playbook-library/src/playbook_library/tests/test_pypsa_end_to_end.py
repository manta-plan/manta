# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A whole playbook of real blocks, run against a real but tiny network.

This is the end-to-end check: a network revision goes in, each block writes a new
revision into the same store, and the last record points at the finished result. The
playbook is the one this library ships, and the network is the one `examples.py`
seeds, so what a contributor runs by hand is what is tested here.
"""

import shutil
from pathlib import Path
from uuid import UUID

import pytest

pypsa = pytest.importorskip("pypsa", reason="the PyPSA blocks need PyPSA installed")

from playbook.blocks.core import DataRecord
from playbook.playbooks.yaml_io import playbook_from_doc

from playbook_library.examples import build_example_network
from playbook_library.myopic_capacity_expansion import MyopicCapacityExpansion
from playbook_library.overnight_capacity_expansion import OvernightCapacityExpansion
from playbook_library.perfect_capacity_expansion import PerfectCapacityExpansion
from playbook_library.playbooks import library_playbooks
from playbook_library.pypsa_helpers import BUILT_COMPONENTS, nominal_attr, to_network

pytestmark = pytest.mark.pypsa


def build_playbook():
    return playbook_from_doc(library_playbooks()["cluster-expand-dispatch"].doc)


@pytest.fixture
def network_record(store_record) -> DataRecord:
    return store_record(build_example_network(), "start")


CONFIG = {
    "globals": {"expansion_mode": "overnight"},
    "cluster": {"n_hours": 3},
    "expansion_overnight": {},
    "expansion_myopic": {},
    "dispatch": {"optimize_config": {"horizon": 4}},
}


def test_a_playbook_of_real_blocks_runs_from_one_network_to_another(network_record, ancestry):
    result = build_playbook().run(network_record, CONFIG)

    assert result.url == network_record.url
    lineage = ancestry(result)
    assert len(lineage) == 4
    assert lineage[0] == network_record.uuid

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


BEL_STORE = Path(__file__).parent / "data" / "BEL-pre-aggregated"
BEL_ROOT = UUID("3de02051-8918-45ab-a61b-980b3da170c4")


@pytest.fixture
def bel_record(tmp_path) -> DataRecord:
    store_dir = tmp_path / "BEL"
    shutil.copytree(BEL_STORE, store_dir)
    return DataRecord(url=str(store_dir), uuid=BEL_ROOT)


BUILT_CARRIERS = [
    "Generator CCGT",
    "Generator biomass",
    "Generator offwind-ac",
    "Generator offwind-dc",
    "Generator offwind-float",
    "Generator oil",
    "Generator onwind",
    "Generator solar",
    "Generator solar-hsat",
    "Generator waste",
    "Link H2 Electrolysis",
    "Link H2 Fuel Cell",
    "StorageUnit battery",
    "Store H2",
    "Line AC",
]
PYPSA_EUR_BUILT: dict[tuple[str, int | None], list[float]] = {
    ("perfect", None): [
        7359.2, 113.0, 871.0, 871.2, 878.1, 130.2, 15287.4, 73882.7, 0.0, 293.8,
        6264.9, 20009.1, 12727.1, 10322859.3, 25670.6,
    ],
    ("overnight2050", 2050): [
        6634.2, 113.0, 871.0, 871.2, 1742.2, 130.2, 15287.4, 71464.9, 0.0, 293.8,
        6677.9, 14479.2, 10289.6, 9643619.4, 25607.4,
    ],
    ("myopic", 2030): [
        7432.4, 113.0, 871.0, 871.2, 0.0, 130.2, 15287.4, 52805.8, 0.0, 293.8,
        0.0, 0.0, 11987.9, 0.1, 25490.1,
    ],
    ("myopic", 2040): [
        7432.4, 113.0, 1033.5, 1742.5, 0.0, 130.2, 20815.8, 52805.8, 0.0, 293.8,
        3558.8, 5891.0, 11987.9, 4724087.0, 25490.1,
    ],
    ("myopic", 2050): [
        7432.4, 113.0, 1033.5, 1742.5, 0.0, 130.2, 21412.9, 52812.7, 0.0, 293.8,
        5434.7, 14931.3, 11987.9, 8472659.7, 25490.1,
    ],
}  # fmt: skip
PYPSA_EUR_OBJECTIVE: dict[tuple[str, int | None], float] = {
    ("perfect", None): 2.2021688830e11,
    ("overnight2050", 2050): 6.4785309730e10,
    ("myopic", 2030): 6.8140855875e10,
    ("myopic", 2040): 2.4082960130e10,
    ("myopic", 2050): 1.4424425926e10,
}


def _built(n: pypsa.Network) -> dict[str, float]:
    totals = {}
    for c in n.components[BUILT_COMPONENTS]:
        if c.empty:
            continue
        active = c.static[c.get_active_assets(n.investment_periods)]
        built = active.groupby("carrier")[nominal_attr(c.name) + "_opt"].sum()
        totals |= built.add_prefix(f"{c.name} ").to_dict()
    return totals


@pytest.mark.slow
@pytest.mark.parametrize(
    ("block_cls", "mode", "periods", "dispatched"),
    [
        pytest.param(
            PerfectCapacityExpansion,
            "perfect",
            [None],
            [2030, 2040, 2050],
            id="pypsa-eur-test-elec-preaggregated-perfect-datarecords-perfect",
        ),
        pytest.param(
            OvernightCapacityExpansion,
            "overnight2050",
            [2050],
            [2050],
            id="pypsa-eur-test-elec-preaggregated-perfect-datarecords-overnight2050",
        ),
        pytest.param(
            MyopicCapacityExpansion,
            "myopic",
            [2030, 2040, 2050],
            [2030, 2040, 2050],
            id="pypsa-eur-test-elec-preaggregated-perfect-datarecords-myopic",
        ),
    ],
)
def test_expansion_of_a_real_network_matches_the_pypsa_eur_reference(
    block_cls, mode, periods, dispatched, bel_record, ancestry
):
    objectives = []

    class Recorded(block_cls):
        def optimize(self, n: pypsa.Network) -> pypsa.Network:
            solved = super().optimize(n)
            objectives.append(solved.objective)
            return solved

    result = Recorded({}).run(bel_record)
    root, *revisions = ancestry(result)

    assert result.url == bel_record.url
    assert root == BEL_ROOT
    assert revisions[-1] == result.uuid
    expected = [PYPSA_EUR_OBJECTIVE[mode, period] for period in periods]
    assert objectives == pytest.approx(expected, rel=1e-5)
    for uuid, period in zip(revisions, periods, strict=True):
        select = None if period is None else {"period": [period]}
        n = to_network(DataRecord(url=result.url, uuid=uuid), select=select)
        built = dict(zip(BUILT_CARRIERS, PYPSA_EUR_BUILT[mode, period], strict=True))
        assert _built(n) == pytest.approx(built, rel=1e-3, abs=1.0)

    n = to_network(result)
    assert list(n.investment_periods) == [2030, 2040, 2050]
    dispatch = n.c.generators.dynamic.p.sum(axis=1).groupby(level="period").sum()
    assert list(dispatch.index[dispatch > 0]) == dispatched
