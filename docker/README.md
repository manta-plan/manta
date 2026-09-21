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
  databases, created by the init scripts in `conf/postgres-init/` on the
  volume's **first boot only** — after pulling a change to those scripts, run
  `docker compose --env-file ../backend/.env -f compose-dev-services.yaml down -v`
  once to re-initialise (this wipes local dev data).
- **seaweedfs** — S3-compatible object storage (see
  [S3FileStorageService](../backend/src/manta/services/s3_file_storage_service.py)),
  running via SeaweedFS's own `mini` command (single-container
  master+volume+filer+S3+Admin UI, purpose-built for dev/small-scale use).
  Once running, the Admin UI (bucket/object browser, cluster status) is at
  `http://localhost:23646` by default (`SEAWEEDFS_ADMIN_PORT` in
  [`backend/.env`](../backend/.env)).
- **keycloak** - identity provider, you can access it with bootstrap credentials
  via [localhost:8080](http://localhost:8080)
- **prefect-server** — workflow orchestration, backed by its own Postgres
  database (not SQLite). UI at [localhost:4200](http://localhost:4200).
- **blocks-runner** — one-shot boot step that builds (and sanity-checks) the
  blocks runner image from
  [`blocks-runner.Dockerfile`](blocks-runner.Dockerfile), then exits.
  **One container per block step** of a playbook run is spawned from this image
  (see [manta-runtime](../manta-runtime/README.md)); those containers are
  siblings of this stack (they won't appear in `docker compose ps`; they join
  the stack's network and remove themselves when done), and contain only
  manta-blocks and the blocks' dependencies — no Prefect, no Manta.
- **blocks-exec** — one-shot boot step that builds the **execution image**
  ([`exec.Dockerfile`](exec.Dockerfile)) as a thin layer over the blocks runner
  image, adding Prefect and manta-runtime. A Prefect worker never marks a flow
  run completed itself — the state and result are reported by the engine inside
  the container — so a bare block image would run its block, exit 0, and leave
  the run pending for ever. Block authors neither build nor name this image.
- **playbooks-provision** — one-shot boot step that creates both work pools,
  registers the `run-block` and `run-playbook` deployments, and points Prefect's
  result storage at the object store, then exits. Idempotent, so re-running `up`
  is how an image or wiring change rolls out.
- **prefect-worker-blocks** — long-lived dispatcher for the **docker** pool: it
  asks the daemon for a fresh container per block step and reaps it. It never
  imports a block and holds no block dependencies.
- **prefect-worker-orchestrator** — long-lived, and what actually runs a
  playbook. It drains the **process** pool, and each playbook run holds one of its
  slots for the run's whole duration while its steps run elsewhere. This is also
  why a run survives restarting the backend: the backend dispatches at a
  deployment by name and is never in the execution path.

The last three run the **control image**
([`control.Dockerfile`](control.Dockerfile)): Prefect's own image plus
manta-runtime and manta-blocks, with neither pixi nor PyPSA. Orchestration only
moves record pointers between steps and resolves blocks from the committed
catalogue, so it never imports one.

Only the blocks worker mounts the host's docker socket, since block containers
are siblings on that daemon rather than children of it. Socket access is
root-equivalent control of the host's docker and is acceptable for this dev
stack only; Kubernetes replaces it with a k8s work pool.

A step's output record travels back through Prefect's result storage, which
points at SeaweedFS rather than a shared volume — a volume would be the one thing
tying every container to a single machine. Only the small record pointers go that
way; model data goes straight from block to object store.

The first `up` builds the blocks runner image, which installs the PyPSA stack —
expect a few minutes once; later boots reuse the cache. After changing
`manta-blocks/` or `manta-runtime/`, rebuild with `... up --build`.

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
