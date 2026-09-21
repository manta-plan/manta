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
- **Block containers must stay bare.** The runner image holds `manta-blocks` plus
  the blocks' own dependencies — no Prefect, no Manta. Containers that run
  modeling code (eventually third-party code) carry no app code, no framework,
  and no pathways to the app database or identity provider; and the image is
  exactly the environment an outside block author tests against. This also keeps
  interpreter choices independent: the image runs Python 3.12 (what the PyPSA
  stack resolves on) while the backend runs 3.14.

Keeping the orchestration in the backend proper — rather than in a third package —
means one codebase and one deploy unit: Prefect is pinned in exactly two places
(backend and server image), and the deployment name the API dispatches to is an
ordinary import, not a cross-package contract.

## What does the execution runtime consist of?

`manta_runtime.flows` (~200 lines) plus one contract in manta-blocks:

- **The `run-playbook` flow** — rebuilds the playbook from its submitted document
  (blocks resolved from the committed catalogue, since this process cannot import
  them), validates it, and walks it with manta-blocks' engine. It is served as a
  Prefect deployment on a **process work pool**, drained by a long-lived worker
  container — that is what lets the API dispatch runs by name, and what keeps an
  in-flight run alive across a backend restart.
- **One Prefect task per step** (`run_block`, task-run name `<step>[<block>]`) —
  spawns the step's container, relays its log lines live into the task run,
  parses the result, and cleans the container up.
- **`DockerStepRunner`** — the `StepRunner` implementation that turns the engine's
  "run this block with these inputs, write here" calls into those task runs.
- **`python -m blocks.run_one`** (in manta-blocks) — the container entrypoint and
  the entire driver↔container contract: plain arguments in, ordinary logs out,
  one final `MANTA_BLOCK_RESULT` stdout line carrying the output record, exit
  code for success. The marker's printer and parser live side by side in
  `blocks/run_one.py`, so the protocol cannot drift.

Configuration (image name, docker network, the object-store endpoint as seen from
inside containers) comes from `manta_runtime.config`. Not the runtime's job: deciding *what* to run (API services) and *how* blocks work or
steps are wired (manta-blocks).

## How does a block execute in isolation?

One fresh container per step, from the one blocks-runner image (proposal: one
image for the MVP; per-environment images become necessary only when blocks with
conflicting dependency environments appear — the `StepRunner` seam is where that
lands). The task checks the image exists locally, starts
`python -m blocks.run_one <block> --record … --output-base … --config … --inputs …`
with `AWS_*` credentials on the stack's network, streams the logs, and reads the
result from the final marker line. Data never travels through the orchestrator:
blocks read and write S3 records directly, each step at
`s3://<bucket>/<project>/runs/<run>/steps/<step>.<ext>`, so a finished run is a
browsable folder of every step's output.

Because the result returns through the container's own stdout to the process that
awaits it, there is no separate result store to configure and nothing to go stale
if a step is ever retried.

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
(per-step states in start order — a single `read_task_runs` query by the flow
run's id), `/logs`, `/outputs` (one file per executed step). Steps of nested
playbooks appear in the same flat list; their storage paths
(`steps/<nesting>/<step>.<ext>`) encode the nesting.

## What is missing for production, what can go wrong, and what are the alternatives?

**Correctness & robustness:** no retries or timeouts on steps yet (both are
one-line Prefect task options; a retried step overwrites its own `output_base`,
which is the intended idempotent behavior); no per-container memory/CPU limits,
and the proposal's data-relative resource declarations are unmodeled; orphan
windows in run creation (dispatch-then-commit — add row-first + reconciler and an
`idempotency_key`); no cancel/re-run endpoints, and cancellation must also kill
the step's container; no cap on concurrent containers (Prefect task concurrency
limits by tag, or a work-queue limit).

**Security:** containers receive static S3 credentials via environment (readable
by anyone who can inspect containers on the host — move toward per-run scoped
credentials or IAM); the new endpoints and the Prefect server itself are
unauthenticated; driving containers requires Docker API access from the backend
host, which is root-equivalent — the k8s runner removes that.

**Operability:** `list_runs` makes one Prefect call per run (bulk-read, or sync
state into Manta's DB via events); Prefect's flow-run/log history grows unbounded
in Postgres (retention needed, and container logs are duplicated into it); the
image needs a registry + digest pinning, with the digest recorded per run for
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

- **Prefect's docker work-pool worker** (one *flow run container* per step,
  provisioned by a worker service): buys declarative per-step infrastructure and
  orchestrator-in-a-container durability, but requires Prefect and flow code
  inside the block image — giving up the bare-image property and adding a
  version contract between image and backend. Bare block images are the stronger
  invariant here.
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
