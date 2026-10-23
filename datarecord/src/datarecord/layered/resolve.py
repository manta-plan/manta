# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The owner map, and the resolved reads gated by it.

The map answers which layer owns each key; `Resolver` exposes the reads over
it - one long relation per attribute, a group's frame, this
layer's own outputs. Tool-agnostic: turning these into a framework's
object is `datarecord.tools`.

Notes
-----
- [the DuckDB read path](https://energy-models.github.io/datarecord/design/read-path/)
- [resolving a relation](https://energy-models.github.io/datarecord/design/read-path/#resolving-a-relation)
- [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
- [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
"""

from __future__ import annotations

import dataclasses
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from hashlib import sha256
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import duckdb
import narwhals as nw
from duckdb import CoalesceOperator as coalesce
from duckdb import ColumnExpression as col
from duckdb import ConstantExpression as lit
from duckdb import DuckDBPyConnection, DuckDBPyRelation, Expression
from duckdb import SQLExpression as sql
from duckdb import StarExpression as star

from datarecord.duck import (
    DuckTypes,
    dead_keys,
    distinct_values,
    ensure_local_dir,
    fn,
    fold_axis,
    null_safe,
    struct_field,
    struct_of,
    try_read_parquet,
    union_all_by_name,
)
from datarecord.layered import categories
from datarecord.layered.fold import Fold
from datarecord.layered.sources import LayerSource, ParquetLayer
from datarecord.schema import LAYER_COLUMN, Schema

if TYPE_CHECKING:
    from datarecord.store import Store, Workspace

# The owner map's `layer_uuid` column type - a layering mechanism, not
# something a schema declares.
LAYER_UUID_TYPE = "UUID"


def _base_and_above(
    sources: Sequence[LayerSource], con: DuckDBPyConnection, schema: Schema
) -> tuple[Fold | None, list[LayerSource]]:
    """Split `sources` at the deepest materialised one: its `Fold`, then the rest.

    The deepest materialised source's `Fold` is the fold's base - already folded
    over everything at or below it - and only the sources above it are folded on
    top. No materialised source means no base and the whole list folds from the
    root.

    The last source is never the base: a node resolves from its own layer, never
    from its own cache. Reading a node through its own materialised `Fold` would
    return the cached answer instead of resolving it, and folding *nothing* on
    top - the same reason `sources_to_read` truncates only at proper ancestors.
    """
    for i in range(len(sources) - 2, -1, -1):
        base = sources[i].materialised(con, schema)
        if base is not None:
            return base, list(sources[i + 1 :])
    return None, list(sources)


def resolve_coords(
    schema: Schema,
    sources: Sequence[LayerSource],
    con: DuckDBPyConnection,
    split: tuple[Fold | None, list[LayerSource]] | None = None,
) -> Coords:
    """Fold every dim `schema` declares to its axis relation.

    Parameters
    ----------
    schema
        The record's schema, which declares the dims and their keys.
    sources : sequence of LayerSource
        Root first, ending in the layer being resolved.
    con : DuckDBPyConnection
    split
        `_base_and_above(sources, ...)`, where the caller already read it.

    Returns
    -------
    Coords

    Notes
    -----
    - [the schema](https://energy-models.github.io/datarecord/design/schema/)
    """
    # One listing per source rather than one probe per declared dim per source
    # (D x A misses, most declared dims absent from most layers): `present` says
    # which dims that source actually has, so `fold_axis` below is only ever
    # asked for a dim at least one source holds, and only passed the sources
    # that hold it.
    base, above = split or _base_and_above(sources, con, schema)
    present = [source.axes() for source in above]
    axes = {}
    for dim in schema.dims:
        # The base's resolved axis is depth 0 - already folded and tombstone-
        # free - so a layer above it still wins per key and its tombstones still
        # remove a base key, exactly as folding from the root would.
        seed = None if base is None else base.axes.get(dim)
        holding = [s for s, names in zip(above, present) if dim in names]
        if seed is None and not holding:
            continue
        # Keyed by the axis key, not the dim alone: a nested dim's labels
        # identify a point only within its parents (https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis), so `(period,
        # timestep)` is what last-writer-wins applies to.
        rel = fold_axis(
            [seed, *(s.axis(dim) for s in holding)], schema.axis_key(dim), con
        )
        if rel is not None:
            axes[dim] = rel
    return Coords(
        schema=schema,
        axes=axes,
        groups=resolve_groups(schema, base, above, con),
        dead=_resolve_dead(schema, base, above, present, con),
    )


def mortal(schema: Schema) -> tuple[str, ...]:
    """The coordinates a fold keeps the dead labels of.

    One the owner map does not key, whose values naming a dead label only the
    read can drop (`_living`), and a dim a group's tuples name, which the
    writer checks them against (`write._require_living_tuples`). A keyed
    coordinate's values the fold drops itself (`fold_inputs`).

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    drawn = {d for g in schema.group_columns for d in schema.groups[g].over.values()}
    unkeyed = set(schema.broadcast_dims) - set(schema.partial_dims)
    return tuple(
        c for c in (*schema.dims, *schema.group_columns) if c in drawn | unkeyed
    )


def _resolve_dead(
    schema: Schema,
    base: Fold | None,
    above: Sequence[LayerSource],
    present: Sequence[set[str]],
    con: DuckDBPyConnection,
) -> dict[str, DuckDBPyRelation]:
    """Each `mortal` coordinate's dead labels: those whose winning row is a tombstone.

    The base's resolved axes and groups are tombstone-free, so its dead labels
    seed depth 0 from its own cache, a label a layer above restates reviving.
    Absent where nothing is dead.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    dead = {}
    for name in mortal(schema):
        if name in schema.groups:
            key: tuple[str, ...] = (name,)
            rows = [source.group(name) for source in above]
        else:
            key = schema.axis_key(name)
            rows = [s.axis(name) for s, names in zip(above, present) if name in names]
        seed = None if base is None else base.dead.get(name)
        if seed is not None:
            seed = seed.project(*(col(c) for c in key), lit(True).alias("deleted"))  # noqa: FBT003
        rel = dead_keys([seed, *rows], key, con)
        if rel is not None:
            dead[name] = rel
    return dead


def resolve_groups(
    schema: Schema,
    base: Fold | None,
    above: Sequence[LayerSource],
    con: DuckDBPyConnection,
) -> dict[str, DuckDBPyRelation]:
    """Fold every declared group to its resolved relation, keyed by its struct column.

    A group folds through `fold_axis` like any axis, keyed by the one column
    named for it: last-writer-wins per tuple, static columns (`into`,
    group properties) on the winning row, its own tombstones honoured, member
    order the file's row order.
    The base `Fold`'s resolved group seeds depth 0. Absent from the result where
    no layer wrote a row.

    Notes
    -----
    - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    groups = {}
    for group in schema.groups:
        seed = None if base is None else base.groups.get(group)
        rows = [seed, *(source.group(group) for source in above)]
        if all(rel is None for rel in rows):
            continue
        rel = fold_axis(rows, (group,), con)
        if rel is not None:
            groups[group] = rel
    return groups


@dataclass(frozen=True)
class Coords:
    """A record's schema, plus each declared dim's folded axis relation.

    They travel together because the fold needs both wherever it broadcasts a
    NULL against "all values of that dim".

    Parameters
    ----------
    schema : Schema
        The record's schema.
    axes : dict of str to DuckDBPyRelation
        Each declared dim's folded axis relation, full row rather than the key
        column alone - its properties ride along. A dim with no rows
        anywhere is absent rather than present-and-empty.
    groups : dict of str to DuckDBPyRelation
        Each declared group's folded relation, keyed by its struct column,
        carrying its static columns, in member order - a group folds like an
        axis, no owner map. Absent where no layer wrote a row.
    dead : dict of str to DuckDBPyRelation
        Each `mortal` coordinate's dead labels, keyed as its axis or group.

    Notes
    -----
    - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    - [the schema](https://energy-models.github.io/datarecord/design/schema/)
    """

    schema: Schema
    axes: dict[str, DuckDBPyRelation]
    groups: dict[str, DuckDBPyRelation] = field(default_factory=dict)
    dead: dict[str, DuckDBPyRelation] = field(default_factory=dict)

    def expand_dims(
        self,
        rel: DuckDBPyRelation,
        layer_keys: tuple[str, ...],
        con: DuckDBPyConnection,
    ) -> tuple[DuckDBPyRelation, dict[str, Expression]]:
        """Join `rel` against each of `layer_keys`' axis, broadcasting NULLs.

        Only a row of an attribute whose `dims` name the dim broadcasts: any
        other is NULL there in every layer, so its key needs no
        expansion, and expanding it would multiply its owner-map rows by the
        axis length for no change in ownership. A NULL of an attribute a trait
        narrows reaches only the labels carrying it (`categories.carriers`),
        and none where no label does.

        Parameters
        ----------
        rel : DuckDBPyRelation
            Carries an `attribute` column.
        layer_keys : tuple of str
            The broadcast coordinates of `schema.partial_dims`; a group's
            axis is its resolved relation.

        Returns
        -------
        DuckDBPyRelation
            `rel`, joined.
        dict of str to Expression
            Per dim, the expression to project for its (possibly broadcast)
            value - referencing `rel`'s original alias, since each join
            wraps the relation in a new auto-generated alias.

        Notes
        -----
        `rel` must carry a column for every dim in `layer_keys`, which
        `write_layer` enforces: a record whose frames do not is one the
        writer rejected, and binding here would resolve it as though the dim
        were broadcast everywhere.

        Notes
        -----
        - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
        - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        """
        alias = rel.alias
        exprs = {}
        for dim in layer_keys:
            axis = self.axes.get(dim, self.groups.get(dim))
            over = [
                a
                for a in self.schema.attributes
                if dim in self.schema.coordinates_of(a)
            ]
            if axis is None or not over:
                exprs[dim] = col(alias, dim)
                continue
            names, carriers = categories.carriers(
                self.schema, self.axes, self.groups, dim, over, con
            )
            plain = [lit(a) for a in over if a not in names]
            expanded = [col(alias, dim)]
            if plain:
                # `... = true` rather than the bare condition: an equality hashes,
                # a one-sided condition is a nested loop over every row and label.
                # An attribute not over `dim` holds NULL there for want of the
                # column, which is no broadcast.
                broadcasts = col(alias, dim).isnull() & col(alias, "attribute").isin(
                    *plain
                )
                key = axis.project(col(dim), lit(True).alias("_broadcast"))  # noqa: FBT003
                rel = rel.join(
                    key, broadcasts == col(key.alias, "_broadcast"), how="left"
                )
                expanded.append(col(key.alias, dim))
            if carriers is not None:
                key = _with_pass_row(
                    carriers.project(col(dim), col("attribute")), con
                ).set_alias(f"_carried_{len(exprs)}")
                narrowed = col(alias, dim).isnull() & col(alias, "attribute").isin(
                    *(lit(a) for a in names)
                )
                carried = duckdb.CaseExpression(narrowed, col(alias, "attribute"))
                rel = rel.join(
                    key,
                    sql(
                        f"{carried} IS NOT DISTINCT FROM {col(key.alias, 'attribute')}"
                    ),
                )
                expanded.append(col(key.alias, dim))
            exprs[dim] = coalesce(*expanded)
        return rel, exprs


def _with_pass_row(
    carriers: DuckDBPyRelation, con: DuckDBPyConnection
) -> DuckDBPyRelation:
    """`carriers` plus one all-NULL row, which every row not narrowed joins.

    What lets `expand_dims` join the carriers inner, so that a NULL no label
    carries reaches nothing, without a filter: a filter wraps the join in a new
    alias, which the caller's projection off the original one cannot bind.
    """
    dim, attribute = carriers.columns
    types = dict(zip(carriers.columns, carriers.types, strict=True))
    pass_row = con.sql("SELECT 1").project(
        lit(None).cast(types[dim]).alias(dim),
        lit(None).cast(types[attribute]).alias(attribute),
    )
    return carriers.union(pass_row)


# -- paths and probes -------------------------------------------------------


def materialised(revision_id: UUID, store: Store) -> bool:
    """Whether `revision_id`'s node caches are materialised.

    A node's caches are written together (`materialise`), so one map answers
    for all three, and for the resolved dims and schema beside them.

    This is a filesystem question rather than recorded state: layers are
    write-once, so a materialised cache is valid forever and its
    presence is the whole answer.

    Notes
    -----
    - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    # `inputs` answers for the rest: the maps are written together, and it is
    # the one kind every schema has, whatever groups it declares.
    uri = store.owner_map_uri(revision_id, "inputs")
    return try_read_parquet(uri, store.workspace.con) is not None


def sources_to_read(
    ancestry: list[UUID], store: Store, schema: Schema
) -> list[LayerSource]:
    """`ancestry` as the sources to fold, truncated at the deepest materialised node.

    A materialised owner map is already folded over everything above it, so
    nothing further up need be read: the truncation is *fewer sources* rather
    than a shorter list of UUIDs. The node stopped at stays a plain
    `ParquetLayer`; its `materialised(con)` yields the base `Fold` the live fold
    starts from, so the fold folds only the layers below it.

    Only proper ancestors count: the node being resolved is always read from its
    own layer, since stopping *at* it would return its cached answer instead of
    resolving it.

    Parameters
    ----------
    ancestry
        Root-first, ending in the node being resolved (`records.ancestry`).
    store
        Where the layers are.
    schema
        The record's one manifest, carried by every source so `write_layer`
        can read it off the layer it is handed.

    Returns
    -------
    list of LayerSource
        Root first, ending in the node's own layer.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    for depth in range(len(ancestry) - 2, -1, -1):
        if materialised(ancestry[depth], store):
            return [ParquetLayer(uid, schema, store) for uid in ancestry[depth:]]
    return [ParquetLayer(uid, schema, store) for uid in ancestry]


def _table_name(revision_id: UUID, kind: str) -> str:
    return f"owner_map_{kind}_{revision_id.hex}"


def _coord_table(kind: str, name: str, revision_id: UUID) -> str:
    """The shared table one folded axis or group is kept in.

    The name is hashed rather than spelled, being a caller's string that becomes
    an identifier.
    """
    digest = sha256(name.encode()).hexdigest()[:16]
    return f"{kind}_{digest}_{revision_id.hex}"


def _shared(
    con: DuckDBPyConnection, name: str, build: Callable[[], DuckDBPyRelation]
) -> DuckDBPyRelation:
    """Table `name`, built by whichever cursor misses it first.

    Two cursors missing at once both build, and DuckDB fails the second
    `create` with a write-write conflict rather than a name clash; what it
    would have created is the winner's table, so that is read instead. The
    conflict can come before the winner commits, when its table is not yet
    visible, so the `create` is retried until it either lands or meets the
    committed table.

    Notes
    -----
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    """
    try:
        return con.table(name)
    except duckdb.CatalogException:
        pass
    rel = build()
    while True:
        try:
            rel.create(name)
        except duckdb.TransactionException as e:
            if "conflict" not in str(e).lower():
                raise
            time.sleep(0.001)
            continue
        except duckdb.CatalogException:
            pass
        return con.table(name)


# -- fold relations -----------------------------------------------------


def _living(
    rel: DuckDBPyRelation, keys: Coords, unkeyed: Sequence[str]
) -> DuckDBPyRelation:
    """`rel` without the rows naming, in one of `unkeyed`, a dead label.

    The fold drops a removed label's rows by anti-joining the owner map on its
    key. A coordinate outside `partial` is no key column, so the fold cannot
    reach the rows naming a label there: they are dropped here instead, against
    that coordinate's dead labels (`Coords.dead`).

    Notes
    -----
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    schema = keys.schema
    for c in unkeyed:
        dead = keys.dead.get(c)
        key = (c,) if c in schema.groups else schema.axis_key(c)
        if dead is None or not set(key) <= set(rel.columns):
            continue
        rel = rel.set_alias("r").join(
            dead.set_alias("x"), null_safe("r", "x", key), how="anti"
        )
    return rel


def _deleted_relation(
    rel: DuckDBPyRelation | None,
    keys: Coords,
    con: DuckDBPyConnection,
    *,
    fixed: tuple[str, ...],
) -> DuckDBPyRelation:
    """One layer's tombstones of one membership, keyed as the map they filter.

    A deletion removes the thing whole - across every attribute and every dim,
    since a row exists or it does not. So the tombstone is its key columns and
    nothing else: no axis to scope it along, none to expand.

    Read from the same source relation the membership itself folds from
    (`source.axis(dim)`, `source.group(g)`), since reading membership from one
    file and deletions from another would resolve a deletion the map never saw.

    Parameters
    ----------
    rel
        The layer's rows of that membership, or `None` where it has none.
    fixed
        The key columns: a dim's `axis_key` for a label, the group's struct
        column for a group.

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    """
    schema = keys.schema
    if rel is None or "deleted" not in rel.columns:
        return _empty_relation(schema, con, *fixed)
    return rel.filter(col("deleted")).project(*(col(c) for c in fixed)).distinct()


def cast_declared(schema: Schema, rel: DuckDBPyRelation) -> DuckDBPyRelation:
    """`rel`, with its columns of a declared type cast, others as-is.

    Notes
    -----
    - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
    """
    duck_types = DuckTypes(rel)
    cols = [
        col(c).cast(duck_types(t)).alias(c) if (t := schema.column_type(c)) else col(c)
        for c in rel.columns
    ]
    return rel.project(*cols)


def _empty_relation(
    schema: Schema, con: DuckDBPyConnection, *columns: str
) -> DuckDBPyRelation:
    """A zero-row relation with `columns`, cast to their declared type, `VARCHAR` if none.

    Notes
    -----
    - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
    """
    return DuckTypes(con).empty_relation(
        **{c: schema.column_type(c) or nw.String() for c in columns}
    )


def with_columns(
    schema: Schema, rel: DuckDBPyRelation, *columns: str
) -> DuckDBPyRelation:
    """`rel` with any of `columns` it lacks added as typed NULLs.

    One file carries one attribute's coordinates, so a column another attribute
    uses is simply absent - and a coordinate an attribute is not addressed by
    means the value applies across every value of it, which is what NULL means.
    Materialising it here lets every path downstream project the column
    unconditionally instead of branching on its presence.

    Notes
    -----
    - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    """
    missing = [c for c in columns if c not in rel.columns]
    if not missing:
        return rel
    duck_types = DuckTypes(rel)
    added = [
        duck_types.null(schema.column_type(c) or nw.String()).alias(c) for c in missing
    ]
    return rel.project(star(), *added)


def _owned(dim: str) -> str:
    return f"__owned_{dim}"


def _as_stored(om: DuckDBPyRelation, dims: tuple[str, ...]) -> DuckDBPyRelation:
    """`om` with each of `dims` as its owning layer stored it, the owned value in `__owned_<dim>`.

    A raw row then finds its owned keys by NULL-safe equality, which hashes where
    `raw IS NULL OR raw IS NOT DISTINCT FROM owned` does not. A key its layer
    wrote both ways appears once per way. A flag field NULL from
    `UNION ALL BY NAME`, or missing from a map folded before the dim was
    declared, is a dim no row set: `varies` false, `broadcast` true.

    Notes
    -----
    - [resolving a relation](https://energy-models.github.io/datarecord/design/read-path/#resolving-a-relation)
    """
    types = dict(zip(om.columns, om.types, strict=True))
    for d in dims:
        stored = fn.list_concat(
            duckdb.CaseExpression(
                struct_field(om, "varies", d, lit(False)),
                fn.list_value(col(d)),
            ),
            duckdb.CaseExpression(
                struct_field(om, "broadcast", d, lit(True)),
                fn.list_value(lit(None).cast(types[d])),
            ),
        )
        om = om.project(
            star(exclude=(col(d),)), col(d).alias(_owned(d)), fn.unnest(stored).alias(d)
        )
    return om


def fold_inputs(
    source: LayerSource, keys: Coords, con: DuckDBPyConnection, parent: DuckDBPyRelation
) -> DuckDBPyRelation:
    """This layer's inputs map: its `inputs/` keys, folded over `parent`.

    A tombstone drops the parent rows keyed by its label: a `partial` dim's,
    a `partial` group's tuple. A label inside a struct is reached through its
    tuple's tombstone, which removing it wrote.

    Notes
    -----
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    schema = keys.schema
    rel = source.all_attributes("inputs")
    if rel is None:
        own = _empty_relation(schema, con, *schema.input_columns)
    else:
        # Every declared dim and group column too, not just `breakpoint`: one
        # file carries only its own attribute's columns, so a coordinate another
        # attribute uses is absent here and must read as NULL rather than fail
        # to bind.
        broadcast = schema.broadcast_dims
        rel = cast_declared(
            schema,
            with_columns(
                schema, rel, "breakpoint", *schema.group_columns, *schema.dims
            ),
        )
        rel, dims = keys.expand_dims(
            rel.set_alias("i"),
            tuple(d for d in schema.partial_dims if d in broadcast),
            con,
        )
        # Each broadcast dim is carried twice: the (possibly broadcast) key
        # value, and `_raw_<dim>` as the row stored it. The flags describe the
        # stored form - whether a row set the dim or left it NULL - so they
        # cannot be read off the expanded value, which is never NULL once
        # broadcast (https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule).
        # `dims` covers the partial ones, expanded; the rest pass through as
        # stored. Together they are every declared dim, exactly once.
        expanded = set(dims)
        tagged = rel.project(
            *(
                col("i", d)
                for d in (*schema.group_columns, *schema.dims)
                if d not in expanded
            ),
            *(expr.alias(d) for d, expr in dims.items()),
            *(col("i", d).alias(f"_raw_{d}") for d in broadcast),
            col("i", "attribute"),
            lit(str(source.layer_id)).cast(LAYER_UUID_TYPE).alias(LAYER_COLUMN),
            col("i", "breakpoint"),
        )
        own = tagged.aggregate(
            [
                *(col(c) for c in (*schema.input_key, LAYER_COLUMN)),
                # A field aggregating to NULL - what a map written before the
                # dim was declared yields - reads as "not set", the same as
                # false.
                struct_of(
                    {d: fn.bool_or(col(f"_raw_{d}").isnotnull()) for d in broadcast}
                ).alias("varies"),
                struct_of(
                    {d: fn.bool_or(col(f"_raw_{d}").isnull()) for d in broadcast}
                ).alias("broadcast"),
                fn.bool_or(col("breakpoint").isnotnull()).alias("breakpoints"),
            ]
        )

    # Each membership this layer tombstones anti-joins `parent`, keyed as it is
    # in `input_key` (https://energy-models.github.io/datarecord/design/read-path/#owner-map).
    keyed = set(schema.input_key)
    # A partial dim's `axis_key` is always in `input_key`, so a miss there is a
    # nested dim whose parents the schema failed to keep in the fold key, and
    # the assert names it.
    partial_dims = [d for d in schema.partial or () if d in schema.dimensions]
    for d in partial_dims:
        assert keyed.issuperset(schema.axis_key(d)), (
            f"partial dim keyed by {schema.axis_key(d)} outruns `input_key` "
            f"{schema.input_key}; a nested dim needs its parents in the fold key"
        )
    memberships = [
        *(
            (
                _deleted_relation(source.group(g), keys, con, fixed=(g,)),
                null_safe("x", "p", (g,)),
            )
            for g in schema.group_columns
            if g in keyed
        ),
        *(
            (
                _deleted_relation(source.axis(d), keys, con, fixed=schema.axis_key(d)),
                null_safe("x", "p", schema.axis_key(d)),
            )
            for d in partial_dims
        ),
    ]
    kept = parent.set_alias("p")
    for deleted, on in memberships:
        kept = kept.join(deleted.set_alias("x"), on, how="anti").set_alias("p")
    # Parent minus what this layer restates, union this layer's own.
    kept = kept.join(
        own.set_alias("o"), null_safe("p", "o", schema.input_key), how="anti"
    )
    return union_all_by_name([kept, own], con)


def _fold_map(
    sources: Sequence[LayerSource],
    con: DuckDBPyConnection,
    schema: Schema,
    *,
    kind: str,
    columns: Callable[[Coords], tuple[str, ...]],
    fold: Callable[
        [LayerSource, Coords, DuckDBPyConnection, DuckDBPyRelation], DuckDBPyRelation
    ],
) -> DuckDBPyRelation:
    """A record's owner map of one kind, folded down over `sources`.

    Only `inputs` remains a kind; the axes fold to a resolved copy instead
    (`resolve_coords`). The deepest materialised source's map is the fold's
    *seed* rather than a step of it: it is already folded over everything at or
    below it, so it is read as the starting relation (`_frozen_table`) and only
    the sources above it are folded on top.

    Notes
    -----
    - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    """
    base, above = split = _base_and_above(sources, con, schema)
    keys = resolve_coords(schema, sources, con, split)
    if base is None:
        rel = _empty_relation(keys.schema, con, *columns(keys))
    else:
        seed = sources[: len(sources) - len(above)]
        rel = _frozen_table(
            seed[-1].layer_id, seed, con, keys.schema, kind=kind, read=base.owner_map
        )

    for source in above:
        rel = fold(source, keys, con, rel)
    return rel


def map_kinds(
    schema: Schema,
) -> dict[str, tuple[Callable[[Coords], tuple[str, ...]], Callable]]:
    """This schema's owner maps, each a `kind` -> (column set, fold) pair.

    One kind: `inputs`, the only relation with a genuine key/row split - an
    attribute's ownership spans every `inputs/<attr>.parquet`. Every axis is a
    single keyed file resolved inline (`resolve_coords`), so none needs a map.

    Notes
    -----
    - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    """
    return {"inputs": (lambda keys: keys.schema.input_columns, fold_inputs)}


def _fold_kind(
    kind: str,
    sources: Sequence[LayerSource],
    con: DuckDBPyConnection,
    schema: Schema,
) -> DuckDBPyRelation:
    columns, fold = map_kinds(schema)[kind]
    return _fold_map(sources, con, schema, kind=kind, columns=columns, fold=fold)


def frozen_prefix(sources: Sequence[LayerSource]) -> int:
    """How many leading sources cannot change under a reader.

    The one rule the source list has to carry: **the fold is materialised up to
    the last frozen source; everything after it stays a relation.** Everything a
    `Resolver` caches rests on layers being write-once, which a staging area is
    not - so a staged source ends the prefix, and a frozen one under it stays
    outside without either needing to know about the other.

    Notes
    -----
    - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
    """
    prefix = 0
    for source in sources:
        if not source.frozen:
            break
        prefix += 1
    return prefix


def _table(
    revision_id: UUID,
    sources: Sequence[LayerSource],
    con: DuckDBPyConnection,
    schema: Schema,
    *,
    kind: str,
) -> DuckDBPyRelation:
    """One owner map for `revision_id`, materialised as far as `frozen` allows.

    The frozen prefix is folded once and kept as a connection-scoped table,
    which never needs invalidating since layers are write-once. Whatever follows
    it is folded on top per call and handed back as a relation, so a staging
    area's edits are picked up with no bookkeeping at all: a relation over a
    staging table reads whatever the table holds when it is collected.

    Notes
    -----
    - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    """
    prefix = frozen_prefix(sources)
    rel = _frozen_table(revision_id, sources[:prefix], con, schema, kind=kind)
    if prefix == len(sources):
        return rel

    keys = resolve_coords(schema, sources, con)
    _, fold = map_kinds(schema)[kind]
    for source in sources[prefix:]:
        rel = fold(source, keys, con, rel)
    return rel


def _frozen_table(
    revision_id: UUID,
    sources: Sequence[LayerSource],
    con: DuckDBPyConnection,
    schema: Schema,
    *,
    kind: str,
    read: DuckDBPyRelation | None = None,
) -> DuckDBPyRelation:
    """The frozen prefix's owner map, its own materialised one or a cached fold.

    Keyed by `revision_id` rather than by the prefix: the prefix *is* what that
    node resolves from, a staged source only ever being appended after it. The
    table is shared by every cursor on the workspace and carries no schema in
    its name, so a schema widened since the fold reads it as it is, a column it
    lacks padded as unset. A persisted map is cast, parquet not carrying the
    declared types.

    The one place a cached map enters a fold: a materialised seed is read here
    too (`_fold_map`).

    Parameters
    ----------
    read
        The prefix's materialised map where the caller already holds it.

    Notes
    -----
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    """
    last = sources[-1] if sources else None
    rel = read
    if (
        rel is None
        and isinstance(last, ParquetLayer)
        and last.revision_id == revision_id
    ):
        rel = try_read_parquet(last.store.owner_map_uri(revision_id, kind), con)
    if rel is not None:
        rel = cast_declared(schema, rel)
    elif not sources:
        # Nothing frozen to fold, which is a `WorkingRecord` over a base that is
        # itself unfrozen; the tail folds onto an empty map.
        columns, _ = map_kinds(schema)[kind]
        return _empty_relation(schema, con, *columns(Coords(schema=schema, axes={})))
    else:
        rel = _shared(
            con,
            _table_name(revision_id, kind),
            lambda: _fold_kind(kind, sources, con, schema),
        )
    return with_columns(schema, rel, *schema.input_key)


def _frozen_coords(
    revision_id: UUID,
    sources: Sequence[LayerSource],
    con: DuckDBPyConnection,
    schema: Schema,
) -> list[tuple[str, str]]:
    """The `(kind, name)` of every axis and group this frozen fold resolved.

    Each is a shared table (`_coord_table`); the list is one more, created after
    them, so a reader finding it finds every table it names.

    Notes
    -----
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    """

    def fold() -> DuckDBPyRelation:
        coords = resolve_coords(schema, sources, con)
        made = [
            *(("dims", dim, rel) for dim, rel in coords.axes.items()),
            *(("group", group, rel) for group, rel in coords.groups.items()),
            *(("dead", name, rel) for name, rel in coords.dead.items()),
        ]
        for kind, name, rel in made:
            table = _coord_table(kind, name, revision_id)
            _shared(con, table, lambda: rel)  # noqa: B023 - called before `rel` moves on
        return con.sql(
            "SELECT unnest($kinds::VARCHAR[]) AS kind, unnest($names::VARCHAR[]) AS name",
            params={"kinds": [k for k, _, _ in made], "names": [n for _, n, _ in made]},
        )

    rows = _shared(con, f"coords_{revision_id.hex}", fold).fetchall()
    return [(kind, name) for kind, name in rows]


def materialise(
    revision_id: UUID, sources: Sequence[LayerSource], store: Store
) -> None:
    """Write `revision_id`'s node caches: owner maps and resolved dims.

    Purely additive. It changes no answer a read would give, only how many
    layers a read touches to reach it: once these files exist, a descendant's
    fold stops here rather than walking further up (`sources_to_read`).

    Safe to call more than once, and safe to call on any node - layers are
    write-once, so what is folded here cannot later become stale. Two writers
    write the same content, so racing is harmless.

    `owner_map/inputs.parquet` is what `materialised` reads as the whole
    cache's presence, so it is written last: a reader that sees it finds the
    rest, and a write that fails part-way leaves the node unmaterialised.

    Notes
    -----
    - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    schema = read_schema(store)
    con = store.workspace.con
    _materialise_dims(revision_id, sources, store, schema)
    ensure_local_dir(store.resolved_dir(revision_id) + "owner_map/")
    for kind in sorted(map_kinds(schema), key=lambda kind: kind == "inputs"):
        uri = store.owner_map_uri(revision_id, kind)
        _to_parquet(_fold_kind(kind, sources, con, schema), uri)


def _to_parquet(rel: DuckDBPyRelation, uri: str) -> None:
    """`rel.to_parquet(uri)`, never visible half-written where `uri` is local.

    `to_parquet` creates the file at its final path before it is complete, and
    a reader meeting it mid-write fails rather than misses, so a local file is
    written under a temporary name and renamed into place.
    """
    if "://" in uri:
        rel.to_parquet(uri)
        return
    tmp = f"{uri}.{uuid4().hex}.tmp"
    rel.to_parquet(tmp)
    os.replace(tmp, uri)


def _to_parquet_unless_empty(
    rel: DuckDBPyRelation, uri: str, con: DuckDBPyConnection
) -> None:
    """`_to_parquet`, writing nothing where `rel` has no row.

    `rel` is evaluated once, into a temporary table, rather than once to
    probe and again to write.
    """
    table = f"_unless_empty_{uuid4().hex}"
    rel.create(table)
    try:
        rows = con.table(table)
        if rows.limit(1).fetchone() is not None:
            _to_parquet(rows, uri)
    finally:
        con.execute(f"DROP TABLE {table}")


def _materialise_dims(
    revision_id: UUID,
    sources: Sequence[LayerSource],
    store: Store,
    schema: Schema,
) -> None:
    """Fold this node's resolved axes into its node cache, not its layer.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    con = store.workspace.con
    dims = resolve_coords(schema, sources, con)
    base = store.resolved_dir(revision_id) + "dims/"
    ensure_local_dir(base)
    for dim, rel in dims.axes.items():
        _to_parquet(rel, f"{base}{dim}.parquet")
    groups = store.resolved_dir(revision_id) + "groups/"
    ensure_local_dir(groups)
    for group, rel in dims.groups.items():
        _to_parquet(rel, f"{groups}{group}.parquet")
    dead = store.resolved_dir(revision_id) + "dead/"
    ensure_local_dir(dead)
    for name, rel in dims.dead.items():
        _to_parquet_unless_empty(rel, f"{dead}{name}.parquet", con)


# -- the schema (https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record) ---------------------------------------------


def read_schema(store: Store) -> Schema:
    """The record's one schema, read from beside `store`'s layers.

    No fold and no ancestry: a schema is not layered data. One file makes it a
    property of the record, knowable before any layer is read and stated once
    for a hundred-layer tree. A record that declares none reads as an empty
    `Schema`, which declares no dims and no attributes.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """
    found = store.files.read_text(store.manifest_uri)
    return Schema() if found is None else Schema.model_validate_json(found[0])


def write_schema(schema: Schema, store: Store) -> None:
    """Write the record's one schema, beside the layers.

    Amending it is a schema change rather than a patch, so this replaces the
    file: `Schema.compatible_with` is what says whether existing layers
    survive the amendment.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
    """
    store.files.write_text(store.manifest_uri, schema.model_dump_json(), expect=None)


# -- public API -------------------------------------------------------------


@dataclass(frozen=True)
class Resolver:
    """A record's resolved view: owner map, dims, schema, and the relations over them.

    The cached artifacts and the reads gated by them
    (`attribute`/`group_frame`/`fold.flags`) live
    together because every one of the latter is a semi-join against the former.
    Tool-agnostic throughout: the long relations here are what a tool
    (`datarecord.tools`) builds its own object from.

    Notes
    -----
    `sources` is root first, ending in the layer being resolved, and already
    truncated at the deepest materialised ancestor (`sources_to_read`) - so a
    hundred-layer tree with a materialised parent resolves from two entries. A
    `WorkingRecord`'s staged rows are one more entry on the end, which is the
    whole of what makes staging a layer.

    Nothing up to the last `frozen` source can go stale: layers are write-once,
    so the fold over them is materialised and cached. Past it there is nothing
    to invalidate, because nothing is materialised - `dims` and the maps re-fold
    the unfrozen tail per access, over a relation that reads whatever the
    staging tables hold when it is collected.

    Notes
    -----
    - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    - [resolving a relation](https://energy-models.github.io/datarecord/design/read-path/#resolving-a-relation)
    - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
    """

    revision_id: UUID
    sources: list[LayerSource]
    workspace: Workspace
    schema: Schema
    """This record's one manifest, resolved by the caller and passed in.

    A plain field, not a lazy read: every fold needs it, both construction sites
    already hold it (a tree node reads its store's, a standalone directory its
    own), and each source carries the same reference so `write_layer` can
    read one off the layer it is handed.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """

    def with_source(self, source: LayerSource) -> Resolver:
        """This cache with one more layer folded on top.

        What a `WorkingRecord` builds to read its staged rows: the staged source
        is the last entry, resolved over whatever the record was reading before.
        The schema comes along unchanged - an edit is made *under* a
        declaration, never one that redeclares.

        Notes
        -----
        - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
        - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
        """
        return Resolver(
            self.revision_id, [*self.sources, source], self.workspace, self.schema
        )

    @property
    def con(self) -> DuckDBPyConnection:
        """The calling thread's cursor: every relation this builds lands on it.

        Notes
        -----
        - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
        """
        return self.workspace.con

    def _map(self, kind: str) -> DuckDBPyRelation:
        return _table(self.revision_id, self.sources, self.con, self.schema, kind=kind)

    def source_for(self, layer_uuid: UUID) -> LayerSource:
        """The source the fold stamped `layer_uuid` from.

        How a winning row is read back: the map names which layer owns a key,
        and the row itself comes from that layer's own member.

        Notes
        -----
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        """
        for source in self.sources:
            if source.layer_id == layer_uuid:
                return source
        # A layer the map names but the source list does not hold: the map was
        # materialised over a longer ancestry than this node reads, so the
        # winning row is still in that layer's own directory, in the same store.
        store = next(s.store for s in self.sources if isinstance(s, ParquetLayer))
        return ParquetLayer(layer_uuid, self.schema, store)

    @property
    def fold(self) -> Fold:
        """This node's resolved view as one `Fold`: the folded coords and map.

        Assembled from `dims` (the folded axes and groups) and `_map("inputs")`
        (the folded owner map), both of which carry their own frozen-scoped
        cache, so `fold` re-wraps rather than re-folds.
        """
        coords = self.dims
        return Fold(
            schema=self.schema,
            axes=coords.axes,
            groups=coords.groups,
            owner_map=self._map("inputs"),
            dead=coords.dead,
        )

    @property
    def inputs(self) -> DuckDBPyRelation:
        """The resolved inputs owner map: which layer owns each attribute key.

        Ownership only: a tombstoned label or group tuple drops the keys naming
        it as the map folds (`fold_inputs`), not here.

        Notes
        -----
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        """
        return self.fold.owner_map

    def group(self, name: str) -> DuckDBPyRelation | None:
        """One declared group's resolved relation, folded like an axis.

        The winning row per tuple, static columns carried, in member order.
        `None` where no layer wrote a row.

        Notes
        -----
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        return self.dims.groups.get(name)

    @property
    def frozen(self) -> bool:
        """Whether every source is frozen, so a fold over them cannot go stale.

        What decides between caching an answer and re-folding per access - here
        and in the `Record` over this resolver, where the same question governs
        its key sets. False exactly when the last source is a staging area.
        `all(s.frozen for s in sources)`, distinct from `frozen_prefix`, which
        counts how far the leading run is frozen to decide materialisation.

        Notes
        -----
        - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
        """
        return frozen_prefix(self.sources) == len(self.sources)

    @property
    def dims(self) -> Coords:
        """Every declared dim's folded axis relation.

        Where every source is frozen the fold cannot go stale, so each axis and
        group is a shared table (`_frozen_coords`), the same rule `_map`
        applies; a relation over one is built per call on the calling thread's
        cursor. A schema widened since the fold reads it as it is, a compatible
        widening changing no column an axis or group already has. Past a
        staging area the whole fold is redone per call.

        Notes
        -----
        - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
        - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
        - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
        """
        con = self.con
        if not self.frozen:
            return resolve_coords(self.schema, self.sources, con)
        tables = {
            (kind, name): con.table(_coord_table(kind, name, self.revision_id))
            for kind, name in self._coord_names
        }
        return Coords(
            schema=self.schema,
            axes={n: rel for (k, n), rel in tables.items() if k == "dims"},
            groups={n: rel for (k, n), rel in tables.items() if k == "group"},
            dead={n: rel for (k, n), rel in tables.items() if k == "dead"},
        )

    @cached_property
    def _coord_names(self) -> list[tuple[str, str]]:
        """Which axes and groups the frozen fold resolved - plain data, any thread."""
        return _frozen_coords(self.revision_id, self.sources, self.con, self.schema)

    def axes(self) -> set[str]:
        """Which dims this fold has an axis for - the shared `LayerData` name.

        Notes
        -----
        - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
        """
        return set(self.dims.axes)

    def axis(self, dim: str) -> DuckDBPyRelation | None:
        """One dim's folded axis relation, `None` where no layer wrote one.

        Notes
        -----
        - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
        """
        return self.dims.axes.get(dim)

    def groups(self) -> set[str]:
        """Declared groups with any resolved row.

        Notes
        -----
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        return set(self.dims.groups)

    def attributes(self, kind: str = "inputs") -> list[str]:
        """Every attribute of `kind` any layer owns a row for.

        `inputs` reads the owner map, already folded over every layer;
        `outputs` reads this record's own layer alone, results not overlaying.

        Notes
        -----
        - [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
        """
        if kind == "inputs":
            return self.fold.attributes()
        rel = self.sources[-1].all_attributes("outputs")
        if rel is None:
            return []
        return list(distinct_values(rel, "attribute"))

    def attribute(self, name: str, kind: str = "inputs") -> DuckDBPyRelation:
        """The resolved long relation for one attribute of `kind`.

        The shared `LayerData` name for `relation`/`outputs`: `inputs` folds
        over every layer, `outputs` reads this record's own layer alone,
        results not overlaying. Never `None`, unlike a `LayerSource`'s own
        read - an attribute with no owning layer still resolves to an empty
        relation in the long schema, which lets the catalog `default` apply
        uniformly.

        Notes
        -----
        - [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
        - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
        """
        if kind == "inputs":
            return self._relation(name)
        return self._outputs(name)

    def _relation(self, attribute: str) -> DuckDBPyRelation:
        """The resolved long relation for one input attribute.

        Joins the owning layers' rows to the `inputs` map; a broadcast dim
        stored NULL takes each value it is owned for.

        Returns
        -------
        DuckDBPyRelation
            Unmaterialised, in the long schema (`schema.long_columns`).
            Empty when no layer wrote the attribute - the consumer then
            applies the catalog `default`.

        Notes
        -----
        - [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
        - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
        - [resolving a relation](https://energy-models.github.io/datarecord/design/read-path/#resolving-a-relation)
        """
        con = self.con
        om = self.inputs.filter(col("attribute") == lit(attribute))
        keys = self.dims
        partial_dims = keys.schema.partial_dims
        # This attribute's own columns, not every declared dim: one file per
        # attribute is one column set per attribute (https://energy-models.github.io/datarecord/design/format/#the-long-schema).
        columns = keys.schema.long_columns_for(attribute)
        # The join's arms are the map's key columns this attribute's file also
        # carries. A dim outside `partial` is in neither: it is not in the map
        # at all, so it constrains nothing and passes straight through.
        #
        # Of those that are, each - a dim or a group - matches NULL-aware
        # (https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule).
        coordinates = set(keys.schema.coordinates_of(attribute))
        broadcast_over = tuple(d for d in partial_dims if d in coordinates)
        layers = [
            with_columns(keys.schema, rel, *columns).project(
                lit(layer_uuid).alias(LAYER_COLUMN), star()
            )
            for layer_uuid in self._layers_owning(attribute)
            if (rel := self.source_for(layer_uuid).attribute(attribute)) is not None
        ]
        if not layers:
            return _empty_relation(keys.schema, con, *columns)

        unkeyed = [c for c in columns if c not in partial_dims]
        return _living(
            union_all_by_name(layers, con)
            .set_alias("l")
            .join(
                _as_stored(om, broadcast_over).set_alias("o"),
                null_safe("l", "o", (LAYER_COLUMN, *broadcast_over)),
            )
            .project(
                *(
                    coalesce(col("l", dim), col("o", _owned(dim))).alias(dim)
                    if dim in broadcast_over
                    else col("l", dim)
                    for dim in columns
                )
            ),
            keys,
            unkeyed,
        )

    def _layers_owning(self, attribute: str) -> list[UUID]:
        """The layers owning any key of `attribute`, whose rows `_relation` reads.

        Where every source is frozen, one scan of the map answers every
        attribute and is kept; otherwise the map may change under the reader,
        so each call asks for its own attribute.
        """
        if self.frozen:
            return self._cached_layers_owning.get(attribute, [])
        om = self.inputs.filter(col("attribute") == lit(attribute))
        return [u for (u,) in om[LAYER_COLUMN].distinct().fetchall()]

    @cached_property
    def _cached_layers_owning(self) -> dict[str, list[UUID]]:
        """`_layers_owning` for every attribute, where every source is frozen.

        Plain data any thread computes the same, so it is kept on the resolver
        rather than as a shared table beside the owner map it is read from.

        Notes
        -----
        - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
        """
        rows = self.inputs.aggregate(
            "attribute, list(DISTINCT layer_uuid)", "attribute"
        ).fetchall()
        return dict(rows)

    def _outputs(self, attribute: str) -> DuckDBPyRelation:
        """A result attribute from this record's own layer; outputs do not overlay.

        No fold and no owner map: if this layer has no `outputs/`, the record
        has no results - an ancestor's are not inherited.

        Notes
        -----
        - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
        """
        rel = self.sources[-1].attribute(attribute, "outputs")
        if rel is not None:
            return rel
        return _empty_relation(self.schema, self.con, *self.schema.long_columns)

    def group_frame(self, group: str) -> DuckDBPyRelation | None:
        """One group's resolved rows, folded like an axis, in member order.

        The folded relation is
        already the winning row per tuple, carrying every non-key column -
        a group property, an `into` label - in member order, read
        inline with no owner map. `None` where no layer wrote a row; empty, not
        `None`, where every row written is tombstoned.

        Notes
        -----
        - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        return self.group(group)


@dataclass(frozen=True)
class PinnedResolver(Resolver):
    """A `Resolver` folding its unfrozen tail once rather than per access.

    For a reader that reads many keys while nothing stages, as `write_layer`
    does: the folded coords and owner map are built on first access and kept,
    so each key costs its own join rather than a re-fold. Held correct only
    while no source changes, and only on the cursor of the thread that built
    it, the relations kept being planned on that cursor. The owner map is a
    table in the database until `release`, which the reader must call.

    Notes
    -----
    - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    """

    @classmethod
    def of(cls, resolver: Resolver) -> PinnedResolver:
        """`resolver` pinned at what its sources hold now."""
        return cls(
            resolver.revision_id, resolver.sources, resolver.workspace, resolver.schema
        )

    @cached_property
    def dims(self) -> Coords:  # type: ignore[override]
        return super().dims

    @cached_property
    def fold(self) -> Fold:  # type: ignore[override]
        fold = super().fold
        fold.owner_map.create(self._table)
        return dataclasses.replace(fold, owner_map=self.con.table(self._table))

    @cached_property
    def _table(self) -> str:
        return f"_pinned_{uuid4().hex}"

    def release(self) -> None:
        """Drop the table the fold is held in; nothing reads the fold after."""
        if "fold" in self.__dict__:
            self.con.execute(f"DROP TABLE IF EXISTS {self._table}")

    def _layers_owning(self, attribute: str) -> list[UUID]:
        return self._cached_layers_owning.get(attribute, [])
