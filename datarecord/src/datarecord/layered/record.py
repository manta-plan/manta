# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""`Record`, the narwhals face of one `Resolver`.

The `Resolver`-backed implementation of `RecordLike`, beside its backing.
`resolve.py` stays the DuckDB fold; this is the narwhals interface over it.

Notes
-----
- [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
- [module layout](https://energy-models.github.io/datarecord/design/module-layout/)
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, cast

import narwhals as nw
from duckdb import ColumnExpression as col

from datarecord.layered.categories import with_properties
from datarecord.record import Flags, LazyFrames

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection, DuckDBPyRelation

    from datarecord.layered.resolve import Resolver
    from datarecord.schema import Schema


def _stable_cache(method: Callable[[Record], LazyFrames]) -> property:
    """A `Record` member cached only while the fold behind it cannot go stale.

    Every one of these answers a *key set*, which is a question about which
    layers exist rather than about their rows - so it is cacheable exactly when
    `Resolver.frozen` holds. Past a staging area it is not: an `add` or a `set`
    naming a new attribute changes the answer, and a cached tuple of names would
    hide the edit that was just made.

    What is cached is the names and a lookup building each frame per access, so
    no relation is held and the record reads from any thread.

    Notes
    -----
    - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
    - [reading with pending edits](https://energy-models.github.io/datarecord/design/working-record/#reading-with-pending-edits)
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    """
    attr = f"_cached_{method.__name__}"

    @wraps(method)
    def get(self: Record) -> LazyFrames:
        if not self.resolver.frozen:
            return method(self)
        try:
            return cast("LazyFrames", object.__getattribute__(self, attr))
        except AttributeError:
            value = method(self)
            object.__setattr__(self, attr, value)
            return value

    return property(get)


@dataclass(frozen=True)
class Record:
    """A record's resolved view, as narwhals frames.

    The narwhals interface over one `Resolver`, not a second implementation of
    it: a member costs what the equivalent `Resolver` call costs, and `flags`
    in particular is free, the owner map having folded it in.

    One class for every backing, because a fold over one source degenerates to
    a scan of it - so a plain parquet directory is read as the one layer it is
    (`Workspace.at`) rather than by a second code path. `RecordLike` is the
    protocol a caller annotates against; this is the class a caller holds.

    Notes
    -----
    - [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
    - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
    """

    resolver: Resolver

    @property
    def schema(self) -> Schema:
        return self.resolver.schema

    @property
    def con(self) -> DuckDBPyConnection:
        """The calling thread's cursor, which a frame from this record is planned on."""
        return self.resolver.con

    @_stable_cache
    def dims(self) -> LazyFrames:
        names = tuple(self.resolver.dims.axes)
        return LazyFrames(names, self._axis_frame)

    @_stable_cache
    def properties(self) -> LazyFrames:
        coords = self.resolver.dims
        subjects = tuple(
            s for s in self.schema.properties if s in coords.axes or s in coords.groups
        )
        return LazyFrames(subjects, self._property_frame)

    @_stable_cache
    def groups(self) -> LazyFrames:
        """Each declared group's rows, keyed by group - one frame each.

        Only groups some layer wrote a row of; a declared group nothing
        populates is absent rather than present-and-empty.

        Notes
        -----
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        """
        groups = tuple(
            g for g in self.resolver.schema.groups if self.resolver.group(g) is not None
        )
        return LazyFrames(groups, self._group_frame)

    @_stable_cache
    def attributes(self) -> LazyFrames:
        names = tuple(self.resolver.attributes())
        return LazyFrames(
            names, lambda attr: nw.from_native(self.resolver.attribute(attr))
        )

    @_stable_cache
    def outputs(self) -> LazyFrames:
        names = tuple(self.resolver.attributes("outputs"))
        return LazyFrames(
            names, lambda attr: nw.from_native(self.resolver.attribute(attr, "outputs"))
        )

    def flags(self, **categories: str | Sequence[str]) -> dict[str, Flags]:
        """Straight off the `inputs` owner map, which folded these in for free.

        Notes
        -----
        - [the owner map](https://energy-models.github.io/datarecord/design/read-path/#owner-map)
        """
        return self.resolver.fold.flags(**categories)

    # -- frames, in member order (the resolved file's row order) (https://energy-models.github.io/datarecord/design/read-path/#one-record-over-one-fold) --

    def _axis_frame(self, dim: str) -> nw.LazyFrame:
        rel = self._rel(self.resolver.axis(dim), dim)
        return nw.from_native(rel.project(*(col(k) for k in self.schema.axis_key(dim))))

    def _property_frame(self, subject: str) -> nw.LazyFrame:
        is_group = subject in self.schema.groups
        found = (
            self.resolver.group(subject) if is_group else self.resolver.axis(subject)
        )
        key = (subject,) if is_group else self.schema.axis_key(subject)
        rel = with_properties(
            self.schema, self._rel(found, subject), subject, self.resolver.con
        )
        names = (*key, *self.schema.properties[subject])
        return nw.from_native(rel.project(*(col(n) for n in names)))

    def _group_frame(self, group: str) -> nw.LazyFrame:
        return self._frame(self.resolver.group_frame(group), group)

    @staticmethod
    def _rel(rel: DuckDBPyRelation | None, key: str) -> DuckDBPyRelation:
        if rel is None:
            raise KeyError(key)
        return rel

    def _frame(self, rel: DuckDBPyRelation | None, key: str) -> nw.LazyFrame:
        """`rel` as a frame; it already carries member order as its row order.

        The resolved relation is folded in first-introduced member order and read
        back order-preserving (`fold_axis`), so a `Record` promises that order
        without a re-sort and without a persisted `order_key`.

        Parameters
        ----------
        key
            The group name the frame was looked up by, so a miss raises the
            `KeyError` the caller asked with.

        Notes
        -----
        - [one fold for every axis](https://energy-models.github.io/datarecord/design/read-path/#one-fold-for-every-axis)
        """
        if rel is None:
            raise KeyError(key)
        return nw.from_native(rel)
