# Step 1 summary

Items 1 to 6 are done. Item 7 (format freeze) is yours to decide; item 8 (verification) comes after this.
Detail: `playbook.md` (items 1-3), `backend.md` (4, 6), `quack.md`, `quack-issue-1..5.md`, `lifecycle.md` (5).
Findings are the agents' reports, tagged verified or read there. I re-ran only the DuckDB no-grants check.

## What we learned

- **Handle.** Replace `DataRecord{url}` with `RevisionRef{id, parent, store}`. The orchestrator imports no datarecord and holds no S3 credentials.
- **Block output.** `input.child(edits)`. `output_base` / `output_prefix` go away.
- **PyPSA blocks.** Writing the whole network as a layer is wrong, not just big: a child overlays its parent, so removed components and resampled snapshots come back. Solve blocks stage edits natively (`WorkingRecord`, 587 B instead of 17.8 kB on the example). Blocks that restructure the network need a differ (~70 lines).
- **Backend.** The store is the truth for tree and data; the DB holds provenance and naming. One store per project at `s3://{bucket}/{project_uuid}/datarecord`, created at the first root.
- **FE edits.** The FE sends `base` plus an ordered op list. The backend stages and writes `base.child(edits)` in one request. A stale base branches by default.
- **Quack.** One instance per project, in a container, started by the runner and not the backend. One expiring session token per attach. DuckDB has no users or grants (parser errors in 2.0.0), so per-user control is a hook.

## Blockers upstream in datarecord (verified)

- `to_datarecord` fails on a multi-period network, which blocks `myopic`.
- Snapshot weightings are dropped, which breaks `cluster_time` and every solve after it.
- `PyPSA.build` doesn't restore results (`p_nom_opt` reads 0.0), so dispatch must read capacities from the outputs.

## Key vulnerabilities

All verified on DuckDB 2.0.0 unless noted. A token holder is the attacker; none is fixed by DuckDB config alone.

| # | Issue | Why it matters |
|---|---|---|
| 1 | Any client can call `quack_serve` and `quack_stop`, despite `lock_configuration` and `enable_external_access=false` | Rogue listener on `0.0.0.0` with an attacker-chosen token, bypassing the TLS proxy and outliving revocation. Also kills the real server. |
| 2 | The server's S3 secret signs any bucket or prefix the key permits | Project A's client reads project B. One credential serves every project today. |
| 3 | `allowed_directories` doesn't resolve `..` on S3 paths | The allow-list is not a boundary. DuckDB core, 1.5.5 and 2.0.0. |
| 4 | `CREATE` / `DROP SECRET` pass the lock | A client secret with a longer `SCOPE` redirects the server's own S3 reads. |
| 5 | Clients see all connections' queries, read internal tables (`revisions`, token tables) and cancel others' queries | `quack_cancel` never reaches the hook. Self-disclosure only while a project has one owner. |
| 6 | `run_request.data_record_url` is a free S3 URL (`run_request.py:22`) | A run can read another project's store. Read from source, not run. |

Mitigation, in layers: per-project S3 credential scoped at the storage layer; an authorization hook that denies by default (SELECT-only plus a function allowlist, untested beyond SELECT-only); a container with one published port and egress limited to S3; loopback bind behind a TLS proxy. For #6, the request carries a revision uuid and the backend builds the handle.

## Decisions for you

Recommendation in brackets. **Blocking** items gate the design.

**Blocking**
1. Can DuckDB-Wasm attach to Quack over HTTPS (CORS, certificates)? Docs are silent. Test in a browser first.
2. Does SeaweedFS support a per-project prefix-scoped credential? Without it, isolation rests on the hook and container.
3. Who fixes the multi-period write and weighting loss, and does the tracer bullet wait? Is the objective needed per revision?

**Playbook side**
4. Wrap `Revision` as `RevisionRef`, or pass it as is? Name? [wrap]
5. Drop `output_base` (third-party-facing, `playbook/README.md:83`)? [drop]
6. Native edits for solve blocks, differ for restructuring blocks; differ in `pypsa_helpers` or upstream? [as stated, local]
7. Dims check at block start, in the backend at `create_run`, or neither? Keep `adds`/`removes`? [both checks]
8. Bake `httpfs` into the block image? Retry on a stale-manifest write failure? [bake; retry]

**Backend and edits**
9. What does `GET .../content` return? [folded-record export, deferred]
10. REST query over attributes, or Quack only? [Quack only]
11. Stale-base policy: branch, replay on request, or reject? [branch]
12. `set` with expression values: drop, or a closed set of named transforms? [open]
13. Who runs import: a Prefect job in the PyPSA image, or the backend with PyPSA added? [Prefect job]
14. A `refs` table with a default `current`; does a successful run advance it automatically? [yes, by compare-and-swap]
15. Staging concurrency: `Workspace.process()` singleton or a workspace per request? [untested; test]
16. Run results from Prefect persistence or from block flow runs? [persist results]
17. Is a PyPSA-version schema change an accepted per-project migration? [open]

**Quack**
18. Who owns instance lifecycle: the runner, or a new sidecar? [runner, if its worker model fits]
19. Hook mechanism: Python callbacks (undocumented, in-process) or a C/Rust extension? [Python, with a pinning test]
20. Revision freshness for a running instance: push on completion, re-read per request, or restart? [push]
21. Token lifetime, and who revokes on project transfer or deletion (neither exists in the backend)? [open]
22. Any write access over Quack? [none]
23. File the issue 1, 3, 4 findings upstream? [your call; nothing filed]

**Yours, not delegated**
24. Which `datarecord_name_analysis.md` format changes land before Manta persists a record (item 7)?

## Untested

SeaweedFS `..` handling; the container egress and rogue-listener claims; the AST allowlist hook; `quack_cancel` reachability; cold start time; a block container against real S3; Python 3.12; `disabled_filesystems`, `allowed_paths`, `allowed_configs`; `quack_generate_keys`.
