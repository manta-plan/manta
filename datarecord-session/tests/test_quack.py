# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A native Quack client reads a registered revision under its prefix, and writes nothing."""

from __future__ import annotations

import duckdb
import pytest
from conftest import PERIODS, STORE, Endpoints, Register, Revisions, attach, remote


def test_reads_an_attribute_view(quack: duckdb.DuckDBPyConnection, registered: str) -> None:
    rows = remote(quack, f"SELECT entity, value FROM {registered}.attributes.p_nom ORDER BY ALL")

    assert rows == [("line", 50.0), ("wind", 100.0)]


@pytest.mark.parametrize("store", [STORE, PERIODS])
def test_static_views_hold_the_constants(
    quack: duckdb.DuckDBPyConnection, register: Register, stores: dict[str, Revisions], store: str
) -> None:
    response = register("static", stores[store].base, store=store)
    prefix = response.raise_for_status().json()["prefix"]
    floats = remote(quack, f"FROM {prefix}.static_float ORDER BY ALL")
    bools = remote(quack, f"FROM {prefix}.static_bool ORDER BY ALL")

    assert floats == [
        ("chp", "DE0", "efficiency", 0.4),
        ("line", "DE1", "efficiency", 0.98),
        ("line", None, "p_max_pu", 0.9),
        ("line", None, "p_nom", 50.0),
        ("wind", None, "p_nom", 100.0),
    ]
    assert bools == [("wind", None, "p_nom_extendable", True)]


@pytest.mark.parametrize(
    ("view", "expected"),
    [
        (
            "bus_location",
            [
                ("DE0", "AC", "DE0", 10.0, 50.0, False),
                ("DE1", "AC", "DE1", 11.0, 51.0, False),
                ("EU gas", "gas", "EU", 0.0, 0.0, True),
            ],
        ),
        ("locations", [("DE0", 10.0, 50.0, 1, ["AC"]), ("DE1", 11.0, 51.0, 1, ["AC"])]),
        ("location_zones", [("busmap_1", "DE0", "Z1"), ("busmap_1", "DE1", "Z2")]),
        (
            "branches",
            [
                ("chp", "Link", "gas", "EU gas", "DE0", "EU", "DE0", "virtual"),
                ("chp", "Link", "gas", "EU gas", "DE1", "EU", "DE1", "virtual"),
                ("line", "Line", "AC", "DE0", "DE1", "DE0", "DE1", "between"),
            ],
        ),
        (
            "attached",
            [
                ("load", "Load", "AC", "DE1", "DE1", False),
                ("wind", "Generator", "wind", "DE0", "DE0", False),
            ],
        ),
        ("regions", []),
        ("entity_geometry", []),
    ],
)
def test_pypsa_eur_pack(
    quack: duckdb.DuckDBPyConnection, registered: str, view: str, expected: list[tuple]
) -> None:
    assert remote(quack, f'FROM {registered}."pypsa-eur".{view} ORDER BY ALL') == expected


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE memory.main.t AS SELECT 1",
        "DROP SCHEMA manta.base CASCADE",
        "COPY (SELECT 1) TO 'out.csv'",
        "ATTACH ':memory:' AS other",
        "SET threads = 1",
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM '/etc/passwd'",
        "SELECT getenv('HOME')",
        "SELECT system.main.current_setting('s3_secret_access_key')",
        "SELECT * FROM duckdb_secrets()",
        "SELECT quack_connection_id()",
    ],
)
def test_refuses_anything_but_a_select(
    quack: duckdb.DuckDBPyConnection, registered: str, statement: str
) -> None:
    with pytest.raises(duckdb.Error, match="Authorization failed"):
        remote(quack, statement)

    assert remote(quack, f"SELECT count(*) FROM {registered}.attributes.p_nom") == [(2,)]


@pytest.mark.parametrize(
    ("statement", "expected"),
    [("SELECT * FROM range(2)", [(0,), (1,)]), ("SELECT * FROM unnest([1, 2])", [(1,), (2,)])],
)
def test_allows_row_table_functions(
    quack: duckdb.DuckDBPyConnection, statement: str, expected: list[tuple]
) -> None:
    assert remote(quack, statement) == expected


def test_refuses_a_wrong_token(endpoints: Endpoints) -> None:
    with pytest.raises(duckdb.Error):
        attach(endpoints.quack_port, "wrong")
