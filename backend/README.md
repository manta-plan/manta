# Manta Backend

The Manta backend is built with [Python](https://www.python.org/) and
[FastAPI](https://fastapi.tiangolo.com/), using [uv](https://docs.astral.sh/uv/)
for dependency management. See the repo-level
[CONTRIBUTING.md](../CONTRIBUTING.md) for the architecture and coding standards
this package follows.

## Setup

```bash
uv sync
```

## Running

You can access API endpoints without [building the
frontend](../frontend/README.md#production-preview) first.

The default url is `localhost:8000`, but the run command should automatically
select a free port.

```bash
uv run manta
```

## Database migrations

We use [Alembic](https://alembic.sqlalchemy.org/) for Postgres DB migrations.
Scripts live in `src/manta/migrations/`

The app runs pending migrations automatically on startup (see
`src/manta/migrations/runner.py`), so `uv run manta` always starts against an
up-to-date schema — nothing to run by hand for normal development, beyond
having Postgres up (see [docker/README.md](../docker/README.md)).

After changing an entity, generate a migration and review it before
committing — autogenerate is a starting point, not the final word:

```bash
uv run alembic revision --autogenerate -m "describe the change"
```

Other useful commands:

```bash
uv run alembic upgrade head   # apply migrations without starting the app
uv run alembic downgrade -1   # roll back one revision
uv run alembic current        # show the currently applied revision
```

## File storage

Files are stored in S3-compatible object storage — [SeaweedFS](https://github.com/seaweedfs/seaweedfs)
locally (see [docker/README.md](../docker/README.md#services)), via
[`S3FileStorageService`](src/manta/services/s3_file_storage_service.py) (boto3
under the hood). Config lives in `backend/.env`, read by
[`src/manta/config/s3_config.py`](src/manta/config/s3_config.py). Like
migrations, the target bucket is provisioned automatically on startup (see
`ensure_bucket_exists()` in `main.py`) — nothing to run by hand, beyond having
SeaweedFS up.

## Linting & formatting

We use [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting.

```bash
uv run ruff check .     # lint
uv run ruff format .    # format
```

### Pre-commit hooks

A [pre-commit](https://pre-commit.com/) hook runs Ruff automatically before
each commit and auto-fixes what it can. One-time setup, from anywhere in the
repo:

```bash
uv tool install pre-commit   # install the tool once, machine-wide
pre-commit install           # wire it up to this repo's git hooks
```

## Testing

We use [pytest](https://docs.pytest.org/), with
[pytest-cov](https://pytest-cov.readthedocs.io/) for coverage measurement.

```bash
uv run pytest                     # everything
uv run pytest tests/unit          # unit tests only
uv run pytest tests/integration   # integration tests only
```

### Coverage

```bash
uv run pytest --cov=manta --cov-report=term-missing
```

CI combines coverage from the unit and integration suites and reports
coverage on lines changed by a PR. Not enforced yet (threshold is 0%) while
the project is still young — expect this to ratchet up over time.
Run the command above locally (against `tests/unit`, `tests/integration`, or
both) to check before pushing.

### Integration tests

Integration tests need a running [Docker](https://docs.docker.com/) daemon. 
`tests/integration/conftest.py` boots the required service
containers itself (via [testcontainers](https://testcontainers-python.readthedocs.io/),
reusing [`docker/compose-dev-services.yaml`](../docker/compose-dev-services.yaml)) and
runs the app as a subprocess, all on random ports — so there's nothing to
start by hand first, and it won't clash with or affect a dev stack you might
already have running. Everything is torn down again once the test session
ends. See [docker/README.md](../docker/README.md#testing) for how the
isolation works.

The app subprocess's logs (including the request log for the endpoint under
test) stream through as they're the app's own stdout/stderr; the Postgres
container's logs are dumped separately at the end of the session, since they
live inside the container rather than in this process. Both are subject to
pytest's normal output capturing — pass `-s` to see them live, otherwise
they're still shown for any failing test:

```bash
uv run pytest tests/integration -s
```

## Manually testing a run (temporary, will be removed)

This section exists only until the frontend can create a run with real data
on its own, and will be removed once that lands.

1. In one terminal, bring up the stack (from `docker/`) and leave it running
   so you can see the container logs:

   ```bash
   docker compose --env-file ../backend/.env -f compose-dev-services.yaml up
   ```

   Wait until the logs settle, then do the rest of the steps in a second
   terminal.

2. Start the backend (from `backend/`):

   ```bash
   uv run manta
   ```

3. Create a project:

   ```bash
   curl -s -X POST http://localhost:8000/v1/projects \
     -H "Content-Type: application/json" \
     -d '{"name": "Manual test", "description": "Manual test project"}'
   ```

   Copy the returned `uuid` as `PROJECT_UUID`.

4. Upload a starting network to S3 — `tests/integration/fixtures/example_network.nc`
   works (from `backend/`):

   ```bash
   uv run python -c "
   import boto3
   from botocore.config import Config
   client = boto3.client(
       's3',
       endpoint_url='http://localhost:8333',
       aws_access_key_id='dev',
       aws_secret_access_key='dev',
       config=Config(s3={'addressing_style': 'path'}),
   )
   client.upload_file('tests/integration/fixtures/example_network.nc', 'manta', 'manual-test/input.nc')
   "
   ```

5. Create a run:

   ```bash
   curl -s -X POST http://localhost:8000/v1/runs \
     -H "Content-Type: application/json" \
     -d '{"project_uuid": "PROJECT_UUID", "playbook": "cluster-expand-dispatch", "data_record_url": "s3://manta/manual-test/input.nc"}'
   ```

   Copy the returned `uuid` as `RUN_UUID`.

6. Poll status and logs:

   ```bash
   curl -s http://localhost:8000/v1/runs/RUN_UUID
   curl -s http://localhost:8000/v1/runs/RUN_UUID/logs
   ```

   A completed run writes its outputs to
   `s3://manta/PROJECT_UUID/runs/RUN_UUID/output/`.

7. Tear down (from `docker/`, in the second terminal — this also stops the
   first terminal's `up`):

   ```bash
   docker compose --env-file ../backend/.env -f compose-dev-services.yaml down -v
   ```
