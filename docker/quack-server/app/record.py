"""Expose a datarecord revision as named views in a catalog of its own."""

from __future__ import annotations

import duckdb
from datarecord import Record

from .manta_views import SCHEMA, register_manta_views

# Each kind becomes a schema, so `dims.entity` and `properties.entity` don't clash.
KINDS = ("dims", "properties", "attributes")


def _quote_name(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def create_views(con: duckdb.DuckDBPyConnection, record: Record, catalog: str, database: str) -> dict[str, list[str]]:
    """One view per relation, plus the `manta` views, in `catalog`.

    The record registers its views as the schema `catalog` of the workspace's
    database (`database`, as in `datarecord.<catalog>.dims.bus`); the views
    here read those. So a client names a scenario by one catalog, which also
    holds our `manta` schema, and datarecord keeps what its views read alive.
    """
    record.register(catalog)
    views: dict[str, list[str]] = {}
    for kind in KINDS:
        names = sorted(getattr(record, kind))
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{kind}")
        for name in names:
            quoted = _quote_name(name)
            con.execute(f"CREATE OR REPLACE VIEW {catalog}.{kind}.{quoted} AS FROM {database}.{catalog}.{kind}.{quoted}")
        views[kind] = names
    dims = {name: set(record.schema.attributes[name].dims) for name in views["attributes"]}
    views[SCHEMA] = register_manta_views(con, dims, catalog)
    return views
