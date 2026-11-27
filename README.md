# Manta

<!-- --8<-- [start:docs-preamble] -->
Manta is an open-source energy modeling tool, designed to make cutting-edge
energy models accessible to all.

For more details on the vision and roadmap, see our website: https://manta-plan.org/
<!-- --8<-- [end:docs-preamble] -->

> [!NOTE]
> This repository and the instructions below are for **developers**. If you
> want to use Manta or join as a beta tester, please wait for the MVP, which
> will be available at a public URL in the near future.

<!-- --8<-- [start:docs-install] -->
## Running Manta locally

The quickest way to try Manta is to run the whole stack (frontend, backend and
all supporting services) in Docker. If you want to work on the backend or
frontend, see [Development setup](#development-setup) below instead.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose
  (Docker Desktop includes it; on Linux, add the
  [Compose plugin](https://docs.docker.com/compose/install/linux/))

### 1. Clone the repository

```bash
git clone https://github.com/manta-plan/manta.git
cd manta
```

### 2. Start Manta

From the repo root:

```bash
docker compose -f docker/compose-dev-fullstack.yaml --env-file backend/.env \
  --profile temporary-quack-setup up --build
```

This builds the backend and frontend images and starts them along with
Postgres, SeaweedFS (S3 storage), Prefect, Keycloak, the playbook workers and
the temporary record server (`quack-server`), which serves the example data
records: the list you pick from when creating a project, and the data the
Build, Inspect and Analyse tabs read. The `--profile temporary-quack-setup`
flag is what starts the record server; without it the frontend has no records
to show.

All configuration comes from [`backend/.env`](backend/.env), which already has
working local defaults. Nothing needs to be filled in.

The first run takes a while: besides building the images, the backend
downloads the example data on its first boot and puts it in SeaweedFS. Wait
until the `frontend` container has started. The record server picks the
example data up within a minute after that.

### 3. Open Manta

Go to `localhost` (port 80) and log in as `manta-admin`,
password `manta-admin`. Everything goes through this one address: the frontend's
Caddy serves the app and forwards `/v1` to the backend and `/api` and `/quack`
to the record server, so there is nothing else to configure. To use another host
port, set `FRONTEND_PORT` in [`backend/.env`](backend/.env).

The services also have their own UIs, which help when you want to see what is
happening under the hood:

| Service       | URL             | Notes                          |
| ------------- | --------------- | ------------------------------ |
| Backend API   | localhost:8000  | the API the app calls under `/v1` |
| Prefect       | localhost:4200  | playbook runs and their steps  |
| SeaweedFS     | localhost:23646 | buckets and stored files       |
| Keycloak      | localhost:8080  | admin console, `admin`/`admin` |
| Record server | localhost:8010  | catalogue API, token `devtoken`; reachable from this machine only, and through the app at `localhost/api` |

### Stopping

To stop the containers, press `Ctrl+C` in their terminal, or run from the repo
root:

```bash
docker compose -f docker/compose-dev-fullstack.yaml --env-file backend/.env \
  --profile temporary-quack-setup down
```

This does not delete your local data (database, stored files, Keycloak
state), so the next `up` picks up where you left off.

To wipe everything and start from scratch next time, add `-v` to also delete
the data volumes:

```bash
docker compose -f docker/compose-dev-fullstack.yaml --env-file backend/.env \
  --profile temporary-quack-setup down -v
```

See [docker/README.md](docker/README.md) for details on each service.

### Development setup

When working on Manta, run the backend and frontend from source so changes
reload on save, and keep only the supporting services in Docker.

> [!NOTE]
> The backend container from the setup above uses the same port (8000) as the
> backend dev server. Stop it first (see [Stopping](#stopping)). The frontend
> container is on port 80, so the Vite dev server (5173) can run beside it.

#### Prerequisites

In addition to Docker:

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs
  the right Python for you)
- [Node.js](https://nodejs.org/en/download) and pnpm (run
  `corepack enable pnpm` to get the version pinned in
  [`frontend/package.json`](frontend/package.json), or see the
  [pnpm docs](https://pnpm.io/installation))

#### 1. Start the services

From the repo root:

```bash
docker compose -f docker/compose-dev-services.yaml --env-file backend/.env \
  --profile temporary-quack-setup up
```

This starts everything except the backend and frontend, including the record
server. Leave it running and wait until the logs settle. Stop it the same way
as above, using `compose-dev-services.yaml` in place of
`compose-dev-fullstack.yaml`.

#### 2. Start the backend

In a second terminal:

```bash
cd backend
uv sync
uv run uvicorn manta.main:app --reload --host 0.0.0.0 --port 8000
```

On startup the backend applies database migrations, creates the storage
bucket and checks that Prefect is reachable, then serves the API on
`localhost:8000`. `--reload` restarts it whenever you save a file under
`backend/`.

#### 3. Start the frontend

In a third terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

The dev server proxies `/v1` requests to the backend on `localhost:8000`, and
`/api` and `/quack` to the record server on `localhost:8010`. It reads the
record server's port and token (`QUACK_SERVER_PORT` and `QUACK_TOKEN`) from
[`backend/.env`](backend/.env), so no environment variables are needed. Open
`localhost:5173` and log in as above.

If you only work on the frontend, you can skip step 2 and start the services
with `compose-dev-backend.yaml` instead (same flags), which runs the backend
in Docker too. For more on each part, see
[backend/README.md](backend/README.md) and
[frontend/README.md](frontend/README.md).

## Testing a pull request

Use this walk-through to check a change end to end in the browser, whether it
is your own or someone else's. It takes about fifteen minutes once the stack is
up.

### 1. Start the PR's stack

Check out the PR's branch (`gh pr checkout <number>`), then follow
[Running Manta locally](#running-manta-locally) with `up --build`, so the
images are built from that branch.

The volumes keep the database, Keycloak and the example data between runs. When
the PR touches the database, the realm or the example data, start from clean
volumes (`down -v`, see [Stopping](#stopping)) so you test what a new user gets.

### 2. Know what the app talks to

For now the frontend has two dependencies that don't know about each other:

| The app talks to                           | For                                                         |
| ------------------------------------------ | ----------------------------------------------------------- |
| Main backend (`/v1`)                       | Login, the Projects page, the Run tab (playbooks and runs)  |
| Temporary record server (`/api`, `/quack`) | The Data Catalogue, and the Build, Inspect and Analyse tabs |

> [!NOTE]
> The record server is temporary. It is to be replaced by a real record session
> server in the backend, and the frontend will be adjusted to match. Much of
> this section, the split above and the list of what doesn't connect, will then
> change, and another PR will update it.

The two are linked only by the data record's name. That has consequences for
what you see:

- The record server always opens the same record for a project's tabs,
  `BEL-pre-aggregated-incl-patches-incl-results`, whatever project you opened.
- A run executes on a copy of the data record you pick, in the backend's own
  storage. **The record server never sees its result**, so Inspect and Analyse
  show the BEL record, not your run.
- A run does not take a scenario yet: the scenario you pick is only a label.
- Scenarios you draft on Build stay drafts, kept in your browser's local
  storage, because there is no backend endpoint for them yet.
- The feedback dialog talks to neither. It posts to an external endpoint set by
  `VITE_FEEDBACK_ENDPOINT`, which the stack doesn't set, so locally the dialog
  opens and closes but sends nothing.

### 3. Walk through the app

1. **Log in** at `localhost` as `manta-admin` with password `manta-admin`, or
   choose **Continue as guest**.
2. **Open the existing project**, "Example project", from the Projects page.
3. **Explore Build.** Click through the Record tree, a tile or a table cell
   to open level pages, and open the table, the map and the chart full screen.
   Everything here only reads.
4. **Draft a scenario.** In the Scenarios panel, create a scenario and add a
   change to it. It appears as a draft and stays one.
5. **Create a run** on the Run tab, with **New run**:
   - Scenario: any
   - Playbook: `cluster-expand-dispatch`
   - Data record: `ac-dc-meshed`
   - Expansion mode: `overnight`

   Then click **Create Run**. This opens a draft run with its steps (blocks).
   Click a step to change its configuration in the right sidebar. The defaults
   are the safest choice.
6. **Start the run** (**Start run**) and watch the steps go through to
   completed. The Prefect UI at `localhost:4200` shows each step's flow run and
   logs.
7. **Open Inspect.** It shows the BEL record's results (see above), so use it
   to check the level pages and the run-result views work.
8. **Open Analyse** and explore its reports and widgets.
9. **Open the feedback dialog** and check it opens, takes a message and closes.

### What works today

| What | Works | Not yet |
| --- | --- | --- |
| Playbooks | `cluster-expand-dispatch` in `overnight` mode, from the app | `expand` and the `myopic` and `perfect` modes have not been checked in the app. `expand` on `BEL-pre-aggregated` is covered through the API, see [Run a playbook through the REST API](docs/contributing/manual-run.md) |
| Data records | `ac-dc-meshed` for a run | The other example records are listed (`model-energy`, the `BEL-*` ones) but not yet checked with a run from the app. `BEL-full-res` is large |
| Data shown in Build, Inspect and Analyse | `BEL-pre-aggregated-incl-patches-incl-results` | Any other record, and the result of your own run |
| Scenarios | Drafting and editing in the browser | Saving them, and running on them |
| Login | Username and password, and guest | |

If you check another playbook, record or mode, add what you found to this table
in your PR.

### If something breaks

Say which PR or commit you tested, the step, and what you expected against what
you saw, with a screenshot. For the stack's side of it:

```bash
docker compose -f docker/compose-dev-fullstack.yaml --env-file backend/.env \
  --profile temporary-quack-setup logs --tail 100 backend
```

The same works for `frontend` (Caddy), `quack-server` and the workers. To drive
a run without the web app, which separates a frontend fault from a backend one,
use [Run a playbook through the REST API](docs/contributing/manual-run.md).

## Repository Structure

This is a monorepo containing the backend, frontend, and local deployment
tooling:

```
manta/
├── backend/           # Python/FastAPI backend — see backend/README.md
├── frontend/          # React/Vite frontend — see frontend/README.md
├── runner/            # the Prefect runtime that executes playbooks — see runner/README.md
├── playbook/          # blocks and playbooks: the modelling framework
├── playbook-library/  # the blocks and playbooks Manta ships, built on PyPSA
├── docker/            # the local stack (Postgres, SeaweedFS, Prefect, Keycloak, record server) — see docker/README.md
├── docs/              # the documentation site, built with MkDocs
├── scripts/deploy/    # scripts the Deploy workflow runs to set up a VM
└── tools/docs/        # helpers that generate parts of the docs site
```

`playbook/` and `playbook-library/` are standalone Python packages that know nothing
about the Manta app: the first defines what a block and a playbook are, the second is
the modelling content built on them. They live here for now, but are written to move
to their own repositories.

See [CONTRIBUTING.md](CONTRIBUTING.md) for coding standards and architecture, and
the package-level READMEs for setup instructions:

- [backend/README.md](backend/README.md) for the FastAPI backend.
- [frontend/README.md](frontend/README.md) for the React frontend.
- [runner/README.md](runner/README.md) for the Prefect runtime that executes playbooks.
- [playbook/README.md](playbook/README.md) for writing blocks and playbooks.
- [playbook-library/README.md](playbook-library/README.md) for the blocks and playbooks Manta ships.
- [docker/README.md](docker/README.md) for local services and Docker notes.

<!-- --8<-- [start:docs-test-deployment] -->
## Internal test deployment

> [!IMPORTANT]
> This section is for the Manta core team. It documents an ad-hoc prototype
> instance on our own GCP project and is not a supported way to deploy Manta.
> To try Manta yourself, see [Running Manta locally](https://github.com/manta-plan/manta/blob/main/README.md#running-manta-locally).

Currently a test instance is deployed for internal purposes on a GCP VM, at
`https://<vm_name>.manta-plan.org`. It runs the same stack as
[Running Manta locally](#running-manta-locally): `compose-dev-fullstack.yaml`
with the `temporary-quack-setup` profile, so the frontend's Caddy serves the app
on ports 80 and 443.

### Deploying

Deployments are manual and run from GitHub: **Actions > Deploy > Run workflow**
([`deploy.yml`](.github/workflows/deploy.yml)). The inputs are:

| Input         | Meaning                                                       |
| ------------- | ------------------------------------------------------------- |
| `vm_name`     | VM name, also the subdomain (`<vm_name>.manta-plan.org`)      |
| `gcp_project` | GCP project that hosts the VM                                 |
| `ref`         | branch, tag or SHA to deploy (default `main`)                 |
| `reset_data`  | delete the instance's data (database, files, users) first     |
| `dry_run`     | only check the configuration, authentication and permissions  |

The workflow builds the images in CI and pushes them to GitHub Container
Registry as `ghcr.io/manta-plan/manta-<name>`, tagged with the commit SHA. It
skips any image that already exists for the commit. It then creates the VM and
its firewall rules if they don't exist, points a Cloud DNS record at it, and
runs [`scripts/deploy/vm-deploy.sh`](scripts/deploy/vm-deploy.sh) on the VM.
The VM builds nothing: it checks out `ref` for the compose files, pulls the
images and starts the stack
([`docker/compose-deploy.yaml`](docker/compose-deploy.yaml) points the services
at them and adds restart policies). The frontend's Caddy gets and renews a
Let's Encrypt certificate for the hostname by itself, so nothing else needs to
be installed or configured by hand. The certificate lives in the `caddy-data`
volume and survives redeployments, including `reset_data`. For how HTTPS is
configured, see [docker/README.md](docker/README.md#https-on-a-domain).

The VM pulls the images without logging in, so the five packages must be public.
GitHub creates them private on the first publish: in the organisation's
**Packages**, open each `manta-*` package, then **Package settings > Change
visibility > Public**. This is needed once.

### Deploying the `app` branch

[`deploy-app.yml`](.github/workflows/deploy-app.yml) calls the same workflow on
every push to the `app` branch and deploys it to `app.manta-plan.org`. To
release, fast-forward `app` to the commit you want to ship:

```bash
git push origin main:app
```

It stays off until you set one repository variable (**Settings > Secrets and
variables > Actions > Variables**): `AUTO_DEPLOY_GCP_PROJECT`, the GCP project
that hosts the VM. Delete it to turn the automatic deploy off again. A push runs
the workflow file of the pushed branch, so create `app` from a `main` that
already has `deploy-app.yml`. Deployments to one VM queue rather than overlap.

Pushing to `app` releases to the live instance, so restrict who can push to it
in the branch settings.

### Summary

This is still a prototype: one VM, no backups and development credentials. A
proper deployment with Terraform and the like is on the way.
<!-- --8<-- [end:docs-test-deployment] -->
