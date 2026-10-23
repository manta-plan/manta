# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Editing a record: staged edits, written as a layer by whoever writes them.

What `Record` (read-only) and a whole-record write do not cover: an edit costs
a row in a staging table rather than a rewrite, and nothing touches the record
until `edits` is written as a child.

Notes
-----
- [WorkingRecord](https://energy-models.github.io/datarecord/design/working-record/)
"""

from __future__ import annotations

import operator
import re
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass
from functools import reduce
from hashlib import sha256
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID, uuid4

import duckdb
import narwhals as nw
from duckdb import ColumnExpression as col
from duckdb import ConstantExpression as lit
from duckdb import DuckDBPyRelation, Expression
from duckdb import SQLExpression as sql

from datarecord.duck import (
    DuckTypes,
    as_relation,
    fn,
    null_safe,
    struct_of,
    union_all_by_name,
)
from datarecord.layered.categories import matching
from datarecord.layered.fold import Fold
from datarecord.layered.record import Record
from datarecord.layered.resolve import Resolver
from datarecord.record import (
    EMPTY,
    Frames,
    LazyFrames,
    RecordLike,
)
from datarecord.schema import LONG_TAIL, Schema

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


# -- value normalisation (https://energy-models.github.io/datarecord/design/working-record/#set) ----------------------------------------------


def _incoming(frame: Any, con: DuckDBPyConnection) -> nw.LazyFrame:
    """A caller's frame as a lazy frame on `con`, whatever backend it arrived on.

    Every edit converts at this one point, so the steps behind it join and union
    in narwhals without minding where the frame came from.

    Notes
    -----
    - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
    """
    return nw.from_native(as_relation(nw.from_native(frame).lazy(), con)).lazy()


def _is_frame(value: Any) -> bool:
    """Whether `value` supplies its own keys rather than being a value.

    Notes
    -----
    - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
    """
    if isinstance(value, nw.DataFrame | nw.LazyFrame):
        return True
    try:
        nw.from_native(value)
    except TypeError:
        return False
    return True


def _series_index(value: Any) -> Sequence[Any] | None:
    """`value`'s labels if it is a one-dimensional labelled series, else None."""
    index = getattr(value, "index", None)
    if index is None or getattr(value, "ndim", None) != 1:
        return None
    return list(index)


def _series_index_name(value: Any) -> str | None:
    """A labelled series' index name, where it has one a caller could have meant.

    `pd.Series(...).index.name` is the caller already saying what the index
    holds. A `MultiIndex` has `names` rather than one `name` and is no
    one-dimensional index, so it answers None.
    """
    index = getattr(value, "index", None)
    name = getattr(index, "name", None)
    return name if isinstance(name, str) else None


def _is_labels(value: Any) -> bool:
    """Whether a keyword's value lists several labels rather than naming one."""
    return isinstance(value, Sequence) and not isinstance(value, str | bytes)


def normalise_value(
    value: Any, labels: Sequence[Any] | None = None
) -> tuple[list[Any] | None, list[Any]]:
    """One of `set`'s four `value` forms as labels and the values at them.

    Parameters
    ----------
    value
        Scalar, sequence, mapping, or a one-dimensional labelled series.
    labels
        What a sequence aligns to positionally.

    Returns
    -------
    keys
        The label each value belongs to, or None for a scalar.
    values
        One value per key, or the scalar alone.

    Raises
    ------
    ValueError
        If a sequence has no `labels`, or a different length.

    Notes
    -----
    - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
    """
    index = _series_index(value)
    if index is not None:
        return list(index), list(value)
    if isinstance(value, Mapping):
        return list(value), list(value.values())
    if not _is_labels(value):
        return None, [value]
    if labels is None:
        msg = "a sequence needs labels to align to; pass them as a list keyword"
        raise ValueError(msg)
    if len(value) != len(labels):
        msg = (
            f"{len(value)} values for {len(labels)} labels; a length mismatch is "
            f"an error at the call rather than a truncated edit"
        )
        raise ValueError(msg)
    return list(labels), list(value)


@dataclass(frozen=True)
class StagedSource:
    """A staging area as one layer's rows - the last source the fold reads.

    "The layer as it would be written": each member reads its staging table,
    which an edit replaces by key rather than appending to (`_replace`), so the
    table is already one row per key and what a write would persist.

    Unfrozen, which is the whole of what distinguishes it: a `set` changes these
    rows under a reader, so the fold must stay a relation past this point rather
    than materialise. Nothing here needs invalidating in exchange - a relation
    over a staging table reads whatever the table holds when it is collected.

    Structural rather than inheriting `LayerSource`, so `mutable.py` keeps its
    rule of importing from `layered/` only inside function bodies.

    Notes
    -----
    - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
    - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
    """

    record: WorkingRecord
    layer_id: UUID
    frozen: bool = False

    @property
    def schema(self) -> Schema:
        """This record's schema - the `LayerData` a write reads for one.

        A staging area is not a `LayerSource` a fold folds under a schema
        someone else supplies; it is also what `rev.child(w.edits)` writes
        directly, where it needs its own.
        """
        return self.record.schema

    @property
    def base(self) -> UUID:
        """The revision these edits are a delta against: the base's `revision_id`."""
        return self.record._base.revision_id

    def materialised(self, con: DuckDBPyConnection, schema: Schema) -> Fold | None:
        """A staging area has no `resolved/` cache: it is never a fold's base."""
        return None

    def axes(self) -> set[str]:
        """The dims with staged rows - by `add`, `remove` or a `set` on an axis column."""
        return set(self.record._staged_dims())

    def axis(self, dim: str) -> DuckDBPyRelation | None:
        """One axis as this layer would write it - `_axis_layer`, exactly.

        Which matters for the columns rather than the labels: the fold is
        last-writer-wins per *label*, over the whole row, so a source handing
        over only the column its `set` named would blank every sibling
        property on that label. A `set` on an axis carries the siblings into
        the staged row when it patches it (`_patch_axis`), so the table is
        already the row a write of `edits` persists.

        Notes
        -----
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
        """
        if self.record._rows(f"{_AXIS_PREFIX}{dim}") is None:
            return None
        return self.record._axis_layer(dim)

    def groups(self) -> set[str]:
        """Which declared groups have staged rows."""
        return set(self.record._staged_groups())

    def group(self, name: str) -> DuckDBPyRelation | None:
        return self.record._collapsed_group(name)

    def attributes(self, kind: str = "inputs") -> set[str]:
        """Which attributes of `kind` have staged rows."""
        return set(self.record._staged_attributes_of(kind))

    def attribute(self, name: str, kind: str = "inputs") -> DuckDBPyRelation | None:
        if kind == "outputs":
            # Results do not overlay, so the table is already what is written -
            # one row per coordinate (`_replace`) and no fold to apply.
            return self.record._rows("outputs", name)
        return self.record._collapsed_inputs(name)

    def all_attributes(self, kind: str = "inputs") -> DuckDBPyRelation | None:
        """Every staged attribute of `kind`, unioned by name and unprojected.

        By name because the tables carry per-attribute column variation exactly
        as the files do - one attribute's coordinates and no others - which is
        what lets `fold_inputs` pad both the same way.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        """
        arms = [
            rel
            for name in self.record._staged_attributes_of(kind)
            if (rel := self.attribute(name, kind)) is not None
        ]
        if not arms:
            return None
        return union_all_by_name(arms, self.record.con)


# -- the DuckDB-backed implementation (https://energy-models.github.io/datarecord/design/working-record/#staging) ---------------------------------


class WorkingRecord(Record):
    """A `Record` whose last source is a staging area, plus the edit surface.

    A `Record` in the type as well as in the fold: what it reads is the data
    *with its pending edits applied*, and it reads it by being one layer deeper
    than its base rather than by overlaying anything of its own. Every read
    member is inherited unchanged - `outputs` alone is overridden, results not
    overlaying - so an edit reads back through the same code path a committed
    layer would.

    Staged rows live in connection-scoped DuckDB tables, the *only* place a
    staged row exists: the reads fold them rather than holding a copy, so what
    is staged is asked of the reads themselves.

    The `Resolver` is fixed at construction and the source list never changes;
    a `set` changes what the last source's tables hold, not which sources there
    are. That is what lets the inherited members stay correct - they cache a key
    set only where the fold is stable, which a staged source makes it not.

    Notes
    -----
    - [WorkingRecord](https://energy-models.github.io/datarecord/design/working-record/)
    - [staging](https://energy-models.github.io/datarecord/design/working-record/#staging)
    - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
    """

    #: This record's one identity, which is the staged layer's: the fold stamps
    #: it as `layer_uuid` and dispatches a winning row back through the source
    #: carrying it. Synthetic, the staged layer having no revision until
    #: `edits` is written as one, and it names the staging tables too - so two
    #: `WorkingRecord`s on one connection collide in neither.
    _layer_id: UUID
    #: What the base resolves from, which every use of the base here wants: the
    #: schema, one dim's axis, one attribute's rows and the revision the edits
    #: are a delta against are all members of one.
    _base: Resolver
    #: Keyed by `(kind, attribute)`, the attribute being None for an axis or a
    #: group. A long kind stages one table per attribute because that is the
    #: file it stands for: one `value` column at the attribute's own type, and
    #: its own coordinates and no others.
    _staged: dict[tuple[str, str | None], str]

    def __init__(self, base: RecordLike) -> None:
        # `object.__setattr__` throughout: the base is a frozen dataclass, and
        # these are set before `super().__init__` because the `StagedSource`
        # below reads them off `self`.
        object.__setattr__(self, "_layer_id", uuid4())
        object.__setattr__(self, "_staged", {})
        base_cache = _base_resolver(base)
        object.__setattr__(self, "_base", base_cache)
        # This record *is* the fold one layer deeper, and that layer is the
        # staging area - so the field the base class holds is that fold, whose
        # last source is the staged layer, `edits`.
        super().__init__(base_cache.with_source(StagedSource(self, self._layer_id)))

    # -- staging tables -----------------------------------------------------

    def _table(self, kind: str, attribute: str | None = None) -> str:
        """A staging table's name, unique per record and per attribute.

        The attribute is hashed rather than spelled: it is a caller's string,
        and a table name is the one thing here that cannot be an expression, so
        it would be an injection and a quoting problem at once.
        """
        if kind.startswith(_AXIS_PREFIX):
            # Hashed for the same reason the attribute is: a dim name is a
            # caller's string, and this becomes an identifier.
            digest = sha256(kind[len(_AXIS_PREFIX) :].encode()).hexdigest()[:16]
            return f"staged_axis_{digest}_{self._layer_id.hex}"
        if attribute is None:
            return f"staged_{kind}_{self._layer_id.hex}"
        digest = sha256(attribute.encode()).hexdigest()[:16]
        return f"staged_{kind}_{digest}_{self._layer_id.hex}"

    def _ensure(self, kind: str, attribute: str | None = None) -> str:
        """The staging table for `kind`, created on first use.

        `kind` is `inputs` or `outputs`, an axis (`_AXIS_PREFIX` and its dim),
        or a declared group's name - an axis or a group gets a table shaped by
        its own file.

        A long kind takes an `attribute` and gets a table per attribute, shaped
        like the file it becomes: `long_columns_for` for the columns, and the
        declared dtype for `value`.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        """
        key = (kind, attribute)
        if key in self._staged:
            return self._staged[key]
        name = self._table(kind, attribute)
        self._shape(kind, attribute).create(name)
        self._staged[key] = name
        return name

    def _shape(self, kind: str, attribute: str | None) -> DuckDBPyRelation:
        """A row-less relation shaped like the file `kind` becomes.

        The one place a staging table's columns are decided, so a new kind is a
        branch here rather than a second dispatch beside it.
        """
        if attribute is not None:
            return self._empty_long(attribute)
        if kind.startswith(_AXIS_PREFIX):
            columns = _axis_columns(self.schema, kind[len(_AXIS_PREFIX) :])
        else:
            columns = _group_columns(self.schema, kind)
        return DuckTypes(self.con).empty_relation(**columns)

    def _empty_long(self, attribute: str) -> DuckDBPyRelation:
        """A row-less relation shaped like one attribute's long file.

        What the staging table is created from, so the table's shape is a
        projection rather than assembled DDL - the same expressions the inserts
        then project, which is what keeps the two from drifting.

        `value` takes the attribute's declared type, results being declared
        beside inputs. A name neither vocabulary holds falls back to a string,
        which is the widest thing a value column can be.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        - [the shape of an edit](https://energy-models.github.io/datarecord/design/working-record/#the-shape-of-an-edit)
        """
        duck_types = DuckTypes(self.con)
        value_type = self.schema.value_type(attribute) or nw.String()
        types = {
            "attribute": nw.String(),
            "breakpoint": nw.Float64(),
            "value": value_type,
        }
        shaped = {
            c: types.get(c) or self._column_type(c)
            for c in self.schema.long_columns_for(attribute)
        }
        return duck_types.empty_relation(**shaped)

    def _rows(self, kind: str, attribute: str | None = None) -> DuckDBPyRelation | None:
        name = self._staged.get((kind, attribute))
        return None if name is None else self.con.table(name)

    def _staged_attributes_of(self, kind: str) -> tuple[str, ...]:
        """Which attributes `kind` has staged rows for, in insertion order.

        The staging map is the answer, so this is not a query: a table exists
        exactly where rows were staged.
        """
        return tuple(a for (k, a), _ in self._staged.items() if k == kind and a)

    def _column_type(self, column: str) -> nw.dtypes.DType:
        return _column_type(self.schema, column)

    def _staged_coordinates(self, attribute: str) -> tuple[str, ...]:
        """The dim columns one attribute's staging table has, in table order.

        `long_columns_for` minus the fixed tail, rather than `coordinates_of`:
        the two disagree for an *undeclared* attribute, where the first widens
        to every declared dim and the second answers none. The table is built
        from the first, so an insert deriving its columns from the second would
        supply too few - which is the shape a result arrives in.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        """
        return tuple(
            c for c in self.schema.long_columns_for(attribute) if c not in LONG_TAIL
        )

    # -- Record, one fold deeper (https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits) --------------------------------

    # `schema`, `dims`, `groups`, `attributes` and `flags` are
    # inherited from `Record` unchanged, which is the property this design
    # exists to have: a staged edit is read by the same fold that reads a
    # committed layer, so there is no second overlay to keep in step. Only
    # `outputs` below differs, and only because results do not overlay.

    def _owned_whole(self, attribute: str) -> tuple[str, ...]:
        """`AttributeSpec.dims` minus the fold key - the value axes owned whole.

        The complement of `owned_per`: a dim or group the attribute varies over
        but that is not in `partial_dims` (a non-`partial` `timestep`, or
        `connection`) is owned whole, so a patch to one value restates the
        attribute's whole extent along it.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
        """
        spec = self.schema.attributes.get(attribute)
        whole = (
            frozenset() if spec is None else spec.dims - set(self.schema.partial_dims)
        )
        return tuple(
            d for d in (*self.schema.group_columns, *self.schema.dims) if d in whole
        )

    @property
    def outputs(self) -> Frames:
        """Staged results, keyed by attribute - what a tool handed back.

        Results reach a record through `set(..., kind="outputs")`, so a tool can
        solve against this record's pending inputs and attach what it computed
        without committing first. The base's results are *not* included: they
        were computed from inputs these edits may have changed, and results do
        not overlay, so what is staged is the whole answer.

        Keeping them coherent with the inputs is the caller's business - editing
        an input after attaching results leaves results describing a record that
        no longer exists, and nothing here silently discards them.

        Notes
        -----
        - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
        - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
        """
        names = tuple(sorted(self._staged_attributes_of("outputs")))
        if not names:
            return EMPTY

        def frame(attr: str) -> nw.LazyFrame:
            rel = cast("DuckDBPyRelation", self._rows("outputs", attr))
            # The table is already the shape of the file: results do not overlay,
            # so there is nothing to collapse them against (https://energy-models.github.io/datarecord/design/read-path/#outputs).
            return nw.from_native(rel)

        return LazyFrames(names, frame)

    # -- edits (https://energy-models.github.io/datarecord/design/working-record/#set, https://energy-models.github.io/datarecord/design/working-record/#an-nwexpr-value-derived-from-the-current-one, https://energy-models.github.io/datarecord/design/working-record/#add-remove) ----------------------------------------

    def _key_coordinate(self, attribute: str, value: Any, given: Container[str]) -> str:
        """Which coordinate a mapping's keys or a labelled series' index holds.

        The series' own `index.name` where it names a coordinate of this
        attribute, else the one coordinate no keyword names. Never read off the
        labels: one dim's label may be a string just like another's, so a
        membership test would make one call mean different things in two
        records.

        An `index.name` naming no coordinate is ignored rather than rejected; it
        may be `None`, or a pandas artefact like `"index"`.

        Raises
        ------
        ValueError
            Where the index names a coordinate also given as a keyword, or
            nothing says which of several open coordinates is meant.

        Notes
        -----
        - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
        """
        coordinates = _flat_coordinates(self.schema, attribute)
        named = _series_index_name(value)
        if named in coordinates:
            if named in given:
                msg = (
                    f"`set({attribute!r}, ...)` keys its values by {named!r} and "
                    f"names it as a keyword too; give its labels one way"
                )
                raise ValueError(msg)
            return cast("str", named)
        open_ = [c for c in coordinates if c not in given]
        if len(open_) != 1:
            msg = (
                f"`set({attribute!r}, ...)` keys its values by one of {open_}; "
                f"say which by naming the series' index, or name the others as "
                f"keywords"
            )
            raise ValueError(msg)
        return open_[0]

    def _coordinate_type(self, attribute: str, coordinate: str) -> nw.dtypes.DType:
        """The declared type of one flat coordinate of `attribute` - a group field's dim's."""
        dim = _flat_coordinates(self.schema, attribute).get(coordinate, coordinate)
        return self._column_type(dim)

    def _axis_values(
        self, dim: str, name: str, value: Any, coords: Mapping[str, Any]
    ) -> Any:
        """One property's edit, as a mapping from label to value or a bare scalar.

        `value` is a mapping or labelled series from label to value, a scalar or
        sequence over the labels a `dim=` keyword names, or a scalar for every
        label the axis currently has - which stays a scalar.

        Raises
        ------
        ValueError
            On a keyword other than `dim`, a sequence with no labels to align
            to, or a nested `dim`.

        Notes
        -----
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
        """
        unknown = sorted(set(coords) - {dim})
        if unknown:
            msg = (
                f"`set({name!r}, ...)` names {unknown}, but {name!r} is a "
                f"property of {dim!r} - a column of dims/{dim}.parquet, keyed "
                f"by nothing else"
            )
            raise ValueError(msg)
        if not isinstance(value, Mapping) and (
            dim in coords or _series_index(value) is not None
        ):
            given = coords.get(dim)
            labels = (
                None if given is None else list(given) if _is_labels(given) else [given]
            )
            keys, values = normalise_value(value, labels)
            if keys is None:
                keys, values = cast("list[Any]", labels), values * len(labels or ())
            value = dict(zip(keys, values, strict=True))
        elif _is_frame(value) or _is_labels(value):
            msg = (
                f"`set({name!r}, <sequence>)` has no labels to align to; "
                f"{name!r} is a property of {dim!r}, so pass a mapping from "
                f"{dim!r} label to value, or a scalar for every label"
            )
            raise ValueError(msg)
        if len(self.schema.axis_key(dim)) > 1:
            msg = (
                f"{name!r} is a property of {dim!r}, which is `within` "
                f"{sorted(self.schema.dimensions[dim].within)}; a nested axis's "
                f"labels identify a point only within its parents, which a "
                f"mapping from label alone cannot name"
            )
            raise ValueError(msg)
        return value

    def _stage_axis(self, dim: str, name: str, value: Any) -> None:
        """Stage property `name` of `dim`, `value` as `_axis_values` returns it.

        A scalar reaches every label of the axis as staged, one added in this
        record included.

        Notes
        -----
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
        """
        if not isinstance(value, Mapping):
            value = dict.fromkeys(self._labels_matching(dim, {}), value)
            if not value:
                msg = (
                    f"`set({name!r}, <scalar>)` reaches every label the "
                    f"{dim!r} axis has, and it has none; `add` labels first"
                )
                raise ValueError(msg)
        if not value:
            return
        table = self._ensure(f"{_AXIS_PREFIX}{dim}", None)
        edit = self._values_relation(
            {dim: list(value), name: list(value.values())},
            {dim: self._column_type(dim), name: self.schema.column_type(name)},
        )
        self._patch_axis(dim, name, table, edit, self._base.dims.axes.get(dim))

    def _patch_axis(
        self,
        key: str,
        attribute: str,
        table: str,
        edit: DuckDBPyRelation,
        base: DuckDBPyRelation | None,
    ) -> None:
        """Set property `attribute` on each label or tuple `edit` names, in place.

        `key` is the one column a row is keyed by: a dim, or a group's struct
        column. `base` is the base's resolved axis or group.

        An axis row's columns are independently editable, so this patches the one
        column rather than replacing the row - a sibling a `set` did not name is
        never read and so cannot be lost. A label falls to one of two statements
        by whether a prior `set` already staged it:

        - **INSERT** a label not yet staged, taking its siblings from the base row
          where the base has one and the edited column from `edit`. Its siblings
          have to travel with it: the fold is whole-row last-writer-wins per label
          (`fold_axis`), so a staged patch carrying only its own column would win
          the label and blank the rest - the resolved row is the layer's, not one
          the read rebuilds column by column. A label the base also lacks is new,
          and the edit is the whole of its row.
        - **UPDATE** a label already staged, patching the one column in place so
          the siblings an earlier edit carried stay put.

        `partial` decides only the label *extent* the layer carries, which is
        `_axis_layer`'s business, not this.

        Notes
        -----
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
        - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
        """
        staged = self.con.table(table)
        # Raw SQL because `UPDATE ... FROM` is a join-update, which the relational
        # `update` cannot express (https://duckdb.org/docs/stable/clients/python/relational_api).
        self.con.execute(
            f"UPDATE {table} AS t SET {col(attribute)} = {col('e', attribute)} "
            f"FROM edit e "
            f"WHERE {col('t', key)} IS NOT DISTINCT FROM {col('e', key)}"
        )
        fresh = edit.set_alias("e").join(
            staged.set_alias("s"), null_safe("e", "s", [key]), how="anti"
        )
        if base is None:
            rows = fresh.set_alias("e").select(col(key), col(attribute))
        else:
            # A left join, since a fresh label the base also lacks has no row.
            siblings = [c for c in base.columns if c not in (key, attribute)]
            rows = (
                fresh.set_alias("e")
                .join(base.set_alias("b"), null_safe("e", "b", [key]), how="left")
                .select(
                    col("e", key), col("e", attribute), *(col("b", c) for c in siblings)
                )
            )
        self._insert(rows, table, {})

    def _validate_dims(self, dims: Mapping[str, Any]) -> None:
        """The dim vocabulary, checked for either `kind`.

        A group's key coordinate is a keyword too, `from=` for a corridor,
        though it names no dim.

        Notes
        -----
        - [results through kind="outputs"](https://energy-models.github.io/datarecord/design/working-record/#results-through-kindoutputs)
        - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
        """
        keys = {c for g in self.schema.groups for c in self.schema.group_key(g)}
        unknown = sorted(set(dims) - set(self.schema.dims) - keys)
        if unknown:
            msg = f"the schema declares no dims {unknown}"
            raise KeyError(msg)

    def _validate_result(self, attribute: str, dims: Mapping[str, Any]) -> None:
        """A result's name and dims, against the schema's `results`.

        The attribute check only - not labels, which stay relaxed for a result:
        a solve may produce rows for labels it derived rather than read, and
        rejecting those would refuse a legitimate result.

        Notes
        -----
        - [results through kind="outputs"](https://energy-models.github.io/datarecord/design/working-record/#results-through-kindoutputs)
        - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
        """
        self._validate_dims(dims)
        spec = self.schema.results.get(attribute)
        if spec is None:
            known = sorted(self.schema.results)
            msg = (
                f"the schema declares no result {attribute!r}; it declares "
                f"{known or 'none'}. A result is declared like an input, so a "
                f"tool states its vocabulary before attaching what it computed"
            )
            raise KeyError(msg)
        outside = sorted(
            set(dims) - spec.dims - set(_flat_coordinates(self.schema, attribute))
        )
        if outside:
            msg = (
                f"result {attribute!r} does not vary over {outside}; "
                f"it varies over {sorted(spec.dims) or 'nothing'}"
            )
            raise ValueError(msg)

    def _validate_input(self, attribute: str, coords: Mapping[str, Any]) -> None:
        """An input's name, its keywords, and the labels they give.

        Notes
        -----
        - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
        """
        self._validate_dims(coords)
        spec = self.schema.attributes.get(attribute)
        if spec is None:
            msg = f"the schema declares no attribute {attribute!r}"
            raise KeyError(msg)
        coordinates = _flat_coordinates(self.schema, attribute)
        outside = sorted(set(coords) - spec.dims - set(coordinates))
        if outside:
            msg = (
                f"{attribute!r} does not vary over {outside}; "
                f"it varies over {sorted(spec.dims) or 'nothing'}"
            )
            raise ValueError(msg)
        for c, given in coords.items():
            if c in coordinates:
                labels = list(given) if _is_labels(given) else [given]
                self._require_labels(attribute, coordinates[c], labels)

    def _require_labels(self, attribute: str, dim: str, labels: Sequence[Any]) -> None:
        """Reject labels of a `partial` dim the record does not resolve, or whose categories lack `attribute`.

        Only a `partial` dim keyed by itself alone, and with an axis some layer
        wrote: its label is what the fold keys a row by, so a value for one no
        layer declares would resolve to nothing - caught here rather than
        dropped at read time. Its categories are checked only where one
        coordinate of `attribute` alone is over `dim`; a label of no category
        passes.

        Raises
        ------
        KeyError
            Naming the unknown labels, or the labels whose categories do not carry
            `attribute`.

        Notes
        -----
        - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
        - [traits](https://energy-models.github.io/datarecord/design/schema/#traits)
        """
        if dim not in (self.schema.partial or ()) or self.schema.axis_key(dim) != (
            dim,
        ):
            return
        axis = self.resolver.axis(dim)
        if axis is None:
            return
        drawing = [
            c for c, d in _flat_coordinates(self.schema, attribute).items() if d == dim
        ]
        keys = (
            [k for k in self.schema.categorizing(dim) if k in axis.columns]
            if len(drawing) == 1
            else []
        )
        found = self._require_existing(dim, labels, keys)
        refused = sorted(
            f"{n!r} is {' and '.join(f'{k} {v!r}' for k, v in c.items())}"
            for n, c in found.items()
            if c and attribute not in self.schema.attributes_for(dim, **c)
        )
        if refused:
            msg = f"{attribute!r} is not carried where {', '.join(refused)}"
            raise KeyError(msg)

    def set(
        self,
        attribute: str,
        value: Any,
        *,
        kind: Literal["inputs", "outputs"] = "inputs",
        **coords: Any,
    ) -> None:
        """Stage values of one attribute.

        Every coordinate is a keyword - `entity=`, `snapshot=`, a group's field
        such as `bus=` or a corridor's `from=` - since which exist is declared
        rather than fixed. A keyword holds one label, fixing that coordinate, or
        a list of labels the value is staged at each of. A coordinate no keyword
        names is NULL, which by the broadcast rule is every label of it.

        `value` takes six forms:

        - a scalar, staged at every combination of the listed labels;
        - a sequence, aligned positionally to the one list keyword;
        - a mapping or a one-dimensional labelled series, keyed by labels of
          the series' `index.name` where that names a coordinate, else of the
          one coordinate no keyword names;
        - a long frame supplying its own keys, which keywords may complete with
          single labels;
        - a narwhals expression, a *function of the current value*: it reads the
          rows the keywords select before it stages, so two such calls compose.

        An attribute's values are long rows, whatever its `dims`. A property -
        a category included - patches one column of existing axis rows: a
        mapping or series from label to value, a `dim=` keyword naming the
        labels, or a scalar for every label the axis has. A group's property
        takes a scalar, its fields as keywords selecting the tuples, none
        selecting every tuple.

        A property keyword - `entity_type="Generator"`, or a list of values -
        selects the labels of its dim matching it on the record as staged, the
        keywords combining as an intersection; `set` writes one row per label,
        and stores nothing of the filter, so a label added later is not reached.

        `kind="outputs"` stages into `outputs/` instead of `inputs/`, which is
        how a tool hands results back. Results use the same long schema; they do
        not overlay, and their labels are not checked, a solve producing rows
        for labels it derived rather than read.

        Raises
        ------
        KeyError
            On an undeclared attribute, result or keyword, a `partial` dim's
            label the record does not resolve, a property's label no layer
            wrote, or a label whose categories do not carry `attribute`.
        ValueError
            On a keyword the attribute does not vary over, a sequence with no
            single list keyword to align to, keys whose coordinate is
            ambiguous, a value an `Enum` property does not list, or a property
            keyword whose dim the attribute does not reach through exactly one
            coordinate, or that is given beside that coordinate's own keyword.

        Notes
        -----
        - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
        - [the shape of an edit](https://energy-models.github.io/datarecord/design/working-record/#the-shape-of-an-edit)
        - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
        - [a derived value](https://energy-models.github.io/datarecord/design/working-record/#an-nwexpr-value-derived-from-the-current-one)
        - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
        """
        keyed = isinstance(value, Mapping) or _series_index(value) is not None
        subject = self.schema.subject_of(attribute)
        if subject in self.schema.groups:
            self._set_group_property(subject, attribute, value, coords)
            return
        coords = self._select(attribute, coords)
        if subject is not None:
            self._set_property(subject, attribute, value, coords)
            return
        listed = {c: list(v) for c, v in coords.items() if _is_labels(v)}

        if _is_frame(value) and not keyed:
            if listed:
                msg = (
                    f"`set({attribute!r}, <frame>)` supplies its own keys, so "
                    f"keywords {sorted(listed)} may give one label each, not a list"
                )
                raise ValueError(msg)
            lazy = _incoming(value, self.con)
            self.schema.check_group_columns(
                self.schema.groups_of(attribute),
                lazy,
                carrier=f"`set({attribute!r}, <frame>)`",
            )
            if kind == "inputs":
                self._validate_frame(lazy, attribute, coords)
            else:
                self._validate_result(attribute, coords)
            self._stage_long(attribute, lazy, kind, coords)
            return

        if kind == "inputs":
            self._validate_input(attribute, coords)
        else:
            self._validate_result(attribute, coords)

        if isinstance(value, nw.Expr):
            self._stage_derived(attribute, value, kind, coords)
            return

        if keyed:
            key = self._key_coordinate(attribute, value, coords)
            keys, values = normalise_value(value)
            if kind == "inputs":
                self._require_labels(
                    attribute,
                    _flat_coordinates(self.schema, attribute)[key],
                    cast("list[Any]", keys),
                )
            column: dict[str, Sequence[Any]] = {key: cast("list[Any]", keys)}
        elif _is_labels(value):
            if len(listed) != 1:
                msg = (
                    f"`set({attribute!r}, <sequence>)` aligns to exactly one list "
                    f"keyword, and was given {sorted(listed) or 'none'}"
                )
                raise ValueError(msg)
            ((key, labels),) = listed.items()
            del listed[key]
            _, values = normalise_value(value, labels)
            column = {key: labels}
        else:
            values = [value]
            column = {}
        rel = self._values_relation(
            {**column, "value": values},
            {
                **{c: self._coordinate_type(attribute, c) for c in column},
                "value": None,
            },
        )
        for c, labels in listed.items():
            rel = rel.cross(
                self._values_relation(
                    {c: labels}, {c: self._coordinate_type(attribute, c)}
                )
            )
        fixed = {c: v for c, v in coords.items() if not _is_labels(v)}
        self._insert_long(
            rel, self._ensure(kind, attribute), attribute, set(rel.columns), fixed
        )

    def _set_property(
        self, dim: str, name: str, value: Any, coords: Mapping[str, Any]
    ) -> None:
        """Stage property `name` of `dim`: a patch of one column of each label's row.

        Raises
        ------
        KeyError
            On a label the record does not resolve.
        ValueError
            On a value an `Enum` property does not list, and as `_axis_values`
            does.
        """
        values = self._axis_values(dim, name, value, coords)
        keyed = isinstance(values, Mapping)
        self.schema.require_listed(
            dim,
            {name: list(values.values()) if keyed else [values]},
            f"`set({name!r}, ...)`",
        )
        if keyed:
            self._require_existing(dim, list(values))
        self._stage_axis(dim, name, values)

    def _set_group_property(
        self, group: str, name: str, value: Any, coords: Mapping[str, Any]
    ) -> None:
        """Stage scalar property `name` of `group` on the tuples its field keywords select, all if none.

        Raises
        ------
        KeyError
            Where keywords are given and select no tuple.
        ValueError
            On a keyword naming no field of `group`, a value that is not a
            scalar, or one an `Enum` property does not list.
        """
        call = f"set({name!r}, ...)"
        key = self.schema.group_key(group)
        unknown = sorted(set(coords) - set(key))
        if unknown:
            msg = (
                f"`{call}` names {unknown}, but {name!r} is a property of the "
                f"group {group!r}, whose tuples its fields {list(key)} select"
            )
            raise ValueError(msg)
        # Not left to the cast: DuckDB would store a dict or list as its text.
        if isinstance(value, Mapping) or _is_labels(value) or _is_frame(value):
            msg = (
                f"`{call}` takes one value for the tuples its keywords select, "
                f"{name!r} being a property of the group {group!r}"
            )
            raise ValueError(msg)
        self.schema.require_listed(group, {name: [value]}, f"`{call}`")
        tuples = self.resolver.dims.groups.get(group)
        if tuples is None:
            msg = f"`{call}` finds no tuple of {group!r}; `add_group` them first"
            raise KeyError(msg)
        selected = nw.from_native(tuples).lazy()
        for field, given in coords.items():
            labels = list(given) if _is_labels(given) else [given]
            selected = selected.filter(nw.col(group).struct.field(field).is_in(labels))
        rel = cast("DuckDBPyRelation", selected.select(group).to_native())
        if coords and rel.limit(1).fetchone() is None:
            scope = ", ".join(f"{c}={v!r}" for c, v in coords.items())
            msg = f"`{call}` selects no tuple of {group!r} at {scope}"
            raise KeyError(msg)
        duck_types = DuckTypes(rel)
        dtype = self.schema.column_type(name) or nw.String()
        edit = rel.project(col(group), duck_types.lit(value, dtype).alias(name))
        self._patch_axis(
            group, name, self._ensure(group), edit, self._base.dims.groups.get(group)
        )

    def _require_existing(
        self, dim: str, labels: Sequence[Any], keys: Sequence[str] = ()
    ) -> dict[str, dict[str, str]]:
        """Reject labels of `dim` the record as staged does not resolve.

        Returns
        -------
        dict of str to dict of str to str
            Per label, its value of each of `keys` that is not NULL.

        Raises
        ------
        KeyError
            Naming the unknown labels.
        """
        wanted = list(dict.fromkeys(str(n) for n in labels if n is not None))
        axis = self.resolver.axis(dim)
        rows = (
            []
            if axis is None
            else nw.from_native(axis)
            .lazy()
            .filter(nw.col(dim).cast(nw.String()).is_in(wanted))
            .select(dim, *keys)
            .collect()
            .iter_rows()
        )
        found = {
            str(row[0]): {k: str(v) for k, v in zip(keys, row[1:]) if v is not None}
            for row in rows
        }
        unknown = [n for n in wanted if n not in found]
        if unknown:
            msg = (
                f"no {dim!r} label {unknown}; `add` them first - a value for a "
                f"label no layer declares would resolve to nothing"
            )
            raise KeyError(msg)
        return found

    def _select(self, name: str, coords: Mapping[str, Any]) -> dict[str, Any]:
        """`coords` with each property keyword replaced by the labels it selects.

        Those of its dim storing one of the keyword's values, as staged, each
        under the one coordinate of attribute or dim property `name` over the
        dim.

        Raises
        ------
        ValueError
            Where `name` reaches the dim through no coordinate or several, the
            coordinate is also given as a keyword, or a value is not one of an
            `Enum` property's categories.

        Notes
        -----
        - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
        """
        call = f"set({name!r}, ...)"
        by_dim: dict[str, dict[str, list[Any]]] = {}
        rest: dict[str, Any] = {}
        for c, given in coords.items():
            dim = self.schema.subject_of(c)
            if dim is None:
                rest[c] = given
            else:
                values = list(given) if _is_labels(given) else [given]
                by_dim.setdefault(dim, {})[c] = values
        subject = self.schema.subject_of(name)
        flat = {subject: subject} if subject else _flat_coordinates(self.schema, name)
        for dim, wanted in by_dim.items():
            drawing = [c for c, d in flat.items() if d == dim]
            if len(drawing) != 1:
                msg = (
                    f"`{call}` selects by {sorted(wanted)}, properties of "
                    f"{dim!r}, but {name!r} reaches {dim!r} through "
                    f"{drawing or 'no coordinate'}, not exactly one"
                )
                raise ValueError(msg)
            (coordinate,) = drawing
            if coordinate in rest:
                msg = (
                    f"`{call}` names {coordinate}= and selects it by "
                    f"{sorted(wanted)} too; give its labels one way"
                )
                raise ValueError(msg)
            self.schema.require_listed(dim, wanted, f"`{call}`")
            rest[coordinate] = self._labels_matching(dim, wanted)
        return rest

    def _labels_matching(self, dim: str, wanted: Mapping[str, list[Any]]) -> list[Any]:
        """The labels of `dim`, as staged, storing one of `wanted`'s values of each property."""
        axis = self.resolver.axis(dim)
        if axis is None:
            return []
        return [r[0] for r in matching(axis, wanted).project(col(dim)).fetchall()]

    def _validate_frame(
        self, lazy: nw.LazyFrame, attribute: str, coords: Mapping[str, Any]
    ) -> None:
        """A long input frame's keywords, and the labels its coordinates carry.

        Every coordinate over a `partial` dim the frame supplies - a column, or
        a field of a group's struct, so each party of a contract - must name a
        label the record resolves.

        Notes
        -----
        - [validation](https://energy-models.github.io/datarecord/design/working-record/#validation)
        """
        self._validate_input(attribute, coords)
        columns = lazy.collect_schema().names()
        partial = self.schema.partial or frozenset()
        for c, dim in _flat_coordinates(self.schema, attribute).items():
            if dim not in partial or c in coords:
                continue
            field = (
                nw.col(c)
                if c in columns
                else next(
                    (
                        nw.col(g).struct.field(c)
                        for g in self.schema.groups_of(attribute)
                        if g in columns and c in self.schema.group_key(g)
                    ),
                    None,
                )
            )
            if field is None:
                continue
            labels = lazy.select(field.alias("n")).unique().collect()["n"].to_list()
            self._require_labels(attribute, dim, labels)

    def _coordinate(self, attribute: str, name: str) -> nw.Expr:
        """Coordinate `name` of `attribute`'s rows, inside its group's struct if there.

        Notes
        -----
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        if name in self.schema.long_columns_for(attribute):
            return nw.col(name)
        group = next(
            g
            for g in self.schema.groups_of(attribute)
            if name in self.schema.group_key(g)
        )
        return nw.col(group).struct.field(name)

    def _insert(
        self,
        rel: DuckDBPyRelation,
        table: str,
        supplied: Mapping[str, Expression],
        key: Sequence[str] | None = None,
    ) -> None:
        """Project `rel` into `table`'s column order and insert it.

        `insert_into` is positional, and a staging table's order is its own -
        `ALTER TABLE` appends each extra column as `add` first sees one - so the
        projection is built from the table rather than from the caller. A column
        `supplied` does not name is taken from `rel` where it carries one, and is
        otherwise a NULL typed from the table, which is what spares the insert a
        coercion.

        `key` given, the rows `rel` names by it are deleted first, so the table
        holds one row per key and *is* the file it becomes - no fold on the way
        out. The match is `null_safe` so a broadcast coordinate's NULL replaces
        the same NULL rather than sitting beside it (https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule).
        `rel` must not read `table`, or the delete changes what the insert then
        reads: a caller deriving from the staged rows snapshots them first
        (`_insert_snapshot`), and the one path that patches columns in place
        (`_patch_axis`) passes no `key`.

        Notes
        -----
        - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
        """
        staging = self.con.table(table)
        carried = {c.lower() for c in rel.columns}

        def column(name: str, dtype: str) -> Expression:
            if name in supplied:
                return supplied[name].alias(name)
            if name.lower() in carried:
                return col(name)
            return lit(None).cast(dtype).alias(name)

        projected = rel.project(
            *(
                column(c, str(t))
                for c, t in zip(staging.columns, staging.types, strict=True)
            )
        )
        if key is not None:
            # `null_safe`, not `IN`/`=`: those never match a broadcast row's NULL.
            on = null_safe(table, "p", key)
            self.con.execute(f"DELETE FROM {table} USING projected p WHERE {on}")
        try:
            projected.insert_into(table)
        except duckdb.ConversionException as exc:
            # An `Enum` dim or property reaches DuckDB as one, so this is what rejects a
            # label its vocabulary does not hold - as a conversion to `UINT8`,
            # the enum's storage type, naming neither the dim nor what it
            # declares. The source column is in the message, which is what makes
            # it restatable.
            match = re.search(r"casting from source column (\w+)", str(exc))
            if match is None:
                raise
            source = match.group(1)
            dtype = self.schema.column_type(source)
            if not isinstance(dtype, nw.Enum):
                raise
            msg = (
                f"{source!r} declares no such label; its dtype is an Enum over "
                f"{sorted(dtype.categories)}, which pins the vocabulary"
            )
            raise ValueError(msg) from exc

    def _insert_long(
        self,
        rel: DuckDBPyRelation,
        table: str,
        attribute: str,
        present: Container[str],
        dims: Mapping[str, Any],
    ) -> None:
        """Insert `rel` as one attribute's long rows.

        `present` names the coordinates `rel` already carries; the rest come from
        `dims` where the caller scoped them and are otherwise NULL - "every value
        of it" by the broadcast rule - typed as the schema declares them either
        way, so the insert needs no coercion. A group column `rel` lacks is
        packed from its key coordinates the same way, a field at a time.

        Only this attribute's own coordinates: the staging table is the shape of
        the file it becomes, so a dim it is not addressed by has no column to
        fill, and the projection is in that table's order.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        duck_types = DuckTypes(rel)

        def coordinate(d: str) -> Expression:
            if d in present:
                return col(d)
            if d in self.schema.groups_of(attribute):
                return _packed(self.schema, d, present, dims, duck_types).alias(d)
            return duck_types.lit(dims.get(d), self._column_type(d)).alias(d)

        shaped = rel.project(
            *(coordinate(d) for d in self._staged_coordinates(attribute)),
            lit(attribute).alias("attribute"),
            duck_types.null(nw.Float64()).alias("breakpoint"),
            col("value"),
        )
        self._insert(shaped, table, {}, key=self._long_key(attribute))
        self._complete_owned_whole(attribute, table)

    def _long_key(self, attribute: str) -> tuple[str, ...]:
        """The coordinate columns one long table is keyed on - what an edit replaces.

        The fold partitions on these too (`_collapsed_inputs` before this change),
        so replacing them per edit removes exactly what it would have discarded.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
        """
        return tuple(c for c in self.schema.long_columns_for(attribute) if c != "value")

    def _complete_owned_whole(self, attribute: str, table: str) -> None:
        """Carry the base extent a non-partial axis obliges the staged rows to hold.

        Done as the rows are staged rather than at write, so the staging table
        *is* the layer: touching one snapshot of a series makes
        this layer the owner of that key's whole extent along the dim, and the
        untouched coordinates have to be carried or the written layer would
        report a loss.

        Scoped by the keys already staged, not by the attribute: the semi-join
        below reaches only the keys some edit named, so an entity this record
        never touched stays in the parent.

        Idempotent, which is what lets it run per insert instead of once: the
        anti-join drops any coordinate the table already holds, so a second edit
        to the same attribute carries only what the first did not. That
        anti-join is also the whole of what keeps a fill off an edited
        coordinate - it keys on `_long_key`, the same coordinate a later `set`
        deletes on (`_replace`), so the fill it excludes and the row that
        replaces one are one key, and no ordering column is needed to rank them.

        Notes
        -----
        - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
        - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
        """
        whole = self._owned_whole(attribute)
        if not whole or attribute not in self._base.attributes():
            return

        # Intersected with the attribute's own columns: a key column its file
        # does not carry is absent from both sides rather than NULL in them,
        # and joining on it would fail to bind (`long_columns_for`).
        columns = set(self.schema.long_columns_for(attribute))
        scope = [c for c in self.schema.input_key if c not in whole and c in columns]
        present = [d for d in whole if d in columns]
        if not present:
            # No column for any whole-owned dim, so the file holds one row per
            # key and there is no extent to complete.
            return
        coordinate = self._long_key(attribute)
        staged = self.con.table(table)
        base = self._base.attribute(attribute)
        # A staged row leaving a whole-owned dim NULL already covers that dim's
        # whole extent by the broadcast rule, so its key has nothing left to
        # carry and a base row there would overlap it.
        broadcast = staged.filter(
            sql(" OR ".join(f"{col(d)} IS NULL" for d in present))
        )
        carried = (
            base.set_alias("b")
            # The keys some edit touched, minus those a broadcast already covers.
            .join(staged.set_alias("s"), null_safe("b", "s", scope), how="semi")
            .set_alias("b")
            .join(broadcast.set_alias("s"), null_safe("b", "s", scope), how="anti")
            # Then away the coordinates already staged, leaving the rest of the
            # extent the layer now owns whole and so must carry.
            .set_alias("b")
            .join(staged.set_alias("s"), null_safe("b", "s", coordinate), how="anti")
        )
        self._insert(carried, table, {})

    def _values_relation(
        self,
        columns: Mapping[str, Sequence[Any]],
        schema: Mapping[str, nw.dtypes.DType | None],
    ) -> DuckDBPyRelation:
        """A relation over `columns`, each an equal-length sequence of scalars.

        Column-wise, so nothing here is per-row: a caller's product of entities
        and labels never becomes Python objects.

        A `None` in `schema` is inferred, which an undeclared result's value
        column needs. An `Enum` is built as its `String` and cast by the insert -
        narwhals cannot construct an arrow enum - which is also what rejects a
        label the dtype does not declare.
        """
        buildable = {
            name: (nw.String() if isinstance(dtype, nw.Enum) else dtype)
            for name, dtype in schema.items()
        }
        return as_relation(
            nw.DataFrame.from_dict(
                dict(columns), schema=buildable, backend="pyarrow"
            ).lazy(),
            self.con,
        )

    def _stage_long(
        self, attribute: str, lazy: nw.LazyFrame, kind: str, dims: dict[str, Any]
    ) -> None:
        """Stage a long frame that supplies its own keys.

        Its keys are whatever coordinates it carries; `dims` supplies any the
        frame leaves out, so a caller may scope a whole frame
        to one connection without repeating it per row.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
        """
        table = self._ensure(kind, attribute)
        rel = as_relation(lazy, self.con)
        self._insert_long(
            rel, table, attribute, set(lazy.collect_schema().names()), dims
        )

    def _stage_derived(
        self,
        attribute: str,
        expr: nw.Expr,
        kind: str,
        coords: Mapping[str, Any],
    ) -> None:
        """Stage a value derived from the current one - the `Expr` form.

        Reads before it stages, so what it derives from is the resolved value
        *including earlier pending edits*, and two such calls compose. What is
        staged is the result, never the expression, so a committed layer holds
        ordinary rows and nothing stores that a value was derived.

        On a layered base the read is a fold, so this is the one edit whose cost
        scales with the ancestry rather than with the rows written.

        Unscoped, this derives from every row of the attribute.

        Notes
        -----
        - [a derived value](https://energy-models.github.io/datarecord/design/working-record/#an-nwexpr-value-derived-from-the-current-one)
        """
        source = self.outputs if kind == "outputs" else self.attributes
        frame = source[attribute] if attribute in source else None
        if frame is not None:
            for c, given in coords.items():
                field = self._coordinate(attribute, c)
                frame = frame.filter(
                    field.is_in(list(given)) if _is_labels(given) else field == given
                )

        # A scoped target that resolves to no row is a failed change, not a
        # no-op: the caller asked for these rows to take a new value and there
        # is nothing to derive one from. Unscoped, the instruction is "whatever
        # resolves", so an empty result is an answer.
        if coords:
            # `head(1)`: `is_empty` is a `DataFrame` method, so the question
            # costs a collect either way - this one collects a single row.
            if frame is None or frame.head(1).collect().is_empty():
                scope = ", ".join(f"{c}={v!r}" for c, v in coords.items())
                msg = (
                    f"no {attribute!r} rows resolve for {scope}, so there is "
                    f"no current value to derive from; `set` a value directly to "
                    f"create one (https://energy-models.github.io/datarecord/design/working-record/#an-nwexpr-value-derived-from-the-current-one)"
                )
                raise KeyError(msg)
        if frame is None:
            return
        self._stage_resolved(frame.with_columns(expr.alias("value")), attribute, kind)

    def _stage_resolved(
        self, frame: nw.LazyFrame, attribute: str, kind: str = "inputs"
    ) -> None:
        """Stage an already-long frame carrying every key column.

        `value` needs no cast: the table is this attribute's own, so its column
        already has the attribute's type (`_empty_long`).
        """
        table = self._ensure(kind, attribute)
        # A coordinate the frame leaves out is one it broadcasts over, so it is
        # filled with a typed NULL rather than left to `INSERT ... BY NAME`:
        # projecting the table's full column list keeps the insert positional
        # and the types the table's own (https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule).
        present = set(frame.collect_schema().names())
        rel = as_relation(frame, self.con)
        duck_types = DuckTypes(rel)

        def column(c: str) -> Expression:
            if c in present:
                return col(c)
            if c == "attribute":
                return lit(attribute).alias(c)
            dtype = nw.Float64() if c == "breakpoint" else self._column_type(c)
            return duck_types.null(dtype).alias(c)

        # Keyed the same whether input or result: a repeat coordinate is the
        # caller restating one, and replacing it is the answer folding it gave.
        # No `_complete_owned_whole`: the derived frame resolved the current
        # value, so it already carries the extent an edit would have to.
        self._insert_snapshot(
            rel.project(*(column(c) for c in self.schema.long_columns_for(attribute))),
            table,
            {},
            key=self._long_key(attribute),
        )

    def add(self, dim: str, labels: Sequence[Any], **columns: Any) -> None:
        """Stage labels of `dim`, each as one whole row of its axis file.

        `columns` are that file's other columns - `dim`'s properties and a
        nested dim's parent keys - each a scalar for every label or a sequence
        aligned to `labels`. A column
        no keyword names is NULL on these rows: `add` restates a label's row
        whole, replacing any this record staged for it, a `remove`'s tombstone
        included.

        Not a sequence of `set` calls: a label exists by virtue of its axis row,
        so adding one with no columns at all is an edit. An attribute's value,
        whatever its `dims`, goes through `set`, a group's row through
        `add_group`.

        Raises
        ------
        KeyError
            If the schema declares no `dim`.
        ValueError
            On an attribute, a column the axis file has no place for, a nested
            dim's missing parent key, a sequence of the wrong length, or a
            value an `Enum` property does not list.

        Notes
        -----
        - [add / remove](https://energy-models.github.io/datarecord/design/working-record/#add-remove)
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        """
        if dim not in self.schema.dimensions:
            msg = f"the schema declares no dim {dim!r}"
            raise KeyError(msg)
        call = f"add({dim!r}, ...)"
        table = self._ensure(f"{_AXIS_PREFIX}{dim}")
        self._reject_undeclared(call, table, [*columns])
        missing = [
            c for c in self.schema.axis_key(dim) if c != dim and c not in columns
        ]
        if missing:
            msg = (
                f"`{call}` gives no {missing}; {dim!r} is `within` them, so a "
                f"label names a point only with its parents' keys "
                f"(https://energy-models.github.io/datarecord/design/schema/#within-an-axis-inside-an-axis)"
            )
            raise ValueError(msg)
        names = list(labels)
        data: dict[str, list[Any]] = {dim: names}
        for c, given in columns.items():
            data[c] = list(given) if _is_labels(given) else [given] * len(names)
            if len(data[c]) != len(names):
                msg = (
                    f"`{call}` has {len(data[c])} {c!r} values for {len(names)} labels"
                )
                raise ValueError(msg)
        self.schema.require_listed(dim, data, f"`{call}`")
        rel = self._values_relation(data, {c: self._column_type(c) for c in data})
        self._insert(
            rel,
            table,
            {"deleted": lit(False)},  # noqa: FBT003
            key=self.schema.axis_key(dim),
        )

    def remove(self, dim: str, labels: Sequence[Any]) -> None:
        """Stage a tombstone per label of `dim`.

        Need not enumerate what it deletes: one axis row per label, and the fold
        drops every value keyed by the label where `dim` is `partial`. A nested
        dim's label is a tuple in `Schema.axis_key` order. No labels stage
        nothing.

        And one tombstone per tuple, of any group, with a field over `dim`
        naming one of `labels`, read from the record as it currently resolves:
        a group attribute's value goes with its tuple. Only for a dim keyed by
        its label alone, a nested dim's label naming no point without its
        parents, which a tuple does not carry.

        Notes
        -----
        - [add / remove](https://energy-models.github.io/datarecord/design/working-record/#add-remove)
        - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
        - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
        """
        if not labels:
            return
        key = self.schema.axis_key(dim)
        rows = [label if len(key) > 1 else (label,) for label in labels]
        rel = self._values_relation(
            {c: [row[i] for row in rows] for i, c in enumerate(key)},
            {c: self._column_type(c) for c in key},
        )
        self._insert(
            rel,
            self._ensure(f"{_AXIS_PREFIX}{dim}"),
            {"deleted": lit(True)},  # noqa: FBT003
            key=key,
        )
        if len(key) > 1:
            return
        groups = self.resolver.dims.groups
        for g in self.schema.group_columns:
            fields = [f for f, d in self.schema.groups[g].over.items() if d == dim]
            if not fields or g not in groups:
                continue
            naming = reduce(
                operator.or_,
                (
                    fn.struct_extract(col(g), lit(f)).isin(*(lit(r[0]) for r in rows))
                    for f in fields
                ),
            )
            self._insert_snapshot(
                groups[g].filter(naming).project(col(g)),
                self._ensure(g),
                {"deleted": lit(True)},  # noqa: FBT003
                key=(g,),
            )

    def _insert_snapshot(
        self,
        rel: DuckDBPyRelation,
        table: str,
        supplied: Mapping[str, Expression],
        key: Sequence[str],
    ) -> None:
        """`_insert`, for a `rel` read from `table` itself.

        Snapshotted into a table first: the replace-by-key delete would
        otherwise change what `rel` reads.
        """
        snapshot = f"{table}_snapshot"
        rel.create(snapshot)
        try:
            self._insert(self.con.table(snapshot), table, supplied, key=key)
        finally:
            self.con.execute(f"DROP TABLE {snapshot}")

    def _reject_undeclared(self, call: str, table: str, columns: Sequence[str]) -> None:
        """Refuse a column the staging table's file has no place for, an attribute's included.

        A staging table is shaped from the schema, like the file it becomes, so
        a column outside that shape has no declared dtype; widening the table
        would have to guess it. A tool that grows a column changes its schema
        first.

        Raises
        ------
        ValueError
            Naming the columns, what the file does hold, and pointing an
            attribute at `set`.

        Notes
        -----
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        - [versioning](https://energy-models.github.io/datarecord/design/schema/#versioning)
        """
        known = list(self.con.table(table).columns)
        allowed = {c.lower() for c in known}
        extra = sorted(c for c in columns if c.lower() not in allowed)
        if not extra:
            return
        attributes = [
            c for c in extra if c in {*self.schema.attributes, *self.schema.results}
        ]
        hint = (
            f"; attributes {attributes} are long rows whatever their `dims` - "
            f"stage them with `set` once the row exists"
            if attributes
            else ""
        )
        msg = (
            f"`{call}` was given columns {extra} the schema does not declare "
            f"there; it holds {sorted(known)}. A column there is a property, so "
            f"declare it on its subject before writing it (https://energy-models.github.io/datarecord/design/schema/#versioning){hint}"
        )
        raise ValueError(msg)

    def add_group(self, group: str, frame: Any) -> None:
        """Stage rows of one declared group from a frame keyed by its struct column.

        The frame carries the group as one struct column named for it, its
        `into` label and the group's properties as plain columns - the shape of
        `groups/<group>.parquet`. The one path every group is added
        through, a record's `connection` group included.

        Raises
        ------
        ValueError
            On a missing group or `into` column, an attribute column, and as
            `Schema.check_group_columns` does.

        Notes
        -----
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        call = f"`add_group({group!r}, ...)`"
        lazy = _incoming(frame, self.con)
        columns = lazy.collect_schema()
        self.schema.check_group_columns([group], lazy, carrier=call)
        into = self.schema.groups[group].into
        for required in (group, *([into] if into else [])):
            if required not in columns:
                msg = f"{call} needs a {required!r} column"
                raise ValueError(msg)
        table = self._ensure(group)
        self._reject_undeclared(call, table, list(columns))
        self._insert(
            as_relation(lazy, self.con),
            table,
            {"deleted": lit(False)},  # noqa: FBT003
            key=(group,),
        )

    def remove_group(self, group: str, keys: Sequence[tuple[Any, ...]]) -> None:
        """Stage a tombstone per tuple, each in `Schema.group_key` order.

        Each tuple is packed into the group's struct column. An `into` label is
        no part of a key: the tuple is removed, whatever label it carried.

        Notes
        -----
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        key = self.schema.group_key(group)
        over = self.schema.groups[group].over
        types = {c: self.schema.dimensions[d].dtype for c, d in over.items()}
        flat = self._values_relation(
            {c: [k[i] for k in keys] for i, c in enumerate(key)}, types
        )
        packed = _packed(self.schema, group, key, {}, DuckTypes(flat))
        self._insert(
            flat.project(packed.alias(group)),
            self._ensure(group),
            {"deleted": lit(True)},  # noqa: FBT003
            key=(group,),
        )

    # -- edits / rollback (https://energy-models.github.io/datarecord/design/working-record/#edits) --------------------------

    def rollback(self) -> None:
        """Clear every staged row without writing.

        Notes
        -----
        - [WorkingRecord](https://energy-models.github.io/datarecord/design/working-record/)
        """
        for name in self._staged.values():
            self.con.execute(f"DROP TABLE IF EXISTS {name}")
        self._staged.clear()

    def _collapsed_inputs(self, attribute: str) -> DuckDBPyRelation | None:
        """One attribute's staged rows, tombstones applied.

        The rows are already one per coordinate - an edit replaced its key rather
        than appending beside it (`_replace`) - so this is the table scan minus
        the coordinates a tombstone of this layer reaches. Those anti-joins stay,
        being a cross-table fact rather than an ordering one, and the fold
        applies a layer's tombstones to its parents only: a `remove` has to
        clear this attribute's rows for a `partial` dim's label too, and a
        `remove_group` its rows for the tuple. A group attribute's row naming a
        removed label goes by its tuple, which `remove` tombstoned.

        None where nothing is staged for it, which is what says the base's rows
        stand alone.

        Notes
        -----
        - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
        - [deletion](https://energy-models.github.io/datarecord/design/layers/#deletion)
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        rel = self._rows("inputs", attribute)
        if rel is None:
            return None
        for dim in self.schema.partial or ():
            if dim not in self.schema.dimensions:
                continue
            key = self.schema.axis_key(dim)
            dead = self._tombstoned(dim)
            if dead is not None and set(key) <= set(rel.columns):
                rel = rel.set_alias("l").join(
                    dead.set_alias("d"), null_safe("l", "d", key), how="anti"
                )
        for g in self.schema.groups_of(attribute):
            tuples = self._rows(g)
            if tuples is None:
                continue
            rel = rel.set_alias("l").join(
                tuples.filter(col("deleted")).set_alias("d"),
                null_safe("l", "d", [g]),
                how="anti",
            )
        return rel

    def _tombstoned(self, dim: str) -> DuckDBPyRelation | None:
        """The axis keys of `dim` whose staged row is a tombstone.

        One row per label in the table already (`_replace` on the axis key), so
        an `add` after a `remove` has replaced the tombstone rather than sitting
        above it - the scan is the answer.

        Notes
        -----
        - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
        """
        rel = self._rows(f"{_AXIS_PREFIX}{dim}")
        if rel is None:
            return None
        return rel.filter(col("deleted")).project(
            *(col(c) for c in self.schema.axis_key(dim))
        )

    def _collapsed_group(self, group: str) -> DuckDBPyRelation | None:
        """One group's staged rows - a table scan, one per tuple.

        Restating a tuple replaced its row (`_replace` on the group's column), so the
        table already holds one per key; a different `into` label is that edit,
        not a second row.

        Notes
        -----
        - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
        """
        return self._rows(group)

    # -- what edits write (https://energy-models.github.io/datarecord/design/working-record/#edits) ------------------------------------------

    def _staged_dims(self) -> tuple[str, ...]:
        """Which axes have staged rows, in declaration order.

        Rows rather than tables: `_ensure` creates the table before the label
        checks run, so a rejected `set` leaves an empty one behind and a table
        that exists is not yet an edit.

        Notes
        -----
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        - [the schema](https://energy-models.github.io/datarecord/design/schema/)
        """
        staged = {
            k[len(_AXIS_PREFIX) :]
            for (k, _), _ in self._staged.items()
            if k.startswith(_AXIS_PREFIX)
        }
        return tuple(
            d
            for d in self.schema.dims
            if d in staged
            and self.con.table(self._table(f"{_AXIS_PREFIX}{d}")).limit(1).fetchone()
        )

    def _axis_layer(self, dim: str) -> DuckDBPyRelation:
        """One axis as this layer writes it, which `partial` decides the extent of.

        The staged table already holds one complete row per label an edit touched
        (`_patch_axis`), so there is nothing to merge on the way out - what
        `partial` decides is only how many labels are in it:

        - **`partial`** - the touched labels alone, the fold resolving the rest
          from the parent. The staged table is exactly that.
        - **not `partial`** - a dim a layer owns whole once it touches it, so the
          untouched labels are carried from the base, unioned by name so a base
          row lacking a newly-added column reads NULL there.

        Notes
        -----
        - [partial](https://energy-models.github.io/datarecord/design/schema/#partial-the-granularity-of-an-override)
        """
        staged = self._rows(f"{_AXIS_PREFIX}{dim}")
        assert staged is not None, "only a staged dim reaches an axis layer"
        base = self._base.dims.axes.get(dim)
        if base is None or dim in self.schema.partial_dims:
            return staged
        # The untouched labels the layer owns whole and so must carry, taken from
        # the base with their whole rows - unioned by name, the staged side
        # carrying any column the base lacks and the base side the reverse.
        untouched = base.set_alias("b").join(
            staged.set_alias("s"),
            null_safe("b", "s", self.schema.axis_key(dim)),
            how="anti",
        )
        return union_all_by_name([staged, untouched], self.con)

    def _staged_groups(self) -> Frames:
        """The staged group rows, keyed by group - one frame each.

        A `Frames` for `StagedSource.groups()`'s key set, not a builder of the
        rows themselves - `StagedSource.group` reads those directly off
        `_collapsed_group`.
        """
        staged = {
            g: rel
            for g in self.schema.groups
            if (rel := self._collapsed_group(g)) is not None
        }
        return LazyFrames(tuple(staged), lambda group: nw.from_native(staged[group]))

    @property
    def edits(self) -> StagedSource:
        """The staged layer alone: the delta against the base, as a `LayerData`.

        What `rev.child(w.edits)` writes, where `rev` is the revision this
        record was built over - only the edits, the fold resolving the rest from
        the parent. The record itself is the flattened whole, base plus edits,
        which is what a standalone `ws.write(w, uri)` wants; `rev.child(w)`
        would write that whole as a child, reading back right but larger.

        Writing clears nothing: `rollback()` does, called or not.

        Notes
        -----
        - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
        - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
        """
        return cast("StagedSource", self.resolver.sources[-1])


def _base_resolver(base: RecordLike) -> Resolver:
    """What `base` resolves from, as a `Resolver` a staged layer can extend.

    A `Record` is one already - whether it came from a revision or from
    `Workspace.at(uri)`, since a directory read as its one layer is a fold like
    any other.

    Raises
    ------
    TypeError
        For anything else. A framework object hands over narwhals frames and has
        no layer layout behind it, so synthesising one would be rebuilding the
        format from a protocol that deliberately lacks it.
    """
    if not isinstance(base, Record):
        msg = (
            f"a `WorkingRecord` reads by folding its staged rows over the base's, "
            f"and a {type(base).__name__} has no layer layout to fold - pass a "
            f"`Record`, which `Revision.record` and `Workspace.at(uri)` both give"
        )
        raise TypeError(msg)
    return base.resolver


def _column_type(schema: Schema, column: str) -> nw.dtypes.DType:
    """A staged column's declared type, for a typed NULL or literal.

    Every column a staging table has is a declared dim or a structural one,
    both of which the schema types - so a missing type is a disagreement
    between the table's shape and the schema, not a column to guess at.

    Raises
    ------
    ValueError
        If the schema declares no type for `column`.
    """
    dtype = schema.column_type(column)
    if dtype is None:
        msg = (
            f"the schema declares no type for {column!r}, which a staged "
            f"row needs to fill (https://energy-models.github.io/datarecord/design/format/#the-long-schema)"
        )
        raise ValueError(msg)
    return dtype


def _group_columns(schema: Schema, group: str) -> dict[str, nw.dtypes.DType]:
    """One group's staged columns: its struct column, `into`, its tombstone and its properties.

    Notes
    -----
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    """
    into = schema.groups[group].into
    return {
        group: schema.group_type(group),
        **({into: schema.dimensions[into].dtype} if into else {}),
        "deleted": nw.Boolean(),
        **{p: spec.dtype for p, spec in schema.properties.get(group, {}).items()},
    }


def _flat_coordinates(schema: Schema, attribute: str) -> dict[str, str]:
    """`coordinates_of`, each group column spelled as its key coordinates, each to its dim.

    The names a caller addresses a row by - `bus=` for a connection attribute -
    where the row itself carries `connection`; a group field maps to the dim it
    draws on, a plain coordinate to itself.

    Notes
    -----
    - [set](https://energy-models.github.io/datarecord/design/working-record/#set)
    """
    groups = schema.groups_of(attribute)
    flat: dict[str, str] = {}
    for coordinate in schema.coordinates_of(attribute):
        if coordinate in groups:
            over = schema.groups[coordinate].over
            flat.update({c: over[c] for c in schema.group_key(coordinate)})
        else:
            flat[coordinate] = coordinate
    return flat


def _packed(
    schema: Schema,
    group: str,
    present: Container[str],
    dims: Mapping[str, Any],
    duck_types: DuckTypes,
) -> Expression:
    """`group`'s struct column, packed from flat coordinates.

    A field is the column of that name where the relation carries one, else
    the caller's keyword. No field given at all is a NULL struct, every tuple.

    Raises
    ------
    ValueError
        Where some fields are given and others not: a struct NULL in some
        fields and not all matches no tuple.

    Notes
    -----
    - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    """
    over = schema.groups[group].over
    missing = [c for c in over if c not in present and c not in dims]
    if len(missing) == len(over):
        return duck_types.null(schema.group_type(group))
    if missing:
        msg = (
            f"{group!r} is keyed by {list(over)}, and {missing} was not given; "
            f"name it as a keyword, e.g. `{missing[0]}=...` (https://energy-models.github.io/datarecord/design/schema/#groups)"
        )
        raise ValueError(msg)
    return struct_of(
        {
            c: col(c)
            if c in present
            else duck_types.lit(dims[c], schema.dimensions[d].dtype)
            for c, d in over.items()
        }
    ).cast(duck_types(schema.group_type(group)))


def _axis_columns(schema: Schema, dim: str) -> dict[str, nw.dtypes.DType]:
    """One axis's staged columns - the shape of `dims/{dim}.parquet`: its key, its tombstone, its properties.

    Notes
    -----
    - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
    """
    return {
        **{c: _column_type(schema, c) for c in schema.axis_key(dim)},
        "deleted": nw.Boolean(),
        **{p: spec.dtype for p, spec in schema.properties.get(dim, {}).items()},
    }


# A staging kind, so it becomes part of a table name: no punctuation a SQL
# identifier would need quoting for, and no collision with a group's name,
# which `Schema` already rejects for colliding with a declared dim.
_AXIS_PREFIX = "axis_of_"
