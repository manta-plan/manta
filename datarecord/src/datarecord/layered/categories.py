# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Which labels of a categorized dim carry what, and the properties they read.

Every answer is the schema's (`Schema.attributes_for`, `properties_for`,
`default_for`), asked once per category combination a relation holds.

Notes
-----
- [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
- [traits](https://energy-models.github.io/datarecord/design/schema/#traits)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import reduce
from itertools import product
from typing import Any

import duckdb
from duckdb import CoalesceOperator as coalesce
from duckdb import ColumnExpression as col
from duckdb import ConstantExpression as lit
from duckdb import DuckDBPyConnection, DuckDBPyRelation, Expression
from duckdb import StarExpression as star

from datarecord.duck import DuckTypes, ex_all, fn, null_safe
from datarecord.schema import Schema

Categories = Mapping[str, "str | Sequence[str]"]
"""Per categorizing property, the one category or the categories to select."""


def narrowed(schema: Schema, dim: str, attributes: Sequence[str]) -> list[str]:
    """Those of `attributes` that not every label of `dim` carries."""
    everywhere = schema.attributes_for(dim)
    return [a for a in attributes if a not in everywhere]


def label_carriers(
    schema: Schema,
    axis: DuckDBPyRelation,
    dim: str,
    attributes: Sequence[str],
    con: DuckDBPyConnection,
) -> DuckDBPyRelation:
    """`(dim, attribute)` for each label of `axis` carrying one of `attributes`.

    Judged by the category combinations `axis` holds when called.
    """

    def carried(cats: dict[str, str]) -> list[Expression]:
        carrying = schema.attributes_for(dim, **cats)
        names = [a for a in attributes if a in carrying]
        return [lit(names).cast("VARCHAR[]").alias("attribute")]

    return _per_combination(schema, dim, axis, carried, con).project(
        col("r", dim), fn.unnest(col("t", "attribute")).alias("attribute")
    )


def carriers(
    schema: Schema,
    axes: Mapping[str, DuckDBPyRelation],
    groups: Mapping[str, DuckDBPyRelation],
    coordinate: str,
    attributes: Sequence[str],
    con: DuckDBPyConnection,
) -> tuple[list[str], DuckDBPyRelation | None]:
    """Of `attributes` over `coordinate`, the narrowed ones and who carries them.

    A group's tuple carries what the label its field over a categorized dim
    names carries; a group with several such fields narrows nothing.

    Returns
    -------
    list of str
        The narrowed attributes.
    DuckDBPyRelation or None
        `(coordinate, attribute)` per carrying label or tuple, `None` where
        nothing is narrowed.
    """
    if coordinate in axes:
        names = narrowed(schema, coordinate, attributes)
        if not names:
            return [], None
        return names, label_carriers(schema, axes[coordinate], coordinate, names, con)
    fields = [
        (f, d, names)
        for f, d in schema.groups[coordinate].over.items()
        if d in axes and (names := narrowed(schema, d, attributes))
    ]
    if len(fields) != 1:
        return [], None
    [(field, dim, names)] = fields
    labels = label_carriers(schema, axes[dim], dim, names, con).set_alias("c")
    rel = (
        groups[coordinate]
        .set_alias("g")
        .join(
            labels,
            fn.struct_extract(col("g", coordinate), lit(field)) == col("c", dim),
        )
        .project(col("g", coordinate), col("c", "attribute"))
    )
    return names, rel


def categorized_dim(schema: Schema, categories: Categories) -> str:
    """The one dim every key of `categories` categorizes.

    Raises
    ------
    ValueError
        If a key categorizes no dim, or the keys categorize different dims.
    """
    dims = {d for d in schema.dims for k in categories if k in schema.categorizing(d)}
    unknown = sorted(
        k for k in categories if not any(k in schema.categorizing(d) for d in dims)
    )
    if unknown:
        msg = f"{unknown} categorize no dim; a category is an Enum property of a partial dim"
        raise ValueError(msg)
    if len(dims) != 1:
        msg = f"{sorted(categories)} categorize several dims {sorted(dims)}; name one dim's"
        raise ValueError(msg)
    return dims.pop()


def selected(
    schema: Schema, dim: str, categories: Categories
) -> dict[str, tuple[str, ...]]:
    """`categories` checked against `dim`'s, each as a tuple of categories.

    Raises
    ------
    ValueError
        If a key does not categorize `dim`, or a value is none of its categories.
    """
    schema.require_categorizing(dim, categories)
    chosen = {
        k: (v,) if isinstance(v, str) else tuple(v) for k, v in categories.items()
    }
    schema.require_listed(dim, chosen, "the selection")
    return chosen


def matching(
    axis: DuckDBPyRelation, chosen: Mapping[str, Sequence[Any]]
) -> DuckDBPyRelation:
    """The rows of `axis` whose stored values are among `chosen`; none for an absent column."""
    if any(k not in axis.columns for k in chosen):
        return axis.filter(lit(False))  # noqa: FBT003
    if not chosen:
        return axis
    return axis.filter(
        ex_all(col(k).isin(*(lit(v) for v in vs)) for k, vs in chosen.items())
    )


def attributes_among(
    schema: Schema, dim: str, chosen: Mapping[str, Sequence[str]]
) -> set[str]:
    """The attributes a label of any combination of `chosen` carries."""
    return _carried_by_any(
        schema.attributes_for, dim, list(chosen), product(*chosen.values())
    )


def with_defaults(
    schema: Schema,
    subject: str,
    rel: DuckDBPyRelation,
    key: Sequence[str],
    names: Sequence[str],
    con: DuckDBPyConnection,
) -> DuckDBPyRelation:
    """`rel` projected to `key` and `names`, an unset name read as its default.

    A label not carrying a name reads NULL for it, a stored value included.
    """
    if not names:
        return rel.project(*(col(k) for k in key))
    duck = DuckTypes(con)

    def columns(cats: dict[str, str]) -> list[Expression]:
        carried = schema.properties_for(subject, **cats)
        return [
            *(lit(n in carried).alias(f"_carries_{n}") for n in names),
            *(
                duck.lit(
                    schema.default_for(n, **cats),
                    schema.property_spec(n).dtype,  # type: ignore[union-attr]
                ).alias(f"_default_{n}")
                for n in names
            ),
        ]

    return _per_combination(schema, subject, rel, columns, con).project(
        *(col("r", k) for k in key),
        *(
            duckdb.CaseExpression(
                col("t", f"_carries_{n}"),
                coalesce(col("r", n), col("t", f"_default_{n}")),
            ).alias(n)
            for n in names
        ),
    )


def carried_properties(schema: Schema, dim: str, rel: DuckDBPyRelation) -> list[str]:
    """The properties of `dim` a label of `rel` carries, in declaration order.

    Judged by the category combinations `rel` holds when called.
    """
    carried = _carried_by_any(
        schema.properties_for, dim, *_combinations(schema, dim, rel)
    )
    return [n for n in schema.properties.get(dim, {}) if n in carried]


def with_properties(
    schema: Schema, rel: DuckDBPyRelation, subject: str, con: DuckDBPyConnection
) -> DuckDBPyRelation:
    """`rel` with each property of `subject` it lacks added as a typed NULL."""
    missing = [n for n in schema.properties.get(subject, {}) if n not in rel.columns]
    if not missing:
        return rel
    duck = DuckTypes(con)
    return rel.project(
        star(),
        *(duck.null(schema.properties[subject][n].dtype).alias(n) for n in missing),
    )


def _combinations(
    schema: Schema, subject: str, rel: DuckDBPyRelation
) -> tuple[list[str], list[tuple[Any, ...]]]:
    """`subject`'s categorizing columns in `rel`, and their distinct value combinations."""
    keys = [k for k in schema.categorizing(subject) if k in rel.columns]
    if not keys:
        return keys, [()]
    return keys, rel.project(*(col(k) for k in keys)).distinct().fetchall()


def _categories_of(keys: Sequence[str], combo: Sequence[Any]) -> dict[str, str]:
    """`combo` by key, a NULL category left out, so it matches no trait or `default_by` keyed on it."""
    return {k: c for k, c in zip(keys, combo, strict=True) if c is not None}


def _carried_by_any(
    carried: Callable[..., Mapping[str, Any]],
    subject: str,
    keys: Sequence[str],
    combos: Iterable[Sequence[Any]],
) -> set[str]:
    """The union of `carried(subject, **categories)` over `combos`."""
    return {n for c in combos for n in carried(subject, **_categories_of(keys, c))}


def _per_combination(
    schema: Schema,
    subject: str,
    rel: DuckDBPyRelation,
    columns: Callable[[dict[str, str]], list[Expression]],
    con: DuckDBPyConnection,
) -> DuckDBPyRelation:
    """`rel` as `r`, joined on its categories to `t`, `columns` of them.

    `t` is built eagerly, one row per category combination `rel` holds when
    called, so the trait and default rules stay the schema's.
    """
    keys, combos = _combinations(schema, subject, rel)
    types = dict(zip(rel.columns, rel.types, strict=True))

    def row(combo: Sequence[Any]) -> DuckDBPyRelation:
        return con.values(
            (
                *(
                    lit(c).cast(types[k]).alias(k)
                    for k, c in zip(keys, combo, strict=True)
                ),
                *columns(_categories_of(keys, combo)),
            )  # type: ignore[arg-type]
        )

    table = (
        reduce(DuckDBPyRelation.union, map(row, combos))
        if combos
        else row((None,) * len(keys)).limit(0)
    ).set_alias("t")
    if not keys:
        return rel.set_alias("r").cross(table)
    return rel.set_alias("r").join(table, null_safe("r", "t", keys))
