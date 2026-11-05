"""The record catalogue and the `manta` views against the 30 October
BEL-pre-aggregated, perfect foresight, in `data/records` (the server's local
root; see the README). The store opens as the server opens it: on demand,
after the lockdown. Counts and changes as the modeller describes them.

`RECORD_TEST_ROOT=s3://…` also runs the remote test against that root, with
the AWS_* environment (server/.env)."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest
from datarecord import Workspace

from app import stores
from app.quack import DISABLED_FILESYSTEMS
from app.stores import Catalogue, configure

ROOT = Path(__file__).resolve().parents[1] / "data/records"
# A plain record (no revisions) of the 30 October records, if present.
PLAIN = Path(__file__).resolve().parents[1] / "data/records/BEL-pre-aggregated"
STORE = "BEL-pre-aggregated-perfect"
BASE = "bel_pre_aggregated_perfect__inputs"
PATCH = "bel_pre_aggregated_perfect__patch"

pytestmark = pytest.mark.skipif(not (ROOT / STORE).is_dir(), reason="sample record not present")


def open_catalogue(root: str) -> tuple[Workspace, Catalogue]:
    """A catalogue locked down as the server locks down (quack.serve), before
    any store opens."""
    ws = Workspace()
    configure(ws.con)
    catalogue = Catalogue(ws, root)
    ws.con.execute(f"SET disabled_filesystems = '{','.join(DISABLED_FILESYSTEMS)}'")
    ws.con.execute("SET lock_configuration = true")
    return ws, catalogue


@pytest.fixture(scope="module")
def opened():
    ws, catalogue = open_catalogue(str(ROOT))
    catalogue.open(STORE)
    yield ws.con, catalogue
    ws.close()


@pytest.fixture(scope="module")
def con(opened):
    return opened[0]


def rows(con, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


def test_listing(tmp_path):
    ws, catalogue = open_catalogue(str(tmp_path))
    try:
        assert catalogue.stores() == {}
        link_store(tmp_path)
        # The listing is kept for a while, then sees the new store.
        assert catalogue.stores() == {}
        catalogue._listed -= stores.LISTING_TTL_S + 1
        assert list(catalogue.stores()) == [STORE]
        assert not catalogue.is_open(STORE)
    finally:
        ws.close()


def test_summary(opened):
    _, catalogue = opened
    assert STORE in catalogue.stores()
    listed = catalogue.get(STORE).as_json()
    assert listed["label"] == "Belgium, 5 regions: perfect foresight"
    assert listed["revisions"] == ["inputs", "results", "patch", "patch_results"]
    assert listed["files"] == 752 and listed["size"] > 30_000_000


def test_open(opened):
    _, catalogue = opened
    record = catalogue.open(STORE).as_json()
    assert record["defaultScenario"] == "inputs"
    # Scenarios get a catalog; run results don't, for now.
    assert {r["name"]: r["catalog"] for r in record["revisions"]} == {
        "inputs": BASE, "results": None, "patch": PATCH, "patch_results": None,
    }
    assert "p_max_pu" in record["views"]["attributes"]
    with pytest.raises(KeyError):
        catalogue.open("nope")


def test_catalogs_alike(con):
    def names(catalog: str) -> set[tuple]:
        return set(rows(con, f"SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name = '{catalog}' "
                             f"UNION ALL SELECT schema_name, view_name FROM duckdb_views() WHERE database_name = '{catalog}' "
                             "AND NOT internal"))
    assert names(BASE) == names(PATCH)
    assert ("manta", "scenario_changes") in names(BASE)


def test_locations(con):
    # 5 regions, each an AC bus with an H2 bus at the same location.
    assert rows(con, f"SELECT count(*), sum(buses) FROM {BASE}.manta.locations") == [(5, 10)]
    assert rows(con, f"SELECT DISTINCT carriers FROM {BASE}.manta.locations") == [(["AC", "H2"],)]
    assert rows(con, f"SELECT count(*) FROM {BASE}.manta.bus_location WHERE virtual") == [(0,)]


def test_no_zones_or_regions(con):
    # The network is aggregated already (no busmap_*), and holds no shapes.
    assert rows(con, f"SELECT count(*) FROM {BASE}.manta.location_zones") == [(0,)]
    assert rows(con, f"SELECT count(*) FROM {BASE}.manta.regions") == [(0,)]


def test_branches(con):
    by_scope = rows(con, f"SELECT ctype, scope, count(DISTINCT entity) FROM {BASE}.manta.branches GROUP BY ALL ORDER BY 1")
    assert by_scope == [("Line", "between", 6), ("Link", "within", 30)]
    links = rows(con, f"SELECT carrier, count(*) FROM {BASE}.manta.branches WHERE ctype = 'Link' GROUP BY ALL ORDER BY 1")
    assert links == [("H2 Electrolysis", 15), ("H2 Fuel Cell", 15)]


def test_attached(con):
    counts = dict(rows(con, f"SELECT ctype, count(*) FROM {BASE}.manta.attached GROUP BY ALL"))
    assert counts == {"Generator": 68, "Load": 5, "Store": 15, "StorageUnit": 5}


def test_attribute_summary(con):
    # Inputs only: no result attributes.
    assert rows(con, f"SELECT count(*) FROM {BASE}.manta.attribute_summary WHERE attribute = 'p_nom_opt'") == [(0,)]
    # p_max_pu varies for every entity that has it: series only, no constants.
    assert rows(con, f"""SELECT count(*), sum(series_rows), count(constant) FROM {BASE}.manta.attribute_summary
                         WHERE attribute = 'p_max_pu'""") == [(54, 118260, 0)]
    # Connection attributes are per connection: a link's efficiency per output bus.
    assert rows(con, f"SELECT count(*), count(bus) FROM {BASE}.manta.attribute_summary WHERE attribute = 'efficiency'") == [(98, 98)]
    used = {a for (a,) in rows(con, f"SELECT attribute FROM {BASE}.manta.ctype_attributes WHERE ctype = 'Generator'")}
    assert {"p_nom", "p_max_pu", "capital_cost"} <= used


def test_revisions(con):
    revisions = rows(con, f"SELECT name, parent, kind, label, catalog FROM {BASE}.manta.revisions ORDER BY name")
    assert revisions == [
        ("inputs", None, "scenario", "Base case", BASE),
        ("patch", "inputs", "scenario", "Wind and solar stress test", PATCH),
        ("patch_results", "patch", "result", "Wind and solar stress test, solved", None),
        ("results", "inputs", "result", "Base case, solved", None),
    ]
    # The same table in every catalog of the record.
    assert rows(con, f"FROM {PATCH}.manta.revisions EXCEPT FROM {BASE}.manta.revisions") == []


def test_scenario_changes(con):
    changes = rows(
        con,
        f"""SELECT attribute, dim, count(*), sum(series_rows), round(median(ratio), 2) FROM {BASE}.manta.scenario_changes
            WHERE scenario = 'patch' GROUP BY ALL ORDER BY 1""",
    )
    # As the sample's README says: offshore wind cost ×1.3, onshore wind
    # potential ×0.5, solar availability ×0.9.
    assert changes == [
        ("capital_cost", "entity", 9, 0, 1.3),
        ("nom_max_onwind_2030", "bus", 5, 0, 0.5),
        ("nom_max_onwind_2040", "bus", 5, 0, 0.5),
        ("nom_max_onwind_2050", "bus", 5, 0, 0.5),
        ("p_max_pu", "entity", 30, 55470, 0.9),
        ("p_nom_max", "entity", 15, 0, 0.5),
    ]
    # The layer restates all 10 buses' limits; only the 5 AC buses changed.
    assert rows(con, f"""SELECT DISTINCT p.carrier FROM {BASE}.manta.scenario_changes c
                         JOIN {BASE}.properties.bus p ON p.bus = c.label WHERE c.dim = 'bus'""") == [("AC",)]
    # The base case changes nothing: it has no parent.
    assert rows(con, f"SELECT count(*) FROM {BASE}.manta.scenario_changes WHERE scenario = 'inputs'") == [(0,)]


def test_each_catalog_reads_its_own_values(con):
    # Each catalog's summary is its own revision's: offshore wind ×1.3 in patch.
    ratio = rows(con, f"""
        SELECT count(*), round(median(TRY_CAST(p.constant AS DOUBLE) / TRY_CAST(b.constant AS DOUBLE)), 2)
        FROM {PATCH}.manta.attribute_summary p JOIN {BASE}.manta.attribute_summary b
          ON (b.attribute, b.dim, b.label) = (p.attribute, p.dim, p.label) AND b.bus IS NOT DISTINCT FROM p.bus
        WHERE p.attribute = 'capital_cost' AND p.constant IS DISTINCT FROM b.constant""")
    assert ratio == [(9, 1.3)]
    # Views too: p_max_pu's series is lower in patch.
    assert rows(con, f"SELECT sum(TRY_CAST(value AS DOUBLE)) < (SELECT sum(TRY_CAST(value AS DOUBLE)) FROM {BASE}.attributes.p_max_pu) "
                     f"FROM {PATCH}.attributes.p_max_pu") == [(True,)]


def link_store(root: Path) -> None:
    """The sample store under `root`, without its labels file."""
    (root / STORE).symlink_to(ROOT / STORE, target_is_directory=True)
    (root / f"{STORE}.json").write_text((ROOT / f"{STORE}.json").read_text())


def test_opens_once(tmp_path):
    link_store(tmp_path)
    ws, catalogue = open_catalogue(str(tmp_path))
    try:
        results = []
        threads = [threading.Thread(target=lambda: results.append(catalogue.open(STORE))) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(results) == 3 and all(r is results[0] for r in results)
        assert rows(ws.con, "SELECT count(*) FROM duckdb_databases() WHERE database_name LIKE 'bel_pre_aggregated_perfect__%'") == [(2,)]
    finally:
        ws.close()


def test_labels_are_optional(tmp_path):
    link_store(tmp_path)
    ws, catalogue = open_catalogue(str(tmp_path))
    try:
        labels = {r.name: r.label for r in catalogue.open(STORE).revisions}
        assert labels == {"inputs": "Base case", "results": "results", "patch": "patch", "patch_results": "patch_results"}
    finally:
        ws.close()


@pytest.mark.skipif(not PLAIN.is_dir(), reason="plain record not present")
def test_plain_record(tmp_path):
    (tmp_path / PLAIN.name).symlink_to(PLAIN, target_is_directory=True)
    ws, catalogue = open_catalogue(str(tmp_path))
    try:
        summary = catalogue.get(PLAIN.name)
        assert summary.plain and summary.revisions == ["inputs"]
        record = catalogue.open(PLAIN.name)
        assert [(r.name, r.parent, r.kind, r.catalog) for r in record.revisions] == [
            ("inputs", None, "scenario", "bel_pre_aggregated__inputs")
        ]
        assert rows(ws.con, "SELECT count(*), sum(buses) FROM bel_pre_aggregated__inputs.manta.locations") == [(5, 10)]
        assert rows(ws.con, "SELECT count(*) FROM bel_pre_aggregated__inputs.manta.scenario_changes") == [(0,)]
    finally:
        ws.close()


@pytest.mark.skipif(not os.environ.get("RECORD_TEST_ROOT"), reason="RECORD_TEST_ROOT not set")
def test_remote_root():
    ws, catalogue = open_catalogue(os.environ["RECORD_TEST_ROOT"])
    try:
        assert STORE in catalogue.stores()
        record = catalogue.open(STORE)
        assert record.default_scenario == "inputs"
        assert rows(ws.con, f"SELECT count(*) FROM {BASE}.manta.scenario_changes WHERE scenario = 'patch'") == [(69,)]
    finally:
        ws.close()
