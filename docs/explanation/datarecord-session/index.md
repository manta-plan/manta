<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# datarecord-session: overview

Status: draft 9 for team discussion, 2026-11-18, with the MVP step of the BE in the [MVP backend note](backend-mvp.md). This page is the entry. It describes the flows through the system, step by step, and links to the detail in the design notes. Reference material (terms, facts, measurements, requests to datarecord, decisions, known issues, phases) is in the [appendix](appendix.md).

The part that the team builds first, without the write path, is in the [work plan](read-path-first.md).

Terms: **BE** = main FastAPI backend. **FE** = frontend (prototype in `baby-manta`, product in `manta/frontend`). **DR** = the datarecord library. **Session** = the new service of this plan. **Store** = one dataset of a project, a folder in S3 that holds layers. **Revision** = a committed state of a store, named by a UUID. Each revision is one layer on top of its parent. **Registration** = a revision that a session exposes to SQL under a name. **WR** = working record, DR's editable record on top of a revision.

## 1. Goal

Each logged-in user reads and edits the data of a project through a private, short-lived service, the datarecord-session.
The session reads the project's stores from S3, serves selected revisions over the Quack protocol to the DuckDB-WASM client in the FE, and writes edits as new revisions.
FE API calls go through the BE. Quack data goes from the frontend Caddy straight to the session, after the BE has checked the request. The BE lists stores and revisions and owns every write permission.

The session replaces `docker/quack-server` (issue #223). That server has one shared token for all users, no isolation between users, and no write path.

## 2. Schematic overview

```
Browser                       Frontend Caddy      BE (FastAPI)                            Session (one per user + project)
-------                       --------------      ------------                            --------------------------------
DuckDB-WASM --POST /quack---> route /quack -----> quack-auth: checks token,
                              forward_auth <----- ensure_datarecord_session,
                                    |             204 + X-Session-Upstream
                                    +-- body unchanged, not through the BE --------------> Quack server (read-only SQL)
session client --/v1/...----> /v1/* ------------> session routes ------------------------> session API
                                                  DatarecordSessionService                    |
                                                   - Postgres: datarecord_sessions,           | reads: token for the
                                                     datarecord_session_registrations         |   project's folder
                                                   - DR, store.json: stores, revisions,       | writes: token for one
                                                     references                               |   layer, from the BE
                                                   - DatarecordSessionLauncher (Docker)       |
                                                   - claims + scoped write tokens             |
                                                   - idle and suspend policy                  v
                                                            |                          S3: <bucket>/<project_uuid>/<store>/
                                                            +-- claim.json, store.json ------^
```

State: S3 holds the data of every revision and is the truth. In the MVP, the only Postgres tables are `datarecord_sessions` and `datarecord_session_registrations`. The BE reads stores, revisions and references from S3, through DR and `store.json`. After the MVP, stores, revisions and references move into Postgres tables too. A session holds nothing that cannot be rebuilt from the other two.

DR session is a subordinate of BE: BE calls the session and receives answers. the session does not need a BE credential. The session can be stopped at any time, because the BE can rebuild it.

| Component | What it is | Design note |
|---|---|---|
| Session | A new service, `datarecord-session/`. One container per user and project. A Quack server for SQL, and an HTTP API that only the BE calls. | [session.md](session.md) |
| BE | Gains store and revision routes over DR and `store.json`, the session management, and the Quack auth check. Later a revision index. | [backend.md](backend.md), [backend-mvp.md](backend-mvp.md) for the MVP step |
| S3 and tokens | The session reads with a token for the project's folder. It writes with a token for one layer. | [storage-commit.md](storage-commit.md) |
| FE | Keeps DuckDB-WASM and SQL. Talks to the BE, and sends Quack queries through the frontend Caddy to the session. | [frontend.md](frontend.md) |

The flows below, in the order a user meets them:

| # | Flow | Parts involved |
|---|---|---|
| 3 | A store enters a project | BE, S3 |
| 4 | A user opens a project | FE, BE, session |
| 5 | The FE reads data | FE, BE, session, S3 |
| 6 | The FE shows what a scenario changes | FE, BE, session |
| 7 | A user commits an edit | FE, BE, session, S3 |
| 8 | A session stops and comes back | BE, session, FE |
| 9 | A run writes results | blocks, BE, S3 |
| 10 | Later: live editing | FE, BE, session |

## 3. A store enters a project

Today the BE has no record of a store or a revision. It looks them up in S3 and in Prefect when asked. The MVP keeps it so and builds no index.

1. A store arrives in the project's folder in S3: example data, a copy, or an import. The file `store.json` at the store's root is written last. It marks the store as complete.
2. The BE lists the project's folder in S3. Each folder with a `store.json` is a store.
3. The BE lists the store's revisions with DR: id, parent, kind (`scenario` or `result`), author, times. The BE answers the revision routes by calling the store's `revisions()` method. DR lists `layers/` at each call and reads only the manifests it does not hold yet. The BE keeps DR's in-memory DuckDB between requests as a read cache. A claim or a commit needs none of it (flow 7), so a restart loses only speed.
4. The BE reads `store.json`. It holds the store's label and the *references*.

A reference is a named pointer to one revision, like a branch in Git. It carries the name, the label and the description that the user sees. A name is not part of a revision. A scenario can therefore be renamed, or moved to a newer revision, without a new revision. A reference also records its *base*: the reference it was made from, fixed at creation (flow 6).

S3 stays the only truth. Only the BE writes `store.json`. It changes a reference by a conditional write of the whole file (flow 7). So the names travel with an export.

`GET /v1/projects/{id}/datarecord-stores` and `GET .../datarecord-stores/{store}/datarecord-revisions` answer from these reads. Neither needs a session. A new revision shows at the next listing, and no writer has to tell the BE.

A revision index in Postgres is the later step. It holds the contents of `store.json` and the manifests' metadata for queries and filters, behind the same routes and the same `store.json`. The [backend note](backend.md#1-revision-index) describes it, and the [MVP backend note](backend-mvp.md#13-what-the-mvp-step-is-good-for-and-when-to-move-to-the-index) names when it is due.

Detail: [Stores of a project](backend-mvp.md#4-stores-of-a-project), [Revisions](backend-mvp.md#5-revisions), [References in `store.json`](backend-mvp.md#6-references-in-storejson).

## 4. A user opens a project

1. The FE reads stores, revisions and references from the BE, which reads them from S3 (flow 3). No session runs yet.
2. The FE opens the project's session: `POST /v1/projects/{id}/datarecord-session`. This is a call of its own, apart from login and from reading the project. A session belongs to a user and a project, and pages that only list or configure a project must not start a container.
   - 2.1 The BE checks that the user owns the project and runs `ensure_datarecord_session` for the pair of user and project. `ensure_datarecord_session` means "start the session if none runs": it locks the datarecord session's row, starts a container when needed, and repeats the stored registrations. The BE stores the datarecord session's metadata in that row, so it can recreate the connection and continue operations later. The lock makes parallel requests start one container. Every later session call and every query runs `ensure_datarecord_session` too, so a stopped session comes back by itself.
   - 2.2 If no container runs, the BE's launcher starts one. It passes four inputs: the project's folder `s3://<bucket>/<project_uuid>/`, an S3 token that can only read that folder, a Quack token, and a secret for the API.
   - 2.3 The session opens one DuckDB connection and creates one DR workspace on it, attached as the catalog `manta`. It starts the Quack server on the same connection, installs the SQL guard, and reports ready. This takes under a second.
   - 2.4 The BE returns the Quack address and the Quack token to the FE.
3. The FE registers the revision of the active scenario: `PUT /v1/projects/{id}/datarecord-session/registrations/{name}`, with store, revision and view packs.
   - 3.1 The BE writes this as a row, then calls the session. The row is what makes a restart possible (flow 8).
   - 3.2 The session opens the revision with DR and registers it. DR *folds* the revision: it works out, for every value, which layer of the revision's history holds it. The result is the *owner map*. DR creates lazy views in the DuckDB schema `manta.<name>`. No value is read.
   - 3.3 The session adds its own views to the same DuckDB schema, and reads the Parquet metadata ahead of the first query. Steps 3.2 and 3.3 take about 3 seconds for the largest store.
   - 3.4 The BE returns the SQL prefix of the registration, for example `manta.<name>`. The FE puts it in front of every view name.
4. The FE attaches DuckDB-WASM to the `/quack` address on the app's own origin.

What a registration `manta.<name>` holds after step 3.3:

| View | From | Content |
|---|---|---|
| `dimensions.<d>` | DR | the labels of a dimension (entities, buses, snapshots) |
| `properties.<subject>` | DR | the properties of each label (carrier, component type) |
| `attributes.<A>` | DR | the values of one attribute, as stored |
| `owner_map` | DR | which attributes exist for which label, and whether each is a constant or a series |
| `static_<dtype>` | session | all constant values in one long view per value type: entity, bus, attribute, value |
| `"pypsa-eur".<view>` | session, on request | a *view pack*: the seven map and topology views of today's quack-server, which encode PyPSA-Eur conventions |

The launcher behind step 2.2 is an interface with three calls: start, stop, list. The first implementation uses Docker. Kubernetes follows next year.

Detail: [Session service](session.md#3-session-service), [Names in DuckDB](session.md#4-names-in-duckdb), [View packs](session.md#5-replacing-the-manta-objects), [Launcher](backend.md#4-launcher), [Backend routes](backend.md#5-routes-and-quack-auth-check).

## 5. The FE reads data

### One query

1. The FE runs a query that names its views in full, with the prefix of the registration, for example `manta.<name>.attributes.p_nom`. DuckDB-WASM sends it as one HTTP request to `/quack` on the app's origin, where the frontend Caddy receives it. A Quack client can only post to `/quack` at the root of a host, so the route lives there, outside `/v1`.
2. The request carries two HTTP headers from a Quack secret that the FE created: the user's Keycloak token and the project id.
3. Caddy asks the BE with a subrequest that has the headers but no body. The BE authenticates the token, finds the session of that user and project, and runs `ensure_datarecord_session`. It answers with the container's address, and Caddy proxies the request there, body unchanged.
4. The session checks the Quack token inside the body. Two guards then apply. DuckDB's settings forbid HTTP file access and lock the configuration. A statement check lets only SELECT pass.
5. DuckDB runs the query on the views. The views read Parquet files from S3 with the read token. A filter on an entity reaches the Parquet scan, so a query for one entity reads only the matching part of a file.
6. The rows travel back through Caddy, raw, as the layers store them. They do not pass the BE.

Detail: [Quack auth check](backend.md#5-routes-and-quack-auth-check), [Rules of the session service](session.md#3-session-service), [measurements](appendix.md#8-spikes-and-measurements).

### A component table

Today the page reads a table that quack-server prepares at open with a full scan of every attribute. That table goes away. The page asks two cheap questions instead.

1. The FE reads the owner map: which attributes this component type stores, for how many entities, and which have a series. This reads no values. It gives the column picker, the counts and the profile markers.
2. The FE reads the constant values of the visible columns from the `static_<dtype>` views, with a filter on those attributes. This is one query per value type.
3. The FE computes sort, search, totals and the "same, range or mixed" figures in the browser from the loaded rows. A revision never changes, so loaded rows stay valid.

The drawer of one entity works the same way: the owner map for that entity, then the attributes the map lists. A series is one query on `attributes.<A>` with a filter on the entity.

Detail: [Constant values and the owner map](frontend.md#2-constant-values-and-the-owner-map), with the list of attributes the FE loads at page open.

### Settling the rows

The session returns rows as stored. A stored row can leave a dimension empty, and then stands for every label of it: one `marginal_cost` for all snapshots, or one value for all entities. Several rows can cover the same coordinate. DR's broadcast rule says which one holds: the most specific. To apply the rule is to *settle*.

Today's FE queries ignore this or apply partial rules of their own. In the target the FE owns one TypeScript function that composes the rule as SQL.

1. The function takes a source query and, per dimension, the labels to expand over. It returns one SQL statement.
2. If the result is small (a series of one entity, a total per carrier), the FE sends the statement to the session like any query.
3. If the raw rows are the small form (the constants of a whole table), the FE fetches them raw and runs the same statement on its local DuckDB-WASM.

The session offers no settled view. DR ships 20 test cases as a JSON file; DR's own settle and the FE's function run the same cases.

Detail: [Settling in the FE](frontend.md#4-settling-in-the-fe).

## 6. The FE shows what a scenario changes

A scenario is a reference, and a reference moves with every commit. So the FE shows each scenario against its base, the scenario it was made from. The baseline is the *fork point*: the last revision that the histories of the two share. It stays the same when the base is edited later.

The FE has two needs here, with two sources.

The FE's panel, its view of the differences, shows per scenario and attribute how many entities changed. This change summary compares the scenario's current revision with the fork point with the scenario's base.

1. The FE asks the BE for the changes of each scenario.
2. The BE resolves each scenario to two revision ids: its current revision and its fork point. It reads the current revisions of the scenario and of its base from `store.json`. DR gives the chain of parents of both from the manifests. The fork point is the last revision that the two chains share.
3. The BE asks the session. The session computes the summary from the two revisions, and the BE passes it to the FE.

Nothing is stored. The session computes the summary at each request, and `ensure_datarecord_session` starts the session if none runs.

The change table and the change markers need the values before and after:

1. The FE registers a diff: `PUT .../datarecord-session/registrations/{name}` with the kind `diff` and the scenario's reference as `after`. Without `before`, the baseline is the fork point with the scenario's base.
2. The BE resolves both sides to revision ids and calls the session.
3. The session opens both revisions; neither has to be registered. It creates a DuckDB schema with three lazy views.
4. The FE reads `static_<dtype>` of the diff for the attributes on screen. It has the same shape as the view of a revision, with `before` and `after` in place of `value`.

| View of a diff | Content | Cost |
|---|---|---|
| `map_rows` | the entries of the two owner maps that differ: "what was touched" | no value read |
| `static_<dtype>` | constants that differ, with `before` and `after` | reads the constants of the touched attributes |
| `series_<dtype>` | series values that differ | read on demand; the FE aggregates over it in SQL |

The same call compares two scenarios as they are today: the FE names both references. The BE then uses their current revisions, so later edits of either one show as differences.

A scenario does not see later edits of its base, because its parent chain is fixed. The plan has no rebase.

Detail: [Changes between revisions](frontend.md#3-changes-between-revisions), [Fork point](backend-mvp.md#7-the-fork-point).

## 7. A user commits an edit

The session can read the project's folder and nothing else. For each commit the BE reserves the new revision and creates a token that can write into that one layer.

1. **The FE sends a changeset** to `POST /v1/projects/{id}/datarecord-stores/{store}/datarecord-revisions`. A changeset is an ordered list of operations: `set` (a value at coordinates, or a table of values), `add` (new labels with their properties) and `remove` (labels). It is one multipart request: a JSON part that names the reference to move, a JSON part with the list, and one Parquet part per table.
2. **The BE checks.** The user must own the project. The move is a compare-and-swap, like moving a branch in Git: the FE asks to move reference A from revision X to the new revision Y. The BE reads `store.json` and refuses at once if A no longer points to X. A reference only points to committed revisions, so this check also proves that the parent X is committed.
3. **The BE claims.** It calls DR's `Store.claim` with the parent and the `meta` (kind and author). The BE passes the parent as `Revision(id=X, store=store)`, which reads nothing from S3. A claim therefore needs no manifest and no state in the BE's memory. DR draws the id of the new revision and writes `layers/<id>/claim.json`. The BE keeps no row for it.
4. **The BE mints a write token.** It asks the object store for a short-lived token (`sts:AssumeRole`) with a policy that allows put, get and list under `layers/<id>/` only. The token lives 15 minutes.
5. **The BE calls the session** with the claim, the token and the changeset.
6. **The session builds the layer.** It opens a WR on the parent and applies the operations in order. The WR completes the layer: a layer must restate every series it touches in full, and only a WR does this. This is why neither the FE nor the BE builds a layer.
7. **The session commits.** It calls `Claim.commit` with the write token. DR writes the Parquet files and `manifest.json` under `layers/<id>/` with that token. It reads the parent layers with the session's read token.
8. **The session returns the manifest.**
9. **The BE confirms.** It compares id, parent and `meta` of the manifest with its claim.
10. **The BE moves the reference.** It reads `store.json` again and checks that the reference still points to the expected revision. It sets the reference to the new revision and writes `store.json` back with a conditional write. The object store accepts the write only if the file is unchanged since the read. If another change came first, the BE reads again and repeats the check. If another commit moved the reference, the BE reports a conflict; the new revision exists, but no name points to it. A task in the BE should remove such unreachable revisions. That task can come later.
11. **The FE registers the new revision** and shows it.

The two tokens come from the same mechanism as the storage grants for runs, tested on SeaweedFS:

| Token | Can read | Can write | Lives |
|---|---|---|---|
| Session read | the project's folder | nothing | as long as the session may |
| Commit | nothing outside its layer | `<project>/<store>/layers/<id>/` | 15 minutes |

A token cannot be taken back; it only expires. Until then the session could overwrite files of the layer it just committed. The short lifetime limits this.

If a commit fails, the claim stays as a `claim.json`. A task in the BE removes it after a time.

The FE has an edit model today that nothing sends. A direct change (one value of one entity) becomes a `set` operation. A rule change ("multiply `p_nom_max` of all solar generators") becomes `set` operations too: the FE has the current values and computes the new ones. One more operation type, which the session expands with SQL, is sketched as a later addition and is not decided.

Detail: [Commit flow](storage-commit.md#1-commit-flow), [References in `store.json`](backend-mvp.md#6-references-in-storejson), [The two tokens](storage-commit.md#2-the-two-tokens), [Changeset format](storage-commit.md#3-changeset-format).

## 8. A session stops and comes back

1. Every Quack request that the BE checks counts as activity and sets a time on the session row. Presence is a separate call that the FE sends while the tab is open. Today's `SELECT 1` every 15 seconds goes away, because the BE cannot tell it from a real query.
2. After 10 minutes without activity the session is idle. The BE may stop it when it needs capacity, and it picks the session that was used least recently.
3. After 60 minutes without activity the BE stops the session at once.
4. Nothing is lost, because the session holds only views.
5. At the next request `ensure_datarecord_session` starts a new container and repeats every registration from the rows of flow 4.
6. The FE's attached client gets the error `Invalid connection id` on its next query. The FE calls `POST /v1/projects/{id}/datarecord-session` again, detaches, attaches, and repeats the query. The user sees one slow request.

A task in the BE stops containers that no session row claims. A container also exits by itself after a hard limit.

Detail: [Session lifetime](backend.md#3-session-lifetime).

## 9. A run writes results

Blocks of a run write revisions too, outside the session.

1. The BE starts the run and passes the run's id to the blocks as a flow parameter.
2. A block commits its output with the global S3 key, as today. DR claims and commits in one call. The commit `meta` carries `manta.kind = result`, `manta.created_by`, `manta.run` and `manta.step`.
3. The next listing of the store shows the new revision. No block has to report it.
4. The run pages find a run's revisions through Prefect, as today. The input revision is a flow parameter, and each block publishes its last output revision as an artifact.
5. A block can write several revisions and publishes only the last (a myopic solve writes one per investment period). The earlier ones are its parents, and the BE can walk to them from the cached manifests.

Later, with the revision index, the BE records each revision with the id of the run, and the run pages read it there. The target is flow 7 for blocks: the block asks the BE for each claim and commits into it. The BE then knows every revision of a run from its claim on, and it can hand the block a scoped token that only allows writing a single new layer.

Detail: [Results of runs](backend-mvp.md#8-results-of-runs), [Runs and blocks](backend.md#2-runs-and-blocks).

## 10. Later: live editing

Planned after MVP. A WR registered for live editing lets the FE see its own unsaved edits in SQL. It is state that S3 does not hold, so the flow keeps a copy in the BE.

1. The FE opens a WR on a revision. The BE writes a registration row of the kind `edit`.
2. The FE sends each edit to the BE as a list of the operations of flow 7.
3. The BE appends the edit to an *edit log* of that WR, then passes it to the session. The session applies it. The registered views follow the edit. If the session refuses an edit, the BE drops it from the log.
4. A diff with the WR on one side shows the unsaved changes (flow 6).
5. To commit, the FE asks the BE. Flow 7 runs with the live WR in place of a fresh one. The log is cleared.
6. After a restart (flow 8) the BE opens the WR again and replays the log.

This shapes the design now: edits are an ordered list of operations, every write passes the BE, registration rows carry a kind, and one thread in the session owns the DR objects.

Detail: [Working records](session.md#6-working-records).

## 11. Issues that the plan touches

Issue lists read on 2026-11-19 with `gh` from `manta-plan/manta` (open issues, open PRs, closed issues), `manta-plan/baby-manta` and `energy-models/datarecord` (open issues).

Relations: **solved** (the plan's design removes the problem), **partly** (the plan covers a part; the rest is named), **prerequisite** (must be done before a phase), **affected** (the plan changes how the issue should be solved), **conflict** (the issue asks for something the plan decides against). Phases are those of [phases](appendix.md#4-phases).

### manta-plan/manta: open issues

| Issue | Relation | How the plan addresses it | Where | Phase |
|---|---|---|---|---|
| [#250](https://github.com/manta-plan/manta/issues/250) Design a BE Quack server | solved | The plan is this design. It chooses a separate per-user session service behind a Quack auth check in the BE, with the data proxied by the frontend Caddy. It rejects a Quack server inside the BE process. | [goal](index.md#1-goal), [session service](session.md#3-session-service), [routes and Quack auth check](backend.md#5-routes-and-quack-auth-check) | 3, 4 |
| [#245](https://github.com/manta-plan/manta/issues/245) Remove temporary quack server | solved | Phase 7 removes `docker/quack-server` and moves the WASM build scripts. The table of the appendix assigns every function of the server a new home. | [where the quack-server functions move](appendix.md#9-where-the-quack-server-functions-move) | 7 |
| [#201](https://github.com/manta-plan/manta/issues/201) Integrate the datarecord package | partly | The plan covers parts 2 and 3 of the issue: new scenarios through the commit flow, and data reads through one session per user and project. Part 1 (blocks) stays as today: blocks commit with the global key (I6), and the claim flow for blocks is a later target. | [commit flow](storage-commit.md#1-commit-flow), [runs and blocks](backend.md#2-runs-and-blocks) | 2 to 6, 8 |
| [#267](https://github.com/manta-plan/manta/issues/267) Design scenario mutation endpoints | solved | The plan specifies the endpoint (`POST .../datarecord-stores/{store}/datarecord-revisions`), the changeset, the move of the reference and the rewrite of `store.json`, and the refresh (the FE registers the new revision). It deviates from the issue in one point: the FE sends an ordered list of operations, not serialised layer data, because only a WR in the session can complete a layer. | [commit flow](storage-commit.md#1-commit-flow), [changeset format](storage-commit.md#3-changeset-format), [flow 7](index.md#7-a-user-commits-an-edit) | 6 |
| [#283](https://github.com/manta-plan/manta/issues/283) Store scenario and revision context in datarecord metadata | prerequisite | The issue records the MVP decision: scenario and revision context stays in DR metadata and `store.json`, with no new Manta tables, and the link from a run to its revisions stays in Prefect. It names the move to the Manta database as a later step. The plan follows this order. The MVP step works without a revision index and writes the same `store.json` and the same `manta.` keys. The revision index comes after it and is filled from what the MVP step already writes. | [MVP backend without a revision index](backend-mvp.md), [revision index](backend.md#1-revision-index) | 2 |
| [#284](https://github.com/manta-plan/manta/issues/284) Performance test of a large datarecord + quack + FE | partly | The plan measured the server side on DR main and lists the stack's numbers (register about 3 s, one entity's series 0.23 s). The end-to-end test from SeaweedFS through Caddy into the browser is left, as is the rerun of S2 and S3 on the stack. | [spikes and measurements](appendix.md#8-spikes-and-measurements) | 1, after 5 |
| [#271](https://github.com/manta-plan/manta/issues/271) Figure out S3 permissions for blocks | partly | The plan aligns its tokens with the storage grants for runs (F25) and proposes the claim flow through the BE, so a block could get a write right for one layer. How a block authenticates to the BE and whether it can reach the BE are open with Kristijan. | [runs and blocks](backend.md#2-runs-and-blocks), [the two tokens](storage-commit.md#2-the-two-tokens) | 8 |
| [#193](https://github.com/manta-plan/manta/issues/193) S3 security | partly | Sessions get no S3 key of their own: a read token for the project's folder and a 15-minute write token per layer. Blocks keep the global key (I6) until the claim flow for blocks. | [the two tokens](storage-commit.md#2-the-two-tokens), [known issues](appendix.md#5-known-issues) | 6, 8 |
| [#273](https://github.com/manta-plan/manta/issues/273) Harden the user register endpoint | prerequisite | The plan names this as I5: with sessions, any registered identity can start containers. The fix must land before session containers run in a public deployment. | [known issues](appendix.md#5-known-issues) | 4 |
| [#53](https://github.com/manta-plan/manta/issues/53) Deploy Production S3 Store | affected | The production store must support `sts:AssumeRole` with inline policies for the two tokens. SeaweedFS, AWS S3 and MinIO do; GCS does not, so a GCS bucket cannot serve sessions. | [the two tokens](storage-commit.md#2-the-two-tokens) | 6 |
| [#276](https://github.com/manta-plan/manta/issues/276) Create GH workflow files along with GCP configurations for MVP deployment | affected | The deployment runs Docker Compose on a VM. With the Docker launcher the BE must reach the Docker daemon to start session containers, and the session image must be built and deployed beside FE and BE. | [launcher](backend.md#4-launcher) | 4 |
| [#285](https://github.com/manta-plan/manta/issues/285) Cache keycloak signing keys | affected | The BE authenticates the Keycloak token on every Quack auth subrequest, so once per query. Without a cached JWKS each SQL query from the FE also costs a request to Keycloak, so this issue gains weight. | [routes and Quack auth check](backend.md#5-routes-and-quack-auth-check) | 4 |
| [#249](https://github.com/manta-plan/manta/issues/249) Add CI check to ensure we're using same datarecord package version everywhere | affected | The plan decides one DR commit hash for session, BE and blocks, moved together (D19). The check gains two more places: the session package and the BE's new dependency on `datarecord[remote]`. | [decisions](appendix.md#2-decisions), [revision index](backend.md#1-revision-index) | 0 |
| [#298](https://github.com/manta-plan/manta/issues/298) Seed built-in projects for each user | affected | Seeding copies stores into a project. A copy is a store of the project once its `store.json` is written. The references of `store.json` (such as `inputs`) are the project's scenarios. No sync step runs. | [stores of a project](backend-mvp.md#4-stores-of-a-project), [flow 3](index.md#3-a-store-enters-a-project) | 2 |
| [#221](https://github.com/manta-plan/manta/issues/221) Provide a example project with completed runs for each guest user | affected | Copied results show in the store listing as `result` revisions and as references of `store.json`, without a run row. Completed example runs that show as runs need a `runs` row and a link to their revisions. In the MVP the run pages find revisions through Prefect, which has no flow run for a copy; this link is open. Later, with the revision index, `input_revision_id` and `run_id` give it. | [results of runs](backend-mvp.md#8-results-of-runs), [runs and blocks](backend.md#2-runs-and-blocks) | 2 |
| [#282](https://github.com/manta-plan/manta/issues/282) Use datarecord metadata instead of hardcoded data catalogue | affected | In phase 2 the FE home page drops `record-server.ts` and reads stores and revisions from the BE routes, which answer from the S3 listing and `store.json`. The data catalogue should build on these routes, not on the temporary record server. | [phases](appendix.md#4-phases), [stores of a project](backend-mvp.md#4-stores-of-a-project) | 2 |
| [#246](https://github.com/manta-plan/manta/issues/246) Port Model tab from baby manta | affected | The ported tab should not read `attribute_summary`, which goes away. It reads the owner map and the `static_<dtype>` views, and settles rows with the FE's own function. | [constant values and the owner map](frontend.md#2-constant-values-and-the-owner-map), [settling in the FE](frontend.md#4-settling-in-the-fe) | 5 |
| [#79](https://github.com/manta-plan/manta/issues/79) Port Inspect tab from baby manta | affected | The tab reads a run's results by registering a `result` revision. The BE finds it through Prefect, as today; later through `run_id` in the index. Map views come from the `pypsa-eur` view pack. | [results of runs](backend-mvp.md#8-results-of-runs), [replacing the manta objects](session.md#5-replacing-the-manta-objects) | 2, 5 |
| [#187](https://github.com/manta-plan/manta/issues/187) Manta's database representation of playbooks and runs | affected | The plan settles one part. In the MVP every revision a run writes carries `manta.run` and `manta.step` in its `meta`, and the run pages keep the lookups in Prefect. Later, with the revision index, `runs` gains `input_revision_id`, and every revision carries `run_id` and `step`. This replaces the lookups in Prefect's parameters and artifacts. | [results of runs](backend-mvp.md#8-results-of-runs), [runs and blocks](backend.md#2-runs-and-blocks) | 8 |
| [#104](https://github.com/manta-plan/manta/issues/104) [KEY FEATURE] Scenario management & comparison | partly | References give named scenarios that can move and be renamed. Change summaries and diff registrations compare two scenarios. Upload of a model and runs of several scenarios at once are left. | [changes between revisions](frontend.md#3-changes-between-revisions), [revision index](backend.md#1-revision-index) | 2, 5 |
| [#10](https://github.com/manta-plan/manta/issues/10) [KEY FEATURE] Modify static model parameters directly in UI | partly | A direct change becomes a `set` operation, and a series can be sent as a Parquet table. Rule changes ("multiply all `p_nom_max`") need an operation type that is open as D6, and the editing UI is not part of the plan. | [changeset format](storage-commit.md#3-changeset-format) | 6 |
| [#11](https://github.com/manta-plan/manta/issues/11) [KEY FEATURE] Build model directly in UI | partly | The changeset has `add` (new labels with their properties) and `remove`. The UI and the assignment of BYO data are left. | [changeset format](storage-commit.md#3-changeset-format) | 6 |
| [#20](https://github.com/manta-plan/manta/issues/20) [KEY FEATURE] Collaborate building models/scenarios | partly | Revisions and references give the git-like history the issue asks for. Sharing and access control within an organisation are left: sessions are per user, a shared session is spike S5. | [revision index](backend.md#1-revision-index), [scope of a session](session.md#1-scope-of-a-session) | 2, 8 |
| [#139](https://github.com/manta-plan/manta/issues/139) How do we handle project deletion | partly | The plan decides the database side of the revision index: its `datarecord_*` tables cascade from the project. In the MVP stores, revisions and references live only in the project's S3 folder. Deleting that folder and stopping the project's sessions are not specified. | [decisions](appendix.md#2-decisions) | 8 |
| [#190](https://github.com/manta-plan/manta/issues/190) K8s execution environment | affected | The Kubernetes environment must also host session containers. The plan's launcher interface (start, stop, list) gets a Kubernetes implementation next year. | [launcher](backend.md#4-launcher) | 8 |
| [#71](https://github.com/manta-plan/manta/issues/71) Document trust boundaries and attack surface | affected | The plan adds a boundary: user SQL runs in a session container that holds S3 credentials. Its residual risks (guard I2, upstream Quack issue 325 as I8, the shared network with SeaweedFS as I10) belong in that document. | [known issues](appendix.md#5-known-issues), [the two tokens](storage-commit.md#2-the-two-tokens) | 4 |

### manta-plan/manta: open PRs

| PR | Relation | How the plan addresses it | Where | Phase |
|---|---|---|---|---|
| [#281](https://github.com/manta-plan/manta/pull/281) feat: use `store.json` and per-revision `meta` keys | prerequisite | The plan builds on `store.json` and the `manta.` keys of the commit `meta`. The first step of phase 2 makes the example data import read `store.json`. The PR's slug scheme (`<scenario>/<playbook>`) differs from the plan's references, which carry a `base` and take their kind from the revision they point to. | [the `store.json` form](backend-mvp.md#the-storejson-form) | 2 |
| [#287](https://github.com/manta-plan/manta/pull/287) feat: wire data records metadata with projects, data catalogue, and playbook | affected | The PR reads the catalogue and the `inputs` revision from the temporary record server. In the plan both come from the BE's store and revision routes, and `record-server.ts` goes in phase 2. | [phases](appendix.md#4-phases), [revision index](backend.md#1-revision-index) | 2 |
| [#301](https://github.com/manta-plan/manta/pull/301) feat: update docker setup for quack server | affected | The PR configures the temporary server. Phase 3 puts one fixed session instance in compose in its place, and phase 7 removes the server. | [phases](appendix.md#4-phases) | 3, 7 |
| [#209](https://github.com/manta-plan/manta/pull/209) docs: datarecord integration, vendored fork and step 1 requirements | affected | The plan continues this work on DR's own stack. Its pin (D19) is the stack tip, not the vendored fork at `521fef2`. | [decisions](appendix.md#2-decisions) | 0 |

### manta-plan/manta: recently closed issues

| Issue | Relation | How the plan addresses it | Where | Phase |
|---|---|---|---|---|
| [#223](https://github.com/manta-plan/manta/issues/223) Add a temporary quack server to enable porting FE features | affected | The plan replaces the server that this issue built. Follow-up #245 tracks its removal. | [goal](index.md#1-goal) | 7 |
| [#224](https://github.com/manta-plan/manta/issues/224) Design datarecord API for writing new revisions | prerequisite | Done in DR: one folder per layer with its own manifest and `claim.json`. The commit flow and the claim for blocks build on it. | [commit flow](storage-commit.md#1-commit-flow) | 6 |
| [#247](https://github.com/manta-plan/manta/issues/247) Optimize temporary quack server | affected | The copy to local disk goes away. The session reads S3 directly with its read token; the stack's fold makes a cold register take seconds. | [spikes and measurements](appendix.md#8-spikes-and-measurements) | 3 |
| [#248](https://github.com/manta-plan/manta/issues/248) Upgrade the datarecord version used in manta | prerequisite | Closed, but the plan pins the stack tip, which is still unmerged (I11). The bump repeats in phase 0, together with a new export of all stores (I9). | [open next](appendix.md#3-open-next), [known issues](appendix.md#5-known-issues) | 0 |

### energy-models/datarecord: open issues

| Issue | Relation | How the plan addresses it | Where | Phase |
|---|---|---|---|---|
| [#95](https://github.com/energy-models/datarecord/issues/95) Key a connection by (component, port), with the bus as its value | affected | DR PR 142 implements this outside the stack. When the pin moves to it, the `static` views and the `pypsa-eur` pack must take the bus of a connection from its properties (D18, F31). | [constant values and the owner map](frontend.md#2-constant-values-and-the-owner-map), [facts](appendix.md#6-facts) | 0, 3 |

`manta-plan/baby-manta` was reachable and has no open issues and no open PRs.

Issues that the plan does not cover, and work of the plan that has no issue yet, are in the appendix: [issues the plan does not cover](appendix.md#10-issues-the-plan-does-not-cover), [plan items without an issue](appendix.md#11-plan-items-without-an-issue).
