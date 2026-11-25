"""The app's own views, in the `manta` schema: plain SQL over the record views.

They hold what the app assumes about a record, in one place, and nothing here
calls datarecord, so they work over any database that has the record views
(a baked `.duckdb` file included).

- A bus's **location** is its `location` property (PyPSA-Eur names a site
  after its AC bus), or, where that's empty, the bus itself (PyPSA-Earth
  leaves it empty: every bus is its own site). `VIRTUAL_LOCATIONS` aren't
  places: `EU` is PyPSA-Eur's copper plate for fuels and CO₂, and the empty
  name a bus without one (PyPSA-Earth's, at 0, 0). Nothing in the data marks
  them, so they're named here.
- A **zone** comes from a `busmap_*` attribute (PyPSA-Eur's clustering), or
  a `busmap_*` bus property (as BEL-full-res stores it), read at the bus the
  location is named after. Each such name is one zone level, for example
  `busmap_5`; an attribute wins over a property of the same name. A record
  without them has no zones.
- An entity's **geometry** is its `geometry` property (WKT): a point where a
  plant sits, a line's route, or an area (a renewable potential's polygon).
- A **branch** is one input → output pair of a line, link or transformer, from
  the `connection` dim, whose labels are `{entity, bus}` pairs with a `role`.
  A link with several outputs gives several branches.
- `attribute_summary` is the one table: per attribute and subject (an entity,
  or a bus, carrier, …), its constant value and how many series rows it has.
  A row without a snapshot holds for every snapshot, so "constant or series"
  is a property of the rows, not of the attribute. It's built once, at
  start, since a served record doesn't change (datarecord copies the dims the
  same way); otherwise every entity lookup would scan every attribute view.
"""

from __future__ import annotations

import duckdb

SCHEMA = "manta"
ZONE_LEVEL_PREFIX = "busmap_"
VIRTUAL_LOCATIONS = ("EU", "")
# What an attribute is about: the first of these among its dims. Snapshot is
# the series axis unless it's the subject itself.
SUBJECTS = ("entity", "connection", "bus", "carrier", "sub_network", "period", "snapshot", "scenario")


def zone_levels(attributes: list[str]) -> list[str]:
    return sorted(name for name in attributes if name.startswith(ZONE_LEVEL_PREFIX))


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _summary_select(name: str, dims: set[str], prefix: str) -> str:
    subject = next(dim for dim in SUBJECTS if dim in dims)
    if subject == "connection":
        # Per link output: the entity, and the bus that output goes to.
        dim, label, bus = "entity", "connection.entity", "connection.bus"
    else:
        dim, label, bus = subject, subject, "NULL"
    series = "snapshot" in dims and subject != "snapshot"
    constant = "any_value(value::VARCHAR) FILTER (WHERE snapshot IS NULL)" if series else "any_value(value::VARCHAR)"
    rows = "count(*) FILTER (WHERE snapshot IS NOT NULL)" if series else "0"
    table = '"' + name.replace('"', '""') + '"'
    return (
        f"SELECT {_quote(name)} AS attribute, '{dim}' AS dim, {label}::VARCHAR AS label, {bus}::VARCHAR AS bus, "
        f"{constant} AS constant, {rows} AS series_rows FROM {prefix}attributes.{table} GROUP BY ALL"
    )


# A bus's own polygons, as bus properties (the 30 October records); the
# `component` a region gets from each.
BUS_SHAPES = {"shape_onshore": "onshore", "shape_offshore": "offshore"}


def _columns(con: duckdb.DuckDBPyConnection, prefix: str, table: str) -> set[str]:
    """The columns of `properties.<table>` in the catalog (none if it's absent)."""
    database = _quote(prefix[:-1]) if prefix else "current_database()"
    return {name for (name,) in con.execute(
        f"SELECT column_name FROM duckdb_columns() WHERE database_name = {database} "
        f"AND schema_name = 'properties' AND table_name = {_quote(table)}"
    ).fetchall()}


def _zones_sql(levels: list[str], bus_columns: set[str]) -> str:
    """One row per zone level and real location: from the `busmap_*`
    attributes, and from the `busmap_*` bus properties no attribute names."""
    parts = [
        f"SELECT '{level}' AS level, m.bus AS location, m.value AS zone "
        f'FROM attributes."{level}" m WHERE m.bus IN (SELECT location FROM manta.bus_location WHERE NOT virtual)'
        for level in levels
    ]
    for column in zone_levels(sorted(bus_columns - set(levels))):
        name = '"' + column.replace('"', '""') + '"'
        parts.append(
            f"SELECT {_quote(column)} AS level, l.location, p.{name}::VARCHAR AS zone "
            f"FROM manta.locations l JOIN properties.bus p ON p.bus = l.location WHERE p.{name} IS NOT NULL"
        )
    return " UNION ALL ".join(parts) or (
        "SELECT NULL::VARCHAR AS level, NULL::VARCHAR AS location, NULL::VARCHAR AS zone WHERE false"
    )


# A WKT's leading type word (`POINT`, `LINESTRING`, …), and a point's two
# coordinates. The spatial extension isn't loaded, so plain string functions.
_WKT_TYPE = r"^\s*([A-Za-z]+)"
_WKT_POINT = r"(?i)^\s*POINT\s*(?:ZM|Z|M)?\s*\(\s*([-+0-9.e]+)\s+([-+0-9.e]+)"


def _entity_geometry_sql(entity_columns: set[str]) -> str:
    """Entities with a geometry of their own: `kind` is 'point' (a site, with
    its lon and lat), 'route' (a line's path) or 'area' (a polygon); another
    WKT type is its lowercase name."""
    if "geometry" not in entity_columns:
        return (
            "SELECT NULL::VARCHAR AS entity, NULL::VARCHAR AS ctype, NULL::VARCHAR AS carrier, NULL::VARCHAR AS kind, "
            "NULL::VARCHAR AS wkt, NULL::DOUBLE AS lon, NULL::DOUBLE AS lat WHERE false"
        )
    return f"""
        SELECT entity, ctype, carrier,
               CASE type WHEN 'POINT' THEN 'point'
                         WHEN 'LINESTRING' THEN 'route' WHEN 'MULTILINESTRING' THEN 'route'
                         WHEN 'POLYGON' THEN 'area' WHEN 'MULTIPOLYGON' THEN 'area'
                         ELSE lower(type) END AS kind,
               wkt,
               CASE WHEN type = 'POINT' THEN TRY_CAST(regexp_extract(wkt, '{_WKT_POINT}', 1) AS DOUBLE) END AS lon,
               CASE WHEN type = 'POINT' THEN TRY_CAST(regexp_extract(wkt, '{_WKT_POINT}', 2) AS DOUBLE) END AS lat
        FROM (
            SELECT entity, ctype, carrier, geometry::VARCHAR AS wkt,
                   upper(regexp_extract(geometry::VARCHAR, '{_WKT_TYPE}', 1)) AS type
            FROM properties.entity
            WHERE geometry IS NOT NULL AND trim(geometry::VARCHAR) <> ''
        )
    """


def _regions_sql(con: duckdb.DuckDBPyConnection, prefix: str, attributes: list[str]) -> str:
    """Region polygons as WKT, with the bus (and location) they belong to:
    PyPSA's Shape entities, and the bus properties in BUS_SHAPES. A bus's
    region is named `<bus> <component>` (`BE0 0AC onshore`), apart from
    any entity."""
    parts = []
    if {"geometry", "component", "idx"} <= set(attributes):
        parts.append("""
            SELECT g.entity, c.value AS component, i.value AS bus, b.location, g.value AS wkt
            FROM attributes.geometry g
            JOIN properties.entity e ON e.entity = g.entity AND e.ctype = 'Shape'
            LEFT JOIN attributes.component c ON c.entity = g.entity
            LEFT JOIN attributes.idx i ON i.entity = g.entity
            LEFT JOIN manta.bus_location b ON b.bus = i.value""")
    columns = _columns(con, prefix, "bus")
    for column, component in BUS_SHAPES.items():
        if column in columns:
            parts.append(f"""
            SELECT p.bus || ' {component}' AS entity, '{component}' AS component, p.bus, b.location, p.{column} AS wkt
            FROM properties.bus p LEFT JOIN manta.bus_location b ON b.bus = p.bus
            WHERE p.{column} IS NOT NULL""")
    return " UNION ALL ".join(parts) or (
        "SELECT NULL::VARCHAR AS entity, NULL::VARCHAR AS component, NULL::VARCHAR AS bus, "
        "NULL::VARCHAR AS location, NULL::VARCHAR AS wkt WHERE false"
    )


def register_manta_views(con: duckdb.DuckDBPyConnection, dims: dict[str, set[str]], catalog: str | None = None) -> list[str]:
    """Create the `manta` views over the record views; return their names.

    `dims` maps every attribute with a view to its declared dims. `catalog`
    is where the record views are and the `manta` ones go (None: the
    default). A view reads unqualified names in its own catalog; a table
    built with CREATE TABLE … AS reads the default one, so its sources are
    qualified.
    """
    prefix = f"{catalog}." if catalog else ""
    attributes = sorted(dims)
    levels = zone_levels(attributes)
    virtual = ", ".join(f"'{location}'" for location in VIRTUAL_LOCATIONS)
    views = {
        # Every bus with its location, and whether that location is virtual.
        "bus_location": f"""
            SELECT bus, carrier, location, x, y, location IN ({virtual}) AS virtual
            FROM (SELECT b.bus, b.carrier, coalesce(nullif(b.location, ''), b.bus) AS location, b.x, b.y FROM properties.bus b)
        """,
        # Real locations only: where the map draws a point.
        "locations": """
            SELECT location, any_value(x) AS x, any_value(y) AS y, count(*) AS buses,
                   list(DISTINCT carrier ORDER BY carrier) AS carriers
            FROM manta.bus_location WHERE NOT virtual
            GROUP BY location
        """,
        # One row per zone level and real location.
        "location_zones": _zones_sql(levels, _columns(con, prefix, "bus")),
        "branches": """
            WITH ends AS (
                SELECT connection.entity AS entity, connection.bus AS bus, role
                FROM properties.connection WHERE role IN ('input', 'output')
            )
            SELECT e.entity, e.ctype, e.carrier,
                   i.bus AS bus0, o.bus AS bus1,
                   b0.location AS location0, b1.location AS location1,
                   CASE WHEN b0.virtual OR b1.virtual THEN 'virtual'
                        WHEN b0.location = b1.location THEN 'within'
                        ELSE 'between' END AS scope
            FROM ends i
            JOIN ends o ON o.entity = i.entity AND i.role = 'input' AND o.role = 'output'
            JOIN properties.entity e ON e.entity = i.entity
            JOIN manta.bus_location b0 ON b0.bus = i.bus
            JOIN manta.bus_location b1 ON b1.bus = o.bus
        """,
        # Generators, loads, stores and storage units, at their bus.
        "attached": """
            SELECT e.entity, e.ctype, e.carrier, c.connection.bus AS bus, b.location, b.virtual
            FROM properties.connection c
            JOIN properties.entity e ON e.entity = c.connection.entity
            JOIN manta.bus_location b ON b.bus = c.connection.bus
            WHERE c.role = 'attached'
        """,
        "regions": _regions_sql(con, prefix, attributes),
        # Entity sites, line routes and areas, from the `geometry` property.
        "entity_geometry": _entity_geometry_sql(_columns(con, prefix, "entity")),
    }
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {prefix}{SCHEMA}")
    for name, sql in views.items():
        con.execute(f"CREATE OR REPLACE VIEW {prefix}{SCHEMA}.{name} AS {sql}")
    summary = " UNION ALL ".join(_summary_select(name, dims[name], prefix) for name in attributes)
    con.execute(f"CREATE OR REPLACE TABLE {prefix}{SCHEMA}.attribute_summary AS {summary}")
    # Which attributes each ctype uses in this record: where an absent value
    # means the manifest's default rather than "doesn't apply".
    con.execute(f"""
        CREATE OR REPLACE VIEW {prefix}{SCHEMA}.ctype_attributes AS
        SELECT e.ctype, s.attribute, count(DISTINCT s.label) AS entities
        FROM {SCHEMA}.attribute_summary s JOIN properties.entity e ON e.entity = s.label
        WHERE s.dim = 'entity'
        GROUP BY ALL
    """)
    return [*views, "attribute_summary", "ctype_attributes"]
