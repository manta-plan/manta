# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Where a layer's rows come from, behind a protocol the fold reads them through.

The fold names files, not locations: `inputs/p_nom.parquet` is what it wants
and a source hands over its rows. Three answer - a parquet directory under
`layers/<uuid>/`, a plain directory read as one layer, and a staging area whose
rows are tables rather than files (`mutable.StagedSource`) - so the fold is
written once and knows about none of them.

Notes
-----
- [the record format](https://energy-models.github.io/datarecord/design/format/)
- [the DuckDB read path](https://energy-models.github.io/datarecord/design/read-path/)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

from datarecord.duck import parquet_names, try_read_parquet
from datarecord.layered.fold import Fold
from datarecord.record import Kind

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection, DuckDBPyRelation

    from datarecord.schema import Schema
    from datarecord.store import Store, Workspace


@runtime_checkable
class LayerSource(Protocol):
    """One layer's own rows, however they are stored.

    "The layer as it would be written", not "the rows as stored": a source
    hands over what `write_layer` would persist, so however a staging area
    reaches one row per key happens behind it and the fold never learns about it.
    `None` means this layer wrote nothing of that kind.

    Rows only. Everything the fold does to them - padding to the long schema,
    expanding broadcasts against an axis, the ownership aggregate, `order_key` -
    stays in the fold, which is the point: an implementation computing any of it
    would be a second copy of the fold.

    Structural, so an implementation needs no import from here: `mutable.py`'s
    `StagedSource` satisfies it by shape alone, and a source outside this
    package would too.

    Attributes
    ----------
    layer_id : UUID
        What the fold stamps as `layer_uuid`, and what a read dispatches a
        winning row back through.
    frozen : bool
        Whether these rows can change under a reader. `False` for a staging
        area, which is what stops the fold materialising past it.

    Notes
    -----
    - [the record format](https://energy-models.github.io/datarecord/design/format/)
    - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
    """

    # Properties rather than variables, so a frozen dataclass satisfies this:
    # mypy reads a plain annotation here as a *settable* attribute, which a
    # frozen field is not.
    @property
    def layer_id(self) -> UUID: ...

    @property
    def frozen(self) -> bool: ...

    @property
    def schema(self) -> Schema:
        """The record's one manifest, passed in at construction, never re-read.

        A layer holds only data - its schema lives beside the tree, not in the
        layer - so this is the reference the constructing reader already held,
        carried so `write_layer` can read it off the source it is handed. Every
        source in one fold carries the same one.

        Notes
        -----
        - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
        """
        ...

    def materialised(self, con: DuckDBPyConnection, schema: Schema) -> Fold | None:
        """This layer's resolved `Fold` if it is materialised, else `None`.

        A filesystem fact, distinct from `frozen`: `frozen` says the rows cannot
        change under a reader, `materialised` says a `resolved/` cache exists on
        disk. The deepest materialised source in a fold's list is its base - the
        prior fold it starts from rather than re-folds. Only a `ParquetLayer`
        ever answers non-`None`; a directory or a staging area has no cache.
        """
        ...

    def axes(self) -> set[str]:
        """Which dims this layer has an axis file for.

        One listing rather than a probe per declared dim: `resolve_coords` asks
        each source once and folds only the dims some source holds.
        """
        ...

    def axis(self, dim: str) -> DuckDBPyRelation | None:
        """`dims/<dim>.parquet` - one axis's full row, not the key alone.

        Its properties ride along as columns, its tombstones as `deleted`.
        """
        ...

    def groups(self) -> set[str]:
        """Which groups this layer has a row for, by file - like `axes()`.

        For `write_layer`'s benefit; not scoped to a schema, which a
        `LayerSource` does not carry - a file some other source's declaration
        does not recognise is the reader's concern, not this listing's.
        """
        ...

    def group(self, name: str) -> DuckDBPyRelation | None:
        """`groups/<name>.parquet` - one group's rows, tombstones included."""
        ...

    def attributes(self, kind: Kind = "inputs") -> set[str]:
        """Which `<kind>/*.parquet` files this layer has, by name.

        For `write_layer`'s benefit: a read learns owned attributes from the
        owner map, never by listing a source's own files.
        """
        ...

    def attribute(self, name: str, kind: Kind = "inputs") -> DuckDBPyRelation | None:
        """`<kind>/<name>.parquet` - one attribute's own columns, unpadded.

        Not the singular of `all_attributes`: this is the *owned* read, and it
        must keep exactly the columns the file has, a padded one being ambiguous
        against the broadcast rule.

        Notes
        -----
        - [the broadcast rule](https://energy-models.github.io/datarecord/design/record/#the-broadcast-rule)
        """
        ...

    def all_attributes(self, kind: Kind = "inputs") -> DuckDBPyRelation | None:
        """Every `<kind>/*.parquet` unioned by name, unprojected.

        Only the long kinds have one: they share `input_key`, so a single scan
        answers the ownership `GROUP BY` for every attribute at once. An axis or
        a group folds on a key of its own, so a union across them would have
        nothing to fold on.
        """
        ...


class _FileLayer:
    """The layer layout over a URI, shared by every file-backed source.

    Each member is one file, addressed by what keys it. A subclass supplies
    where the layer root is (`uri`), the workspace to read it through, and the
    schema its reader held, and inherits every accessor unchanged - which is
    what keeps "a directory read as a layer" from being a second reading of the
    format.

    No cursor is held: each read takes the calling thread's (`_con`), so a
    source serves every thread.

    Notes
    -----
    - [a cursor per thread](https://energy-models.github.io/datarecord/design/read-path/#a-cursor-per-thread)
    """

    schema: Schema
    frozen: bool = True

    def uri(self, path: str = "") -> str:
        """Where `path` is, relative to the layer root.

        Empty is the root itself, with its trailing slash.
        """
        raise NotImplementedError

    @property
    def _con(self) -> DuckDBPyConnection:
        """The calling thread's cursor on the workspace this layer is read through."""
        raise NotImplementedError

    def _read(self, path: str, **kwargs: object) -> DuckDBPyRelation | None:
        return try_read_parquet(self.uri(path), self._con, **kwargs)

    def axes(self) -> set[str]:
        return {
            name.removesuffix(".parquet")
            for name in parquet_names(self.uri("dims/"), self._con)
        }

    def axis(self, dim: str) -> DuckDBPyRelation | None:
        return self._read(f"dims/{dim}.parquet", union_by_name=True)

    def groups(self) -> set[str]:
        return {
            name.removesuffix(".parquet")
            for name in parquet_names(self.uri("groups/"), self._con)
        }

    def group(self, name: str) -> DuckDBPyRelation | None:
        return self._read(f"groups/{name}.parquet", union_by_name=True)

    def attributes(self, kind: Kind = "inputs") -> set[str]:
        return {
            name.removesuffix(".parquet")
            for name in parquet_names(self.uri(f"{kind}/"), self._con)
        }

    def attribute(self, name: str, kind: Kind = "inputs") -> DuckDBPyRelation | None:
        return self._read(f"{kind}/{name}.parquet")

    def all_attributes(self, kind: Kind = "inputs") -> DuckDBPyRelation | None:
        return self._read(f"{kind}/*.parquet", union_by_name=True)

    def materialised(self, con: DuckDBPyConnection, schema: Schema) -> Fold | None:
        """No cache by default: only a `ParquetLayer` has a revision to key one by."""
        return None


@dataclass(frozen=True)
class ParquetLayer(_FileLayer):
    """A layer as a parquet directory, located from its revision UUID.

    The location is derived from the store, never stored, so changing the
    layout is a change to `Store.layer_dir` and nothing else.

    Notes
    -----
    - [the record format](https://energy-models.github.io/datarecord/design/format/)
    """

    revision_id: UUID
    schema: Schema
    store: Store
    frozen: bool = True

    @property
    def layer_id(self) -> UUID:
        return self.revision_id

    @property
    def _con(self) -> DuckDBPyConnection:
        return self.store.workspace.con

    def uri(self, path: str = "") -> str:
        return self.store.layer_dir(self.revision_id) + path

    def materialised(self, con: DuckDBPyConnection, schema: Schema) -> Fold | None:
        """This node's resolved `Fold` if its `resolved/` cache exists, else `None`."""
        return Fold.read(self.revision_id, con, schema, self.store)


@dataclass(frozen=True)
class DirectorySource(_FileLayer):
    """A plain parquet directory read as one layer.

    What `Workspace.at(uri)` and `Store.layer(id)` fold over, and the whole of what reading a plain
    directory takes: the layout is the same as a tree layer's, so every member
    is one of the directory's files and the fold needs no conditional path.

    It is no node in a layer tree, so this makes such a record *readable*
    through the fold, not a revision to branch from.

    Attributes
    ----------
    id
        The layer's identity, which keys the workspace's shared fold tables:
        a standalone record's is minted by its write and read from its
        manifest, so a record written again at one URI is another layer.

    Notes
    -----
    - [the record format](https://energy-models.github.io/datarecord/design/format/)
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """

    base: str
    schema: Schema
    workspace: Workspace
    id: UUID
    frozen: bool = True

    def __post_init__(self) -> None:
        if not self.base.endswith("/"):
            object.__setattr__(self, "base", self.base + "/")

    @property
    def layer_id(self) -> UUID:
        return self.id

    @property
    def _con(self) -> DuckDBPyConnection:
        return self.workspace.con

    def uri(self, path: str = "") -> str:
        return self.base + path
