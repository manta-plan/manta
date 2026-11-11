# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""A node's resolved view: the folded axes, groups and owner map, and the reads.

A `Fold` is what `materialise` wrote and what a live resolution computes: the
folded axes, groups and the `inputs` owner map, each
folded over the node's whole ancestry. `Resolver.fold` takes the deepest
materialised source's `Fold` as its base and folds the layers below it on top,
so a `Fold` read from disk is the prior incarnation of one computed live - the
same shape either tense.

This is the object `ResolvedLayer` used to masquerade as: a fold-result, held as
a base, never an entry in the fold-input `sources` list. The folding that builds
a live `Fold` stays in `resolve.py`, where the DuckDB expression machinery lives;
`Fold.read` reads a materialised one back, and the map reads gated by the fold
(`owners`, `attributes`, `flags`) are here, on the object that holds the map.

Notes
-----
- [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
- [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import reduce
from typing import TYPE_CHECKING, Any
from uuid import UUID

from duckdb import ColumnExpression as col
from duckdb import ConstantExpression as lit
from duckdb import DuckDBPyRelation

from datarecord.duck import (
    distinct_values,
    fn,
    parquet_names,
    struct_field,
    struct_of,
    try_read_parquet,
)
from datarecord.layered.categories import (
    attributes_among,
    categorized_dim,
    matching,
    selected,
)
from datarecord.record import Flags

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from duckdb import DuckDBPyConnection

    from datarecord.schema import Schema
    from datarecord.store import Store


def flags_from_rows(
    schema: Schema,
    dims: tuple[str, ...],
    rows: Iterable[tuple[str, Mapping[str, Any], Mapping[str, Any], Any]],
) -> dict[str, Flags]:
    """Fold `(attribute, varies, broadcast, breakpoints)` rows into `Flags`.

    Separate from the aggregate that produces the rows because the scoping below
    is about the *schema*, not about the map: it is the same cut whatever
    ownership decided, and keeping it out of the SQL is what makes it readable.

    Both sets are cut to the attribute's own coordinates. The relation aggregated
    over covers every attribute, so a dim one attribute is addressed by reads
    NULL for the rows of one that is not, and reporting that NULL as "every row
    broadcasts over it" would tell a consumer to build a container along an axis
    the attribute has no values on. An attribute the schema does not declare
    keeps every dim, its shape not being the schema's to say.

    Parameters
    ----------
    dims
        The broadcast dims the two mappings have an entry per; a dim missing
        from one - declared after a persisted map was written - reads as unset.

    Notes
    -----
    - [Flags](https://energy-models.github.io/datarecord/design/record/#flags)
    """

    def scope(attribute: str) -> tuple[str, ...]:
        own = set(schema.coordinates_of(attribute))
        return tuple(d for d in dims if d in own) if own else dims

    return {
        attribute: Flags(
            frozenset(d for d in scope(attribute) if varies.get(d)),
            frozenset(d for d in scope(attribute) if broadcast.get(d)),
            bool(breakpoints),
        )
        for attribute, varies, broadcast, breakpoints in rows
    }


@dataclass(frozen=True)
class Fold:
    """A node's resolved view, and the map reads over it.

    Each member is folded over the node's ancestry: `read` builds one from a
    `resolved/` cache, and `resolve.py` builds one live over sources. Either way
    it is the same shape, which is what lets a live fold start from a read one as
    its base.

    Attributes
    ----------
    schema
        The record's one schema, which says which broadcast dims the flags carry.
    axes
        Each resolved dim's axis relation, keyed by dim.
    groups
        Each resolved group's relation, keyed by group.
    owner_map
        The resolved `inputs` owner map: `(input_key, layer_uuid, varies,
        broadcast, breakpoints)`, one row per owned key.
    dead
        Each `resolve.mortal` coordinate's dead labels, where it has any.
    """

    schema: Schema
    axes: dict[str, DuckDBPyRelation]
    groups: dict[str, DuckDBPyRelation]
    owner_map: DuckDBPyRelation
    dead: dict[str, DuckDBPyRelation]

    def attributes(self) -> list[str]:
        """Every input attribute any layer owns a row for, from the owner map.

        Ordered, so a `Record` over this has a stable key order.

        Notes
        -----
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        """
        return list(distinct_values(self.owner_map, "attribute"))

    def owners(self, attribute: str) -> DuckDBPyRelation:
        """The owner-map rows for one attribute - which layer owns each of its keys.

        Notes
        -----
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        """
        return self.owner_map.filter(col("attribute") == lit(attribute))

    def flags(self, **categories: str | Sequence[str]) -> dict[str, Flags]:
        """Per attribute, which dims its rows use, across the record or one category.

        A dim in both sets is the instruction to use both containers, each
        taking the rows it matches.

        Parameters
        ----------
        categories
            Categorizing properties of one dim, each one category or several:
            only rows reaching a matching label count, and only attributes
            those labels carry (`Schema.attributes_for`) are present. None
            given, every row counts.

        Raises
        ------
        ValueError
            If the keywords categorize no dim or several.

        Notes
        -----
        - [Flags](https://energy-models.github.io/datarecord/design/record/#flags)
        - [traits](https://energy-models.github.io/datarecord/design/schema/#traits)
        """
        dims = self.schema.broadcast_dims
        if not categories:
            # The structs come back as dicts keyed by dim, so each set is a filter
            # by name rather than a positional slice.
            return flags_from_rows(
                self.schema, dims, self._flag_rows(self.owner_map, dims)
            )
        dim = categorized_dim(self.schema, categories)
        chosen = selected(self.schema, dim, categories)
        carried = attributes_among(self.schema, dim, chosen)
        axis = self.axes.get(dim)
        if axis is None or not carried:
            return {}
        rows = self._owned_reaching(dim, matching(axis, chosen).project(col(dim)))
        flags = flags_from_rows(self.schema, dims, self._flag_rows(rows, dims))
        return {a: f for a, f in flags.items() if a in carried}

    def _owned_reaching(self, dim: str, labels: DuckDBPyRelation) -> DuckDBPyRelation:
        """The owner-map rows naming one of `labels`, on `dim` or a group's field over it.

        One semi-join per path, unioned rather than OR-ed into one condition,
        which would be a nested loop; a row matched twice changes no flag.
        """
        om = self.owner_map.set_alias("o")
        paths = []
        if dim in om.columns:
            paths.append(col("o", dim))
        for group in self.schema.groups:
            field = self.schema.field_over(group, dim)
            if group in om.columns and field is not None:
                paths.append(fn.struct_extract(col("o", group), lit(field)))
        reached = [
            om.join(labels.set_alias("l"), path == col("l", dim), how="semi")
            for path in paths
        ]
        if not reached:
            return om.filter(lit(False))  # noqa: FBT003
        return reduce(DuckDBPyRelation.union, reached)

    def _flag_rows(
        self, rel: DuckDBPyRelation, dims: tuple[str, ...]
    ) -> list[tuple[Any, ...]]:
        """`rel`'s flag columns, aggregated per attribute."""
        flag = {
            c: struct_of(
                {d: fn.bool_or(struct_field(rel, c, d, lit(False))) for d in dims}
            ).alias(c)
            for c in ("varies", "broadcast")
        }
        return rel.aggregate(
            [
                col("attribute"),
                flag["varies"],
                flag["broadcast"],
                fn.bool_or(col("breakpoints")).alias("breakpoints"),
            ]
        ).fetchall()

    @classmethod
    def read(
        cls,
        revision_id: UUID,
        con: DuckDBPyConnection,
        schema: Schema,
        store: Store,
    ) -> Fold | None:
        """This node's `Fold`, or `None` if it is not materialised.

        The `inputs` owner map is the presence marker: the maps, dims and groups
        are written together (`resolve.materialise`), so if the map is absent
        the node has no `resolved/` cache at all.
        """
        base = store.resolved_dir(revision_id)
        owner_map = try_read_parquet(f"{base}owner_map/inputs.parquet", con)
        if owner_map is None:
            return None
        return cls(
            schema=schema,
            axes=_read_dir(f"{base}dims/", con),
            groups=_read_dir(f"{base}groups/", con),
            owner_map=owner_map,
            dead=_read_dir(f"{base}dead/", con),
        )


def _read_dir(dir_uri: str, con: DuckDBPyConnection) -> dict[str, DuckDBPyRelation]:
    """Every `<name>.parquet` in `dir_uri`, keyed by name, tolerant of an absent dir."""
    rels = {}
    for name in parquet_names(dir_uri, con):
        stem = name.removesuffix(".parquet")
        rel = try_read_parquet(f"{dir_uri}{name}", con, union_by_name=True)
        if rel is not None:
            rels[stem] = rel
    return rels
