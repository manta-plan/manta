# Manta Docker

Local development services, run via [Docker Compose](https://docs.docker.com/compose/).

**Not meant for production.** These compose files are for local dev only —
no restart policy (crashes should be visible, not silently healed), default
credentials, no backups/replication. Production deployment is a separate,
not-yet-addressed concern.

## Usage

```bash
docker compose --env-file ../backend/.env -f compose-dev-services.yaml up
```

Configuration (credentials, port) lives in [`backend/.env`](../backend/.env)
— the same file the backend app reads — not here, so there's one source of
truth instead of two.

## Services

- **postgres** — the app database. Also hosts Keycloak's and Prefect's own
  databases, each created by the matching script in `conf/postgres-init/` on
  the volume's **first boot only** — after pulling a change to those
  scripts, remove the volume to re-initialise (this wipes local dev data):
  `docker volume rm manta_postgres-data`.
- **seaweedfs** — S3-compatible object storage (see
  [S3FileStorageService](../backend/src/manta/services/s3_file_storage_service.py)),
  running via SeaweedFS's own `mini` command (single-container
  master+volume+filer+S3+Admin UI, purpose-built for dev/small-scale use).
  Once running, the Admin UI (bucket/object browser, cluster status) is at
  `http://localhost:23646` by default (`SEAWEEDFS_ADMIN_PORT` in
  [`backend/.env`](../backend/.env)).
- **prefect-server** — workflow orchestration, backed by its own Postgres
  database (not SQLite). UI at [localhost:4200](http://localhost:4200).
- **keycloak** - identity provider, you can access it with bootstrap credentials
  via [localhost:8080](http://localhost:8080)

## Testing

`compose-test-services.yaml` is used only by the backend's integration test
suite — see
[backend/tests/integration/conftest.py](../backend/tests/integration/conftest.py).
It `include`s `compose-dev-services.yaml` wholesale (every service, as-is) and
gives the stack its own Compose project name. Host ports are randomized via
[`.env.test`](.env.test), loaded on top of `backend/.env`, so a test run never
clashes with a locally running dev stack. You don't need to run any of this
yourself; `uv run pytest tests/integration` boots and tears it down
automatically.

## Deployment

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
