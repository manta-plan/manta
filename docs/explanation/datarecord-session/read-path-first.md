<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Work plan: read path first

This page describes the part of the datarecord-session plan that the team builds in the week of 2026-11-23, and what it postpones. Start with the [overview](index.md). The codes F, S, D and I point to the [appendix](appendix.md).

The week delivers the session and the read path: a user opens a project, registers a revision and queries it over Quack. Nothing writes to a store. The pentest on 2026-11-27 then tests a session per user and project in place of `docker/quack-server`, with its one shared token ([#322](https://github.com/manta-plan/manta/issues/322)).

## 1. Scope

The week covers flows 3, 4, 5 and 8 of the overview, and flow 3 only as a read. Postgres gains two tables: `datarecord_sessions` and `datarecord_session_registrations` ([session tables](backend.md#session-tables)).

| Part | In this week | Postponed |
|---|---|---|
| Session service | Start-up, Quack, SQL guard, `GET /health`, `PUT`, `GET` and `DELETE /registrations/{name}` of the kind `view`, view packs | `POST /commits`, `POST /summaries`, registrations of the kinds `diff` and `edit`, `PUT /credentials`, `POST /suspend` |
| BE session routes | `POST` and `DELETE .../datarecord-session`, the three registration routes, `GET /v1/datarecord-session/quack-auth` | `.../datarecord-session/changes`, `.../datarecord-session/heartbeat` |
| BE store routes | `GET .../datarecord-stores`, `GET .../datarecord-stores/{store}/datarecord-revisions` | `POST .../datarecord-revisions`, and the `POST`, `PATCH` and `DELETE` routes of `datarecord-references` |
| Session management | The two tables, the Docker launcher, `ensure_datarecord_session` with replay, one forced stop after 60 minutes, removal of orphans | The idle stage with a session cap, presence, the exemption for unsaved edits |
| Caddy | The `/quack` route with `forward_auth` ([Quack auth check](backend.md#quack-auth-check)) | |
| FE | Session client, registration, attach, queries with the SQL prefix | Diff views, commit of edits, settling of edits |
| Storage | The global S3 credential, passed to each session by the launcher | The read token for the project's folder, the write token per layer, the conditional write of `store.json` |

Three things make this cut cheap:

- The BE writes nothing to S3. So the week does not wait for the `If-Match` test on SeaweedFS ([open next](appendix.md#3-open-next), step 7), nor for the claim and the write token.
- `store.json` and the manifests stay as the plan describes them. The postponed routes read and write the same files, so the week builds nothing that the commit path replaces.
- A registration of the kind `view` needs only a store name and a revision id. The fork point, and with it `Revision.ancestry()`, comes with the diff registrations.

## 2. Preconditions

These must hold on Monday, or the first work package waits.

1. Manta pins the tip of the DR stack (D19). The stack is not merged (I11), so the pin is a commit hash on a branch.
2. The test stores are exported again with the stack's DR, with `store.json` and `meta` as in `2026-11-13/` (I9, F30). No existing store opens with the stack.
3. The BE container can reach the Docker daemon in the deployment ([#276](https://github.com/manta-plan/manta/issues/276)), and the image runs Caddy 2.11 or later (S8).

## 3. Work packages

| # | Package | Depends on | Done when |
|---|---|---|---|
| W1 | Session service. The package `datarecord-session/` with start-up, Quack, the guard moved from `docker/quack-server`, the internal registration API and the `pypsa-eur` view pack. One fixed instance in compose. | preconditions 1 and 2 | A native Quack client reads `manta.<name>.attributes.p_nom` of a registered revision. A statement other than SELECT is refused. |
| W2 | BE store and revision listings. The two `GET` routes over an S3 listing, DR and `store.json`. | preconditions 1 and 2 | The listing of a test store shows its revisions and references. No route starts a session. |
| W3 | BE sessions. The two tables with a migration, the Docker launcher, `ensure_datarecord_session`, and the open, suspend and registration routes. | W1 | Two users of one project get two containers. A registration survives `DELETE .../datarecord-session` and the next request. |
| W4 | Quack auth check. The `quack-auth` route, the `/quack` route in `frontend/Caddyfile`, and a network that Caddy shares with the session containers. | W3 | A query with a valid token reaches the user's own container. A bad token gets 401, a foreign project 403, and a spoofed `X-Session-Upstream` changes nothing. |
| W5 | Lifetime. A BE task stops a session after 60 minutes without activity and stops labelled containers without an active row. | W3 | A session that is not used stops, and the next query starts it again. |
| W6 | FE. The record client ported from `baby-manta` to the BE routes: open the session, register, attach, re-attach after `Invalid connection id` (S4). | W2, W4 | The app shows a registered revision from a session behind Caddy. The `SELECT 1` keep-alive is gone. |
| W7 | Switch. Compose and the deployment start no `docker/quack-server`. | W4, W6 | The pentest deployment has no route to the temporary server. |

## 4. Pull requests

The backend work lands as a stack of four pull requests. Each one builds on the one before it and is reviewed alone. The listings of W2 touch no session code, so they are a pull request of their own on `main`.

| # | Pull request | Packages | Base | What a reviewer can run |
|---|---|---|---|---|
| 1 | The session service: the package `datarecord-session/`, its image and one fixed instance in compose | W1 | `main` | The service alone, with a native Quack client. `docker/quack-server` still serves the app. |
| 2 | BE sessions: the two tables with a migration, the launcher interface with the Docker implementation, `ensure_datarecord_session`, the open, suspend and registration routes | W3 | 1 | The routes with the BE's tests. A container starts per user and project, and a registration is replayed. |
| 3 | The Quack auth check: the `quack-auth` route, the `/quack` route in `frontend/Caddyfile`, the shared network | W4 | 2 | A query from a native client through Caddy to the user's own container. |
| 4 | Lifetime: the forced stop and the removal of orphans | W5 | 3 | A session that stops after the limit and comes back on the next query. |
| | The store and revision listings | W2 | `main` | The two `GET` routes on a test store. |

The stack merges from the bottom. Pull request 1 adds a service that nothing calls, and pull requests 2 to 4 add routes that the FE does not use yet. So each one can merge to `main` when its review is done, and none waits for the FE.

The FE port (W6) and the switch (W7) follow as two more pull requests on top of pull request 4 and the listings. The size of W6 is not known yet.

The three browser checks of the [Quack auth check](backend.md#quack-auth-check) belong to W6: the headers of the Quack secret reach Caddy from WASM (I3), a refreshed Keycloak token reaches later requests, and a real DuckDB-WASM client works through Caddy.

## 5. Risks

- The headers of the Quack secret may not arrive from WASM (I3). The fallback puts the BE back in the data path and costs about a day. So this check runs as soon as pull request 3 serves a query through Caddy.
- Each session holds the global S3 credential this week (I1). A token that reads only the project's folder needs STS on SeaweedFS 4.53, and `main` runs 4.05 without code that mints tokens. So only the SQL guard stands between a user's query and other projects (I2), and the pentest must know this. One BE function returns the credential for a project, so the scoped token replaces it later without a change to the session.
- `POST /v1/auth/register` is unauthenticated (I5, [#273](https://github.com/manta-plan/manta/issues/273)). With W3 any registered identity can start containers. The fix must land before the pentest deployment, or W3 needs a low cap on running sessions.
- The DR stack can still change under the pin (I11). The pin moves only when a work package needs a fix.

## 6. What follows

The postponed parts keep their place in the [phases](appendix.md#4-phases).

1. The reference routes and the conditional write of `store.json`, the rest of phase 2.
2. Diff registrations and the change summary, with the fork point ([changes between revisions](frontend.md#3-changes-between-revisions)).
3. The commit path, phase 6: claim, write token, changeset ([commit flow](storage-commit.md#1-commit-flow)).
4. The read token for the project's folder, with `PUT /credentials` to renew it ([the two tokens](storage-commit.md#2-the-two-tokens)).
5. The idle stage and presence ([session lifetime](backend.md#3-session-lifetime)).
6. Removal of `docker/quack-server`, phase 7.

After this week the team can judge the session, the launcher and the Quack path on a running system, before the write path adds claims and tokens to them.
