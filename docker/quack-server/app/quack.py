"""Run DuckDB's Quack server inside this process, restricted to read-only queries.

Quack hands every client the full SQL surface of the server. Two guards:

1. DuckDB itself: the HTTP file systems are switched off (no reads of
   arbitrary URLs), extension installs are off, and the configuration is
   locked. External access stays on: datarecord's SQL reads Python objects by
   name, which DuckDB only resolves with it on, and records open on demand,
   after this lockdown (stores.py). Reads of the bucket go through the S3 file
   system, with a key that can only read the records bucket. The local file
   system stays on too: DuckDB needs it for temp files.
2. The authorization callback, which works on the parsed query:

   - it must parse as SELECT statements only (no DDL, DML, COPY, ATTACH, SET,
     PRAGMA), bar the bare transaction statements the client wraps every query in,
   - table functions are limited to the catalog ones the Quack client calls when
     it attaches, which shuts out read_csv/read_parquet/glob/query/quack_* and
     friends, including inside the record directory,
   - table names can't be file paths or URLs (replacement scans like `FROM 'x.csv'`).

Treat this as a proof-of-concept guard, not an audited security boundary.
"""

from __future__ import annotations

import duckdb

AUTHORIZE_MACRO = "manta_authorize"

# Table functions the Quack client issues while syncing the remote catalog.
CATALOG_TABLE_FUNCTIONS = (
    "duckdb_columns",
    "duckdb_databases",
    "duckdb_schemas",
    "duckdb_tables",
    "duckdb_views",
)

# Picks the function name out of every TABLE_FUNCTION node in json_serialize_sql's
# output. If a node doesn't match the pattern, the count check below fails closed.
_TABLE_FUNCTION_NAME = (
    r'"type":"TABLE_FUNCTION","alias":"(?:[^"\\]|\\.)*","sample":null,'
    r'[^{]*"function":\{[^{}]*"function_name":"([^"]+)"'
)

# Sent verbatim by the Quack client around each query; they change no data.
TRANSACTION_STATEMENTS = ("BEGIN TRANSACTION", "COMMIT", "ROLLBACK")


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def install_authorization(con: duckdb.DuckDBPyConnection) -> None:
    allowed = ", ".join(_sql_string(name) for name in CATALOG_TABLE_FUNCTIONS)
    transactions = ", ".join(_sql_string(s) for s in TRANSACTION_STATEMENTS)
    con.execute(f"""
        CREATE OR REPLACE MACRO {AUTHORIZE_MACRO}(sid, query) AS (
            upper(trim(query::VARCHAR)) IN ({transactions})
        ) OR (
            WITH parsed AS (SELECT json_serialize_sql(query::VARCHAR) AS j),
            table_functions AS (
                SELECT
                    j,
                    len(regexp_extract_all(j, '"type":"TABLE_FUNCTION"')) AS n,
                    regexp_extract_all(j, {_sql_string(_TABLE_FUNCTION_NAME)}, 1) AS names
                FROM parsed
            )
            SELECT
                NOT coalesce(json_extract_string(j, '$.error')::BOOLEAN, true)
                AND n = len(names)
                AND list_bool_and(list_transform(names, lambda f: lower(f) IN ({allowed}))) IS NOT FALSE
                AND NOT regexp_matches(j, '"table_name":"[^"]*[./:\\\\][^"]*"')
            FROM table_functions
        )
    """)


# Not needed by the server once it serves; S3 (the bucket) and the local file
# system (temp files) are.
DISABLED_FILESYSTEMS = ("HTTPFileSystem", "HuggingFaceFileSystem")


def serve(con: duckdb.DuckDBPyConnection, port: int, token: str) -> str:
    """Start Quack on localhost; the HTTP app in front of it is the public face."""
    con.execute("LOAD quack")
    # Quack's encryption needs httpfs's crypto module; without it, quack_serve
    # fails on a machine that doesn't already have httpfs cached.
    con.execute("LOAD httpfs")
    # The authorization macro needs json; load it now rather than on first use.
    con.execute("LOAD json")
    install_authorization(con)
    # Nothing may install new extensions once clients are connected.
    con.execute("SET autoinstall_known_extensions = false")
    uri = f"quack:localhost:{port}"
    con.execute("CALL quack_serve(?, token = ?)", [uri, token])
    con.execute(f"SET GLOBAL quack_authorization_function = '{AUTHORIZE_MACRO}'")
    con.execute("SET disabled_filesystems = ?", [",".join(DISABLED_FILESYSTEMS)])
    con.execute("SET lock_configuration = true")
    return uri


def stop(con: duckdb.DuckDBPyConnection, uri: str) -> None:
    con.execute("CALL quack_stop(?)", [uri])
