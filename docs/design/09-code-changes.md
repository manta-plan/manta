# 09 — Changes required to the current code

Every place these documents describe something the code does not yet do. Unlike
[08](08-open-questions.md), which lists undecided questions, everything here is a
decided delta waiting to be implemented.

Two baselines:

- `blocks` — the `feature/playbooks` branch, commit `f6dc47f`.
- `manta` — Prefect integration merged as a demonstration flow (PR #106).

## In `blocks`

### Pass a catalogue reference, not the catalogue body

`run_playbook(playbook, config, record, catalogue)` currently takes the whole catalogue
as a parameter, and `start_run` serialises it into the flow run. That copies a sizeable
JSON blob into Prefect's database for every run and renders it in the UI.

**Change:** take a catalogue version and URI. The orchestrator fetches it from the URI
— the object store, not Manta's API — and caches by version. Rationale and the
alternatives in [05](05-repository-interface.md#the-catalogue-travels-by-reference-not-by-value).

### Do not deploy on the run path

`start_run(..., deploy_first=True)` deploys before every run, touching the Prefect API
once per block in the playbook on each request.

**Change:** make deployment a separate, explicit call. Manta decides when — at release
time, or when a playbook is saved — and records in its own database what has been
applied. See [05](05-repository-interface.md#plan-apply-policy).

### Require `orchestrator_env` rather than defaulting to `current_env()`

`deploy` and `start_run` default the orchestrator environment to whatever environment
the calling process is in. Correct for a command-line user; wrong for a server. Manta's
backend does not run under Pixi, so `current_env()` returns `"default"` and the call
silently resolves to `run_playbook/default` on pool `manta-default`, which does not
exist.

**Change:** make it a required argument.

### Move deployment creation out of `blocks`

`blocks` currently owns both the deployment plan and the code that applies it — the
`Renderer` interface, `ProcessPixiRenderer`, and the deploy path in `deploy.py` /
`control.py`.

**Change:** `blocks` keeps the `DeploymentPlan` and name construction (the plan), plus
a thin runner that runs a playbook against the caller's own Prefect for terminal use
and tests. Creating managed `manta-<env>` deployments, work pools and workers moves to
Manta's apply layer — `docker/` locally, a future `manta-infra` repo for Kubernetes.
See [05](05-repository-interface.md#plan-apply-policy) and
[07](07-deployment-topology.md). This supersedes the earlier plan to keep a
`ProcessPixiProvisioner` in `blocks` and add a `KubernetesProvisioner` beside it.

### Records must live in the object store

`pypsa_helpers.patch_record` writes a new netCDF file beside the input file on a local
filesystem. Once steps run in separate containers this stops working: each pod starts
with an empty disk.

**Change:** read and write records through the object store. Confined to one module by
design. Blocks Kubernetes entirely, and interacts with the open question about what a
record *is* — see [08](08-open-questions.md#record-storage-and-format).

### Declare resource requirements

No block states CPU, memory or wall time, and the `DeploymentPlan` has nowhere to carry
them. Tolerable on a developer's machine; a solver pod with no memory limit is an
outage.

**Change:** a declaration on the block, flowing through the plan into the Job
specification. Whether it is static or expressed relative to the data is open —
[08](08-open-questions.md#resource-requirements-are-not-modelled).

### Populate `EnvironmentSpec.image`

`EnvironmentSpec` declares `image` and `work_pool` fields that nothing ever sets;
`for_block` populates only `name` and `manifest`.

**Change:** have `blocks` CI inject the built image reference per environment when it
publishes the merged catalogue, so the catalogue doubles as the environment-to-image
manifest. See [05](05-repository-interface.md#the-catalogue-contract).

### `MANIFEST` has no meaning on Kubernetes

`MANIFEST` points at a third-party block's Pixi manifest, which is meaningless once
environments are images. **Open:** drop it for container targets, or reinterpret it as
"where to build the image from".

## In `manta`

### Remove the worker subprocess from `create_app()`

`create_app()` spawns `manta.workflows.pi_digit_stats` via `subprocess.Popen`. Worker
lifecycle belongs to whatever manages the infrastructure —
[07](07-deployment-topology.md#who-starts-workers).

### Remove the demonstration workflow

`manta/workflows/pi_digit_stats.py` and the `workflows/` package go. Manta defines no
Prefect flows: the orchestrator flow lives in `blocks`, which is also the answer to the
open question in the superseded `docs/prefect.md` about whether Manta keeps a
`workflows/` module.

### Replace the pi-specific run request

`CreateRunRequest` carries `num_pi_digits`. It becomes `playbook_uuid`, an optional
configuration override, and an input datarecord reference.

### Add the `Playbook` entity

Manta has `Project` and `Run`. It needs a `Playbook` holding the playbook document and
its configuration document, scoped to a project, with `Run` gaining a `playbook_id`.

### Add a database-backed `PlaybookLoader`

`blocks` resolves nested `playbook:` references through a loader interface; only the
file loader exists. Manta implements one that resolves locators against its playbook
table, keyed by playbook UUID — the circular-reference check keys on whatever the
loader reports, so the key must be stable.
See [05](05-repository-interface.md#nested-playbook-resolution).

### Add the catalogue, playbook and graph endpoints

`GET /v1/blocks`, playbook CRUD, `POST /v1/playbooks/{uuid}/validate` and
`GET /v1/playbooks/{uuid}/graph` do not exist. See
[05](05-repository-interface.md#what-manta-exposes-as-a-result).

### Per-step logs

`GET /v1/runs/{uuid}/logs` returns logs accumulated across the whole playbook. The
frontend needs them per step, to show alongside the failed node.

### Store the final output record

**Proposed, not yet decided** — [08](08-open-questions.md#should-manta-store-the-final-output-record).
Run state stays in Prefect, but the output artefact URL outlives Prefect's retention
and is a product object.

### Own deployment creation (the apply layer)

Nothing in Manta creates Prefect flow deployments today; the deploy path lives in
`blocks`. Manta takes the `DeploymentPlan` from `manta-blocks` and applies it: creating
or updating flow deployments bound to `manta-<env>` pools, deciding *when* to apply (at
release time, or when a playbook is saved), and recording in its own database what has
been applied so it is idempotent. Locally this is `docker/`; for Kubernetes it is
`manta-infra`. See [05](05-repository-interface.md#plan-apply-policy).

## Repository structure

### Make `manta` a monorepo with `manta-blocks` as a workspace package

`blocks` is a separate repository today. Move it into `manta` as a workspace package,
keeping only a few example blocks for tests, and set up path-filtered CI that builds,
versions and publishes the `manta-blocks` subtree to PyPI and conda independently of
the application. Manta depends on it as a workspace/path dependency in development and
on the pinned published version in production. Add an import-linter rule forbidding
`manta-blocks → manta` so the published package stays standalone. See
[05](05-repository-interface.md#monorepo-and-the-block-library).

### Extract the PyPSA block library into its own repository

The blocks that need PyPSA move out of the monorepo into a separate library repository
— `manta-batteries` *(proposed name)* — which depends on the published `manta-blocks`,
owns its own environments, images and catalogue CI, and serves as the reference for
third-party block contributors.

### Stand up `manta-infra` (future)

A separate repository for the Kubernetes apply layer: work pools, workers, flow
deployments and the production topology. Not needed until the Kubernetes target — see
[07](07-deployment-topology.md).

## Shared infrastructure

### Configure Prefect result persistence

The orchestrator reads each child's return value across a process boundary. That needs
result persistence backed by storage both sides can reach. Not configured today; the
PoC passes because its tests run in one process. Verify on Compose with separate worker
processes before relying on it.

### Move Prefect off SQLite

Prefect's default SQLite backend becomes a PostgreSQL database on the shared server,
with its own role. See
[03](03-workflow-orchestration.md#prefects-own-database).

### Create work pools, workers and deployments as infrastructure

Pools and workers are created by hand from printed commands, and deployments from the
`blocks` deploy path. In a managed deployment all three belong to Manta's apply layer —
`docker/` locally, `manta-infra` on Kubernetes — under review and rollback like
anything else.
