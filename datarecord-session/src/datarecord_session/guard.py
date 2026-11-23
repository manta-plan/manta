# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Serve the session's connection over Quack, restricted to read-only queries.

Moved from `docker/quack-server/app/quack.py`. Quack hands every client the full
SQL surface of the server. Two guards:

1. DuckDB itself: the HTTP file systems are switched off (no reads of
   arbitrary URLs), extension installs are off, and the configuration is
   locked. External access stays on: datarecord's SQL reads Python objects by
   name, which DuckDB only resolves with it on, and revisions register after
   this lockdown. Reads of the bucket go through the S3 file system, with the
   session's credential. The local file system stays on too: DuckDB needs it
   for temp files.
2. The authorization callback, which works on the parsed query:

   - it must parse as SELECT statements only (no DDL, DML, COPY, ATTACH, SET,
     PRAGMA), bar the bare transaction statements the client wraps every query in,
   - table functions are limited to the catalog ones the Quack client calls when
     it attaches, plus a few that only make rows (range, unnest), which shuts out
     read_csv/read_parquet/read_text/glob/query/duckdb_settings/duckdb_secrets/
     quack_* and friends,
   - no call, anywhere in the query and however it's qualified or cased, to a
     function that reveals the server: its settings (current_setting), its
     environment (getenv), its secrets, Quack's own functions,
   - table names can't be file paths or URLs (replacement scans like `FROM 'x.csv'`).

Every name is read from json_serialize_sql's parse of the query, not its text.

Treat this as a proof-of-concept guard, not an audited security boundary.
"""

from __future__ import annotations

import duckdb

AUTHORIZE_MACRO = "manta_authorize"

CATALOG_TABLE_FUNCTIONS = (
    "duckdb_columns",
    "duckdb_databases",
    "duckdb_schemas",
    "duckdb_tables",
    "duckdb_views",
)

ROW_TABLE_FUNCTIONS = ("generate_series", "range", "unnest")

DENIED_FUNCTIONS = (
    "current_setting",
    "getenv",
    "duckdb_secrets",
    "which_secret",
    "duckdb_settings",
    "json_execute_serialized_sql",
    "query",
    "query_table",
    AUTHORIZE_MACRO,
)

QUACK_PREFIX = "quack_"

_TABLE_FUNCTION_NAME = (
    r'"type":"TABLE_FUNCTION","alias":"(?:[^"\\]|\\.)*","sample":null,'
    r'[^{]*"function":\{[^{}]*"function_name":"([^"]+)"'
)

_FUNCTION_NAME = r'"function_name":"((?:[^"\\]|\\.)*)"'

TRANSACTION_STATEMENTS = ("BEGIN TRANSACTION", "COMMIT", "ROLLBACK")

DISABLED_FILESYSTEMS = ("HTTPFileSystem", "HuggingFaceFileSystem")

EXTENSIONS = ("quack", "httpfs", "json")


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def install_authorization(con: duckdb.DuckDBPyConnection) -> None:
    allowed = ", ".join(_sql_string(name) for name in CATALOG_TABLE_FUNCTIONS + ROW_TABLE_FUNCTIONS)
    denied = ", ".join(_sql_string(name) for name in DENIED_FUNCTIONS)
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
                    regexp_extract_all(j, {_sql_string(_TABLE_FUNCTION_NAME)}, 1) AS names,
                    list_transform(
                        regexp_extract_all(j, {_sql_string(_FUNCTION_NAME)}, 1),
                        lambda f: lower(f)
                    ) AS calls
                FROM parsed
            )
            SELECT
                NOT coalesce(json_extract_string(j, '$.error')::BOOLEAN, true)
                AND coalesce(json_array_length(j, '$.statements'), 0) > 0
                AND n = len(names)
                AND list_bool_and(
                    list_transform(names, lambda f: lower(f) IN ({allowed}))
                ) IS NOT FALSE
                AND NOT list_has_any(calls, [{denied}])
                AND NOT list_bool_or(
                    list_transform(calls, lambda f: starts_with(f, {_sql_string(QUACK_PREFIX)}))
                ) IS TRUE
                AND NOT regexp_matches(j, '"table_name":"[^"]*[./:\\\\][^"]*"')
            FROM table_functions
        )
    """)


def serve(con: duckdb.DuckDBPyConnection, host: str, port: int, token: str) -> str:
    for extension in EXTENSIONS:
        con.load_extension(extension)
    con.execute("SET GLOBAL enable_http_metadata_cache = true")
    con.execute("SET GLOBAL parquet_metadata_cache = true")
    install_authorization(con)
    con.execute(f"SET GLOBAL quack_authorization_function = '{AUTHORIZE_MACRO}'")
    con.execute("SET autoinstall_known_extensions = false")
    con.execute("SET disabled_filesystems = ?", [",".join(DISABLED_FILESYSTEMS)])
    uri = f"quack:{host}:{port}"
    con.execute(
        "CALL quack_serve(?, token = ?, allow_other_hostname = true, disable_ssl = true)",
        [uri, token],
    )
    con.execute("SET lock_configuration = true")
    return uri


def stop(con: duckdb.DuckDBPyConnection, uri: str) -> None:
    con.execute("CALL quack_stop(?)", [uri])
