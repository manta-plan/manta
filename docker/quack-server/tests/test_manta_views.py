"""The record catalogue and the `manta` views against the 11 November
BEL-pre-aggregated combined store (inputs, the stress test, and three run
types solved for each), in `data/records` (the server's local root; see the
README). The store opens as the server opens it: on demand,
after the lockdown. Counts and changes as the modeller describes them.

`RECORD_TEST_ROOT=s3://…` also runs the remote test against that root, with
the AWS_* environment (server/.env)."""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import threading
from pathlib import Path

import pytest
from datarecord import Workspace

from app import stores
from app.quack import DISABLED_FILESYSTEMS
from app.stores import Catalogue, configure

ROOT = Path(__file__).resolve().parents[1] / "data/records"
# A plain record (a folder with manifest.json, no revisions), if present.
PLAIN = Path(__file__).resolve().parents[1] / "data/records/BEL-pre-aggregated-plain"
STORE = "BEL-pre-aggregated-incl-patches-incl-results"
BASE = "bel_pre_aggregated_incl_patches_incl_results__inputs"
PATCH = "bel_pre_aggregated_incl_patches_incl_results__patch"
RESULTS = "bel_pre_aggregated_incl_patches_incl_results__myopic"
RESULT_NAMES = ["perfect", "patch/perfect", "myopic", "patch/myopic", "overnight2050", "patch/overnight2050"]

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
    # No labels file: the store's own name.
    assert listed["label"] == STORE
    assert listed["revisions"] == ["inputs", "patch", *RESULT_NAMES]
    assert listed["files"] > 400 and listed["size"] > 10_000_000


def test_open(opened):
    _, catalogue = opened
    record = catalogue.open(STORE).as_json()
    assert record["defaultScenario"] == "inputs"
    # Every revision has a catalog; only scenarios are attached on opening.
    assert {r["name"]: (r["catalog"], r["open"]) for r in record["revisions"]} == {
        "inputs": (BASE, True),
        "patch": (PATCH, True),
        **{name: (f"bel_pre_aggregated_incl_patches_incl_results__{name.replace('/', '_')}", False) for name in RESULT_NAMES},
    }
    results = {r["name"]: r["results"] for r in record["revisions"]}
    assert results["inputs"] == [] and results["patch"] == []
    assert {"p", "p_nom_opt", "marginal_price"} <= set(results["myopic"])
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


def test_no_zones(con):
    # The network is aggregated already: no busmap_*.
    assert rows(con, f"SELECT count(*) FROM {BASE}.manta.location_zones") == [(0,)]


def test_regions(con):
    # From the AC buses' shape properties: one onshore region each, and an
    # offshore one for the coastal region.
    regions = rows(con, f"SELECT component, count(*), count(DISTINCT location) FROM {BASE}.manta.regions GROUP BY ALL ORDER BY 1")
    assert regions == [("offshore", 1, 1), ("onshore", 5, 5)]
    assert rows(con, f"SELECT entity, bus FROM {BASE}.manta.regions WHERE component = 'offshore'") == [("BE0 0AC offshore", "BE0 0AC")]
    assert rows(con, f"SELECT count(*) FROM {BASE}.manta.regions WHERE wkt NOT SIMILAR TO '(MULTI)?POLYGON.*'") == [(0,)]


def test_branches(con):
    by_scope = rows(con, f"SELECT ctype, scope, count(DISTINCT entity) FROM {BASE}.manta.branches GROUP BY ALL ORDER BY 1")
    assert by_scope == [("Line", "between", 6), ("Link", "within", 30)]
    links = rows(con, f"SELECT carrier, count(*) FROM {BASE}.manta.branches WHERE ctype = 'Link' GROUP BY ALL ORDER BY 1")
    assert links == [("H2 Electrolysis", 15), ("H2 Fuel Cell", 15)]


def test_attached(con):
    counts = dict(rows(con, f"SELECT ctype, count(*) FROM {BASE}.manta.attached GROUP BY ALL"))
    # The land-use limits are global constraints at their bus.
    assert counts == {"Generator": 128, "GlobalConstraint": 54, "Load": 5, "Store": 15, "StorageUnit": 5}


def test_attribute_summary(con):
    # Inputs only: no result attributes.
    assert rows(con, f"SELECT count(*) FROM {BASE}.manta.attribute_summary WHERE attribute = 'p_nom_opt'") == [(0,)]
    # p_max_pu varies for every entity that has it: series only, no constants.
    assert rows(con, f"""SELECT count(*), sum(series_rows), count(constant) FROM {BASE}.manta.attribute_summary
                         WHERE attribute = 'p_max_pu'""") == [(83, 181770, 0)]
    # Connection attributes are per connection: a link's efficiency per output bus.
    assert rows(con, f"SELECT count(*), count(bus) FROM {BASE}.manta.attribute_summary WHERE attribute = 'efficiency'") == [(158, 158)]
    used = {a for (a,) in rows(con, f"SELECT attribute FROM {BASE}.manta.ctype_attributes WHERE ctype = 'Generator'")}
    assert {"p_nom", "p_max_pu", "capital_cost"} <= used


def test_revisions(con):
    revisions = rows(con, f"SELECT name, parent, kind, label FROM {BASE}.manta.revisions WHERE name IN ('inputs', 'patch', 'myopic', 'patch/myopic') ORDER BY name")
    assert revisions == [
        ("inputs", None, "scenario", "Base case"),
        ("myopic", "inputs", "result", "myopic"),
        ("patch", "inputs", "scenario", "patch"),
        ("patch/myopic", "patch", "result", "patch/myopic"),
    ]
    assert rows(con, f"SELECT kind, count(*) FROM {BASE}.manta.revisions GROUP BY ALL ORDER BY 1") == [("result", 6), ("scenario", 2)]
    # The same table in every catalog of the record.
    assert rows(con, f"FROM {PATCH}.manta.revisions EXCEPT FROM {BASE}.manta.revisions") == []


def test_scenario_changes(con):
    changes = rows(
        con,
        f"""SELECT attribute, dim, count(*), sum(series_rows), round(median(ratio), 2) FROM {BASE}.manta.scenario_changes
            WHERE scenario = 'patch' GROUP BY ALL ORDER BY 1""",
    )
    # As the store's README says: offshore wind cost ×1.3, onshore wind
    # potential ×0.5 (generators' p_nom_max and the land-use limits'
    # constant), solar availability ×0.9.
    assert changes == [
        ("capital_cost", "entity", 13, 0, 1.3),
        ("constant", "entity", 15, 0, 0.5),
        ("p_max_pu", "entity", 40, 70416, 0.9),
        ("p_nom_max", "entity", 15, 0, 0.5),
    ]
    assert rows(con, f"""SELECT DISTINCT e.ctype FROM {BASE}.manta.scenario_changes c
                         JOIN {BASE}.properties.entity e ON e.entity = c.label WHERE c.attribute = 'constant'""") == [("GlobalConstraint",)]
    # The base case changes nothing: it has no parent.
    assert rows(con, f"SELECT count(*) FROM {BASE}.manta.scenario_changes WHERE scenario = 'inputs'") == [(0,)]


def test_each_catalog_reads_its_own_values(con):
    # Each catalog's summary is its own revision's: offshore wind ×1.3 in patch.
    ratio = rows(con, f"""
        SELECT count(*), round(median(TRY_CAST(p.constant AS DOUBLE) / TRY_CAST(b.constant AS DOUBLE)), 2)
        FROM {PATCH}.manta.attribute_summary p JOIN {BASE}.manta.attribute_summary b
          ON (b.attribute, b.dim, b.label) = (p.attribute, p.dim, p.label) AND b.bus IS NOT DISTINCT FROM p.bus
        WHERE p.attribute = 'capital_cost' AND p.constant IS DISTINCT FROM b.constant""")
    assert ratio == [(13, 1.3)]
    # Views too: p_max_pu's series is lower in patch.
    assert rows(con, f"SELECT sum(TRY_CAST(value AS DOUBLE)) < (SELECT sum(TRY_CAST(value AS DOUBLE)) FROM {BASE}.attributes.p_max_pu) "
                     f"FROM {PATCH}.attributes.p_max_pu") == [(True,)]


def test_open_run_result(opened):
    con, catalogue = opened
    assert rows(con, f"SELECT count(*) FROM duckdb_databases() WHERE database_name = '{RESULTS}'") == [(0,)]
    store = catalogue.open_revision(STORE, "myopic")
    assert next(r for r in store.revisions if r.name == "myopic").open
    # Its catalog is like a scenario's, with the result attributes too.
    assert rows(con, f"SELECT count(*) FROM {RESULTS}.manta.attribute_summary WHERE attribute = 'p_nom_opt'") != [(0,)]
    assert rows(con, f"SELECT count(*) FROM {RESULTS}.manta.locations") == [(5,)]
    assert rows(con, f"FROM {RESULTS}.manta.revisions EXCEPT FROM {BASE}.manta.revisions") == []
    assert rows(con, f"SELECT count(*) FROM {RESULTS}.attributes.p") == [(492750,)]
    assert catalogue.open_revision(STORE, "myopic") is store
    with pytest.raises(KeyError):
        catalogue.open_revision(STORE, "nope")


def link_store(root: Path) -> None:
    """The sample store under `root`."""
    (root / STORE).symlink_to(ROOT / STORE, target_is_directory=True)


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
        assert rows(ws.con, "SELECT count(*) FROM duckdb_databases() WHERE database_name LIKE 'bel_pre_aggregated_incl_patches_incl_results__%'") == [(2,)]
    finally:
        ws.close()


def test_labels_are_optional(opened):
    _, catalogue = opened
    labels = {r.name: r.label for r in catalogue.open(STORE).revisions}
    assert labels == {"inputs": "Base case", "patch": "patch", **{name: name for name in RESULT_NAMES}}


def test_labels_beside_the_store(tmp_path):
    link_store(tmp_path)
    (tmp_path / f"{STORE}.labels.json").write_text(json.dumps({
        "_store": {"name": "Belgium, 5 regions"},
        "patch": {"name": "Wind and solar stress test"},
        "patch/myopic": {"name": "Stress test, myopic", "kind": "result"},
    }))
    ws, catalogue = open_catalogue(str(tmp_path))
    try:
        assert catalogue.get(STORE).label == "Belgium, 5 regions"
        labels = {r.name: r.label for r in catalogue.open(STORE).revisions}
        assert labels["patch"] == "Wind and solar stress test" and labels["patch/myopic"] == "Stress test, myopic"
        assert labels["myopic"] == "myopic"
    finally:
        ws.close()


def test_scenario_on_a_run_result(tmp_path):
    # `patch/overnight2050` relabelled a scenario: its parent, `patch`, is
    # relabelled a run result. Its changes are read against that result,
    # whose catalog is attached when the store opens, as the scenarios' are.
    link_store(tmp_path)
    (tmp_path / f"{STORE}.labels.json").write_text(json.dumps({
        "patch": {"kind": "result"},
        "patch/overnight2050": {"kind": "scenario"},
    }))
    ws, catalogue = open_catalogue(str(tmp_path))
    try:
        record = catalogue.open(STORE)
        opened = {r.name for r in record.revisions if r.open}
        assert opened == {"inputs", "patch", "patch/overnight2050"}
        changed = rows(ws.con, f"SELECT DISTINCT scenario FROM {BASE}.manta.scenario_changes ORDER BY 1")
        assert changed == [("patch/overnight2050",)]
        assert rows(ws.con, f"SELECT count(*) > 0 FROM {BASE}.manta.scenario_changes") == [(True,)]
    finally:
        ws.close()


def test_files_endpoint(opened):
    from types import SimpleNamespace

    from app.main import record_files

    _, catalogue = opened
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(catalogue=catalogue)))
    found = record_files(STORE, request)
    names = json.loads((ROOT / STORE / "revisions.json").read_text())
    assert found["revisions"] == names
    assert set(found["layers"]) == set(names.values())
    assert all("schema" not in m and "files" in m for m in found["layers"].values())
    assert "p_nom_opt" in found["schema"]["attributes"]
    perfect = found["layers"][names["perfect"]]
    assert perfect["parent"] == names["inputs"] and "p_nom_opt" in perfect["files"]["attributes"]


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


class FakeS3:
    """Copies from the local root, as boto3's download_file would from the
    bucket; counts the copies."""

    def __init__(self) -> None:
        self.copied: list[str] = []

    def download_file(self, bucket: str, key: str, path: str) -> None:
        self.copied.append(key)
        shutil.copyfile(ROOT / key, path)


def test_copy_to_disk(tmp_path):
    ws, catalogue = open_catalogue(str(ROOT))
    # As for a bucket root, with the bucket faked.
    s3 = FakeS3()
    catalogue.remote, catalogue.cache = True, tmp_path
    catalogue._s3 = lambda: (s3, "bucket", "")
    try:
        record = catalogue.open(STORE)
        summary = catalogue.get(STORE)
        # Layer data only of the layers the named revisions read (here, every
        # layer is named); every layer's manifest, to find them.
        named = set(json.loads((ROOT / STORE / "revisions.json").read_text()).values())
        data = {f.split("/")[2] for f in s3.copied if f.split("/")[1] == "layers" and f.count("/") > 3}
        assert data == named
        assert all((tmp_path / key).is_file() for key in s3.copied)
        # Opened from the copy, and its run results too.
        assert record.default_scenario == "inputs"
        assert rows(ws.con, f"SELECT count(*) FROM {PATCH}.manta.scenario_changes WHERE scenario = 'patch'") == [(83,)]
        catalogue.open_revision(STORE, "myopic")
        assert rows(ws.con, f"SELECT count(*) > 0 FROM {RESULTS}.attributes.p_nom_opt") == [(True,)]
        # Layer data copied once isn't copied again; the small files (names,
        # manifests), which can change in place, are.
        copied = len(s3.copied)
        catalogue._download(summary, json.loads((ROOT / STORE / "revisions.json").read_text()))
        again = s3.copied[copied:]
        assert again and all(not (k.startswith(f"{STORE}/layers/") and k.count("/") > 3) for k in again)
        assert f"{STORE}/revisions.json" in again
    finally:
        ws.close()


def test_copy_stays_in_the_cache(tmp_path):
    ws, catalogue = open_catalogue(str(ROOT))
    s3 = FakeS3()
    catalogue.remote, catalogue.cache = True, tmp_path / "cache"
    catalogue._s3 = lambda: (s3, "bucket", "")
    try:
        summary = catalogue.get(STORE)
        planted = stores.StoreFile("../../escaped.json", 2, summary.files[0].modified)
        with pytest.raises(ValueError, match="outside the store"):
            catalogue._download(dataclasses.replace(summary, files=[planted, *summary.files]), {})
        assert not (tmp_path / "escaped.json").exists() and not s3.copied
    finally:
        ws.close()


@pytest.mark.skipif(not os.environ.get("RECORD_TEST_ROOT"), reason="RECORD_TEST_ROOT not set")
def test_remote_root():
    ws, catalogue = open_catalogue(os.environ["RECORD_TEST_ROOT"])
    try:
        assert STORE in catalogue.stores()
        record = catalogue.open(STORE)
        assert record.default_scenario == "inputs"
        assert rows(ws.con, f"SELECT count(*) FROM {BASE}.manta.scenario_changes WHERE scenario = 'patch'") == [(83,)]
        # Opened from its copy on disk.
        assert (catalogue.cache / STORE / "revisions.json").is_file()
        catalogue.open_revision(STORE, "myopic")
    finally:
        ws.close()
