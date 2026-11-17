<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# DEP 5: one `Record`, over a `NodeCache`

| DEP      | 5                                       |
| -------- | --------------------------------------- |
| Title    | one `Record`, over a `NodeCache`        |
| Author   | Jonas Hörsch                            |
| Status   | Implemented 2026-09-01                  |
| Requires | [DEP 4](dep-0004-staging-as-a-layer.md) |
| Created  | 2026-09-01                              |
| Version  | v0.1.0a1                                |

The design is [the read path](../read-path.md#one-record-over-one-fold) and [the Record protocol](../record.md); this page is the argument for the change rather than the current description, and those pages are authoritative where the two disagree.

Stacked on [staging as a layer](dep-0004-staging-as-a-layer.md), which made a staging area a source of one fold. This is the same observation one level up: a plain directory is a source too, so `DirectoryRecord` is a second reading of what the fold already does.

## What starts it

[read-path](../read-path.md#one-record-over-one-fold) says two implementations differ in four ways. Measured on one directory — `DirectoryRecord(uri)` against a `NodeCache` over `[DirectorySource(uri)]` — **all four are the same answer**:

| what was compared                                         | result                        |
| --------------------------------------------------------- | ----------------------------- |
| `dims`, `entity_types`, `groups`, `attributes`, `outputs` | identical                     |
| `flags`, every declared type                              | identical                     |
| member order, every declared type                         | identical                     |
| resolved rows per attribute                               | identical                     |
| `flags`, first call                                       | 6.6 ms scanned, 2.9 ms folded |

The table was not describing a design property. It was describing an implementation that predates the fold being able to read anything but a layer tree, and each row of it dissolves on contact:

- **Resolution.** Over one source the fold degenerates to a scan. There is one layer, so every key is owned by it and the anti-join has nothing to evict.
- **`flags`.** The fold computes them _in_ that scan's ownership `GROUP BY`, where `DirectoryRecord` scans a second time to get them. Which is why the fold is the faster of the two, not the more expensive one — the opposite of what the table implies.
- **Member order.** `order_key` over one source is `(0, file order)`. Which is file order.
- **`schema.partial`.** It is the granularity of a patch, and one layer patches nothing — so it is inert either way rather than absent from one side.

Two fallback arguments for keeping it also fail, and both were mine:

- **"Folding leaves an owner map on the connection."** It does not. `_frozen_table` keys its cached fold on `revision_id`, and a `DirectorySource`'s id is derived from its URI, so nothing is `.create()`d. Measured: five tables on the connection before, five after.
- **"A foreign directory needs no layering machinery."** A plain parquet directory copied out of any tree, with no revision and no `revisions` row, folds and answers identically. Being a node in a tree is not what the fold needs; being a layer layout is, and that is what a directory _is_.

## The construct

**`NodeCache` does not grow.** It is already the module the design calls relational algebra of real complexity, and the fix here is not to add the `Record` surface to it. It stays what it is: the DuckDB-shaped view over a list of sources, answering in relations.

**`Record` becomes the narwhals interface over one.** One class, holding a `NodeCache` and adapting it — relations to `LazyFrames`, `order_key` sorting, the key sets. That is exactly what `LayeredRecord` already is, so this proposal is mostly _deleting `DirectoryRecord` and renaming what remains_:

```python
@dataclass(frozen=True)
class Record:
    """A record's resolved view, as narwhals frames."""

    node_cache: NodeCache

    @classmethod
    def over(cls, *sources: LayerSource, con: DuckDBPyConnection) -> Record: ...

    @classmethod
    def at(cls, uri: str, con: DuckDBPyConnection | None = None) -> Record:
        """A plain parquet directory, read as the one layer it is."""
        con = con or default_connection()
        return cls.over(DirectorySource(uri, con), con=con)


class WorkingRecord(Record):
    """A `Record` whose last source is a staging area, plus the edit surface."""
```

The two views stay separable, which is the property worth keeping: `tools/` builds against narwhals frames and [says so explicitly](https://github.com/energy-models/datarecord/blob/main/datarecord/tools/base.py) — `to_relation` exists so a tool needing DuckDB's own SQL unwraps a frame "rather than reaching past the record to a `NodeCache`". Collapsing the two would take that seam away.

### What happens to the protocol

`Record` is a `Protocol` today because several things satisfy it. That stays true and stays load-bearing — a framework object presenting itself as a record is the case [`tools`](../tools.md) is built on, and structural typing is what lets it do so without depending on this package.

So the name has to split. **Settled: `Record` is the class, `RecordLike` the protocol.** The concrete thing gets the short name because it is what a caller constructs and holds; the protocol is read at a signature, where the longer name says what it means — "anything shaped like a record", which is exactly the set a framework object joins.

The rename is smaller than it sounds: 17 annotation and `isinstance` sites across `tools/base.py`, `tools/pypsa.py`, `layered/write.py`, `mutable.py` and three test modules. Every one of them is a _consumer_ position - `write_record(record)`, `PyPSA.build(record)` - which is exactly where `RecordLike` is the honest type, because a framework object satisfies it there and always could.

### `WorkingRecord` is a `Record`

Not a wrapper around one. It already forwards every read member to a resolved record it builds internally, so as a subclass it inherits all of them and adds only what it has beyond them:

```python
class WorkingRecord(Record):
    """A `Record` whose last source is a staging area."""
```

The `NodeCache` it holds is the base's with a `StagedSource` appended, which is [what the last proposal established](dep-0004-staging-as-a-layer.md) — so "a record with pending edits" is literally "a record whose last layer is unwritten", in the type as well as in the fold. The `_resolved` property and the internal `LayeredRecord` it constructs both go: `self` is the resolved record.

Two constraints this puts on the base class, neither of which is an obstacle:

- **`frozen=True` has to accommodate a staging area.** `_staged` is mutated per edit, and a frozen dataclass holds a mutable container fine — `DirectoryRecord._flags_cache` does it today via `object.__setattr__` in `__post_init__`. What must stay true is that the _`NodeCache`_ is fixed at construction, which it is: a staged edit changes the tables the last source reads, never which sources there are.
- **Every read member must be inherited unchanged.** That is the property worth having and worth asserting — a member `WorkingRecord` overrides is a member where staging is not just another layer, which is the duplication [the last proposal existed to delete](dep-0004-staging-as-a-layer.md#what-starts-it). `outputs` is the one genuine exception, results not overlaying, and it should carry a comment saying so.

### What the implementation had to add

Two things this page did not see, both found by writing it:

**The `cached_property` members were the real obstacle, not `frozen=True`.** `dims`, `entity_types`, `groups` and `attributes` each cache a **key set**, and a `set` naming a new attribute changes that set — so inheriting them unchanged would have made a staged addition invisible, the exact bug this direction exists to prevent. The fix is not to override them in `WorkingRecord`, which would have cost the inheritance property above; it is to cache them only where the fold is stable, which is [the rule `NodeCache.dims` already applied](../layers.md#a-layers-data-is-write-once) one level down. `NodeCache.stable` names it once and `Record._stable_cache` applies it, so the concept appears twice rather than as a special case — and `WorkingRecord` inherits all four.

**`over` takes its connection explicitly.** A `LayerSource` is only obliged to hand over rows; where it reads them is its own business, and the protocol carries no `con`. So the sketch's `over(*sources)` could not derive one, and it is `over(*sources, con=...)`.

**A standalone record's own schema had to come with it.** `DirectoryRecord.schema` read the directory's `manifest.json` before falling back to the connection root's, and nothing in this page noticed. It matters for exactly one case, which is the case that motivates the manifest existing: a [standalone record](../schema.md#one-schema-per-record) is one whole record and may be read through a connection rooted anywhere. So `Record.at` reads it and `NodeCache` carries it as `declared`, and `with_source` passes it along — a `WorkingRecord` over such a base reads under its schema, an edit being a layer and a layer declaring nothing. The first attempt put an `own_schema` member on `LayerSource` and had the fold ask every source; that invents a question with one possible answer, since a fold holds at most one directory and it is always the root.

## What this deletes

- **`directory.py` entirely** — `DirectoryRecord`, its `_read`/`_require`/`_keyed_by`, and its `flags` aggregate, which is [the second of the two the last proposal left](dep-0004-staging-as-a-layer.md#6-what-directoryrecordflags-keeps-and-the-aggregate-it-shares). With one caller the question that proposal deferred answers itself: there is nothing to share the fold's aggregate _with_, so the parameterised helper it declined to write is not needed at all.
- **`LayeredRecord`**, as a distinct name — it becomes the one class.
- **The read-path table**, and the paragraph under it about a `WorkingRecord` over a directory building a map. Both describe a distinction that is not there.

## What this does not change

- **`WorkingRecord` keeps its edit surface.** `set`, `add`, `remove` and `commit` are what it has beyond a `Record`, and a read-only record must not grow them. What changes is only that it _is_ one rather than wrapping one.
- **`Frames` and `LazyFrames`** are untouched: the laziness contract is the interface's, not the fold's.
- **No format change.** Nothing on disk moves, and no file is read differently. A directory that reads today reads identically after.

## What it costs

**A design property is withdrawn, not just an implementation.** The read-path table has said since it was written that a directory is read without resolution. That was true of the code and is now false, and this proposal's whole claim is that it was never a property worth having — a plain directory is a one-layer record, and reading it as one is both simpler and faster. If that argument is wrong, it is wrong here rather than in the code.

**`tests/test_records.py`'s `both` fixture loses its subject.** It exists to assert two backings agree, and with one backing it asserts nothing. What replaces it has content and is arguably the better test: one directory read _as a directory_ against the same rows read _as a revision's layer_ — the same files reached by two source constructions, which is the invariant that survives.

**A one-source fold is not free where a scan was cached.** `DirectoryRecord.flags` memoises per type; the fold answers from a relation each time. First call favours the fold (2.9 ms against 6.6 ms) and the tenth favours the cache. Bounded by the map rather than by anything a caller controls, and the fold's answer is composable where the cached dict is not — but it is a real difference, and `attributes_of`'s `fetchall()` is where it lands.

## How to know it worked

**The rows, keys, flags and member order are already asserted equal** for the two implementations by `test_backings_agree_on_*`. Rewriting those to compare two _source constructions_ of one directory keeps every assertion and changes only what produces the right-hand side — so the evidence for this change is the evidence that already exists.

**A foreign directory is the case to add.** A parquet directory with no `revisions` row and no tree — which is what the format promises a non-blocks reader can consume — must read through the fold. It does today; nothing asserts it.

**`tools/` must not notice.** It builds from narwhals frames and the PyPSA round-trip is the end-to-end check, so `test_tools.py` passing unchanged is what says the seam held.

**That `WorkingRecord` overrides no read member** is worth asserting directly rather than trusting. Every member it defines beyond `Record`'s should be an edit or a commit; one that is not means staging stopped being just another layer somewhere, which is the failure this whole direction exists to prevent and which no behavioural test would name. `outputs` is the allowed exception, and the assertion should list it explicitly so adding a second requires saying why.

## What it opens

**Whether `Revision` still needs `record`.** If a record is a `NodeCache` plus an adapter, `Revision.record` and `Revision.node_cache` are one construction apart, and the second is what `materialise` already uses.

**Whether the edit path still needs `self.base`.** Landed already, ahead of the rest: `WorkingRecord` reached its base only for the schema, for the parent's rows of one kind (`_axis_frame`, `_complete_owned_whole`), and for the revision to branch from — all `NodeCache` members — so it now holds that cache rather than the record it was handed, resolved once in `__init__`. Two things fell out of it. The `isinstance` ladder became one module-level function at the edge instead of a branch every read crossed. And `NewChild()`'s "no node to branch from" stopped being a question about the base's _class_ and became one about the `revisions` table, which is what it always meant — a directory's derived `revision_id` names no row there. Once `WorkingRecord` _is_ a `Record`, that cache is this one minus the last source, so the attribute becomes a slice.
