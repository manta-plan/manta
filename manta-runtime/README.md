# Manta Runtime

The execution runtime for [manta-blocks](../manta-blocks/README.md) playbooks: the
**one place in the system that knows Prefect runs them**. Blocks and playbooks stay
orchestration-agnostic, and the Manta backend only talks to the Prefect API by
deployment name — everything in between is this small package.

## How a run works

```
Manta backend ──run_deployment("run-playbook/run-playbook")──▶ Prefect server
                                                                   │
                                              docker worker picks it up
                                                                   │
                              ┌─── container: run-playbook flow ───┐
                              │  validates the playbook document,  │
                              │  walks its steps, and dispatches   │
                              │  each one via PrefectStepRunner    │
                              └──────────────┬────────────────────┘
                                             │ run_deployment("run-block/run-block")
                                             ▼  (one per step, sequentially)
                              ┌─── container: run-block flow ──────┐
                              │  imports the named block, runs it, │
                              │  writes its output + result record │
                              │  under the run's S3 prefix         │
                              └────────────────────────────────────┘
```

- **Two static deployments, ever.** Playbooks, configs, records and output locations
  travel as flow-run *parameters*, so nothing is deployed per playbook or per block,
  and editing a playbook needs no redeployment.
- **One container per block run** (the proposal's isolation requirement): the docker
  work pool spawns a fresh container from the blocks runner image for every
  dispatched flow run. The playbook flow itself also runs in a container, so runs
  survive backend restarts.
- **Results cross containers through S3**: a block flow writes
  `<output_base>.record.json` next to its output and the playbook flow reads it back
  (see `flows.result_record_url` for why, and the TODO about Prefect result storage).

## Deployment & boot

`python -m manta_runtime.deploy` (run automatically by the `prefect-deployer`
service in [docker/compose-dev-services.yaml](../docker/compose-dev-services.yaml))
idempotently creates:

- the `manta-blocks` **docker work pool**, and
- the `run-playbook` / `run-block` **deployments**, pointing at this package as
  installed in the blocks runner image (module-path entrypoints — the proposal's
  "fetch the code locally from the manta-blocks module" for the MVP).

Configuration comes from the environment (all optional, with dev defaults):
`MANTA_BLOCKS_WORK_POOL`, `MANTA_BLOCKS_IMAGE`, `MANTA_DOCKER_NETWORK`, plus the
`PREFECT_API_URL` / `AWS_*` values that are stamped into every job container.

## The future seams, on purpose

- **k8s instead of docker** (post-MVP plan): create a kubernetes work pool in
  `deploy.py` and run a k8s worker; `flows.py` and everything above it stay as they
  are, because they only ever name a work pool.
- **Fetching block code from git** instead of baking it into the image: swap the
  `.deploy(...)` calls for `flow.from_source(<manta-blocks repo url>).deploy(...)`.
  That is also how outside contributors' blocks can eventually run without a PR to
  this repo.
- **Per-environment images**: today every block declares `ENV = "pypsa"` and one
  image serves them all, so `run-block` is a single deployment on a single pool.
  When a second environment appears, this package grows a deployment/pool (or
  image) per environment, keyed off `EnvironmentSpec` — the catalogue and playbook
  validation already carry everything needed.

## Development

```bash
uv sync
uv run pytest
```

The tests here cover the seams (step dispatch, result hand-off, job configuration)
without a Prefect server; the real end-to-end path — API request to finished
containers — is covered by the backend's integration suite.
