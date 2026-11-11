# Step 1: playbook, runner and PyPSA blocks (items 1, 2, 3)
Requirements only. **verified** = I ran it (`datarecord/.venv/bin/python -I`, local stores, scripts in `/tmp/step1-playbook`; Python 3.14, pypsa
1.4.0, duckdb 2.0.0). **read** = from source. No S3, container, Prefect or Python 3.12 run. The venv can't import `playbook` or `playbook_library`,
so the scripts put their `src` dirs on `sys.path` (`common.py`). I replayed what the blocks do by hand; I did not run them.

## Item 1: the cross-process handle
**1. Every site, and what a serialised `Revision` needs there.**
- `core.py:33-52` `DataRecord{url}`, `to_dict/from_dict`. It is also the type of `INPUTS` settings (`core.py:79-83,156`;
  `rolling_horizon_dispatch.py:21`) and sits in `catalogue.json:463-474` as `$defs.DataRecord`. Needs a type with a JSON schema.
  `Revision` has none: `model_json_schema()` raises on `Store` (**verified**).
- `run_one.py:28-42,84-86`: the `MANTA_BLOCK_RESULT` line and the `--record`/`--inputs` JSON. Needs only the new dict shape. The Prefect
  path doesn't use it (**read**).
- `execution.py:44-67,99-142`: threads the handle through steps and never opens it. A nested playbook with every step inactive returns its
  input unchanged (`:126`). Needs: the engine stays opaque. `LocalBlockRunner` validates wired handles into settings (`merge_config`).
- `flows.py:84-113` `run-block`: dicts in, `result.to_dict()` out, persisted (`:80`). Needs `Revision.model_validate(dict)` in the container
  (AWS env, datarecord) and `model_dump(mode="json")` back. Validating reads the revision file (`revision.py:95-103`; **verified**: a
  missing store gives `KeyError`, an `s3://` URI without boto3 gives `ImportError`).
- `flows.py:130-186` `PrefectBlockRunner` and `run-playbook`: dicts only, no `persist_result` (backend.md Q1). They run in `playbook-worker`,
  which has no S3 credentials and "only ever moves pointers" (`compose-dev-services.yaml:153-169`). Needs: no store access there.
- `storage.py:66-`: callers are `pypsa_helpers.py:44,55` and `examples.py:51` only. Nothing survives for records; the `s3` extra goes too.
- `run_service.py:192-214` (`data_record_url`, `{"url": ...}`, `output_prefix` at `:206`), `run_request.py:22`, `run_route.py:37`. Needs the
  backend-built `{id, parent, store}` (backend.md Q4).
- Tests that build one: `playbook/src/conftest.py:13`, `blocks/tests/fakes.py` (encodes a trace in the URL, `f"{record.url}+{suffix}"`, which
  the engine tests assert on), the other `playbook` tests, `runner/tests/test_flows.py`, playbook-library `test_library.py` and
  `test_pypsa_end_to_end.py` (netCDF seeds), `backend/tests/unit/services/test_run_service.py:126`, `test_run_request.py`, integration
  `conftest.py:160`. Needs an opaque fake for engine tests and a local store seeded by `store.root(PyPSA.to_datarecord(n, con))` (**verified**, 0.3 s).

**2. What a block container needs.**
- Env: `job_environment()` already sets `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL` from `S3_*` (`runner/config.py:167-176`),
  which is what datarecord reads (`store.py:150-161`, `files.py:184`). No new variable. No region is set, and the backend sets one because "SigV4
  signing requires a region" (`s3_config.py:29`); untested on SeaweedFS (**read**).
- `Workspace` runs `INSTALL httpfs; LOAD httpfs;` on first `s3://` use (`store.py:163`): a download from DuckDB's extension repository in every
  fresh container, unless the extension is baked into the image (**read**).
- Crossing (**verified**): `rev.model_dump(mode="json")` is `{id, parent, store}`; a fresh `-I` process validated it and `PyPSA.build` read it.
- Install: `datarecord[pypsa,remote]` (`pyproject.toml:23-31`): duckdb>=1.5.4 uncapped (pip picks 2.0.0), boto3>=1.35.69, pypsa unpinned;
  playbook-library pins `pypsa>=1.2,<2` (`pyproject.toml:30`); only 1.4.0 was exercised here.
- Images: `block-image.Dockerfile:52-59` copies and installs only `playbook` and `playbook-library`; `.dockerignore:6-8` allowlists only those
  and `runner`. It needs `!datarecord`, `COPY datarecord` and `pip install ./datarecord[pypsa,remote]` first. The runner image needs datarecord
  only if the wrapper imports it. `playbook-library/pixi.toml:29` needs it for local tests.

**3. Naming.** Recommend Manta **wraps**: a small pydantic model in `playbook.blocks.core` (`id`, `parent`, `store` strings, no datarecord
import) called `RevisionRef` ("record" is datarecord's resolved view, and `DataRecord` is out). Reasons:
(1) `Revision` has no JSON schema, so it can't be a setting type or appear in the catalogue (**verified**); (2) validating it touches the
store, which the orchestrator can't (**read**); (3) engine tests need a fake; (4) `playbook` stays free of duckdb, and the name analysis
proposes `Store`->`Repository`, so the serialised `store` key may change and only the wrapper follows. Blocks convert with
`Revision.model_validate(ref.model_dump())`.

**4. `output_base` / `output_prefix`.** Today the engine builds `<prefix>/<step>` (`execution.py:103`), the block adds a suffix, and the backend
picks `s3://bucket/{project}/runs/{run}/output` (`run_service.py:60-64,206`), which the file endpoints list (`:383,397`). With a child revision
the store comes from the input and datarecord names the layer (`store.py:299`), so the engine has nothing to choose. What remains: (a) the step
path, as a label for logs and run/step provenance (revision files hold only `{id, parent}`); (b) a prefix for non-record artefacts (logs, plots),
which no library block writes. Recommend dropping `output_base` from `MantaBlock.run`/`BlockRunner.run_block` and `output_prefix` from
`execute_playbook`, `run-playbook` and the backend; keep `step_name`.

## Item 2: BlockDims and datarecord dims
**5. Use and mapping.** Nothing checks `BlockDims`. It is declared (`core.py:55-67,110`), copied into the catalogue (`registry.py:86-98,113,176`;
`catalogue.json:34-40,238-244,443-449,684-690`), and playbooks declare `initial_data.dims` (`playbook.py:160`, `yaml_io.py:71,186,252`).
`BlockDims.apply` has no caller (**read**: grep); `execution.py:84-87` says checking is "not yet part of this package"; the README expects dims to
be read from the record later (`README.md:294`). Strings in use: `snapshot` (cluster_time, overnight, dispatch:
`time_cluster.py:35`, `overnight_capacity_expansion.py:22`, `rolling_horizon_dispatch.py:34`) and `investment_period` (myopic,
`myopic_capacity_expansion.py:31`); none uses `adds` or `removes`.
- `snapshot` is the schema dim `snapshot`; `investment_period` is PyPSA's word for the schema dim `period` (`tools/pypsa.py:62`). Neither is a
  group (`connection`), attribute or property.
- A `BlockDims` string means "this axis has rows". A datarecord dim is declared for every record and may be empty: the example has
  `schema.dims` = bus, entity, period, scenario, snapshot but `record.dims` = snapshot, entity (**verified**). So it maps to the keys of
  `Record.dims`, a subset of the schema's. `adds`/`removes` would be `WorkingRecord.add`/`remove` on a dim (`mutable.py:1512,1575`, **read**).
  Needs such as a component type or an attribute are datarecord's `Requirements.categories/attributes` (`tools/base.py:33-78`), which
  `BlockDims` can't say.

**6. When to check.** From a `Revision` and `BlockDims` a pre-run check can verify `requires <= set(rev.record.dims)` (**verified** keys), a
non-empty `period` for a multi-period block, and `PyPSA.verify(record)` (empty for the example, **verified**; it tests the schema's declared
dims, `pypsa.py:1137`, and folds every component type). `apply()` can predict dims along the chain, replacing `initial_dims`, but later steps'
input revisions don't exist yet, so a misprediction shows only at run time. It can't judge attribute values or what a solve will do.
Recommend both: (1) an exact check at block start against the real input revision (in `MantaBlock` or `run_block`), failing before the build;
(2) a predicted-dims check in the backend at `create_run` (it will hold datarecord), failing with a 4xx before a container starts. Checking
nothing costs a container crash after the pull. The orchestrator can't check (no datarecord, no credentials).

## Item 3: PyPSA blocks as the first consumer
**7. `pypsa_helpers.py`.** `to_network` (`:37-45`) reads netCDF through `local_copy`, giving each call its own network. `write_network(n,
output_base)` (`:48-57`) writes a whole netCDF and never receives the parent, so it can't make a child; all four blocks end with it and hold
`record`. Its docstring (`:8-11`) says PyPSA can't compare networks; datarecord has no diff either (**read**). `apply_optimised_capacities`
(`:83-92`) reads `p_nom_opt` from a second network (the wired `capacity_source`). `PyPSA.build` does not restore results: `p_nom_opt` read back 0.0
where netCDF gave 50.0 (**verified**), so dispatch would fix every capacity at 0. It must read `capacity_source.record.outputs["p_nom_opt"]` (50.0;
rows at default are absent).

**8. Three options**, on the 24-snapshot example and a generated 8760-snapshot network (`bignet.py`: 5 buses, 12 generators, 5 loads, 4 lines;
root layer 1,063,913 B, 94 files). Layer size, **verified**:

| change | (a) whole | (b) diff | (c) native |
|---|---|---|---|
| example, one `capital_cost` | 17,800 B, 72 files | 587 B, 1 file | 587 B, 1 file |
| 8760 net, `capital_cost` x1.1 on all generators | 1,063,944 B, 94 files | 795 B, 1 file | 797 B, 1 file |
| 8760 net, solved (HiGHS, 2 s) | 2,951,651 B, 96 files | 1,866,561 B, 14 files | 1,864,894 B, 12 files |

- **(a) writes and reads but isn't the mutated network** (**verified**). `rev.child(PyPSA.to_datarecord(n, con))` works and is a full copy. A
  child overlays its parent: after `n.remove("Generator", "gen")` plus an add, `build` returned both; after `resample("4h")` it returned 24
  snapshots, not 6; `marginal_cost` set to its default 0.0 read back 10.0 (rows at default aren't written). Snapshot weightings are lost even at
  a root (4 became 1; `dims` writes only the `snapshot` column, `tools/pypsa.py:1679-1683`; `build` expects weight columns, `:603-613`). A solve
  widens the project schema for good: `Line.v_nom`, and a `SubNetwork` entity with an `inputs/obj` column holding a Python repr. Reject.
- **(b) works, with a differ of about 70 lines** (`diff_lib.py`). datarecord gives pieces only: long frames from `new.attributes`, DuckDB
  `except_`, and `WorkingRecord.set/add/remove/add_group/remove_group`; a long frame goes into `set` as is. Round trips **verified**: scalar and
  time-series changes; add and remove a generator; reset-to-default (needs `Schema.default_for` per entity type, else silently dropped); and
  `resample("4h")` (6 snapshots, aggregated `p_max_pu` matches, weights lost). Bus reattachment needs explicit `remove_group` for the old tuples
  (issue 94); without it one component came back with bus `''`. After a solve the diff picks up PyPSA bookkeeping (`Bus.control`,
  `Line.v_nom`, `Line.carrier`, `SubNetwork.obj`) and `set` rejects some of it (`KeyError`), so it needs an ignore list. Each axis, group and
  property needs its own code.
- **(c) is exact and cheapest** (**verified**): `w.set("capital_cost", ...)` reads back right. Solve results: `PyPSA.results(n, con)` returns long
  frames and `w.set(attr, frame, kind="outputs")` stages them (declared in the registry schema); `p` read back identical (219,000 rows, same sum).
  Results aren't inherited (a child without `outputs/` has none) and a second solve's outputs replace the first's (**verified**), so a reader
  needs the exact revision. Native and diff children carry no `meta`, so `objective` isn't recoverable (None; (a) keeps it). Fits:
  `overnight_capacity_expansion` (outputs only) and `rolling_horizon_dispatch` (capacity sets from the wired outputs, then outputs; the `p_nom`
  set is **read**, not run). `cluster_time` can't: it needs PyPSA's clustering on a network, so (b). `myopic` can't yet (item 9).
- **Recommend (c) for solve blocks and (b) for blocks that restructure the network**, both in `pypsa_helpers`, with a test that diff-then-`build`
  equals the mutated network. Not (a): it is wrong, not just large.

**9. Constraints on the library's networks.**
- Unique names: the example (`bus`, `gen`, `load`) passes; a `Load` named `bus` raises `UnsupportedRecordError` (**verified**). SubNetworks get a
  `0 SubNetwork` key (`design/tools.md:58`). The error comes at write time, after a solve; no library block adds components.
- One spec per attribute: library networks have no custom columns; a solve adds `SubNetwork.obj` (**verified**), which (b) and (c) avoid. Write
  before read: `PyPSA.results` and `to_datarecord(...).attributes` read an unwritten source (**verified**); `build` rejects it, so (a) must `child()` first.
- Issue 94 (open, read with `gh`): no library block removes a bus or any entity (**read**), so it isn't hit today. (b) must tombstone vanished
  tuples itself (**verified**); a native `remove("entity", [bus])` leaves connections.
- Blockers (**verified**): `to_datarecord` fails on a multi-period network (`missing axis key columns ['snapshot']`, from the `timestep` level; no
  upstream test covers it), which blocks myopic. Snapshot weightings are dropped, so `cluster-expand-dispatch` would solve with weights of 1.

## Requirements
1. Replace `DataRecord` with a Manta type (`RevisionRef`: `id`, `parent`, `store`) that has a JSON schema, never touches the store on
   construction, and becomes a `Revision` only in block code. The orchestrator imports no datarecord and needs no S3 credentials. The backend
   builds the handle from a revision uuid, and run requests carry no URL. Engine tests get a fake handle.
2. Block images install `datarecord[pypsa,remote]` from `./datarecord` with tested duckdb and pypsa versions; `.dockerignore` and
   `block-image.Dockerfile` copy it. The httpfs extension is baked in or reachable at start. A smoke test reads and writes a revision from a
   container against SeaweedFS (region, httpfs, path-style).
3. A block's output is `input.child(edits)`; the engine passes each output on as the next input. Drop `output_base`/`output_prefix`; keep
   `step_name` and report each step's revision with it (persist results per step).
4. `pypsa_helpers`: `to_network` becomes `PyPSA.build` over the handle's record; `write_network` takes the parent and returns the child.
5. Solve blocks stage `PyPSA.results` as outputs plus any input changes as sets, and read results from the exact revision. Blocks that restructure
   the network use a differ covering entities, properties, groups, snapshots and defaults, with an ignore list, tested by diff-then-build equality.
   Never write a solved network whole into a project store.
6. Blocked on datarecord: multi-period write (myopic) and snapshot weightings (cluster_time and every later solve).
7. `BlockDims` is checked against `Record.dims` keys at block start; `investment_period` becomes `period`.

## Open questions
1. Wrap `Revision` (recommended, as `RevisionRef`) or pass it as is? Name?
2. Drop `output_base` (recommended) or keep a vestigial argument? It is third-party-facing (`playbook/README.md:83`).
3. (c) for solve blocks and (b) for restructuring blocks (recommended), with the differ in `pypsa_helpers` or contributed upstream?
4. Dims check at block start and in the backend (recommended), one of them, or neither? Keep `adds`/`removes`?
5. Who fixes the multi-period write and the weighting loss, and does the tracer bullet wait? Is the objective needed per revision (only
   whole-source writes keep it)?
6. Bake httpfs into the block image (recommended) or allow the fetch at container start? A `Revision` cached before another write widens the
   manifest fails to write (**verified**); retry with a fresh one?
