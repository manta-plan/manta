# Prefect workflow execution + Runs entity

## Summary

This change introduces Prefect as Manta's workflow execution engine and adds a `Runs` entity/endpoint following the existing Model-Service-Controller pattern (mirroring `Project`). Prefect already handles async execution, state tracking, and logging, so Manta's job is to submit runs to Prefect and query it back, not to reimplement any of that. The demo workload (computing digits of pi + digit-frequency stats) is a disposable stand-in for what will eventually be a "Playbook": external workflow code (in the `blocks` repo) with its own dependencies/environment. The design is deliberately generic so today's demo flow and tomorrow's external playbooks fit the same shape.

## Design decisions

- **Prefect server runs in `docker-compose`**, SQLite-backed (Prefect's default) for now to keep this PR small — see [Future work](#future-work) for how we will switch to a separate Postgres database for Prefect's own metadata. The alternative is an in-process ephemeral prefect API, which may be simpler, but it doesn't allow persisting history or multiple worker processes -- which we will definitely need at some point. Adding a prefect-server docker compose service now also gives us the UI and the ability to use postgres later.
- **No new dependencies for the demo workload.** Pi is computed with a short, self-contained pure-Python routine (e.g. Bailey–Borwein–Plouffe, or a `decimal`-based Chudnovsky implementation) that takes on the order of a few seconds for ~100k–1M digits. If that proves too slow or fiddly to get right, fall back to a trivial `time.sleep(N)` "flow" — the point of this feature is the plumbing, not the math.
- **No run status/result columns in Manta's database.** Prefect is the single source of truth for run state, logs, and results. The `Run` row exists only to link a `project_id` to a `prefect_flow_run_id`; `GET /runs/{uuid}` queries Prefect live rather than caching or duplicating state that could drift out of sync.
- **Cascade delete**: `Run.project_id`'s FK uses `ondelete="CASCADE"` — deleting a project deletes its runs.
- **Worker initialization in `create_app()` alongside other required services.** Following the pattern established by migrations and S3 bucket setup, the Prefect worker subprocess is spawned in `create_app()` on startup. The backend process itself never runs flows — it only submits them to Prefect via `run_deployment()` and queries state/logs via the Prefect client. The separate worker process polls for and executes flow runs asynchronously.
- **Request schema stays generic.** `CreateRunRequest` takes `project_uuid` and an open `parameters: dict[str, Any] | None`, passed straight through to Prefect — no pi-specific fields like `num_digits`. This will change in the future once we know exactly what Playbook configs look like and how Manta will handle them, but seems like a good enough starting point.
## New dependency

Add `prefect` to `backend/pyproject.toml`:
```bash
cd backend && uv add prefect
```

Also add a prebuilt `prefect-server` service to Docker Compose (see [Docker Compose changes](#docker-compose-changes) below). No other new application dependencies needed beyond `prefect`.

## Docker Compose changes (`docker/compose-dev-services.yaml`)

Add a `prefect-server` service:
```yaml
  prefect-server:
    image: prefecthq/prefect:3-latest
    command: prefect server start --host 0.0.0.0
    env_file: ../backend/.env
    ports:
      - "${PREFECT_PORT}:4200"
    volumes:
      - prefect-data:/root/.prefect
    healthcheck:
      # curl isn't available in this image, so using python
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:4200/api/health')"]
      interval: 5s
      timeout: 5s
      retries: 10
```
Add `prefect-data:` to the `volumes:` block. `compose-test-services.yaml` needs no change — it already `include`s `compose-dev-services.yaml` wholesale, so the integration test stack picks up `prefect-server` automatically.

Add to `backend/.env`:
```
PREFECT_PORT=4200
PREFECT_API_URL=http://localhost:4200/api
```
Add `PREFECT_PORT=0` to `docker/.env.test` (ephemeral port, matching the existing `POSTGRES_PORT=0` pattern).

## Executing the demo flow: `flow.serve()`, not a full worker/work-pool setup yet

Prefect's execution model has two tiers of complexity:
- **`flow.serve(name=...)`**: runs in a single long-lived process, implicitly registers a deployment, and polls for scheduled runs against it — no explicit work pool or separate worker to set up. This is the right amount of machinery for one built-in demo flow living in Manta's own codebase/environment.
- **Work pools + `prefect worker start`**: the real deployment model, needed once flow code has different dependencies/environment than the backend (i.e. once external playbooks exist). See [External playbooks](#external-playbooks-what-changes-and-how-workers-scale) below.

Instead of a separate `manta-worker` script, spawn the flow-serving process as a **subprocess** from within `create_app()` in `backend/src/manta/main.py` — consistent with how migrations and S3 bucket initialization are run on startup. This keeps all app-startup logic centralized in `create_app()`. The subprocess runs `pi_digit_stats_flow.serve(name="pi-digit-stats")` (not `prefect worker start` — that command only dispatches to deployments registered via `flow.deploy()` against a work pool, which is the tier of machinery this section deliberately avoids for now), isolated from the API server (see rationale below).

## Backend changes

**Flow module** — new `backend/src/manta/workflows/pi_digit_stats.py` (new `workflows/` package alongside `entities/`, `services/`, `routes/`):
```python
from prefect import flow, task

@task
def compute_pi_digits(num_digits: int) -> str: ...   # short pure-Python routine, or time.sleep fallback

@task
def digit_frequency(digits: str) -> dict[str, int]: ...  # Counter over '0'-'9'

@flow(name="pi-digit-stats", log_prints=True)
def pi_digit_stats_flow(num_digits: int = 100_000) -> None:
    digits = compute_pi_digits(num_digits)
    print(digit_frequency(digits))
```
`log_prints=True` routes `print()` output into Prefect's captured flow-run logs. That's where run output lives — fetched via `GET /v1/runs/{uuid}/logs`. No return-value plumbing is needed for the demo; if a future flow needs structured results, Prefect supports `persist_result=True` + `state.result()`, but that's not needed here.

See [Open Questions](#open-questions) below for discussion of whether this `workflows/` module stays even after integrating external playbooks.

**Entity** — `backend/src/manta/entities/run.py`:
```python
class Run(Base):
    __tablename__ = "runs"
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    prefect_flow_run_id: Mapped[UUID] = mapped_column(unique=True)
```
(`id`, `uuid`, `created_at` come from `Base`.) No status, result, or error columns. Add `Run` to `entities/__init__.py`'s `__all__`.

**Migration**: `uv run alembic revision --autogenerate -m "create runs table"`, hand-reviewed per existing convention (check the FK/`ondelete` renders correctly).

**Request DTO** — `routes/v1/requests/run_request.py`:
```python
class CreateRunRequest(BaseModel):
    project_uuid: UUID
    num_pi_digits: int = 100_000
```
For this PR, we hardcode the request to have a pi-specific `num_pi_digits` parameter that is passed through to the Prefect deployment. The code will have a **TODO**: once external playbooks are integrated from the `blocks` repo, replace this with a generic playbook-config schema (name, parameters dict, etc.) that Manta resolves to a deployment.

**Result DTOs** — `services/results/run_result.py`:
- `CreateRunResult(uuid, project_uuid, created_at)` — minimal response; `prefect_flow_run_id` is stored only in Manta's database, internal to the backend.
- `GetRunResult(uuid, project_uuid, status, created_at)` — `status` is fetched live from Prefect, not stored. Logs are fetched via a separate endpoint (see below).
- `GetRunLogsResult(logs: list[str], run_status: str)` — `logs` are the accumulated Prefect flow-run logs; `run_status` is the current Prefect state (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, etc.) to clarify whether logs are still accumulating or final.

**Service** — `services/run_service.py`:
- `RunService(db: Session = Depends(get_db_session))`.
- `create_run(project_uuid, num_pi_digits) -> CreateRunResult`: look up `Project` by `uuid` (404 if missing); call Prefect's `run_deployment("pi-digit-stats/pi-digit-stats", parameters={"num_digits": num_pi_digits}, timeout=0)` — `timeout=0` makes it submit-and-return rather than waiting for completion; insert `Run(project_id=project.id, prefect_flow_run_id=flow_run.id)`, commit; return `CreateRunResult`.
- `get_run(run_uuid) -> GetRunResult`: fetch `Run` row (404 if missing); use Prefect's client to read the flow run's current state by `prefect_flow_run_id` (`prefect.client.orchestration.get_client()` — async, so wrap with `asyncio.run(...)` from this sync service method); map into `GetRunResult`.
- `get_run_logs(run_uuid) -> GetRunLogsResult`: fetch `Run` row (404 if missing); use Prefect's client to read the flow run's current state and logs by `prefect_flow_run_id`; return logs and run status.

**Route** — `routes/v1/run_route.py`:
```python
router = APIRouter(prefix="/runs", tags=["runs"])

@router.post("", response_model=CreateRunResult, status_code=status.HTTP_201_CREATED)
def create_run(request: CreateRunRequest, service: RunService = Depends()) -> CreateRunResult: ...

@router.get("/{run_uuid}", response_model=GetRunResult)
def get_run(run_uuid: UUID, service: RunService = Depends()) -> GetRunResult: ...

@router.get("/{run_uuid}/logs", response_model=GetRunLogsResult)
def get_run_logs(run_uuid: UUID, service: RunService = Depends()) -> GetRunLogsResult: ...
```
Wire into `routes/v1/__init__.py` alongside `project_router`.

## Implementation notes

**Flow-serving subprocess architecture** — [Prefect officially recommends separate process workers](https://docs.prefect.io/v3/advanced/background-tasks), not threaded within the app. The same rationale applies to a `flow.serve()` process, which is likewise a long-lived loop polling Prefect for scheduled runs:

1. **Isolation**: Failures (crashes, deadlocks, resource exhaustion) don't crash the API server. If the Prefect server goes down, the API keeps serving; runs just don't execute until the flow-serving process recovers.
2. **Python GIL (Global Interpreter Lock)**: Threading Python code prevents true parallelism even on multi-core systems — only one thread executes Python bytecode at a time. A subprocess executes independently with its own GIL, enabling true parallel flow execution.
3. **Graceful shutdown**: A subprocess responds to signals and can clean up resources (close DB connections, flush logs) before exiting. Daemon threads are abruptly terminated, risking resource leaks.
4. **Industry standard**: [Celery (Python's de facto task queue)](https://docs.celeryq.dev/en/4.4.0/userguide/workers.html) defaults to multiprocessing, not threading, for these same reasons.

**Implementation**: Spawn the flow-serving process via `subprocess.Popen()` in `create_app()`, following the pattern established by S3 bucket initialization. Give `pi_digit_stats.py` a `__main__` entrypoint that calls `.serve()` — **not** `prefect worker start --type process`, which only dispatches to deployments registered via `flow.deploy()` against a work pool. That's a different, incompatible execution model from `flow.serve()` (see [Executing the demo flow](#executing-the-demo-flow-flowserve-not-a-full-workerwork-pool-setup-yet)); a bare `prefect worker start` subprocess would never see runs from a flow only registered via `.serve()`, since `.serve()`'s polling loop runs in — and only in — the process that called it.

```python
# backend/src/manta/workflows/pi_digit_stats.py
if __name__ == "__main__":
    pi_digit_stats_flow.serve(name="pi-digit-stats")
```

```python
import subprocess
import sys

def create_app():
    configure_logging()
    logger.info("Running database migrations...")
    run_migrations()
    logger.info("Ensuring S3 bucket exists...")
    S3FileStorageService(...).ensure_bucket_exists()

    logger.info("Starting Prefect flow-serving process...")
    try:
        flow_serve_process = subprocess.Popen(
            [sys.executable, "-m", "manta.workflows.pi_digit_stats"],
            env=os.environ.copy(),  # inherits PREFECT_API_URL, etc.
            stdout=subprocess.PIPE,  # optional: capture logs
            stderr=subprocess.PIPE,
        )
        logger.info("Prefect flow-serving process started")
    except Exception as e:
        logger.error(f"Failed to start Prefect flow-serving process: {e}")
        # Non-fatal: app continues, runs just won't execute

    app = FastAPI(...)
    # ... rest of app setup ...
    return app
```

For production on Linux, [wrap the subprocess in a systemd service](https://docs.prefect.io/v3/advanced/daemonize-processes) so it auto-restarts on failure — separate from the Manta app's lifecycle.

**Prefect client API** — `run_deployment()` and `get_client()` are async functions:
- `run_deployment()`: from `prefect.deployments`; returns a `FlowRun` object with an `id` property (the `prefect_flow_run_id`).
- `get_client()`: from `prefect.client.orchestration`; returns an async Prefect client. Use it to call `get_flow_run()` by ID.
- In `run_service.py` (which is sync), wrap async calls with `asyncio.run(...)`. This is safe because the service is called from FastAPI's request context (which is also sync for this codebase).

**Prefect version** — add a specific version constraint to `pyproject.toml`, e.g. `prefect>=3.0.0,<4.0.0` to avoid breaking changes in a future major version.

**Flow registration** — `pi_digit_stats_flow.serve()` automatically registers a deployment named `pi-digit-stats/pi-digit-stats` (project_name/deployment_name). This must match the hardcoded name in `run_deployment()` calls.

**Prefect server health** — if `PREFECT_API_URL` is unreachable at app startup, the worker process won't start or will crash. The app should still run (the worker startup failure is non-fatal), but runs won't execute. Log the error and continue; once Prefect server is reachable, restart the worker process (or the app).

## Tests

No test for the demo flow's internals — it's a disposable stand-in, not product logic.

**Unit** (`tests/unit/services/test_run_service.py`): mirror `test_project_service.py`'s `mock_db` pattern. Monkeypatch `run_deployment` and the Prefect client calls (module-level patches in `run_service`) so tests never talk to a real Prefect server:
  - `create_run` with a known `project_uuid` — asserts a `Run` row is persisted with the `prefect_flow_run_id` returned by the mocked `run_deployment`, and the right DTO is returned.
  - `create_run` with an unknown `project_uuid` — 404.
  - `get_run` for a known/unknown run, with the Prefect client mocked to return a fake state/logs — asserts DTO mapping; 404 for unknown run.

**Unit** (`tests/unit/routes/v1/requests/test_run_request.py`): mirror `test_project_request.py` — `project_uuid` must be a valid UUID; `num_pi_digits` must be a positive integer.

**Integration** (`tests/integration/routes/v1/test_run_route.py`): real HTTP round trip per existing pattern. The Prefect worker subprocess is spawned as part of `create_app()` in the test's `app_server` fixture, so no additional test setup is needed — `create_app()` handles both the API server and the worker process. Flow:
  1. `POST /v1/projects` — `project_uuid`.
  2. `POST /v1/runs` with that `project_uuid` and `num_pi_digits` (small value to keep the test fast) — assert `201` and a `uuid` (the Manta run UUID) is present.
  3. Poll `GET /v1/runs/{uuid}` in a bounded retry loop until `status` reports a Prefect terminal state (`COMPLETED`).
  4. `GET /v1/runs/{uuid}/logs` — assert logs contain the printed digit-frequency output.
  5. Assert the `Run` row itself via `db_connection` as existing tests do (project_id/prefect_flow_run_id persisted).

The integration setup mirrors the existing pattern: `prefect-server` is a docker service (like `postgres` and `seaweedfs`), and the Prefect worker is booted as part of `create_app()` startup (like migrations and S3 bucket initialization). No additional subprocess management is needed beyond what the test harness already does for the postgres-dependent app. This follows the same model as existing integration tests and adds acceptable weight for exercising the real Prefect submit → execute → query loop end-to-end.

**CI**: no workflow-file changes needed — `backend-test.yml` already runs `tests/unit`/`tests/integration` via `uv run pytest`; the testcontainers-booted compose stack picks up `prefect-server` automatically. First run pays image-pull latency for `prefecthq/prefect:3-latest`.

## External playbooks: what changes, and how workers scale

This is the target architecture the design above is shaped to grow into.

**The core shift**: today, `pi_digit_stats_flow` lives in Manta's own codebase and is executed by a Prefect worker booted as part of `create_app()`, running in Manta's own Python environment. A Playbook is the opposite: independently versioned code (its own git repo), with its own dependencies, that Manta must be able to execute without installing it into — or even being compatible with — Manta's own environment. Manta should end up knowing almost nothing about a playbook beyond "there's a deployment name I can call `run_deployment()` on, and a work pool it runs on."

Concretely, per playbook:
- **A Docker image**, built from the playbook's own repo (its own Dockerfile, its own dependency set — can be Python 3.9 with old scientific libraries, or nothing like Manta's stack at all). Alternatively, Prefect deployments can pull code from a git source at run time (`flow.from_source(source="https://github.com/...", entrypoint="flow.py:my_flow")`) rather than baking it into the image — useful if the playbook's dependencies are simple enough to install into a shared base image, but the general case (arbitrary dependencies) needs the playbook's own image.
- **A work pool** dedicated to that playbook (e.g. `<playbook-name>-pool`, type `docker` or `process`). Work pools are how Prefect routes a flow run to an environment capable of executing it — flow runs queued to a pool only get picked up by workers polling that specific pool. Playbooks with genuinely different or conflicting dependencies cannot share a pool, since whichever worker picks up the run needs that playbook's exact environment already available to it.
- **A deployment** registering the playbook's flow entrypoint against that work pool, via that repo's own `prefect.yaml` + `prefect deploy`, run as part of the playbook's own CI/release process — not something Manta's backend does.
- **A worker** polling that pool (`prefect worker start --pool <playbook-name>-pool`, running the playbook's Docker image), added as a service in whatever orchestrator runs the stack (a new docker-compose service per playbook in dev, a container/pod per playbook in prod).

**Current plan: one worker per playbook.** A work pool with zero workers just accumulates queued runs forever, so the minimum viable setup is one dedicated worker per playbook that's in active use. An idle worker is cheap — it's a polling loop hitting the Prefect API every few seconds, consuming negligible CPU/memory while waiting — so provisioning one worker per playbook up front, even for playbooks used rarely, is a reasonable default and doesn't waste meaningful resources. `RunService.create_run` resolves which deployment to call from something playbook-identifying (once a `Playbook` entity exists, its `deployment_name`) instead of today's hardcoded demo deployment name; `parameters` and the rest of the flow (submit via `run_deployment`, poll via the Prefect client) stays exactly the same, which is the point of designing it generically now.

## Future work

- **Prefect's own metadata store**: this plan uses Prefect's default SQLite backend rather than pointing it at a Postgres instance. Before any non-ephemeral deployments (e.g. the MVP), we should upgrade to Postgres, which is what most production Prefect deployments use. The strategy is to **share the Postgres server but use separate databases** — one `dbname` for Manta, another for Prefect. This avoids the shared-schema isolation problem that [Prefect does not natively support](https://github.com/PrefectHQ/prefect/issues/18015); PostgreSQL's database-level permissions enforce hard boundaries — a Prefect user account simply cannot access tables in the Manta database. Security implementation: (a) create a dedicated database user for Prefect with permissions only on its own database, (b) store the connection URL in `PREFECT_API_DATABASE_CONNECTION_URL` as an environment variable, and (c) disable automatic migrations on any non-primary instance if needed. This approach is cost-efficient (shared infrastructure for one Postgres server) and safe (database-level isolation enforced by PostgreSQL). If Prefect's workload or scaling eventually demands isolated infrastructure, a separate Postgres instance can be introduced later without code changes — just connection-string updates. Migration path: add `prefect-db` service to `docker-compose.yml` pointing to a separate `dbname`, update the env var, restart Prefect server.
- **Dedicated Postgres instance for Prefect (optional at scale).** The current plan shares the Postgres server for cost efficiency, but if Prefect's workload becomes substantial (many frequent runs, large event/flow-run history) or if independent scaling becomes necessary, a separate Postgres instance can be introduced with zero application-code changes — just point `PREFECT_API_DATABASE_CONNECTION_URL` at a new server. This is worth reconsidering if: (a) Prefect's queries start impacting Manta's API latency, (b) retention/vacuum operations on Prefect's tables cause disk contention, or (c) operational requirements demand independent backup/recovery policies. For now, shared infrastructure keeps costs minimal.
- **Scaling workers onto Kubernetes, one container per flow run.** Once there are many playbooks or highly bursty workloads, a long-lived worker per playbook (as planned above) is not the only option. Prefect has a Kubernetes work pool type where the worker itself doesn't execute flow runs directly — it watches its pool and, for each flow run, creates a Kubernetes Job (a fresh Pod, from that playbook's image) to run it, then lets Kubernetes garbage-collect the Pod on completion. This gives per-run isolation (no state leaks between runs sharing a process) and scales workers to zero compute between runs (the worker pod itself stays cheap; the actual execution pods only exist while a run is in flight), at the cost of per-run container startup latency and needing a Kubernetes cluster to deploy into. This is a deployment-target change, not an architecture change — Manta's `run_deployment`/poll-via-client calls stay identical.
- **Chaining playbooks with different environments into one pipeline.** A user may want to run playbook A, then feed its output into playbook B, where A and B need entirely different Docker images/dependencies — no single flow run can span two environments. This is feasible; Prefect has native support for it that's preferable to hand-rolling the sequencing in Manta (see [Open Questions](#open-questions)):
  - **Prefect-native sequencing via a parent flow** (preferred): define a lightweight orchestrator flow, deployed and run like any other flow, whose only job is to call `run_deployment` for each playbook step in order:
    ```python
    from prefect.deployments import run_deployment

    @flow
    def parent_flow():
        run_deployment("subflow-a/deployment-a")  # runs on work pool A
        run_deployment("subflow-b/deployment-b")  # runs on work pool B
    ```
    By default `run_deployment` called from within a flow blocks until that deployment run finishes and links it as a subflow in the Prefect UI (`as_subflow=True` is the default) — so this gets sequencing, waiting, and a grouped parent/child view in the UI for free, without Manta polling anything itself. Each `run_deployment` call still resolves to that playbook's own deployment/work pool/worker, so step A and step B execute in their own environments exactly as they would standalone — the parent flow only orchestrates, it doesn't run playbook code itself. The parent flow needs a (very lightweight) deployment and worker of its own, since it's a real flow, but it does no heavy computation — it just calls out and waits.
  - **Manta-level sequencing** (an alternative if avoiding an extra orchestrator flow/worker matters more than UI grouping): Manta itself calls `run_deployment` for playbook A, polls to completion via the Prefect client, then calls `run_deployment` for playbook B with parameters derived from A's output. Same per-step isolation as above, but the sequencing logic and polling loop live in Manta's backend instead of in Prefect, and the parent/child UI grouping is lost.
  - Either approach shares the same data hand-off gap: since steps execute in different containers/environments, output can't be passed via shared memory or a shared filesystem — it needs an explicit medium (e.g. a shared object store like S3, or passing small results as flow-run parameters/state if they fit that path).
  - **A first-class "pipeline" concept in Manta**, sitting above playbook runs, that models a fixed or user-defined sequence of playbook invocations plus the hand-off contract between steps (what output format step N produces, what input step N+1 expects) — likely implemented *using* the parent-flow pattern above under the hood. This is the more product-shaped answer if chaining becomes a common pattern rather than a one-off, but is a larger addition than anything in this plan and should be scoped separately once there's a concrete multi-playbook workflow to support.
- **Mixing an always-alive pool for parent flows with on-demand k8s pools for subflows.** Work pools are independent and can be of different types within the same Prefect server/workspace, and each deployment targets its own pool — so the parent-flow pattern discussed in [Chaining playbooks](#chaining-playbooks-with-different-environments-into-one-pipeline) can be split across infrastructure tiers: the orchestrator (parent) flow deploys to a `process`-type work pool with a long-lived worker (near-zero dispatch latency, since it's already running and just needs to call out and wait), while each playbook's subflow deploys to a `kubernetes`-type work pool that spins up a fresh Job/Pod per flow run (no idle compute, isolated per-run environment). This gets the best of both: fast, cheap orchestration plus on-demand, isolated execution for the actual (potentially heavier/bursty) playbook work, at the cost of needing a Kubernetes cluster and at least two separate worker processes running concurrently — a Prefect worker only polls one work pool at a time, so the always-alive `process` worker and the `kubernetes` worker are two distinct processes, not one worker serving both pools.

## Open questions

### Does Manta need to orchestrate playbooks even after external playbooks from `blocks` are integrated?

Once playbooks live in the external `blocks` repo and are deployed to Prefect as independent deployments, one option could be that we remove the `backend/workflows/` module and have the `flow.serve()` call from the blocks repo.

However, if a user wants to compose multiple playbooks that use incompatible environments, see the Chaining playbooks Future work item above, perhaps Manta still needs to do some orchestration -- so we would retain the `workflows` module.


**Options:**
- **Manta orchestrates:** Manta calls `run_deployment` for each step, polls to completion, then calls the next step with derived parameters. Sequencing and data hand-off happen in Manta's backend. This is simpler for users (one REST endpoint to trigger the whole sequence) but couples Manta to workflow orchestration logic.
- **Prefect orchestrates:** Define a lightweight parent flow (deployed to a `process`-type work pool) whose only job is to call `run_deployment` for each playbook step in order (see Future work section, "Prefect-native sequencing via a parent flow"). This leverages Prefect's native UI grouping and sequencing, but requires users to define and deploy the parent flow as a separate artifact.
- **User orchestrates client-side:** The user's UI/app makes sequential API calls to `POST /v1/runs` for each step. Simplest for Manta, but no automatic waiting/sequencing — the client is responsible for polling and chaining.

This decision depends on whether cross-environment playbook composition is a common/important pattern for Manta's users. If it becomes necessary, the Prefect-orchestrated parent-flow approach (already detailed in [Chaining playbooks](#chaining-playbooks-with-different-environments-into-one-pipeline) under Future work) is likely preferable, as it keeps Manta's backend focused on single-playbook execution and lets Prefect handle orchestration. Manta's role would remain: look up the playbook/parent-flow name by UUID, call `run_deployment`, and serve the status/logs via the `Runs` endpoint — no change from the current design.

## Verification

- `docker compose --env-file ../backend/.env -f docker/compose-dev-services.yaml up` — confirm `prefect-server` becomes healthy and its UI is reachable at `http://localhost:4200`.
- `uv run manta` running (app + Prefect worker subprocess spawned in `create_app()`) — confirm startup logs show successful Prefect worker process launch with `PREFECT_API_URL` set.
- `POST /v1/projects` then `POST /v1/runs` via curl/httpie — `201` with a `uuid`; confirm the run appears in the Prefect UI and transitions to `Completed`; `GET /v1/runs/{uuid}` reflects that status; `GET /v1/runs/{uuid}/logs` returns the printed digit-frequency output.
- `uv run pytest tests/unit` and `uv run pytest tests/integration` (from `backend/`) — all new and existing tests pass.
- `uv run ruff check .` / `uv run ruff format --check .` — lint clean.

## Implementation plan

Nine commits, each independently reviewable and (with the exception of the last two, which need the full stack) independently runnable through lint/tests. Ordered so every commit only depends on ones before it. Model picks assume Claude Code's default agentic loop (planning + tool use already handled); pick a size up if the assigned model struggles.

1. **Infra: Prefect dependency, docker-compose service, env vars**
   - `cd backend && uv add "prefect>=3.0.0,<4.0.0"`
   - `docker/compose-dev-services.yaml`: add `prefect-server` service + `prefect-data` volume (per [Docker Compose changes](#docker-compose-changes-dockercompose-dev-servicesyaml))
   - `backend/.env`: add `PREFECT_PORT`, `PREFECT_API_URL`
   - `docker/.env.test`: add `PREFECT_PORT=0`
   - No application code touched. Verify with `docker compose --env-file ../backend/.env -f docker/compose-dev-services.yaml up` and confirm `prefect-server` reports healthy.
   - **Model: Haiku** — config/YAML/env edits only, no logic.

2. **Demo workflow module: `pi_digit_stats` flow**
   - New `backend/src/manta/workflows/__init__.py`, `backend/src/manta/workflows/pi_digit_stats.py` with `compute_pi_digits` task, `digit_frequency` task, `pi_digit_stats_flow`, and a `__main__` entrypoint calling `pi_digit_stats_flow.serve(name="pi-digit-stats")` (per [Backend changes](#backend-changes) and [Implementation notes](#implementation-notes)).
   - No test per the doc (disposable demo) — verify manually with a plain Python call (not yet wired to Prefect server/deployment).
   - **Model: Sonnet** — getting a correct, reasonably fast pi-digit routine (or judging that the `time.sleep` fallback is the better call) needs a bit more judgment than pure boilerplate.

3. **`Run` entity + migration**
   - `backend/src/manta/entities/run.py`, add `Run` to `entities/__init__.py`'s `__all__`.
   - `uv run alembic revision --autogenerate -m "create runs table"`, hand-review the FK/`ondelete="CASCADE"`.
   - **Model: Haiku** — directly mirrors `Project`/its migration; AGENTS.md's "Adding a New Entity" recipe covers it exactly.

4. **Run request/result DTOs**
   - `backend/src/manta/routes/v1/requests/run_request.py` (`CreateRunRequest`)
   - `backend/src/manta/services/results/run_result.py` (`CreateRunResult`, `GetRunResult`, `GetRunLogsResult`)
   - **Model: Haiku** — pure Pydantic boilerplate mirroring the `Project` DTOs.

5. **`RunService`**
   - `backend/src/manta/services/run_service.py`: `create_run`, `get_run`, `get_run_logs` (per [Backend changes](#backend-changes)), wrapping Prefect's async client with `asyncio.run(...)`.
   - **Model: Sonnet** — the sync/async boundary and mapping Prefect's `FlowRun`/state objects onto the result DTOs need more care than a mechanical mirror of `ProjectService`.

6. **Run route**
   - `backend/src/manta/routes/v1/run_route.py` (`POST /runs`, `GET /runs/{uuid}`, `GET /runs/{uuid}/logs`); wire into `routes/v1/__init__.py`.
   - **Model: Haiku** — directly mirrors `project_route.py`.

7. **Start the flow-serving subprocess in `create_app()`**
   - `backend/src/manta/main.py`: spawn the entrypoint added in commit 2 as a subprocess (`[sys.executable, "-m", "manta.workflows.pi_digit_stats"]`) in `create_app()`, alongside migrations/S3 bucket init (per [Implementation notes](#implementation-notes)) — non-fatal on failure to start.
   - **Model: Sonnet** — subprocess lifecycle/error-handling logic (non-fatal startup failure, as specified) needs more judgment than a mechanical mirror of the S3 bucket init step.

8. **Unit tests: `RunService`, `CreateRunRequest`**
   - `backend/tests/unit/services/test_run_service.py` — mirrors `test_project_service.py`'s `mock_db` pattern; monkeypatch `run_deployment` and the Prefect client so no real server is contacted.
   - `backend/tests/unit/routes/v1/requests/test_run_request.py` — mirrors `test_project_request.py`.
   - **Model: Sonnet** — correctly monkeypatching Prefect's async client calls (module-level patches, `asyncio.run` interplay) is fiddlier than the existing sync-only `mock_db` fixture covers.

9. **Integration test: `run_route`**
   - `backend/tests/integration/routes/v1/test_run_route.py` — full `POST /runs` → poll `GET /runs/{uuid}` → `GET /runs/{uuid}/logs` round trip (per [Tests](#tests)).
   - `backend/tests/integration/conftest.py` — add a `prefect_service` fixture (mirroring `postgres_service`/`seaweedfs_service`) and pass its host/port to `app_server`'s subprocess env as `PREFECT_API_URL`.
   - **Model: Sonnet** — bounded-retry polling loops and multi-service fixture wiring are the most failure-prone part of this plan to get right first try.

**Not its own commit**: no CI workflow changes needed (per [Tests](#tests) — the existing `backend-test.yml` picks up `prefect-server` automatically via the testcontainers-booted compose stack).
