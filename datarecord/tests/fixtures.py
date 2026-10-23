# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Hand-built patch layers, since the v2 write path does not exist.

Notes
-----
- [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
"""

from pathlib import Path
from typing import Any

import duckdb
import narwhals as nw
import pandas as pd

from datarecord.files import Files, Version
from datarecord.layered.resolve import write_schema as record_write_schema
from datarecord.layered.revision import Revision
from datarecord.schema import (
    AttributeSpec,
    Dimension,
    Group,
    PropertySpec,
    Schema,
    Trait,
)
from datarecord.store import Store

TYPES = (
    "Bus",
    "Carrier",
    "Generator",
    "Line",
    "Link",
    "Load",
    "Process",
    "StorageUnit",
    "Store",
    "Transformer",
    "Widget",
)
"""The `entity_type` labels `schema()` declares - every one a test writes."""

# No `entity_type`: an attribute row is keyed by `name`, unique across every type
# (https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types). The entity tables below keep it.
LONG_COLUMNS = [
    "entity",
    "bus",
    "snapshot",
    "scenario",
    "period",
    "attribute",
    "breakpoint",
    "value",
]


def write_input(
    layer: str,
    attribute: str,
    rows: list[dict],
    *,
    snapshot_dtype="datetime64[ns]",
    connection: bool | None = None,
) -> None:
    """Write `inputs/<attribute>.parquet` in the long schema.

    Each row needs at least `name` and `value`; missing dimension columns
    default to NULL, i.e. "applies to the whole axis".
    A `bus` on any row marks a per-connection attribute, its `entity` and `bus`
    packed into the one `connection` struct column - unless `connection` says
    otherwise, for an attribute over the `bus` dim itself; `breakpoint` marks a
    piecewise-linear one; neither is the ordinary component-level scalar.

    Write every file of a layer before its first read: a read freezes the
    layer for its workspace, as a layer is write-once.

    Notes
    -----
    - [wide and long rows](https://energy-models.github.io/datarecord/design/record/#wide-and-long-rows)
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    df = pd.DataFrame(rows)
    if connection is None:
        connection = "bus" in df
    df["attribute"] = attribute
    for col in LONG_COLUMNS:
        if col not in df:
            df[col] = None
    df["snapshot"] = pd.Series(df["snapshot"]).astype(snapshot_dtype)
    df["scenario"] = df["scenario"].astype("string")
    df["entity"] = df["entity"].astype("string")
    df["bus"] = df["bus"].astype("string")
    df["period"] = df["period"].astype("Int64")
    df["breakpoint"] = df["breakpoint"].astype("float64")
    df["value"] = df["value"].astype("float64")

    target = Path(layer, "inputs")
    target.mkdir(parents=True, exist_ok=True)
    rel = duckdb.connect().from_df(df[LONG_COLUMNS])
    if connection:
        rel = rel.project(
            "{'entity': entity, 'bus': bus} AS connection, * EXCLUDE (entity, bus)"
        )
    rel.to_parquet(str(target / f"{attribute}.parquet"))


def write_group(layer: str, group: str, rows: list[dict]) -> None:
    """Write `groups/<group>.parquet` from plain rows, whatever columns they carry.

    The generic form of `write_connections`: one file per group, keyed by the
    struct column named for it - a dict per row here - with `deleted` supplied
    where a row does not carry it.

    Notes
    -----
    - [where the rows live](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    """
    df = pd.DataFrame(rows)
    if "deleted" not in df:
        df["deleted"] = False
    df["deleted"] = df["deleted"].fillna(False).astype(bool)
    target = Path(layer, "groups")
    target.mkdir(parents=True, exist_ok=True)
    df.to_parquet(target / f"{group}.parquet", index=False)


def unpacked(frame: Any, group: str = "connection") -> pd.DataFrame:
    """A group-keyed frame or relation as pandas, its struct column spread flat.

    A numpy-backed pandas frame has no struct dtype, so the unnest happens on
    the DuckDB side.
    """
    rel = frame.to_native() if isinstance(frame, nw.LazyFrame) else frame
    return rel.project(f"unnest({group}), * EXCLUDE ({group})").df()


def write_connections(layer: str, rows: list[dict]) -> None:
    """Write `groups/connection.parquet`, including the `deleted` tombstone.

    Each row needs `entity` and `bus`, packed into the `connection` struct the
    file is keyed by; `role` describes the connection and keys nothing, so it is
    optional here.

    No component type - one file holds every type's rows. Appended rather than
    replaced, since a layer may write them a call at a time.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    - [where the rows live](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    """
    df = pd.DataFrame(rows)
    for col in ("scenario", "role"):
        if col not in df:
            df[col] = None
        df[col] = df[col].astype("string")
    if "deleted" not in df:
        df["deleted"] = False
    df["deleted"] = df["deleted"].fillna(False).astype(bool)
    df["connection"] = [
        {"entity": e, "bus": b} for e, b in zip(df.pop("entity"), df.pop("bus"))
    ]

    lead = ["connection", "role", "scenario", "deleted"]
    ordered = lead + [c for c in df.columns if c not in lead]
    target = Path(layer, "groups")
    target.mkdir(parents=True, exist_ok=True)
    path = target / "connection.parquet"
    out = df[ordered]
    if path.exists():
        out = pd.concat([pd.read_parquet(path), out], ignore_index=True)
    out.to_parquet(path, index=False)


def tombstone_connection(layer: str, pairs: list[tuple[str, str]]) -> None:
    """Mark connections deleted in this layer, by `(entity, bus)`.

    Notes
    -----
    - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
    """
    write_connections(
        layer,
        [{"entity": name, "bus": bus, "deleted": True} for name, bus in pairs],
    )


def write_entity_type(layer: str, ctype: str, rows: list[dict]) -> None:
    """Append rows of category `ctype` to `dims/entity.parquet`.

    The label is the `entity_type` property column; tombstones ride along as
    `deleted`. Appended rather than replaced: several labels land in one entity
    axis, and a layer may write them one call at a time.
    """
    df = pd.DataFrame(rows)
    df["entity_type"] = ctype
    if "deleted" not in df:
        df["deleted"] = False
    df["deleted"] = df["deleted"].fillna(False).astype(bool)

    lead = ["entity", "entity_type", "deleted"]
    entities = df[lead + [c for c in df.columns if c not in lead]]
    target = Path(layer, "dims")
    target.mkdir(parents=True, exist_ok=True)
    axis = target / "entity.parquet"
    if axis.exists():
        entities = pd.concat([pd.read_parquet(axis), entities], ignore_index=True)
    entities.to_parquet(axis, index=False)


def tombstone(layer: str, ctype: str, names: list[str]) -> None:
    """Mark components deleted in this layer.

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    write_entity_type(
        layer,
        ctype,
        [{"entity": n, "deleted": True} for n in names],
    )


def write_scenarios(layer: str, rows: list[dict]) -> None:
    """Write `dims/scenario.parquet`; each row needs `scenario`."""
    df = pd.DataFrame(rows)
    target = Path(layer, "dims")
    target.mkdir(parents=True, exist_ok=True)
    df.to_parquet(target / "scenario.parquet", index=False)


def write_periods(layer: str, rows: list[dict]) -> None:
    """Write `dims/period.parquet`; each row needs `period`."""
    df = pd.DataFrame(rows)
    target = Path(layer, "dims")
    target.mkdir(parents=True, exist_ok=True)
    df.to_parquet(target / "period.parquet", index=False)


def write_snapshots(layer: str, rows: list[dict]) -> None:
    """Write `dims/snapshot.parquet`; each row needs `snapshot`.

    A `period` column makes it a nested axis, keyed by `(period,
    snapshot)` rather than by the timestamp alone.

    Notes
    -----
    - [within](https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis)
    """
    df = pd.DataFrame(rows)
    df["snapshot"] = pd.Series(df["snapshot"]).astype("datetime64[ns]")
    if "period" in df:
        df["period"] = df["period"].astype("Int64")
    target = Path(layer, "dims")
    target.mkdir(parents=True, exist_ok=True)
    df.to_parquet(target / "snapshot.parquet", index=False)


def write_axis(layer: str, dim: str, rows: list[dict]) -> None:
    """Write `dims/<dim>.parquet` from plain rows, whatever columns they carry.

    The generic form of `write_scenarios`/`write_periods`: an axis file is its
    key columns plus the dim's properties.

    Notes
    -----
    - [the record format](https://energy-models.github.io/datarecord/design/format/)
    """
    target = Path(layer, "dims")
    target.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(target / f"{dim}.parquet", index=False)


def example(load):
    """A PyPSA example network, loaded offline once it is cached.

    PyPSA asks GitHub for a newer release on every netCDF import, without a
    timeout, so a stalled connection hangs the suite. Network requests are
    allowed only to download an example not cached yet, which PyPSA refuses
    with a `ValueError` while they are off.
    """
    import pypsa

    with pypsa.option_context("general.allow_network_requests", False):
        try:
            return load()
        except ValueError:
            pass
    return load()


def rename_components(n, ctype: str, suffix: str) -> None:
    """Suffix one type's member names, in `static` and every dynamic container.

    PyPSA's example networks scope names per component type - a `Load` named
    after its `Bus`, a `Generator` after its `Carrier` - which a record cannot
    represent, names being unique across types.
    `PyPSA.to_datarecord` rejects such a network rather than renaming it,
    so the suffix here is the test suite standing in for the caller that has to
    reconcile the two vocabularies.

    Both containers, because they are keyed by the same names: renaming only
    `static` would orphan every dynamic column, and so silently drop that
    attribute from the record. A stochastic network is keyed by
    `(scenario, name)`, so only the `name` level moves.

    The renamed level is cast back to the dtype it had: `rename` yields an
    `object` index where PyPSA's own is `str`, and `assert_networks_equal`
    compares index dtypes exactly - so without this the helper, not the code
    under test, would fail the round-trip.

    Notes
    -----
    - [entity is unique across types](https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types)
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    c = n.c[ctype]
    index = c.static.index
    nested = "name" in (index.names or []) and index.nlevels > 1
    if nested:
        level = index.get_level_values("name")
        renamed = {name: f"{name}{suffix}" for name in level}
        c.static.rename(index=renamed, level="name", inplace=True)
        c.static.index = c.static.index.set_levels(
            c.static.index.levels[index.names.index("name")].astype(level.dtype),
            level="name",
        )
        # Per *level*, which is what `rename` does on a MultiIndex - a
        # tuple-keyed mapping matches nothing and silently leaves the columns
        # pointing at names `static` no longer has.
        for frame in c.dynamic.values():
            frame.rename(columns=renamed, level="name", inplace=True)
        return
    renamed = {name: f"{name}{suffix}" for name in index}
    c.static.rename(index=renamed, inplace=True)
    c.static.index = c.static.index.astype(index.dtype)
    for frame in c.dynamic.values():
        frame.rename(columns=renamed, inplace=True)


def empty_root(store: Store) -> Revision:
    """A new root revision with no layer, for a test to hand-write one into.

    No public API makes an empty revision; this is the store's private
    revision-file write.

    Write every file of a layer before its first read: a read freezes the
    layer for its workspace, as a layer is write-once.
    """
    return store._create(None)


def empty_child(parent: Revision) -> Revision:
    """A new child of `parent` with no layer, like `empty_root`.

    Write every file of a layer before its first read: a read freezes the
    layer for its workspace, as a layer is write-once.
    """
    return parent.store._create(parent.id)


def export_network(n, store: Store) -> Revision:
    """Write `n` as a new root of `store`, through the record layer's own writer.

    Not `n.export_to_parquet`: that emits PyPSA's upstream manifest format,
    which is a different vocabulary from the schema a record declares.
    Going through `store.root` means a test record is written exactly as
    `blocks` writes one.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """
    from datarecord.tools.pypsa import PyPSA

    return store.root(PyPSA.to_datarecord(n, store.workspace.con))


def write_schema(schema: Schema, store: Store) -> None:
    """Declare the record's one schema, beside the layers.

    Not per layer: a layer holds only data, so this writes the record-level
    `manifest.json` that every layer in the tree is read under.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """
    record_write_schema(schema, store)


def widened(base: Schema, attribute: str) -> Schema:
    """`base` declaring one more attribute, shaped like its `p_nom`."""
    return Schema(
        **{
            **dict(base),
            "attributes": {**base.attributes, attribute: base.attributes["p_nom"]},
        }
    )


class RivalWrite:
    """`Files` where a rival replaces `uri` right after this writer reads it.

    Two writers racing on the manifest, made deterministic: the read hands back
    a version the rival's write has already made stale, once.

    Notes
    -----
    - [the manifest's compare-and-swap](https://energy-models.github.io/datarecord/design/writing/#the-manifests-compare-and-swap)
    """

    def __init__(self, inner: Files, uri: str, text: str) -> None:
        self._inner = inner
        self._uri = uri
        self._text = text
        self.raced = False

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def read_text(self, uri: str) -> tuple[str, Version] | None:
        found = self._inner.read_text(uri)
        if uri == self._uri and not self.raced:
            self.raced = True
            self._inner.write_text(uri, self._text, expect=None)
        return found


def _default_attributes(
    dims: dict[str, nw.dtypes.DType], groups: dict[str, dict[str, str]]
):
    """The attributes tests write, declared over whichever dims are in play.

    Writing an attribute the schema does not declare is rejected, since its
    `dims` are what say which columns its file carries - so every attribute a
    test writes has to be declared, and these are the ones they write.

    Addressed over every declared dim rather than a narrower set, which is the
    widest shape and so the one that accepts any row a test writes.
    `efficiency` is the exception, being over the `connection` group where one
    is declared: that is what puts a `connection` struct column on its file.

    `weight` is the other, addressed by `scenario` alone - long rows of
    `inputs/weight.parquet` like any attribute, whatever its `dims`.
    """
    varying = {"entity", *dims}
    connection = "connection" if "connection" in groups else "entity"
    # A dim the connection's column already carries cannot address it again.
    per_connection = set(dims) - set(groups.get(connection, ()))
    declared = {
        "p_nom": AttributeSpec(dtype=nw.Float64(), dims=varying),
        "e_nom": AttributeSpec(dtype=nw.Float64(), dims=varying),
        "p_max_pu": AttributeSpec(dtype=nw.Float64(), dims=varying),
        "p_min_pu": AttributeSpec(dtype=nw.Float64(), dims=varying),
        "marginal_cost": AttributeSpec(
            dtype=nw.Float64(), dims=varying, breakpoints=True
        ),
        "efficiency": AttributeSpec(
            dtype=nw.Float64(), dims={connection, *per_connection}
        ),
    }
    if "scenario" in dims:
        declared["weight"] = AttributeSpec(
            dtype=nw.Float64(),
            dims={"scenario"},
            description="How much this scenario counts in the expectation.",
        )
    return declared


def schema(
    *,
    partial: set[str] = {"scenario", "connection"},
    attributes: dict[str, dict[str, AttributeSpec]] | None = None,
    dims: dict[str, nw.dtypes.DType] = {
        "snapshot": nw.Datetime(),
        "period": nw.Int64(),
        "scenario": nw.String(),
    },
    groups: dict[str, dict[str, str]] = {
        "connection": {"entity": "entity", "bus": "bus"}
    },
    within: dict[str, set[str]] | None = None,
) -> Schema:
    """A schema shaped like the PyPSA records most tests build on.

    Defaults match `PyPSA.to_datarecord`: the `entity` axis carrying the
    `entity_type` property (categories `TYPES`), a `connection` group over
    `(entity, bus)`, and three declared dims. Override `partial` to pin a
    different layering granularity, `dims` to declare another axis, `groups` to
    declare a different sparse relation, `within` to nest one axis inside
    another.

    A group's coordinates are declared dims. `entity` is always `partial`, so
    a layer patches one component's value without restating the rest, and
    `connection` is by default, as the PyPSA tool declares it, so the same
    holds per connection.

    Notes
    -----
    - [the schema](https://energy-models.github.io/datarecord/design/schema/)
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    - [within](https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis)
    """
    nesting = within or {}
    # Callers declare per type, which is how a modelling framework thinks; the
    # schema stores one spec per attribute, record-wide, and a trait per type
    # narrows it back. Flattening here keeps the tests readable and is exactly
    # what a tool does on the way in.
    flat: dict[str, AttributeSpec] = {}
    traits: dict[str, Trait] = {}
    for ctype, attrs in (attributes or {}).items():
        for attr, spec in attrs.items():
            flat.setdefault(attr, spec)
        traits[ctype] = Trait(
            attributes=frozenset(attrs), on={"entity_type": frozenset({ctype})}
        )
    # Declared whether or not a caller named them: a test writing `p_max_pu`
    # needs it declared, and one passing `attributes=` is narrowing what a type
    # *carries* rather than shortening the record's vocabulary.
    for attr, spec in _default_attributes(dims, groups).items():
        flat.setdefault(attr, spec)
    # A group's coordinates are dims like any other, so they are declared here
    # rather than assumed - which is what lets a caller pass a group over
    # coordinates that are not called `bus`.
    coordinates = {c for over in groups.values() for c in over}
    declared = {
        "entity": nw.String(),
        **{c: nw.String() for c in coordinates},
        **dims,
    }
    return Schema(
        groups={g: Group(over=over) for g, over in groups.items()},
        dimensions={
            d: Dimension(dtype=t, within=frozenset(nesting.get(d, set())))
            for d, t in declared.items()
        },
        properties={"entity": {"entity_type": PropertySpec(dtype=nw.Enum(TYPES))}},
        attributes=flat,
        traits=traits,
        # The default names `connection`, which a caller's own `groups` may drop.
        partial=frozenset(
            p for p in {"entity", *partial} if p in declared or p in groups
        ),
    )


def relation(revision, attribute: str):
    """The resolved long relation for one input attribute, as a DuckDB relation.

    A test helper rather than a `Revision` method: `Revision` presents its data
    through `.record` (a `Record`), and a DuckDB-shaped accessor beside it would
    duplicate `record.attributes[attr]` while inverting what `outputs` means -
    a relation on the revision against a `Frames` mapping on the record. Tests
    want relations because they assert on `.df()`, so the affordance lives here.
    """
    return revision.resolver.attribute(attribute)


def outputs(revision, attribute: str):
    """One result attribute as a DuckDB relation; outputs do not overlay.

    Notes
    -----
    - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
    """
    return revision.resolver.attribute(attribute, "outputs")
