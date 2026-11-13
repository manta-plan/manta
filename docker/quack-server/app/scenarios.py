"""A store's named revisions as scenarios and run results, and what each
scenario changes: the `manta.revisions` and `manta.scenario_changes` tables.

- **Names** come from the `references` of the store's `store.json`: per name
  the `revision` it points to, a `label` and an optional `description`.
  A revision without a name isn't shown. A name is also the revision's name
  here (`patch/myopic`), and its catalog is `<record>__<name>` as a slug.
- **Kind:** each named revision has a `manta.kind` in the flat `meta` of its
  layer's manifest (`layers/<id>/manifest.json`): `scenario` for inputs, the
  base inputs included, or `result` for the output of a solve.
- **A revision's parent** is its nearest named ancestor, from the parents in
  the layers' manifests. The base scenario has none.
- **A change** is one attribute in a scenario's own layer whose value differs
  from the parent's, per subject (entity, bus, …). Rows a layer restates
  unchanged aren't changes. Built once, when the store opens: an open store
  doesn't change.

Files are read through datarecord's `Files`, so a store can be local or on
`s3://`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import duckdb
from datarecord import Record, Workspace
from datarecord.store.manifest import Manifest

from .manta_views import SCHEMA, SUBJECTS

BASE_NAME = "inputs"
BASE_LABEL = "Base case"
KIND = "manta.kind"


def slug(text: str) -> str:
    slugged = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slugged if slugged[:1].isalpha() else f"r_{slugged}"


@dataclass
class Layer:
    """A named revision, as `store.json` and its manifest describe it."""

    name: str
    id: str
    parent: str | None
    kind: str
    label: str
    description: str
    written: list[str] = field(repr=False)


@dataclass
class Revision(Layer):
    record: Record = field(repr=False)
    # Its catalog's name (scenarios and run results alike), and whether it's
    # attached yet: scenarios are, when the record opens; a run result is
    # when first asked for (Catalogue.open_revision).
    catalog: str | None = None
    open: bool = False
    # A run result's result attributes: those its layer adds to its parent's.
    results: list[str] = field(default_factory=list)

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


def named_layers(ws: Workspace, store: str, references: dict[str, dict[str, str]]) -> list[Layer]:
    """The store's named revisions (`references` of its `store.json`): the
    base scenario first, then the other scenarios, then the run results."""
    manifests: dict[str, Manifest] = {str(r.id): r.manifest for r in ws.store(store).revisions()}
    names = {reference["revision"]: name for name, reference in references.items()}
    unknown = sorted(name for id, name in names.items() if KIND not in manifests[id].meta)
    if unknown:
        raise ValueError(f"{store}: revisions {unknown} have no {KIND} in their manifest meta")

    def parent(m: Manifest) -> str | None:
        while m.parent is not None and str(m.parent) not in names:
            m = manifests[str(m.parent)]
        return None if m.parent is None else names[str(m.parent)]

    layers = []
    for name, reference in references.items():
        m = manifests[reference["revision"]]
        layer = Layer(
            name=name,
            id=reference["revision"],
            parent=parent(m),
            kind=m.meta[KIND],
            label=reference["label"],
            description=reference.get("description", ""),
            written=sorted(m.files.attributes),
        )
        layers.append(layer)
    return sorted(layers, key=lambda layer: (layer.kind == "result", layer.parent is not None))


def open_revisions(ws: Workspace, store: str, layers: list[Layer]) -> list[Revision]:
    """The named revisions as records of the store at `store`."""
    opened = ws.store(store)
    records = {layer.name: opened.revision(UUID(layer.id)).record for layer in layers}
    revisions = []
    for layer in layers:
        before = records[layer.parent].attributes if layer.parent is not None else None
        new = [a for a in layer.written if before is None or a not in before or not before[a].limit(1).fetchall()]
        revisions.append(Revision(**vars(layer), record=records[layer.name], results=new if layer.kind == "result" else []))
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
