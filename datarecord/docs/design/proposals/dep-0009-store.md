<!--
SPDX-FileCopyrightText: datarecord contributors

SPDX-License-Identifier: CC-BY-4.0
-->

# DEP 9: a `Workspace` holds the connection, a `Store` holds a location

| DEP     | 9                                                              |
| ------- | -------------------------------------------------------------- |
| Title   | a `Workspace` holds the connection, a `Store` holds a location |
| Author  | Jonas Hörsch                                                   |
| Status  | Implemented 2026-10-10                                         |
| Created | 2026-10-09                                                     |
| Version | Unreleased                                                     |

Landed in four steps ([landing](#landing)) on [layers](../layers.md#the-store), [writing](../writing.md), [the working record](../working-record.md#edits), [the read path](../read-path.md#a-cursor-per-thread), [consuming a record](../tools.md) and [the module layout](../module-layout.md); this page is kept as the argument for the change rather than as the current description, and those pages are authoritative where the two disagree.

The departures are all in the remote `Files`. boto3 uses path-style addressing whenever `AWS_ENDPOINT_URL` is set, as DuckDB's secret does, since a self-hosted server has no bucket-subdomain DNS. A failure setting up `httpfs` raises rather than leaving a workspace that fails on its first remote read. A `403` on a read or an `exists` counts as a miss, since S3 answers one for an absent key the caller may not list, and a `409` counts as a refused write alongside `412`, since that is how a server reports a racing conditional write.

One claim: **what a process now gets from `duck`'s module globals is two objects' state, not one.** A `Workspace` holds the DuckDB connection and the means to reach files, local or remote, which is all a standalone directory needs. A `Store` holds one store location — the directory with its manifest, its revision tree, its layers — and works through a workspace, which several stores share. Every `Revision`, `Record` and `WorkingRecord` reaches its connection and its paths through the object it came from, and a revision crosses a process boundary as its store's location.

Changes [layered resolution](../layers.md), [writing a whole record](../writing.md), [the working record](../working-record.md#edits), [the read path](../read-path.md#owner-map), [consuming a record](../tools.md), [the module layout](../module-layout.md) and [what a data record is](../index.md#what-a-data-record-is), for the optional remote dependency.

## What starts it

Each claim below was checked against `49b7268`; the last three rows were found while checking the others.

| claim                                                                                                                       | holds?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| --------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `default_connection()` is a process singleton `Revision` attaches lazily, deserialisation included                          | **Yes, and worse than stated.** The default connection is `:memory:`, and the `revisions` table lives only in it. A revision deserialised in a new process reattaches to an empty tree: `Revision.model_validate_json(child.model_dump_json()).ancestry()` returns `[]`. The serialised form (`{"id", "parent"}`) does not even say which store it belongs to.                                                                                                                                        |
| the base URI is `DEFAULT_BASE_URI` (from `DATARECORD_BASE_URI`) plus `_BASE_URIS` keyed by connection; tests monkeypatch it | **Yes, and the two disagree.** Only the schema consults `base_uri_of(con)` (`read_schema`, `_reconcile_schema`). Layers and caches use the process default: `write_record` calls `layer_dir(revision_id)`, `sources_to_read` and `Resolver` build `ParquetLayer(uid, schema, con)` with no `base_uri`, and `_map_uri`/`materialise` call `resolved_dir(revision_id)`. A connection opened with `connect(base_uri=X)` therefore writes its manifest under `X` and its layers under `DEFAULT_BASE_URI`. |
| an empty base makes `layer_dir`, `schema_uri` and the `layer_dir` macro fall back to the working directory                  | **Yes.** `DEFAULT_BASE_URI` is `""` unless the env var is set, so any path that misses the fixture's monkeypatch writes `layers/<id>/` into the cwd. The `layer_dir` SQL macro is registered by `connect` but called from nowhere.                                                                                                                                                                                                                                                                    |
| `_NetworkSource` builds relations on `duckdb.default_connection()` unless `write_record` calls `on_connection(con)`         | **Yes.** `write.py` checks `hasattr(source, "on_connection")`; `PyPSA.results(n)` builds `_NetworkSource(model)` with no connection, so its frames land on DuckDB's own default. `as_relation` passes any `DuckDBPyRelation` through, and the next union or replacement scan on the record's connection fails ("Cannot combine LEFT and RIGHT relations of different connections", "created by another Connection"). `WorkingRecord.set(..., kind="outputs")` reaches that through `_incoming`.       |
| revisions cannot be listed                                                                                                  | **Yes.** No API reads the table as a whole, and in a new process there is nothing to read.                                                                                                                                                                                                                                                                                                                                                                                                            |
| a remote location works                                                                                                     | **No.** `read_json` opens a URI with `urlopen`, which has no `s3://` handler, so a remote manifest is unreadable. `write_schema` writes with `open()`, and `write_record` writes a standalone directory's manifest only `if local`, so a remote manifest is unwritable too. Only the parquet goes through DuckDB's `httpfs`. A remote `write_record` also has no staging directory, so a failed write leaves part of a layer behind.                                                                  |
| a connection may be shared between threads                                                                                  | **No.** Eight threads querying one DuckDB 1.5.5 connection: seven fail with "Attempting to execute an unsuccessful or closed pending query result". `default_connection()` hands every thread the same one.                                                                                                                                                                                                                                                                                           |
| a node's materialised caches are complete once `materialised()` says so                                                     | **No.** `materialised()` takes `resolved/<id>/owner_map/inputs.parquet` to stand for the whole cache, but `materialise()` writes that map first and the resolved dims and groups after. A reader in another process can see a node as materialised and fold from half its cache, and a failed `materialise()` on a remote location leaves it that way for good.                                                                                                                                       |

The second row is the root of the third: every path helper takes `base_uri: str | None = None` and treats `None` as "the process default", so forgetting to pass one is silent. A store makes its location unavoidable rather than defaulted.

One object holding both the location and the connection would fix those rows, but at a cost: a location is needed only by the tree, and a connection by everything. Reading or writing a standalone directory would have to name a location it never uses, and two locations would each own a connection, so records from them could not be joined. So the two are split.

## The construct

```python
class Workspace:
    con: DuckDBPyConnection  # the calling thread's cursor

    def __init__(self, database: str = ":memory:") -> None: ...
    @classmethod
    def process(cls) -> Workspace: ...  # the process's, created on first use

    def store(self, uri: str) -> Store: ...
    def at(self, uri: str) -> Record: ...  # a standalone directory
    def write(self, source: LayerData | RecordLike, uri: str) -> Record: ...
    def close(self) -> None: ...


class Store:
    uri: str  # the store location: absolute, never empty
    workspace: Workspace

    def root(self, source: LayerData | RecordLike) -> Revision: ...
    def revision(self, id: UUID) -> Revision: ...
    def revisions(self) -> list[Revision]: ...
    def layer(self, id: UUID) -> Record: ...  # one layer, read alone

    def layer_dir(self, id: UUID) -> str: ...
    def resolved_dir(self, id: UUID) -> str: ...


class Revision:
    def child(self, source: LayerData | RecordLike) -> Revision: ...

    # record, ancestry(), materialise() as now
```

```python
ws = Workspace()
store = ws.store("/data/a")

root = store.root(PyPSA.to_datarecord(n, ws.con))  # a new root with this layer
child = root.child(other_record)  # a new child of root with this layer
rev = store.revision(rid)  # look one up
out = ws.write(rev.record, "out/")  # a standalone directory, read back
```

Three calls make something, one per place it can go, and each is named for what it returns:

| you hold    | call                 | you get                  |
| ----------- | -------------------- | ------------------------ |
| `Store`     | `store.root(src)`    | a new root `Revision`    |
| `Revision`  | `rev.child(src)`     | a new child `Revision`   |
| `Workspace` | `ws.write(src, uri)` | the directory's `Record` |

**What needs the workspace named, and what does not.** A call reaches the workspace explicitly only where nothing in hand carries one: `ws.store`, `ws.at`, `ws.write`, and the `con` a tool converting a framework object is handed. Everything built _from_ something takes the connection from it — `WorkingRecord(record)` from the record, `rev.child` and `rev.record` from the revision's store. Naming the workspace there as well would be a second name for one thing, which can disagree, and a check to catch it; taking it from the source makes the disagreement unrepresentable.

### The workspace

- **The connection**, on `database`, `:memory:` by default — see [the location is authoritative, the database is disposable](#the-location-is-authoritative-the-database-is-disposable).
- **Files**, local and remote — see [files, local and remote](#files-local-and-remote). Both DuckDB's `httpfs` and boto3 read the AWS environment, and are set up the first time the workspace is handed a `://` URI, whether a store's location or a directory's; today `httpfs` is loaded only for a remote _base URI_, so an `s3://` directory read through a connection with a local base has no `httpfs`. A purely local workspace still never pays `PROVIDER credential_chain`'s metadata probe.
- **Standalone directories.** `at(uri)` reads one and `write(source, uri)` writes one. Both need only the connection and files. `at` requires the directory's own `manifest.json` and raises if it has none: a directory without one is a tree layer, read under its store's schema through `store.layer(id)`. Today `Record.at` falls back to the connection's base URI for that case, which is the coupling this split removes.
- **Its stores.** `store(uri)` returns this workspace's store at `uri`, the same object for the same normalised location, so two calls do not hold two views of one tree. The map is filled with `dict.setdefault`, which is atomic, so two threads asking for a new location at once still get one store.
- **A cursor per thread** — see [a cursor per thread, a relation per thread](#a-cursor-per-thread-a-relation-per-thread).

### The store

- **The location.** Required and non-empty: `ws.store("")` raises `ValueError`. A local path is resolved to an absolute one, so neither a later `chdir` nor a process with another cwd moves it. That ends the working-directory leak by construction — there is no fallback left to fall back to.
- **The tree.** Persisted at the location, not in the connection — see [the tree lives beside the layers](#the-tree-lives-beside-the-layers).
- **Paths.** `layer_dir`, `resolved_dir` and the manifest's location derive from the location and nothing else.

What it hands out:

- **`Revision`s**, from `root`, `revision` and `revisions`, and from `child` on a revision. A revision carries its store, and `child`, `record`, `materialise()` and `ancestry()` reach the connection and paths through it. `Revision.create`/`Revision.get` and their `con=` go.
- **`Record`s**, from `revision.record` and `store.layer(id)`. A `Record` keeps exposing `con` — the calling thread's cursor, read through its `Resolver` — because that is how [a tool](../tools.md) building from one reaches DuckDB SQL.

A store holds no connection of its own and has no `close`; closing is the workspace's.

### A revision exists only by writing its layer

`write_record(revision_id, source, con, *, uri=None)` splits by where the result goes:

- **`store.root(source)`** and **`rev.child(source)`** create a revision and write `source` as its layer, in one call. There is no empty revision: `Revision.create` and the source-less `child()` go, and branching is writing a child.
- **`ws.write(source, uri)`** writes a standalone record carrying its own manifest, and returns it as `ws.at(uri)` would. It is the one call taking a URI, because a directory hangs from no tree.

`child` lives on the parent rather than as `store.write(source, parent=…)`, which would name the store twice — a parent is always its own store's. It is not `rev.write`, which would read as changing `rev` when layers are [write-once](../layers.md#a-layers-data-is-write-once). And a call per destination, rather than one taking a `NewChild | Directory` target, because the destinations need different things — a tree write the location and the tree, a directory write only a connection — and return different things, which a target union could only express through overloads.

**The revision file is written last, and its existence is what makes the layer real.** Locally, a failed write leaves nothing: the layer is staged into a sibling and renamed, as now. Remotely there is no rename, so a failed write can leave part of a layer behind — but without a revision file no `revision()`, `revisions()` or ancestry reaches it. A remote write becomes atomic in what any reader can see, and its leftovers are unreachable rather than half-read. Sweeping orphaned layers is a follow-up.

So a tree write runs in three steps: **the layer, then the manifest, then the revision file.** The manifest check comes after the layer rather than before it as today, so a layer whose schema turns out incompatible, or whose write fails, leaves the manifest untouched as well as unreachable; the manifest is never widened for a layer that does not exist.

`materialise()` follows the same rule: the maps other than `inputs`, the resolved dims and groups, then `owner_map/inputs.parquet`, the file `materialised()` reads. Locally each file is written under a temporary name and renamed, because `to_parquet` creates the file at its final path before it is complete and a reader meeting it mid-write fails rather than misses. Two writers materialising one node then write the same content, so that race is harmless.

A standalone directory has no revision file, so there **the manifest is written last**: `ws.at` requires one, which gives `ws.write` the same property, and a directory whose write failed reads as no record rather than part of one. Before any `COPY`, a remote `ws.write` refuses a URI under which `Files.list` finds anything, as the local write refuses an existing directory. Unlike a layer's UUID the caller picks this URI, and DuckDB's `COPY` would overwrite an existing record's files before the `Absent` manifest write could fail, leaving a mix of both under the old manifest. The check and the write are two steps, so two writers racing to one new URI can still mix; a standalone directory has one writer.

The tests that create a revision and hand-write its layer files keep doing so through a helper in `tests/fixtures.py` over the store's private revision-file write; no public API makes an empty revision.

The write path itself — staging into a sibling locally, the refusal of an existing directory, validation — is otherwise untouched ([writing](../writing.md)).

### A `WorkingRecord` does not write

`WorkingRecord(record)` takes no `con`: it stages on `record.con`, and `_base_resolver`'s "base reads through another connection" check has nothing left to check. It loses `commit`, and `NewChild`, `Directory` and `Target` go with it. What it gains is **`edits`**, its staged layer as the `LayerData` it already is (`StagedSource`, [staging as a layer](dep-0004-staging-as-a-layer.md)):

```python
w = WorkingRecord(rev.record)
w.set("p_nom", 100.0, entity=["gen1"])
edited = rev.child(w.edits)  # the delta, as a child layer
ws.write(w, "out/")  # base plus edits, flattened
w.rollback()
```

`commit` did three things, and each now has one owner. Which rows to write — the delta for a child, the flattened record for a directory — is the caller's choice of `w.edits` or `w`, where `commit` chose it by target. Which parent — `NewChild()` defaulted to the base's revision, looked up by `revision_id` in `_base_revision` with its own error for a base that is no node — is named by the caller, who built `w` from it. Clearing the staging area is `rollback()`, called or not: a `WorkingRecord` still holding its edits after a write reads exactly what it did before.

The cost is one mistake nothing catches: `rev.child(w)` writes the whole resolved record as a child layer rather than the delta. It reads back correctly, just larger, and there is no cheap guard, a resolved record being a valid layer source too. `edits` is the name that has to carry it.

The other mistake is caught. `other.child(w.edits)`, with `w` built over a different revision, would write a delta computed against the wrong parent — an axis edit carries its base's sibling columns — and read back wrong. `NewChild()` made that impossible by defaulting the parent; `child` keeps it impossible by comparing a staged source's base revision with its own id and raising on a mismatch.

A `WorkingRecord` still needs a base, so there is no empty start. Building one from a schema alone would have nothing to take a connection from, so it would be the workspace's (`ws.new(schema)`); that is a follow-up, not part of this change.

### The tree lives beside the layers

A store that serialises as its location is only useful if the location is enough to find the tree, and today it is not. Each revision becomes one file, written once, right after its layer:

```text
<location>/
├── manifest.json
├── revisions/<id>.json        # {"id": ..., "parent": ...}
└── layers/<id>/
```

Beside `layers/` rather than inside a layer: a layer directory stays exactly what the layer wrote, which is what lets a foreign reader consume it ([deletion](../layers.md#deletion)), and listing the tree is one listing over small files rather than a probe into every layer. One file per revision rather than one table because a file named by a fresh UUID is [write-once](../layers.md#a-layers-data-is-write-once) like a layer, so two processes creating revisions in one location never write the same object — which a shared DuckDB file or a single `revisions.parquet` could not promise on S3. Written create-only through [files](#files-local-and-remote), so write-once is enforced by the store rather than assumed. JSON rather than parquet because it is one small document, like the manifest beside it, read and listed through `Files` as the manifest is. The UUID is drawn in Python rather than by `gen_random_uuid()`, since the layer directory is named by it before any row exists.

The workspace's `revisions` table stays, as a cache of those files for every store on it: `(location, id, parent)`, so `revisions()` and `revision(id)` filter by location — a revision of another store on the same workspace is not this store's — while ancestry, a walk from a revision already found, needs none. It cannot go stale, only incomplete, for the same reason [a node cache never needs invalidating](../layers.md#a-layers-data-is-write-once): a revision's parent never changes. So it is only ever added to:

- `revisions()` lists `revisions/` once through `Files.list`, compares the names against the table, and reads only the files it does not hold — one listing per call rather than one read per revision, which on S3 is one request per thousand revisions rather than one per revision.
- `revision(id)` that misses the table reads `revisions/<id>.json`, then each parent the table does not hold, until it reaches one it does; `KeyError` where the first file is absent.

Two cursors adding one row at once conflict: DuckDB fails the second with `TransactionException`, even under `ON CONFLICT DO NOTHING`. The row is the same whoever wins, so the insert catches it and moves on.

`revisions()` returns every revision, unordered; a `created` field is for whoever first needs chronology.

**Existing locations.** A location written before this change has layers but no `revisions/`, so it reads as an empty tree. The project holds no compatibility promise, and the fix is one-off: export the `revisions` table of any DuckDB file used with `connect(database=…)` as one JSON file per row. A location only ever opened on `:memory:` has no tree to recover — which is the first row of [what starts it](#what-starts-it).

### Files, local and remote

Two kinds of I/O, with one owner each:

- **Tables go through DuckDB**, as now: reading and writing parquet and globbing it, over `httpfs` for a remote URI.
- **Everything else goes through the workspace's `Files`** — the manifest, the revision files, listing them, and whether a layer exists:

```python
class Files(Protocol):
    def read_text(self, uri: str) -> tuple[str, Version] | None: ...  # None on a miss
    def write_text(
        self, uri: str, text: str, *, expect: Version | Absent | None
    ) -> Version: ...
    def list(self, prefix: str) -> list[str]: ...  # names directly under prefix
    def exists(self, uri: str) -> bool: ...
```

`expect` is the precondition: `Absent` writes only if nothing is there, a `Version` only if the object is unchanged since it was read, `None` unconditionally. It replaces `read_json`'s `urlopen`, `write_schema`'s `open()`, and the `if local` around the standalone manifest. `list` returns names, not contents; remotely it follows S3's pages of a thousand keys.

Two implementations, picked by the URI's scheme: `s3://` is remote and a URI without `://` is local. Any other scheme raises, naming those two; reading over `https://` is for whoever first needs it.

- **Local**, on `pathlib`, which the code already uses. A local location keeps core at `duckdb`, `narwhals` and `pydantic`. `Absent` is `open(…, "x")`, which the OS makes atomic. A `Version` is the SHA-256 of the content, checked and replaced while holding a lock on a sibling `<name>.lock` (`fcntl.flock`, `msvcrt.locking` on Windows, both stdlib), with the new content written to a temporary file and renamed over the old one. The lock is what makes the check and the write one step; without it two local writers race exactly as two remote ones would on a server that ignores the headers.
- **Remote**, on [boto3](https://boto3.amazonaws.com/), behind an optional extra, `datarecord[remote] = ["boto3>=1.35.69"]`. `put_object` is what `expect` maps to: `IfNoneMatch="*"` for `Absent` (botocore 1.35.2) and `IfMatch=<etag>` for a `Version` (botocore 1.35.69, hence the floor); either fails with `412 PreconditionFailed`. A `Version` is the object's ETag.

boto3 because it is what Manta already runs on: the `playbook[s3]` extra its blocks install, the backend's `S3FileStorageService`, and `prefect-aws` in the runner are all boto3, so one S3 library serves the whole stack and the block images already carry it. Its conditional writes guard the two small files a store coordinates through: revision files become create-only by the server's guarantee rather than by trusting that a UUID never collides, and the manifest compare-and-swap. They do not guard the layer: its parquet is written by DuckDB's `COPY` over `httpfs`, which sends no condition, so remotely nothing refuses an existing layer directory. A fresh UUID makes that collision a non-event, and a failed write's leftovers are unreachable without a revision file ([above](#a-revision-exists-only-by-writing-its-layer)). Removing them is cleanup, a separate concern. `fsspec`/`s3fs` has no create-only write, and obstore, which does, would be a second S3 client beside Manta's. The cost is boto3's size and S3 alone, which is every store Manta targets.

**The manifest race closes too.** Two processes writing the first layers into a new location, or widening one location's schema at once, race on `manifest.json` today. With `expect`, the first write is `Absent`, and widening, after the layer is written, reads the manifest with its version, checks compatibility, and writes `expect=<that version>`; a writer that lost re-reads and checks again. `_reconcile_schema` is the one caller that changes.

**Only as far as the server honours the headers.** A server that ignores them accepts every write, so create-only and the manifest check would silently become last-writer-wins. For SeaweedFS, which Manta deploys (`chrislusf/seaweedfs:4.05` in `docker/compose-dev-services.yaml`), the source says:

| SeaweedFS      | `If-None-Match` / `If-Match` on `PutObject`                                                                                                                                                                                              |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| before 3.97    | ignored                                                                                                                                                                                                                                  |
| 3.97 – 4.17    | honoured, but checked once when the request arrives, before the upload: two writers racing on one key can both pass, and the later overwrites ([#7154](https://github.com/seaweedfs/seaweedfs/pull/7154))                                |
| 4.18 and later | checked again under the object's write lock as the entry is committed, so exactly one of two racing writers succeeds ([#8802](https://github.com/seaweedfs/seaweedfs/pull/8802), "make conditional mutations atomic and AWS-compatible") |

On Manta's 4.05 the revision files are safe in practice — two writers never race on one UUID — but the manifest's compare-and-swap can lose a widening inside that window. So Manta's pin moves to 4.18 or later; that is Manta's change, and this proposal names it rather than working around it. AWS S3 itself has honoured `If-None-Match` since August 2024 and `If-Match` since November 2024.

The remote tests run against SeaweedFS in a container at that version, the server Manta deploys, rather than against a mock: a mock that ignores the headers would pass exactly the tests the headers exist for.

**One configuration, two consumers.** The configuration is the AWS environment and config files, following playbook's convention, and there is no datarecord-specific one. boto3 reads all of it itself: the `AWS_*` variables, profiles, session tokens, roles, and `AWS_ENDPOINT_URL`. DuckDB gets `CREATE SECRET (TYPE s3, PROVIDER credential_chain, …)`, which resolves credentials the same way; the workspace adds only what the chain does not supply, `ENDPOINT` and `URL_STYLE 'path'` from `AWS_ENDPOINT_URL`, since SeaweedFS and MinIO need path-style addressing for want of bucket-subdomain DNS. With an endpoint set it also passes `CHAIN 'env;config'`: such a server has no instance-metadata service, and probing for one is the two-minute hang `connect` avoids today. A secret built by hand from `KEY_ID` and `SECRET` would lose session tokens and roles. There is no `remote=` override: a setting passed to one workspace would not reach the `Workspace.process()` a deserialising task builds, while the environment does.

### The location is authoritative, the database is disposable

`database` may name a DuckDB file, and what lives in it is a workspace, never the record: deleting it loses at most uncommitted edits. The tree cannot live only there — a DuckDB file takes one writer at a time, so parallel tasks would serialise on its lock, and it cannot be written to S3 — and a tree in two places is two sources of truth that can disagree, the split this proposal removes for the base URI.

Within that rule a file earns its place three ways:

- **Staged edits outlive the process.** A `WorkingRecord`'s staging tables are tables on the connection, so on a file they survive a crash. Resuming one needs a handle back to its tables, which are keyed by a random `_layer_id` today; that handle is a follow-up, not part of this change.
- **The `revisions` cache persists.** It cannot go stale ([above](#the-tree-lives-beside-the-layers)), so keeping it across runs is safe, and it saves re-reading every `revisions/*.json` of a remote location on open.
- **Room to spill.** A file-backed database gives DuckDB somewhere natural to page out a larger-than-memory plan.

**A location is not reused.** Every cache keyed by id — the `revisions` rows, the [shared fold tables](#a-cursor-per-thread-a-relation-per-thread) — assumes what an id names never changes. A revision keeps that by construction, a fresh UUID over write-once files. A location wiped and written again does not, nor does a standalone directory rewritten at the same URI, its fold being keyed by `uuid5` of the URI: a persisted database would serve the old tree or fold. Rewriting one means a fresh database, or a fresh location.

### A cursor per thread, a relation per thread

A DuckDB connection is not safe to use from two threads at once ([what starts it](#what-starts-it)). DuckDB's answer is a `con.cursor()` per thread, and measured on 1.5.5 it holds: eight threads, each on its own cursor of one database, querying one table concurrently, all succeed. Tables are shared between those cursors, so are the `revisions` cache, the staging tables and the folded owner maps. A `DuckDBPyRelation` is not: it is bound to the cursor that built it, and scanning or unioning it on another fails exactly as across connections.

So the line runs around relations alone:

- **`ws.con` is the calling thread's cursor**, made from the workspace's database on first use in that thread. One workspace serves every thread, and their work shares one database.

  ```python
  class _Cursors(threading.local):
      def __init__(self, db: DuckDBPyConnection) -> None:
          self.con = db.cursor()  # rerun by threading.local in each new thread
  ```

  A `threading.local` subclass reruns `__init__` with its original arguments in each thread that first touches it, so there is no existence check and no lock; sixteen threads taking their first cursor at once, fifty times over, all succeed on 1.5.5. A thread's cursor is dropped with the thread. A dict keyed by `threading.get_ident()` would do neither, ids being reused, and a `ContextVar` is copied into the workers of a task runner, which would share the parent's cursor.

- **Nothing but a relation holds a cursor.** `Store`, `Revision`, `Resolver`, `ParquetLayer` and `DirectorySource` hold their workspace — a layer through its store — and look up `workspace.con` per call, so every relation they build lands on the calling thread's cursor. A `Record` is then usable from any thread, and `Revision._resolver` keeps caching its `Resolver`. What they cache besides is plain values any thread computes the same, so two threads racing on one cost a duplicate, not a wrong answer.
- **A relation, and a narwhals frame over one, belongs to the thread that built it**, and so does a `WorkingRecord`, whose staging is one writer's. A relation reaching another thread's `as_relation` is [rejected](#a-relation-from-another-connection-is-rejected) as one from another connection is.

There is no thread check: concurrent misuse hits DuckDB's own error, and a check on workspace methods would miss the calls a frame makes on its own cursor.

**What a fold caches is shared, not held.** Two caches hold relations today, and both stop:

- `Resolver._cached_dims` keeps a frozen node's folded axes and groups as relations. They become tables, `dims_{dim}_{id}` and `group_{name}_{id}`, beside the `owner_map_{kind}_{id}` that `_frozen_table` already keeps. The unfrozen tail is folded on top per access, as now.
- `Record.dims` captures that dict of axis relations. It builds each frame per access through `resolver.axis(dim)` instead, as the other `_stable_cache` members already do; what those cache is the name tuples, plain data.

`{id}` is the node whose frozen layers were folded: a revision's id, the base's for a `WorkingRecord`, `uuid5` of the URI for a standalone directory. The schema is not in the key, so a table is read through `cast_declared(schema, …)` as a materialised cache already is. Today `_frozen_table` returns it uncast, so a `Resolver` reading under a manifest widened since the fold lacks what the wider schema adds.

A fold one thread builds serves every thread. Two threads that miss at once both fold and both `create`, and DuckDB fails the second with `TransactionException` ("Catalog write-write conflict"), not a name clash; the miss path catches that and `CatalogException` alike and reads the winner's table. The duplicate fold is wasted, not wrong.

Re-issuing a relation on another cursor, so that frames could move too, was considered. A relation over files and tables re-issues from its `sql_query()`, but one over a Python object (the PyPSA melt, `Index.of`, `as_relation`'s arrow landing) serialises as a memory pointer and cannot. Asking the record again costs only the plan.

### Crossing a process boundary

`Revision` serialises its store as its location:

```json
{ "id": "050c…", "parent": "8db9…", "store": "s3://bucket/my-record" }
```

A new process has to attach that to some workspace, and the code deserialising it — Prefect, between tasks — has none to pass. So it validates back through `Workspace.process().store(uri).revision(id)`, which reads the revision file and each parent the cache lacks, so `ancestry()` answers in a fresh process; `Store.__reduce__` does the same for pickle.

**This is the one default that survives**, and it is the same idea as `default_connection()`, narrowed. Nothing reaches it implicitly but deserialisation: every constructor takes an explicit workspace, and `Workspace.process()` is reached by name. It is created on first use on `:memory:`, its remote access comes from the environment like every workspace's, and its `database` does not travel — a second process could not open the same file for writing anyway.

Revisions deserialised in one process share its workspace, and frames built from their records in one thread join. Code that also builds records of its own and wants them joinable with deserialised ones uses `Workspace.process()` rather than `Workspace()` — an opt-in by name rather than the first workspace silently adopted. One that does not gets the [foreign-relation error](#a-relation-from-another-connection-is-rejected), stated at the boundary.

### `Record` moves to `layered/record.py`

`Record` lives in `layered/revision.py` today because its builders did: `Record.at` builds a `DirectorySource` and reads the schema, and `Revision.record` constructs one. With `Record.at` gone to `ws.at` and `store.layer`, and `Record.over` — the other place a `Resolver` is assembled — gone with it as a private helper in `store.py`, nothing ties it there.

It is the `Resolver`-backed implementation of `RecordLike`, so it moves beside its backing, into its own `layered/record.py`, taking `_stable_cache` with it. [Module layout](../module-layout.md)'s rule is the reason: protocols live with their implementations rather than with a consumer, and an implementation lives with what it is built over. Its own module rather than `resolve.py`, so that file stays the DuckDB fold alone rather than also carrying the narwhals face over it. The dependency runs one way — `resolve.py`, `sources.py` and `fold.py` name `Record` only in docstrings — so `layered/record.py` imports `Resolver` and nothing imports back.

What stays:

- **`datarecord/record.py` keeps its name and contents** — `RecordLike` and `LayerData`, and the vocabulary their members speak in: `LazyFrames`, `EMPTY`, `Flags`, `Frames`, `Kind`. Not `protocols.py`: most of those are value types, and a tool building frames imports `LazyFrames` from it. The two `record.py` modules are the record's vocabulary and its one implementation, told apart by package.
- **`LayerData` stays in `datarecord/record.py`**, not `mutable.py`. Its implementations are spread over `layered/sources.py`, `layered/resolve.py` and `mutable.py`, and its one consumer is `layered/write.py`; in `mutable.py` the core write path would import from the edit layer above it.
- **`layered/revision.py` keeps `Revision` and `ancestry`**, which is what its module docstring already says it is.

`mutable.py`, `datarecord/__init__.py` and the tests importing `Record` from `datarecord.layered.revision` import it from `datarecord.layered.record`.

### Tools take the connection; `on_connection` goes

`Tool.to_datarecord(model, con)` and `Tool.results(model, con)` take the connection their frames are planned on, required. A tool is handed `con`, not a workspace or a store: it plans relations and has no business with directories, locations or the tree. `build(record)` is unchanged: it reads `record.con` as `_connection` does now. So `_NetworkSource.con` becomes required, and `_melt_con`, its `duckdb.default_connection()` fallback and `on_connection` go, and `write.py` loses its `hasattr` hook. Core names no tool before or after: the connection is now an argument of the tool protocol in `datarecord/tools/base.py`, not a structural hook in the write path ([module layout](../module-layout.md)).

The call sites that broke now read:

```python
root = store.root(PyPSA.to_datarecord(n, ws.con))
w = WorkingRecord(root.record)
for attr, frame in PyPSA.results(n, w.con).items():
    w.set(attr, frame, kind="outputs")
```

### A relation from another connection is rejected

Copying one onto the target connection would collect it to arrow on its own connection — a full materialisation the caller never asked for, and one that fails anyway if that connection has been closed. Making it impossible by construction covers what this package builds, but a caller can still hand `set` a relation from a connection of their own.

So `as_relation` rejects it, and says why: binding `con.sql("FROM native")` costs no read and raises `duckdb.InvalidInputException` for a relation from another connection, which it re-raises as a `ValueError` naming the fix — build the frame on `record.con` in this thread, or hand over a non-DuckDB frame and let it land. Construction removes the case for every path this package owns; the check turns the case it cannot own from an `InvalidInputException` three calls later into a sentence at the boundary. The same check catches a frame built on another thread's cursor.

## What is deleted

- `duck.DEFAULT_BASE_URI`, the `DATARECORD_BASE_URI` env var, `_BASE_URIS`, `base_uri_of`, `default_connection`, `connect` (its body moves into `Workspace`), and the unused `layer_dir` SQL macro with `_register_macros`. A caller wanting the env var writes `ws.store(os.environ["DATARECORD_BASE_URI"])`.
- Every `base_uri: str | None = None`. `layer_dir`, `resolved_dir` and `schema_uri` become `Store` methods; `ParquetLayer` holds its store in place of `con` and `base_uri`, and `DirectorySource` its workspace in place of `con`; `read_schema(store)`, `write_schema(schema, store)`, `Fold.read(…, store)`, `resolve.materialise(…, store)`, `materialised(revision_id, store)` and `sources_to_read(ancestry, store, schema)` take one, and `_map_uri` becomes a `Store` path. `Resolver` holds its workspace in place of `con`; `source_for` builds a `ParquetLayer` on the store its sources share, and a standalone record, whose one source is a `DirectorySource`, never reaches that path.
- `read_json` with its `urlopen`; the manifest and revision files go through `Files`.
- `Revision.create`, `Revision.get`, the source-less `Revision.child()`, `Record.at`, `Record.over`, and `con=` on `WorkingRecord`.
- `write_record` as a public name, `WorkingRecord.commit`, `NewChild`, `Directory`, `Target` and `_base_revision`. `datarecord.write_record`, `datarecord.layer_dir`, `datarecord.connect`, `NewChild` and `Directory` leave `__all__`; `Workspace` and `Store` join it.
- `on_connection`, `_NetworkSource._melt_con`, and `_base_resolver`'s connection check.
- `Resolver._cached_dims`, for tables; and the axes dict `Record.dims` captures.

A `con` argument stays where a function plans relations — `fold_axis`, `union_all_by_name`, `try_read_parquet`, the fold — since those take the connection they compose on, not a location.

## The test fixtures

```python
@pytest.fixture
def workspace():
    ws = Workspace()
    yield ws
    ws.close()


@pytest.fixture
def store(workspace, tmp_path):
    return workspace.store(str(tmp_path))
```

They replace `base_uri` and `con`: no monkeypatch, since there is no global to patch. `layer_dir(x.id)` in the tests becomes `store.layer_dir(x.id)`, `Revision.create(con)` followed by hand-written layer files goes through the `tests/fixtures.py` helper, `Record.at(layer_dir(x.id), con)` becomes `store.layer(x.id)`, and a test needing the connection reads `workspace.con`. `test_two_roots_in_one_process_read_their_own_schema` becomes two stores on one workspace, and gains an assertion it could not make before, that each location's layers land under it. The `connect(base_uri=…/"unrelated")` cases in `test_write.py` and `test_mutable.py` read a standalone directory through a second connection, and become `ws.at(out)`; what the `test_mutable.py` one pins besides — that edits are validated under their base's schema, not a connection's — gets a test of its own.

New tests pin what this adds: a revision round-tripped through `model_dump_json` into `Workspace.process()` reads its ancestry back; threads sharing one workspace read concurrently, each on its own cursor, and reuse one folded owner map; two threads missing that cache at once both get it; a store and a standalone directory on SeaweedFS (≥ 4.18, in a container) write and read their manifest and revision files; a second create-only write of one revision file fails; two writers widening one manifest end with both widenings or a reported incompatibility, never one silently lost; a remote write that fails part-way leaves no revision `revisions()` lists; a remote `ws.write` to a non-empty URI is refused before it writes; two threads adding one revision row at once both succeed; a fold table built before the manifest widened reads under the wider schema; a `Record` built in one thread reads in another; and `child(w.edits)` on a revision other than `w`'s base raises.

## Landing

1. **`Workspace` and `Store`, with the tree at the location**: the local `Files`, `revisions/<id>.json` read back into the `revisions` table, a revision serialising its store's location, the fixtures, every `con=`/`base_uri` path switched over, a cursor per thread with the fold caches as shared tables, `as_relation` rejecting a foreign relation, and the globals deleted; `Record.at` and `Record.over` go, and `Record` moves to `layered/record.py`. One commit: the half-honoured base is a bug either side of the change, keeping both would be the alias [AGENTS.md](https://github.com/energy-models/datarecord/blob/main/AGENTS.md) forbids, and the tree at the location fixes deserialisation only once a revision carries the location. Until step 2, `Revision.create` writes the revision file before its layer.
2. **Writing**: `store.root`, `rev.child(source)` and `ws.write` replacing `write_record` and `Revision.create`, so the revision file, or a directory's manifest, is written last; `WorkingRecord(record)` with `edits`, and `commit` and its targets gone.
3. **Remote files**: the boto3 `Files` behind `datarecord[remote]`, the AWS environment configuring it and `httpfs` together, and `_reconcile_schema` on conditional writes. Manta's SeaweedFS pin moves to 4.18 or later before it relies on them.
4. **Tools**: the protocol takes `con`, and `on_connection` goes.

The design pages follow in the same commits: [layers](../layers.md) gains `revisions/<id>.json` beside `layers/`, the revision file as what makes a layer real, and the store a revision carries; [writing](../writing.md) documents `root`, `child` and `ws.write`, and the remote write's atomicity; [the working record](../working-record.md#edits) replaces committing with `edits`; [the read path](../read-path.md#owner-map) the fold tables shared between threads and read through `cast_declared`; [tools](../tools.md) the `con` parameter; [module layout](../module-layout.md) adds `store.py` for both classes, `files.py` and `layered/record.py` for `Record`, takes `Record` off the top-level `record.py`'s line, and narrows `duck.py` to relation helpers; [what a data record is](../index.md#what-a-data-record-is) names `datarecord[remote]` as the one optional dependency of core. `record.md` and the usage pages name `write_record(…, con)` and `WorkingRecord(…, con)` and follow too.
