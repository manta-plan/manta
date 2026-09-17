# Playbook PoC — implementation Q&A

Distilled from the design discussion around the playbook/blocks PoC. Companion
reading: [playbook-proposal requirements], [manta-blocks/README.md](manta-blocks/README.md),
[manta-runtime/README.md](manta-runtime/README.md), [how-to-test.md](how-to-test.md).

## Why a separate `manta-runtime` package?

Because the Prefect glue had nowhere else it could correctly live:

- **Not in `manta-blocks`** — blocks/playbooks must stay orchestration-agnostic
  (proposal requirements 7/8), and that package moves to its own repository later.
- **Not in the backend** — the flows must be importable *inside the runner image*
  (deployments use module-path entrypoints and execute in containers). The image
  runs Python 3.12 (the PyPSA stack does not resolve on 3.14) while the backend
  pins `==3.14.*`, so the backend package is uninstallable there — and baking
  FastAPI/Keycloak/alembic into every block container would be wrong anyway.
- **Decoupling** — the backend never imports the runtime; it starts and watches
  runs purely through the Prefect API by deployment name. The API process needs
  no `prefect-docker` and no PyPSA.
- **It is the designated seam** — the post-MVP changes the proposal names
  (docker→k8s work pool, local module→git-sourced code, per-environment images)
  all land in this one small package, which stays in the manta repo when
  manta-blocks leaves ("orchestration lives exclusively in Manta").

Cost: one deliberately duplicated deployment-name constant
(`run-playbook/run-playbook`) in the backend, documented on both sides.

## What are `manta-runtime`'s responsibilities?

Three, across two modules (~250 lines):

1. **The two Prefect flows every run is made of** (`flows.py`):
   `run_playbook` (rebuilds the playbook from its document, validates it, walks
   it — one flow run per playbook run; what the backend dispatches) and
   `run_block` (runs one block by registry name — one flow run per step, hence
   one container per step; flow-run name templated to `<step>[<block>]`).
2. **The `StepRunner` implementation** (`PrefectStepRunner`): turns each
   fully-spelled-out block invocation handed over by manta-blocks' executor into
   a `run_deployment` child flow run, hands results back across the container
   boundary via `<output_base>.record.json` in S3, and surfaces failures as
   `BlockRunFailedError` naming the step and flow run.
3. **Provisioning at boot** (`deploy.py`, run by the compose `prefect-deployer`
   service): idempotently creates the docker work pool and the two *static*
   deployments (image, network, env stamped in as job variables). Playbooks and
   configs travel as flow-run parameters, so nothing is ever deployed per
   playbook or per block.

Not its job: deciding *what* to run (backend), *how* blocks work or steps are
wired (manta-blocks), serving any API.

## How does an external contributor test blocks/playbooks without Manta?

`manta-blocks` alone is a complete, runnable framework — no Manta, Prefect,
Docker, or S3 involved:

- Block definition mistakes raise at class-creation time (`__init_subclass__`
  checks on `CONFIG`, `INPUTS`, defaults).
- A block is testable as a plain method call: `DataRecord.url` takes local
  paths, `output_base` can be a pytest `tmp_path`
  (`src/blocks/tests/test_library.py` is the template).
- Playbooks validate (`issues()`) and draw (`to_mermaid()`) without executing
  anything.
- Whole playbooks run in-process: `playbook.run(record, config, output_prefix=…)`
  — the identical executor and block code Manta uses.
- The loop is `uv sync --extra pypsa && uv run pytest`.

Bridging to Manta needs no manta-repo PR: rebuild the runner image against their
checkout (`up --build`); post-MVP, git-sourced deployments remove even that.
`python -m blocks` (the catalogue) is how their blocks get described to Manta
without Manta importing them.

## How do in-process runs work — which orchestrator do they use?

None — and they do not reuse `manta-runtime`; the reuse goes the other way.
`execute_playbook()` in manta-blocks is a plain Python function: validate,
compute active steps (`when:`), loop sequentially, wire inputs, compute
`output_base`, call `runner.run_block(...)` (nested playbooks recurse). The
default `LocalStepRunner` resolves the block from the registry and calls
`run()` directly in the current process.

`manta-runtime`'s `run_playbook` flow calls that *same* `execute_playbook()`,
passing `PrefectStepRunner` instead. So there is exactly **one** playbook
engine — ordering, conditions, wiring, config scoping, output naming — and the
only difference between a laptop run and a Manta run is which ~30-line
`StepRunner` executes an already-decided block invocation (direct call vs.
`run_deployment` → container).

## Does local execution install and run block dependencies (PyPSA) locally?

Yes — `LocalStepRunner` imports the real block class, so every dependency of
every *executing* block must be in the local environment, and solves run on the
local CPU. Qualifications:

- The registry is lazy: only blocks that actually execute are imported.
  Loading, validation, drawing, and the catalogue work without PyPSA; a
  non-importable running block raises `BlockUnavailableError`.
- A local run assumes one environment can hold all executing blocks — the same
  assumption the MVP's single runner image makes in production. Mixed-environment
  playbooks validate locally but need the `StepRunner` seam to execute.
- Data stays local: with local paths, `blocks.storage` never touches boto3/S3.

## Isn't this two orchestrators? Does local success guarantee a production run?

Not two orchestrators: the orchestration *decisions* exist once (manta-blocks'
executor). Prefect is deliberately not used as a DAG engine — it provides
queueing, container scheduling, state, and logs around single-step invocations.
What is duplicated is a ~30-line, block-agnostic step transport.

Local success guarantees everything **semantic** (same engine, block code,
validation, wiring, naming — a logic bug cannot exist in only one of the two).
It does **not** guarantee:

1. environment drift (no shared lockfile between a contributor venv and the
   runner image);
2. the S3 branch of `blocks.storage` (locally only the local-path branch runs);
3. the JSON serialization boundary of flow-run parameters;
4. infrastructure mechanics and resources (worker, networking, result
   side-channel, container memory).

That gap is covered once, generically, by the backend's end-to-end integration
test — the transport never branches on which block/playbook is involved, so one
passing e2e validates 2–4 for all blocks. The real residual risk is (1); the
honest fix is a locked/published runner environment (contributors can already
run their suite inside the image: `docker run manta-blocks-runner … pytest`).

## Why Prefect deployments? What are they? Could we avoid them?

A deployment is a server-side registration making a flow *triggerable by name
over the API* and binding it to infrastructure: entrypoint (module path in the
runner image), work pool, job variables (image, network, env). They are the
hinge for three requirements at once: backend decoupling
(`run_deployment("run-playbook/run-playbook", …)` needs only a name), one
container per block (pool-routed execution *is* deployments in Prefect 3 —
there is no ad-hoc "run this flow on a pool" API), and durability (a dispatched
run is a server-side object that survives backend restarts).

Kept minimal: exactly two, static, generic, created idempotently at boot.
Avoiding them means giving something up — `flow.serve()` runs flows inside one
long-lived process (no isolation; how the legacy pi flow works), in-process
execution couples the API to block environments, and dropping Prefect for a
hand-rolled Docker driver means rebuilding queueing/state/retries/logs/UI.

## How do you track the blocks of one playbook run (Prefect and API)?

Two deliberate identifiers make it trivial:

- **Parent–child linkage** — each block is dispatched from inside the playbook
  flow run, so block flow runs carry `parent_flow_run_id` of the playbook run.
- **Deterministic names** — playbook run `run-<manta run uuid>`, block runs
  `<step>[<block>]`.

Prefect UI: search `run-<uuid>` → the run page lists each step as a subflow
with state, timing, logs. Manta API (the intended surface): `GET /v1/runs/{uuid}`
(state), `/steps` (per-block states, start order), `/logs`, `/outputs` (one
file per executed step). Raw Prefect API: `read_flow_run(id)` +
`read_flow_runs(FlowRunFilter(parent_flow_run_id=…))` — exactly what
`run_service.py` does. Nuance: nested-playbook steps appear in the same flat
child list; their `output_base` still encodes the nesting path.

## What is missing for production, what can go wrong, what are the alternatives?

**Top gaps (correctness & robustness):** no retries — and the `.record.json`
side-channel is retry-unsafe (same `output_base` on rerun can read a stale
record; adopt Prefect result storage or per-attempt paths *before* enabling
retries); orphan windows in run creation (dispatch-then-commit; add
row-first + reconciler, and `idempotency_key`); no per-block timeouts or
memory/CPU limits (resource declarations are an explicit proposal requirement,
unmodeled); no cancellation/re-run endpoints; no failure-path or load e2e; no
work-pool concurrency limit.

**Security:** AWS credentials are stamped into deployment job variables
(readable via the Prefect API — move to worker env/secret blocks/IAM); the
docker socket mount is root-equivalent on the host (k8s worker fixes it);
the new endpoints and the Prefect server itself are unauthenticated.

**Scalability & operability:** `list_runs` polls Prefect one call per run
(bulk-read or event-driven state sync into Manta's DB); the orchestrator
container idles for the run's whole duration and polling adds ~5s per step;
Prefect server needs restart policy, retention, sizing; every block writes the
full network (storage = steps × model size; needs GC/lifecycle and eventually
record diffing); images need a registry + digest pinning, with the digest
recorded per run for true reproducibility; outputs have no download
(presigned-URL) route yet.

**Design concerns:** requirement 5 is only half-met (`globals` drive `when:`
and nested inheritance, but a global like `solver=highs` does not flow into
block configs — needs layered config resolution, and partial-config merge);
contributor-env vs image drift; the committed catalogue can go stale outside
pypsa-capable CI; declared dims are trusted, not read from data; `DataRecord`
is a bare URL (no checksum/format/lineage); flat step naming can collide for
nested playbooks.

**Alternatives:** Prefect result persistence (cleanest single upgrade);
task-per-block in one flow with Dask/Ray (lower latency, DAG parallelism, but
sacrifices container-per-block isolation); Argo Workflows/k8s Jobs directly
(attractive if k8s is the endgame, at the cost of the Python-native engine —
the `StepRunner`/work-pool seam keeps a Prefect k8s pool as the reversible
first step); Temporal (heavier than needed). Within the current design, the
executor could submit *ready* steps concurrently — the wiring already defines
the DAG — gaining parallelism without changing any interface.
