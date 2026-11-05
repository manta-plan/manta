"""The app's own views, in the `manta` schema: plain SQL over the record views.

They hold what the app assumes about a record, in one place, and nothing here
calls datarecord, so they work over any database that has the record views
(a baked `.duckdb` file included).

- A bus's **location** is its `location` property (PyPSA-Eur names a site
  after its AC bus). `VIRTUAL_LOCATIONS` aren't places: `EU` is PyPSA-Eur's
  copper plate for fuels and CO₂. Nothing in the data marks it, so it's named
  here.
- A **zone** comes from a `busmap_*` attribute (PyPSA-Eur's clustering), read
  at the bus the location is named after. Each such attribute is one zone
  level, for example `busmap_5`. A record without them has no zones.
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
VIRTUAL_LOCATIONS = ("EU",)
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
    zones = " UNION ALL ".join(
        f"SELECT '{level}' AS level, m.bus AS location, m.value AS zone "
        f'FROM attributes."{level}" m WHERE m.bus IN (SELECT location FROM manta.bus_location WHERE NOT virtual)'
        for level in levels
    )
    views = {
        # Every bus with its location, and whether that location is virtual.
        "bus_location": f"""
            SELECT b.bus, b.carrier, b.location, b.x, b.y,
                   b.location IN ({virtual}) AS virtual
            FROM properties.bus b
        """,
        # Real locations only: where the map draws a point.
        "locations": """
            SELECT location, any_value(x) AS x, any_value(y) AS y, count(*) AS buses,
                   list(DISTINCT carrier ORDER BY carrier) AS carriers
            FROM manta.bus_location WHERE NOT virtual
            GROUP BY location
        """,
        # One row per zone level and real location.
        "location_zones": zones
        or "SELECT NULL::VARCHAR AS level, NULL::VARCHAR AS location, NULL::VARCHAR AS zone WHERE false",
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
        # Shape polygons as WKT, with the bus (and location) they belong to.
        "regions": """
            SELECT g.entity, c.value AS component, i.value AS bus, b.location, g.value AS wkt
            FROM attributes.geometry g
            JOIN properties.entity e ON e.entity = g.entity AND e.ctype = 'Shape'
            LEFT JOIN attributes.component c ON c.entity = g.entity
            LEFT JOIN attributes.idx i ON i.entity = g.entity
            LEFT JOIN manta.bus_location b ON b.bus = i.value
        """
        if {"geometry", "component", "idx"} <= set(attributes)
        else "SELECT NULL::VARCHAR AS entity, NULL::VARCHAR AS component, NULL::VARCHAR AS bus, "
        "NULL::VARCHAR AS location, NULL::VARCHAR AS wkt WHERE false",
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
