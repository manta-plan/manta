# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The `Revision` node and its ancestry query.

A thin façade over `resolve`: it holds the node's identity and its store, and
reads the workspace's `revisions` table, knowing nothing about owner maps or
parquet layers. A node has no state beyond its place in the tree - whether its
caches are materialised is a filesystem question, answered by
`resolve.materialised`.

Notes
-----
- [layered resolution](https://energy-models.github.io/datarecord/design/layers/)
- [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
- [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    PlainSerializer,
    PrivateAttr,
    model_validator,
)

from datarecord.layered import resolve
from datarecord.layered.record import Record
from datarecord.layered.resolve import Resolver
from datarecord.record import LayerData, RecordLike
from datarecord.store import Store, Workspace

_ANCESTRY = """
WITH RECURSIVE ancestors(id, parent, depth) AS (
  SELECT id, parent, 0 FROM revisions WHERE location = $location AND id = $id
  UNION ALL
  SELECT d.id, d.parent, ancestors.depth + 1
  FROM revisions d
  JOIN ancestors ON d.id = ancestors.parent
  WHERE d.location = $location
)
SELECT id FROM ancestors ORDER BY depth DESC
"""


def ancestry(store: Store, revision_id: UUID) -> list[UUID]:
    """Revision ids along the root->node path, root first - resolution order.

    The whole path. Truncating it at the nearest materialised node is the
    reader's business (`resolve.sources_to_read`), since whether a node's
    caches exist is a fact about the filesystem rather than about the tree.

    Notes
    -----
    - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
    """
    rows = store.workspace.con.execute(
        _ANCESTRY, {"location": store.uri, "id": revision_id}
    ).fetchall()
    return [r[0] for r in rows]


class Revision(BaseModel):
    """A node in the tree of layers.

    Each revision adds one parquet layer on top of its parent's; the record it
    resolves to is that layer over its ancestors'. The layer location derives
    from `id` via its store's `layer_dir`, it is not stored.

    Serialises its store as the location, and validates or unpickles back
    through `Workspace.process()`, reading the revision file and every parent
    the process does not yet hold - so `ancestry()` answers in a fresh process.
    Nothing cached travels.

    Notes
    -----
    - [layered resolution](https://energy-models.github.io/datarecord/design/layers/)
    - [crossing a process boundary](https://energy-models.github.io/datarecord/design/layers/#crossing-a-process-boundary)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: UUID
    parent: UUID | None = None
    store: Annotated[Store, PlainSerializer(lambda s: s.uri, return_type=str)]

    _resolver: Resolver | None = PrivateAttr(default=None)

    @model_validator(mode="before")
    @classmethod
    def _attach(cls, data: Any) -> Any:
        """A location from the serialised form, attached to the process workspace."""
        if isinstance(data, dict) and isinstance(data.get("store"), str):
            store = Workspace.process().store(data["store"])
            store.revision(UUID(str(data["id"])))
            data = {**data, "store": store}
        return data

    def __reduce__(self) -> tuple[Any, ...]:
        return self.store.revision, (self.id,)

    @property
    def resolver(self) -> Resolver:
        """This record's `Resolver`, built once from its ancestry.

        The ancestry is truncated at the deepest materialised ancestor, so a
        deep tree resolves from few entries. Cached rather than rebuilt per
        call: layers are write-once, so the only thing that can change
        the truncation point is `materialise`, which clears this itself. The
        `Resolver` holds no cursor, so the cache serves every thread.

        Notes
        -----
        - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
        - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
        """
        if self._resolver is None:
            full = ancestry(self.store, self.id)
            schema = resolve.read_schema(self.store)
            sources = resolve.sources_to_read(full, self.store, schema)
            self._resolver = Resolver(self.id, sources, self.store.workspace, schema)
        return self._resolver

    @property
    def record(self) -> Record:
        """This revision's resolved view, as a `Record`.

        Notes
        -----
        - [the Record protocol](https://energy-models.github.io/datarecord/design/record/)
        - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
        """
        return Record(self.resolver)

    # -- tree ---------------------------------------------------------------

    def child(self, source: LayerData | RecordLike) -> Revision:
        """A new child of this revision, with `source` as its layer.

        Any node may be a parent: a layer is write-once, so a base cannot shift
        under its descendants. A `WorkingRecord`'s `edits` are a delta against
        the revision it was built over, so they are written only under that
        one; the `WorkingRecord` itself writes its whole resolved record.

        Raises
        ------
        ValueError
            If `source` is staged edits built over another revision, whose delta
            would read back wrong here.

        Notes
        -----
        - [a layer's data is write-once](https://energy-models.github.io/datarecord/design/layers/#a-layers-data-is-write-once)
        - [writing a whole record](https://energy-models.github.io/datarecord/design/writing/)
        - [edits](https://energy-models.github.io/datarecord/design/working-record/#edits)
        """
        from datarecord.mutable import StagedSource

        if isinstance(source, StagedSource) and source.base != self.id:
            msg = (
                f"these edits were staged over revision {source.base}, so they "
                f"are a delta against it and not against {self.id}; write them "
                f"as a child of the revision the `WorkingRecord` was built over"
            )
            raise ValueError(msg)
        return self.store._write(source, self.id)

    def materialise(self) -> None:
        """Write this node's caches - owner maps and resolved dims.

        A policy rather than a lifecycle step, and purely additive: it changes
        no answer, only how many layers a descendant's read touches. Once these
        exist, a read stops here instead of walking further up.

        Notes
        -----
        - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
        """
        resolve.materialise(self.id, self.resolver.sources, self.store)
        self._resolver = None

    # -- read ---------------------------------------------------------------

    def ancestry(self) -> list[UUID]:
        """Revision ids along the root->self path, root first.

        Notes
        -----
        - [materialised node caches](https://energy-models.github.io/datarecord/design/layers/#materialised-node-caches)
        """
        return ancestry(self.store, self.id)
