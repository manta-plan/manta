# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A whole playbook of real blocks, run against a real but tiny network.

This is the end-to-end check: a network revision goes in, each block writes a new
revision into the same store, and the last record points at the finished result. The
playbooks are the ones this library ships, and the network and example playbook are the
ones `examples.py` runs, so what a contributor runs by hand is what is tested here.
"""

import json
import shutil
from pathlib import Path
from uuid import UUID

import pytest

pypsa = pytest.importorskip("pypsa", reason="the PyPSA blocks need PyPSA installed")

from playbook.blocks.core import DataRecord, DataRecordError
from playbook.playbooks import Playbook
from playbook.playbooks.yaml_io import playbook_from_doc

from playbook_library.examples import EXAMPLE_PLAYBOOK, build_example_network
from playbook_library.myopic_capacity_expansion import MyopicCapacityExpansion
from playbook_library.overnight_capacity_expansion import OvernightCapacityExpansion
from playbook_library.perfect_capacity_expansion import PerfectCapacityExpansion
from playbook_library.playbooks import library_playbooks
from playbook_library.public_data import download_public_store
from playbook_library.pypsa_helpers import BUILT_COMPONENTS, nominal_attr, to_network

pytestmark = pytest.mark.pypsa


def build_playbook(name: str = EXAMPLE_PLAYBOOK) -> Playbook:
    return playbook_from_doc(library_playbooks()[name].doc)


@pytest.fixture
def network_record(store_record) -> DataRecord:
    return store_record(build_example_network(), "start")


CLUSTER_EXPAND_DISPATCH_CONFIG = {
    "globals": {"expansion_mode": "overnight"},
    "cluster": {"n_hours": 3},
    "expansion_overnight": {},
    "expansion_myopic": {},
    "dispatch": {"optimize_config": {"horizon": 4}},
}


def test_the_example_playbook_runs_from_one_network_to_another(network_record, ancestry):
    result = build_playbook().run(
        network_record, library_playbooks()[EXAMPLE_PLAYBOOK].default_config
    )

    assert result.url == network_record.url
    assert ancestry(result) == [network_record.uuid, result.uuid]
    n = to_network(result)
    assert len(n.snapshots) == 24
    assert n.generators.p_nom_opt["gen"] == pytest.approx(50.0, rel=1e-3)


def test_a_playbook_of_chained_blocks_runs_from_one_network_to_another(network_record, ancestry):
    result = build_playbook("cluster-expand-dispatch").run(
        network_record, CLUSTER_EXPAND_DISPATCH_CONFIG
    )

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
    build_playbook("cluster-expand-dispatch").run(network_record, CLUSTER_EXPAND_DISPATCH_CONFIG)
    n = to_network(network_record)
    assert len(n.snapshots) == 24
    assert n.generators.p_nom_extendable["gen"]


@pytest.mark.parametrize(
    ("url", "uuid"),
    [("missing-store", None), (None, UUID(int=0))],
    ids=["missing-store", "missing-revision"],
)
def test_a_record_pointing_at_nothing_raises_a_datarecord_error(network_record, url, uuid):
    record = DataRecord(
        url=network_record.url + url if url else network_record.url,
        uuid=uuid or network_record.uuid,
    )
    with pytest.raises(DataRecordError, match="No revision"):
        to_network(record)


@pytest.fixture(scope="session")
def bel_store(tmp_path_factory) -> Path:
    return download_public_store("BEL-pre-aggregated", tmp_path_factory.mktemp("bel-download"))


@pytest.fixture
def bel_record(tmp_path, bel_store) -> DataRecord:
    store_dir = tmp_path / "BEL"
    shutil.copytree(bel_store, store_dir)
    manifests = [json.loads(path.read_text()) for path in store_dir.glob("layers/*/manifest.json")]
    [base] = [m["id"] for m in manifests if m["parent"] is None]
    return DataRecord(url=str(store_dir), uuid=UUID(base))


BUILT_CARRIERS = [
    "Generator CCGT",
    "Generator biomass",
    "Generator OCGT",
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
        7406.1, 113.0, 1818.4, 871.0, 1565.0, 21.3, 130.2, 15287.4, 103508.8, 7017.2, 293.8,
        8537.2, 21852.5, 13644.7, 13191293.9, 25409.0,
    ],
    ("overnight2050", 2050): [
        0.0, 0.0, 0.0, 174.2, 0.0, 21.3, 0.0, 12890.4, 103288.4, 0.0, 0.0,
        6139.5, 14591.2, 17694.7, 13046611.8, 23773.4,
    ],
    ("myopic", 2030): [
        6634.2, 113.0, 876.6, 871.0, 1565.0, 0.0, 130.2, 15287.4, 49690.6, 0.0, 293.8,
        0.0, 0.0, 11084.1, 0.1, 25642.3,
    ],
    ("myopic", 2040): [
        3088.5, 0.0, 1342.6, 984.6, 1429.0, 0.0, 0.0, 21825.5, 54054.7, 0.0, 0.0,
        4186.6, 6526.1, 11084.1, 5075397.6, 25642.3,
    ],
    ("myopic", 2050): [
        2213.5, 0.0, 1342.6, 522.5, 0.0, 0.0, 0.0, 24515.2, 61247.2, 0.0, 0.0,
        6227.3, 15107.7, 11084.1, 9157711.1, 25642.3,
    ],
}  # fmt: skip
PYPSA_EUR_OBJECTIVE: dict[tuple[str, int | None], float] = {
    ("perfect", None): 2.0088690824e11,
    ("overnight2050", 2050): 6.8943088274e10,
    ("myopic", 2030): 5.2184445142e10,
    ("myopic", 2040): 2.9012039811e10,
    ("myopic", 2050): 1.9758761984e10,
}


def _built(n: pypsa.Network) -> dict[str, float]:
    totals = {}
    for c in n.components[BUILT_COMPONENTS]:
        if c.empty:
            continue
        active = c.static[c.get_active_assets(n.investment_periods)]
        built = active.groupby("carrier")[nominal_attr(c.name) + "_opt"].sum()
        totals |= built.add_prefix(f"{c.name} ").to_dict()
    return {carrier: totals.pop(carrier, 0.0) for carrier in BUILT_CARRIERS} | totals


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
    assert root == bel_record.uuid
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
