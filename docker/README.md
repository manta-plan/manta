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

- **postgres** — the app database. Also hosts the Prefect server's own
  `prefect` database (created idempotently on every start via `post_start`):
  Prefect's default SQLite store throws "database is locked" under the
  concurrent writes that start as soon as workers poll it.
- **prefect-server** — workflow orchestration API + UI
  ([localhost:4200](http://localhost:4200)), state in postgres (see above).
- **seaweedfs** — S3-compatible object storage (see
  [S3FileStorageService](../backend/src/manta/services/s3_file_storage_service.py)),
  running via SeaweedFS's own `mini` command (single-container
  master+volume+filer+S3+Admin UI, purpose-built for dev/small-scale use).
  Once running, the Admin UI (bucket/object browser, cluster status) is at
  `http://localhost:23646` by default (`SEAWEEDFS_ADMIN_PORT` in
  [`backend/.env`](../backend/.env)).
- **keycloak** - identity provider, you can access it with bootstrap credentials
  via [localhost:8080](http://localhost:8080)

## Playbook execution (`--profile playbooks`)

Everything a playbook run needs to actually execute is gated behind the
`playbooks` compose profile, because the worker image is a heavyweight build
(two pixi environments including the PyPSA solver stack):

```bash
docker compose --env-file ../backend/.env -f compose-dev-services.yaml --profile playbooks up
```

The work pools are **docker-type**: every job — each playbook run and each
block run — executes in its own throwaway container, spawned from the image
built by [worker.Dockerfile](worker.Dockerfile) with the right pixi
environment activated (`docker ps` during a run shows them come and go).

- **playbooks-provision** — one-shot: creates the docker work pools (their job
  templates carry the image, network, volumes, and environment every job
  container gets) and registers a Prefect deployment per
  [manta-batteries](../manta-batteries) block plus the playbook orchestrator.
  Idempotent — re-running updates templates and deployments in place, which is
  also how image or wiring changes roll out.
- **prefect-worker-orchestrator** / **prefect-worker-pypsa** — thin
  dispatchers, one per pool: they poll for work and ask the docker daemon to
  run each job. They mount `/var/run/docker.sock` for that, which is
  root-equivalent access to the host's docker — fine for this dev-only stack,
  and the jobs run as *sibling* containers on the host daemon, not nested ones.

Rebuild the image after changing `manta-blocks` or `manta-batteries`
(`docker compose ... --profile playbooks build`); re-`up` re-provisions.

Block results (record pointers, not model data) are persisted to the
`prefect-results` volume mounted into every job container; model data itself
lives in SeaweedFS under `s3://manta/<project>/runs/<run>/`. To seed a tiny
example input network for trying a run end to end:

```bash
docker compose --env-file ../backend/.env -f compose-dev-services.yaml --profile playbooks \
  run --rm --no-deps -e AWS_ACCESS_KEY_ID=dev -e AWS_SECRET_ACCESS_KEY=dev -e AWS_ENDPOINT_URL=http://seaweedfs:8333 \
  prefect-worker-pypsa pixi run -e pypsa python -m manta_batteries.examples.seed_network
```

Process pools (jobs as worker subprocesses, no docker-in-the-loop) remain
available for running outside this stack — set `MANTA_POOL_TYPE=process` for
the provision script and start workers inside the pixi environments; see
[manta-batteries/README.md](../manta-batteries/README.md). Kubernetes work
pools (the future `manta-infra` repo from the playbooks proposal)
intentionally do not exist yet; these services are their local stand-in.

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
