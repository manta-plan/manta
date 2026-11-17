<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# Layered resolution

A `Record` resolves a tree of layers.
Each node adds one layer; a node's data is its layer resolved over its ancestors', last-writer-wins.

```python
class Revision(BaseModel):
    id: UUID
    parent: UUID | None  # None for a root
    store: Store  # serialised as its location
```

Each revision has one layer at `<location>/layers/<id>/`; the path derives from the UUID and its [store](#the-store) rather than being stored.
Caches derived from the ancestry rather than from layer data live in a `resolved/` subdirectory of it, so the layer's own top level stays exactly what that layer wrote.

Nodes form a tree: branching is several children sharing a parent, and they share the parent's layer and all further ancestry by pointing at it, not by duplication.
Resolution order along a root→node path is ancestry order; a node's own layer is last and wins.

The node metadata — `(id, parent)` — is persisted [beside the layers](#the-tree-beside-the-layers), one file per revision, so a revision id resolves to its ancestry, and thus its layer set, from the location alone.

Two of [the protocol's](record.md) columns take their meaning from the overlay key.

A [group](schema.md#groups) [`partial`](schema.md#partial-the-granularity-of-an-override) names is part of the **inputs** key, `(*partial dims, attribute)` — the `connection` column, NULL for an entity-level attribute and NULL-safe-compared so that case is unaffected.
That is what makes a per-connection attribute owned _per connection_: without it, a patch changing one connection's `efficiency` owns — and so restates — every connection's, which is what a group outside `partial` costs.
It is also why a connection is keyed by its bus rather than by position: a patch layer would otherwise have to know a connection's current index, so an ancestor inserting one earlier would silently redirect that patch to a different bus.

`breakpoint` ([wide and long rows](record.md#wide-and-long-rows)), by contrast, is deliberately **not** part of the overlay key.
A layer owns a whole curve, the same rule a non-`partial` dim follows ([partial](schema.md#partial-the-granularity-of-an-override)), so a parent's breakpoints and a descendant's can never resolve into one curve with a hole.

## A layer's data is write-once

A node has no mutable state.

A layer's data is created by one act — [`store.root` or `rev.child`](writing.md), the latter also how a `WorkingRecord`'s [edits](working-record.md#edits) are written — which refuses an existing directory and stages into a sibling path, so a layer is complete when it first becomes visible and never changes afterwards; and its [revision file, written last](writing.md#a-revision-exists-only-by-its-file), is what makes it reachable at all.
Editing needs no mutable layer: edits accumulate in [the staging area](working-record.md#staging) and become a layer when written as a child.

The one thing written into a layer directory after that act is its [`resolved/` cache](#materialised-node-caches), which is why the invariant is stated over the layer's _data_ rather than over the directory.
That is not a loosening that costs anything: a cache is derived from immutable layers, so writing one cannot change an answer, and nothing downstream reads it as data.

Two properties follow. **Any node may be a parent**, since an immutable base cannot shift under its descendants.
And **a cache never needs invalidating**, since one derived from immutable layers cannot go stale.

## Materialised node caches

A node's owner map and resolved dims may be materialised under `layers/<id>/resolved/`.
Not the schema: there is [one for the whole record](schema.md#one-schema-per-record), so there is nothing per node to resolve.

Where a materialised map exists, a read stops there: the map is already folded over everything above it, so a read walks the ancestry only back to the nearest materialised node rather than to the root.
That truncation is what keeps a deep chain cheap.
The same rule decides where resolved dims come from — a node's own `resolved/dims/` where materialised, its raw `dims/` otherwise — answered by the cache's presence rather than by any recorded state.
The two are distinct paths within one directory, so a record read as an ancestor and the same record read as itself never alias.

Beside the resolved dims and groups, `resolved/dead/<coord>.parquet` holds the [dead labels](read-path.md#a-label-outside-the-key) of each coordinate outside `partial` and each dim a group draws on, written only where there are any.
A read above the node seeds its dead labels from these, the resolved relations themselves holding no tombstones.

Materialising is a policy: every N layers, at a branch point, on demand.
It is purely additive, writing files under `resolved/` and changing no answer, only how many layers a read touches to reach it.

## Deletion

A `deleted = true` row in `dims/<dim>.parquet` — [the entity axis](format.md#the-entity-axis) like any other — tombstones a label from every attribute, and from every value of every other dim — [existence does not vary along one](schema.md#existence-does-not-vary-along-a-dim), so there is nothing to scope a deletion by.
A `deleted = true` row in `groups/<group>.parquet` tombstones one row of that group — the row itself, and its `inputs/` rows where the group is `partial` — leaving the labels it names and their other rows intact, so a connection is removed without touching the entity it attached.

A tombstone is honoured by the [one fold](read-path.md#one-fold-for-every-axis) that resolves every axis: the deepest statement of a key wins, and where it is a tombstone the key leaves the resolved relation (a deeper restatement reviving it).
An _attribute's_ orphaned rows stop surfacing the same way, for every key column: an attribute row is keyed by the partial dims and groups its `dims` name, and [`fold_inputs`](read-path.md#owner-map) anti-joins the map against each one's `deleted` rows as it folds — so a key whose entity, connection tuple or dim coordinate was deleted is absent from the resolved map.
A label of a dim or group outside `partial` is in no key, so its rows are [dropped at read](read-path.md#a-label-outside-the-key) against that coordinate's dead labels instead.
Each axis and group honours only its **own** tombstones, read from the same file it folds from, and nothing is inferred from a dead label a row refers to.
So removing a label is written as a cascade, the same for every dim: [`remove(dim, labels)`](working-record.md#add-remove) tombstones the labels and every live group tuple with a field over `dim` naming one, in one layer, and the tuples' values go with them.
A layer adding a tuple that names a dead label, or removing a label a tuple still names, is refused by the writer, which folds the parent's axes and groups to tell. A tuple an ancestor left dangling fails no later write, the check being of what the layer does. A nested dim's labels are not checked, a tuple carrying no parents to place them by.
Re-adding the label does not revive its tuples. Re-adding a tuple outside `partial` revives its values, which are owned per attribute rather than per tuple.
A tombstone only affects the branch that carries it; sibling branches keep the label.

The fold treats an absent `deleted` column as "tombstones nothing", so a layer may be any standard parquet directory, not only one this package wrote.
Every derived cache lives under `resolved/` for the same reason: every glob the read path issues into a layer is single-level — `inputs/*.parquet`, `dims/*.parquet`, `groups/*.parquet` — so nothing under `resolved/` is reachable by one.
A reader pointed at a layer directory therefore sees exactly what that layer wrote, and materialising a node's caches never changes what it sees.

## The store

What a process holds is two objects' state. A **`Workspace`** holds the DuckDB database and the means to reach files, local or remote, which is all a standalone directory needs. A **`Store`** holds one store location — its manifest, its revision tree, its layers — and works through a workspace, which several stores share so that records from them join.

```python
ws = Workspace()  # ":memory:" by default
store = ws.store("/data/a")  # one Store per normalised location
rev = store.revision(rid)  # look one up
record = ws.at("out/")  # a standalone directory, read under its own manifest
layer = store.layer(rid)  # one layer read alone, under the store's manifest
```

A call reaches the workspace explicitly only where nothing in hand carries one: `ws.store`, `ws.at`, and the `con` a tool converting a framework object is handed. Everything built _from_ something takes it from that: a revision from its store, a `Record` from its `Resolver`, a `WorkingRecord` from its base record.

**The location is required and absolute.** `ws.store("")` raises, and a local path is resolved, so neither a later `chdir` nor a process with another cwd moves it — there is no default location left to fall back to. `layer_dir`, `resolved_dir` and the manifest's location derive from it and nothing else.

**The location is authoritative, the database is disposable.** What lives in a workspace's `database` is never the record: deleting it loses at most uncommitted edits. A file-backed one keeps staged edits across a crash, the `revisions` cache across runs, and gives DuckDB room to spill. A location is not reused: every cache keyed by id assumes what an id names never changes, which a fresh UUID over write-once files guarantees and a location wiped and written again does not.

### The tree beside the layers

```text
<location>/
├── manifest.json
├── revisions/<id>.json        # {"id": ..., "parent": ...}
└── layers/<id>/
```

Beside `layers/` rather than inside a layer, so a layer directory stays exactly what the layer wrote and listing the tree is one listing over small files. One file per revision because a file named by a fresh UUID is write-once like a layer, so two processes creating revisions in one location never write the same object; it is written create-only through [files](#files-local-and-remote), so that is enforced rather than assumed.

The workspace's `revisions` table is a cache of those files for every store on it, keyed by `(location, id)`. It cannot go stale, only incomplete, since a revision's parent never changes, so it is only ever added to: `revisions()` lists `revisions/` once and reads only the files the table lacks, and `revision(id)` that misses reads the file and each parent not yet held, raising `KeyError` where the first is absent. Two cursors adding one row at once conflict, and the row is the same whoever wins, so the loser moves on.

### Files, local and remote

Tables go through DuckDB. Everything else — the manifest, the revision files, listing them — goes through the workspace's `Files`, picked by the URI's scheme: a URI without `://` is local, and any scheme but `s3://` raises.

```python
class Files(Protocol):
    def read_text(self, uri: str) -> tuple[str, Version] | None: ...  # None on a miss
    def write_text(
        self, uri: str, text: str, *, expect: Version | Absent | None
    ) -> Version: ...
    def list(self, prefix: str) -> list[str]: ...  # names directly under prefix
    def exists(self, uri: str) -> bool: ...
```

`expect` is the precondition: `Absent` writes only if nothing is there, a `Version` only if the object is unchanged since it was read, `None` unconditionally. Locally every write lands under a temporary name and is moved into place, so a reader meets a whole file or none: `Absent` is a hard link, which the OS refuses over an existing file, and a `Version` — the content's SHA-256 — is checked and replaced while holding a lock on a sibling `<name>.lock`, which is what makes the check and the write one step.

Remotely, `Files` is on [boto3](https://boto3.amazonaws.com/), behind the optional extra `datarecord[remote]`. `expect` maps to `put_object`'s conditional headers — `IfNoneMatch="*"` for `Absent`, `IfMatch` for a `Version`, which is the object's ETag — and a refused write (`412`, or `409` for a racing one) raises `PreconditionFailedError`. They guard the revision files, create-only by the server's guarantee, and the [manifest's compare-and-swap](writing.md#the-manifests-compare-and-swap); not the layer's parquet, which DuckDB's `httpfs` writes unconditionally under a fresh UUID. They hold only as far as the server honours them: SeaweedFS checks them atomically from 4.18, AWS S3 since November 2024.

The configuration is the AWS environment and config files, and nothing datarecord-specific. boto3 reads it itself; DuckDB gets `CREATE SECRET (TYPE s3, PROVIDER credential_chain)`, to which a set `AWS_ENDPOINT_URL` adds its `ENDPOINT`, `URL_STYLE 'path'`, `USE_SSL` per its scheme and `CHAIN 'env;config'`, since a self-hosted server has no bucket-subdomain DNS and no instance-metadata service to probe. Both are set up on the first `s3://` URI a workspace is handed, so a purely local one never pays for either.

### Crossing a process boundary

`Revision` serialises its store as its location, `{"id": …, "parent": …, "store": "/data/a"}`, and validates back through `Workspace.process().store(uri).revision(id)`, reading the revision file and each parent the process lacks — so `ancestry()` answers in a fresh process. `Store` pickles the same way.

That is the one default that survives, and nothing reaches it implicitly but deserialisation: `Workspace.process()` is created on first use, on `:memory:`, and code wanting its own records joinable with deserialised ones names it.
