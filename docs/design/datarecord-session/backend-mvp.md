# Design note: MVP backend without a revision index

What the BE does in the MVP, in line with issue #283. It lists stores, revisions and references from DR and `store.json`. It adds no Postgres table for them. The Postgres revision index of the [backend note](backend.md) is the later step that this one prepares.

Part of the datarecord-session plan, draft 9. Start with the [overview](README.md). The codes F, S, R, D and I point to the [appendix](appendix.md). This note describes the MVP step that comes before sections 1 and 2 of the [backend note](backend.md).

In the MVP the BE keeps no copy of stores, revisions or references. It lists stores with one S3 listing per project. It lists revisions with DR's `Store.revisions()` and `Store.claims()`, and keeps the manifests in a DR workspace in its memory. Revision facts live in the commit `meta` under `manta.` keys. References live in `store.json`, which only the BE writes. The BE moves a reference by a conditional PUT of `store.json` with `If-Match`, which detects a concurrent commit. The fork point comes from `Revision.ancestry()` of both sides. Runs keep finding their revisions through Prefect, as today. The public routes, the response shapes, the `store.json` form and the `meta` keys are those of the later index. So `sync_store` can fill the index from what the MVP wrote, and the FE does not change. The MVP step is good for one owner per project, few revisions per store and one BE host. Move to the index on one of three triggers: several writers per project, a cold listing above its time budget, or queries across stores and projects.

Conventions of this note: "read" means verified in code, with file and line. DR lines are at the pinned commit `468f69b0` (D19), paths under `src/datarecord/`. "Inferred" means not verified. "Unverified" marks a fact that needs a test.

## 1. What issue #283 decided

The issue text (read on 2026-11-19 with `gh issue view 283 --comments`):

- Decision of 2026-11-12: for the MVP, Manta keeps scenario and revision context in the datarecord, not in new Manta DB tables.
- "In the long run this moves to the Manta DB, because these are Manta concepts."
- Which run produced which revision comes from the Prefect metadata, through the existing run endpoints.
- PR #281 replaces `revisions.json` and `<store>.labels.json` with `store.json` and `manta.` keys in the per-revision `meta`.
- Open: how the FE lists a project's scenarios and their revisions.

The comment of 2026-11-16 adds:

- Each revision's `meta` has a `kind`, and a result records the block that created it.
- `store.json` records the head revision of each scenario. Manta walks up the tree from the head to find earlier revisions.
- The keys of `store.json` can collide. This is "fine for now, since this moves to the BE tables in Jonas' plan (#250)".

Scope, as the text says it:

| Topic | Covered by #283 |
|---|---|
| Stores, revisions, references (names, labels, kinds, parents) | Yes: no new tables in the MVP. |
| Run to revision links | Yes: through Prefect, as today. |
| Postgres index later | Yes: named as the long-run target. |
| Session tables (`datarecord_sessions`, `datarecord_session_registrations`) | Not mentioned. They hold runtime state, not scenario or revision context. See [session management](#10-session-management). |

So #283 does not reject the index. It orders it after the MVP. This note is that order.

PR #281 is open. Its `store.json` has `label`, `description` and `references` with `revision`, `label`, `description` per name. It has no `base`. Its names follow the slug scheme `<scenario>/<playbook>`.

## 2. Place in the phases

The MVP step is phase 2 of the [phases](appendix.md#4-phases). The phases that it shapes:

| Phase | Content |
|---|---|
| 0. DR stack | Merge and new export. The new export writes `store.json` in the form of [the shared contract](#3-the-shared-contract), with `base`. |
| 2. BE store routes over DR | The import reads `store.json`. The routes of [the shared contract](#3-the-shared-contract) answer from DR and `store.json`. No table, no `sync_store`. |
| 4. BE sessions | Session tables, launcher, `ensure`, relay. The two session tables stay ([session management](#10-session-management)). |
| 5. FE | Port the record client to the BE routes. The routes and shapes are those of [the shared contract](#3-the-shared-contract). |
| 6. Commit path | Claim, token and changeset. The reference moves by a conditional PUT of `store.json` ([references](#6-references-in-storejson)). |
| 8. Later | WR, Kubernetes, claim flow for blocks, shared sessions, and the revision index: the tables of [revision index](backend.md#1-revision-index), filled by `sync_store` from what the MVP wrote ([path to the index](#14-path-to-the-index)). |

What builds on the MVP step without change:

- The session service. It receives store names and revision ids only ([session service](session.md#3-session-service)). It never reads a BE table.
- The commit path inside the session: `Claim.commit` with the layer token ([commit flow](storage-commit.md#1-commit-flow)).
- The two tokens and their policies ([the two tokens](storage-commit.md#2-the-two-tokens)).
- The FE: every route and response shape of [the shared contract](#3-the-shared-contract).
- The writer of `store.json`. The revision index writes the same file after each change.

## 3. The shared contract

The MVP and the later index serve one contract. The FE sees no difference.

### Routes

| Route | MVP source | Index source |
|---|---|---|
| `GET /v1/projects/{id}/stores` | S3 listing and `store.json` | `datarecord_stores` |
| `GET /v1/projects/{id}/stores/{store}/revisions` | `Store.revisions()`, `Store.claims()`, `store.json` | `datarecord_revisions`, `datarecord_references` |
| `POST /v1/projects/{id}/stores/{store}/revisions` | commit flow, `store.json` by `If-Match` | commit flow, SQL compare-and-set |
| `POST /v1/projects/{id}/stores/{store}/references` | `store.json` by `If-Match` | SQL insert, then `store.json` |
| `PATCH`, `DELETE /v1/projects/{id}/stores/{store}/references/{name}` | `store.json` by `If-Match` | SQL update, then `store.json` |
| `GET /v1/projects/{id}/session/changes`, diff registrations | fork point from `Revision.ancestry()` | fork point from `parent_id` |

Both steps need the three reference routes, to create a scenario, change its label and delete it. The [routes table](backend.md#5-routes-and-quack-relay) lists them.

### Response of the revision listing

```json
{
  "store": "BEL-pre-aggregated-incl-patches-incl-results",
  "revisions": [
    {"id": "07b0661e-…", "parent": "9ec88f52-…", "status": "committed", "kind": "scenario",
     "created_by": "3f2a…", "run": null, "step": null,
     "created_at": "2026-11-10T17:54:52Z", "committed_at": "2026-11-13T18:02:11Z", "meta": {}}
  ],
  "references": [
    {"name": "patch", "kind": "scenario", "revision": "07b0661e-…", "base": "inputs",
     "label": "Patch", "description": "…", "updated_at": null}
  ]
}
```

- `run` is the Manta run UUID, `step` the playbook step. Both are null where the writer recorded none.
- `meta` holds the entries without the `manta.` prefix.
- `status` is `claimed` or `committed`.
- The response has no `user_id`. The MVP cannot fill it ([revisions](#5-revisions)).

### The `store.json` form

The form of the [revision index](backend.md#1-revision-index), unchanged:

```json
{
  "label": "Belgium, pre-aggregated, every solve",
  "description": "Inputs, one patch and six results.",
  "references": {
    "inputs": {"revision": "9ec88f52-…", "label": "Base case"},
    "patch":  {"revision": "07b0661e-…", "base": "inputs", "label": "Patch", "description": "…"}
  }
}
```

One optional addition: `updated_at` per reference, an ISO time that the BE sets at each change. Readers ignore an unknown key, as far as PR #281's reader goes (inferred). The index fills its column `updated_at` from it.

### The `meta` keys

Every key is a flat string, as decided for nested `meta` in [decisions](appendix.md#2-decisions). The writer sets them as follows.

| Key | Set at | By | Index column |
|---|---|---|---|
| `manta.kind` | claim | BE (session commits), block (runs) | `kind` |
| `manta.created_by` | claim | as above: an opaque user UUID, or the block name | `created_by` |
| `manta.committed_at` | commit | the committer | `committed_at` |
| `manta.run` | claim | block, new | `run_id` (through `runs.uuid`) |
| `manta.step` | claim | block, new | `step` |

A claimed `meta` is fixed, and a commit may only add keys (F9; read: `store/manifest.py:221-245`). So the keys set at claim cannot change later.

## 4. Stores of a project

DR has no notion of a set of stores. The BE lists them itself.

1. The BE lists `<bucket>/<project_uuid>/` with the delimiter `/`. One request per 1000 entries.
2. For each folder, the BE reads `<store>/store.json`. A folder without `store.json` is no store.
3. The BE returns `name` (the folder), `label` and `description`.

`store.json` is the marker of a complete store. The example data copy writes it last, as it writes `revisions.json` last today (read: `backend/src/manta/services/example_data_service.py:59-66`). PR #281 moves the marker to the manifests; the MVP moves it to `store.json`.

The data catalogue of the home page (#282) is the same listing on the prefix `EXAMPLE_DATA_PREFIX`. Neither step needs a table for it.

Today the BE has no store route. The FE reads the catalogue from quack-server (read: `frontend/src/features/home/lib/record-server.ts:52-67`). The BE checks only that a run's revision has a manifest (read: `backend/src/manta/services/run_service.py:299-319`).

## 5. Revisions

### Listing

The BE holds one DR `Workspace` per process, in memory, with the backend key. Its tables `revisions` and `schemas` cache each manifest that it reads. The cache gains rows only, so it can be incomplete but never stale (read: DR `docs/reference/store.md:98`).

For each listing:

1. `Store.revisions()` lists `layers/` once and reads only the manifests that the workspace does not hold (read: `store/store.py:985-1034`).
2. `Store.claims()` lists `layers/` again and reads `claim.json` of each pending layer (read: `store/store.py:1050-1070`). It never caches.
3. The BE reads `claim.json` of each new committed revision for `created_at`, and keeps the time in a dict in memory. A claim file is kept after the commit (read: `store/manifest.py:163-178`).
4. The BE reads `store.json` for the references.

A new revision shows at the next listing. No writer has to tell the BE.

### Fields

| Field | MVP source | Verified |
|---|---|---|
| `id`, `parent` | manifest | read: `store/manifest.py:96-100` |
| `status` | `revisions()` gives `committed`, `claims()` gives `claimed` | read: `store/store.py:1007, 1059` |
| `kind`, `created_by` | `manta.kind`, `manta.created_by` | the 2026-11-13 export has both on results, and `manta.created_by` is missing on scenarios (appendix 8.1) |
| `created_at` | `created` of `claim.json` | read: `store/manifest.py:178`. The manifest has no time field (read: `store/manifest.py:96-100`). |
| `committed_at` | `manta.committed_at`, else `created_at` | as decided in [decisions](appendix.md#2-decisions) |
| `run`, `step` | `manta.run`, `manta.step` if written, else null | new keys, see [results of runs](#8-results-of-runs) |
| `meta` | manifest `meta` without the `manta.` keys | |

DR reads the claim of a committed layer only through the private `Store._read_claim` or `ClaimFile.read` in `store/manifest.py:191`. A public call is an optional request ([requests to DR](#15-requests-to-dr)).

### What `meta` cannot hold

A manifest is create-only (read: `store/manifest.py:128-136`). So `meta` holds only facts that are true at the claim or commit and never change.

| Fact | Why not in `meta` | MVP answer |
|---|---|---|
| Name, label, description | They change. | `store.json` |
| Which revision a scenario points to | It moves. | `store.json` |
| A Manta user that must become null on user deletion (`users.id`, `ON DELETE SET NULL` in [decisions](appendix.md#2-decisions)) | The manifest cannot be edited. | `manta.created_by` holds the user's UUID, never the username. After user deletion the UUID points to nothing. In the MVP a project has one owner and cascades with it, so its folder goes too (inferred: #139 does not specify the S3 side yet). |
| Facts learned after the commit (run outcome, "promoted", "archived") | Too late. | Prefect for runs. Nothing else in the MVP. |
| A corrected `kind` | Claimed `meta` is fixed. | A new export. |
| Who moved a reference, and when | It is not a fact of a revision. | `updated_at` in `store.json`. The user is not recorded. |

## 6. References in `store.json`

### Who writes

Only the BE writes `store.json`, with the backend key. The session has a read token for the project folder and a write token for one layer (storage-commit, [the two tokens](storage-commit.md#2-the-two-tokens)). It cannot write `store.json`. Blocks do not write it.

### Moving a reference at commit confirmation

The request names the reference R and the revision E that the FE expects there. The BE runs these steps.

1. At request start, the BE reads `store.json` with its ETag. If R does not point to E, it refuses with 409 before it claims. This fails fast.
2. The BE claims, mints the token, calls the session, and compares the returned manifest with its claim ([commit flow](storage-commit.md#1-commit-flow)). The new revision is N.
3. The BE reads `store.json` again, with its ETag T.
4. The BE checks two conditions. R points to E. The `manta.kind` of N equals the `manta.kind` of E. If one fails, it answers 409.
5. The BE sets R to N and `updated_at` to now. It writes the file with `PUT` and the header `If-Match: T`.
6. On 200 the move is done. The BE answers 201 with N and R.
7. On 412 another writer changed the file after step 3. The BE goes back to step 3. After five tries it answers 503.

On 409 the body names N. N exists, and no name points to it. This is the same outcome as in the [revision index](backend.md#1-revision-index).

The kind check of step 4 replaces the column `kind` of `datarecord_references`. A reference takes the kind of the revision it points to. A move keeps the kind, so the kind never changes.

### Two concurrent commits on one reference

Two tabs commit on `patch` at E. Both pass step 1.

| Step | Commit 1 | Commit 2 |
|---|---|---|
| 2 | commits N1 | commits N2 |
| 3 | reads `store.json`, ETag T0 | reads `store.json`, ETag T0 |
| 5 | `PUT If-Match: T0`: 200, new ETag T1 | `PUT If-Match: T0`: 412 |
| 7 | | reads again: ETag T1, `patch` points to N1 |
| 4 | | `patch` is not at E: 409, names N2 |

A commit on another reference of the same store also changes the ETag. Its writer then gets 412 once, reads again, finds its own reference unchanged, and succeeds. So a 412 is not a conflict. Only step 4 decides a conflict.

The same steps serve the other changes. Each is one read, one check and one conditional PUT.

| Change | Check | Note |
|---|---|---|
| Create a reference | The name is free. `base` names an existing reference. | The new reference points to the current revision of its base. |
| Change a label or description | The reference exists. | |
| Rename | The new name is free. | Every reference whose `base` names the old name is updated in the same PUT. |
| Delete | The reference exists. | The `base` of dependents becomes empty ([open points](backend.md#6-open-points)). |
| First write of a store | | `PUT` with `If-None-Match: *`, as DR's `Files.create` does. |

### What the object store must support

| Need | Header | DR uses it | SeaweedFS | AWS S3 |
|---|---|---|---|---|
| Create-only write | `If-None-Match: *` on PutObject | Yes, for `claim.json` and `manifest.json` (read: `store/files.py:266-278`) | From 4.18 on, by DR's docs (read: DR `docs/reference/store.md:129`) | Yes |
| Replace if unchanged | `If-Match: <etag>` on PutObject | No. DR has no such call. | In the source that reports 4.53 (read: `weed/s3api/s3api_object_handlers_put.go:2859-2876`, local clone at commit `a576398`). Not tested. | Yes, since late 2024 (inferred, not tested here). |
| Check and write in one step | | | The check runs under a per-object lock: routed to the owner filer, or `withObjectWriteLock` (read: `s3api_object_handlers_put.go:1063-1072, 1169`, `s3api_server.go:362-380`). Not tested under a race. | Yes (inferred). |
| Cheap re-read of an unchanged file | `If-None-Match: <etag>` on GetObject, answer 304 | No | In the source (read: `s3api_object_handlers_put.go:2960-3021`). Not tested. | Yes |

The BE writes `store.json` with its own boto3 client, not through DR. boto3 1.43.87 is in `backend/uv.lock`. A botocore copy of 1.43.107 has `IfMatch` on `PutObjectRequest` (read). The BE's own version was not checked.

Two warnings:

- `docker/compose-dev-services.yaml:19` runs SeaweedFS 4.05. That is older than 4.18, so even DR's create-only claim is not safe there (inferred from DR's docs). The `s3-security` branch moves dev to 4.53 (F25). The MVP needs that move first.
- A store without conditional writes loses updates silently: the later PUT wins. GCS through its S3 interface is not a target (D11).

### One file, or one file per reference

| Concern | One `store.json` | One file per reference (`refs/<name>.json`) |
|---|---|---|
| Form | As agreed in #281 and in the backend note. | A new form. Exports and PR #281's reader change. |
| Listing | 1 GET. | 1 LIST and 1 GET per reference. |
| Commit on R | `If-Match` on the whole file. A change of another reference costs one retry. | `If-Match` on R's file. No retry from others. |
| Create | Conditional PUT of the whole file. | `If-None-Match: *`, as DR's `Files.create`. |
| Rename, with the `base` of dependents | One atomic PUT. | Several objects, not atomic. A crash leaves both names. |
| Delete | One atomic PUT. | Delete of one object, plus updates of dependents. |
| Names with `/` (`patch/perfect`) | A map key. | Nested keys. Works on S3 (inferred). |

The design keeps one `store.json`. The writers of one store are the project's owner and the BE, so retries are rare. Rename and delete stay atomic. The form stays as agreed, and the index reads the same file. One file per reference only pays with many concurrent writers per store, and then the index is due anyway.

## 7. The fork point

DR offers:

- `Revision.parent` (read: `store/store.py:1530`).
- `Revision.ancestry()`: the ids from the root to the revision, root first (read: `store/store.py:1384-1400, 1556-1564`). It reads every manifest of the chain that the workspace does not hold.

DR does not offer a common ancestor, a list of children, or a walk down the tree. A `git grep` for `common_ancestor`, `merge_base` and `descendants` in `src` and `docs` finds none.

The BE computes the fork point of a reference R with base B:

1. Resolve R and B to their current revisions from `store.json`.
2. Take `ancestry()` of both.
3. The fork point is the last id of the common prefix of the two lists.

The chains are short, and the manifests are cached after the first listing. So this costs no S3 request when warm. Children of a revision come from a full `revisions()` and a filter on `parent`. Nothing in the MVP needs them.

## 8. Results of runs

### Today

The BE finds a run's revisions through Prefect, with no index (read: `backend/src/manta/services/run_service.py`):

- The input revision is the flow parameter `record` (lines 121-124).
- Each block run publishes its output as the artifact `block-output` (lines 146-167; `runner/src/runner/flows.py:96-123`). Only the last revision of a block is published.
- TODO comments mark both as MVP shortcuts, to be replaced once Manta's database tracks data records (lines 122-123, 149-151).

Issue #283 keeps this for the MVP.

### No row to upsert

In the MVP nobody needs to learn of a new revision. A block commits, and the next listing shows the revision (`revisions()` lists `layers/` each time). What the listing lacks is the link to the run. The three ways of [runs and blocks](backend.md#2-runs-and-blocks) change as follows.

| Way | With the index | In the MVP |
|---|---|---|
| 1. Walk the parents | After a step, the BE walks from the output to the input and stores `run_id` per revision. | The BE walks on request, from the Prefect output to the input, with cached manifests. Nothing is stored. It misses revisions beside the chain. |
| 2. Layer id prefix | The BE lists by prefix. | The listing of `layers/` is already the index, so a prefix per block run finds its layers, failed claims included. Needs the same DR change: a claim accepts an id. |
| 3. Claim through the BE | The BE inserts a row at the claim. | `claim.json` is the row. The BE claims with `manta.run` and `manta.step` in the claimed `meta`. `claims()` shows pending ones. A committer can still change `meta` (F26), so the BE compares at report. |

### What the MVP does

1. The run pages keep the Prefect lookups. This is #283.
2. `write_network` adds `manta.kind = result` and `manta.created_by`. The blocks set no `meta` today (F28; read: `playbook-library/src/playbook_library/pypsa_helpers.py:74-84`). Both steps need this.
3. `write_network` adds `manta.run` and `manta.step` in the same change, as preparation for the index. The block container knows `step_name` as a flow parameter (read: `runner/src/runner/flows.py:96-101`). It does not know the Manta run UUID (F28). The BE passes it as one more flow parameter, and `run_block` hands it to `write_network`.

Point 3 matters for the index. Without it, `sync_store` must fill `run_id` from Prefect later. Prefect may have deleted old flow runs and artifacts by then (unverified: retention not checked).

## 9. Cost

### Requests per route, with nothing cached

N is the number of revisions in a store, P the pending claims, S the stores of a project. One LIST covers 1000 entries.

| Route | Requests, cold | Requests, warm | Payload |
|---|---|---|---|
| `GET .../stores` | 1 LIST, S GET `store.json` | 1 LIST, S conditional GET (304) | `store.json` is small |
| `GET .../stores/{store}/revisions` | 2 LIST, N GET manifest, N GET `claim.json`, P × (GET manifest miss, HEAD and LIST for `exists`, GET claim), 1 GET `store.json` | 2 LIST, 1 conditional GET, the new layers only | a manifest holds the full schema: 46 to 93 KB per layer (measured on the local copies of folder `2026-11-13/`) |
| `POST .../revisions` (commit) | 1 GET `store.json`, 1 GET parent manifest, 1 PUT `claim.json`, the session's commit, 1 GET and 1 PUT `store.json` | the same without the manifest | |
| Reference changes | 1 GET, 1 PUT `store.json` | the same | |
| `GET .../session/changes`, diff registration | 1 GET `store.json`, the manifests of both chains | 1 conditional GET | |
| Run pages | Prefect, as today | Prefect, as today | |

Example: the store `BEL-pre-aggregated-incl-patches-incl-results` has N = 8. A cold listing is 2 LIST and 17 GET, with 714 KB of manifests (measured on the local copy). The example project has six or seven stores with 14 revisions in all. A cold project page that lists every store is then about 50 requests and 1.3 MB.

Time: not measured. The latency of one small S3 request from the BE was not measured on SeaweedFS or on a remote bucket. The BE can run the GETs in parallel; the example data service does so with 10 threads (read: `example_data_service.py:49, 63`).

F18 does not apply here. Its 17 s is a whole record open in quack-server on DR main, with fold and scan (read: `docker/quack-server/README.md:91`). A listing reads manifests and folds nothing.

Each BE process also pays one setup. The first `s3://` store of a workspace runs `INSTALL httpfs; LOAD httpfs;` (read: `store/store.py:432`). The BE image must contain the extension, or the first request downloads it.

### Where a cache in BE memory is enough

- Manifests: always. They never change. DR's workspace is the cache.
- Claim times of committed revisions: always, in a dict.
- `store.json`: keep body and ETag. Each request sends a conditional GET; an unchanged file costs one 304.
- Listings of `layers/` and of the project folder: never cached. One LIST each, so new revisions show at once.

A BE restart loses the cache. The first listing of each store is cold again. Several BE processes each hold their own cache. Both are correct, because S3 stays the only truth.

### Where the session could answer

The session has a DR workspace with the manifests of every registered revision and its ancestors. It could answer an ancestry or a fork point without S3. This note does not use that:

- The listing routes must work without a session.
- The session receives revision ids only, and the BE resolves names ([session service](session.md#3-session-service)).
- The BE's own cache is warm after its first listing.

### The home page without a session

The home page lists projects from Postgres and the data catalogue from the example data prefix: 1 LIST and one GET per store. A project page adds the store listings above. No route starts a session.

## 10. Session management

The two session tables stay in the MVP: `datarecord_sessions` and `datarecord_session_registrations`, as in [session tables](backend.md#session-tables). Issue #283 does not mention them. They hold runtime state: which container serves a user, its tokens, its activity, and which revisions the user registered. A registration row names a revision, but only as the user's current view. The tables hold no scenario or revision context, so #283 does not cover them.

No `datarecord_stores` exists in the MVP. So a registration row names its store by name.

[Session lifetime](backend.md#3-session-lifetime), the [launcher](backend.md#4-launcher), and the [routes and Quack relay](backend.md#5-routes-and-quack-relay) apply to the MVP unchanged.

### Not taken: state in the container

The session state could live in the containers instead, with no table. The table compares the two.

| | Session tables (the design) | State in the container (not taken) |
|---|---|---|
| Sessions | `datarecord_sessions` as in [session tables](backend.md#session-tables). Registrations name the store by name. | Container labels: user, project, generation, endpoint. The BE rebuilds its map from `launcher.list()`. |
| Secrets | In the row. | Derived: HMAC of a BE key over user, project and generation. Nothing to store. |
| Registrations | Rows, replayed by `ensure`. | The running session holds them (`GET /registrations`). After a stop, the FE registers again on the error. |
| Single start | Row lock. | A container name per user and project. Docker refuses a second container of that name (unverified as a lock). |
| Activity | `last_used_at` in the row. | The session counts its own last request; the BE asks it. |
| Several BE replicas | Works. | Works on one Docker host only if the name lock and the activity query hold. In-process locks alone start two containers. |
| BE restart | Works. | Works: containers keep running, labels and the session hold the state. Idle timers restart. |
| Container stop | Registrations come back. | Registrations are lost. The FE needs a re-register path besides re-attach. |
| WR (phase 8) | The edit log needs a table anyway ([working records](session.md#6-working-records)). | Same: a table then. |

State in the container is lighter on one VM (#276). The session tables are robust and already designed, and they hold no scenario or revision context. So the tables stay.

## 11. Comparison with the revision index

| Concern | MVP step (DR and `store.json`) | Revision index (Postgres) |
|---|---|---|
| Source of truth | S3 only. No mirror. | S3, with a mirror in Postgres that `sync_store` repairs. |
| Stores of a project | 1 LIST and S GET. | 1 query. |
| Revision listing, cold | 2N + 3 requests, 46 to 93 KB per manifest. Grows with every commit. | 1 query. |
| Revision listing, warm | 2 LIST and 1 conditional GET. | 1 query. |
| New revisions of blocks | Visible at the next listing, without a report. | Visible after the BE upserts them. |
| Reference move | Conditional PUT with `If-Match`, retry on 412. | `UPDATE ... WHERE revision_id = :expected`. |
| Concurrent commits | Detected, if the store honours `If-Match` atomically (unverified on SeaweedFS). | Detected by the database. |
| Commit and move together | Two objects. A crash between them leaves an unnamed revision. | Row and reference in one transaction. The `store.json` copy is a second write. |
| Fork point | `ancestry()` of both sides, from cached manifests. | Walk of `parent_id`, or a recursive query. |
| Run of a revision | Prefect, or `manta.run` if written. | `run_id` column. |
| Claimed status | `Store.claims()`: one more LIST and a GET per pending claim. | `status` column. |
| Cleanup of claims | A BE task runs `Store.cleanup` per store of every project. | The same, plus the `claimed` rows. |
| Repair | Nothing to repair, except a reference to a missing revision. | `sync_store`. |
| User deletion | An opaque UUID stays in `meta`. Fine while a project has one owner. | `user_id` set to null. |
| Audit of reference moves | Only the last `updated_at`. Bucket versioning could keep old `store.json` files (not checked with conditional writes). | Rows can keep `user_id` and `updated_at`. A history table is easy. |
| Queries across stores and projects | A scan of every store. | SQL. |
| Several BE replicas | Correct. Each replica has its own cache. | Correct. |
| BE restart | Cold caches. | No effect. |
| Object store needs | `If-Match` and `If-None-Match` on PutObject. | `If-None-Match` only (DR). |
| Export of a store | `store.json` is always current. | `store.json` is a copy, written after each change. |
| Build effort | Listing over DR, `store.json` writer with retry, cache. No migration. | Three tables, migrations, `sync_store`, mirror writes, the `store.json` writer. |

## 12. What the MVP step cannot do, or does worse

1. Answer queries across stores or projects, such as "which runs used this revision" or "all scenarios of a user", without a scan.
2. List a large store fast when cold. Every commit adds a manifest of about 90 KB to the first read after a BE restart.
3. Record who moved or renamed a reference. `store.json` keeps the last state only.
4. Set a user to null in a revision. `manta.created_by` stays in an immutable manifest.
5. Move a reference and record the commit in one transaction.
6. Work on an object store without atomic `If-Match`. It would lose updates silently.
7. Show claimed revisions cheaply. Each listing with claims costs one more LIST and a GET per pending claim.
8. Link revisions to runs without Prefect, unless the blocks write `manta.run` and `manta.step`.
9. Name a result automatically. Run results appear through the run routes, not as references, unless the BE writes one.

## 13. What the MVP step is good for, and when to move to the index

The MVP step is good for:

- One owner per project, no sharing. #20 and #83 stay out of scope.
- Stores with tens of revisions, not thousands.
- One BE host, or a few replicas that tolerate cold caches.
- Following #283 now, while every fact that the index needs is already written in S3.

Move to the revision index when one of these holds:

1. **Several writers per project.** Sharing or collaboration gives a project more than one user. Then `user_id`, the audit of moves and contention on `store.json` matter.
2. **Listing time.** A cold store or project listing exceeds its budget, for example 1 s at the 95th percentile, on the target object store. Measure this ([open points](#16-open-points)).
3. **Queries across stores or projects.** A feature needs them: a search in the catalogue, the runs of a revision, or a user's scenarios across projects.

## 14. Path to the index

The index is a mirror of what the MVP writes. `sync_store` fills it with no migration of data:

| Column | Filled from |
|---|---|
| `datarecord_stores.name`, `label`, `description` | folder and `store.json` |
| `datarecord_revisions.id`, `parent_id`, `meta` | manifest |
| `status` | `revisions()` and `claims()` |
| `kind`, `created_by` | `manta.kind`, `manta.created_by` |
| `created_at`, `committed_at` | `claim.json`, `manta.committed_at` |
| `run_id`, `step` | `manta.run` (through `runs.uuid`), `manta.step`. Else from Prefect, while it keeps the runs. |
| `user_id` | the user whose UUID is in `manta.created_by`, if any |
| `datarecord_references.*` | `store.json`, with `kind` from the revision and `updated_at` from the file |
| `datarecord_references.user_id` | not recorded in the MVP: null |

Steps of the switch:

1. Add the tables and `sync_store`.
2. Run `sync_store` on every store of every project.
3. Switch the route handlers from DR to SQL, one route at a time. The FE does not change.
4. Switch the reference writes to the SQL compare-and-set, followed by the `store.json` write.

During step 3 a route can read from either source. Both give the same shape.

## 15. Requests to DR

No request is needed beyond the stack. Optional ones, none of them sent:

| # | Request | Why | Without it |
|---|---|---|---|
| L1 | A public read of the claim time of a committed revision, such as `Revision.created`. | `created_at` of the listing. | `ClaimFile.read` from `store/manifest.py`, or a plain GET of `claim.json`. Both tie the BE to the layout. |
| L2 | A common ancestor of two revisions. | The fork point. | Five lines in the BE over `ancestry()` ([fork point](#7-the-fork-point)). |
| L3 | A commit time in the manifest. | `committed_at` without a Manta key. | `manta.committed_at`, as decided. |
| L4 | A conditional replace in `Files` (`If-Match`). | Only if `store.json` became DR's concern. | The BE's own boto3 client. |
| L5 | A claim that accepts an id from the caller. | Way 2 of [results of runs](#8-results-of-runs). | Ways 1 and 3. Same as in the backend note. |

## 16. Open points

| Question | Test or proposal |
|---|---|
| Does SeaweedFS 4.53 honour `If-Match` on PutObject atomically? | Two PUTs with the same ETag, at once, many times: exactly one 200 and one 412 each time. Also with bucket versioning on, if used. |
| Does SeaweedFS answer a conditional GET with 304? | One test with an unchanged and a changed `store.json`. |
| Does a new manifest show in the next LIST at once on SeaweedFS? | Commit, then `revisions()` from another workspace. |
| Dev compose runs SeaweedFS 4.05, older than DR's 4.18 minimum for create-only writes. | Move dev to 4.53 with the `s3-security` branch before the MVP commit path. |
| How long does a cold listing take, per store and per project page? | Measure from the BE to SeaweedFS and to the target bucket, with 10 parallel GETs. |
| How long does Prefect keep flow runs and artifacts? | Read the server's retention settings. It bounds how long the run to revision link lasts without `manta.run`. |
| `store.json` form: PR #281 has no `base` and uses slugs. | Agree on the form of [the shared contract](#3-the-shared-contract) before the new export of phase 0. |
| Optional `updated_at` per reference in `store.json`. | Agree, and add it to the `store.json` list of the [revision index](backend.md#1-revision-index). |
| Does the BE image ship DuckDB's `httpfs`? | Install it at build time. |
| Who names the result of a run? | Proposal: nobody in the MVP. The run pages show results. A "save as named result" action comes later. |
