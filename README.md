<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Manta

<!-- --8<-- [start:docs-preamble] -->
[![Backend tests](https://github.com/manta-plan/manta/actions/workflows/backend-test.yml/badge.svg?branch=main)](https://github.com/manta-plan/manta/actions/workflows/backend-test.yml?query=branch%3Amain)
[![Playbook tests](https://github.com/manta-plan/manta/actions/workflows/playbook-test.yml/badge.svg?branch=main)](https://github.com/manta-plan/manta/actions/workflows/playbook-test.yml?query=branch%3Amain)
[![Runner tests](https://github.com/manta-plan/manta/actions/workflows/runner-test.yml/badge.svg?branch=main)](https://github.com/manta-plan/manta/actions/workflows/runner-test.yml?query=branch%3Amain)
[![Documentation](https://readthedocs.org/projects/manta-plan/badge/?version=latest)](https://manta-plan.readthedocs.io/en/latest/)
[![Licence](https://img.shields.io/github/license/manta-plan/manta)](https://github.com/manta-plan/manta/blob/main/LICENSE)
[![REUSE status](https://api.reuse.software/badge/github.com/manta-plan/manta)](https://api.reuse.software/info/github.com/manta-plan/manta)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196)](https://www.conventionalcommits.org/en/v1.0.0/)

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
Model, Inspect and Report tabs read. The `--profile temporary-quack-setup`
flag is what starts the record server; without it the frontend has no records
to show.

All configuration comes from [`backend/.env`](backend/.env), which already has
working local defaults. Nothing needs to be filled in.

The first run takes a while: besides building the images, the backend
downloads the example data on its first boot and puts it in SeaweedFS. Wait
until the `frontend` container has started. The record server picks the
example data up within a minute after that.

### 3. Open Manta

Go to `localhost:5173` and log in as `manta-admin`,
password `manta-admin`.

The services also have their own UIs, which help when you want to see what is
happening under the hood:

| Service       | URL             | Notes                          |
| ------------- | --------------- | ------------------------------ |
| Prefect       | localhost:4200  | playbook runs and their steps  |
| SeaweedFS     | localhost:23646 | buckets and stored files       |
| Keycloak      | localhost:8080  | admin console, `admin`/`admin` |
| Record server | localhost:8010  | catalogue API, token `devtoken` |

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
> The backend and frontend containers from the setup above use the same ports
> as the dev servers. Stop them first (see [Stopping](#stopping)).

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
VITE_RECORD_SERVER=localhost:8010 VITE_RECORD_TOKEN=devtoken pnpm dev
```

The dev server proxies `/v1` requests to the backend on `localhost:8000`. The
two `VITE_RECORD_*` variables point the frontend straight at the record server
(`QUACK_SERVER_PORT` and `QUACK_TOKEN` in [`backend/.env`](backend/.env));
without them the data catalogue reports `VITE_RECORD_SERVER is not set.`
Open `localhost:5173` and log in as above.

If you only work on the frontend, you can skip step 2 and start the services
with `compose-dev-backend.yaml` instead (same flags), which runs the backend
in Docker too. For more on each part, see
[backend/README.md](backend/README.md) and
[frontend/README.md](frontend/README.md).

## Repository Structure

This is a monorepo containing the backend, frontend, and local deployment
tooling:

```
manta/
├── backend/           # Python/FastAPI backend — see backend/README.md
├── frontend/          # React/Vite frontend — see frontend/README.md
├── playbook/          # blocks and playbooks: the modelling framework
├── playbook-library/  # the blocks and playbooks Manta ships, built on PyPSA
└── docker/            # local dev services (Postgres, SeaweedFS) — see docker/README.md
```

`playbook/` and `playbook-library/` are standalone Python packages that know nothing
about the Manta app: the first defines what a block and a playbook are, the second is
the modelling content built on them. They live here for now, but are written to move
to their own repositories.

See [CONTRIBUTING.md](CONTRIBUTING.md) for coding standards and architecture, and
the package-level READMEs for setup instructions:

- [backend/README.md](backend/README.md) for the FastAPI backend.
- [frontend/README.md](frontend/README.md) for the React frontend.
- [playbook/README.md](playbook/README.md) for writing blocks and playbooks.
- [playbook-library/README.md](playbook-library/README.md) for the blocks and playbooks Manta ships.
- [docker/README.md](docker/README.md) for local services and Docker notes.

<!-- --8<-- [start:docs-test-deployment] -->
## Internal test deployment

> [!IMPORTANT]
> This section is for the Manta core team. It documents an ad-hoc prototype
> instance on our own GCP project and is not a supported way to deploy Manta.
> To try Manta yourself, see [Running Manta locally](https://github.com/manta-plan/manta/blob/main/README.md#running-manta-locally).

Currently a test instance is deployed for internal purposes, in `europe-north2`
(Stockholm). Its container name is `manta-adhoc-2` (no points for creativity).

### Setup

On a base Debian image, we begin by refreshing the system and installing docker. See [the official docs](https://docs.docker.com/engine/install/debian/).

```bash
sudo apt update # update repositories
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

You need to additionally, explicitly pull down manta afterwards.

```bash
git clone https://github.com/manta-plan/manta
```

Now we can spin up the dependencies:

```bash
cd manta
docker compose -f docker/compose-dev-services.yaml --env-file backend/.env up -d
```

Now that the dependencies are running, it's time to spin up a runtime instance.

Install python, nodejs, pnpm, and uv, to allow for building and running the application.

```bash
sudo apt install nodejs npm
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv python install
curl -fsSL https://get.pnpm.io/install.sh | sh -
source ~/.bashrc # reload to get access to pnpm
```

Spin up the backend

```bash
cd backend
uv sync
uv run uvicorn manta.main:app --host 0.0.0.0 --port 8000
```

Build and serve the frontend, which proxies `/v1` requests to the backend on
port 8000

```bash
cd ../frontend
pnpm install && pnpm build
pnpm preview --host 0.0.0.0
```

Both run in an attached mode, you can use `ctrl-z` to pause them and then `bg` to
background the task, or use `nohup` / `disown` to detach them from your ssh process and let them live on. 

### Summary

This is a very quick and dirty guide to spinning up an instance of manta. There
are many many issues with this right now, but a proper deployment with terraform
etc. is on the way.
<!-- --8<-- [end:docs-test-deployment] -->
