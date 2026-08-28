# 03 — Workflow orchestration

Manta uses [Prefect](https://docs.prefect.io) 3 as its workflow execution engine.
Prefect already solves asynchronous execution, state tracking, retries, logging and
run history, so Manta's job is to submit work to it and query it back — not to
reimplement any of that.

This document is a Prefect primer aimed at someone who has never used it, followed by
exactly how Manta uses it. The rest of the design documents assume both halves.

## A Prefect primer

### Flows and tasks

A **flow** is a Python function decorated with `@flow`. Calling it produces a **flow
run** — a tracked execution with an identifier, a state, timestamps and captured logs.
A **task** (`@task`) is a smaller unit inside a flow, individually tracked and
individually retryable. Tasks are optional; a flow with no tasks is perfectly normal.

The important property is that a flow run is an *object in a database*, not just a
function call. You can ask about it later, from a different process, after a restart.

### The Prefect server

The Prefect server is a REST API plus a scheduler plus a web UI, backed by its own
database. It stores flow runs, their states, their logs and their results metadata. It
does not execute anything itself.

Everything that submits or executes work talks to this API and only to this API. That
is why Manta's backend and Manta's workers never talk to each other directly.

### Deployments

Running a flow by importing it and calling it only works if the calling process can
import the flow — which requires the flow's dependencies. That is exactly what Manta
cannot assume.

A **deployment** solves this. It is a registered, named, remotely-triggerable
description of "this flow, runnable in this place, with these default parameters". Its
name is `<flow-name>/<deployment-name>`. Given only that string, any process that can
reach the Prefect API can request a run:

```python
run_deployment("run_block/cluster_time-pypsa", parameters={...}, timeout=0)
```

`timeout=0` means *submit and return immediately* rather than waiting for the run to
finish. The call returns a flow run object whose `id` is the handle for everything
afterwards.

The caller needs no ability to import, or even install, the code that will run. This
is the single Prefect feature the entire architecture rests on.

### Work pools and workers

A deployment is registered against a **work pool**: a named queue that routes flow
runs to the infrastructure capable of executing them.

A **worker** is a long-running process that polls one work pool, picks up flow runs
queued to it, and executes them. One worker serves exactly one pool.

The consequence that matters: a flow run queued to a pool with no worker sits there
forever. Work pools are not created automatically, and neither are workers — both are
deliberate operational acts.

Worker types differ in *how* they execute a run:

| Type | Behaviour | Used for |
| --- | --- | --- |
| `process` | Runs the flow as a subprocess of the worker, in the worker's own Python environment | Local development; Manta's orchestrator |
| `docker` | Starts a container per flow run | Docker-based deployments |
| `kubernetes` | Creates a Kubernetes Job — a fresh pod — per flow run, then lets Kubernetes reap it | Production block execution |

Switching between them changes deployment configuration and infrastructure, not
application code. See [07](07-deployment-topology.md).

### Nesting: subflows and `run_deployment` from inside a flow

Called from *inside* a running flow without `timeout=0`, `run_deployment` behaves
differently: it blocks until the requested run finishes, and links it as a **subflow**
of the caller. The Prefect UI then shows a parent run with its children nested beneath
it, and the parent can read the child's return value.

This is the mechanism Manta uses to run a multi-step playbook whose steps need
mutually incompatible environments. A lightweight parent flow calls out to each step's
deployment in turn; each step executes in its own environment; the parent does no
modelling work itself, it only sequences and waits. Sequencing, waiting, failure
propagation and the grouped parent/child view all come for free.

### Results and logs

A flow run's return value is its **result**. Because a parent and its child run in
different processes — usually different containers — the child's return value has to
be written somewhere both can reach for the parent to read it. Prefect calls this
**result persistence**, and it must be configured with storage both sides can access.

Prefect captures logs per flow run and per task run, and serves them through its API.
This is where run output lives; Manta reads it back rather than capturing anything
itself.

### What Prefect gives us for free

Retries and retry policies, timeouts, concurrency limits per work pool, run history,
cancellation, a scheduler for recurring runs, and an operator UI for inspecting any of
it. None of this needs to appear in Manta's code, and none of it should be
reimplemented there.

## How Manta uses Prefect

### Two flows, and only two

The whole system is built from two Prefect flows, both defined in the `blocks`
repository:

| Flow | Deployment name | Runs on | Job |
| --- | --- | --- | --- |
| `run_block` | `run_block/<block>-<env>` | The work pool for `<env>` | Execute one block: import it by name, run it, return where it wrote its result |
| `run_playbook` | `run_playbook/<env>` | The orchestrator work pool | Execute a whole playbook: rebuild it from its document, then dispatch each step |

There is one `run_block` deployment per distinct `(block, environment)` pair, not per
block and not per playbook. A block used five times across three playbooks is deployed
once. Every one of those deployments runs the same generic `run_block` function; the
block's name arrives as a parameter. That gives per-block visibility in the Prefect UI
without per-block code.

`run_playbook` is the parent-flow pattern described above, generalised: it is the only
component that knows about step ordering, conditions and data wiring, and it holds no
modelling dependencies at all.

### What Manta's backend does

Three operations, all of them thin:

- **Submit.** `run_deployment("run_playbook/<env>", parameters={playbook document,
  configuration, seed data record, catalogue}, timeout=0)`. Returns a flow run id.
- **Observe.** Read a flow run's state by id; read its child runs' states to report
  per-step progress; read its logs.
- **Persist the link.** One row associating a Manta run with a Prefect flow run id.

The backend process never runs flow code, never starts a worker, and holds no
scientific Python dependencies.

### The `Run` entity, and what it deliberately omits

```
runs
  id, uuid, created_at        (from the shared entity base)
  project_id                  FK → projects, ON DELETE CASCADE
  playbook_id                 FK → playbooks
  prefect_flow_run_id         unique
```

There are **no** status, progress, result or error columns. `GET /v1/runs/{uuid}`
queries Prefect live. The reasoning:

- Prefect already stores this, transactionally, as the system of record.
- Anything Manta cached would have to be kept in sync by polling or events, and would
  be wrong in between.
- A run that fails while Manta is restarting still has the correct state — in Prefect.

The one thing worth reconsidering is the **final output record**: a completed run
produces a URL pointing at its result artefact, and that is a product-level object
whose lifetime should probably exceed Prefect's log retention. See
[08](08-open-questions.md#should-manta-store-the-final-output-record).

### The API surface

| Endpoint | Backed by |
| --- | --- |
| `POST /v1/runs` | Validate, resolve the seed record, submit to Prefect, insert the run row |
| `GET /v1/runs/{uuid}` | Prefect flow run state, plus per-step states from its child runs |
| `GET /v1/runs/{uuid}/logs` | Prefect flow run logs, with the current state so the caller knows whether they are final |

Per-step states are available because each step of a playbook runs as its own flow
named after the step, so the names in Prefect line up with the nodes the frontend
drew at design time. The same graph can be coloured live.

### Prefect's own database

Prefect ships with SQLite by default. Any non-ephemeral deployment uses PostgreSQL
instead.

**Decided:** share the PostgreSQL *server* with Manta, but use a separate *database*
and a separate role. Prefect [does not support schema-level
isolation](https://github.com/PrefectHQ/prefect/issues/18015), whereas
database-level permissions are enforced by PostgreSQL itself — a Prefect role simply
cannot read Manta's tables. Configuration is a single connection URL
(`PREFECT_API_DATABASE_CONNECTION_URL`).

This is cost-efficient and safe. If Prefect's workload ever justifies its own server —
because its queries affect Manta's API latency, because retention and vacuum
operations cause disk contention, or because backup policies need to diverge — moving
it is a connection-string change with no application code involved.

### Exposure

The Prefect server is an internal component. It has no authentication model suitable
for end users, and its UI exposes every run in the system. It must not be reachable
from the public internet; the operator UI is reached through whatever administrative
access path the deployment provides. All user-facing run information is served through
Manta's own API, under Manta's own access control.

## Terminology reference

| Term | Meaning |
| --- | --- |
| Flow | A Python function Prefect tracks as a unit of work |
| Flow run | One tracked execution of a flow |
| Task | A tracked unit inside a flow |
| Deployment | A named, remotely-triggerable registration of a flow against a work pool |
| Work pool | A queue routing flow runs to infrastructure that can execute them |
| Worker | A process that polls one work pool and executes what it finds |
| Subflow | A flow run linked as a child of another flow run |
| Result | A flow run's return value, persisted so other processes can read it |
| State | `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CRASHED`, `CANCELLED` |
