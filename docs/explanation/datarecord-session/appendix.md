<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Appendix

Sections: [terms](#1-terms), [decisions](#2-decisions), [open next](#3-open-next), [phases](#4-phases), [known issues](#5-known-issues), [facts](#6-facts), [requests to datarecord](#7-requests-to-datarecord), [spikes and measurements](#8-spikes-and-measurements), [where the quack-server functions move](#9-where-the-quack-server-functions-move), [issues the plan does not cover](#10-issues-the-plan-does-not-cover), [plan items without an issue](#11-plan-items-without-an-issue).

Reference material of the datarecord-session plan, draft 9 of 2026-11-17. Start with the [overview](index.md). Nothing here needs a first read; the overview and the design notes link into it.

## 1. Terms

Terms: **BE** = main FastAPI backend. **FE** = frontend (prototype in `baby-manta`, product in `manta/frontend`). **S** = datarecord-session. **DR** = datarecord library. **WR** = `WorkingRecord`, DR's mutable record on top of a revision.

Words with one meaning in this document:

- **Revision**: a committed state of a store, named by its UUID. Views, diffs and summaries are always about revisions.
- **Reference**: a named pointer to one revision, like a branch in Git. It carries the name, label and description that the user sees, and moves with every commit. It lives in `store.json`, which only the BE writes ([references in `store.json`](backend-mvp.md#6-references-in-storejson)).
- **Base**: the reference that a reference was made from, fixed at creation ([the `store.json` form](backend-mvp.md#the-storejson-form)).
- **Fork point**: the last revision that the histories of a reference and its base share. It is the default *baseline* of a diff ([changes between revisions](frontend.md#3-changes-between-revisions)).
- **Registration**: a revision (or a WR, or a diff of two revisions, by default a reference's current revision and the fork point with its base) that the session exposes under a name, as one DuckDB schema of that name in the session's one catalog ([names in DuckDB](session.md#4-names-in-duckdb)). The name is only how SQL addresses it.
- **Schema**: DR's schema, the declaration of dimensions and attributes in a manifest. Where a namespace inside DuckDB is meant, the text says "DuckDB schema".
- **Map row**: DR's term (vocabulary of DR PR 144, branch `coordinate-vocabulary`). One row of the fold's owner map. Its index is the attribute's name plus the attribute's dimensions in `partial`. For PyPSA those are one entity, or one entity and bus (a connection), or one bus; the snapshot is not among them. The owner map assigns each map row to a layer. A map row can leave a dimension NULL, which covers every label of it.
- Other DR words follow that PR: dimension (not dim), field (a named part of a multi-dimension's label, such as `bus` of `connection`), coordinate (one label on each dimension, never NULL).

## 2. Decisions

Taken:

| Topic | Result |
|---|---|
| MVP backend step | The BE keeps no Postgres table for stores, revisions or references. It reads them from DR and `store.json`, and moves a reference by a conditional write of `store.json` with `If-Match`. This follows #283. A revision index in Postgres is the later step. It is filled from what the MVP step writes, with the same routes, response shapes, `store.json` and `manta.` keys ([MVP backend note](backend-mvp.md)). |
| Session tables in the MVP | `datarecord_sessions` and `datarecord_session_registrations` stay in the MVP. They hold the running sessions and the revisions the FE asked to access, which are replayed after a suspend. They record no scenario or revision context, so #283 does not cover them. A registration names its store by name ([session management](backend-mvp.md#10-session-management)). |
| Launcher | Interface in the BE, Docker first, Kubernetes next year. Sub-process execution stays possible, not planned. |
| Revision list | Central in the BE, read from DR with `Store.revisions()` and `Store.claims()`. The BE caches the manifests in memory ([revisions](backend-mvp.md#5-revisions)). Later in a Postgres index. |
| Revision names and labels | References in `store.json` (name, label, description, pointer, base), written only by the BE and moved by a conditional write with `If-Match`. Not in the commit `meta`. Later held in Postgres and moved by compare-and-set ([references in `store.json`](backend-mvp.md#6-references-in-storejson)). |
| Reference base | Each reference records its base reference as `base` in `store.json`, set at creation and fixed. For a scenario it is the scenario it was created from; for a result, the scenario reference that was solved. The root scenario has none ([the `store.json` form](backend-mvp.md#the-storejson-form)). |
| Diff baseline | The default diff of a reference compares its current revision with the fork point: the last revision that its history shares with that of its base. The BE finds it from `Revision.ancestry()` of both sides ([fork point](backend-mvp.md#7-the-fork-point)). An explicit compare of two references uses the current revisions of both. A scenario does not see later edits of its base; the plan has no rebase ([changes between revisions](frontend.md#3-changes-between-revisions)). |
| Change summary | Belongs to a reference, not to a commit. By default it compares the reference's current revision with the fork point with its base reference. An explicit compare of two references uses the current revisions of both. It is not in the commit `meta` and not stored in the BE. The BE resolves the two revisions and passes each request to the session ([changes between revisions](frontend.md#3-changes-between-revisions)). |
| Revision kind, author | Commit `meta` (`manta.kind`, `manta.created_by`; every Manta key has the prefix `manta.`), read by the BE from the manifest. Later held in Postgres as `kind` and `created_by`. The base inputs have `kind = scenario`. `created_by` of a run is the name of the block; of a session commit, the user. |
| Write access | The session has none of its own. The BE claims and hands out a credential for one layer. |
| Idle policy | Two stages. Keep-alive queries do not count as activity. |
| Commit credential | Two credentials at once: read secret and a layer-scoped secret (R2). Commit token lifetime 900 s. No revocation. |
| Commit exchange | The BE starts it, always: one-shot commits and commits of a live WR. The session never calls the BE. A suspension commits nothing: the edit log keeps the unsaved edits ([working records](session.md#6-working-records)). |
| Session scope | One session per user and project. A shared session per project stays a later spike (S5), not an open decision. |
| DuckDB names | One catalog, named `manta`: the workspace that DR attaches. A registration is one DuckDB schema in it; the `static` views live in it and packs below it; a diff has its own DuckDB schema with flat views ([names in DuckDB](session.md#4-names-in-duckdb)). |
| Working record persistence | The edit log, kept in full until the commit. No draft revisions. |
| SQL guard | The SQL macro stays for now. `quack-oauth` is not adopted ([results of S7](#82-results-of-s7-quack-oauth)). |
| Idle times | `T1` = 10 minutes, `T2` = 60 minutes, as start values. Capacity pressure is a cap on the number of running sessions at first. |
| Stored fold | Dropped (D17): no rule to materialise before an upload. Required instead: every store is written with the pinned DR, so each layer has `owner_map_rows.parquet` (F18). Materialising stays optional, for anyone. Commits through the session are not materialised. |
| `static` views and DR shape changes | The views follow the shape of the pinned DR. Today that is datarecord 0.1.0a2, with PR 142 and without PR 146 (D18, F31). |
| DR version | A commit hash, the same for session, BE and blocks, moved together. Now: the stack tip, `468f69b0` (`perf/frozen-table-load`). Later: specific commits on DR `main`. Later: a released version (D19). |
| User deletion | `manta.created_by` of a session commit is an opaque user id, never the username. After the user's deletion it points to nothing; the manifest cannot change. In the MVP a project has one owner and goes with it ([what `meta` cannot hold](backend-mvp.md#what-meta-cannot-hold)). Later the `datarecord_*` tables of the [revision index](backend.md#1-revision-index) cascade from the project, as `runs` does (`projects.owner_id` cascades from the user), and `user_id` is `ON DELETE SET NULL`. |
| Commit time | Every writer adds `manta.committed_at` to the `meta` at commit (a flat string, no DR change). An import falls back to the claim time of `claim.json`. |
| Nested `meta` (R13) | Not used by Manta for now. Every `manta.` key in `meta` is a flat value, and the change summary is not stored. No staged rollout: all readers and the writer move to the DR release with R13 at once. |
| Settle | SQL only, composed by the FE in TypeScript. The FE decides per query where the statement runs ([settling in the FE](frontend.md#4-settling-in-the-fe)). |

Open:

| # | Decision | Proposal |
|---|---|---|
| D4 | Closed. Group A: view packs by convention set. Group B: `static_<dtype>` views and the owner map ([constant values and the owner map](frontend.md#2-constant-values-and-the-owner-map)). Changes: a change summary of a reference against the fork point with its base reference, computed on request, and a diff registration of the same two revisions ([changes between revisions](frontend.md#3-changes-between-revisions)). |  |
| D11 | Closed: SeaweedFS only, for now (F25). |  |

Settling: the FE applies the broadcast rule, with its own port of DR's `settle`. DR offers no settled views. The session's views (`static`, diff) are raw. The FE port is checked against DR with shared test cases (R14).

Why the session does not settle: raw rows are smaller than settled rows (one row with a NULL label stands for every label), and settling is mechanical. Settling is always SQL. TypeScript only composes the statement; no JavaScript code settles rows. Detail in [settling in the FE](frontend.md#4-settling-in-the-fe).

Also taken since draft 2: changeset as an operation list ([changeset format](storage-commit.md#3-changeset-format)); STS tokens as write credential ([the two tokens](storage-commit.md#2-the-two-tokens)); view packs for group A; `revisions` in the BE.

## 3. Open next

State on 2026-11-17: no request to DR blocks a phase any more. What blocks is that the stack is not merged (I11) and that every store is in an old layout (I9).

In this order:

1. DR: review and merge PR 144 and the stack. Pin the stack tip in Manta (D19). PR 142 is released in datarecord 0.1.0a2. PR 146 is rebased on the stack in DR; the `static` views follow when the pin moves (D18).
2. Export the test stores again with the stack's DR into a new bucket folder, with `store.json` and `meta` as in `2026-11-13/`. Add the missing `manta.created_by` on scenario revisions on the way ([results of S2 and S3](#81-results-of-s2-and-s3-on-dr-main)).
3. Run S2 and S3 again on these stores: `register`, `materialise()`, a commit, the `static` read, through Quack and on SeaweedFS. This checks the numbers behind D17.
4. Run the left-over of S6: an STS token as `S3Credentials`, for the workspace and for a commit, on SeaweedFS 4.53.
5. Browser checks: the headers of the Quack secret in WASM (I3), the settle statement in WASM ([settling in the FE](frontend.md#4-settling-in-the-fe)).
6. With Kristijan: how the BE mints tokens and which role sessions get ([the two tokens](storage-commit.md#2-the-two-tokens)); how a block authenticates to the BE ([runs and blocks](backend.md#2-runs-and-blocks)).
7. Test a conditional `If-Match` write of `store.json` on SeaweedFS 4.53: two PUTs with the same ETag at once, many times, must give one 200 and one 412 each time. Move the dev setup from SeaweedFS 4.05 to 4.53 first, with the `s3-security` branch (F25). The MVP step depends on this ([open points of the MVP backend note](backend-mvp.md#16-open-points)).
8. Start phase 2, the MVP backend step: store, revision and reference routes over DR and `store.json`. Only its import step waits for step 2.

Open decisions: D6 (a rule operation in the changeset, [changeset format](storage-commit.md#3-changeset-format)) and the owner of a convention set ([replacing the manta objects](session.md#5-replacing-the-manta-objects)).

## 4. Phases

0. **DR stack.** Review and merge of DR PR 144 and PRs 147 to 159, and a new export of all stores (F30). Manta pins the stack tip meanwhile (D19). Added with draft 9.
1. **Spikes** S1, S2, S4, S6. Then S3. S2 and S3 run again on the stack ([what the DR stack changes](#83-what-the-dr-stack-changes)).
2. **BE store routes over DR**, the MVP backend step ([MVP backend note](backend-mvp.md)). First, alone: the example data import reads `store.json` instead of `revisions.json` and moves to folder `2026-11-13`. Then the store, revision and reference routes answer from DR and `store.json`, and the BE moves references by a conditional write of `store.json`. No table. The FE home page can drop `record-server.ts` here.
3. **Session service.** Package, Quack, guard, registration with `Record.register`, view packs. A one-shot compose service builds the image; no session runs in compose until phase 4 starts them.
4. **BE sessions.** Session tables, launcher (Docker), `ensure_datarecord_session`, registration routes, Quack auth check in Caddy, lifetime policy.
5. **FE.** Move `manta/frontend`'s record client to the BE routes: open the session, register, attach, re-attach after `Invalid connection id`, presence call.
6. **Commit path.** Claim, write credential, changeset format, verification, and the move of the reference by a conditional write of `store.json`. The DR side exists (PRs 151 to 153).
7. **Remove** `docker/quack-server`. Move the WASM build scripts.
8. **Later.** Working records ([working records](session.md#6-working-records)), Kubernetes launcher, blocks on the claim flow, shared sessions (S5). The revision index in Postgres ([revision index](backend.md#1-revision-index)), filled by `sync_store` from what the MVP step wrote ([path to the index](backend-mvp.md#14-path-to-the-index)).

## 5. Known issues

| # | Issue |
|---|---|
| I1 | Until the storage grants (F25) reach the session, it holds the global S3 credential. Code alone confines it to the project prefix. |
| I2 | The read-only SQL guard is a proof of concept by its own docstring, and `enable_external_access` must stay on for DR. It protects the credentials inside the session. |
| I3 | Quack routing through the BE relies on HTTP headers from a Quack secret. Confirmed natively, not yet in the browser build. |
| I7 | Closed by DR PR 150: a denied read raises `PermissionError`, and `Store.cleanup` deletes nothing after one. Every credential needs ListBucket on its prefix. |
| I8 | Upstream Quack issue #325: an authenticated client can replace authorization callbacks that are defined in SQL. Our guard is such a macro. |
| I9 | No existing store opens with the stack (F30): not the example stores under `playground/`, and not the bucket folder `2026-11-13/` with its mirror `test-data-2026-11-13/`. All are exported again with the stack's DR. |
| I10 | Session containers share the compose network with SeaweedFS, whose internal ports take no credentials (F25). Reaching them from a user's SQL needs more than a bypass of the statement check: DuckDB's HTTP file systems are disabled and the configuration is locked (`quack.py:81-99`). Reads through the S3 file system are limited by the session's token. |
| I4 | `Record.register` uses private DuckDB API, which pins `duckdb==2.0.0`. With DR PR 158 every attribute read also goes through the private `duckdb._relation._render`. The WASM side needs an unsigned, locally built Quack extension. Server and client versions move together. |
| I5 | `POST /v1/auth/register` is unauthenticated and `aud` is not checked. With sessions, any registered identity can start containers. |
| I6 | Block containers of runs write with the global key and bypass the claim flow. The BE sees their revisions only after the fact, at the next listing. |
| I11 | The DR stack is 14 open PRs without a review (F29). Until it merges, Manta builds on a branch head that can still change. `pytest` fails on Windows from PR 151 upward. |

## 6. Facts

The FE sources of F4 to F7, F22 and F23 are `manta/frontend` on `main`, read on 2026-11-25. Its record client and level pages were ported from the `baby-manta` prototype ([#264](https://github.com/manta-plan/manta/pull/264), [#353](https://github.com/manta-plan/manta/pull/353)), and the Analyse tab follows ([#378](https://github.com/manta-plan/manta/pull/378)).

| # | Fact | Source |
|---|---|---|
| F1 | A store is the S3 prefix `s3://<bucket>/<project_uuid>/<store_name>`. A project holds many stores, a user owns many projects. | `backend/.../run_service.py`, `example_data_service.py` |
| F2 | The BE has no store or revision entity and does not depend on DR. | `backend/src/manta/entities/` |
| F3 | One global bucket, one global S3 credential pair. Block containers of runs receive the same pair. | `config/s3_config.py`, `runner/config.py` |
| F4 | The WASM client is `frontend/src/features/project/lib/record-server/client.ts` in `manta/frontend`, ported from `baby-manta` (#264, #353). It attaches the record server over Quack and runs every read there. | `client.ts`: `connect`, `attach`, `serverQuery` |
| F5 | Quack is plain HTTP, `POST /quack` at the server root. The client addresses `quack:<host>:<port>` with a `TOKEN` option. | `client.ts`: `attach` |
| F6 | The FE runs every query as `quack_query_by_name('r', $$...$$)`. Such a query sees catalogs and DuckDB schemas created after ATTACH, so a new registration needs no re-attach (S1, [results of S2 and S3](#81-results-of-s2-and-s3-on-dr-main)). | `client.ts`: `serverQuery` |
| F7 | The WASM client cannot run Quack's heartbeat thread. The FE sets `HEARTBEAT_TIMEOUT 3600` and sends `SELECT 1` every 15 s while the tab is visible. At the BE's Quack auth check this keep-alive looks like any query. | `client.ts`: `HEARTBEAT_TIMEOUT_S`, `CHECK_INTERVAL_MS`, `checkLink`, `startChecks` |
| F8 | DR exposes a revision as views: `Record.register(name)`, `Workspace.unregister(name)`, `Workspace(con=..., name=...)`. A registered WR's views follow its edits. `register` also adds the view `<name>.owner_map` (F21). | DR `resolve/record.py:611`, DEP 34, PR 149 |
| F9 | DR has no branch, tag or head. A revision is a UUID with a parent and a `meta` of JSON values. Nested values are allowed, null is refused at any depth (PR 154). Claimed `meta` is fixed; a commit may only add entries. `Store.revisions(meta=...)` matches by containment. | DR `store/manifest.py:33, 221`, PR 154 |
| F10 | `Store.claim` writes only `layers/<id>/claim.json`. A commit writes only under `layers/<id>/`. The single conditional PUT is `manifest.json`. A commit also reads all ancestor manifests and data. | DR `store/store.py:608-639, 1095-1162` |
| F11 | A claim crosses processes as JSON with its five fields (`id`, `store`, `parent`, `meta`, `created`): `claim.model_dump_json()` on one side, `Store.claim_from(payload)` on the other, without a read of `claim.json`. The store URI in the payload must equal the URI of the receiving store, else `ValueError`. A documented contract with PR 153. | DR PR 153, `store/store.py:744`, `docs/reference/store.md:304-327` |
| F26 | `Claim.commit` takes parent and `meta` from the claim object in memory. It checks that `claim.json` exists, never what it says. PR 153 documents this: a rebuilt claim commits what it says. A committer can therefore write a manifest with another parent or another `meta` than `claim.json`. Manta does not depend on a check; the BE compares the manifest with its claim ([commit flow](storage-commit.md#1-commit-flow)). DEP 25 line 58 still promises the check. | DR PR 153, `docs/reference/store.md:291` |
| F27 | A claim on a parent that is itself a pending claim is supported and documented (PR 153), so a chain can be claimed before its first commit. The commit of a child raises `KeyError` until its parent is committed. | DR PR 153, `docs/reference/store.md:304-327` |
| F28 | The blocks commit in one place, `write_network`, with `store.commit(source, parent=rev)`: claim and commit in one, no `meta`. Five blocks call it. The myopic block calls it once per investment period, each on the revision of the period before: a chain from the input revision, of which it reports the last. A block container receives only the Prefect URL and the global S3 key; it has no BE address, no token and no run identity. | `playbook-library/.../pypsa_helpers.py:74-84`, `myopic_capacity_expansion.py:64-74`, `runner/config.py:145-163` |
| F12 | A `Workspace` takes S3 credentials as an object: `Workspace(credentials=S3Credentials(key_id, secret, session_token, endpoint, region, url_style))`. `Workspace.set_credentials` replaces them on a live workspace (PR 151). A commit takes a second key for its layer: `Claim.commit(source, credentials=...)`. DR then creates a DuckDB secret with the scope `<store>/layers/<id>/` and drops it after the commit (PR 152). `Store.claim`, the combined `Store.commit` and `materialise()` take no key. Tested on SeaweedFS 4.52 with static keys, not with a session token. | DR PRs 151, 152, `store/files.py:115`, `store/store.py:252, 376, 1199` |
| F13 | "Restatement": along a non-partial dimension a layer must restate the whole extent of every map row it touches. Only a WR does this (at `set`, `add`, `remove`). A hand-made LayerData is not completed at commit: missing extent becomes a deletion. | DR `mutable.py:1591-1663`, open-questions |
| F14 | WR state lives in DuckDB tables (`datarecord._staged.<hex>`) plus a Python-only set of touched staging tables (`(kind, attribute)`, not map rows). It cannot be exported or resumed today (open issue in DEP 9). A WR belongs to the thread that built it. | DR `mutable.py:440-463, 625-635` |
| F15 | `revisions.json` (revision names) and `<store>.labels.json` are Manta conventions. DR does not know them. | grep in DR |
| F16 | The FE has an unconnected edit model: `ScenarioMutation` with a *rule* (filter, property, `set`/`add`/`multiply`/`min`/`max`, value) or a *direct* change (property, previous, value). Nothing builds Parquet or Arrow for writes. | `baby-manta/src/data/scenarios.ts` |
| F17 | The BE has no proxy code and no container management. The production target is undecided; Kubernetes is planned for next year. | `runner/deploy.py`, `docker/README.md` |
| F19 | DR PR 144 (`coordinate-vocabulary`, open) renames the storage layout with no migration: `dims/` becomes `dimensions/`, `dim_owners.parquet` becomes `dimension_owners.parquet`, registered views become `<name>.dimensions.<d>`, and a property's `one_of` becomes `refers`. Stores written before it do not open after it. The stack of F29 sits on it, so this plan uses its names everywhere, in text and in code. | DR PR 144 |
| F20 | A registered attribute view has the columns `<dimensions...>, attribute, breakpoint, value`. Rows are raw. A multi-dimension is one struct column (`connection STRUCT(entity, bus)`), NULL as a whole. `dimensions.<d>` is one column named `<d>`. A row that leaves a dimension in `partial` NULL comes back once per map row it serves: with NULL for its own map row, and with the label filled in for each overlap row (documented with PR 148). | DR `resolve/record.py`, `docs/reference/resolution.md:121` |
| F21 | The owner map has the dimensions in `partial`, then `attribute`, `layer_uuid`, `varies STRUCT(<dimension> BOOLEAN...)`, `broadcast STRUCT(...)`, `breakpoints`. `register` exposes it as the view `<name>.owner_map`, for a revision and for a WR (PR 149). A WR's view follows its edits. Its staged rows carry the WR's own layer id as `layer_uuid`. That id is stable until the WR closes and is not the id of the committed layer. `flags()` is a `bool_or` over the map. | DR PR 149, `docs/reference/format.md:179-199` |
| F22 | The FE does not settle, and the quack-server views are raw. FE queries join attribute rows on an entity, which a NULL `entity` never matches. Series rows and constants crossed with the span are combined by `UNION ALL`, so an entity with both counts twice. `attribute_summary` collapses other dimensions with `any_value`. | `map-shading.ts`: `regionSql` (`load-demand`); `chart-sql.ts`: `attributeValuesSql`; `manta_views.py`: `_summary_select` |
| F23 | `manta/frontend` runs `vitest` in CI and has only DuckDB-Wasm. Its tests check SQL text. Shared settle cases also need a DuckDB for Node (`@duckdb/node-api`). | `frontend/package.json`, `.github/workflows/frontend-test.yml` |
| F24 | `Claim.commit` does not call `materialise()`. `merge_meta` compares values as canonical JSON, so `1`, `1.0` and `true` differ (PR 154). A denied S3 read (403) raises `PermissionError` in every file operation, and `Store.cleanup` deletes nothing after one (PR 150). A credential without `s3:ListBucket` on its prefix cannot run `revisions`, `claims`, `cleanup` or a commit. | DR PRs 150, 154, `store/files.py:158` |
| F25 | The S3 access control plan for runs (Kristijan, 2026-11-12, branch `s3-security`, not pushed) uses the same mechanism as [the two tokens](storage-commit.md#2-the-two-tokens): `AssumeRole` with an inline policy. Tested there on SeaweedFS 4.53: tokens limited to a folder, 7-day lifetime (`maxSessionLength`), no delete, DR reads and commits unchanged with tokens from `AWS_*` variables, and the variant "trusted side claims, block commits into one layer". A token cannot be revoked alone; rotating the signing key revokes all. Identities: admin, backend, and a minter that can only assume the role `manta-block-run` (read, write, list; no delete). Cleanup and deletion stay BE jobs under the backend key. | Kristijan's document "Manta S3 access control plan", not in the repository |
| F18 | A remote store open took about 17 s from Cloud Run. A layer written with the stack carries `owner_map_rows.parquet`, the pre-aggregated rows of its owner map (PR 147). With that file the cold fold of `europe-full-resolution` (1.24 billion rows) takes 0.7 s; for a layer written before PR 147 about 6 s; on DR main about 310 s (numbers of the PR). `Revision.materialise()` writes the fold under `layers/<id>/resolved/` and can run later, by any party. | quack-server README, DR PR 147, `store/materialise.py` |
| F29 | The DR stack: PRs 147 to 159, each on the one before, on top of PR 144. PRs 148 to 155 answer R8, R7, R3, R1, R2, R4, R13 and R14 ([requests to datarecord](#7-requests-to-datarecord)). PRs 147 and 156 to 159 are performance work on the fold and on `register` ([what the DR stack changes](#83-what-the-dr-stack-changes)). All are open and mergeable; none is reviewed. `pytest` fails on Windows from PR 151 upward, cause not read. Nothing is released. The head is the branch `perf/frozen-table-load`. | DR PRs 144, 147 to 159 |
| F30 | Breaking with the stack: a store written before PR 144 does not open. A fold materialised before PR 147 cannot be read and must be materialised again. A workspace database file from before must be deleted. `meta` values that differ only in type (`1`, `1.0`) no longer merge. | DR PRs 144, 147, 154 |
| F31 | Two DR PRs change shapes that this plan uses. PR 142 keys a connection by its port: `connection STRUCT(entity, port)`, and `bus` becomes a property of the connection. It is merged and released in datarecord 0.1.0a2, which the stack pins since [#377](https://github.com/manta-plan/manta/pull/377). PR 146 makes global constraints a dimension `global_constraint`: `investment_period`, `sense`, `constant` and `mu` become attributes over it, not over `entity`. It is still open, based on main with the old names, and not rebased on PR 144. | DR PRs 142, 146 |

## 7. Requests to datarecord

Reviewed on 2026-11-14: a request stays only where the session cannot do the work itself. Eight stayed. Status on 2026-11-17: the stack of F29 answers all eight. The PRs are open and not reviewed. Each request went to DR as a written handover; the DR PRs of F29 are the record. None of the eight PRs adds a DEP, though the handovers asked for one where the design changes; that is a matter for DR's review.

| # | Request | PR | Delivered | Left open |
|---|---|---|---|---|
| R1 | A `Workspace` accepts injected credentials and lets them be replaced. | 151 | `S3Credentials`, `Workspace(credentials=...)`, `Workspace.set_credentials`. | Not tested with an STS session token. The session must pass `url_style="path"` ([session service](session.md#3-session-service)). |
| R2 | A commit of one claim accepts a second credential for its layer. | 152 | `Claim.commit(source, credentials=...)`. DR creates and drops the scoped secret. | Not on `Store.claim`, `Store.commit` or `materialise()`. A block with a layer key must use `Claim.commit`. Not tested with a session token. |
| R3 | A denied read (403) raises. | 150 | `PermissionError` in every file operation. `cleanup` deletes nothing after one. | Every credential needs ListBucket on its prefix; the policies of [the two tokens](storage-commit.md#2-the-two-tokens) have it. Local stores are not covered. |
| R4 | A serialised claim with all five fields, rebuilt without a read. | 153 | `claim.model_dump_json()`, `Store.claim_from(payload)`. A claim on a pending parent is documented. | DEP 25 line 58 is unchanged (F26). |
| R7 | The owner map as a registered view, for revisions and for a WR. | 149 | `<name>.owner_map` with the columns of F21. A WR's `layer_uuid` is stable until it closes. | No view of the dimension owners ([changes between revisions](frontend.md#3-changes-between-revisions), later). On a WR a filter reaches only part of the scans. No row count, as agreed. |
| R8 | Filter pushdown through the registered attribute views. | 148 | `entity = ...` prunes: 5.2 s to 0.23 s on 1,186 million rows. | `snapshot IS NULL` on the whole struct does not prune and will not. Use `snapshot.period IS NULL` ([constant values and the owner map](frontend.md#2-constant-values-and-the-owner-map)). |
| R13 | Nested values in `meta`. | 154 | Nested JSON values. `revisions(meta=...)` matches by containment. | Null is refused. Values compare as canonical JSON (F30). Not used by Manta for now: the change summary is not stored in `meta` ([changes between revisions](frontend.md#3-changes-between-revisions)). |
| R14 | Test cases for `settle` as one JSON file. | 155 | `datarecord/settle_cases.json`, 20 cases. | No `twins` case; the FE does not port `twins`. How the file reaches the FE ([settling in the FE](frontend.md#4-settling-in-the-fe)). |

Not requested, in the same stack: PRs 147 and 156 to 159 make the fold and `register` faster ([what the DR stack changes](#83-what-the-dr-stack-changes)).

Built in the session instead, not requested:

| # | Was | Now |
|---|---|---|
| R5 | An agreed serialisation of edit operations. | The [changeset format](storage-commit.md#3-changeset-format) is the session's own API. The session maps it to the WR calls. |
| R6 | Resume or replay of a WR's staged edits; squash of drafts. | The edit log of [working records](session.md#6-working-records) is kept in full until the commit and replayed by the session on a fresh WR. No drafts exist, so no squash. |
| R9 | The map rows assigned to a layer; a diff of two revisions. | The diff views of [changes between revisions](frontend.md#3-changes-between-revisions) are the session's SQL over two owner maps. |

Dropped:

| # | Was | Why |
|---|---|---|
| R10 | A public replacement for the private DuckDB API behind `register`. | DR's own matter. The session pins the DR and DuckDB versions (I4). |
| R11 | A create-only write for GCS. | GCS is not a target for now (D11). |
| R12 | Constants clustered by the writer. | Already the case ([constant values and the owner map](frontend.md#2-constant-values-and-the-owner-map)). |
| R15 | A contract for DuckDB schemas and views below a registration. | Unnecessary. It works ([names in DuckDB](session.md#4-names-in-duckdb)), and the session pins the DR version; a clash of names would show at an upgrade. |

## 8. Spikes and measurements

| # | Question | Why it matters |
|---|---|---|
| S1 | **Done.** No path. Headers through a Quack secret work (native client). Token in the first body only, then a `connection_id`. Restart needs re-attach. `quack_query_by_name` sees new DuckDB schemas at once. Result in [routes and Quack auth check](backend.md#5-routes-and-quack-auth-check). Left over: the browser check of the headers. | |
| S2 | **Done** on DR main, results in [results of S2 and S3](#81-results-of-s2-and-s3-on-dr-main). To run again on the stack ([what the DR stack changes](#83-what-the-dr-stack-changes)). | |
| S3 | **Done** for local disk, results in [results of S2 and S3](#81-results-of-s2-and-s3-on-dr-main). Left over: the same on the stack and on SeaweedFS, and the duration of a large commit against the 900 s token. | |
| S4 | **Done.** After a server restart every query of an attached client fails with `Invalid connection id`, on both query paths, also when the token changed. `DETACH` and `ATTACH` recover. | |
| S7 | **Done**, results in [results of S7](#82-results-of-s7-quack-oauth). `quack-oauth` is not adopted now. | |
| S5 | Shared session per project. Known from S1: the server accepts several tokens through an authentication callback `(connection_id, client token, server token)`, and an authorization callback `(connection_id, query)` that may rewrite the query. Nothing ties a connection to a user yet (open upstream), a Python callback would have to keep that map. `quack-oauth` exists as a third-party project. Open: separation of the users' registrations in one DuckDB. | D1. Run after the rest of the design is fixed. |
| S6 | **Done** for DuckDB (tested). SeaweedFS 4.53 tested by Kristijan for the runs (F25). Left over: an STS session token passed as `S3Credentials` against SeaweedFS, for the workspace and for a commit (F12). | |
| S8 | **Done** 2026-11-23, Caddy 2.11.9, compared with 2.10.2. `forward_auth` with an upstream per user works: a 5 MiB binary body arrives byte-identical, and a 50 MiB response streams back. The auth subrequest has no body. A 401 reaches the client, and no upstream receives the request. A placeholder upstream needs no extra module. Spoofing: 2.11 removes a client's `X-Session-Upstream` when the auth answer has none. 2.10.2 keeps it and routes to the spoofed upstream. An auth value always replaces the client's. Caddy's proxy transport honours `HTTP_PROXY` variables. Not tested: a real DuckDB-WASM Quack client through this path (the sandbox blocked the extension install). Result in [routes and Quack auth check](backend.md#5-routes-and-quack-auth-check). | Keeps query and result bytes out of the BE. |

### 8.1 Results of S2 and S3 on DR main

Measured on 2026-11-14 on current stores of bucket folder `2026-11-13/`, on scratch copies. Local disk with a warm page cache, DuckDB 2.0.0, DR main 8889d623, the real guard of quack-server with `lock_configuration`. Each process starts cold. Median of three runs, or one run where marked. "srv" is the time on the server connection, "cli" through `quack_query_by_name` from an attached client. The scripts and outputs are not part of the repository. These numbers replace those of the first run on `composed_2050.store`, an older and badly packed store; that run gave 219 s, 209 s and 213 s for the first three slow steps, and the same picture.

These numbers are from DR main. The stack of F29 changes the slow rows by about two orders of magnitude. Read [what the DR stack changes](#83-what-the-dr-stack-changes) with the table and the consequences.

Registration:

- `Record.register` works on the connection that Quack serves, with the guard active, called from the main thread while Quack serves. A registration while a client is attached took 0.8 s, `unregister` 0.01 s.
- Names: the workspace name is the catalog (`dr` in this spike, `manta` in [names in DuckDB](session.md#4-names-in-duckdb)), the registered name a DuckDB schema in it, with nested DuckDB schemas below. The FE writes `quack_query_by_name('r', $$SELECT * FROM dr.r1.attributes.p_nom$$)`.
- A registration made after the client attached is visible through `quack_query_by_name`. Through the client's attached catalog `r` (`r.dr.r2...`) it is not. So the FE keeps using `quack_query_by_name` only.
- `duckdb_views()` shows only the leaf DuckDB schema (`attributes`), so it alone cannot tell two registrations apart; only a join with the `parent_schema` column of `duckdb_schemas()` can ([names in DuckDB](session.md#4-names-in-duckdb)). The view list of a registration must come from the session API ([session service](session.md#3-session-service)).
- The guard rejected every write tried from the client: CREATE TABLE, COPY TO, ATTACH, SET, DROP SCHEMA, `read_parquet`. It also rejects EXPLAIN.

Stores:

| Store | Size | Entities | Snapshots | Largest series attribute |
|---|---|---|---|---|
| `europe-full-resolution`, 1 revision | 1.38 GB | 232,871 (176,737 generators) | 8,760 | `p_max_pu`: 1,186 million rows, 9,516 row groups |
| `BEL-full-res`, 1 revision | 36 MB | 2,770 (1,469 generators) | 26,280 | `p_max_pu`: 27.8 million rows, 226 row groups |
| `BEL-pre-aggregated-incl-patches-incl-results`, leaf result `d147af69`, 3 layers | 13 MB | 246 (128 generators) | 2,190 | `p` of a result: 0.49 million rows |

Timings:

| Step | `europe-full-resolution` | `BEL-full-res` | Result leaf, 3 layers |
|---|---|---|---|
| Process start to Quack ready | 0.37 s | 0.27 s | |
| Workspace, Store, Record | 0.02 s | 0.02 s | |
| `register`, revision not materialised | 330 s, one run (329 s of it builds the owner map) | 6.3 s | 1.35 s |
| `materialise()` | 331 s, one run, writes 15.2 MB | 5.8 s, 80 kB | 0.53 s, 14 kB |
| `register`, revision materialised | 1.6 s | 0.86 s | 1.02 s |
| `register` of a child with one edit, root not materialised | 358 s, one run | 10.9 s | |
| `register` of a child with one edit, root materialised, child not | 2.6 s | 1.08 s | |
| Commit of a child with one edit, root not materialised | 324 s, one run; `commit()` itself 0.09 s, the rest is the fold behind the WR | 10.2 s | |
| Commit of a child with one edit, root materialised | 0.9 s edit, 0.04 s `commit()` | 0.66 s | |
| `p_nom` of all generators | 142k rows: srv 0.07 s, cli 0.13 s | 551 rows: 0.01 s | |
| Constants of six attributes as one `UNION ALL`, the planned `static` read | 990k rows: srv 0.36 s, cli 0.59 s | 10k rows: 0.03 s | under 0.02 s |
| Old `attribute_summary` scan | 1.9 million rows: srv 24.6 s, cli 26.0 s | 0.5 s | 0.11 s |
| `p_max_pu WHERE entity = '...'` (8,760 rows) | srv 5.5 s; 9,516 of 9,516 row groups | 0.10 s; 226 of 226 | |
| `p_max_pu WHERE snapshot IS NULL` (2,465 constant rows) | srv 1.37 s; 9,516 of 9,516 row groups | 0 rows | |
| `marginal_cost WHERE snapshot IS NULL` (file of constants) | 200k rows: srv 0.15 s | 2k rows: 0.005 s | |

Findings:

- The fold of a layer that is not materialised costs about 0.28 s per million series rows. `register`, `materialise()` and a commit on such a parent all pay it. With a stored fold every one of them takes seconds, also on the store of 1.4 GB.
- A child with one edit on a materialised root registers in 2.6 s without a stored fold of its own. This supports the rule that session commits are not materialised.
- `WHERE entity = '...'` prunes nothing through the view, on every store (R8). On the raw file of `europe-full-resolution`, which is sorted by entity, the same filter reads 3 of 9,516 row groups in 0.12 s. So the pushdown is worth a factor of about 45 there.
- `WHERE snapshot IS NULL` no longer prunes. The filter reaches the Parquet scan, but all row groups are read (1.37 s). `snapshot` is now a struct (`period`, `timestep`); on the raw file `snapshot.period IS NULL` reads 1 row group in 0.13 s, `snapshot IS NULL` all of them. The first run on the old store saw 1 row group and 0.12 s, with a plain `snapshot`. Added to R8.
- Constants: each attribute is one file per layer. In a file that mixes constants with series, the constants are one block at the end (`p_max_pu` of Europe: 2,465 rows in the last row group). Most attributes of the `static` read have files with constants only. So the `static` read stays cheap; the constants of a large series file cost a second until R8 covers the struct filter.
- The guard still refuses CREATE TABLE, COPY TO, ATTACH, SET, DROP SCHEMA, `read_parquet`, EXPLAIN and EXPLAIN ANALYZE from the client.

Regenerated stores with revision `meta` and `store.json` (bucket folder `2026-11-13/`, mirrored to `test-data-2026-11-13/`). Measured on 2026-11-13:

- DR main opens all six layered stores. The revision ids are those of folder `2026-11-11`; the manifests were rewritten with `meta`, the `claim.json` files keep an empty `meta`.
- Every store has a `store.json` of the agreed form. Every reference points to an existing revision. The eight references of `BEL-pre-aggregated-incl-patches-incl-results` are the agreed ones.
- The `meta` keys are `manta.kind` and `manta.created_by`. Decided: the prefix stays, for every Manta key in `meta`. `Store.revisions(meta={"manta.kind": "scenario"})` filters correctly.
- `manta.created_by` is missing on every `scenario` revision. The results carry the block name (`myopic_capacity_expansion`, ...).
- `revisions.json` is gone. The BE cannot import this folder until it reads `store.json` instead (decided, [revision index](backend.md#1-revision-index)).
- No store has `resolved/`.
- `ac-dc-meshed-plain-record` is a plain record without `layers/`, and has no `store.json`.

Consequences:

- On DR main: a revision must be materialised before a session registers it. Then a cold start is seconds; without, minutes at every start. Decided then (D16): whoever uploads a store materialises its revisions before the upload. With the stack the reason is weaker ([what the DR stack changes](#83-what-the-dr-stack-changes), D17). Commits through the session are not materialised: an edit layer is small against the inputs, and its fold starts from the stored fold of the parent. Results of runs are out of scope here: the blocks decide when to materialise (the idea is every n-th result).
- On DR main: a commit on a parent that is not materialised can exceed the 900 s commit token on larger stores. With the stack the fold behind the commit takes seconds ([what the DR stack changes](#83-what-the-dr-stack-changes)); not measured as a commit.
- The `static` read at page open is cheap, which supports "the FE reads all default columns at page open" ([constant values and the owner map](frontend.md#2-constant-values-and-the-owner-map)).
- Dropping `attribute_summary` saves about 25 s per open on `europe-full-resolution`.
- None of the `playground/*.store` examples opens with DR main: they keep `manifest.json` at the store root and have no manifest per layer. With the stack no existing store opens (F30). The import of example data needs a new export ([known issues](#5-known-issues), I9).

### 8.2 Results of S7 (quack-oauth)

An evaluation; `quack-oauth` was never decided. Measured with the published binary for DuckDB 1.5.6 (git `f55c3d0`) and with plain Quack on DuckDB 2.0.0. The scripts and outputs are not part of the repository.

- No binary for DuckDB 2.0.0. Release v2026.10.21 builds on 2.0.0 in its CI, but `get.erpl.io` serves binaries for 1.5.6 and 1.4.5 only (release notes; the 2.0.0 paths answer 404). A build from source was not run. The earlier text of this plan, "supports DuckDB 2.0.0", was too strong.
- Token validation works (measured, 1.5.6, against a local JWKS server): expired, wrong audience, wrong issuer, unknown key, wrong signature and garbage tokens are rejected. It checks signature, `iss`, `aud`, `exp` and `nbf`, not `azp` (read). The extension fetches the JWKS with its own HTTP client, so it works with DuckDB's HTTP file systems off and the configuration locked.
- The policy is a SQL table, read at every request, evaluated on DuckDB's parse tree, default deny, with rules per subject or scope. Denied in the test: another DuckDB schema, `read_parquet`, `read_csv`, `glob`, `COPY`, `ATTACH`, `SET`, `CREATE`, `DROP`. A view added at runtime was readable at once. EXPLAIN is allowed.
- It does not fit the names of [names in DuckDB](session.md#4-names-in-duckdb). A name with a catalog in front is rejected as "catalog-qualified object" before any rule runs (`src/sql_inspect.cpp:101-106`). For a nested name it reads only catalog, leaf DuckDB schema and table, so the registration name is lost ([names in DuckDB](session.md#4-names-in-duckdb)). No rule can tell two registrations apart.
- Its callbacks are C++ functions. A client with a valid token could not change the policy table, the callbacks or the settings (measured, 1.5.6). Upstream Quack issue 325 is still open.
- It does not help with token refresh. Quack authenticates when a connection opens. The token travels in the request body, not in an HTTP header. After expiry every query fails until `DETACH` and `ATTACH` (read); on plain Quack 2.0.0 a replaced secret took effect only after a new attach (measured).
- Only the server needs the extension. It has no WASM build and needs none. Quack itself has WASM builds for 2.0.0.
- Signals: one main author, repository from May 2026, eight releases, a large test suite. MIT. The binary is unsigned and served over plain HTTP. Telemetry is on by default (`DATAZOO_DISABLE_TELEMETRY=1` turns it off).
- Not verified: a 2.0.0 build, a real Keycloak (its tokens need an audience mapper), expiry on a live attached connection.

Consequences:

- The SQL macro stays as the guard for now. Argued, not measured: the attack of issue 325 needs a statement that our macro rejects, since it allows SELECT only. One test on DuckDB 2.0.0 settles this.
- To look at again when a 2.0.0 binary exists and nested DuckDB schema paths are supported. What it would add then: login by JWT, rules per user for a shared session (S5), and an audit table.
- The token split of the [Quack auth check](backend.md#5-routes-and-quack-auth-check) is unchanged: the Keycloak token travels in a header to Caddy and the BE, the Quack token in the body to the session.

### 8.3 What the DR stack changes

The DR stack is that of F29. Numbers are those of the PR texts: one laptop with 8 cores, local disk, DuckDB 2.0.0. Not run again for this plan. "Europe stack" is `europe-full-resolution` plus two edit layers. The PRs do not say whether its base layer was materialised.

| Operation | DR main ([results of S2 and S3](#81-results-of-s2-and-s3-on-dr-main)) | Stack | Source |
|---|---|---|---|
| Cold fold of `europe-full-resolution`, one layer | about 310 s | 0.7 s with `owner_map_rows.parquet`; 6.1 s for a layer written before PR 147 | PR 147 |
| Cold fold of all 8 revisions of the BEL store | | 3.3 to 3.5 s | PR 147 |
| `register` of a committed revision, Europe stack | 330 s (one layer, not materialised) | 3.1 s; 2.75 s with an in-memory workspace; peak memory 752 MB | PR 159 |
| WR on the Europe stack: constructor, then `register` | 358 s (`register` of a child), 324 s (commit) | 4.0 s and 3.4 s | PR 159 |
| `p_max_pu WHERE entity = '...'` | 5.5 s, all 9,516 row groups | 0.23 s, 3 row groups | PR 148 |
| `p_max_pu WHERE snapshot IS NULL` | 1.4 s, all row groups | 1.5 s, all row groups | PR 148 |
| `p_max_pu WHERE snapshot.period IS NULL` | | 0.2 to 0.4 s, 1 row group | PR 148 |

Consequences:

- A cold start no longer depends on a stored fold, if every layer carries `owner_map_rows.parquet`. Every writer of the stack writes it. Stores must be exported again anyway (F30), so a new export has it.
- The upload rule (D16) is not needed against minutes any more. Decided (D17): it is dropped.
- The risk that a commit exceeds the 900 s token is small now. It is argued from the fold time, not measured.
- The series of one entity is an interactive read (0.23 s on 1.2 billion rows).
- The session container needs memory for the fold: about 0.75 GB at `register` on the Europe stack.
- Not measured on the stack: `materialise()`, a commit, `BEL-full-res`, and anything through Quack or S3. S2 and S3 run again on stores exported with the stack.
- The numbers of PR 159 were taken before its last rebase.

## 9. Where the quack-server functions move

| Function today | Where | Target | Note |
|---|---|---|---|
| Quack server start and stop | `app/quack.py:84-104` | S | |
| Quack token (one shared token) | `main.py:46` | BE issues, S enforces | One per session. |
| Read-only SQL guard | `quack.py:54-99` | S | Two layers: DuckDB settings (HTTP file systems off, configuration locked) and a statement check as a SQL macro. The settings move as is. The macro moves and stays for now; `quack-oauth` was evaluated and does not fit today ([results of S7](#82-results-of-s7-quack-oauth)). |
| `POST /quack` relay and CORS | `main.py:175-196` | frontend Caddy, checked by the BE | Caddy proxies `/quack` to the session after the BE's auth check. Same origin, so CORS goes away. |
| Bearer auth on `/api/*` | `main.py:106` | BE | Keycloak. |
| `GET /api/records` (store list) | `main.py:121-131` | BE | From an S3 listing and `store.json`. Later from Postgres. |
| `POST /api/records/{id}/open` | `main.py:134-151`, `stores.py:215-304` | split | Revision list: BE. Registration: S. Manifest and view list: S, per registered revision. |
| Revision list, parents (`manta.revisions`) | `scenarios.py:145-153` | BE | Read from DR ([revisions](backend-mvp.md#5-revisions)). Later the Postgres revision index. Not a table in each of today's scenario catalogs. |
| Names, labels, descriptions (side files) | `scenarios.py:90-104` | BE, in `store.json` ([references in `store.json`](backend-mvp.md#6-references-in-storejson)) | Only the BE writes the file. Later a reference table holds its contents. |
| Kind `scenario` or `result` (heuristic) | `scenarios.py:91-96` | commit `meta`, read by the BE | A fact about the revision. The writer records it. Heuristic dropped. |
| Today one catalog per scenario (`ATTACH ':memory:' AS <record>__<scenario>`), each with the DuckDB schemas `dims`, `properties`, `attributes` and `manta` | `stores.py:290-299`, `record.py:24-45` | DR `Record.register(name)`: one DuckDB schema per registration in the session's one catalog ([names in DuckDB](session.md#4-names-in-duckdb)) | Any revision can be registered, results too. |
| `manta` views and tables (today's DuckDB schema `manta` in each scenario catalog) | `manta_views.py`, `scenarios.py` | see [replacing the manta objects](session.md#5-replacing-the-manta-objects) | Decision D4. |
| Parquet metadata prewarm | `stores.py:238-257` | S | At registration. |
| Default record, background open, files endpoint | `main.py` | drop | |
| Explorer page | `static/index.html` | drop | |
| WASM extension files and build scripts | `static/ext/`, `scripts/` | FE static assets | |
| Write path | none | S writes, BE authorises | New, [commit flow](storage-commit.md#1-commit-flow). |
| Per-user isolation | none | BE and S | New. |

## 10. Issues the plan does not cover

Read with the table of [issues that the plan touches](index.md#11-issues-that-the-plan-touches).

- [#83](https://github.com/manta-plan/manta/issues/83) Authorization & RBAC and [#125](https://github.com/manta-plan/manta/issues/125) Users and roles: the plan checks project ownership only.
- [#21](https://github.com/manta-plan/manta/issues/21) Collaborate analyzing results: sessions are per user, and sharing a project is out of scope.
- [#222](https://github.com/manta-plan/manta/issues/222) Generate on-the-fly user accounts: every guest gets a container, and the plan sizes no capacity for the roughly 100 users of the launch hour that #284 expects.
- [#210](https://github.com/manta-plan/manta/issues/210) Set run limits and rate limits: the plan has a global session cap, but no limit per user on sessions, commits or queries.
- [#97](https://github.com/manta-plan/manta/issues/97) Load a premade model: the plan lists a store once it is in S3, not the upload or conversion.
- [#3](https://github.com/manta-plan/manta/issues/3) Handle batches of scenarios: references are created one by one; no batch.
- [#100](https://github.com/manta-plan/manta/issues/100) Export results in standard formats: `store.json` travels with an export, but no export flow is designed.

## 11. Plan items without an issue

- Phase 0: review and merge of DR PR 144 and the stack (I11), and the new export of all stores into a new bucket folder (I9, F30).
- Phase 2: the store, revision and reference routes over DR and `store.json`, with the conditional write of `store.json`.
- Phase 3: the `datarecord-session` package (Quack, guard, registration, view packs) and its image, built by a one-shot compose service.
- Phase 4: session tables, Docker launcher, `ensure_datarecord_session`, registration routes, Quack auth check in Caddy, idle and suspend policy.
- Phase 5: the move of `manta/frontend`'s record client to the BE routes (open the session, register, attach, re-attach after `Invalid connection id`), with the presence call in place of `SELECT 1`.
- Phase 6: implementation of the commit path; #267 is the design only.
- The FE settle function, with a DuckDB for Node added to the existing `vitest` run and a pinned copy of `settle_cases.json` in CI (F23).
- Spikes: S2 and S3 again on the stack, the left-over of S6 (an STS token as `S3Credentials` on SeaweedFS).
- The test of a conditional `If-Match` write of `store.json` on SeaweedFS 4.53, and the move of dev from SeaweedFS 4.05.
- I3: browser check that the Quack secret's headers reach the BE from WASM, also after a token refresh.
- I2 and I8: a test on DuckDB 2.0.0 that the SQL guard blocks the attack of upstream Quack issue 325.
- I4: the pin `duckdb==2.0.0` and the locally built, unsigned Quack WASM extension, moved together.
- I10: session containers share the compose network with SeaweedFS's credential-free internal ports.
- I1: the session holds the global S3 key until the storage grants reach it; how the BE mints tokens and which role sessions get, to agree with Kristijan.
- Blocks: how a block authenticates to the BE and whether it can reach it (needed for the claim flow of blocks).
- BE tasks: cleanup of stale claims and of orphan session containers.
- D6: a rule operation in the changeset.
- Owner of a convention set (view pack) and its preload list.
- Phase 8: working records with the edit log, the shared session per project (S5), and the revision index (tables, `sync_store`, run results recorded per revision), which #283 names as the long-run target.
