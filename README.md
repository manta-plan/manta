# Manta

Manta is an open-source energy modeling tool, designed to make cutting-edge
energy models accessible to all.

For more details on the vision and roadmap, see our website: https://manta-plan.org/

> [!NOTE]
> This repository and the instructions below are for **developers**. If you
> want to use Manta or join as a beta tester, please wait for the MVP, which
> will be available at a public URL in the near future.

## Running Manta locally

The quickest way to try Manta is to run the whole stack on your own machine:
the supporting services in Docker, and the backend and frontend from source.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose
  (Docker Desktop includes it; on Linux, add the
  [Compose plugin](https://docs.docker.com/compose/install/linux/))
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs
  the right Python for you)
- [Node.js](https://nodejs.org/en/download) and pnpm (run
  `corepack enable pnpm` to get the version pinned in
  [`frontend/package.json`](frontend/package.json), or see the
  [pnpm docs](https://pnpm.io/installation))

### 1. Clone the repository

```bash
git clone https://github.com/manta-plan/manta.git
cd manta
```

### 2. Start the services

From the repo root:

```bash
docker compose -f docker/compose-dev-services.yaml --env-file backend/.env up
```

This starts Postgres, SeaweedFS (S3 storage), Prefect, Keycloak and the
playbook workers, and builds the images playbook steps run in. The first run
takes a while. Leave it running and wait until the logs settle. All
configuration comes from [`backend/.env`](backend/.env), which already has
working local defaults. Nothing needs to be filled in.

### 3. Build the frontend

In a second terminal:

```bash
cd frontend
pnpm install
pnpm build
```

### 4. Start the backend

```bash
cd ..
cd backend
uv sync
uv run manta
```

On startup the backend applies database migrations, creates the storage
bucket and checks that Prefect is reachable, then serves both the API and the
frontend you just built. 

The Prefect work pools and deployments that run
playbooks are set up by the `playbooks-provision` container in the Docker
stack, not by the backend.

### 5. Open Manta

Go to `localhost:8000` and log in as `manta-admin`,
password `manta-admin`.

The services also have their own UIs, which help when you want to see what is
happening under the hood:

| Service   | URL                                       | Notes                          |
| --------- | ----------------------------------------- | ------------------------------ |
| Prefect   | localhost:4200  | playbook runs and their steps  |
| SeaweedFS | localhost:23646 | buckets and stored files       |
| Keycloak  | localhost:8080  | admin console, `admin`/`admin` |


### Stopping

To stop Docker containers, press
`Ctrl+C` in their terminal, or run from the repo root:

```bash
docker compose -f docker/compose-dev-services.yaml --env-file backend/.env down
```

This will not delete your local data (database, stored files, Keycloak state) so the next
`up` command picks up where you left off.

To wipe everything and start from scratch next time, add `-v` to also delete
the data volumes:

```bash
docker compose -f docker/compose-dev-services.yaml --env-file backend/.env down -v
```

See [docker/README.md](docker/README.md) for details on each service.

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

## Internal test deployment

> [!IMPORTANT]
> This section is for the Manta core team. It documents an ad-hoc prototype
> instance on our own GCP project and is not a supported way to deploy Manta.
> To try Manta yourself, see [Running Manta locally](#running-manta-locally).

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

Build the frontend files

```bash
cd frontend
pnpm install && pnpm build
```

Spin up the backend

```bash
cd ../backend
uv sync
uv run uvicorn manta.main:app --host 0.0.0.0 --port 8000
```

This runs in an attached mode, you can use `ctrl-z` to pause it and then `bg` to
background the task, or use `nohup` / `disown` to detach it from your ssh process and let it live on. 

### Summary

This is a very quick and dirty guide to spinning up an instance of manta. There
are many many issues with this right now, but a proper deployment with terraform
etc. is on the way.
