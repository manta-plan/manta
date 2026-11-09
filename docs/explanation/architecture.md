<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Architecture

A project in Manta moves from sign-in through modelling, running, inspecting and reporting, as the [user guide](../user-guide/index.md) describes.
A playbook run is the Run stage of that path.
The backend starts it for a project, and the run saves its results as revisions in a data record.

Manta keeps its modelling code apart from the code that schedules and runs it.
So you can write and test a block without any of Manta's services.
This page covers the design principles, who and what Manta talks to, the packages and their dependencies, the running services and the backend inside.
It then follows one playbook run, and states where each kind of data is kept and which technologies Manta uses.
It assumes you know what a block and a playbook are, which are defined in the [user guide concepts page](../user-guide/concepts.md).

## Design principles

Five decisions answer most questions about why Manta is built the way it is.

The backend orchestrates runs and never runs modelling code.
It hands each run to Prefect, the orchestration tool, and reads the state back.
So the backend process stays small and installs no solver and no modelling framework.
[Orchestration with Prefect](orchestration.md) explains how Manta uses Prefect.

Prefect is the only record of a run's state.
The `runs` table links a project to a Prefect flow run and has no status, progress or log column.
State kept in two places drifts apart, so the backend reads it from Prefect on every request.

The environment is the unit of isolation.
A block names the environment it needs, and that name picks the container image its step runs in.
So one playbook can chain blocks whose dependencies could never be installed side by side, such as two modelling frameworks.

Everything about a block is known without importing it.
No single Python environment can import every block, so Manta describes each block as data, in the catalogue.
The backend checks a playbook made of blocks it could never import.
[Blocks, playbooks and the catalogue](blocks-and-playbooks.md) explains the design.

The playbook document is the form in which a playbook travels.
The backend sends the document itself to Prefect, not a name to look up later.
So a run uses the playbook as it was when the run started, even if the library changes afterwards.

## Manta and the world around it

Manta is one system to the people who use it and to the services it relies on.

```mermaid
flowchart LR
    modeller["Modeller<br/>(browser)"] -- "HTTPS" --> manta["Manta"]
    author["Block author"] -- "writes blocks<br/>and playbooks" --> library["Block library<br/>(playbook-library)"]
    library -- "block image<br/>and catalogue" --> manta
    manta -- "OpenID Connect" --> idp["Identity provider<br/>(Keycloak)"]
```

A modeller uses Manta through the web app.
[Users and scope](scope.md) describes each kind of user Manta is designed for, and the constraints they place on it.

A block author never deploys code into the backend process.
Their blocks reach Manta in two forms: a container image that runs them, and an entry in the catalogue that describes them.
Today the only block library is `playbook-library`, in this repository, and the block image is built from it on the local machine.

Manta signs users in through an identity provider over OpenID Connect.
The local stack runs Keycloak for this.
[Planned changes](planned-changes.md) lists the external systems Manta does not talk to yet, such as a container registry and a solver licence server.

## The packages and their dependencies

Manta is a monorepo of five packages.

| Package            | Directory           | What it is                                                                                   |
| ------------------ | ------------------- | -------------------------------------------------------------------------------------------- |
| `manta`            | `backend/`          | The FastAPI web service: REST API, authentication, projects and runs.                        |
| frontend           | `frontend/`         | The React web app, served by Vite, which passes `/v1` requests to the backend.              |
| `playbook`         | `playbook/`         | The modelling framework: what a block and a playbook are, how to check and run a playbook.  |
| `playbook-library` | `playbook-library/` | The blocks and playbooks Manta ships, built on PyPSA.                                        |
| `runner`           | `runner/`           | The Prefect flows that run a playbook and run each of its blocks in a container.             |

The arrows below show which package imports which.
A dotted arrow marks an import that is forbidden, and the test named on it fails if the import appears.

```mermaid
flowchart TB
    frontend["frontend"] -- "HTTP /v1" --> backend["manta (backend)"]
    backend --> runner["runner"]
    backend --> library["playbook-library"]
    backend --> framework["playbook"]
    backend --> orchestration["Prefect"]
    runner --> framework
    runner --> orchestration
    library --> framework

    runner -. "must not import<br/>runner/tests/test_isolation.py" .-> library
    runner -. "must not import<br/>runner/tests/test_isolation.py" .-> backend
    framework -. "must not import<br/>playbook/.../tests/test_isolation.py" .-> orchestration
    framework -. "must not import<br/>playbook/.../tests/test_isolation.py" .-> backend
    library -. "must not import<br/>playbook_library/tests/test_isolation.py" .-> orchestration
    library -. "must not import<br/>playbook_library/tests/test_isolation.py" .-> backend
```

The solid arrows point from a package to what it imports.
The backend imports all three Python packages and Prefect, and `runner` imports `playbook` and Prefect.
`playbook-library` imports only `playbook` among Manta's packages.
The frontend imports none of them and reaches the backend over HTTP.

Each dotted arrow is a rule, checked by an import scan in the test file written on it:

- `runner` must not import `manta` or `playbook_library`, which [`runner/tests/test_isolation.py`](https://github.com/manta-plan/manta/blob/main/runner/tests/test_isolation.py) checks.
- `playbook` must not import `manta`, Prefect, Docker, Kubernetes, Celery or Airflow, which [`playbook/src/playbook/tests/test_isolation.py`](https://github.com/manta-plan/manta/blob/main/playbook/src/playbook/tests/test_isolation.py) checks.
- `playbook-library` must not import the same set, which [`playbook-library/src/playbook_library/tests/test_isolation.py`](https://github.com/manta-plan/manta/blob/main/playbook-library/src/playbook_library/tests/test_isolation.py) checks.
- Inside `playbook`, the `playbook.blocks` layer must not import `playbook.playbooks`, which the `playbook` test file above also checks.

These rules let `playbook` and `playbook-library` work outside Manta.
A modeller runs a block as a plain method call, and tests it with no Prefect server or Docker daemon.
What schedules that call plugs in from outside through the `BlockRunner` protocol in `playbook.playbooks`, which `runner` implements as `PrefectBlockRunner`.
The `runner` rule keeps it reusable by any block library, because depending on one library would tie the runtime to it.
The `playbook.blocks` rule means a block library depends on the block layer alone.

The backend's import of `playbook-library` is the one edge that goes against this design.
The backend reads the shipped playbooks and the block catalogue from it directly, and a comment in `backend/pyproject.toml` marks that dependency as a shortcut.

The backend imports `playbook` itself, rather than talking to Prefect alone.
With Prefect alone, the backend could start runs but could neither check a playbook nor describe its blocks.
The web app could then build no settings forms and mark no problems.
The only way round that is a second copy of the checks in TypeScript, kept in step by hand.
`playbook` could also run as an HTTP service of its own.
It needs no process of its own, because it has no heavy dependencies.
That would cost a service, a schema and a deployment, and pays off only if something other than Python needs the playbook engine.

## The running system

A running Manta is the backend process, the web app's Vite server and the services in [`docker/compose-dev-services.yaml`](https://github.com/manta-plan/manta/blob/main/docker/compose-dev-services.yaml).
The diagram shows the long-lived parts and the connections between them.

```mermaid
flowchart LR
    browser["Browser"] -- "HTTP: web app and /v1 API" --> vite["Vite server<br/>(frontend)"]
    vite -- "HTTP: /v1 API" --> backend["Backend<br/>(manta, FastAPI)"]
    backend -- "log in, verify tokens" --> keycloak["Keycloak<br/>(identity provider)"]
    backend -- "users, projects, runs" --> postgres[("Postgres")]
    backend -- "start runs, read states and logs" --> prefect["Prefect server"]
    backend -- "S3 API" --> seaweed[("SeaweedFS<br/>(S3 object store)")]
    keycloak -- "own database" --> postgres
    prefect -- "own database" --> postgres
    pworker["Playbook worker<br/>(process pool manta-playbooks)"] -- "polls, starts run-block" --> prefect
    bworker["Block worker<br/>(docker pool manta-blocks)"] -- "polls" --> prefect
    bworker -- "Docker socket:<br/>starts a container per step" --> blocks["Block containers"]
    blocks -- "state and logs" --> prefect
    blocks -- "read and write model revisions,<br/>write the result record" --> seaweed
    pworker -- "read each step's result record" --> seaweed
```

The browser loads the web app from Vite on port 5173, and Vite passes every `/v1` request to the backend on port 8000.
So the browser never calls the backend directly, and the backend serves the REST API only.
The backend logs a user in through Keycloak and checks each request's token against it.
Postgres holds three databases: the backend's own, Keycloak's and Prefect's.

Two Prefect workers run playbooks, and neither imports a block.
The playbook worker drains the process pool `manta-playbooks` and runs the `run-playbook` flow, which walks the playbook and starts one `run-block` flow run per step.
The block worker drains the docker pool `manta-blocks`, and starts a fresh container for each `run-block` flow run through the host's Docker socket.
That container runs from the image of the environment the block declares, which contains `playbook-library`, the block's dependencies, Prefect and `runner`.

A playbook run holds a process for its whole length, because it waits on every step.
Running it on a long-lived process worker, instead of in a container per run, means an evicted container cannot take the run down.
It also means a playbook run continues while the backend restarts, because the backend is not in the execution path.

Two one-shot services run when the stack starts and then exit.
`block-image-builder-pypsa` builds the block image for the `pypsa` environment.
`playbooks-provision` runs `python -m runner.deploy`, which creates both work pools, registers the two deployments, and points Prefect's result storage at the object store.

## Inside the backend

The backend is one FastAPI process.
Each route checks its request and hands it to one service, and each service holds the logic for one kind of thing.

```mermaid
flowchart LR
    routes["Routes<br/>(routes/v1)"] --> auth["AuthService"]
    routes --> projects["ProjectService"]
    routes --> playbooks["PlaybookService"]
    routes --> runs["RunService"]
    runs --> playbooks
    runs --> storage["S3FileStorageService"]
    auth -- "log in,<br/>verify tokens" --> keycloak["Keycloak"]
    auth --> db[("Postgres")]
    projects --> db
    runs --> db
    runs -- "start flow runs,<br/>read states and logs" --> prefect["Prefect server"]
    runs -- "deployment name,<br/>catalogue encoding" --> runner["runner"]
    playbooks -- "build and check<br/>a playbook" --> framework["playbook"]
    playbooks -- "shipped playbooks<br/>and catalogue" --> library["playbook-library"]
    storage -- "S3 API" --> s3[("Object store")]
```

`PlaybookService` serves the playbooks that `playbook-library` ships.
It lists them, returns one with each step's block summary and settings schema from the catalogue, and checks a set of settings against one.
`RunService` checks the settings through `PlaybookService` before it starts a run.
It then starts the `run-playbook` flow run and records it, and later reads the run's state, steps, log and output files back.
`AuthService` logs a user in through Keycloak and checks each request's token.

The backend reads the catalogue and the playbooks from `playbook-library` but never runs a block.
It stores no playbook of its own and serves no catalogue or playbook drawing yet, which [Planned changes](planned-changes.md) covers.

!!! info "See also"

    [Contributing: Backend](../contributing/backend.md#coding-standards) sets out the backend's layers: routes, services, entities and the request and result models.

## A run from click to result

One playbook run passes through the backend, Prefect, both workers and one container per step.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant API as Backend
    participant DB as Postgres
    participant P as Prefect server
    participant PW as Playbook worker
    participant BW as Block worker
    participant C as Block container
    participant S3 as Object store

    B->>API: POST /v1/runs (project, playbook, settings, starting record)
    API->>API: check the settings against the block catalogue
    API->>P: start a run-playbook flow run (document, settings, record, catalogue)
    API->>DB: insert a run row with the flow run id
    API-->>B: 201 Created, with the run's uuid
    PW->>P: pick up the run-playbook flow run
    PW->>PW: check the playbook again and work out the active steps
    loop each active step, in order
        PW->>P: start a run-block flow run (block, settings, record, inputs, image)
        BW->>P: pick up the run-block flow run
        BW->>C: start a fresh container from the environment's image
        C->>S3: read the input revision, write a new revision
        C->>S3: write the output record to result storage
        C->>P: report the flow run as completed
        PW->>S3: read the output record
    end
    PW->>P: report the run-playbook flow run as completed
    B->>API: GET /v1/runs/{uuid}/steps
    API->>DB: read the run row
    API->>P: read the flow run and its child flow runs
    API-->>B: status of each step
```

The numbers in the diagram give the order of the calls.
The backend checks the settings before it starts anything.
It refuses a run that cannot work with HTTP 422 and a list of every issue.
It then asks Prefect for a `run-playbook` flow run without waiting for it, and records the flow run's id in a new `runs` row.

The playbook worker runs `execute_playbook` from `playbook` with a `PrefectBlockRunner`.
`execute_playbook` checks the playbook a second time against the catalogue it was handed, because the worker cannot import a block library.
For each active step, `PrefectBlockRunner` starts a `run-block` flow run and waits for it.
It passes the image of the block's environment as a job variable, so the block worker knows which image to start.

Inside the container, `run-block` loads the block library, looks the block up by name and runs it on the input record.
The block reads the model from the record's revision and writes its result as a new revision in the same store.
The returned record, a store URL and a revision uuid, goes to Prefect's result storage on the object store.
The playbook worker reads it back as the next step's input.
Each `run-block` flow run is a child of its `run-playbook` flow run.
So the backend finds a run's steps by asking Prefect for the children of one flow run.

## Where data lives

Each kind of data has one home, and Prefect holds pointers to model data but never the data itself.

| Store              | What it contains                                                                                                                                                  |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Postgres           | The backend's `users`, `projects` and `runs` tables, plus Keycloak's and Prefect's own databases. A `runs` row has the project, the playbook name and the Prefect flow run id. |
| Object store       | The versioned stores of model data (datarecord stores), where every block writes a new revision of the model. Prefect's result storage, under `prefect-results/`. The folder `<project uuid>/runs/<run uuid>/output/`, where the backend lists a run's output files. |
| Prefect            | Each flow run's parameters, state and logs. The parameters of a `run-playbook` flow run are the playbook document, the settings, the starting record and the catalogue. |

A record is a pointer, never the model itself: a store URL and the uuid of one revision in that store.
The store URL is either a local directory or an `s3://` address.
Model data never passes through Prefect or the workers, because only records cross between processes.

No block writes to a run's output folder, so the models a run produces are found only as revisions in the datarecord store.

The `runs` table does not contain a run's settings or status.
The backend reads both back from the Prefect flow run each time a client asks for a run.
[Orchestration with Prefect](orchestration.md#the-runs-table) gives the reasons.

## Technologies

Each layer of Manta uses one main technology.

| Layer                | Technology                                                                                  |
| -------------------- | ------------------------------------------------------------------------------------------- |
| Web app              | TypeScript and React                                                                        |
| Backend              | Python 3.14, FastAPI, SQLAlchemy and Alembic                                                |
| Modelling packages   | Python 3.12 or later, Pydantic, and pixi for the block environments                         |
| Orchestration        | Prefect 3, with its own database on the shared Postgres server                              |
| Block execution      | A Prefect work pool of type `docker`, with one fresh container per step                     |
| Application database | PostgreSQL                                                                                  |
| Model data           | datarecord stores, which are Parquet files read through DuckDB, in an S3-compatible object store |
| Object store         | SeaweedFS on the local stack                                                                |
| Identity provider    | Keycloak, over OpenID Connect                                                               |

Every part except the web app is Python, so a modeller who writes a block reads the same language as the code that runs it.
The model data format comes from the [datarecord](https://github.com/energy-models/datarecord) package, and only `playbook-library` reads or writes it.

## Where to read next

The package READMEs go into each package in detail:

- [`playbook/README.md`](https://github.com/manta-plan/manta/blob/main/playbook/README.md) explains how to write a block and a playbook, and how a playbook is checked.
- [`playbook-library/README.md`](https://github.com/manta-plan/manta/blob/main/playbook-library/README.md) lists the shipped blocks and playbooks and their environments.
- [`runner/README.md`](https://github.com/manta-plan/manta/blob/main/runner/README.md) explains the two flows, the work pools and the block images.
- [`docker/README.md`](https://github.com/manta-plan/manta/blob/main/docker/README.md) describes each local service.
- [`CONTRIBUTING.md`](https://github.com/manta-plan/manta/blob/main/CONTRIBUTING.md) sets out the backend's layers and the coding standards.

The other explanation pages go deeper into one part each:

- [Orchestration with Prefect](orchestration.md) explains the two flows, the work pools and why run state stays in Prefect.
- [Blocks, playbooks and the catalogue](blocks-and-playbooks.md) explains how a playbook names, wires and checks blocks it cannot import.
- [Run lifecycle](run-lifecycle.md) explains where a run is checked and what happens when part of it fails.
- [Deployment topology](deployment.md) explains how the stack is set up, and what changes on Kubernetes.
- [Planned changes](planned-changes.md) and [Open questions](open-questions.md) cover what is not built yet.

The reference pages list the interfaces:

- [`playbook` API](../reference/playbook/api.md)
- [`runner` API](../reference/runner/api.md)
- [REST API](../reference/backend/rest-api.md)
