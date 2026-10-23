# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Relation helpers for the record layer.

Each takes the connection it composes on as a parameter; where a connection
comes from is the `Workspace`'s business, and paths are a `Store`'s.

Nothing here knows about a modelling framework: every column is typed as the
*schema* declares it, whatever a tool's registry holds, so a record whose labels
no tool recognises still reads and it is a tool's `verify` that reports them.

Notes
-----
- [the schema](https://energy-models.github.io/datarecord/design/schema/)
- [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
- [module layout](https://energy-models.github.io/datarecord/design/module-layout/)
"""

import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import partial, reduce
from glob import glob
from pathlib import Path
from typing import Any

import duckdb
import narwhals as nw
import narwhals._duckdb.utils as _nw_duckdb
from duckdb import CoalesceOperator as coalesce
from duckdb import ColumnExpression as col
from duckdb import ConstantExpression as lit
from duckdb import DuckDBPyConnection, DuckDBPyRelation, Expression, FunctionExpression
from duckdb import SQLExpression as sql
from duckdb import StarExpression as star
from narwhals._utils import Version


class _Functions:
    """`fn.bool_or(x)` for `FunctionExpression("bool_or", x)`.

    Attribute access reads closer to the SQL it builds than a name-as-string
    call does, and keeps aggregates out of `SQLExpression` strings, where a
    column name would have to be quoted by hand.
    """

    def __getattr__(self, name: str) -> Callable[..., Expression]:
        return partial(FunctionExpression, name)


fn = _Functions()


def try_read_parquet(
    uri: str, con: DuckDBPyConnection, **kwargs: object
) -> DuckDBPyRelation | None:
    """`con.read_parquet(uri)`, or `None` if `uri` (possibly a glob) matches nothing.

    Parameters
    ----------
    uri
        Path or glob to read, local or remote.
    con
        Connection to read with.
    **kwargs
        Forwarded to `con.read_parquet`.

    Returns
    -------
    DuckDBPyRelation | None
        The relation, or `None` if `uri` matches no files.

    Raises
    ------
    duckdb.Error
        If the read fails for any reason other than a local or remote miss
        (e.g. DNS/TLS/timeout) - a connection failure should not be mistaken
        for a missing layer.

    Notes
    -----
    A local miss is answered without asking DuckDB at all. Inside a transaction
    a failed read *aborts* it, and catching the exception here does not undo
    that - every later statement on the connection would fail until a rollback,
    which would discard whatever the transaction had staged. A missing kind is
    ordinary (an attribute a layer never wrote), so it must not depend on being
    outside one.
    """
    if "://" not in uri and not (
        glob(uri) if any(c in uri for c in "*?[") else Path(uri).exists()
    ):
        return None
    try:
        return con.read_parquet(uri, **kwargs)  # type: ignore[arg-type]
    except duckdb.HTTPException as e:
        # This duckdb build exposes no status code, only the message ("HTTP
        # Error: ... (HTTP 404 Not Found)"). 403 also counts as a miss: S3
        # signals a missing key that way when the caller lacks ListBucket.
        if "HTTP 404" in str(e) or "HTTP 403" in str(e):
            return None
        raise
    except duckdb.IOException as e:
        if "No files found" in str(e):
            return None
        raise


def parquet_names(dir_uri: str, con: DuckDBPyConnection) -> set[str]:
    """Basenames of the `*.parquet` files directly under `dir_uri`.

    One listing regardless of how many files exist there, local or remote -
    what a caller otherwise probing one filename at a time (`try_read_parquet`
    per candidate) should glob instead.
    """
    rows = con.sql(
        "SELECT file FROM glob(?)", params=[f"{dir_uri}*.parquet"]
    ).fetchall()
    return {os.path.basename(row[0]) for row in rows}


def union_all_by_name(
    rels: Sequence[DuckDBPyRelation], con: DuckDBPyConnection
) -> DuckDBPyRelation:
    """Fold relations pairwise through `UNION ALL BY NAME`.

    The local names `u` and `rel` are load-bearing: DuckDB's replacement scan
    binds them by *name* out of this frame's locals, so the SQL below reads
    them despite them looking unused. Renaming either silently returns a short
    union; `test_union_all_by_name_folds_every_relation` pins it.

    Not `con.register`: measured at 2.2-2.6x slower here, widening with layer
    count (the deep-overlay case materialised caches exist to make cheap), and it leaves a
    named view per call on a connection that outlives the fold.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    - [resolving a relation](https://energy-models.github.io/datarecord/design/read-path/#resolving-a-relation)
    """
    u = rels[0]
    for rel in rels[1:]:  # noqa: F841 - bound by name in the SQL below
        u = con.sql("FROM u UNION ALL BY NAME FROM rel")
    return u


def ex_all(exprs: Iterable[Expression]) -> Expression:
    """AND every expression in `exprs` together."""
    return reduce(lambda x, y: x & y, exprs)


def null_safe(alias_a: str, alias_b: str, columns: Iterable[str]) -> Expression:
    """NULL-safe equality on `columns`, between two aliased relations.

    What an address coordinate is matched on everywhere: a row exists or it does
    not, so NULL means "this key has no value there" and must match the same
    NULL on the other side, which a plain `=` never does.
    """
    return ex_all(
        sql(f"{col(alias_a, c)} IS NOT DISTINCT FROM {col(alias_b, c)}")
        for c in columns
    )


def distinct_values(
    rel: DuckDBPyRelation, column: str, *, order: bool = True
) -> tuple[Any, ...]:
    """`rel`'s distinct values of `column`, as a tuple.

    What keys a `LazyFrames` built over a relation: the values are read from a
    column rather than from a directory listing, so one code path serves a local
    directory and a remote prefix alike.
    """
    projected = rel.project(column).distinct()
    if order:
        projected = projected.order(column)
    return tuple(r[0] for r in projected.fetchall())


def as_relation(frame: nw.LazyFrame, con: DuckDBPyConnection) -> DuckDBPyRelation:
    """One narwhals frame as a DuckDB relation, without collecting where possible.

    A DuckDB-backed frame is already a plan, so it passes straight through; any
    other backend is collected to arrow and re-registered. The one boundary where
    a native representation is reached, shared by the write and edit paths.

    Raises
    ------
    ValueError
        For a relation on another connection, or another thread's cursor:
        copying it over would collect it on a connection the caller never
        asked to read.

    Notes
    -----
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    """
    native = frame.to_native()
    if isinstance(native, DuckDBPyRelation):
        try:
            con.sql("FROM native")
        except duckdb.InvalidInputException as e:
            msg = (
                "this relation was built on another connection or thread; build "
                "the frame on `record.con` in this thread, or hand over a "
                "non-DuckDB frame to land"
            )
            raise ValueError(msg) from e
        return native
    arrow = frame.collect(backend="pyarrow").to_native()  # noqa: F841 - bound by name
    return con.sql("FROM arrow")


def ensure_local_dir(uri: str, *, parent: bool = False) -> None:
    """Create `uri`'s directory where it is a local path, a no-op for a remote one.

    A remote store needs no directory created; a local write does, and a record
    that wrote nothing to its layer has no directory yet either.

    Parameters
    ----------
    parent
        `uri` names a file whose directory is created, rather than the directory
        itself.
    """
    if "://" in uri:
        return
    path = Path(uri)
    (path.parent if parent else path).mkdir(parents=True, exist_ok=True)


def struct_of(fields: Mapping[str, Expression]) -> Expression:
    """A struct expression: field name to the expression for its value.

    A struct rather than a column per field, because it comes back as a dict
    keyed by name: the caller filters it by name instead of counting columns
    into a positional slice.

    `struct_pack` is what says this in DuckDB, and the field names are its
    *keyword* arguments - which `FunctionExpression` cannot pass, being
    positional-only. So the call is assembled as text here and the values are
    interpolated as the expressions they already are, keeping SQL text out of
    every caller.

    Never empty, DuckDB having no empty struct.
    """
    packed = ", ".join(f"{col(name)} := {value}" for name, value in fields.items())
    return sql(f"struct_pack({packed})")


def struct_field(
    rel: DuckDBPyRelation, column: str, name: str, default: Expression
) -> Expression:
    """Struct `column`'s field `name` in `rel`, `default` where NULL or absent.

    Whether the field exists is read off `rel`'s type as the plan is built, so
    a struct lacking it costs nothing per row - where `struct_extract` would
    fail to bind.
    """
    fields = dict(rel.types[rel.columns.index(column)].children)
    if name not in fields:
        return default
    return coalesce(fn.struct_extract(col(column), lit(name)), default)


class DuckTypes:
    """Builds DuckDB types and typed shapes from narwhals dtypes, just in time.

    Built once per connection and called per dtype - the constructor's
    relation is where a timezone-aware `Datetime` resolves its zone (DuckDB
    keeps timezone on the connection, not the dtype), and is fetched at most
    once no matter how many dtypes this instance translates.

    Reaches into narwhals' private DuckDB backend
    (`narwhals._duckdb.utils.narwhals_to_native_dtype`) rather than a local
    translation table - unversioned within the `narwhals>=2,<3` pin, so
    `pixi run test` is what catches a break, not a type error here.

    Parameters
    ----------
    rel_or_con
        A connection is queried for the throwaway relation
        `DeferredTimeZone` needs; a relation already in hand is used as-is,
        skipping that query.
    """

    deferred_tz: _nw_duckdb.DeferredTimeZone
    con: DuckDBPyConnection | None

    def __init__(self, rel_or_con: DuckDBPyRelation | DuckDBPyConnection):
        if isinstance(rel_or_con, DuckDBPyConnection):
            self.con = rel_or_con
            rel = rel_or_con.sql("SELECT 1")
        else:
            self.con = None
            rel = rel_or_con
        self.deferred_tz = _nw_duckdb.DeferredTimeZone(rel)

    def __call__(self, dtype: nw.dtypes.DType) -> duckdb.sqltypes.DuckDBPyType:
        """`dtype`'s DuckDB type."""
        return _nw_duckdb.narwhals_to_native_dtype(
            dtype, Version.MAIN, self.deferred_tz
        )

    def lit(self, value: Any, dtype: nw.dtypes.DType) -> Expression:
        """`value`, cast to `dtype`'s DuckDB type - a typed literal."""
        return lit(value).cast(self(dtype))

    def null(self, dtype: nw.dtypes.DType) -> Expression:
        """A typed NULL, which is one column of a shape-only relation."""
        return self.lit(None, dtype)

    def empty_relation(self, **columns: nw.dtypes.DType) -> DuckDBPyRelation:
        """A row-less relation with `columns`' names and types.

        What a staging table is created from: `create` takes the table's
        shape from the relation, so a shape is built as expressions rather
        than assembled as DDL text. One row of typed NULLs, kept for its
        types and dropped for its rows.

        A tuple rather than a list is what routes `values` to its expression
        overload; the stub types only the scalar one.
        """
        assert self.con is not None
        return self.con.values(
            tuple(self.null(t).alias(n) for n, t in columns.items())
        ).limit(0)  # type: ignore[arg-type]


def fold_axis(
    axes: Sequence[DuckDBPyRelation | None],
    key: tuple[str, ...],
    con: DuckDBPyConnection,
) -> DuckDBPyRelation | None:
    """Fold one keyed relation over each layer's, keyed by `key`, in member order.

    The one fold for every axis - a dim's coordinates, a group.
    `axes` is root first, one entry per layer - `None` where that layer has no
    rows. Last-writer-wins per `key`, which is `Schema.axis_key` for a dim or
    the group's struct column for a group, so a nested dim is keyed by
    `(*parents, dim)` and two periods' identically labelled timesteps stay
    distinct.

    A `deleted = true` row is a tombstone: it removes its key unless a still-
    deeper layer restates it, and never survives into the output, which carries
    no `deleted` column. The output is returned **in first-introduced member
    order** - root first, then within a layer file order - so a reader recovers
    member order from the resolved file's own row order without a persisted
    `order_key`.

    `_row` is tagged **per layer, before any union**: `UNION ALL` defines no
    order, so a bare `row_number() OVER ()` over the unioned relation would
    silently scramble which row counts as first-introduced.

    Notes
    -----
    - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
    - [axis order](https://energy-models.github.io/datarecord/design/record/#axis-order)
    - [within](https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis)
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    layers = []
    for depth, rel in enumerate(axes):
        if rel is None:
            continue
        layers.append(
            rel.project(
                lit(depth).alias("_depth"),
                sql("row_number() OVER ()").alias("_row"),
                star(),
            )
        )
    if not layers:
        return None

    union = union_all_by_name(layers, con)
    has_deleted = "deleted" in union.columns
    partition = ", ".join(str(col(c)) for c in key)
    # `OVER (PARTITION BY ...)` stays text below: DuckDB's expression API has no
    # window construct, so only what the window wraps is built as an expression.
    ranked = union.project(
        star(),
        sql(f"row_number() OVER (PARTITION BY {partition} ORDER BY _depth DESC)").alias(
            "_rank"
        ),
        # The first-introducing (depth, row) pair, as one orderable struct -
        # `min()` over two separate window aggregates would answer "smallest
        # _depth" and "smallest _row" independently, not the pair belonging
        # to the earliest actual row.
        sql(
            f"{fn.min(struct_of({'d': col('_depth'), 'r': col('_row')}))} "
            f"OVER (PARTITION BY {partition})"
        ).alias("_first"),
    )
    winners = ranked.filter(col("_rank") == lit(1))
    # The deepest statement of a key wins; a tombstone there removes it.
    if has_deleted:
        # A row from a layer whose file lacks the column reads `deleted` as NULL
        # once unioned by name; NULL is not a tombstone, so coalesce to false
        # rather than letting `~NULL` drop a live row.
        winners = winners.filter(~coalesce(col("deleted"), lit(False)))  # noqa: FBT003
    scaffold = [
        "_depth",
        "_rank",
        "_row",
        "_first",
        *(["deleted"] if has_deleted else []),
    ]
    return winners.order("_first").project(star(exclude=scaffold))


def dead_keys(
    axes: Sequence[DuckDBPyRelation | None],
    key: tuple[str, ...],
    con: DuckDBPyConnection,
) -> DuckDBPyRelation | None:
    """The keys `fold_axis` drops: those whose deepest row is a tombstone.

    A hash aggregate rather than `fold_axis`'s window, there being no row to
    carry and no order to keep. `None` where no layer carries a `deleted`
    column, so nothing is dead.

    Notes
    -----
    - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
    """
    present = [(depth, rel) for depth, rel in enumerate(axes) if rel is not None]
    if not any("deleted" in rel.columns for _, rel in present):
        return None
    layers = [
        rel.project(
            *(col(c) for c in key),
            lit(depth).alias("_depth"),
            (
                coalesce(col("deleted"), lit(False))  # noqa: FBT003
                if "deleted" in rel.columns
                else lit(False)  # noqa: FBT003
            ).alias("_dead"),
        )
        for depth, rel in present
    ]
    deepest = union_all_by_name(layers, con).aggregate(
        [
            *(col(c) for c in key),
            fn.arg_max(col("_dead"), col("_depth")).alias("_dead"),
        ]
    )
    return deepest.filter(col("_dead")).project(*(col(c) for c in key))
