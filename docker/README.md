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

To run the app itself in containers too, use one of the files layered on top:

- `compose-dev-backend.yaml` — every service above plus the backend.
- `compose-dev-fullstack.yaml` — everything in `compose-dev-backend.yaml`
  plus the frontend.

```bash
docker compose --env-file ../backend/.env -f compose-dev-fullstack.yaml up --build
```

To run the backend or frontend on the host instead (`uv run manta`,
`pnpm dev`), stop its container first: they share ports.

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
- **quack-server** — *temporary*, **opt-in** (compose profile
  `temporary-quack-setup`: add `--profile temporary-quack-setup` to the `up`
  command above, or name the service) record server that exposes a datarecord to the
  browser (DuckDB-Wasm) over the Quack protocol, used to port the Model /
  Inspect / Report tabs before datarecord is integrated into the backend. Copied
  from baby-manta's `server/`; see [quack-server/README.md](quack-server/README.md).
  Listens on `localhost:${QUACK_SERVER_PORT:-8010}`, token `${QUACK_TOKEN:-devtoken}`.
  It reads records from `docker/quack-server/data/records` (git-ignored): put
  datarecord stores there before starting, otherwise it serves nothing.

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
