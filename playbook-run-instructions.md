# Running a playbook manually

How to start the Manta backend and put a playbook from the standard library
([manta-batteries](manta-batteries/README.md)) through a complete run, by hand.
Everything below was written for the seeded `cluster-expand-dispatch` playbook
against a tiny example network, so the whole thing takes a few minutes.

Prerequisites: [Docker](https://docs.docker.com/) and [uv](https://docs.astral.sh/uv/).
All commands are run from the repo root unless said otherwise.

## 1. Start the services

```bash
cd docker
docker compose --env-file ../backend/.env -f compose-dev-services.yaml --profile playbooks up
```

The `playbooks` profile adds everything that executes runs: two Prefect workers
and a one-shot provision container that creates the work pools and deployments.
Each block runs in its own docker container; the playbook orchestrator runs
in-process in its long-lived worker — see
[docker/README.md](docker/README.md#playbook-execution---profile-playbooks).

The first `up` builds the ~2 GB job image (PyPSA solver stack); expect a few
minutes. Check that provisioning succeeded:

```bash
docker logs manta-playbooks-provision-1
# -> Provisioned 4 block(s) and the orchestrator (5 deployment(s)) from /catalogue.json
```

## 2. Start the backend

In a second terminal:

```bash
cd backend
uv sync
uv run manta
```

The API is now at `http://localhost:8000`.

## 3. Seed an example input network

A run needs input data in the app bucket. This builds a tiny PyPSA network
(1 bus, 1 extendable generator, 1 load, 24 hours) and uploads it to
`s3://manta/examples/network-tiny.nc`:

```bash
cd docker
docker compose --env-file ../backend/.env -f compose-dev-services.yaml --profile playbooks \
  run --rm --no-deps -e AWS_ACCESS_KEY_ID=dev -e AWS_SECRET_ACCESS_KEY=dev -e AWS_ENDPOINT_URL=http://seaweedfs:8333 \
  prefect-worker-orchestrator pixi run -e pypsa python -m manta_batteries.examples.seed_network
```

Only needed once — the file survives restarts (it lives in the SeaweedFS volume).

## 4. Create a project and find the playbook

Runs belong to a project:

```bash
PROJECT=$(curl -s -X POST http://localhost:8000/v1/projects \
  -H 'Content-Type: application/json' \
  -d '{"name": "Playbook test drive"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['uuid'])")
echo "$PROJECT"
```

List the stored playbooks and grab the seeded one's uuid:

```bash
curl -s http://localhost:8000/v1/playbooks | python3 -m json.tool

PLAYBOOK=$(curl -s http://localhost:8000/v1/playbooks | python3 -c \
  "import json,sys; print(next(p['uuid'] for p in json.load(sys.stdin)['items'] if p['name'] == 'cluster-expand-dispatch'))")
```

`GET /v1/playbooks/$PLAYBOOK` shows its full document and default config.

## 5. (Optional) validate a config first

Validation returns problems as data without running anything — try a broken
config to see it catch the error:

```bash
curl -s -X POST http://localhost:8000/v1/playbooks/$PLAYBOOK/validate \
  -H 'Content-Type: application/json' \
  -d '{"config": {"globals": {"expansion_mode": "overnight"}, "cluster": {"n_hours": "three"}}}' \
  | python3 -m json.tool
```

## 6. Start the run

```bash
RUN=$(curl -s -X POST http://localhost:8000/v1/playbooks/$PLAYBOOK/runs \
  -H 'Content-Type: application/json' \
  -d "{
    \"project_uuid\": \"$PROJECT\",
    \"input_key\": \"examples/network-tiny.nc\",
    \"config\": {
      \"globals\": {\"expansion_mode\": \"overnight\"},
      \"cluster\": {\"n_hours\": 3},
      \"dispatch\": {\"optimize_config\": {\"horizon\": 8, \"overlap\": 2}}
    }
  }" | python3 -c "import json,sys; print(json.load(sys.stdin)['uuid'])")
echo "$RUN"
```

Leave out `"config"` entirely to run with the playbook's default config. The
response's `input_key` shows where your input was frozen: every run gets its
own copy under `<project>/runs/<run>/`, so the source file can never change
under a finished run.

## 7. Watch it

```bash
curl -s http://localhost:8000/v1/runs/$RUN | python3 -m json.tool     # status
curl -s http://localhost:8000/v1/runs/$RUN/logs | python3 -m json.tool
```

Status goes `PENDING → RUNNING → COMPLETED` in roughly 2–3 minutes (each of the
three active blocks pays container startup on top of its solve). While it runs:

- `docker ps` shows a container appear and disappear per block — that is each
  block running in its own container.
- The Prefect UI at <http://localhost:4200> shows the `run_playbook` flow run
  and the `run_block` child runs it dispatches.

## 8. Inspect the outputs

```bash
curl -s http://localhost:8000/v1/runs/$RUN/outputs | python3 -m json.tool
```

Expect four files under the run's prefix — the frozen input plus one output per
block, each named after what produced it:

```text
network-tiny.nc
network-tiny-cluster_time.nc
network-tiny-cluster_time-overnight_capacity_expansion.nc
network-tiny-cluster_time-overnight_capacity_expansion-rolling_horizon_dispatch.nc
```

The same files are browsable in the SeaweedFS admin UI at
<http://localhost:23646> (bucket `manta`), and each item's `url` is the
`s3://…` record a block would read it by.

## 9. Stop everything

Stop the backend with `Ctrl-C`, then:

```bash
cd docker
docker compose --env-file ../backend/.env -f compose-dev-services.yaml --profile playbooks down
```

Volumes (database, object store, Prefect state) are kept, so playbooks, runs,
and the seeded network are all still there on the next `up`.

## If something goes wrong

- **Run stays PENDING/SCHEDULED** — a worker isn't picking it up: check
  `docker logs manta-prefect-worker-orchestrator-1` (and `…-pypsa-1`), and that
  `manta-playbooks-provision-1` exited with the success message from step 1.
- **Run FAILED** — read `GET /v1/runs/$RUN/logs` first, then the flow run in
  the Prefect UI; block-level logs live on the `run_block` child runs.
- **404 on the input** — the seed step (3) hasn't run, or `input_key` doesn't
  match the uploaded key.
- **Changed framework or block code** — rebuild the job image and re-`up`
  (provisioning re-runs itself): `docker compose … --profile playbooks build`.
