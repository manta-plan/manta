# SPDX-FileCopyrightText: Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

"""The authorization macro (quack.py) that every client query passes.

First the macro alone, on a bare connection: it decides on the parsed query,
so the tables needn't exist. Then end to end, as the browser reaches the
server: the sample record opened behind a running Quack, and a client that
attaches it and sends queries through `quack_query_by_name`, as the app's
serverQuery does."""

from __future__ import annotations

import socket

from pathlib import Path

import duckdb
import pytest
from datarecord import Workspace

from app import quack
from app.stores import Catalogue, configure

ROOT = Path(__file__).resolve().parents[1] / "data/records"
STORE = "BEL-pre-aggregated-incl-patches-incl-results"
# The base case's catalog, and a run result's.
C = "bel_pre_aggregated_incl_patches_incl_results__inputs"
RESULT = "bel_pre_aggregated_incl_patches_incl_results__perfect"

# What the app and modellers send: plain SELECT/WITH over the record views.
ALLOWED = [
    "SELECT 1",
    "BEGIN TRANSACTION",
    "COMMIT",
    "ROLLBACK",
    f"SELECT count(*) FROM {C}.attributes.p_nom",
    f"FROM {C}.properties.entity SELECT ctype, count(*) GROUP BY ALL",
    f"""WITH span AS (SELECT snapshot FROM {C}.dims.snapshot)
        SELECT epoch_ms(t.snapshot.timestep)::DOUBLE AS t, strftime(t.snapshot.timestep, '%Y') AS y
        FROM span t LEFT JOIN {C}.attributes.snapshot_weighting_generators w ON w.snapshot = t.snapshot""",
    f"SELECT quantile_cont(value, 0.5), list(entity ORDER BY entity) FROM {C}.attributes.p_nom WHERE starts_with(entity, 'BE')",
    f"SELECT regexp_extract(entity, '(\\d+)', 1), TRY_CAST(value AS INTEGER) FROM {C}.attributes.p_nom",
    f"SELECT list(DISTINCT u.bus) FROM (SELECT unnest([bus0, bus1]) AS bus FROM {C}.manta.branches) u",
    f"SELECT * FROM {C}.manta.bus_location ORDER BY location, bus",
    "SELECT 'getenv(1)' AS s, '\"function_name\":\"getenv\"' AS t",
    "SELECT * FROM range(3)",
    "SELECT * FROM generate_series(1, 3)",
    "SELECT * FROM unnest([1, 2])",
    # The Quack client's catalog sync.
    "SELECT * FROM duckdb_views()",
    "SELECT database_name, schema_name FROM duckdb_schemas()",
    "FROM duckdb_columns() SELECT count(*)",
]

DENIED = [
    # Files, by table function or replacement scan.
    "SELECT * FROM read_text('/app/.env')",
    "SELECT * FROM read_text('/proc/self/environ')",
    "SELECT * FROM read_blob('/etc/hosts')",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM read_csv_auto('/etc/passwd')",
    "SELECT * FROM read_parquet('/app/data/records/x/layers/a/b.parquet')",
    "SELECT * FROM read_json('/etc/x.json')",
    "SELECT * FROM sniff_csv('/etc/hosts')",
    "SELECT * FROM parquet_metadata('x.parquet')",
    "SELECT * FROM glob('/*')",
    "SELECT * FROM GLOB('/*')",
    "SELECT * FROM system.main.read_text('/etc/hosts')",
    "SELECT * FROM '/etc/hosts'",
    "SELECT * FROM 'data.csv'",
    'SELECT * FROM "/etc/hosts"',
    "SELECT * FROM 's3://manta-records/x.parquet'",
    "SELECT (SELECT content FROM read_text('/etc/hosts'))",
    f"SELECT * FROM {C}.attributes.p_nom WHERE (SELECT count(*) FROM glob('/*')) > 0",
    "WITH x AS (FROM read_text('/etc/hosts')) FROM x",
    f"SELECT * FROM {C}.attributes.p_nom, LATERAL (FROM read_text('/etc/hosts'))",
    "DESCRIBE FROM read_text('/etc/hosts')",
    "SUMMARIZE FROM read_text('/etc/hosts')",
    "SELECT 1; SELECT * FROM read_text('/etc/hosts')",
    # The environment, settings and secrets.
    "SELECT getenv('AWS_SECRET_ACCESS_KEY')",
    "SELECT GETENV('HOME')",
    "SELECT system.main.getenv('HOME')",
    "SELECT list_transform([1], x -> getenv('HOME'))",
    f"SELECT * FROM {C}.attributes.p_nom WHERE getenv('HOME') IS NOT NULL",
    "SELECT current_setting('s3_secret_access_key')",
    "SELECT Current_Setting('temp_directory')",
    "SELECT system.main.current_setting('home_directory')",
    "SELECT 'x'.current_setting()",
    "SELECT * FROM duckdb_settings()",
    "SELECT * FROM system.main.duckdb_settings()",
    "SELECT * FROM duckdb_secrets()",
    "SELECT * FROM which_secret('s3://manta-records/x', 's3')",
    "SELECT * FROM duckdb_extensions()",
    "SELECT * FROM pragma_version()",
    # SQL of its own, Quack's functions, the macro itself.
    "SELECT * FROM query('SELECT 42')",
    "SELECT * FROM query_table('t')",
    "SELECT * FROM json_execute_serialized_sql(json_serialize_sql('SELECT 1'))",
    "SELECT * FROM quack_query_by_name('r', 'SELECT 1')",
    "SELECT quack_check_token('a', 'b')",
    "SELECT quack_connection_id()",
    "SELECT manta_authorize(1, 'SELECT 1')",
    # Anything but SELECT.
    "COPY (SELECT 1) TO '/tmp/pwn.csv'",
    "SELECT 1; COPY (SELECT 1) TO '/tmp/pwn.csv'",
    "EXPORT DATABASE '/tmp/x'",
    "ATTACH '/tmp/x.db' AS x",
    "DETACH datarecord",
    "INSTALL spatial",
    "LOAD spatial",
    "FORCE INSTALL httpfs",
    "SET threads = 1",
    "SET GLOBAL quack_authorization_function = 'quack_nop_authorization'",
    "RESET lock_configuration",
    "PRAGMA database_list",
    "PRAGMA enable_profiling",
    "CALL pragma_version()",
    "EXPLAIN SELECT 1",
    "CREATE TABLE t AS SELECT 1",
    "CREATE MACRO m() AS 1",
    "CREATE SECRET s (TYPE s3, KEY_ID 'a', SECRET 'b')",
    "DROP VIEW x",
    "INSERT INTO t VALUES (1)",
    "UPDATE t SET x = 1",
    "DELETE FROM t",
    "CHECKPOINT",
    "VACUUM",
    "USE datarecord",
    "BEGIN TRANSACTION; COPY (SELECT 1) TO '/tmp/pwn.csv'",
    "not sql at all",
    "",
]


@pytest.fixture(scope="module")
def guard():
    con = duckdb.connect()
    con.execute("LOAD json")
    quack.install_authorization(con)
    yield con
    con.close()


def authorized(con: duckdb.DuckDBPyConnection, sql: str) -> bool:
    return con.execute(f"SELECT {quack.AUTHORIZE_MACRO}(1, ?)", [sql]).fetchone()[0] is True


@pytest.mark.parametrize("sql", ALLOWED)
def test_allows(guard, sql):
    assert authorized(guard, sql)


@pytest.mark.parametrize("sql", DENIED)
def test_denies(guard, sql):
    assert not authorized(guard, sql)


# End to end: a client attached over Quack, as the browser is.


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def client():
    """The server as main.py starts it: locked down by quack.serve, then the
    record opened. And a client attached to it."""
    if not (ROOT / STORE).is_dir():
        pytest.skip("sample record not present")
    try:
        duckdb.connect().execute("LOAD quack")
    except duckdb.Error as e:
        pytest.skip(f"Quack extension not available: {e}")
    ws = Workspace()
    configure(ws.con)
    catalogue = Catalogue(ws, str(ROOT))
    port = free_port()
    token = "guardtest"
    uri = quack.serve(ws.con, port, token)
    catalogue.open(STORE)
    catalogue.open_revision(STORE, "perfect")
    con = duckdb.connect()
    con.execute("LOAD quack")
    con.execute(f"ATTACH 'quack:localhost:{port}' AS r (TOKEN '{token}')")
    yield con
    con.close()
    quack.stop(ws.con, uri)
    ws.close()


def remote(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    """As the app's serverQuery sends it."""
    return con.execute(f"FROM quack_query_by_name('r', $${sql}$$)").fetchall()


@pytest.mark.parametrize(
    "sql",
    [s for s in ALLOWED if s not in quack.TRANSACTION_STATEMENTS]
    + [f"SELECT count(*) FROM {RESULT}.attributes.p_nom_opt"],
)
def test_remote_allows(client, sql):
    remote(client, sql)


def test_remote_values(client):
    assert remote(client, f"SELECT count(*) FROM {C}.attributes.p_nom") == [(44,)]
    # Through the ATTACH: the client scans the view on the server.
    assert client.execute(f"SELECT count(*) FROM r.{C}.attributes.p_nom WHERE value > 0").fetchone()[0] > 0


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_text('/etc/hosts')",
        "SELECT * FROM glob('/*')",
        "SELECT * FROM '/etc/hosts'",
        "SELECT getenv('HOME')",
        "SELECT current_setting('temp_directory')",
        "SELECT * FROM duckdb_settings()",
        "SELECT * FROM duckdb_secrets()",
        "COPY (SELECT 1) TO '/tmp/pwn.csv'",
        "ATTACH ':memory:' AS x",
        "INSTALL spatial",
        "LOAD spatial",
        "SET threads = 1",
        "PRAGMA database_list",
    ],
)
def test_remote_denies(client, sql):
    with pytest.raises(duckdb.Error, match="Authorization failed"):
        remote(client, sql)
