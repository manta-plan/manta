# datarecord integration

Working doc for integrating datarecord into Manta's backend-side components (backend, runner,
playbook, playbook-library). Process plan: `~/.claude/plans/drag-a-comb-across-tidy-cake.md`.
Fork divergence is tracked in `datarecord_changes.md`.

| Step | Status |
|---|---|
| 0. Vendor and characterize | Done: vendored, baselined, DuckDB 2.0 fixed, docs audited |
| 1. Requirements and use cases | In progress. Use cases in `datarecord_cases.md` |
| 2. Target API | Not started |
| 3. Stubs | Not started |
| 4. Tests | Not started |
| 5. Implement | Not started |

## Step 0: what datarecord is, from source

Everything here was read from `datarecord/src` at the baseline commit, not from its docs.

### Baseline

Vendored at `521fef2` (2026-10-14). Upstream's suite passes at its `pixi.lock` versions and
fails under DuckDB 2.0.0. The fork fixes that and passes on both 1.5.5 and 2.0.0. Details are
in `datarecord_changes.md`.

### Public API

`datarecord` exports:

| Symbol | Kind | Role |
|---|---|---|
| `Workspace` | class | A DuckDB connection, plus file access for local paths and `s3://`. `Workspace(database=":memory:")`. `Workspace.process()` is the per-process singleton. |
| `Store` | class | One location holding a tree of revisions. Obtained from `ws.store(uri)`. |
| `Revision` | pydantic model | One node in a store's tree: `id`, `parent`, `store`. |
| `Record` | frozen dataclass | The resolved, read-only view of a revision or a standalone directory. |
| `WorkingRecord` | class (subclass of `Record`) | Accumulates edits over a base record. |
| `RecordLike` | Protocol | What any record answers: `schema`, `dims`, `properties`, `groups`, `attributes`, `outputs`, `flags()`. |
| `Frames`, `LazyFrames` | type alias, Mapping | Name to `narwhals.LazyFrame`. Lazy: nothing is read until `.collect()`. |
| `Flags` | frozen dataclass | Which dims an attribute's rows vary along or broadcast over. |
| `Schema`, `Dimension`, `AttributeSpec`, `PropertySpec`, `Group`, `Trait` | pydantic models | The declared schema. |

The main entry points:

- `Workspace.at(uri) -> Record` reads a standalone record (a directory with its own
  `manifest.json`).
- `Workspace.write(source, uri) -> Record` writes a standalone record. It fails if anything
  already exists at `uri`.
- `Workspace.store(uri) -> Store`.
- `Store.root(source) -> Revision`, `Store.revision(id) -> Revision`,
  `Store.revisions() -> list[Revision]`, `Store.layer(id) -> Record` (one layer alone, with
  nothing beneath it folded in).
- `Revision.record -> Record`, `Revision.child(source) -> Revision`,
  `Revision.materialise()`, `Revision.ancestry() -> list[UUID]`.
- `WorkingRecord(base)` has `set`, `add`, `remove`, `add_group`, `remove_group`, `rollback`,
  and `edits` (a `StagedSource`, written with `revision.child(w.edits)`).

The PyPSA tool lives in `datarecord.tools.pypsa`, behind the `pypsa` extra. Its singleton is
`PyPSA = PyPSATool()`:

- `PyPSA.build(record) -> pypsa.Network`
- `PyPSA.to_datarecord(network, con) -> RecordLike`
- `PyPSA.results(network, con) -> Frames` (the solved outputs, in long form)
- `PyPSA.requires(record)` and `PyPSA.verify(record)` return `Requirements`, which says what
  the record lacks for PyPSA.

### Addressing and process boundaries

- A location is a local path (no `://`) or an `s3://` URI. Any other scheme raises
  `ValueError` (`store.py`, `Workspace.files`). Local paths are resolved to absolute paths.
- S3 credentials come from the standard AWS environment. `AWS_ENDPOINT_URL` switches to
  path-style addressing, which works with SeaweedFS and MinIO. This matches how Manta's
  `playbook.blocks.storage` already configures S3.
- A store's layout: `manifest.json` (the schema), `revisions/<uuid>.json` (`{id, parent}`),
  and `layers/<uuid>/` (parquet).
- A standalone record is one directory whose `manifest.json` carries an `id`.
- A `Revision` serializes to `{"id", "parent", "store": "<uri>"}`. It pickles, and
  validates back, through `Workspace.process()`, reading the revision files it needs from
  the store. Nothing cached travels with it. So a `Revision` can already cross a process
  boundary the way Manta's `DataRecord` does today.
- Layers are write-once. A child revision's layer holds only what it changed.

### Constraints that will matter to Manta

- Entity names have to be unique across component types. `PyPSA.to_datarecord` rejects a
  network where, say, a `Load` and a `Bus` share a name. The example network in
  `playbook_library/examples.py` (`bus`, `gen`, `load`) meets this.
- Each attribute name has one spec across the whole record. The test fixture drops PyPSA's
  `Carrier.efficiency` and `Carrier.marginal_cost` for this reason (`tests/conftest.py`).
- The vendored package reports version `0.0.0`. Upstream CI replaces it at release.

### Docs vs source

An agent audited `README.md`, `CONTRIBUTING.md`, `docs/usage/`, `docs/api/` and `docs/design/`
(not `proposals/`) against the source, running most examples. Nothing on S3 was exercised,
and the mkdocs site wasn't built. I re-ran gaps 14 and 24 myself. The usage pages are mostly
right. The schema pages and the editing examples are where the docs are most wrong.

**Corrections to the API above**, from the audit:

- `Dimension`, `AttributeSpec` and `PropertySpec` take a narwhals dtype *instance*, or one
  of 7 manifest encodings (`String`, `Float64`, `Int64`, `Boolean`, `Date`, `{"Enum": ...}`,
  `{"Datetime": ...}`). DuckDB and numpy type names fail validation. Other narwhals dtypes
  (`nw.Int32()`, say) construct but fail to serialize at write time.
- `WorkingRecord.set(attribute, value, *, kind="inputs"|"outputs", **coords)`. A frame value
  takes one label per coordinate keyword, not a list. `kind="outputs"` needs the result
  declared in the schema.
- `WorkingRecord(base)` needs a concrete `Record`, not just a `RecordLike`.
- `Store.layer(id)` needs a `UUID`. A string raises `AttributeError`. `Store.revision` happens
  to accept either.
- `LayerData` (the write-side protocol) exists but isn't exported.
- `datarecord.tools` exports nothing. The PyPSA tool is `datarecord.tools.pypsa.PyPSA`, an
  instance of `PyPSATool`.

**Behaviours that matter for Manta**, beyond doc errors:

- **`to_datarecord` returns `_NetworkSource`, not a `Record`.** `PyPSA.build` and
  `WorkingRecord` both reject it (verified). It has to be written first, with `store.root`,
  `rev.child` or `ws.write`, and then read back.
- **A value set for every label (a NULL coordinate) on a `partial` dim comes back as one row
  per label.** In a revision tree, the layer stores the single NULL row, so labels added in
  later revisions still pick the value up. `ws.write` writes what it reads, so a standalone
  record stores the expanded rows and the value no longer reaches labels added later
  (verified: 1 stored row in the layer, 2 in the standalone file). Records that must keep
  that behaviour belong in a store, not in standalone directories.
- **A NULL value doesn't reach labels added later if a materialised ancestor sits in
  between**, and never reaches labels staged in the same `WorkingRecord`. The docs mention
  this only in `open-questions.md`.
- **Caches are keyed by manifest id, not location.** A copied standalone directory keeps its
  id, and the same workspace serves the original's cached fold for the copy.
- **A deserialized `Revision` always reattaches to `Workspace.process()`**, whichever workspace
  made it.
- **`Schema.version` is never checked.** Any value is accepted, and the manifest keeps the last
  writer's.
- **Listing keys isn't free.** `list(record.attributes)` builds the fold over every input file.
  Listing outputs reads every output file.
- **Remote configuration is per process.** It comes only from the environment
  (`AWS_ENDPOINT_URL` and so on), and the first `s3://` URI in a workspace installs `httpfs`.
- **Store locations are normalised differently by scheme.** A local path goes through
  `Path.resolve()`, so it follows symlinks (`/tmp` becomes `/private/tmp` on macOS). An S3 URI
  only loses its trailing slash, so `s3://b//x` and `s3://b/x` would be different stores
  (read, not run). `file://` and `gs://` raise `ValueError`.
- **`pixi.toml` caps `duckdb <2`; `pyproject.toml` doesn't.** Upstream's own dev environment
  stays on 1.5.

**Gap list.** B = broken (the example fails or the symbol is missing), M = misleading (it runs
but does something else), S = stale naming. Line numbers refer to the baseline docs.

| # | Doc | Claim | Reality | Sev |
|---|---|---|---|---|
| 1 | CONTRIBUTING.md:107 | `Record.at(uri)` | `Workspace.at(uri)` | B |
| 2 | usage/schema.md:62 | a DuckDB type name works as `dtype` | `"VARCHAR"`, `"TIMESTAMP"` fail validation | B |
| 3 | design/schema.md:15,24,38, examples at :104-113, :163-169, :200-202, :268, :376-377 | `dtype: str`, `"float64"`, `"str"`, `"int64"`, `"datetime64[us]"`, `"bool"` | narwhals dtype; all of these fail | B |
| 4 | usage/editing.md:23, design/working-record.md:81 | `set(name, frame, entity=["wind1"])` | a list is refused with a frame; `entity="wind1"` works | B |
| 5 | usage/editing.md:24 | `series.rename_axis("snapshot")` | the usage schema's dim is `timestep` | B |
| 6 | usage/editing.md:30, design/working-record.md:86 | `set("p_nom", ..., scenario="high")` | `p_nom` doesn't vary over `scenario` | B |
| 7 | usage/editing.md:33 | `set("p", ..., kind="outputs")` | the usage schema declares no results; KeyError | B |
| 8 | usage/editing.md:42 | `set("entity_type", "Load", ...)` | `Load` isn't in the usage schema's Enum | B |
| 9 | usage/tools.md:43 | results need not be declared | `set(kind="outputs")` requires a declaration; the writer doesn't | B |
| 10 | design/working-record.md:141 | `nw.col("value").clip(upper=0.9)` | narwhals spells it `upper_bound=` | B |
| 11 | design/record.md:139 | a declared group with no rows reads as empty | KeyError: the group is absent | B |
| 12 | docs/api/ | "every public symbol" | `Group`, `PropertySpec`, `Trait` and `PyPSATool` are on no page; `PyPSA` renders as a bare instance | B |
| 13 | usage/reading.md:23, design/record.md:175 | listing keys reads nothing | listing builds the fold over every input file | M |
| 14 | usage/reading.md:50, design/record.md:114,157 | a value held once is answered once | NULL on a `partial` dim is expanded per label (see above) | M |
| 15 | usage/editing.md:25,36, design/working-record.md:83,97, design/record.md:149 | a NULL reaches labels added later | not past a materialised ancestor, never within one `WorkingRecord` | M |
| 16 | design/working-record.md:107 | `kind="outputs"` is refused for a property | silently patches the input property | M |
| 17 | design/working-record.md:45-47 | read members come structurally, not by inheritance | `WorkingRecord` subclasses `Record` | M |
| 18 | design/working-record.md:327 | staging a result the schema never declares | `set` refuses an undeclared result | M |
| 19 | design/working-record.md:315-318,330 | staging tables named `staged_axis_entity_<id>` | names hash the dim or attribute | M |
| 20 | usage/editing.md:87 | staged rows never touch disk | they persist in a file-backed workspace (`Workspace("x.duckdb")`) | M |
| 21 | design/schema.md:274 | a trait switch must be `bool` | no dtype check; Float64 is accepted | M |
| 22 | design/schema.md:502-504,527 | readers refuse an unexpected `version` | `version` is never read | M |
| 23 | usage/schema.md:62 | `dtype` is any narwhals dtype | only 7 have a manifest encoding | M |
| 24 | usage/tools.md:21, design/tools.md:20 | `to_datarecord` returns a `Record` | `_NetworkSource`; not buildable or editable until written (verified) | M |
| 25 | design/index.md:46 | a PyPSA `Network` presents itself as a record | it doesn't; the adapter lives in `datarecord.tools.pypsa` | M |
| 26 | design/format.md:101 | `verify` reports cross-type name clashes | `to_datarecord` raises instead | M |
| 27 | usage/writing.md:15, design/layers.md:40 | layers are staged and renamed into place | local only; remote writes go in place | M |
| 28 | design/open-questions.md:29-31 | writing into an open record invalidates its cache | no such operation exists | M |
| 29 | several | minor: one optional extra (there are two, `pypsa` and `remote`); install docs omit `[remote]`; module-layout.md:9 says the module split is still to come (it's done) and omits `layered/fold.py`; reading.md:63 uses an undeclared attribute (`marginal_cost`); format.md:32 says every axis file has the same shape | | M |
| 30 | usage/reading.md:9, usage/writing.md:15, usage/index.md:47, design/index.md:35,56, design/record.md:7, design/working-record.md:40-41, design/tools.md:17-21 | "the `Record` protocol" | the protocol is `RecordLike`; `Record` is the class | S |
| 31 | design/working-record.md:357 | a `members` member | doesn't exist | S |
| 32 | design/tools.md:67, design/schema.md:212 | `entity_types` and `members` apply defaults | the private `_members()` does | S |
| 33 | design/tools.md:51 | "`build` takes a `Record` rather than a record" | garbled; the frames must be DuckDB-backed | S |

Two docstrings that render on the API pages are also wrong. `Tool.results` (`tools/base.py:316`)
describes the long schema as "`name`, the dim columns, `value`". `WorkingRecord.set`
(`mutable.py:842-855`) promises six value forms and lists five.

**Accurate, as far as the audit checked:**

- README snippets
- `usage/layers.md`
- `design/writing.md`
- `design/format.md`'s layout and columns, checked against real parquet files
- `design/layers.md`'s Revision fields, paths, caches and round trips
- the rest of `usage/editing.md` and `usage/tools.md`
- the usage schema helpers
- the schema validation rules
- `design/read-path.md`'s owner map and caches
- every `:::` target in `docs/api/`, all 18 of which exist

## Step 1 inputs

Facts gathered so far, to work from when we define requirements. None of these are decisions.

**Manta today.** `DataRecord` (`playbook/src/playbook/blocks/core.py:34`) is `{url}`. It is
serialized in `playbook/blocks/run_one.py` (the `MANTA_BLOCK_RESULT` line),
`runner/src/runner/flows.py` (Prefect flow parameters and results), and the backend's
`run_request.data_record_url` and `run_service` (`"record": {"url": ...}`). Each block
writes a whole new netCDF network under `output_base`. Every block's I/O goes through
`playbook_library/pypsa_helpers.py` (`to_network`, `write_network`), whose docstring
already calls it the one place to change for "richer record storage".

**What the backend intends.** The TODO at `backend/src/manta/services/run_service.py:389`
says data records should be tracked in Manta's database and served as
`GET /v1/data-records/{uuid}/content`, with `GET /v1/runs/{uuid}/outputs` listing a run's
records.

**Frontend access through Quack.** Quack is DuckDB's HTTP client-server protocol. The
polished version ships in DuckDB 2.0.0, and DuckDB-Wasm can connect as a client. A server
exposes the full SQL surface of its instance, read and write. A token authenticates a
connection, and an authorization callback (a function, or a SQL macro) sees each query with
its connection id and can deny it or rewrite it. Sources:
[announcement](https://duckdb.org/2026/05/12/quack-remote-protocol),
[security](https://duckdb.org/docs/2.0/quack/security.html),
[extension](https://duckdb.org/docs/2.0/core_extensions/quack).

**What follows from these.**

- If the frontend reaches records through Quack, the fork has to run on DuckDB 2.x. It does
  now (see `datarecord_changes.md`).
- A Quack server's default exposure is everything its session can see. Restricting a user to
  the records of projects they own would go through the authorization callback, and would
  have to line up with Manta's existing Keycloak-based ownership checks.
- A `Revision` already serializes to the shape a cross-process handle needs.
- Layered child revisions would let a block write only what it changed, instead of a whole
  network.

## Step 1 decisions

- **"Workspace" in the use cases means a Manta `Project`** (`backend/src/manta/entities/project.py`),
  not datarecord's `Workspace`, which is a DuckDB connection.
- **One datarecord `Store` per Project, for now.** Playbook runs read from and write into the
  project's existing store; a run doesn't get a store of its own. A run writes several
  records, which the runners and the backend both have to reach.

  What follows, from source (read, not run):

  - **One schema per project.** A store has one `manifest.json`, and every layer written to
    it must be `compatible_with` it (`layered/write.py`, `reconcile_schema`). Every network
    imported into a project has to fit one schema. The `Carrier.efficiency` clash from step 0
    becomes a project-wide constraint.
  - **Concurrent runs can share the store.** Revision files and layers are create-only under
    fresh UUIDs, and the manifest is updated by compare-and-swap with retries, so two runs
    widening the schema at once both land or one gets an incompatibility error.
  - **A store can hold several trees.** `Store.root` writes a revision with no parent and
    doesn't check for an existing one.
  - **The store has to live on S3 (SeaweedFS) in deployment.** Block containers are removed
    when they finish (`docker/block-image.Dockerfile`), so a local path isn't reachable from
    both the runners and the backend.
- **A block's output is a child revision of its input.** A block reads its input revision,
  stages its changes in a `WorkingRecord`, and writes them with `revision.child(...)`, so its
  layer holds only what it changed. A playbook run is a chain of revisions in the project's
  tree.

## Step 1 work items

Items are grouped by the code they touch, so each group costs one agent's exploration:

| Agent | Items | Output |
|---|---|---|
| A, playbook side | 1, 2, 3 | `datarecord_step1/playbook.md` |
| B, backend | 4, 6 | `datarecord_step1/backend.md` |
| C, Quack | 5 | `datarecord_step1/quack.md` |

The agents run on Sonnet. C goes first as a pilot, and A and B launch after its output and cost
have been checked. Item 7 isn't given to an agent: `datarecord_name_analysis.md` already holds
the analysis, so it's the user's decision. Item 8 runs after the agents.

**Rules every item shares:**

- Write findings to the agent's output file and edit nothing else. In particular, no
  changes to `datarecord/` or to Manta code.
- At most ~150 lines per output file. Stop once each question has an answer or an open
  question. Don't run test suites.
- Don't re-verify facts this doc already states.
- Requirements, not designs. Where a choice is needed, give a recommendation and list it under
  "Open questions" for the user. Don't decide it.
- Cite `file:line`. Mark each claim *verified* (ran it) or *read* (from source).
- Run datarecord code with `datarecord/.venv/bin/python -I`, not `uv run` in `datarecord/`,
  which writes a `uv.lock`.
- Nothing outward-facing: no issues, PRs or comments.
- Take this doc's "Step 1 decisions" as settled.

| # | Slug | Question |
|---|---|---|
| 1 | `handle` | What replaces `DataRecord {url}` as the cross-process handle? Trace every place it is serialized (`run_one.py`, `runner/flows.py`, `run_request.data_record_url`, `run_service`) and say what a serialized `Revision` needs at each one: S3 environment in block containers, reattaching to `Workspace.process()`, and a name that isn't `DataRecord`. |
| 2 | `block-dims` | How do `BlockDims` (`requires`/`adds`/`removes`) map onto datarecord's dims and groups? Should a playbook be checked against the schema before it runs, during the run, or not at all? |
| 3 | `pypsa-blocks` | Make playbook-library's PyPSA blocks the first consumer. A block mutates a `pypsa.Network`, but its output should be a child layer holding only what changed. Is that delta derived by diffing the network against the record, written by the block through `WorkingRecord`, or is the whole network written as the layer? Cover `pypsa_helpers.py`, the `_NetworkSource` write-first constraint, and unique entity names. |
| 4 | `backend-inventory` | Backend tracking and REST: what Manta's DB records versus what the store holds, and which is the source of truth. Covers the endpoints in the `run_service.py:389` TODO, listing a project's records, creating a project's store and its first root (where the schema comes from), and ownership checks consistent with the run endpoints. |
| 5 | `quack-serving` | FE Load: research Quack in DuckDB 2.0. Can the Python client serve it? Which instance should serve: one per project, per user or per session, and who owns its lifecycle? How does the auth callback map onto Keycloak ownership? What does a client with full SQL reach: S3 secrets, `httpfs`, local files, other projects? Read-only enforcement belongs here too. Security is the main concern. |
| 6 | `fe-edits` | FE Edits: how GUI changes get back to the store, via Quack writes or REST. What "flattened" means in revision terms (a child of which revision?). Staging, where it happens, and how it interacts with concurrent runs. The `partial`/NULL semantics from step 0. How playbooks find the edited revision. |
| 7 | `format-freeze` | Which on-disk format changes from `datarecord_name_analysis.md` must land before Manta persists a record? Check each against the source and against upstream's open issues and PRs, and estimate the cost of each. Produce a recommendation for the user to decide. |
| 8 | `verification` | After 1–7: define the end state of the tracer bullet and how to verify it. Rewrites "Verification" below. |

## Step 2: target API

Not started.

## Verification

To be defined in step 1.
