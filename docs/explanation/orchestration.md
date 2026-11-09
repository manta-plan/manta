<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Orchestration with Prefect

Manta runs every playbook through [Prefect](https://docs.prefect.io), an open-source tool that runs Python functions as tracked, remote jobs.
This page explains the parts of Prefect that Manta relies on, then how Manta uses them.
After it, you can judge where a change to how runs execute belongs: in Manta's code, or in Prefect's configuration.

Prefect already queues work, tracks its state, retries it, keeps its logs and its history.
So Manta submits work to Prefect and reads it back, and builds none of that itself.

## Prefect in brief

This section names each Prefect idea the rest of the docs use.
Prefect's own [concepts pages](https://docs.prefect.io/v3/concepts) define them in full.

### Flows and flow runs

A Python function decorated with `@flow` is a flow.
Calling a flow creates a flow run: a tracked execution with an id, a state, timestamps and its captured log.
A flow run is a row in Prefect's database, not only a function call.
So any process can ask about it later, even after the process that started it has restarted.

A flow run's state is one of `SCHEDULED`, `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CRASHED` or `CANCELLED`, among a few others.
Manta's run status is this state, read straight from Prefect.

Prefect also has tasks, smaller tracked units inside a flow.
Manta's flows use no tasks.

### The Prefect server

The Prefect server is a REST API, a scheduler and a web UI, with a database of its own.
It stores flow runs, their states, their logs and where their results are.
It runs no flow code itself.

Every process that submits or runs work talks to this API, and to nothing else.
That is why Manta's backend and the processes that run blocks never talk to each other.

### Deployments

To run a flow by calling it, a process has to import the flow and all of the flow's dependencies.
Manta cannot assume that, because the backend cannot import a block.

A Prefect deployment removes the need.
It is a registered, named description of a flow, with where to run it and the infrastructure to run it on.
Its full name is `<flow name>/<deployment name>`.
Any process that reaches the Prefect API can start a run of a deployment from that name alone, with `run_deployment`.
The caller never imports, or even installs, the code that runs.

`run_deployment` called with `timeout=0` returns as soon as Prefect has created the flow run.
Called without it, `run_deployment` waits until the flow run ends.

### Work pools and workers

A deployment belongs to a work pool, which is a named queue of flow runs.
A worker is a long-running process that polls one work pool and starts each flow run queued to it.
The pool's type decides how the worker starts a flow run:

| Pool type    | How the worker starts a flow run                                    |
| ------------ | ------------------------------------------------------------------- |
| `process`    | As a subprocess, in the worker's own Python environment             |
| `docker`     | In a new container, from the image the flow run asks for            |
| `kubernetes` | As a Kubernetes Job, in a new pod that Kubernetes removes afterwards |

A pool, its worker and a deployment are three separate things.
The pool states the kind of infrastructure and its defaults.
The worker creates that infrastructure for each flow run and removes it afterwards.
The deployment states which flow to run and with what.

Prefect creates no pool and starts no worker on its own.
A flow run queued to a pool that no worker polls stays `PENDING` until a worker appears.

### Child flow runs

A flow that calls `run_deployment` without `timeout=0` waits for the new flow run and becomes its parent.
Prefect links the two, so its UI shows the child flow run under its parent, and the parent reads the child's return value.

Manta uses this to run a playbook whose steps need different environments.
A light parent flow starts each step as a child flow run in turn, and does no modelling work itself.
Prefect then provides the order, the waiting, the failure of the parent when a child fails, and the grouped view.

### Results and logs

A flow run's return value is its result.
A parent and its child run in different processes.
So the child writes its result to storage that both can reach, which Prefect calls result persistence.

Prefect captures the log of each flow run and serves it through its API.
Manta reads logs from there and captures none itself.

### What else Prefect provides

Prefect also provides retry policies, timeouts, concurrency limits per work pool, cancellation, a scheduler for repeated runs, and a UI to inspect all of it.
Manta's code contains none of these, and should not reimplement them.
Manta does not configure retries, timeouts or concurrency limits yet.

## How Manta uses Prefect

The [`runner`](../reference/runner/api.md) package contains everything Manta runs on Prefect.
[Architecture](architecture.md#a-run-from-click-to-result) follows one run through these parts.

### Two flows and two deployments

Manta is built from two flows, each with one deployment of the same name:

| Flow           | Deployment                  | Work pool                       | What one flow run does                                                       |
| -------------- | --------------------------- | ------------------------------- | ---------------------------------------------------------------------------- |
| `run-playbook` | `run-playbook/run-playbook` | `manta-playbooks`, type `process` | Rebuilds a playbook from its document, checks it, and starts one `run-block` flow run per active step |
| `run-block`    | `run-block/run-block`       | `manta-blocks`, type `docker`     | Imports one block by name, runs it on its input record, and returns the output record |

One `run-playbook` deployment serves every playbook, because the playbook arrives as a parameter.
One `run-block` deployment serves every block, because the block's name arrives as a parameter.
The image of the block's environment arrives as a job variable on each flow run, so one docker pool serves every environment.

A deployment per block and environment would also work, and would show each block as its own deployment in Prefect's UI.
Manta passes the block as a parameter instead, so a new block needs no new deployment.
Each `run-block` flow run is named `<step>[<block>]`, which still shows the block in the UI.

Both deployments are created once, when the stack starts, by `python -m runner.deploy`.
Running it again updates the pools and deployments rather than duplicating them.
[Deployment topology](deployment.md) describes where the workers run.

### Why the playbook flow runs on a process pool

A `run-playbook` flow run waits for every one of its steps, so it lasts as long as the whole playbook.
In a container per run, that container would idle for hours.
A restart or eviction of it would then fail the run while its steps carry on.
A long-lived process worker costs little, because it mostly waits, and it is already running when a run arrives.
Blocks still get a fresh container each, for isolation between steps.

### What the backend does

The backend does three things with Prefect, and each is small:

- It submits a run. `run_deployment` starts `run-playbook` with the playbook document, the settings, the starting record and the catalogue, with `timeout=0`, and returns the flow run's id.
- It observes a run. It reads the flow run's state, the states of its child flow runs for the status of each step, and the flow run's log.
- It keeps the link. It inserts one row that ties the Manta run to the Prefect flow run id.

The backend never runs flow code and never starts a worker.
So a playbook run continues while the backend restarts, and the backend reads the right state on the next request.

The catalogue crosses into `run-playbook` as a JSON string rather than a dictionary.
Prefect reads a `$ref` key inside a dictionary parameter as a reference to one of its own objects, and the catalogue's JSON schemas contain many.
The [runner README](https://github.com/manta-plan/manta/blob/main/runner/README.md#the-catalogue-crosses-as-a-json-string-never-a-dict) records the failure this avoids.

### The runs table

A row of the `runs` table has an `id`, a `uuid` and a `created_at` time.
It also has the project, the name of the playbook, and the Prefect flow run id.
It has no column for status, progress, settings, result or error.
`GET /v1/runs/{uuid}` and the other run endpoints read those from Prefect on every request.

Three reasons keep that state out of Manta's database.
Prefect already stores it, in one transaction with the work itself.
A copy in Manta would need polling or events to stay current, and would be wrong in between.
A run that fails while the backend restarts still has the right state, in Prefect.

Deleting a project deletes its runs, through a cascade on the foreign key.
The Prefect flow runs they pointed at stay, until Prefect's own retention removes them.

### Prefect's own database

Prefect uses SQLite by default, which suits one machine and one process.
Manta gives it a database of its own on the shared Postgres server instead, with a role of its own.

Prefect cannot keep its tables in a separate schema of a shared database, as [Prefect issue 18015](https://github.com/PrefectHQ/prefect/issues/18015) records.
A separate database and role keep the boundary in Postgres's own permissions instead: Prefect's role cannot read Manta's tables.
An integration test, `test_prefect_database_isolation.py`, checks this.

The Prefect server finds its database through one connection URL, `PREFECT_API_DATABASE_CONNECTION_URL`.
So moving Prefect to a server of its own is a change of that URL, with no change to Manta's code.
That move would pay off if Prefect's queries slowed Manta's API, if Prefect's clean-up competed for the disk, or if the two needed different backups.

### Who can reach Prefect

The Prefect server has no sign-in for end users, and its UI shows every run of every project.
So it is an internal service, and a deployment open to the internet must not expose it.
Users see runs only through Manta's API, which checks that the user owns the run's project.
The local stack publishes the Prefect UI on `localhost:4200`, for development only.

## What this means for a change

A change to what a run does belongs in `playbook` or a block library.
A change to where or how a step runs belongs in a work pool, a worker or an image.
`runner` and the stack set those up.
Retries, timeouts and limits on concurrent runs are Prefect settings, so a change to them belongs in Prefect's configuration, not in the backend.
