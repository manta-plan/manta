# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The `RecordLike` protocol: what a record answers, however it is backed.

`layered.revision.Record` is the class this package provides; a framework
object presenting itself as a record satisfies the protocol structurally,
which is what `tools/` is built on.

Notes
-----
- [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
- [the protocol names no engine](https://energy-models.github.io/datarecord/design/record/#the-protocol-names-no-engine)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

import narwhals as nw

from datarecord.schema import Schema

if TYPE_CHECKING:
    from duckdb import DuckDBPyRelation

Kind = Literal["inputs", "outputs"]
"""Which long directory an attribute lives in - the alias `set` takes."""

Frames = Mapping[str, "nw.LazyFrame"]
"""What a `Record` hands over: named frames, each an unmaterialised plan.

The `Mapping` ABC, so a plain `dict` satisfies it as fully as `LazyFrames`
does. A DuckDB-backed record reaches it with `nw.from_native(rel)`, which stays
an unexecuted plan.

Notes
-----
- [Frames](https://energy-models.github.io/datarecord/design/record/#frames)
"""


class LazyFrames(Mapping[str, "nw.LazyFrame"]):
    """A `Frames` whose values are built on `__getitem__`, not up front.

    For a backing where *building* a frame is itself I/O: `read_parquet` reads
    the footer to bind the schema, a round trip per file against a remote record.

    Parameters
    ----------
    keys
        Every key this mapping holds, in iteration order. Listing them must be
        cheap: nothing here builds a frame.
    build
        Called with one key to produce its frame, once per `__getitem__`;
        memoise inside `build` if repeated lookups matter.

    Notes
    -----
    - [Frames](https://energy-models.github.io/datarecord/design/record/#frames)
    """

    def __init__(self, keys: tuple[str, ...], build: Callable[[str], nw.LazyFrame]):
        self._keys = keys
        self._build = build

    def __getitem__(self, key: str) -> nw.LazyFrame:
        if key not in self._keys:
            raise KeyError(key)
        return self._build(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def __contains__(self, key: object) -> bool:
        # `Mapping`'s default answers this by calling `__getitem__` and
        # catching `KeyError`, which would build a frame just to test for one.
        return key in self._keys

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self._keys)!r})"


def _unreachable(key: str) -> nw.LazyFrame:
    raise KeyError(key)  # pragma: no cover - `EMPTY` has no keys to look up


EMPTY = LazyFrames((), _unreachable)
"""A `LazyFrames` with no keys, for a record that has none of some kind."""


@dataclass(frozen=True)
class Flags:
    """Which axes an attribute's rows actually use.

    The two sets are **not** complements: a dim in both means the rows
    disagree, which is the instruction to use both containers rather
    than an ambiguity to resolve. `varies | broadcast` is the test for
    whether an attribute touches a dim at all.

    Parameters
    ----------
    varies
        Dims some row of this attribute sets.
    broadcast
        Dims some row leaves NULL, i.e. "all values of that dim".
    breakpoints
        Whether any row carries a breakpoint. Not a dim.

    Notes
    -----
    - [wide and long rows](https://energy-models.github.io/datarecord/design/record/#wide-and-long-rows)
    - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
    - [Flags](https://energy-models.github.io/datarecord/design/record/#flags)
    """

    varies: frozenset[str]
    broadcast: frozenset[str]
    breakpoints: bool = False


@runtime_checkable
class RecordLike(Protocol):
    """What a record answers, however it is backed, as narwhals frames.

    Read-only: writing is `store.root(source)`, `rev.child(source)` or
    `ws.write(source, uri)`, whose writer reads a `LayerData` rather than this -
    a framework's own `RecordLike` reaches it through an adapter.

    Notes
    -----
    - [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
    - [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
    """

    @property
    def schema(self) -> Schema:
        """The record's schema: its dims, its attributes, its patch granularity.

        Notes
        -----
        - [the schema](https://energy-models.github.io/datarecord/design/schema/)
        """
        ...

    @property
    def dims(self) -> Frames:
        """Axis frames, keyed by dim: each one's key columns, nothing else.

        The labels and their `within` parents; properties are in
        `properties`, attributes in `attributes`.

        Notes
        -----
        - [where a value lives](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        - [axis order](https://energy-models.github.io/datarecord/design/record/#axis-order)
        """
        ...

    @property
    def properties(self) -> Frames:
        """Per dim or group declaring properties, its key and their stored values, no default applied.

        Notes
        -----
        - [properties](https://energy-models.github.io/datarecord/design/schema/#properties)
        """
        ...

    @property
    def groups(self) -> Frames:
        """Each declared group's rows, keyed by group - one frame each.

        A group declares which tuples over several dims exist - `connection`
        over `(entity, bus)` is the one every record with connections has, and
        it is one instance rather than a member of its own.

        Notes
        -----
        - [connections](https://energy-models.github.io/datarecord/design/record/#connections)
        - [groups](https://energy-models.github.io/datarecord/design/schema/#groups)
        - [where the rows live](https://energy-models.github.io/datarecord/design/format/#where-a-value-lives)
        """
        ...

    @property
    def attributes(self) -> Frames:
        """Long input frames, keyed by attribute name - one per file.

        A row carries its coordinates alone; select by category through
        `properties`.

        Notes
        -----
        - [the long schema](https://energy-models.github.io/datarecord/design/format/#the-long-schema)
        """
        ...

    @property
    def outputs(self) -> Frames:
        """Long result frames, keyed by attribute name.

        Empty for a record carrying no results.

        Unlike its neighbours, this does **not** overlay on a layered record: a
        record's results are its own layer's, never a resolution over its
        ancestors'.

        Notes
        -----
        - [outputs](https://energy-models.github.io/datarecord/design/read-path/#outputs)
        """
        ...

    def flags(self, **categories: str | Sequence[str]) -> dict[str, Flags]:
        """Every attribute with rows, mapped to the shape its rows take.

        Given `categories` of one dim, only rows reaching a label among them
        count, and only attributes those labels carry.

        Raises
        ------
        ValueError
            If the keywords categorize no dim or several.

        Notes
        -----
        - [Flags](https://energy-models.github.io/datarecord/design/record/#flags)
        """
        ...


@runtime_checkable
class LayerData(Protocol):
    """The rows of one thing - a layer, or a fold - enumerated and read.

    `write_layer`'s input: it needs `schema` and, per kind, which keys this
    thing holds and each one's rows - the enumerate-and-read pairs below, no
    more. `layered.sources.LayerSource` and `layered.resolve.Resolver` both
    satisfy this structurally, one answering for its own layer and the other
    for everything folded into it; the object decides which, never a mode flag
    or a name prefix. Rows are raw `DuckDBPyRelation`s, not narwhals frames -
    unlike `RecordLike`, which a framework's own producer speaks instead and
    `write_layer` adapts.

    `schema` is not a peer of the other members but what decides which of them
    exist: `groups`/`group` answer only for the groups it declares - an
    enumerator answers the empty set rather than a phantom key where the schema
    declares nothing.

    Notes
    -----
    - [LayerData](https://energy-models.github.io/datarecord/design/record/#layerdata)
    """

    @property
    def schema(self) -> Schema: ...

    @property
    def frozen(self) -> bool: ...

    def axes(self) -> Iterable[str]: ...
    def axis(self, dim: str) -> DuckDBPyRelation | None: ...

    def groups(self) -> Iterable[str]: ...
    def group(self, name: str) -> DuckDBPyRelation | None: ...

    def attributes(self, kind: Kind = "inputs") -> Iterable[str]: ...
    def attribute(
        self, name: str, kind: Kind = "inputs"
    ) -> DuckDBPyRelation | None: ...
