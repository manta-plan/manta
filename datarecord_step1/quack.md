# Step 1: Quack for data-record inspection

Requirements only. **verified** = I ran it (DuckDB 2.0.0 from `datarecord/.venv/bin/python -I`, scratch scripts in
`/tmp/qk`). **read** = from source or docs. S3 was a fake endpoint that logs request headers; no real S3 was touched.
`boto3` is not in that venv, so I ran the SQL of `store.py:163-164` by hand, with the same secret options.

Sources: [Quack announcement](https://duckdb.org/2026/05/12/quack-remote-protocol),
[Quack security](https://duckdb.org/docs/2.0/quack/security.html),
[Quack reference](https://duckdb.org/docs/2.0/quack/reference.html),
[quack extension page](https://duckdb.org/docs/2.0/core_extensions/quack).
The docs have no page I could read on Wasm connection details (CORS, TLS from a browser). See open questions.

## 1. Serving

- A Quack server runs inside any DuckDB process. No separate binary. **verified**
- Minimum, from Python: `con.execute("INSTALL quack; LOAD quack;")` then
  `con.execute("CALL quack_serve('quack:localhost:9494', token='...')")`. It returns at once and the listener runs on
  DuckDB's own threads. The Python process need not block. **verified** (listening socket confirmed with `lsof`).
- The extension downloads on first `INSTALL`. Under `enable_external_access=false` `INSTALL` fails (section 4), so
  install and load before locking. **verified**
- Defaults: bind `localhost`, plain HTTP for local URIs, HTTPS with a self-signed cert otherwise, port 9494. A
  non-local bind needs `allow_other_hostname=true`. Token minimum 4 chars. **read**
  ([reference](https://duckdb.org/docs/2.0/quack/reference.html)).
- Stop: `quack_stop(uri)`. Inspect: `quack_server_list()`, `quack_active_connections()`. **verified**
- Clients attach with `ATTACH 'quack:host:port' AS r (TOKEN '...')`. A bad token fails at ATTACH with
  "Authentication failed". **verified**
- The vendor says to put an nginx or Caddy reverse proxy in front for TLS and not to expose Quack to the internet.
  **read** ([security](https://duckdb.org/docs/2.0/quack/security.html)). A browser on an HTTPS page needs HTTPS
  (mixed content), so TLS termination is a requirement for the frontend, not an option.

## 2. Instance granularity and lifecycle

- Recommendation: **one Quack-serving DuckDB per project**, in its own process, separate from the backend's
  `Workspace.process()`. Reasons below. Not decided; see open questions.
- Why not share one instance across projects. The client sees the whole instance. Secrets, the `revisions`
  table (`store.py:42-49`, `87`: `location` of every store opened in the workspace), and any cached tables are
  shared by everyone connected. **verified** (`SELECT * FROM revisions` works for a client). Caches are keyed by manifest
  id, not location (known fact), so cross-project mixing in one process is also a correctness risk.
- Why not per user or per session. Each instance holds a connection, httpfs, a secret and its caches. Memory scales
  with instances. A project's users all read the same store, so a per-user instance buys nothing the per-project
  token does not.
- Why not inside the FastAPI process. `Workspace.process()` is a singleton (`store.py:99-117`) and S3 config comes
  from the process environment only (`store.py:135-164`). The backend serves every project from one environment.
  Locking the process (section 4) would also lock the backend's own writes and settings.
- Lifecycle, requirements. Something must start the instance on first demand, stop it when idle, and restart it
  after a crash. The backend, as the only party that knows project ownership, must be the one that mints tokens for it.
  Whether that something is the backend, a sidecar or a Prefect-style worker is a design choice.
- Memory: `quack_server_stream_buffer_bytes` defaults to 256 MiB per stream, capped at a quarter of
  `memory_limit`. `max_connections` defaults to 1024. **read** ([reference](https://duckdb.org/docs/2.0/quack/reference.html)).
  `memory_limit` and `threads` must be set per instance and then locked.
- New revisions from playbook runs in other containers. The server instance never sees them on its own.
  `Store.revisions()` and the `revisions` table are workspace-local state, filled when the store is read. What is
  shared is the files in S3. A new revision is a new `revisions/<uuid>.json`, and `manifest.json` holds only the
  schema. (Corrected by the reviewer: the original said the manifest was the shared pointer.) So the server
  needs one of: re-read the manifest on each request, be told by the backend after a run finishes (the backend
  learns it from Prefect), or be restarted. I did not test refresh (no datarecord S3 store available here).
  Frontend need: a way to ask "what is the latest revision" that does not depend on instance age.

## 3. Auth

Existing model, **read**: `authenticated_user` (`auth_service.py:58-67`, `_authenticate` at `:31-55`) decodes a
Keycloak bearer JWT, checks signature, `exp`, `iss`, and loads the `User` by `(sub, iss)`. Run endpoints then
load the project and compare `project.owner_id != user.id`, raising `AuthorizationError`
(`run_service.py:198, 258, 285, 326`). Routes pull the user via `Security(authenticated_user)` (`run_route.py:28-36`).
Quack has no Keycloak awareness; the browser cannot send a bearer header on a Quack connection the way it does
to FastAPI (the protocol takes a `TOKEN` at ATTACH). So a Quack token has to be issued by the backend.

- Token source. A new backend endpoint, behind `authenticated_user`, loads the project, checks
  `owner_id == user.id`, and returns `{url, token}` for that project's instance. Same check as the run endpoints, same
  failure modes (404, then 403). The Quack token is a separate credential from the Keycloak JWT.
- Tie to identity. The token must be unguessable, short-lived and scoped to one project. Store only a hash on the
  server side: a client can read any table the instance has (`SELECT * FROM tok` returned the rows), so a table of
  raw tokens would leak every token. A table of `sha256(token)` is safe against that. **verified**
- Authentication hook: `quack_authentication_function(session_id, client_token, server_token)` returns a boolean.
  The session id becomes the connection id seen by the authorization hook (same 32-char value in both). **verified**
  Wrong or unknown token is rejected at ATTACH. **verified**
- Authorization hook: `quack_authorization_function(connection_id, query)` returns a boolean or a rewritten
  query string. NULL or false denies. **read** ([security](https://duckdb.org/docs/2.0/quack/security.html)).
  I verified deny (`CREATE TABLE` returned "Authorization failed").
- Callbacks can be plain macros (verified) **and can call Python UDFs.** The docs say Python UDFs do not work in
  callbacks. In 2.0.0 with the server in the registering Python process they did: `con.create_function` functions
  behind a macro received `(session_id, token)` and `(connection_id, query)`. **verified**. A Python callback can
  therefore keep a `connection_id -> (user, project, expiry)` map, which macros cannot (macros cannot write).
  That relies on undocumented behaviour. It holds only when the instance is an in-process Python connection.
- If one instance serves one project, the authorization hook needs no per-connection identity, only the
  token table and expiry. A multi-project instance needs the map above.
- Quirks the callbacks must handle. `ATTACH` itself sends catalog-discovery queries (`duckdb_schemas()`,
  `duckdb_tables()`, `duckdb_views()`) through the authorization hook first. **verified** A deny-by-default
  hook has to allow those.
- Expiry and revocation are the backend's job: the hook must check expiry on each query, and a project transfer
  or deletion must revoke. Quack itself has no notion of either. Keycloak token expiry does not propagate.

## 4. Exposure

All of the following were run against a client that held a valid token, instance configuration "open"
(datarecord-style secret, nothing else set), unless noted.

| Reach | Open instance | Stopped by |
|---|---|---|
| `duckdb_secrets()` | Lists the secret, redacted (no key, no secret). **verified** | n/a |
| `duckdb_secrets(redact=false)` | "Displaying unredacted secrets is disabled". **verified** | Default setting |
| Use the secret on other buckets | **Works.** A client `read_parquet('s3://other-bucket/...')` was sent signed with the server's key id. **verified** | Instance config only |
| Other prefixes, same bucket | Same as above. The secret is bucket-wide (Manta's S3 account is one credential). **verified** | Instance config only |
| Local files | `read_csv('/etc/passwd')` read 142 rows, `glob('/etc/*')` listed. **verified** | `enable_external_access=false` or `allowed_directories` |
| `INSTALL`/`LOAD` extensions | `INSTALL json` worked. **verified** | Locked: `INSTALL` denied, `LOAD` of an already-installed extension still works. **verified** |
| `ATTACH` a file | Not tested open (read: allowed). | External access off (denied, **verified**) |
| `COPY ... TO` | Not tested open (read: allowed, so writes wherever the key can). | External access off: denied. Under `allowed_directories`: only the allowed path. **verified** |
| `SET enable_external_access`, `SET memory_limit` | A client turned `enable_external_access=false` on, which breaks the server's own S3 reads | `lock_configuration=true` (denied after). **verified** |
| `CREATE TABLE`, `CREATE TEMP TABLE` | Allowed. Memory pressure by a client. **verified** | Authorization hook, `memory_limit` |
| `CREATE OR REPLACE SECRET` | Allowed even locked. A client can replace datarecord's secret and break reads. **verified** | Authorization hook only |
| `quack_stop(uri)`, `quack_serve(...)`, `quack_active_connections()` | Callable as a plain `SELECT`. See below. **verified** | Authorization hook only |

Things I did not expect:

- **A client can start its own Quack listener.** `SELECT * FROM quack_serve('quack:0.0.0.0:9595',
  allow_other_hostname=true, disable_ssl=true, token='x')` succeeded and opened a socket on all interfaces, even
  with external access off and configuration locked. **verified**. Without `disable_ssl` it failed under the lock
  (it tries to write a cert to `~/.duckdb`). It also stops the real server: `quack_stop` succeeded. **verified**
- **`allowed_directories` on S3 does not stop `..`.** With `allowed_directories=['s3://bucket/projA/']` and
  external access off, `s3://bucket/projA/../projB/a.parquet` passed the check and a `HEAD /bucket/projB/a.parquet`
  reached the endpoint. Both `read_parquet` and `glob`. **verified**. Local paths are not affected: `/tmp/qk/allowed/../../../etc/passwd`
  was denied. **verified**. Prefix `s3://bucket/projA-evil/` was denied, so it is a path-normalisation gap,
  not a prefix-matching one. Whether an S3 server (SeaweedFS) normalises `..` is untested; the allow-list is not a
  boundary on its own.
- Other clients' queries are visible. `quack_active_connections()` returns every connection's id and current
  query. **verified**
- `getenv()` does not exist in 2.0.0 SQL, so the process environment is not readable that way. **verified**

What the authorization hook can do. A `SELECT`-only check works as a macro:
`json_serialize_sql(q)` errors on non-SELECT statements. A macro returning `q` when
`json_extract(json_serialize_sql(q), '$.error')` is not true blocked `CREATE TABLE` and
`WITH a AS (SELECT 1) INSERT INTO tok ...` (the bypass the docs warn a prefix regex allows). **verified**
That is insufficient: every row in the table above marked "authorization hook" is a `SELECT` or a table function,
and `read_csv`, `quack_stop` and `duckdb_secrets()` are all `SELECT`s. A hook needs a function allowlist, and a regex on the
query text is not one. I did not build one. A hook that walks the parsed AST (`json_serialize_sql` output) in a Python callback could allowlist functions
and tables. Untested.

Read-only mode. The vendor's recommendation is a read-only ATTACH (**read**), which applies to a database file.
datarecord's workspace is `:memory:` and is written by datarecord itself (the `revisions` table,
`store.py:87`; `WorkingRecord` tables, `mutable.py:678`). There is no instance-wide read-only setting I
could find. Read-only is therefore authorization-hook-enforced (SELECT-only plus function allowlist) on top of
instance config, not a database mode. **Not fully enforceable by config alone.**

What `enable_external_access=false` breaks for datarecord. **verified** on the server side:
- `CREATE OR REPLACE SECRET (... PROVIDER credential_chain)` is denied. `_connect_remote` (`store.py:163-164`) must
  run before the lock. So must `INSTALL httpfs`: it is denied after.
- With `allowed_directories` set to the project's `s3://` prefix and the project's local path, datarecord's own
  `read_parquet` and `glob` reached the S3 endpoint and local files; other prefixes and paths were denied. So
  datarecord reads work under `allowed_directories`, subject to the `..` gap above.
- Plain `enable_external_access=false` with no allow-list blocks all file and S3 reads, so it is unusable for an
  instance that has to read the store.

## Requirements

1. Each Quack-serving instance serves exactly one project's store, so secrets, `revisions`, caches and tokens never span projects.
2. The instance does not share a process with `Workspace.process()` of the backend, or any process that writes.
3. Order of setup: install and load `quack` and `httpfs`, create the S3 secret (`_connect_remote`), open the store,
   call `quack_serve`, then set `allowed_directories`, `enable_external_access=false`, `memory_limit`, `threads`, then
   `lock_configuration=true`. `quack_serve` fails after the lock, because it reads `~/.duckdb/stored_secrets`.
   **verified** (by the reviewer)
4. The S3 credential on that instance is scoped to the project's prefix at the storage layer (SeaweedFS identity or policy), since a client can use it on any key the credential permits. `allowed_directories` is not a substitute (`..` gap).
5. A backend endpoint behind `authenticated_user` checks `project.owner_id == user.id` (same as `run_service.py:198`) and returns `{url, token}`.
6. Tokens are random, per session, expiring, and held server-side only as hashes.
7. The authentication hook accepts only a live token. The authorization hook checks expiry on every query.
8. The authorization hook denies by default: SELECT only, a function allowlist that excludes `quack_*`, `read_*`, `glob`, `duckdb_secrets`, `query`, and every statement that is not a SELECT. It must pass the catalog-discovery queries ATTACH sends.
9. The listener is TLS-terminated by a reverse proxy; the instance binds loopback only; the browser reaches the proxy over HTTPS.
10. The instance learns of revisions written by other containers, by a mechanism chosen in step 2.
11. Idle and crash handling for instances: start on demand, stop when idle, restart on failure, revoke tokens on stop.
12. Per-connection and per-query limits (`quack_server_max_connections`, `memory_limit`, `threads`) set to values chosen from load, not defaults.

## Open questions

- Granularity: one instance per project (recommended) versus one per user or session. Cost is memory per instance.
- Who starts, stops and restarts instances: the backend, a sidecar, or a worker. Recommend a sidecar, so the backend is not locked.
- Revision freshness: re-read manifest per request, push from the backend, or restart. Recommend push on run completion.
- Authorization hook: Python UDF callbacks (works in 2.0.0, undocumented, in-process only) versus a C/Rust extension (documented, heavier). Recommend Python for now, with a test pinning the behaviour.
- Is a S3 credential scoped per project available in SeaweedFS in this deployment? Without it, requirement 4 fails.
- Does SeaweedFS resolve `..` in object keys? Untested.
- Browser to Quack: CORS and certificate handling from DuckDB-Wasm. The docs I could read are silent. Needs a test against a real browser.
- Token lifetime and who revokes on project transfer.
- Whether the first client may be given write (the backend writes through the Python process, not Quack); recommend no write at all.
