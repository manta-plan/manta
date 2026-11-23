# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The `static_<dtype>` views of a registration: every constant value, one long view per value type.

`<prefix>.static_<dtype>(entity, bus, attribute, value)` has one branch per
attribute of that type over `entity` or `connection` that holds rows by the
owner map. A branch reads the rows without a snapshot, by the snapshot's first
field where it is a multi-dimension, so the filter reaches the Parquet scan.
`bus` is set only for attributes over `connection`: the bus the port attaches
to, from the connection's `bus` property. A caller filters on
`attribute` first, which drops branches before any read.
"""

from __future__ import annotations

import duckdb
from datarecord import Schema
from datarecord.schema.dtypes import DUCK_TYPES

from datarecord_session.packs import field_of, literal, quote

DTYPES = ("float", "int", "bool", "str")


def _without_snapshot(schema: Schema) -> str:
    over = schema.dimensions["snapshot"].over if "snapshot" in schema.dimensions else None
    return "snapshot IS NULL" if over is None else f"snapshot.{quote(next(iter(over)))} IS NULL"


def _branch(prefix: str, schema: Schema, attribute: str) -> str:
    dims = schema.attributes[attribute].dims
    source = f"{prefix}.attributes.{quote(attribute)} a"
    entity, bus = "a.entity", "NULL"
    if "connection" in dims:
        entity, bus = f"a.connection.{field_of(schema, 'connection', 'entity')}", "c.bus"
        source += f" LEFT JOIN {prefix}.properties.connection c ON c.connection = a.connection"
    where = f" WHERE {_without_snapshot(schema)}" if "snapshot" in dims else ""
    return (
        f"SELECT {entity} AS entity, {bus}::VARCHAR AS bus, {literal(attribute)} AS attribute, "
        f"a.value FROM {source}{where}"
    )


def create_static_views(con: duckdb.DuckDBPyConnection, prefix: str, schema: Schema) -> list[str]:
    stored = {
        a for (a,) in con.execute(f"SELECT DISTINCT attribute FROM {prefix}.owner_map").fetchall()
    }
    labelled = {a for a, spec in schema.attributes.items() if spec.dims & {"entity", "connection"}}
    names = []
    for dtype in DTYPES:
        attributes = sorted(a for a in stored & labelled if schema.attributes[a].dtype == dtype)
        empty = (
            f"SELECT NULL::VARCHAR AS entity, NULL::VARCHAR AS bus, NULL::VARCHAR AS attribute, "
            f"NULL::{DUCK_TYPES[dtype]} AS value WHERE false"
        )
        sql = " UNION ALL ".join(_branch(prefix, schema, a) for a in attributes) or empty
        con.execute(f"CREATE VIEW {prefix}.static_{dtype} AS {sql}")
        names.append(f"static_{dtype}")
    return names
