# Step 1: backend tracking, REST and FE edits (items 4 and 6)

Requirements only. **verified** = I ran it (`datarecord/.venv/bin/python -I`, local stores in `/tmp/step1-backend`).
**read** = from source. No S3, Prefect or backend code was run. "Workspace" means a Manta `Project`.

## Item 4
**1. DB versus store, and the source of truth.**
- A revision file is `{"id", "parent"}` and nothing else (**verified**, `store.py:360-368`): no author, run, name or
  timestamp. The manifest holds the schema, not a revision list (`write.py:185-245`, **read**). The store says what
  exists; it can't say why. Only S3 `LastModified` gives a time.
- Recommendation: **the store is the source of truth for existence, tree and data.** Revision files are create-only and
  written last (`store.py:347-358`, **read**), so a revision named anywhere exists. **The DB is the source of truth for
  provenance and naming**: run and step, FE-edit author, label, created-at, refs (Q7). It never holds layers or schema.
- How the backend learns of revisions. It reads no run result today. `get_run*` uses only flow-run state and parameters
  (`run_service.py:106-116`). `run-playbook` doesn't set `persist_result` (`flows.py:166`; `run-block` does, `:80`) and
  returns only the final record (`execution.py:126`, `flows.py:186`). `MANTA_BLOCK_RESULT` (`run_one.py`) is the stdout
  contract for a standalone driver, not the Prefect path.
- Requirement: use both, for different jobs.
  (a) The result names the run's *final* revision. With the run's recorded *input* revision, its records are
  `ancestry(final) - ancestry(input)` (`revision.py:23-48`, **read**). That holds for a linear chain only: a wired-in
  input doesn't add a parent, and a failed run has no result.
  (b) `Store.revisions()` is one S3 listing plus one GET per unseen file, then cached (`store.py:439-472`, **read**). The
  backend reconciles with it on run completion and on inventory reads, registering unknown revisions as unattributed.
- Disagreement. A revision with no DB row is expected (crash, failed run, direct write): register it, run NULL. A DB row
  with no revision file shouldn't happen (nothing deletes revisions): surface it as an error. A layer with no revision
  file can exist, since `_write` writes layer, manifest, then revision file, so an incompatible schema leaves the layer
  on S3 (**read**). Nothing lists it; it needs garbage collection.
- The backend has no `datarecord` or `duckdb` dependency (`backend/pyproject.toml:8-32`, **read**). Manta's S3 config is
  `S3_*` (`s3_config.py:9-32`); datarecord reads only `AWS_*` (`store.py:134-164`), so the backend exports those before
  its first `s3://` use. One credential serves every project: isolation is by key prefix and ownership checks.

**2. REST endpoints.** Names are suggestions; all apply Q4.
- `GET /v1/projects/{project_uuid}/data-records`: the project's revisions, flat, each with id, parent id, created-at,
  origin (run uuid and step, `fe-edit`, `import`, `unattributed`), name, `current` flag. Parents let the FE draw the tree.
  Reconciles first (Q1b).
- `GET /v1/data-records/{uuid}`: one revision's metadata plus a schema summary (dims, attribute names). Listing keys
  builds the fold over every input file (step 0), so cache it per revision; revisions are immutable.
- `GET /v1/runs/{uuid}/outputs` (TODO at `run_route.py:101`, `run_service.py:389-396`): the run's revisions (Q1a),
  replacing the S3 file listing of netCDF outputs.
- `GET /v1/data-records/{uuid}/content`: **open question** what it returns. Options: the whole folded record as an export
  file (netCDF or zipped parquet), one layer (`Store.layer`, `store.py:474`), or nothing. Quack serves interactive reads,
  so `content` is only for download. Recommend an export of the folded record, deferred until a consumer asks. One layer
  alone is a delta, rarely meaningful.
- Query: Quack owns SQL. Recommend no REST query at first; if needed, a bounded, paginated attribute read. Open question.
- Writes: `POST /v1/projects/{uuid}/data-records` (import a network as a root, Q3) and
  `POST /v1/data-records/{uuid}/edits` (Q5). Only create-project exists today (`project_route.py`): no list, get or delete
  of projects, so deleting a store has no hook.

**3. Creating the store and its first root.**
- Location: `s3://{bucket}/{project_uuid}/datarecord`, built by one function. S3 URIs are only trailing-slash-normalised,
  so `s3://b//x` and `s3://b/x` would be two stores (step 0, **read**). Existing keys are `{project_uuid}/…`
  (`s3_file_storage_service.py:34,63,90`). The run listing narrows to `runs/…` (`run_service.py:397`), so it's unaffected.
- Timing: recommend **lazy, at the first root.** No public API makes an empty revision (`tests/fixtures.py:349`, **read**).
  An empty `pypsa.Network()` fails (**verified**: default snapshot `"now"` isn't a timestamp, `ConversionException`). One
  with snapshots roots fine (**verified**) but forces an arbitrary snapshot. The URI is derived, so the DB needs no flag:
  the store exists when `revisions()` is non-empty.
- Schema: nobody supplies it. The first root's source states it (`reconcile_schema`, `write.py:185`); for PyPSA, the
  tool's. An empty network and a one-bus network gave equal manifests apart from set order (**verified**, 114 attributes),
  so it looks fixed by the PyPSA version, though step 0's `Carrier.efficiency` clash shows custom columns can change it.
  Later layers must satisfy `compatible_with`, which allows widening only (`schema.py:1432-1495`, **read**): a PyPSA upgrade
  that removes or retypes an attribute breaks every existing project. A failed import returns 4xx naming the reasons.
- Import needs PyPSA, which the backend lacks. Recommend a Prefect job in the PyPSA image, as blocks run.

**4. Ownership.** As for runs: 404 if the project is missing, `AuthorizationError` (403) if `project.owner_id != user.id`
(`run_service.py:198,258,285,326`). Requirements:

- Every endpoint resolves a project first. `/data-records/{uuid}` needs the revision-to-project mapping from the DB; an
  unregistered id is 404, never a store lookup.
- **The run request must stop taking a free `data_record_url`** (`run_request.py:22`, passed straight to the flow at
  `run_service.py:213`). That is an arbitrary S3 URL today. It should carry a revision uuid; the backend checks the
  revision belongs to the project and builds the `{id, parent, store}` handle itself. Otherwise a run could read another
  project's store.
- No store URI or S3 credential goes to clients.

## Item 6
**5. The edit payload.** Staged rows live in connection-scoped DuckDB tables (`mutable.py:272-290`, **read**), so staging
can't span HTTP requests. Requirement: the FE accumulates a change list and sends it whole; the backend stages, writes and
discards in one request. It must express:

- `base`: the revision uuid the FE read. Required.
- `ops`, an ordered list (a `remove` then `add` restates a label, so order matters):
  - `set`: `attribute` (or property), `value`, `kind`, `coords` (coordinate to one label or a list). An omitted coordinate
    is NULL, meaning every label; the payload must tell omitted from explicit null. `value` is a scalar, a sequence aligned
    to the one list coordinate, a label-to-value map, or long rows carrying their own keys (`mutable.py:819-870`).
  - `add`: `dim`, `labels`, `columns` (properties and nested-dim parent keys).
  - `remove`: `dim`, `labels`; a nested dim's label is a tuple in `Schema.axis_key` order.
  - `add_group` (`group`, rows with the struct column, `into` label, properties); `remove_group` (`group`, `keys` as
    tuples in `Schema.group_key` order).
- `set` also takes a narwhals expression (a function of the current value); that can't travel as JSON. Open question: drop
  it, or define a closed set of named transforms (scale, offset, clip).
- Datetime labels travel as ISO strings, coerced to the dim dtype. A failing op returns 422 with its index (datarecord
  `KeyError`/`ValueError` are 4xx, storage errors 5xx). The payload can't change the schema.

**6. "Flattened and stored as a record."**
- It means `base.child(w.edits)`: a delta layer, a child of the revision the FE named (`mutable.py:1910-1927`).
  `rev.child(w)` writes the whole folded record instead: same reading, larger.
- A stale base isn't a storage error, and edits can't be rebased there: `child()` refuses edits staged over another
  revision with `ValueError` (**verified**, `revision.py:165`). Three policies remain:
  - **Branch**: stage over the FE's base, write as its child, a sibling of the run's output. **Verified**: it has the edit
    (`p_nom` 99) and not the run's change (`marginal_cost` 10, not 7). No conflict is possible.
  - **Replay**: re-run the ops over the newer revision. **Verified**: gives `p_nom` 99 and keeps the run's
    `marginal_cost` 7. It's a re-edit, not a merge. Ops naming removed labels raise `KeyError`, and an omitted coordinate
    reaches whatever the new base resolves, under step 0's NULL rules (not past a materialised ancestor, never labels
    staged in the same record). It may not mean what the user saw.
  - **Reject**: 409 when `base` isn't the project's current revision.
- Recommendation: **branch by default**; it keeps what the user saw and loses no run output. Replay only on request, 409
  with the op index on any `KeyError`. Rejecting every stale edit would make each run completion fail someone's save.
- Staging runs in the backend (or a worker): a throwaway `WorkingRecord` over `base.record`, which reads the fold from S3
  per request. Whether the backend uses the `Workspace.process()` singleton or a workspace per request is **untested**:
  `Store` has per-thread cursors (`store.py:52-65`) but I ran no concurrent `WorkingRecord`s. Open question.
- Afterwards the backend registers the revision (`fe-edit`, user) and tells the Quack instance, which can't see new
  revisions on its own (`quack.md`).

**7. How playbooks find the edited revision.** A run takes an input revision (Q4), so the backend needs a name for "the
revision to start from". Recommendation: a **refs** table, `(project_id, name, revision_uuid)`, with a default ref
`current` per project, git-style:

- `current` moves only by compare-and-swap in the DB (`UPDATE … WHERE revision_uuid = :expected`); a miss is a 409.
- `Run` gains `input_revision` and, on success, `output_revision` (`run.py` has neither). Today a run's input is only in
  Prefect's parameters (`run_service.py:110-116`), lost with Prefect's history.
- `POST /runs` takes an optional revision; omitted means `current`. A successful run advances `current` only if it's still
  the run's input; otherwise the output stays a branch tip. An FE edit on `current` advances it likewise; on a stale base
  it branches and leaves `current` alone.

## Requirements
1. The store is the source of truth for revisions, tree and data. The DB holds one row per revision (project, uuid, parent,
   origin, user, name, created-at) plus refs, never layers or schema.
2. The backend reads a run's final revision from the run result (`persist_result` on `run-playbook`, or the block flow
   results) and reconciles against `Store.revisions()` on completion and inventory reads. A row without a file is an error.
3. `Run` records `input_revision` and `output_revision`. The run request carries a revision uuid, never a URL.
4. One function builds `s3://{bucket}/{project_uuid}/datarecord`; clients never see it. The first import creates the store
   and states the schema; an incompatibility returns 4xx.
5. The backend depends on `datarecord[remote]` and DuckDB 2.x and exports `AWS_*` from its `S3_*` settings.
6. Endpoints: list records, one record, run outputs, import, edits, refs, content (deferred), each with the owner check.
7. Edits take `base` plus an ordered op list, stage in one request, write `base.child(edits)`, and fail whole. A stale base
   branches by default.
8. A new revision is registered in the DB and announced to the project's Quack instance. Layers orphaned by a failed
   schema reconcile need cleanup (not scoped here).

## Open questions
1. What does `content` return: an export of the folded record (recommended, deferred), one layer, or nothing?
2. Is REST query over attributes needed, or is Quack the only query path?
3. Stale-base policy: branch by default (recommended), replay on request, or reject?
4. Do `set` edits include expression values, and if so which named transforms?
5. Who runs import: a Prefect job in the PyPSA image (recommended), or the backend with PyPSA added?
6. Is a `refs` table with a default `current` the right model, and does a successful run advance it automatically?
7. Staging concurrency: `Workspace.process()` singleton or a workspace per request? Untested.
8. Results from Prefect result persistence, or from the block flow runs?
9. Is a PyPSA-version schema change a per-project migration we accept, given widening-only compatibility?
