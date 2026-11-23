<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Design note: session service

The new service `datarecord-session`: its scope, components, internal API, the names it creates in DuckDB, working records, and the fate of today's `manta` objects.

Part of the datarecord-session plan, draft 9. Start with the [overview](index.md). The codes F, S, R, D and I point to the [appendix](appendix.md).

This note describes the session as a developer builds it. A session is a container per user and project. It holds one DuckDB connection with one DR workspace, attached as the catalog `manta`. A Quack server serves read-only SQL on that connection. An HTTP API, called only by the BE, registers revisions, diffs and later working records as DuckDB schemas `manta.<name>`, computes change summaries, and commits changesets. A diff and a change summary compare by default a reference's current revision with the fork point with its base reference. The BE resolves both to revision ids. The session holds nothing that the BE cannot rebuild, so it can stop at any time. [Replacing the manta objects](#5-replacing-the-manta-objects) lists today's `manta` objects of quack-server and what replaces each of them: view packs, the `static_<dtype>` views with the owner map, the BE's revision listing, and diff registrations.

## 1. Scope of a session

There is one session per pair of user and project.

A shared session per project stays a later option, not an open decision. It would reuse the DR caches of all users of a project. It needs one Quack identity per user and separation of the users' registrations inside one DuckDB (spike S5).

To keep that option open, the design separates two things from the start:

| Term | What it is |
|---|---|
| *session* | a user's token and registrations (revisions, working records, diffs) |
| *instance* | the running container, addressed by the launcher with its own id |

Today each session has one instance.

## 2. Components

```
Browser                       BE (FastAPI)                            Session (one per user + project)
-------                       ------------                            --------------------------------
DuckDB-WASM --POST quack----> quack relay ---------------------------> Quack server
session client --/v1/...----> session routes                           session API
                              DatarecordSessionService -------------------^   |
                               - Postgres: datarecord_sessions,               | read-only credential,
                                 datarecord_session_registrations             | project prefix
                               - DR, store.json: stores, revisions,           |
                                 references                                   |
                               - DatarecordSessionLauncher (Docker)           v
                               - claims + scoped write tokens ---------> S3: <bucket>/<project_uuid>/<store>/
                               - idle and suspend policy
```

The BE calls the session. The session never calls the BE. The session is therefore a plain server without BE credentials.

The BE side (stores and revisions, lifetime, launcher, routes) is in the [MVP backend note](backend-mvp.md), [session lifetime](backend.md#3-session-lifetime), [launcher](backend.md#4-launcher) and [routes and Quack relay](backend.md#5-routes-and-quack-relay).

## 3. Session service

The service lives in `datarecord-session/`, a new top-level uv package.

### Start-up

The launcher passes four inputs:

1. the store root `s3://<bucket>/<project_uuid>/`;
2. a read-only S3 credential;
3. the Quack token;
4. the API secret.

On start the session does these steps:

1. Create one `Workspace` on the connection that Quack serves, attached as the catalog `manta`.
2. Start Quack on that connection.
3. Install the SQL guard.
4. Report ready.

### Internal API

Only the BE calls this API.

| Call | Body | Effect |
|---|---|---|
| `GET /health` | | Ready when Quack serves. |
| `PUT /registrations/{name}` | `{kind: "view", store, revision, packs}` | Register the revision as the DuckDB schema `manta.<name>`. Add the `static_<dtype>` views to it and the requested view packs below it. Prewarm. Idempotent. Answers the SQL prefix of the registration, `manta.<name>`. |
| `PUT /registrations/{name}` | `{kind: "diff", store, after, before}` | Expose the diff of two revisions as the DuckDB schema `manta.<name>` ([changes between revisions](frontend.md#3-changes-between-revisions)). By default `after` is a reference's current revision and `before` the fork point with its base reference. `after` and `before` are revision ids, both required. The BE resolves the reference and its fork point to them before the call ([routes and Quack relay](backend.md#5-routes-and-quack-relay)). Later `after` can name a registration of the kind `edit`, with its base revision as `before` ([working records](#6-working-records)). |
| `POST /summaries` | `{store, after, before}` | Compute the change summary of two revision ids and answer it as JSON. By default `after` is a reference's current revision and `before` the fork point with its base reference; the BE resolves both ([changes between revisions](frontend.md#3-changes-between-revisions)). Registers nothing. |
| `GET /registrations` | | The registered names. |
| `GET /registrations/{name}` | | The manifest and view list of one registration. |
| `DELETE /registrations/{name}` | | Unregister. |
| `POST /commits` | claim, write credential, changeset | Apply the changeset to a WR on the claim's parent, then commit ([commit flow](storage-commit.md#1-commit-flow)). |
| `PUT /credentials` | read credential | Replace an expiring read credential with `Workspace.set_credentials` (F12). |
| later: `PUT /registrations/{name}` | `{kind: "edit", store, revision}` | Open a WR on the revision and register it ([working records](#6-working-records)). |
| later: `POST /registrations/{name}/edits` | operation list ([changeset format](storage-commit.md#3-changeset-format)) | Apply edits to a registration of the kind `edit` ([working records](#6-working-records)). |
| later: `POST /suspend` | | Hook before the BE stops the instance ([working records](#6-working-records), [session lifetime](backend.md#3-session-lifetime)). |

The `kind` of a registration is the same value that the BE stores in its `datarecord_session_registrations` row: `view`, `diff`, and later `edit`. A registration is a revision of a store that the FE asked to access. When the datarecord session wakes from suspend, `ensure_datarecord_session` replays the registrations to rebuild it. The FE removes a registration by unregistering. The registrations are not an audit log.

### Rules

- The session accepts store names, never URIs. It joins a name to its fixed root. It refuses a name with `/` or `..`.
- The BE's public routes name a store the same way (`/v1/projects/{id}/datarecord-stores/{store}`). The run API of the storage grants takes the full URL `s3://<bucket>/<project>/<store>` (F25). Both resolve to that one form.
- Quack is read-only. Every write goes through the HTTP API.
- One thread owns the DR workspace objects (F14). API calls queue onto that thread.
- The session passes its read credential to DR as `S3Credentials`, with `url_style="path"` and the endpoint as scheme, host and port (F12).
- The session sets no `AWS_*` variable and creates no other S3 secret on the connection. Another unscoped S3 secret can win over DR's.

## 4. Names in DuckDB

The session uses one catalog, named `manta`. It is the database that DR's `Workspace(con=..., name="manta")` attaches on the connection that Quack serves. The session attaches no other database. Every registration, view pack and diff is a DuckDB schema inside this catalog. The connection's default catalog `memory` stays empty.

Today's quack-server works differently. It attaches one catalog per scenario ([where the quack-server functions move](appendix.md#9-where-the-quack-server-functions-move)). Its DuckDB schema `manta` goes away ([replacing the manta objects](#5-replacing-the-manta-objects)). Only the catalog carries that name.

Placeholders in the table: `<name>` is a registration name, `<pack>` a view pack (`pypsa-eur`), `<d>` a dimension, `<A>` an attribute, `<hex>` the 32-digit hex of a revision's or layer's UUID.

| Object | Fully qualified name | Named by |
|---|---|---|
| The catalog | `manta` | the session, as `Workspace(name=...)` |
| Dimension labels of a registered revision | `manta.<name>.dimensions.<d>` | `<name>`: the session; the rest: DR |
| Properties of a registered revision | `manta.<name>.properties.<subject>` | as above |
| Attributes of a registered revision | `manta.<name>.attributes.<A>` | as above |
| Owner map of a registration | `manta.<name>.owner_map` | DR (PR 149) |
| Group A views of a pack ([replacing the manta objects](#5-replacing-the-manta-objects)) | `manta.<name>."pypsa-eur".bus_location`, ... | the session |
| Constant values ([constant values](frontend.md#2-constant-values-and-the-owner-map)) | `manta.<name>.static_<dtype>` | the session |
| Working record registration ([working records](#6-working-records)) | `manta.<name>.dimensions.<d>`, `.properties.<subject>`, `.attributes.<A>`, `.owner_map`, as for a revision | as for a revision |
| Diff registration ([changes between revisions](frontend.md#3-changes-between-revisions)) | `manta.<name>.map_rows`, `manta.<name>.static_<dtype>`, `manta.<name>.series_<dtype>` | the session, every part |
| DR's own tables | `manta.main.registered`, `manta.main.revisions`, `manta.main.schemas` | DR |
| Fold of a revision | `manta._fold.<hex>.owner_map`, `.dimension_owners`, `.dimensions_<d>` | DR |
| Staging tables of a WR | `manta._staged.<hex>.<table>` | DR |

Short forms in this plan (`attributes.<A>`, `static_<dtype>`) stand for the full names above.

### Facts behind the layout

These facts were measured on DuckDB 2.0.0 and DR main. The names are those of the DR stack. The behaviour was not run again on the stack.

What DR creates:

- `register(name)` creates the DuckDB schema `manta.<name>`. Inside it are the nested DuckDB schemas `dimensions`, `properties` and `attributes`, and the view `owner_map`. It also adds a row to `manta.main.registered`.
- The fold tables stay in `manta._fold.<hex>`.
- `unregister(name)` drops `manta.<name>` with `CASCADE`.

What the session may add, and how:

- The session must not create an object named `owner_map` in a registration.
- The session can create DuckDB schemas and views below a registration, also several levels deep.
- `unregister(name)` drops these objects too, and does not fail. The session needs no cleanup of its own for packs. It adds them again after each `register`.
- DR does not document this behaviour. The session relies on it with a pinned DR version.
- A diff's DuckDB schema is the session's own and is not in `registered()`. `unregister` refuses it. The session drops it with `DROP SCHEMA manta.<name> CASCADE`.
- Names cannot collide. `register` fails on a name that the session already used for a diff. The session's `CREATE SCHEMA` fails on a registered name.
- The session must not use `CREATE SCHEMA IF NOT EXISTS`. It passes on an existing name without an error.

How names bind in SQL:

- A registration name is one DuckDB schema, not a path. `register("a.b")` creates one DuckDB schema named `a.b`, which SQL must quote. The unquoted `manta.a.b.attributes.p_nom` does not bind.
- A name such as `patch/perfect` works when quoted.
- Proposed, not yet fixed: the session refuses `.` in a registration name.
- A four-part name binds from any cursor of the connection.
- A three-part name (`r1.attributes.p_nom`) binds only after `USE manta`. The FE never runs `USE`, so it always uses four-part names.
- A view that reads `manta.<name>` from outside it fails after `unregister(name)`. It works again after the next `register(name)`.

What catalog functions and parsers report:

- `duckdb_views()` and `information_schema` report only the leaf DuckDB schema of a view (`attributes`).
- `duckdb_schemas()` has a column `parent_schema`. It names the DuckDB schema one level up.
- DuckDB's parser reports `dr.reg1.attributes.a` with the legacy fields `catalog` = `dr`, `schema` = `attributes`, `table` = `a`. Only `qualified_name.path` holds the full path (other spike).
- A tool that reads only these three fields loses the registration name. For this reason `quack-oauth` cannot express a rule per registration today (S7).

### What changes in the FE

Today the FE prefixes every view with the catalog of the active scenario: `serverName` in `client.ts:239-241`, and `at(catalog, ...)` in `entityPage.ts:48` and `componentPage.ts:204`. The catalog name comes from the server's open response (`revision.catalog`). A scenario switch only changes that prefix (`recordSlice.ts:31`). No query runs `USE`.

In the target the prefix is `manta.<name>`. The FE takes it from the answer of the registration call and does not build it itself. Group A views move from `manta.<view>` to `<prefix>.<pack>.<view>`.

## 5. Replacing the manta objects

Decision D4 covers these objects. Today quack-server attaches one catalog per scenario. It adds a fourth DuckDB schema `manta` to each, beside `dims`, `properties` and `attributes`. This DuckDB schema holds ten objects of three different natures.

In the target there is one catalog and no DuckDB schema `manta`. The names of the new objects are in [Names in DuckDB](#4-names-in-duckdb).

| Group | Today | Target |
|---|---|---|
| A | six map and topology views | the view pack `pypsa-eur` |
| B | `attribute_summary`, `ctype_attributes` | the `static_<dtype>` views and the owner map ([constant values and the owner map](frontend.md#2-constant-values-and-the-owner-map)) |
| C | `revisions` | the BE's revision listing ([revisions](backend-mvp.md#5-revisions)) |
| C | `scenario_changes` | a change summary of a reference against the fork point with its base reference, computed on request, and diff registrations of the same two revisions ([changes between revisions](frontend.md#3-changes-between-revisions)) |

### Group A: map and topology views

The six views are plain SELECT statements over `properties.*` and `attributes.*`. They encode PyPSA-Eur conventions.

| View | Content | Convention it hard-codes |
|---|---|---|
| `bus_location` | bus, carrier, location, x, y, `virtual` | bus property `location`; location `EU` is virtual |
| `locations` | one map point per real location, with bus count and carriers | as above |
| `location_zones` | level, location, zone; one branch per `busmap_*` attribute | attribute prefix `busmap_`; location name equals AC bus name |
| `branches` | entity, ctype, carrier, both buses and locations, `scope` (`within`, `between`, `virtual`) | the join over `connection` and `role` is generic PyPSA; `scope` is PyPSA-Eur |
| `attached` | generators, loads, stores at their bus and location | role `attached`; location columns |
| `regions` | region polygons as WKT | ctype `Shape`, attributes `geometry`, `component`, `idx` |

The FE uses all six: map points, map lines, zone levels, entity location, location graph, region polygons. Two of them (`location_zones`, `regions`) have SQL text that depends on which attributes exist.

In the target, group A becomes view packs, named by convention set:

- A *view pack* is a set of SQL templates in the session.
- The session adds a pack below a registered revision when the registration asks for it (`packs: ["pypsa-eur"]`).
- The pack `pypsa-eur` becomes the DuckDB schema `manta.<name>."pypsa-eur"`.
- The code of the six views moves as is.
- The FE cannot own the views cleanly. Two views need the attribute list, and every page would repeat the SQL.

Open: who owns a convention set. It must match between the playbooks that write the data, the session and the FE.

### Group B: summary objects

| Object | Content | Note |
|---|---|---|
| `attribute_summary` (table) | per attribute and subject: the constant value, and the number of series rows | One full scan over every attribute, done once at open and stored. It feeds the entity tables and the attribute panel. The subject order (`entity`, `connection`, `bus`, ...) is PyPSA-flavoured. |
| `ctype_attributes` (view) | which attributes each component type really stores | A view over `attribute_summary`. |

In the target, group B is not a prepared table. No full scan runs beyond the fold. The `static_<dtype>` views and the owner map replace both objects. Detail in [constant values and the owner map](frontend.md#2-constant-values-and-the-owner-map). The `static` views follow the shape of the pinned DR (D18, D19).

### Group C: revision objects

| Object | Content | Note |
|---|---|---|
| `revisions` (table) | name, id, parent, kind, label, description | |
| `scenario_changes` (table) | per scenario, attribute and subject: before, after, changed series rows, median ratio | A FULL JOIN of the attribute in the revision and in its parent, keeping rows whose value differs. Restated but unchanged values do not count. Built for all scenarios at open. |

In the target:

- `revisions` moves to the BE. The BE lists revisions with DR and references from `store.json` ([revisions](backend-mvp.md#5-revisions)). It is gone from the session.
- `scenario_changes` is not per registration and not per revision. Its unit is a pair of revisions. By default the pair is the current revision of a scenario and its fork point with the scenario's base ([changes between revisions](frontend.md#3-changes-between-revisions)).
- `scenario_changes` becomes two things. The first is a change summary per pair. The session computes it at each request (`POST /summaries`); nothing stores it. The second is diff registrations of two revisions.

## 6. Working records

Working records are planned in 1 to 2 months, and they constrain the design now. A WR registered for the FE is state that S3 does not hold. The design keeps the session disposable anyway.

### How a WR lives

- `datarecord_session_registrations` has a `kind` column from the start: `view` (a revision) or `edit` (a WR on a base revision). Diffs add the kind `diff` ([changes between revisions](frontend.md#3-changes-between-revisions)).
- The edit call is a sibling of the registration call. The BE route is `POST .../datarecord-session/registrations/{name}/edits`, with the operation list of the [changeset format](storage-commit.md#3-changeset-format). The BE passes it to the session's `POST /registrations/{name}/edits`.
- Every edit passes the BE. The BE appends it to an *edit log* of that WR. The log holds the operation list in Postgres and the table payloads in S3 under a session prefix.
- The log is kept in full until the commit (D9). No draft revision is written, so nothing has to be squashed.
- To watch: the storage cost of large table payloads in a long log.

### Restore

1. Start an instance.
2. Register the views.
3. Open the WR.
4. Replay the log.

The same path covers a crash.

### Commit

The commit is the [commit flow](storage-commit.md#1-commit-flow), with the live WR instead of a fresh one.

1. The FE asks the BE.
2. The BE claims, mints the token, and calls the session with the name of the WR.
3. The session commits.
4. The BE clears the log. The WR is registered again on the new revision.

### Suspension

The session does not flush the WR to a draft revision when the BE asks it to suspend. With a flush, a crash would lose the edits, and drafts would need a squash. The edit log covers both cases instead.

### What must hold now

So that WRs fit later, these rules hold from the start:

1. Edits are a serialisable, ordered, deterministic operation list ([changeset format](storage-commit.md#3-changeset-format)).
2. Every write passes the BE.
3. Registration rows carry a kind.
4. Suspension is a decision of the BE with a hook (`POST /suspend`), not only a kill.
5. One thread owns the DR objects.

## 7. Open points

- Dots in registration names: should the session refuse `.`? Proposal: yes, refuse it.
- Owner of a convention set (view pack): who owns it so that playbooks, session and FE match? Proposal: none yet.
- Layout facts on the DR stack: do they still hold on the pinned DR? Proposal: run `catalog-check` again on the pin.
- Edit log size: what does a long log with large table payloads cost in storage? Proposal: watch it after WRs ship.
