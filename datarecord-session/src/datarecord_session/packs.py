# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""View packs: SQL templates a registration asks for, created below it as `<prefix>."<pack>"`.

The pack `pypsa-eur` holds the map and topology views moved from
`docker/quack-server/app/manta_views.py`. They encode PyPSA-Eur conventions:

- A bus's location is its `location` property, or the bus itself where that is
  empty. `VIRTUAL_LOCATIONS` are no places: `EU` is PyPSA-Eur's copper plate,
  and the empty name a bus without one.
- A zone comes from a `busmap_*` attribute, or a `busmap_*` bus property, read
  at the bus the location is named after. Each such name is one zone level.
- An entity's geometry is its `geometry` property (WKT).
- A connection is a port of an entity, attached to the bus in its `bus`
  property. Port 0 is PyPSA's `bus0`, the input of a line, link or
  transformer, and the one port of an entity that has no other.
- A branch is port 0 and one other port of an entity: a link with several
  outputs gives several branches. An entity with one port is attached at it.
- A region is a polygon of a PyPSA `Shape` entity, or a bus property in
  `BUS_SHAPES`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Literal

import duckdb
from datarecord import Schema

Pack = Literal["pypsa-eur"]

ZONE_LEVEL_PREFIX = "busmap_"
VIRTUAL_LOCATIONS = ("EU", "")
BUS_SHAPES = {"shape_onshore": "onshore", "shape_offshore": "offshore"}

_WKT_TYPE = r"^\s*([A-Za-z]+)"
_WKT_POINT = r"(?i)^\s*POINT\s*(?:ZM|Z|M)?\s*\(\s*([-+0-9.e]+)\s+([-+0-9.e]+)"


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def field_of(schema: Schema, dim: str, over: str) -> str:
    fields = {d: field for field, d in (schema.dimensions[dim].over or {}).items()}
    return quote(fields[over])


def zone_levels(names: Iterable[str]) -> list[str]:
    return sorted(name for name in names if name.startswith(ZONE_LEVEL_PREFIX))


def _zones_sql(r: str, p: str, levels: list[str], bus_columns: set[str]) -> str:
    parts = [
        f"SELECT {literal(level)} AS level, m.bus AS location, m.value AS zone "
        f"FROM {r}.attributes.{quote(level)} m "
        f"WHERE m.bus IN (SELECT location FROM {p}.bus_location WHERE NOT virtual)"
        for level in levels
    ]
    parts += [
        f"SELECT {literal(column)} AS level, l.location, p.{quote(column)}::VARCHAR AS zone "
        f"FROM {p}.locations l JOIN {r}.properties.bus p ON p.bus = l.location "
        f"WHERE p.{quote(column)} IS NOT NULL"
        for column in zone_levels(bus_columns - set(levels))
    ]
    empty = (
        "SELECT NULL::VARCHAR AS level, NULL::VARCHAR AS location, NULL::VARCHAR AS zone "
        "WHERE false"
    )
    return " UNION ALL ".join(parts) or empty


def _entity_geometry_sql(r: str, entity_columns: set[str]) -> str:
    if "geometry" not in entity_columns:
        return (
            "SELECT NULL::VARCHAR AS entity, NULL::VARCHAR AS ctype, NULL::VARCHAR AS carrier, "
            "NULL::VARCHAR AS kind, NULL::VARCHAR AS wkt, NULL::DOUBLE AS lon, "
            "NULL::DOUBLE AS lat WHERE false"
        )
    return f"""
        SELECT entity, ctype, carrier,
               CASE type WHEN 'POINT' THEN 'point'
                         WHEN 'LINESTRING' THEN 'route' WHEN 'MULTILINESTRING' THEN 'route'
                         WHEN 'POLYGON' THEN 'area' WHEN 'MULTIPOLYGON' THEN 'area'
                         ELSE lower(type) END AS kind,
               wkt,
               CASE WHEN type = 'POINT'
                    THEN TRY_CAST(regexp_extract(wkt, '{_WKT_POINT}', 1) AS DOUBLE) END AS lon,
               CASE WHEN type = 'POINT'
                    THEN TRY_CAST(regexp_extract(wkt, '{_WKT_POINT}', 2) AS DOUBLE) END AS lat
        FROM (
            SELECT entity, ctype, carrier, geometry::VARCHAR AS wkt,
                   upper(regexp_extract(geometry::VARCHAR, '{_WKT_TYPE}', 1)) AS type
            FROM {r}.properties.entity
            WHERE geometry IS NOT NULL AND trim(geometry::VARCHAR) <> ''
        )
    """


def _ports_sql(r: str, schema: Schema) -> str:
    entity = field_of(schema, "connection", "entity")
    port = field_of(schema, "connection", "port")
    return (
        f"SELECT connection.{entity} AS entity, connection.{port} AS port, bus, "
        f"count(*) OVER (PARTITION BY connection.{entity}) AS ports "
        f"FROM {r}.properties.connection"
    )


def _regions_sql(r: str, p: str, attributes: set[str], bus_columns: set[str]) -> str:
    parts = []
    if {"geometry", "component", "idx"} <= attributes:
        parts.append(f"""
            SELECT g.entity, c.value AS component, i.value AS bus, b.location, g.value AS wkt
            FROM {r}.attributes.geometry g
            JOIN {r}.properties.entity e ON e.entity = g.entity AND e.ctype = 'Shape'
            LEFT JOIN {r}.attributes.component c ON c.entity = g.entity
            LEFT JOIN {r}.attributes.idx i ON i.entity = g.entity
            LEFT JOIN {p}.bus_location b ON b.bus = i.value""")
    parts += [
        f"""
            SELECT p.bus || ' {component}' AS entity, '{component}' AS component, p.bus,
                   b.location, p.{column} AS wkt
            FROM {r}.properties.bus p LEFT JOIN {p}.bus_location b ON b.bus = p.bus
            WHERE p.{column} IS NOT NULL"""
        for column, component in BUS_SHAPES.items()
        if column in bus_columns
    ]
    empty = (
        "SELECT NULL::VARCHAR AS entity, NULL::VARCHAR AS component, NULL::VARCHAR AS bus, "
        "NULL::VARCHAR AS location, NULL::VARCHAR AS wkt WHERE false"
    )
    return " UNION ALL ".join(parts) or empty


def pypsa_eur_views(r: str, schema: Schema) -> dict[str, str]:
    p = f"{r}.{quote('pypsa-eur')}"
    attributes = set(schema.attributes)
    bus_columns = set(schema.properties.get("bus", {}))
    virtual = ", ".join(literal(location) for location in VIRTUAL_LOCATIONS)
    return {
        "bus_location": f"""
            SELECT bus, carrier, location, x, y, location IN ({virtual}) AS virtual
            FROM (
                SELECT b.bus, b.carrier, coalesce(nullif(b.location, ''), b.bus) AS location,
                       b.x, b.y
                FROM {r}.properties.bus b
            )
        """,
        "locations": f"""
            SELECT location, any_value(x) AS x, any_value(y) AS y, count(*) AS buses,
                   list(DISTINCT carrier ORDER BY carrier) AS carriers
            FROM {p}.bus_location WHERE NOT virtual
            GROUP BY location
        """,
        "location_zones": _zones_sql(r, p, zone_levels(attributes), bus_columns),
        "branches": f"""
            WITH ends AS ({_ports_sql(r, schema)})
            SELECT e.entity, e.ctype, e.carrier,
                   i.bus AS bus0, o.bus AS bus1,
                   b0.location AS location0, b1.location AS location1,
                   CASE WHEN b0.virtual OR b1.virtual THEN 'virtual'
                        WHEN b0.location = b1.location THEN 'within'
                        ELSE 'between' END AS scope
            FROM ends i
            JOIN ends o ON o.entity = i.entity AND i.port = 0 AND o.port <> 0
            JOIN {r}.properties.entity e ON e.entity = i.entity
            JOIN {p}.bus_location b0 ON b0.bus = i.bus
            JOIN {p}.bus_location b1 ON b1.bus = o.bus
        """,
        "attached": f"""
            WITH ends AS ({_ports_sql(r, schema)})
            SELECT e.entity, e.ctype, e.carrier, c.bus, b.location, b.virtual
            FROM ends c
            JOIN {r}.properties.entity e ON e.entity = c.entity
            JOIN {p}.bus_location b ON b.bus = c.bus
            WHERE c.ports = 1
        """,
        "regions": _regions_sql(r, p, attributes, bus_columns),
        "entity_geometry": _entity_geometry_sql(r, set(schema.properties.get("entity", {}))),
    }


PACKS: dict[Pack, Callable[[str, Schema], dict[str, str]]] = {"pypsa-eur": pypsa_eur_views}


def create_pack(
    con: duckdb.DuckDBPyConnection, prefix: str, pack: Pack, schema: Schema
) -> list[str]:
    views = PACKS[pack](prefix, schema)
    con.execute(f"CREATE SCHEMA {prefix}.{quote(pack)}")
    for name, sql in views.items():
        con.execute(f"CREATE VIEW {prefix}.{quote(pack)}.{name} AS {sql}")
    return list(views)
