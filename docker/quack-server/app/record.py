"""Expose a datarecord revision as named views on the server's DuckDB connection."""

from __future__ import annotations

from typing import Any

import duckdb
from datarecord import Record

from .manta_views import SCHEMA, register_manta_views

# Each kind becomes a schema, so `dims.entity` and `properties.entity` don't clash.
KINDS = ("dims", "properties", "attributes")


def _quote_name(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def create_views(con: duckdb.DuckDBPyConnection, record: Record, catalog: str, keep: list[Any]) -> dict[str, list[str]]:
    """One view per relation, plus the `manta` views, in `catalog`.

    The views are datarecord's own resolved SQL (layers already folded), so a
    query against them reads the parquet files lazily. Appends the relations
    to `keep`, which must outlive the views: a relation can register Python
    objects its SQL reads, released when the relation is.
    """
    views: dict[str, list[str]] = {}
    for kind in KINDS:
        relations = getattr(record, kind)
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{kind}")
        for name in relations:
            relation = relations[name]
            keep.append(relation)
            con.execute(f"CREATE OR REPLACE VIEW {catalog}.{kind}.{_quote_name(name)} AS {relation.sql_query()}")
        views[kind] = sorted(relations)
    dims = {name: set(record.schema.attributes[name].dims) for name in views["attributes"]}
    views[SCHEMA] = register_manta_views(con, dims, catalog)
    return views
