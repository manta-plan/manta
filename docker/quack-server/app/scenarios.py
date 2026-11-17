"""A store's named revisions as scenarios and run results, and what each
scenario changes: the `manta.revisions` and `manta.scenario_changes` tables.

- **Names** come from the store's `revisions.json` (name → revision id);
  unnamed revisions aren't shown. `<store>.labels.json`, beside the store,
  is optional: per revision a `name` and `description` to show, and a `kind`.
- **Kind:** the label's `kind`, else the layer's `meta` `kind`, else a guess.
  Nothing in the format says which attributes a solve computes, so the guess
  is that a revision is a `result` when most of the attributes its layer
  writes have no rows in its parent: a solve adds `p_nom_opt`,
  `marginal_price`, …, while a scenario edits values its parent has. (A base
  layer may write empty files for every result attribute, so it's rows that
  count, not files.)
- **A revision's parent** is in its layer's manifest
  (`layers/<id>/manifest.json`), as are the attributes its layer writes.
- **A change** is one attribute in a scenario's own layer whose value differs
  from the parent's, per subject (entity, bus, …). Rows a layer restates
  unchanged aren't changes. Built once, when the store opens: an open store
  doesn't change.

Files are read through datarecord's `Files`, so a store can be local or on
`s3://`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import duckdb
from datarecord import Record, Workspace

from .manta_views import SCHEMA, SUBJECTS

BASE_NAME = "inputs"
BASE_LABEL = "Base case"


@dataclass
class Revision:
    name: str
    id: str
    parent: str | None
    kind: str
    label: str
    description: str
    # The revision's record, for building the change table.
    record: Record = field(repr=False)
    # Its catalog's name (scenarios and run results alike), and whether it's
    # attached yet: scenarios are, when the record opens; a run result is
    # when first asked for (Catalogue.open_revision).
    catalog: str | None = None
    open: bool = False
    # A run result's result attributes: those its layer adds to its parent's.
    results: list[str] = field(default_factory=list)
    # The attributes its own layer writes.
    written: list[str] = field(default_factory=list, repr=False)

    def as_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "id": self.id,
            "parent": self.parent,
            "kind": self.kind,
            "label": self.label,
            "description": self.description,
            "catalog": self.catalog,
            "open": self.open,
            "results": self.results,
        }


def read_json(ws: Workspace, uri: str) -> Any:
    found = ws.files(uri).read_text(uri)
    if found is None:
        raise FileNotFoundError(uri)
    return json.loads(found)


def layer_manifest(ws: Workspace, store: str, revision_id: str) -> dict[str, Any]:
    return read_json(ws, f"{store}/layers/{revision_id}/manifest.json")


def _named_parent(ws: Workspace, store: str, manifest: dict[str, Any], names_by_id: dict[str, str]) -> str | None:
    """The nearest named ancestor of a revision."""
    parent = manifest.get("parent")
    while parent and parent not in names_by_id:
        parent = layer_manifest(ws, store, parent).get("parent")
    return names_by_id.get(parent) if parent else None


def open_revisions(ws: Workspace, store: str, names: dict[str, str], labels: dict[str, dict[str, str]]) -> list[Revision]:
    """The store's named revisions. `names` is `revisions.json` (name → id);
    `labels` is `<store>.labels.json`, or empty."""
    names_by_id = {revision_id: name for name, revision_id in names.items()}
    opened = ws.store(store)
    records = {name: opened.revision(UUID(revision_id)).record for name, revision_id in names.items()}

    revisions = []
    for name, revision_id in names.items():
        manifest = layer_manifest(ws, store, revision_id)
        parent = _named_parent(ws, store, manifest, names_by_id)
        label = labels.get(name, {})
        written = sorted(manifest["files"].get("attributes", []))
        before = records[parent].attributes if parent is not None else None
        new = [a for a in written if before is None or a not in before or not before[a].limit(1).fetchall()]
        kind = (
            label.get("kind")
            or manifest.get("meta", {}).get("kind")
            or ("result" if parent is not None and len(new) * 2 > len(written) else "scenario")
        )
        revisions.append(
            Revision(
                name=name,
                id=revision_id,
                parent=parent,
                kind=kind,
                label=label.get("name") or (BASE_LABEL if name == BASE_NAME else name),
                description=label.get("description", ""),
                record=records[name],
                results=new if kind == "result" else [],
                written=written,
            )
        )
    return revisions


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _change_select(scenario: str, attribute: str, dims: list[str], before: str, after: str) -> str:
    """One attribute's changed values in a scenario, one row per subject."""
    subject = next(dim for dim in SUBJECTS if dim in dims)
    if subject == "connection":
        dim, label, bus = "entity", "k.connection.entity", "k.connection.bus"
    else:
        dim, label, bus = subject, f"k.{subject}", "NULL"
    series = "snapshot" in dims and subject != "snapshot"
    on = " AND ".join(f"b.{d} IS NOT DISTINCT FROM s.{d}" for d in dims)
    keys = ", ".join(f"coalesce(s.{d}, b.{d}) AS {d}" for d in dims)
    ratio = "TRY_CAST(after AS DOUBLE) / nullif(TRY_CAST(before AS DOUBLE), 0)"
    return f"""
        SELECT {_quote(scenario)} AS scenario, {_quote(attribute)} AS attribute, '{dim}' AS dim,
               {label}::VARCHAR AS label, {bus}::VARCHAR AS bus,
               {"NULL" if series else "any_value(before)"} AS before,
               {"NULL" if series else "any_value(after)"} AS after,
               {"count(*)" if series else "0"} AS series_rows,
               median({ratio}) AS ratio
        FROM (
            SELECT {keys}, b.value::VARCHAR AS before, s.value::VARCHAR AS after
            FROM ({before}) b FULL JOIN ({after}) s ON {on}
            WHERE b.value IS DISTINCT FROM s.value
        ) k
        GROUP BY ALL"""


def register_scenarios(con: duckdb.DuckDBPyConnection, ws: Workspace, store: str, revisions: list[Revision], catalogs: list[str]) -> list[str]:
    """Create `manta.revisions` and `manta.scenario_changes` in each of
    `catalogs`: built in the first, copied to the others."""
    first = catalogs[0]
    con.execute(f"""
        CREATE OR REPLACE TABLE {first}.{SCHEMA}.revisions (
            name VARCHAR, id VARCHAR, parent VARCHAR, kind VARCHAR,
            label VARCHAR, description VARCHAR, catalog VARCHAR)""")
    for r in revisions:
        con.execute(
            f"INSERT INTO {first}.{SCHEMA}.revisions VALUES (?, ?, ?, ?, ?, ?, ?)",
            [r.name, r.id, r.parent, r.kind, r.label, r.description, r.catalog],
        )

    by_name = {r.name: r for r in revisions}
    selects = []
    for r in revisions:
        if r.kind != "scenario" or r.parent is None:
            continue
        parent = by_name[r.parent]
        for attribute in r.written:
            # Each catalog has a view per attribute its record declares.
            if attribute not in r.record.attributes:
                continue
            dims = list(r.record.schema.attributes[attribute].dims)
            view = f'attributes."{attribute}"'
            after = f"FROM {r.catalog}.{view}"
            # An attribute the parent doesn't declare: every row is added.
            before = f"FROM {parent.catalog}.{view}" if attribute in parent.record.attributes else f"{after} WHERE false"
            selects.append(_change_select(r.name, attribute, dims, before, after))
    empty = (
        "SELECT NULL::VARCHAR AS scenario, NULL::VARCHAR AS attribute, NULL::VARCHAR AS dim, NULL::VARCHAR AS label, "
        "NULL::VARCHAR AS bus, NULL::VARCHAR AS before, NULL::VARCHAR AS after, 0::BIGINT AS series_rows, "
        "NULL::DOUBLE AS ratio WHERE false"
    )
    con.execute(f"CREATE OR REPLACE TABLE {first}.{SCHEMA}.scenario_changes AS {' UNION ALL '.join(selects) or empty}")
    for catalog in catalogs[1:]:
        for table in ("revisions", "scenario_changes"):
            con.execute(f"CREATE OR REPLACE TABLE {catalog}.{SCHEMA}.{table} AS FROM {first}.{SCHEMA}.{table}")
    return ["revisions", "scenario_changes"]
