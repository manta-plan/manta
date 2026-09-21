# Playbook execution — implementation Q&A

The design rationale behind Manta's playbook/blocks implementation, as questions.
Companion reading: [manta-blocks/README.md](manta-blocks/README.md),
[backend playbook runs](backend/README.md#playbook-runs),
[how-to-test.md](how-to-test.md).

## Where does playbook orchestration live, and why?

In `manta-runtime` — a package of its own, beside `manta-blocks` and `backend` —
and nowhere else. Two boundaries force that placement:

- **`manta-blocks` must stay orchestration-agnostic** (proposal requirements 7/8):
  blocks and playbooks are written and tested by modelers, the package is destined
  for its own repository, and nothing in it may import Prefect or Docker. It
  exposes a `StepRunner` protocol instead, and `manta-runtime` plugs into it.
- **The image a block author works with must stay bare.** `manta-blocks-runner`
  holds manta-blocks plus the blocks' own dependencies — no Prefect, no Manta —
  and is the environment an outside block author tests against. Manta layers its
  execution image on top of it rather than into it (see below), so no app code,
  no framework and no route to the app database or identity provider reaches a
  container running modelling code. It also keeps interpreter choices
  independent: the image runs Python 3.12 (what the PyPSA stack resolves on)
  while the backend runs 3.14.

Keeping orchestration out of the backend means the app is never in the execution
path: it dispatches at a deployment by name, so a run outlives an app restart and
the app needs no docker access.

## What does the execution runtime consist of?

`manta_runtime.flows` (~200 lines) plus one contract in manta-blocks:

- **The `run-playbook` flow** — rebuilds the playbook from its submitted document
  (blocks resolved from the committed catalogue, since this process cannot import
  them), validates it, and walks it with manta-blocks' engine. It is served as a
  Prefect deployment on a **process work pool**, drained by a long-lived worker
  container — that is what lets the API dispatch runs by name, and what keeps an
  in-flight run alive across a backend restart.
- **The `run-block` flow** — one deployment shared by every block, on a **docker
  work pool**, so each step is a fresh container. The block to run arrives as a
  parameter and the flow run is named `<step>[<block>]`, so per-step visibility
  survives without a deployment per block. It is the only Manta code that runs
  inside a block's environment, and it imports a block only when asked for one by
  name.
- **`PrefectStepRunner`** — the `StepRunner` implementation that turns the
  engine's "run this block with these inputs, write here" calls into those flow
  runs, and raises if one does not complete.

Configuration (the images, the pools, the docker network, the object-store
endpoint as seen from inside containers) comes from `manta_runtime.config`. Not
the runtime's job: deciding *what* to run (API services) and *how* blocks work or
steps are wired (manta-blocks).

## How does a block execute in isolation?

One fresh container per step, started by the docker work pool's worker from that
environment's execution image, joined to the stack's network and removed when it
finishes. Data never travels through the orchestrator: blocks read and write S3
records directly, each step at
`s3://<bucket>/<project>/runs/<run>/steps/<step>.<ext>`, so a finished run is a
browsable folder of every step's output. The step's *record* — the pointer, not
the data — comes back through Prefect's result storage.

A block container is told five things and nothing else: how to reach the Prefect
API, where to persist its result, which of its loggers to ship, and the object
store's address and credentials. It gets no route to the app database or the
identity provider.

## Why does a block container hold Prefect, when the point was that it should not?

Because a Prefect worker cannot decide that a flow run succeeded. It resolves the
job template, starts the container, waits, and reports `CRASHED` on a non-zero
exit — and that is all (`prefect/workers/base.py`). The terminal state and the
result are reported over the API by the Prefect engine *inside* the container. A
bare container whose command was overridden to run a block directly would do the
work, exit 0, and leave its flow run `PENDING` for ever, with the orchestrator
blocked on it.

So "use the work pool" and "keep Prefect out of the block image" cannot both
hold, and the image is built in two layers instead:

- **`manta-blocks-runner:<env>`** — manta-blocks plus the blocks' own
  dependencies. No Prefect, no Manta. This is what a block author writes, tests
  and runs against, and running their suite inside it stays an exact
  environment-parity check.
- **`manta-exec:<env>`** — that image plus Prefect, prefect-aws and
  manta-runtime, built and registered by Manta. Block authors never build it,
  name it, or depend on it.

What the derived layer costs: a Prefect version contract between the image and
the server (both pinned to 3.8.3), and Prefect's dependency set having to resolve
alongside the block environment's. Both are Manta's problem rather than a
contributor's.

What it buys: per-step infrastructure declared in a job template rather than
imperatively, a per-run image override (which is how environments get their own
image), logs and state that Prefect handles natively rather than being relayed,
the docker socket confined to one dispatcher service, and a k8s move that changes
a work pool's type rather than any code.

## How do a step's logs reach Manta?

They are the flow run's own logs — Prefect's API log handler ships them from
inside the container, and nothing relays anything. `GET /v1/runs/{uuid}/logs`
gives the playbook's, `GET /v1/runs/{uuid}/steps/{step}/logs` one step's.

Prefect captures its own loggers and, with `log_prints`, whatever a flow prints.
A modelling framework's logging is neither, so the loggers to ship are named by
`MANTA_BLOCK_LOGGERS` — a property of the installed block library rather than of
the runtime, so it is configuration rather than a constant.

*Known gap:* output a solver writes straight to the process's stdout from native
code (HiGHS's console output, for instance) is not Python logging and does not
ship. The previous Docker-SDK transport relayed the container's raw stdout and so
did capture it. Recovering it means either having the block route its solver's
output through `logging`, or capturing the file descriptor inside `run-block`.

## How does an external contributor test blocks and playbooks without Manta?

`manta-blocks` alone is a complete, runnable framework — no Manta, Prefect,
Docker, or S3 involved:

- Block definition mistakes raise at class-creation time (`__init_subclass__`
  checks on `CONFIG`, `INPUTS`, defaults).
- A block is testable as a plain method call: `DataRecord.url` takes local paths
  and `output_base` can be a pytest `tmp_path`
  (`src/blocks/tests/test_library.py` is the template).
- Playbooks validate (`issues()`) and draw (`to_mermaid()`) without executing.
- Whole playbooks run in-process: `playbook.run(record, config, output_prefix=…)`
  with the default `LocalStepRunner`.
- The loop is `uv sync --extra pypsa && uv run pytest`.

Two properties connect that to production with no Manta PR: the runner image *is*
manta-blocks plus dependencies, so running their suite inside it
(`docker run manta-blocks-runner … pytest`) is an exact environment-parity check;
and `python -m blocks` (the catalogue) is how their blocks get described to Manta
without Manta importing them.

## How do in-process runs relate to Manta runs? Is there one orchestrator or two?

One. The orchestration *decisions* — which steps run (`when:` conditions), their
order, what feeds what, which config each step sees, where outputs land — exist
once, in manta-blocks' `execute_playbook`. It is a plain sequential function, and
both worlds call it: a laptop run passes `LocalStepRunner` (resolve the block
from the registry, call `run()` in-process), Manta's flow passes
`DockerStepRunner` (one container per step). The only thing that differs is that
~30-line step transport, and it is block-agnostic — it never branches on which
block or playbook is involved.

Prefect is deliberately **not** used as a DAG engine. It contributes dispatch,
queueing, state, per-step tracking, and logs *around* the engine.

What a passing local run guarantees: everything semantic (same engine, same block
code, same validation — a logic bug cannot exist in only one of the two). What it
does not: the S3 branch of `blocks.storage`, the JSON boundary of flow-run
parameters, container mechanics and resources, and dependency-resolution drift
between a contributor's venv and the image (no shared lockfile). The backend's
end-to-end integration test covers the first three generically — the transport is
identical for every block — and image-parity testing addresses the fourth.

## Does local execution install and run block dependencies (PyPSA) locally?

Yes: `LocalStepRunner` imports the real block class, so every dependency of every
*executing* block must be in the local environment, and solves run on the local
CPU (hence `uv sync --extra pypsa`). The registry is lazy, so only blocks that
actually execute are imported — loading, validation, drawing, and the catalogue
work without PyPSA, and a non-importable executing block raises
`BlockUnavailableError`. A local run assumes one environment can hold all
executing blocks, the same assumption the single runner image makes in
production. With local paths, `blocks.storage` never touches boto3/S3.

## Why is Prefect involved at all, and why exactly one deployment?

What Prefect buys here: the API starts work **by name**
(`run_deployment("run-playbook/run-playbook", …)`) without importing any flow
machinery at request time; a dispatched run is a server-side object with a state
machine, per-task retries and timeouts available, per-step tracking, log
aggregation, and a UI — none of which is worth hand-building. Avoiding it would
mean owning queueing, state, and observability ourselves.

There is one deployment, `run-playbook`, registered by the one-shot
`playbooks-provision` service when the stack boots. Playbooks, configs, records
and output locations all travel as flow-run *parameters*, so nothing is ever
deployed per playbook or per block — editing a playbook redeploys nothing.
Blocks need no deployments at all: a step is a task run that drives a container
directly.

It runs on a **process** work pool rather than a docker one. `run_playbook`
blocks for the whole playbook while its steps run, so as a per-run container it
would idle for hours, exposed to eviction, and would orphan its already-started
steps if it died. A long-lived process worker costs almost nothing, since it
calls out and waits.

## How are the blocks of one playbook run tracked and grouped?

Two deliberate identifiers:

- **One flow run per playbook run**, named `run-<manta run uuid>` by the backend.
- **One task run per executed step** inside it, named `<step>[<block>]`, with the
  step's container logs relayed into it.

Prefect UI: search `run-<uuid>` → the run page lists every step's task run with
state, timing, and logs. Manta API: `GET /v1/runs/{uuid}` (state), `/steps`
(per-step states in start order — a single `read_flow_runs` query by parent flow
run id), `/steps/{step}/logs` (that step's own log), `/logs`, `/outputs` (one
file per executed step). Steps of nested
playbooks appear in the same flat list; their storage paths
(`steps/<nesting>/<step>.<ext>`) encode the nesting.

## What is missing for production, what can go wrong, and what are the alternatives?

**Correctness & robustness:** no retries or timeouts on steps yet (a retried step
overwrites its own `output_base`, which is the intended idempotent behavior); the
job template declares no per-container memory/CPU limits, and the proposal's
data-relative resource declarations are unmodeled; orphan windows in run creation
(dispatch-then-commit — add row-first + reconciler and an `idempotency_key`); no
cancel/re-run endpoints; no cap on concurrent containers (a work-queue
concurrency limit on the blocks pool is the natural place).

**Security:** containers receive static S3 credentials via environment (readable
by anyone who can inspect containers on the host — move toward per-run scoped
credentials or IAM); the new endpoints and the Prefect server itself are
unauthenticated; starting containers needs Docker API access, which is
root-equivalent — it is confined to the one blocks-worker service, and a k8s work
pool removes it.

**Operability:** `list_runs` makes one Prefect call per run (bulk-read, or sync
state into Manta's DB via events); Prefect's flow-run/log history and its result
objects grow unbounded (retention and lifecycle rules needed for both); the
images need a registry + digest pinning, with the digest recorded per run for
full reproducibility; outputs have no download (presigned-URL) route yet; block
storage grows as steps × model size because PyPSA cannot diff networks (needs
lifecycle/GC).

**Design concerns:** requirement 5 is only half-met — `globals` drive `when:`
conditions and nested-playbook inheritance, but a global like `solver=highs` does
not flow into block configs (needs layered config resolution: defaults < globals
< step — and a partial-config merge on run creation); the committed catalogue can
go stale outside PyPSA-capable CI; declared dims are trusted rather than read
from the data; `DataRecord` is a bare URL with no checksum/format/lineage; flat
step naming can collide for nested playbooks reusing leaf names.

**Alternatives weighed:**

- **Driving the Docker SDK directly from the orchestrator**, with a bare block
  image and its result on stdout. This is what the runtime did first. It keeps
  Prefect out of the block image entirely, at the cost of ~60 lines of container
  plumbing, per-step infrastructure expressed in code rather than a job template,
  logs relayed by hand, a docker socket wherever the orchestrator runs, and no
  way to vary the image per run. The derived execution image recovers the
  bare-image property for the artifact that matters — the one block authors
  test against — so the work pool wins on every other count. Its one real loss is
  the raw-stdout capture noted above.
- **Task-per-block on Dask/Ray in one process:** lower latency and free DAG
  parallelism, but sacrifices container-per-block isolation — the requirement
  that shapes everything.
- **Argo Workflows / raw k8s Jobs:** attractive if k8s-native is the endgame, at
  the cost of the Python engine and YAML authoring. The planned path instead is a
  `K8sJobStepRunner` (Jobs API) behind the same `StepRunner` seam, changing
  nothing above it.
- **In-engine parallelism:** `execute_playbook` runs steps sequentially today;
  the wiring already defines a DAG, so submitting independent steps concurrently
  is an engine-only change behind the same interfaces.
