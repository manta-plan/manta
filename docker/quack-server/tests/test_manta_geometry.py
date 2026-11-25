# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

"""Zones from bus properties and `manta.entity_geometry`, over a small
in-memory record (no sample record needed): with and without the columns,
in the default catalog and in a named one, as the server registers them."""

from __future__ import annotations

import duckdb
import pytest

from app.manta_views import register_manta_views

GEOMETRY_COLUMNS = [
    ("entity", "VARCHAR"),
    ("ctype", "VARCHAR"),
    ("carrier", "VARCHAR"),
    ("kind", "VARCHAR"),
    ("wkt", "VARCHAR"),
    ("lon", "DOUBLE"),
    ("lat", "DOUBLE"),
]


def make_record(con: duckdb.DuckDBPyConnection, catalog: str | None, *, busmap_property: bool, geometry: bool,
                busmap_attribute: bool = False) -> dict[str, set[str]]:
    """Two locations (an AC and an H2 bus each) and a virtual EU bus; a
    generator, a line and a load. Returns the attributes' dims."""
    prefix = f"{catalog}." if catalog else ""
    if catalog:
        con.execute(f"ATTACH ':memory:' AS {catalog}")
    for schema in ("properties", "attributes"):
        con.execute(f"CREATE SCHEMA {prefix}{schema}")
    busmap = ", busmap_5 VARCHAR" if busmap_property else ""
    con.execute(f"CREATE TABLE {prefix}properties.bus (bus VARCHAR, carrier VARCHAR, x DOUBLE, y DOUBLE, location VARCHAR{busmap})")
    rows = [
        ("A", "AC", 4.0, 50.0, "A", "Z1"),
        ("A H2", "H2", 4.0, 50.0, "A", "Z1"),
        ("B", "AC", 5.0, 51.0, "B", "Z2"),
        ("B H2", "H2", 5.0, 51.0, "B", "Z2"),
        ("EU gas", "gas", 0.0, 0.0, "EU", None),
    ]
    for row in rows:
        values = row if busmap_property else row[:-1]
        con.execute(f"INSERT INTO {prefix}properties.bus VALUES ({', '.join('?' * len(values))})", list(values))
    geom = ", geometry VARCHAR" if geometry else ""
    con.execute(f"CREATE TABLE {prefix}properties.entity (entity VARCHAR, ctype VARCHAR, carrier VARCHAR{geom})")
    entities = [
        ("solar 1", "Generator", "solar", "POINT (4.25 50.5)"),
        ("solar 2", "Generator", "solar", "  point z(4.5 -50.75 3)"),
        ("onwind 1", "Generator", "onwind", "POLYGON ((4 50, 5 50, 5 51, 4 50))"),
        ("onwind 2", "Generator", "onwind", ""),
        ("line 1", "Line", "AC", "LINESTRING (4 50, 5 51)"),
        ("load 1", "Load", "electricity", None),
        ("odd 1", "Generator", "oil", "GEOMETRYCOLLECTION EMPTY"),
    ]
    for row in entities:
        values = row if geometry else row[:-1]
        con.execute(f"INSERT INTO {prefix}properties.entity VALUES ({', '.join('?' * len(values))})", list(values))
    con.execute(f"""CREATE TABLE {prefix}properties.connection AS
        SELECT {{'entity': 'line 1', 'bus': 'A'}} AS connection, 'input' AS role
        UNION ALL SELECT {{'entity': 'line 1', 'bus': 'B'}}, 'output'
        UNION ALL SELECT {{'entity': 'solar 1', 'bus': 'A'}}, 'attached'""")
    con.execute(f"CREATE TABLE {prefix}attributes.p_nom AS SELECT 'solar 1' AS entity, 10.0 AS value")
    dims = {"p_nom": {"entity"}}
    if busmap_attribute:
        # The attribute names the zones differently from the property, so
        # the test can tell which one was read.
        con.execute(f"CREATE TABLE {prefix}attributes.busmap_5 AS SELECT * FROM (VALUES ('A', 'attr1'), ('B', 'attr2')) t(bus, value)")
        dims["busmap_5"] = {"bus"}
    return dims


@pytest.fixture(params=[None, "rec__inputs"], ids=["default", "catalog"])
def catalog(request):
    return request.param


def build(catalog: str | None, **kwargs) -> tuple[duckdb.DuckDBPyConnection, str]:
    con = duckdb.connect()
    dims = make_record(con, catalog, **kwargs)
    names = register_manta_views(con, dims, catalog)
    assert {"location_zones", "entity_geometry"} <= set(names)
    return con, f"{catalog}." if catalog else ""


def test_zones_from_bus_property(catalog):
    con, p = build(catalog, busmap_property=True, geometry=False)
    # One row per real location (not per bus, and not the virtual EU).
    assert con.execute(f"SELECT level, location, zone FROM {p}manta.location_zones ORDER BY location").fetchall() == [
        ("busmap_5", "A", "Z1"),
        ("busmap_5", "B", "Z2"),
    ]


def test_zones_attribute_wins(catalog):
    con, p = build(catalog, busmap_property=True, geometry=False, busmap_attribute=True)
    assert con.execute(f"SELECT level, location, zone FROM {p}manta.location_zones ORDER BY location").fetchall() == [
        ("busmap_5", "A", "attr1"),
        ("busmap_5", "B", "attr2"),
    ]


def test_no_zones(catalog):
    con, p = build(catalog, busmap_property=False, geometry=False)
    assert con.execute(f"SELECT count(*) FROM {p}manta.location_zones").fetchall() == [(0,)]


def geometry_columns(con: duckdb.DuckDBPyConnection, catalog: str | None) -> list[tuple]:
    return con.execute(
        "SELECT column_name, data_type FROM duckdb_columns() WHERE database_name = ? "
        "AND schema_name = 'manta' AND table_name = 'entity_geometry' ORDER BY column_index",
        [catalog or "memory"],
    ).fetchall()


def test_entity_geometry(catalog):
    con, p = build(catalog, busmap_property=False, geometry=True)
    assert geometry_columns(con, catalog) == GEOMETRY_COLUMNS
    got = con.execute(f"SELECT entity, ctype, carrier, kind, lon, lat FROM {p}manta.entity_geometry ORDER BY entity").fetchall()
    # Empty and NULL geometries are left out.
    assert got == [
        ("line 1", "Line", "AC", "route", None, None),
        ("odd 1", "Generator", "oil", "geometrycollection", None, None),
        ("onwind 1", "Generator", "onwind", "area", None, None),
        ("solar 1", "Generator", "solar", "point", 4.25, 50.5),
        ("solar 2", "Generator", "solar", "point", 4.5, -50.75),
    ]
    assert con.execute(f"SELECT wkt FROM {p}manta.entity_geometry WHERE entity = 'line 1'").fetchall() == [("LINESTRING (4 50, 5 51)",)]


def test_entity_geometry_without_the_column(catalog):
    con, p = build(catalog, busmap_property=False, geometry=False)
    assert geometry_columns(con, catalog) == GEOMETRY_COLUMNS
    assert con.execute(f"SELECT count(*) FROM {p}manta.entity_geometry").fetchall() == [(0,)]
