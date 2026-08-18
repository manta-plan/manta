# Prefect workflow execution + Runs entity

## Summary

This change introduces Prefect as Manta's workflow execution engine and adds a `Runs` entity/endpoint following the existing Model-Service-Controller pattern (mirroring `Project`). Prefect already handles async execution, state tracking, and logging, so Manta's job is to submit runs to Prefect and query it back, not to reimplement any of that. The demo workload (computing digits of pi + digit-frequency stats) is a disposable stand-in for what will eventually be a "Playbook": an external, independently-versioned unit of workflow code with its own dependencies/environment. The design is deliberately generic so today's demo flow and tomorrow's external playbooks fit the same shape.

## Design decisions

- **Prefect server runs in `docker-compose`**, SQLite-backed (Prefect's default) — no separate Postgres database for Prefect's own metadata initially (see Future work for reconsidering this). The server container's own Python version is irrelevant to app code — it's infra, nothing runs inside it — so it's pulled as `prefecthq/prefect:3-latest` rather than pinned to a Python minor version.
- **No new dependencies for the demo workload.** Pi is computed with a short, self-contained pure-Python routine (e.g. Bailey–Borwein–Plouffe, or a `decimal`-based Chudnovsky implementation) that takes on the order of a few seconds for ~100k–1M digits. If that proves too slow or fiddly to get right, fall back to a trivial `time.sleep(N)` "flow" — the point of this feature is the plumbing, not the math.
- **No run status/result columns in Manta's database.** Prefect is the single source of truth for run state, logs, and results. The `Run` row exists only to link a `project_id` to a `prefect_flow_run_id`; `GET /runs/{uuid}` queries Prefect live rather than caching or duplicating state that could drift out of sync.
- **Cascade delete**: `Run.project_id`'s FK uses `ondelete="CASCADE"` — deleting a project deletes its runs.
- **No manual background threading.** Prefect already handles asynchronous execution: `create_run` calls Prefect's `run_deployment(...)`, which submits the flow run and returns immediately without waiting for completion. A separate long-lived process — a Prefect worker, or `flow.serve()` for the simple case (see below) — is what actually executes it. The backend process never runs the flow itself.
- **Request schema stays generic.** `CreateRunRequest` takes `project_uuid` and an open `parameters: dict[str, Any] | None`, passed straight through to Prefect — no pi-specific fields like `num_digits`. This is the shape a future "run this playbook" request also needs.

## New dependency

Add `prefect` to `backend/pyproject.toml` (`uv add prefect`). Nothing else.

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
- **Work pools + `prefect worker start`**: the real deployment model, needed once flow code has different dependencies/environment than the backend (i.e. once external playbooks exist). See "External playbooks" below — that complexity belongs there, not in this initial change.

Add a new `[project.scripts]` entry in `backend/pyproject.toml`: `manta-worker = "manta.workflows.serve:main"`, where `backend/src/manta/workflows/serve.py` calls `pi_digit_stats_flow.serve(name="pi-digit-stats")`. This runs as its own host process (`uv run manta-worker`), analogous to `uv run manta` for the API — documented in `backend/README.md` as a second process to run locally alongside the API and `docker compose up`.

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
`log_prints=True` routes `print()` output into Prefect's captured flow-run logs. That's where run output lives — fetched from Prefect (`GET /flow_runs/{id}/logs`), not stored by Manta. No return-value plumbing is needed for the demo; if a future flow needs structured results, Prefect supports `persist_result=True` + `state.result()`, but that's not needed here.

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
    parameters: dict[str, Any] | None = None
```
No pi-specific fields. For now the service hardcodes which Prefect deployment gets called (the demo flow); `parameters` passes through to it (e.g. `{"num_digits": ...}` if a caller wants to override the default) without Manta knowing or caring what's inside.

**Result DTOs** — `services/results/run_result.py`:
- `CreateRunResult(uuid, project_uuid, prefect_flow_run_id, created_at)`
- `GetRunResult(uuid, project_uuid, prefect_flow_run_id, status, logs, created_at)` — `status` and `logs` are fetched live from Prefect, not stored.

**Service** — `services/run_service.py`:
- `RunService(db: Session = Depends(get_db_session))`.
- `create_run(project_uuid, parameters) -> CreateRunResult`: look up `Project` by `uuid` (404 if missing); call Prefect's `run_deployment("pi-digit-stats/pi-digit-stats", parameters=parameters or {}, timeout=0)` — `timeout=0` makes it submit-and-return rather than waiting for completion; insert `Run(project_id=project.id, prefect_flow_run_id=flow_run.id)`, commit; return `CreateRunResult`.
- `get_run(run_uuid) -> GetRunResult`: fetch `Run` row (404 if missing); use Prefect's client to read the flow run's current state and logs by `prefect_flow_run_id` (`prefect.client.orchestration.get_client()` — async, so wrap with `asyncio.run(...)` from this sync service method, matching how `run_deployment` itself is used); map into `GetRunResult`.

**Route** — `routes/v1/run_route.py`:
```python
router = APIRouter(prefix="/runs", tags=["runs"])

@router.post("", response_model=CreateRunResult, status_code=status.HTTP_201_CREATED)
def create_run(request: CreateRunRequest, service: RunService = Depends()) -> CreateRunResult: ...

@router.get("/{run_uuid}", response_model=GetRunResult)
def get_run(run_uuid: UUID, service: RunService = Depends()) -> GetRunResult: ...
```
Wire into `routes/v1/__init__.py` alongside `project_router`.

## Tests

No test for the demo flow's internals — it's a disposable stand-in, not product logic.

**Unit** (`tests/unit/services/test_run_service.py`): mirror `test_project_service.py`'s `mock_db` pattern. Monkeypatch `run_deployment` and the Prefect client calls (module-level patches in `run_service`) so tests never talk to a real Prefect server:
  - `create_run` with a known `project_uuid` — asserts a `Run` row is persisted with the `prefect_flow_run_id` returned by the mocked `run_deployment`, and the right DTO is returned.
  - `create_run` with an unknown `project_uuid` — 404.
  - `get_run` for a known/unknown run, with the Prefect client mocked to return a fake state/logs — asserts DTO mapping; 404 for unknown run.

**Unit** (`tests/unit/routes/v1/requests/test_run_request.py`): mirror `test_project_request.py` — `project_uuid` must be a valid UUID; `parameters` is optional and accepts an arbitrary dict.

**Integration** (`tests/integration/routes/v1/test_run_route.py`): real HTTP round trip per existing pattern. This test needs the demo flow actually served somewhere for the run to complete, so `conftest.py` needs a fixture that starts `pi_digit_stats_flow.serve(...)` as a subprocess (same shape as the existing `app_server` fixture: spawn `uv run manta-worker` — or `python -m manta.workflows.serve` — pointed at the ephemeral `prefect-server` via `PREFECT_API_URL`, wait until it's polling). Flow:
  1. `POST /v1/projects` — `project_uuid`.
  2. `POST /v1/runs` with that `project_uuid` (small `parameters` if the flow honors it, to keep the test fast) — assert `201` and a `prefect_flow_run_id` is present.
  3. Poll `GET /v1/runs/{uuid}` in a bounded retry loop until `status` reports a Prefect terminal state (`COMPLETED`) — assert `logs` contains the printed digit-frequency output.
  4. Assert the `Run` row itself via `db_connection` as existing tests do (project_id/prefect_flow_run_id persisted).

This is the one place the new setup adds real weight to the integration suite (a `prefect-server` plus a served-flow subprocess, on top of the existing app subprocess) — acceptable since it's exactly what's needed to exercise the real Prefect submit → execute → query loop end-to-end, but worth calling out as new CI runtime.

**CI**: no workflow-file changes needed — `backend-test.yml` already runs `tests/unit`/`tests/integration` via `uv run pytest`; the testcontainers-booted compose stack picks up `prefect-server` automatically. First run pays image-pull latency for `prefecthq/prefect:3-latest`.

## External playbooks: what changes, and how workers scale

This is the target architecture the design above is deliberately shaped to grow into, not a separate redesign.

**The core shift**: today, `pi_digit_stats_flow` lives in Manta's own codebase and is executed by a process running in Manta's own Python environment (`flow.serve()`, via `uv run manta-worker`). A Playbook is the opposite: independently versioned code (its own git repo), with its own dependencies, that Manta must be able to execute without installing it into — or even being compatible with — Manta's own environment. Manta should end up knowing almost nothing about a playbook beyond "there's a deployment name I can call `run_deployment()` on, and a work pool it runs on."

Concretely, per playbook:
- **A Docker image**, built from the playbook's own repo (its own Dockerfile, its own dependency set — can be Python 3.9 with old scientific libraries, or nothing like Manta's stack at all). Alternatively, Prefect deployments can pull code from a git source at run time (`flow.from_source(source="https://github.com/...", entrypoint="flow.py:my_flow")`) rather than baking it into the image — useful if the playbook's dependencies are simple enough to install into a shared base image, but the general case (arbitrary dependencies) needs the playbook's own image.
- **A work pool** dedicated to that playbook (e.g. `<playbook-name>-pool`, type `docker` or `process`). Work pools are how Prefect routes a flow run to an environment capable of executing it — flow runs queued to a pool only get picked up by workers polling that specific pool. Playbooks with genuinely different or conflicting dependencies cannot share a pool, since whichever worker picks up the run needs that playbook's exact environment already available to it.
- **A deployment** registering the playbook's flow entrypoint against that work pool, via that repo's own `prefect.yaml` + `prefect deploy`, run as part of the playbook's own CI/release process — not something Manta's backend does.
- **A worker** polling that pool (`prefect worker start --pool <playbook-name>-pool`, running the playbook's Docker image), added as a service in whatever orchestrator runs the stack (a new docker-compose service per playbook in dev, a container/pod per playbook in prod).

**Current plan: one worker per playbook.** A work pool with zero workers just accumulates queued runs forever, so the minimum viable setup is one dedicated worker per playbook that's in active use. An idle worker is cheap — it's a polling loop hitting the Prefect API every few seconds, consuming negligible CPU/memory while waiting — so provisioning one worker per playbook up front, even for playbooks used rarely, is a reasonable default and doesn't waste meaningful resources. `RunService.create_run` resolves which deployment to call from something playbook-identifying (once a `Playbook` entity exists, its `deployment_name`) instead of today's hardcoded demo deployment name; `parameters` and the rest of the flow (submit via `run_deployment`, poll via the Prefect client) stays exactly the same, which is the point of designing it generically now.

## Future work

- **Prefect's own metadata store**: this plan uses Prefect's default SQLite backend rather than pointing it at the same Postgres instance Manta uses. Reconsider once Prefect's history/durability matters operationally (SQLite is fine for a single-node dev/demo setup but is not what most production Prefect deployments run): pointing `prefect-server` at the same Postgres server (a separate database, not a shared one, to avoid coupling schemas/migrations) is the natural next step and needs no application-code changes, only compose/env config.
- **Scaling workers onto Kubernetes, one container per flow run.** Once there are many playbooks or highly bursty workloads, a long-lived worker per playbook (as planned above) is not the only option. Prefect has a Kubernetes work pool type where the worker itself doesn't execute flow runs directly — it watches its pool and, for each flow run, creates a Kubernetes Job (a fresh Pod, from that playbook's image) to run it, then lets Kubernetes garbage-collect the Pod on completion. This gives per-run isolation (no state leaks between runs sharing a process) and scales workers to zero compute between runs (the worker pod itself stays cheap; the actual execution pods only exist while a run is in flight), at the cost of per-run container startup latency and needing a Kubernetes cluster to deploy into. This is a deployment-target change, not an architecture change — Manta's `run_deployment`/poll-via-client calls stay identical.
- **Chaining playbooks with different environments into one pipeline.** A user may want to run playbook A, then feed its output into playbook B, where A and B need entirely different Docker images/dependencies — no single flow run can span two environments. This is feasible, but needs to be modeled as orchestration *above* individual playbook runs, not inside a playbook itself:
  - **Manta-level sequencing** (simplest, keeps playbooks fully decoupled): Manta calls `run_deployment` for playbook A, polls to completion, then calls `run_deployment` for playbook B with parameters derived from A's output. Each step still runs in its own dedicated worker/image via normal work-pool routing — no playbook needs to know the other exists. The gap this leaves is data hand-off: since steps execute in different containers/environments, output can't be passed via shared memory or a shared filesystem — it needs an explicit medium (e.g. a shared object store like S3, or passing small results as flow-run parameters/state if they fit that path).
  - **Flow-level sequencing** (a flow triggers another deployment from within itself, via `run_deployment` called inside playbook A's flow code): possible, but couples playbook A to knowing about playbook B and to Prefect's orchestration API — likely undesirable given the goal of playbooks staying independent and environment-agnostic.
  - **A first-class "pipeline" concept in Manta**, sitting above playbook runs, that models a fixed or user-defined sequence of playbook invocations plus the hand-off contract between steps (what output format step N produces, what input step N+1 expects). This is the more product-shaped answer if chaining becomes a common pattern rather than a one-off, but is a larger addition than anything in this plan and should be scoped separately once there's a concrete multi-playbook workflow to support.

## Verification

- `docker compose --env-file ../backend/.env -f docker/compose-dev-services.yaml up` — confirm `prefect-server` becomes healthy and its UI is reachable at `http://localhost:4200`.
- `uv run manta` (API) and `uv run manta-worker` (serves the demo flow) both running — confirm startup works with `PREFECT_API_URL` set.
- `POST /v1/projects` then `POST /v1/runs` via curl/httpie — `201` with a `prefect_flow_run_id`; confirm the run appears in the Prefect UI and transitions to `Completed`; `GET /v1/runs/{uuid}` reflects that status and returns the printed digit-frequency logs.
- `uv run pytest tests/unit` and `uv run pytest tests/integration` (from `backend/`) — all new and existing tests pass.
- `uv run ruff check .` / `uv run ruff format --check .` — lint clean.
