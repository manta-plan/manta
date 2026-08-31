# 06 — Execution lifecycle

End to end, in three phases: what happens when blocks are released, what happens while
a user authors a playbook, and what happens when they press Run.

## Phase 0 — Release time

Performed by `blocks` CI and by whoever operates the deployment. Nothing here is on a
user's request path, and none of it involves Manta's backend.

1. **Build each environment.** One container image per environment, from that
   environment's dependency set. Third-party plug-in environments are built from their
   own repositories.
2. **Generate the catalogue.** Run `python -m blocks` inside each environment, merge
   the results, inject the image reference for each environment, publish
   `catalogue.json` with a version.
3. **Create work pools and start workers.** One pool per environment (`manta-<env>`)
   plus one for the orchestrator of each playbook. A pool with no worker accumulates queued runs
   forever, so this is a prerequisite, not an optimisation. In production these are
   declared in the cluster manifests rather than created by hand.
4. **Apply deployments.** One `run_block/<block>-<env>` per pair, plus
   `run_playbook/<orchestrator-env>`.
5. **Manta loads the catalogue** at startup and serves it at `GET /v1/blocks`.

## Phase 1 — Design time

The user is in the browser. Nothing executes; no solver starts.

1. The frontend fetches the catalogue and renders a palette of available blocks. Each
   block's settings form is generated from its JSON Schema, skipping fields marked
   `x-manta-input` — those are wiring points, not user input.
2. The user adds steps, wires outputs to inputs, sets conditions and fills in
   settings. The frontend saves the playbook document and configuration document to
   Manta.
3. `POST /v1/playbooks/{uuid}/validate` → Manta rebuilds the playbook from its
   document using the catalogue, calls `issues(config)`, and returns the list. Each
   issue carries the step path and the exact field, so the canvas marks the offending
   node and the form marks the offending input.
4. `GET /v1/playbooks/{uuid}/graph` → nodes, edges, per-step dimensions, and which
   steps will run under the current settings. The canvas draws it, including the
   branches conditions have switched off.

Every step of this path runs in Manta's backend, which cannot import a single one of
the blocks involved.

## Phase 2 — Run time

```mermaid
sequenceDiagram
    autonumber
    actor U as Analyst (browser)
    participant API as Manta Backend
    participant DB as Application DB
    participant P as Prefect Server
    participant O as Orchestrator Worker
    participant W as Environment Worker
    participant S3 as Object Store

    U->>API: POST /v1/runs {playbook_uuid, config}
    API->>DB: load project, playbook doc, config
    API->>API: rebuild playbook from doc + catalogue, validate
    Note over API: 422 with the issue list if invalid
    API->>S3: resolve the seed data record
    API->>P: run_deployment("run_playbook/{env}", {doc, config, record, catalogue}, timeout=0)
    P-->>API: flow_run_id
    API->>DB: INSERT run(project_id, playbook_id, prefect_flow_run_id)
    API-->>U: 201 {run uuid}

    P->>O: dispatch run_playbook
    O->>O: rebuild playbook from doc + catalogue

    loop each active step
        O->>P: run_deployment("run_block/{block}-{env}", {block, config, record, inputs})
        P->>W: dispatch run_block on pool manta-{env}
        W->>W: import the block class (available here, and only here)
        W->>S3: read the input record
        W->>W: execute the block
        W->>S3: write the result artefact
        W-->>P: COMPLETED, result {url}
        P-->>O: child finished, result {url}
    end

    O-->>P: COMPLETED, final record {url}
```

Note that the backend's involvement ends at step 8. Everything after that happens
without it, and would continue happening if it were restarted.

### Submission, in detail

`POST /v1/runs` does five things, in order:

1. Loads the project, playbook document and configuration from the database.
2. Rebuilds the playbook using the catalogue and validates it. An invalid playbook
   fails here, with the issue list, before anything is submitted — a run that could
   not succeed is never started.
3. Resolves the seed `DataRecord`: the URL of the project's input model in the object
   store.
4. Submits `run_playbook/<env>` with the document, configuration, record and
   catalogue as parameters, and returns immediately.
5. Inserts the run row linking the project and playbook to the returned flow run id.

The playbook travels **as its document**, not as a reference. What runs is exactly
what was on screen when the user pressed Run, even if the stored playbook is edited a
second later.

### Dispatch, in detail

The orchestrator worker rebuilds the playbook from the document. It uses the catalogue
rather than importing blocks, so the orchestrator environment needs no modelling
dependencies at all — it is a small, cheap, long-lived process.

For each step that the conditions say will run, it:

- collects the wired inputs — records from specific earlier steps;
- calls `run_deployment` for that step's `(block, environment)` deployment, passing
  the block name, that step's settings, the spine record and the wired inputs;
- blocks until the child finishes, and takes the returned record as the new spine
  record.

Nested playbooks recurse: an inner playbook becomes a subflow of the outer one, and
its steps become subflows of that.

Each step's flow is named after the step, so the run tree in Prefect mirrors the graph
the user drew.

### Execution, in detail

The environment worker picks up `run_block` and, for the first time in the whole
lifecycle, imports the actual block class. This is the only process in the system that
can — it is running in the environment the block declared.

It merges the wired records into the block's settings, validates the merged settings
in full (so a record wired to the wrong kind of setting is caught here rather than
surfacing deep inside the block), instantiates the block fresh for this run, and calls
it. The block reads its input from the object store, does its work, writes its result,
and returns a record pointing at it.

A fresh instance per run means a block never carries state between runs.

## How data moves between steps

Steps run in different processes, usually different containers, possibly on different
machines. The only thing that crosses between them is a URL.

```mermaid
flowchart LR
    s3[("Object Store")]
    a["Step A<br/>worker: pypsa"]
    b["Step B<br/>worker: pypsa"]

    a -->|writes artefact| s3
    a -. returns the record URL .-> b
    s3 -->|reads artefact| b
```

Two mechanisms are involved and both must work:

- **The record URL** travels through Prefect as the child flow run's return value.
  Because parent and child are separate processes, this requires Prefect result
  persistence backed by storage both can reach.
- **The artefact itself** lives in the object store, written by one worker and read by
  the next.

Neither shared memory nor a shared filesystem is available, and the design must not
grow a dependency on either.

## Observing a run

The frontend polls `GET /v1/runs/{uuid}`. Manta looks up the Prefect flow run id, asks
Prefect for the run's state and for the states of its children, and returns both.
Because each child flow is named after its step, the frontend can colour the same
graph it drew at design time — no separate progress model is needed.

`GET /v1/runs/{uuid}/logs` returns the accumulated logs together with the current
state, so a caller knows whether they are still growing. [**TODO**: we probably need an endpoint to get the log of each block/step, not accumulated over the entire playbook.]

Per-step detail is reported where Prefect can supply it and omitted where it cannot,
so a missing detail degrades the response rather than failing it.

## Failure modes

| Failure | What happens | Who notices |
| --- | --- | --- |
| Playbook invalid | Rejected at submission with the issue list; nothing is queued | User, immediately |
| Prefect server unreachable at submission | `POST /v1/runs` fails; no run row is written | User, immediately |
| Work pool exists but has no worker | The run queues indefinitely in `PENDING` | Nobody, unless monitored — see [08](08-open-questions.md) |
| A block raises | That child flow run fails; the orchestrator's `run_deployment` raises; the parent run fails | Run state and logs |
| Orchestrator worker dies mid-run | The parent run fails or crashes; already-dispatched children continue and are orphaned | Run state |
| Manta backend restarts mid-run | Nothing. The run continues; state is read live on the next request | Nobody |
| Object store unreachable from a worker | That block fails at read or write | Run logs |

The row worth designing against is the orchestrator dying: it holds a process open for
the entire duration of a playbook. Keeping it on stable, long-lived infrastructure
rather than on ephemeral per-run infrastructure is the mitigation, and it is why the
orchestrator runs on a process pool even in Kubernetes deployments. See
[07](07-deployment-topology.md).

## What the user sees

| Moment | Response |
| --- | --- |
| Press Run | `201` with a run identifier, immediately — no waiting |
| While running | Overall state plus per-step state, mapped onto the graph they authored |
| A step fails | The failed node is identified by name, with that step's logs |
| Complete | Terminal state and the output record, available for download or onward analysis |
