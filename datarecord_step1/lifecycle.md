# Quack deployment: per-project instances, started on demand

Design conclusions and open items from the discussion following `quack.md` and `quack-issue-1..5.md`. Read those first.

Evidence tags: **verified** = run on DuckDB 2.0.0 (`datarecord/.venv/bin/python -I`). **read** = from docs or source.
**reasoned** = my inference, not tested. **untested** = named, not tried.

Sources: [Quack security](https://duckdb.org/docs/2.0/quack/security.html),
[Securing DuckDB](https://duckdb.org/docs/2.0/operations_manual/securing_duckdb/overview.html),
[Quack reference](https://duckdb.org/docs/2.0/quack/reference.html).

## 1. Decisions reached

1. **DuckDB has no users, roles or grants.** `CREATE USER`, `CREATE ROLE`, `GRANT` and `CREATE POLICY` all fail with
   parser errors in 2.0.0. **verified**. The `user`/`username` settings are "Kept for legacy compatibility". **verified**.
   The Quack security page lists only a shared token plus custom authentication and authorization callbacks. **read**.
   "Per-user permissions" therefore means a token table plus hooks, not a DuckDB feature.
2. **One instance per project, not one shared instance.** A shared instance puts every tenant behind one hook, one
   global `allowed_directories` and one S3 credential. Issues 1 to 4 are owner-versus-other-tenants problems, so
   single ownership of a project does not reduce them. A shared instance also makes `revisions` and `quack_cancel`
   cross-tenant (issue 5).
3. **Not one instance per user.** It would need a per-user storage policy updated on every project create, transfer
   and delete, and leaves the cache-keyed-by-manifest-id risk from `quack.md` section 2. **reasoned**
4. **Because a project has one owner, the per-user layer collapses.** A per-project token is a per-user token, and
   issue 5 shrinks to self-disclosure. Use one session token per attach: random, hashed server-side, expiring, scoped to
   the project. Keep a `user_id` column in the token table so project sharing later is not a schema change.
5. **DuckDB offers no in-process isolation, so sandbox outside it.** The securing guide says SQL runs with the full
   privileges of the process and that its settings are defense-in-depth. **read**. Run each instance in its own
   container with only the proxy port published and egress limited to the S3 endpoint. Expected effects: a rogue
   listener (issue 1) is unreachable from outside, and the `..` gap (issue 3) is moot when the credential is
   prefix-scoped. **reasoned**
6. **The authorization hook stays required.** Secrets (issue 4), `quack_stop` and `quack_serve` (issue 1) are reachable
   from inside the instance regardless of the container. The container limits what a hook failure costs.
7. **The backend does not hold the container runtime.** It is the internet-facing component. The repo already puts
   Docker-daemon access in the `runner` package (`docker/runner-image.Dockerfile`). The backend asks the runner for an
   instance, the runner starts it and returns the internal address, and the backend mints the token and returns
   `{url, token}`.

## 2. DuckDB isolation settings on offer

| Mechanism | Covers | Gap |
|---|---|---|
| `enable_external_access=false`, `allowed_directories`, `allowed_paths`, `disabled_filesystems` | Local file reads, `INSTALL`, `COPY`, file `ATTACH` | `..` on S3 paths (issue 3). `quack_serve` still works (issue 1). |
| `lock_configuration`, `allowed_configs` | `SET` | Secrets and `quack_*` (issues 1, 4) |
| `memory_limit`, `threads`, `max_temp_directory_size`, `operator_memory_limit` | Resource use | Not presented as DoS protection |
| `autoload/autoinstall_known_extensions`, `allow_community_extensions`, `allow_unsigned_extensions` | Extension loading | No effect on secrets (issue 4) |
| `allow_persistent_secrets=false`, `allow_unredacted_secrets` | Secret persistence and disclosure | Temporary secrets still work; the client does not need the values (issue 2) |
| `ATTACH ... READ_ONLY`, `access_mode` | Writes to an attached database file | datarecord's workspace is `:memory:` and written by datarecord, so not applicable |
| Quack authentication and authorization hooks | Whatever a function can express over session and query text | The allowlist is ours to write |

Not tested: `disabled_filesystems`, `allowed_paths`, `allowed_configs`, `extension_directories`, `home_directory`.

## 3. Lifecycle requirements

Extends `quack.md` requirements 1 to 12.

1. The backend resolves the project, checks `project.owner_id == user.id`, then requests an instance from the runner.
2. The runner starts the instance in an isolated container with a per-project S3 credential, applies the setup order in
   `quack.md` requirement 3, and returns an internal address.
3. The backend mints the session token, ensures the instance holds only its hash, and returns `{url, token}`.
4. Idle instances are stopped. Stopping an instance revokes its tokens.
5. A crashed instance is restarted on the next request, never silently, and its tokens are re-issued or re-checked.
6. New revisions (run completion, FE edits) are announced to a running instance. A stopped instance re-reads on start.
7. The frontend flow has a "starting" state; attach is not a blocking call on cold start.

## 4. Open items

Numbered for answering. Items marked (blocking) gate the design.

1. **Browser to Quack over HTTPS (blocking).** Can DuckDB-Wasm attach through the TLS proxy: CORS, certificates, mixed
   content? The docs I could read are silent. Needs a test in a real browser before lifecycle work.
2. **Per-project S3 credential (blocking).** Does SeaweedFS here support per-identity prefix policies, and can the
   runner issue one per instance? Without it, the isolation rests on the hook and the container alone.
3. **Token handoff.** How does the instance learn the token hash without the client seeing it? The backend-to-instance
   channel is the same `quack_*` surface as issue 1, so it must be unreachable from clients (separate loopback or unix
   socket, or hash passed at start).
4. **Who owns the lifecycle.** Does the runner's worker model host a long-lived service, or does this need a new
   sidecar? Not checked.
5. **Idle detection.** Poll `quack_server_list()` and `quack_active_connections()` from the runner or the backend? What
   idle timeout, and is it tied to token expiry?
6. **Cold start.** How long does container start, store open and secret creation take? Not measured.
7. **Revision push.** Mechanism for telling a running instance about new revisions. `quack.md` recommends push on run
   completion. Not tested.
8. **Hook mechanism.** Python callbacks (work in 2.0.0, undocumented, in-process only) versus a C/Rust extension
   (documented, heavier). With one project per instance the hook needs no session map, but the function allowlist may
   still need Python. An AST allowlist built on `json_serialize_sql` is **untested**.
9. **`quack_cancel`.** It never reaches the hook (issue 5). Is it unreachable if connection ids are unguessable and
   `quack_active_connections()` is denied? Can a client reuse another connection's id toward the hook? Both untested.
10. **Does SeaweedFS resolve `..` in object keys?** Probably moot for object reads, since DuckDB collapses `..`
    client-side. **verified** (issue 3). Matters only for `glob` prefixes. Untested.
11. **Does `scope` secret matching see `s3://bucket/projA/../projB/x`?** Untested (issue 2).
12. **Container claims.** The effects in decision 5 are reasoned, not tested: rogue listener unreachable, egress limit
    works with httpfs.
13. **Token lifetime and revocation.** What lifetime, and who revokes on project transfer or deletion? Neither exists
    in the backend today (`project_route.py` has create only).
14. **Write access.** `quack.md` recommends none; the backend writes through its own process. Confirm.
15. **Instance limits.** Values for `memory_limit`, `threads`, `quack_server_max_connections`,
    `quack_server_stream_buffer_bytes`, chosen from load and not defaults.
16. **`quack_generate_keys(directory)`.** Exists in 2.0.0. Not tested; may relate to TLS certificates, not client keys.
17. **Upstream.** Whether to file the issue 1, 3 and 4 findings. None filed.
