# Design note: backend

What the BE gains: the revision index in Postgres, the session tables and routes, the launcher, the lifetime policy and the Quack relay.

Part of the datarecord-session plan, draft 9. Start with the [overview](README.md). The codes F, S, R, D and I point to the [appendix](appendix.md).

This note covers the BE side of the plan. The BE keeps an index of stores, revisions and references in Postgres. The index mirrors the manifests in S3, which stay the truth. A reference gives a revision its name and moves by compare-and-set. Runs record their revisions in the same index. The BE starts one session per user and project through a launcher, and stops it again after a time without activity. Every session route and every Quack request runs `ensure`, so a stopped session comes back by itself. The FE reaches the session only through the BE: through the session routes, and through a Quack relay at `/quack`.

## 1. Revision index

### Tables

| Table | Columns | Unique |
|---|---|---|
| `datarecord_stores` | `project_id`, `name`, `label`, `description` | `project_id`, `name` |
| `datarecord_revisions` | `id` (the DR revision UUID), `store_id`, `parent_id`, `status` (`claimed`, `committed`), `kind` (`scenario`, `result`), `meta` (JSON), `created_by`, `user_id`, `run_id`, `step`, `created_at`, `committed_at` | |
| `datarecord_references` | `store_id`, `name`, `kind` (`scenario`, `result`), `revision_id`, `base`, `label`, `description`, `user_id`, `updated_at` | `store_id`, `name` |

`runs` gains the column `input_revision_id`: the revision the run started from.

A reference is a named pointer to one revision, like a branch in Git.

The columns of `datarecord_revisions`:

- `kind` and `created_by` mirror the manifest's `manta.kind` and `manta.created_by`. `created_by` names the writing program for a run.
- `meta` holds the manifest's other entries.
- `run_id` links a revision to the run that wrote it (`runs.id`). It is empty for imported revisions and for edits committed through the session. A run can write several revisions, one per block or per investment period. All of them carry its `run_id`.
- `step` is the name of the playbook step whose block wrote the revision. With `run_id` it tells two uses of the same block apart.

`user_id` is the Manta user who caused the row (`users.id`). It is in `datarecord_revisions` and in `datarecord_references`. In `datarecord_revisions` it is the user who imported the store, started the run, or committed the edit. `created_by` stays beside it as the mirror of the manifest entry. In `datarecord_references`, `user_id` is the user who last moved or renamed the reference.

`base` in `datarecord_references` is the name of another reference of the same store, or empty. It is the reference this reference was made from:

- For a scenario it is the scenario it was created from.
- For a result it is the scenario reference that was solved.
- The root scenario (`inputs` in the [example](#example)) has none.

### Rules

**S3 and Postgres.** The S3 manifest stays the truth. Postgres is a mirror. The BE writes it at claim and at commit confirmation.

**Names.** A name is not part of a revision. It lives in the reference table only. So a name can move, be renamed and be deleted without a new revision.

**The commit `meta`.** The commit `meta` holds facts about the revision itself, under keys with the prefix `manta.`:

- `manta.kind`
- `manta.created_by`
- `manta.committed_at`

Writers add `manta.committed_at` at commit. An import of a revision without it falls back to the claim time in `claim.json`. The change summary is not part of the commit `meta`.

**The base of a reference.** The BE sets `base` when it creates a reference. `base` never changes afterwards. A move of the reference keeps it.

**The fork point.** The default diff of a reference R with base B compares two revisions. `after` is the current revision of R. `before` is the *fork point*: the last revision that the histories of R and B share. The BE finds it through `parent_id` in `datarecord_revisions`. It walks the parents of both current revisions and takes the nearest common ancestor. The fork point stays the same when B moves later.

**Change summaries.** A change summary belongs to a pair of revisions, not to a commit. The BE does not store it. For each request the BE resolves the baseline to two revision ids and passes them to the session (`POST /summaries` in the [session service](session.md#3-session-service)). The scenario panel is part of the record view, where the session runs anyway.

**Moving a reference.** A reference moves by compare-and-set:

```sql
UPDATE ... SET revision_id = :new
WHERE store_id = :s AND name = :n AND revision_id = :expected
  AND kind = (SELECT kind FROM datarecord_revisions WHERE id = :new)
```

- No matched row means one of two things. Another commit moved the reference first, or the new revision has another kind. The BE then reports a conflict.
- A reference's `kind` is set when it is created and never changes. A reference can only point to a revision of its own kind. The BE enforces this in the move itself, so the column cannot go out of date.
- The move happens at commit confirmation, never at claim.
- Promotion of a result to a scenario is parked. It would create a new reference, not retype one.

**Results of a run.** The BE finds the results of a run through `parent_id`. A reference for a result is optional.

### `store.json`

A store that travels without the BE carries its references in a file `store.json` at its root. Examples are example data and an export. The file holds:

- the store's `label` and `description`;
- per reference: `name`, `revision`, `base`, `label`, `description`.

The BE reads the file at import. The BE writes the file again after each change of a reference or of the store's label, under the backend key. So the names survive a lost database, and an export needs no extra step. Postgres stays the truth; the file is a copy.

`store.json` replaces `revisions.json`. Today the BE reads `revisions.json` for two uses (`example_data_service.py:47, 93, 147-171`):

1. as the marker of a complete copy;
2. for the `inputs` revision of a run.

Both uses move to `store.json` (`references.inputs.revision`). This happens in the same change that moves `PUBLIC_DATA_VERSION` to the folder of the new export (I9). The folder `2026-11-13/` does not open with the pinned DR (F30).

### `sync_store`

`sync_store(store)` lists the store with DR and upserts the missing revisions. It runs in three cases:

- when a store is created;
- when a store is copied (example data);
- as repair.

Names and labels come from `store.json` only. Stores with the older side files `revisions.json` and `<store>.labels.json` do not open with the pinned DR (F30), so `sync_store` does not read them.

### Dependency on DR

The BE gains a dependency on `datarecord[remote]`. It uses it for `claim`, `revisions`, `cleanup` and manifest reads only.

### Public routes

`GET /v1/projects/{id}/stores` and `GET /v1/projects/{id}/stores/{store}/revisions` answer from Postgres. Stores, revisions and references need no session. The full list of routes is in [routes and Quack relay](#5-routes-and-quack-relay).

The listing carries no change summary. The scenario panel asks for it through the session route `GET /v1/projects/{id}/session/changes` ([routes and Quack relay](#5-routes-and-quack-relay)).

### Example

The example shows the shared store `BEL-pre-aggregated-incl-patches-incl-results` after its import into a project.

- Ids are cut to eight characters.
- Ids, parents and `created_at` are the store's real values. `created_at` comes from `claim.json`.
- Labels, descriptions and `created_by` are examples, because the store carries none yet.
- The manifest holds no commit time yet. So `committed_at` shows the time of the import here.

`datarecord_stores`

| id | project_id | name                                         | label                                | description                        |
|----|------------|----------------------------------------------|--------------------------------------|------------------------------------|
| 17 | 4f1c2a9e   | BEL-pre-aggregated-incl-patches-incl-results | Belgium, pre-aggregated, every solve | Inputs, one patch and six results. |

`datarecord_revisions`

| id | store_id | parent_id | status | kind | meta | created_by | user_id | run_id | step | created_at | committed_at |
| ---------- | ---------- | ----------- | ----------- | ---------- | ------ | ------------------ | ------- | ------ | ---- | --------------------- | --------------------- |
| 9ec88f52 | 17 |  | committed | scenario | {} | playbook-library | 3 |  |  | 2026-11-10 17:54:48 | 2026-11-13 18:02:11 |
| 07b0661e | 17 | 9ec88f52 | committed | scenario | {} | playbook-library | 3 |  |  | 2026-11-10 17:54:52 | 2026-11-13 18:02:11 |
| 830c3226 | 17 | 9ec88f52 | committed | result | {} | playbook-library | 3 |  |  | 2026-11-10 17:54:52 | 2026-11-13 18:02:11 |
| 8e3afa3a | 17 | 9ec88f52 | committed | result | {} | playbook-library | 3 |  |  | 2026-11-10 17:54:54 | 2026-11-13 18:02:11 |
| 639bdb70 | 17 | 9ec88f52 | committed | result | {} | playbook-library | 3 |  |  | 2026-11-10 17:54:56 | 2026-11-13 18:02:11 |
| e2a674f6 | 17 | 07b0661e | committed | result | {} | playbook-library | 3 |  |  | 2026-11-10 17:54:53 | 2026-11-13 18:02:11 |
| 7b68a9ca | 17 | 07b0661e | committed | result | {} | playbook-library | 3 |  |  | 2026-11-10 17:54:55 | 2026-11-13 18:02:11 |
| d147af69 | 17 | 07b0661e | committed | result | {} | playbook-library | 3 |  |  | 2026-11-10 17:54:58 | 2026-11-13 18:02:11 |

`run_id` and `step` are empty, because all revisions are imported.

`datarecord_references`

| store_id | name | kind | revision_id | base | label | description | user_id | updated_at |
| ---------- | --------------------- | ---- | ------------- | ------ | -------------------------- | --------------------------------------- | ------- | --------------------- |
| 17 | inputs | scenario | 9ec88f52 |  | Base case |  | 3 | 2026-11-13 18:02:11 |
| 17 | patch | scenario | 07b0661e | inputs | Patch | The scenario patch on the base case. | 3 | 2026-11-13 18:02:11 |
| 17 | perfect | result | 830c3226 | inputs | Perfect foresight |  | 3 | 2026-11-13 18:02:11 |
| 17 | myopic | result | 8e3afa3a | inputs | Myopic |  | 3 | 2026-11-13 18:02:11 |
| 17 | overnight2050 | result | 639bdb70 | inputs | Overnight 2050 |  | 3 | 2026-11-13 18:02:11 |
| 17 | patch/perfect | result | e2a674f6 | patch | Perfect foresight, patch |  | 3 | 2026-11-13 18:02:11 |
| 17 | patch/myopic | result | 7b68a9ca | patch | Myopic, with patch | Myopic solve of the patched inputs. | 3 | 2026-11-13 18:02:11 |
| 17 | patch/overnight2050 | result | d147af69 | patch | Overnight 2050, patch |  | 3 | 2026-11-13 18:02:11 |

`inputs` is the root scenario and has no base. `patch` was created from `inputs`. The three results without a prefix solve `inputs`, and the three `patch/...` results solve `patch`.

A user edits `patch` and commits. Then:

1. One row is added to `datarecord_revisions`, with parent `07b0661e` and kind `scenario`.
2. The `patch` row of `datarecord_references` moves to the new id. Its `base` stays `inputs`.
3. The three `patch/...` results keep their parent `07b0661e`. So they show as results of the earlier state.
4. The fork point of `patch` with `inputs` stays `9ec88f52`. The default diff of `patch` therefore covers both of its layers, not only the new one.

## 2. Runs and blocks

### The reported revision

A block reports its output revision. The BE upserts it with `kind=result` and the `run_id` of its run. The BE also sets `input_revision_id` on the run. This replaces the lookups in Prefect's flow parameters and artifacts (`run_service.py:121-166`). The code marks these lookups as a shortcut until revisions are tracked.

### Several revisions per block

A block can commit several revisions and reports only its last one. A myopic solve writes one per investment period. Each revision has a claim, because a DR commit is a claim and a commit in one. Today the block makes both itself.

The blocks set no `meta` today (F28). `manta.kind = result` and `manta.created_by` must come from the block or from the BE's claim, whichever way is used.

The BE learns of the earlier revisions in one of three ways. They are listed in the order of effort.

| Way | How | Finds | Changes |
|---|---|---|---|
| 1. Walk the parents | After the step, the BE walks the parents from the reported revision back to the step's input revision. | Every revision of a chain. It misses revisions that the block wrote beside the chain. | None. |
| 2. Layer id prefix | The BE lists the layers with a prefix per block run. | Every revision of the block run, also failed claims. | A claim accepts an id from the caller (DR). |
| 3. Claim through the BE | The block asks the BE for each claim, then commits into it. | Every revision of a run from its claim on, failed ones included. | `write_network`, new block inputs, a BE route. |

### Way 1: walk the parents

Every revision on the way gets the `run_id` and `step`. This needs no change anywhere, and it covers a chain. With way 1, `write_network` passes `manta.kind` and `manta.created_by` to `store.commit`.

### Way 2: a layer id prefix

This is step 6 of the storage grants (F25). The prefix also limits the block's write right.

DR draws every layer id itself (`uuid4()` in `Store.claim`, `store.py:633`). DR has no reason of its own for a prefix. The smallest request is "a claim accepts an id from the caller". The prefix is then Manta's rule for building the id. This is not agreed with DR and not requested yet.

### Way 3: the claim flow for blocks

This is the claim flow of the [commit flow](storage-commit.md#1-commit-flow) for blocks:

1. The block sends parent and `meta` to the BE.
2. The BE writes `claim.json` and inserts the row with `run_id` and `step`.
3. The BE returns the claim in its serialised form (R4).
4. The block commits into the claim with the store-wide token it has anyway.

Details:

- The change sits in one function (F28). `write_network` asks the BE instead of calling `store.commit`. It rebuilds the claim on its own store with `Store.claim_from(payload)` (F11) and calls `claim.commit(source)`. The four blocks with one commit need nothing else.
- Myopic: the revisions are a chain (F28), so way 1 finds them all. For way 3 the block asks once per period, with the id of the claim before as parent. Or it asks once for the whole chain. It knows the periods up front, and a claim on a pending parent works (F27).
- A block container needs new inputs: the BE's address, a credential for it, and the run and step it works for. `MantaBlock.run(record)` has no such context today.
- A block run without a BE (local runner, tests) keeps the combined `store.commit`.
- A retried block asks for new claims. The old claims stay pending until cleanup. A crash after period k leaves a committed chain of k revisions. The index shows it as such.
- A claim by the BE does not bind the block. The block can commit another parent or `meta` (F26). The BE compares the manifest with its claim when the block reports, as it does for the session.
- A token per layer can be added later on the same call.

### Status

Preferred, not decided: way 3 as the target, way 1 as the start. With way 3 the BE knows every revision of a run from its claim on, failed ones included. Sessions and blocks then follow one flow. The requests are small. Way 2 stays a noted alternative.

Two questions are open, with Kristijan:

- how a block authenticates to the BE (the signed run grant could serve);
- whether a block can reach the BE on the network.

## 3. Session lifetime

### States

```
stopped --ensure--> starting --healthy + replay--> active --no activity for T1--> idle --no activity for T2--> suspending --> stopped
                                                     ^                             |  |
                                                     +--------- activity ----------+  +-- capacity needed --> suspending
```

### Activity and presence

- **Activity** is any proxied API call or Quack request. It sets `last_used_at`.
- **Presence** is an explicit FE call, `POST /v1/projects/{id}/session/heartbeat`. The BE answers it alone.

The FE's `SELECT 1` link check (F7) is removed. The relay cannot tell it from a query.

### Two stages

| Stage | After, without activity | Effect |
|---|---|---|
| 1, idle | `T1` = 10 minutes | The BE may suspend the session when it needs capacity (session cap reached, memory pressure). It picks the least recently used idle session. |
| 2, forced | `T2` = 60 minutes | The BE suspends the session at once. |

`T1` and `T2` are start values.

A session with unsaved edits and a live presence is exempt from both stages. This applies to [working records](session.md#6-working-records). Without presence such a session follows the stages. Its edits survive through the working records.

### Suspend and restore

**Suspend:**

1. The BE calls `POST /suspend` on the session. For views this is a no-op.
2. The BE stops the instance.

**Restore:** the next request runs `ensure`. `ensure` starts an instance and replays the registration rows. The FE sees a slow request, not an error.

### Generation

Each start increases `generation`. The Quack token stays the same across starts.

After a restart, every query of an attached client fails with `Invalid connection id`. This lasts until the client runs `DETACH` and `ATTACH` (tested, S1). On that error the FE calls `POST .../session` and attaches again.

### Single start

`ensure` locks the session row. So parallel requests and several BE replicas start one instance.

### Orphans

Instances carry labels. A BE task stops labelled instances that have no active row. The session also exits by itself after a hard limit.

## 4. Launcher

`SessionLauncher` in the BE has three calls:

- `start(spec) -> endpoint`
- `stop(ref)`
- `list() -> refs`

The first implementation uses Docker. Kubernetes follows next year. A sub-process implementation stays possible, because the interface names no container concept beyond an opaque `ref`. It is not planned.

## 5. Routes and Quack relay

### Opening the session and `ensure`

`POST /v1/projects/{id}/session` opens the project's session. It is a call of its own, apart from login and from reading the project. Pages that only list or configure a project do not start an instance.

`ensure` means "start the session if none runs". It locks the session row, starts an instance when needed, and replays the registration rows (see [session lifetime](#3-session-lifetime)). The open call runs `ensure`. The registration routes, the commit route and every Quack request run it too. So a stopped session comes back by itself. Two routes do not run it: the heartbeat, which the BE answers alone, and `DELETE .../session`, which suspends.

### Routes

All routes are behind Keycloak auth and a project ownership check.

| Route | Effect |
|---|---|
| `GET /v1/projects/{id}/stores` | From Postgres. |
| `GET /v1/projects/{id}/stores/{store}/revisions` | From Postgres. |
| `POST /v1/projects/{id}/stores/{store}/revisions` | The [commit flow](storage-commit.md#1-commit-flow). The request names the reference to move and the revision expected there. Optional `register_as`: a name under which the BE registers the new revision in the session at once, so the FE needs no second call. |
| `POST /v1/projects/{id}/session` | Open the project's session: runs `ensure`. Returns `{status, generation, quack: {uri, token}}`. |
| `DELETE /v1/projects/{id}/session` | Suspend now. |
| `POST /v1/projects/{id}/session/heartbeat` | Presence. |
| `GET`, `PUT`, `DELETE /v1/projects/{id}/session/registrations/{name}` | Write the row, then apply it to the session. |
| `GET /v1/projects/{id}/session/changes` with `store`, `after`, optional `before` | The change summary of two revisions. `after` and `before` are reference names or revision ids. Without `before`, the baseline is the fork point with the base of `after`. The BE runs `ensure`, calls the session's `POST /summaries`, and passes the answer through. Nothing is stored. |
| `POST /quack` (server root) | Quack relay, see below. |

### Diff registrations

A registration of the kind `diff` takes `after` and `before`. Each names a reference or a revision id.

- Without `before`, the BE uses the fork point of the `after` reference with its base ([revision index](#1-revision-index)). It refuses the request if `after` is not a reference with a base.
- With two references, the diff compares their current revisions.
- The BE resolves both sides to revision ids before it calls the session. The session receives revision ids only ([session service](session.md#3-session-service)).

### Session tables

`datarecord_sessions`:

- `user_id`, `project_id`
- `status`, `generation`
- `quack_token`, `api_secret`
- `instance_ref`, `endpoint`
- `started_at`, `last_used_at`, `last_seen_at`

`datarecord_session_registrations`: `session_id`, `name`, `kind`, `store_id`, `revision_id`, `before_revision_id`, `packs`. A row of the kind `diff` holds its two resolved revisions: `revision_id` is `after`, `before_revision_id` is `before`. For the other kinds `before_revision_id` is empty.

### Quack relay

The relay design comes from spike S1.

A Quack client always posts to `/quack` at the root of a host and port. It cannot address a path. So the relay lives at `/quack`, outside `/v1`, and Caddy forwards it to the BE.

The FE creates a Quack secret that adds HTTP headers to every request:

```sql
CREATE OR REPLACE SECRET manta (TYPE quack, SCOPE 'quack:<host>:<port>', TOKEN '<quack token>',
  EXTRA_HTTP_HEADERS MAP {'Authorization': 'Bearer <keycloak token>', 'X-Manta-Project': '<project id>'})
```

For each request the BE:

1. authenticates the bearer token as on every route;
2. finds the session by user and project;
3. runs `ensure`;
4. streams the body to the instance unchanged.

The Quack token still travels inside the body. The session checks it. It is a second factor and plays no part in routing.

The headers are confirmed with the native client. The WASM path is read from source only (I3). Two checks in the browser remain:

- the headers reach the BE from WASM;
- a refreshed Keycloak token reaches later requests after `CREATE OR REPLACE SECRET`.

Fallback if headers fail in WASM: the BE reads the token from the first request body. It reads the `connection_id` from the fixed offset of later bodies. This is possible, but it ties the BE to the binary format.

## 6. Open points

| Question | Proposal |
|---|---|
| How does the BE learn of all revisions that a block writes (see [runs and blocks](#2-runs-and-blocks))? | Way 3 (claim through the BE) as the target, way 1 (walk the parents) as the start. Way 2 stays a noted alternative. |
| How does a block authenticate to the BE? | The signed run grant could serve. Open with Kristijan. |
| Can a block reach the BE on the network? | Open with Kristijan. |
| Does DR accept a layer id from the caller (way 2)? | Not agreed with DR and not requested yet. |
| How does a result become a scenario? | Parked. A new reference, not a retyped one. |
| What happens to `base` when the base reference is deleted? | `base` becomes empty, and the reference has no default diff. |
| The session computes a change summary again at each request. Is that fast enough for a panel with many scenarios? | Measure first. If it is slow, the session keeps a cache keyed by the two revision ids. No table in the BE. |
| Do the Quack secret's headers work in WASM, also after a token refresh (I3)? | Verify in the browser. Fallback: the BE reads token and `connection_id` from the body. |
