# How to test the playbook PoC

This walks through running Manta's playbook execution end to end, from a clean
machine: boot the stack, start the backend, run the built-in
`cluster-expand-dispatch` playbook against a small PyPSA network, watch each
block execute in its own container, and inspect the results.

**What's under the hood** (details in the package READMEs):

- [`manta-blocks/`](manta-blocks/README.md) — blocks & playbooks, orchestration-agnostic.
- [`backend/`](backend/README.md) — the API (validates runs early, exposes
  statuses/steps/outputs) and the execution runtime: the `run-playbook` Prefect
  flow that spawns one bare container per block step. Block code itself never
  runs in the backend.
- [`docker/`](docker/README.md) — Prefect server on Postgres, and the one
  blocks-runner image (manta-blocks + PyPSA, no Prefect/Manta) every block
  executes in.

**Prerequisites**: Docker with the compose plugin, [uv](https://docs.astral.sh/uv/),
and free default ports `5432, 8333, 23646, 4200, 8080, 8000` (all configurable in
`backend/.env`). Building the frontend additionally needs `pnpm` (optional, see
step 2).

Paths in the commands are relative, so **each step says which directory to run
its commands from** — stick to that. Steps 3 and 4 must also run **in one shell
session**, because they reuse the `$PROJECT_UUID` / `$RUN_UUID` variables set by
earlier commands.

## 0. Start clean (only if you ran an older stack before)

The Postgres init scripts (which create Keycloak's and Prefect's databases) only
run on the volume's **first** boot, and compose reuses previously built images.
If this machine ever ran the Manta dev stack before, reset it once. From the
**repo root**:

```bash
docker compose --env-file backend/.env -f docker/compose-dev-services.yaml down -v --remove-orphans
```

```bash
docker rmi -f manta-blocks-runner:latest manta-prefect-worker:latest
```

## 1. Boot the services

From the **repo root**:

```bash
docker compose --env-file backend/.env -f docker/compose-dev-services.yaml up --build
```

This stays in the foreground, streaming every service's logs — leave it running
and use a **second terminal** for everything that follows. The first boot builds
the blocks-runner image (Python 3.12 + PyPSA + HiGHS + manta-blocks) — expect
**3–6 minutes** once; it's cached afterwards. `blocks-runner` is a one-shot
service that only exists to build and sanity-check that image, then exits; the
backend spawns block containers from it during runs.

Verify it came up — in the second terminal, from the **repo root**:

```bash
docker compose --env-file backend/.env -f docker/compose-dev-services.yaml ps -a
```

Expected: `postgres`, `seaweedfs`, `keycloak`, `prefect-server` **healthy**, and
`blocks-runner` **Exited (0)** — that exit is correct. The Prefect UI is at
<http://localhost:4200>; its *Deployments* page stays empty until the backend
starts (step 2), because the backend is what serves the `run-playbook` flow.

## 2. Start the backend

From **`backend/`**:

```bash
uv sync
```

The app serves the frontend build from `frontend/dist`, so that directory must
exist. Either build it properly (needs pnpm) — from **`frontend/`**:

```bash
pnpm install && pnpm build
```

…or, if you only want to exercise the API, drop in any placeholder — from the
**repo root**:

```bash
mkdir -p frontend/dist && echo '<html><body>manta</body></html>' > frontend/dist/index.html
```

Then start the app (it runs DB migrations, creates the S3 bucket, and starts
the flow-serving subprocesses that register the `run-playbook` and
`pi-digit-stats` deployments with Prefect) — from **`backend/`**:

```bash
uv run manta
```

This also stays in the foreground with the app's logs. **Leave it running and
open a third terminal in `backend/` for steps 3–4.** Check it's alive:

```bash
curl -s http://localhost:8000/v1/health
```

## 3. Run a playbook

Run all of step 3 and 4 **in one shell, from `backend/`** (the upload/download
commands use paths relative to it, and later commands reuse the
`$PROJECT_UUID` / `$RUN_UUID` variables set by earlier ones).

### 3.1 See what's on offer

**From `backend/`, same shell:**

```bash
curl -s http://localhost:8000/v1/playbooks | python3 -m json.tool
```

You get each built-in playbook's document (steps, wiring, `when:` conditions)
plus a ready-to-edit `default_config`.

### 3.2 Create a project and upload an input network

**From `backend/`, same shell:**

```bash
PROJECT_UUID=$(curl -s -X POST http://localhost:8000/v1/projects -H 'Content-Type: application/json' -d '{"name": "Playbook test drive"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['uuid'])") && echo "PROJECT_UUID=$PROJECT_UUID"
```

Upload the committed test network (one bus, one extendable generator, 24 hourly
snapshots — solves instantly) into the project's storage, reusing the backend's
own S3 config:

**From `backend/`, same shell:**

```bash
uv run python -c "
from manta.config.s3_config import get_s3_client, s3_bucket_name
get_s3_client().upload_file('tests/integration/fixtures/network.nc', s3_bucket_name(), '$PROJECT_UUID/network.nc')
print('uploaded network.nc')
"
```

### 3.3 Start the run

**From `backend/`, same shell:**

```bash
RUN_UUID=$(curl -s -X POST http://localhost:8000/v1/runs -H 'Content-Type: application/json' -d '{
  "project_uuid": "'$PROJECT_UUID'",
  "playbook_name": "cluster-expand-dispatch",
  "input_file": "network.nc",
  "config": {
    "globals": {"expansion_mode": "overnight"},
    "cluster": {"n_hours": 3},
    "expansion_overnight": {},
    "expansion_myopic": {},
    "dispatch": {"optimize_config": {"horizon": 4}}
  }
}' | python3 -c "import sys,json; print(json.load(sys.stdin)['uuid'])") && echo "RUN_UUID=$RUN_UUID"
```

Behind that one request: the config was validated against the block catalogue
*before* anything started, the input file was copied to the run's own storage
prefix, and the `run-playbook` deployment was dispatched.

### 3.4 Watch it execute

Re-run until `status` is `COMPLETED` (≈ 1–2 minutes; `PENDING` → `RUNNING` →
`COMPLETED`):

**From `backend/`, same shell:**

```bash
curl -s http://localhost:8000/v1/runs/$RUN_UUID | python3 -m json.tool
```

While it runs, each step really is its own container from the runner image —
you can watch them come and go:

**From `backend/`, same shell:**

```bash
docker ps --filter ancestor=manta-blocks-runner:latest --format 'table {{.Names}}\t{{.Status}}'
```

You'll see one short-lived container per block, named
`manta-block-<step>-<id>`; the playbook flow itself runs inside the backend's
flow-serving process. The same picture, with each container's logs, is in the
Prefect UI at <http://localhost:4200/runs>: the `run-<RUN_UUID>` flow run has
one task run per step, named `<step>[<block>]`.

Per-step states via the API (note `expansion_myopic` never appears — its
`when:` condition switched it off):

**From `backend/`, same shell:**

```bash
curl -s http://localhost:8000/v1/runs/$RUN_UUID/steps | python3 -m json.tool
```

Aggregated logs:

**From `backend/`, same shell:**

```bash
curl -s http://localhost:8000/v1/runs/$RUN_UUID/logs | python3 -m json.tool
```

### 3.5 See the results

Every artifact of the run lives under one prefix,
`s3://manta/<project>/runs/<run>/` — the input copy and one output file per
executed step:

**From `backend/`, same shell:**

```bash
curl -s http://localhost:8000/v1/runs/$RUN_UUID/outputs | python3 -m json.tool
```

Browse the same files visually in the SeaweedFS admin UI at
<http://localhost:23646> (bucket `manta`), or pull a result down:

**From `backend/`, same shell:**

```bash
uv run python -c "
from manta.config.s3_config import get_s3_client, s3_bucket_name
get_s3_client().download_file(s3_bucket_name(), '$PROJECT_UUID/runs/$RUN_UUID/steps/dispatch.nc', '/tmp/dispatch.nc')
print('downloaded /tmp/dispatch.nc')
"
```

To open it as a PyPSA network, use the manta-blocks dev environment (the
backend has no PyPSA).

**From `manta-blocks/` — the one exception in this step (any shell):**

```bash
uv sync --extra pypsa && uv run python -c "
import pypsa
n = pypsa.Network('/tmp/dispatch.nc')
print(len(n.snapshots), 'snapshots (clustered down from 24)')
print(n.generators[['p_nom', 'p_nom_extendable']])
"
```

Expected: 8 snapshots, and `gen` fixed (non-extendable) at ~50 MW — the
capacity the expansion block chose, which dispatch was not allowed to change.

The run also shows up in the frontend's Runs page (<http://localhost:8000>, if
you built the frontend) and stays reproducible from the `runs` table alone:

**From `backend/`, same shell:**

```bash
docker exec manta-postgres-1 psql -U dev -d manta -c "select playbook_name, input_url, output_prefix from runs"
```

## 4. See validation catch a bad run early

Ask for the myopic branch, whose block needs an `investment_period` dimension
the input data doesn't declare — the API refuses with the exact step and
problem, and nothing is dispatched:

**From `backend/`, same shell:**

```bash
curl -s -X POST http://localhost:8000/v1/runs -H 'Content-Type: application/json' -d '{
  "project_uuid": "'$PROJECT_UUID'",
  "playbook_name": "cluster-expand-dispatch",
  "input_file": "network.nc",
  "config": {
    "globals": {"expansion_mode": "myopic"},
    "cluster": {"n_hours": 3},
    "expansion_overnight": {}, "expansion_myopic": {}, "dispatch": {}
  }
}' | python3 -m json.tool
```

A wrongly-typed setting (`"cluster": {"n_hours": "three"}`) is likewise refused
with `step: cluster, field: [n_hours]`.

## 5. The automated suites

Each package tests its own layer; the backend integration suite is the
end-to-end proof (it boots its own isolated stack on random ports — the dev
stack from step 1 can stay up, but note the first session builds the runner
image if you removed it).

From **`manta-blocks/`**:

```bash
uv run pytest
```

From **`backend/`**:

```bash
uv run pytest tests/unit
```

```bash
uv run pytest tests/integration/routes/v1/test_playbook_run_route.py -q
```

(The full `tests/integration` suite also works but additionally needs `pnpm`
for the frontend-serving test.)

## Troubleshooting

- **`run-playbook/run-playbook` not found when creating a run** — the app's
  flow-serving subprocess hasn't registered the deployment yet (it does so a
  few seconds after `uv run manta` starts) or died; restart the app and watch
  its log for "Prefect flow-serving process started".
- **Run stuck in PENDING** — the serving subprocess isn't picking runs up;
  restart the app.
- **A step fails with "blocks runner image ... not available locally"** — the
  image was never built or was removed: re-run step 1 (`up --build`).
- **Prefect server unhealthy after changing DB settings** — the Prefect
  database is created on the Postgres volume's first boot only: `down -v` and
  boot again (step 0).
- **Changed code in `manta-blocks/` but runs behave old** — the runner image is
  baked at build time: re-run step 1's `up --build`.
- Block container logs are relayed live into each step's task run in the
  Prefect UI (and aggregated under `/v1/runs/{uuid}/logs`).

## Teardown

Stop the app and the compose process with Ctrl-C in their terminals, then from
the **repo root**:

```bash
docker compose --env-file backend/.env -f docker/compose-dev-services.yaml down -v --remove-orphans
```

(`-v` wipes Postgres/SeaweedFS data so the next boot re-initialises; drop it to
keep your projects and runs.)
