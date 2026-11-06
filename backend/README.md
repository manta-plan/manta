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

### Example data

With `EXAMPLE_DATA_SEED=true` (the default in `backend/.env`), startup also
copies the example datarecord stores of the public `manta-public-test-data`
bucket into the storage of the example project
`33b9abe3-2f25-4824-89e2-5a3d93671b6c`, each under
`s3://manta/33b9abe3-2f25-4824-89e2-5a3d93671b6c/<store>` (see
[`ExampleDataService`](src/manta/services/example_data_service.py)). Stores
already there are skipped, so only a clean SeaweedFS volume pays for the
download. Stores listed in `EXAMPLE_DATA_EXCLUDED_STORES` are left out, which
by default is `europe-full-res-2030` (~125 MB). Without internet access, the
app logs a warning and starts without them.

| Store | Size | `inputs` revision |
| --- | --- | --- |
| `ac-dc-meshed` | 0.1 MB | `e5f2eacd-ba5c-463c-a663-3017ef904d1d` |
| `model-energy` | 0.2 MB | `075955d5-fe04-48de-bc6c-75ad873de6c0` |
| `BEL-pre-aggregated` | 0.4 MB | `c7525fa8-e4da-4569-bbf3-b76669d1a2df` |
| `BEL-pre-aggregated-hourly` | 2.9 MB | `fc0145a7-3cdf-4c5f-a9c9-ec77a472cb99` |
| `BEL-pre-aggregated-incl-patches-incl-results` | 11.5 MB | `4dbf521c-2911-40be-8c6e-b075daa1a8ec` |
| `BEL-full-res` | 32.5 MB | `f910244f-99d2-4ae0-8ba7-a10dbd54f7e0` |
| `europe-full-res-2030` | 124.4 MB | `2f276825-9deb-4abc-ad57-ceb08f57ea94` |

Each store's `revisions.json` names its revisions, `inputs` being the one a run
starts from. The integration tests copy only `ac-dc-meshed`, with the same code,
under each test's own project.

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

You need three terminals: one for the Docker stack, one for the backend, and
one for the requests.

1. In the first terminal, bring up the stack (from `docker/`) and leave it
   running so you can see the container logs:

   ```bash
   docker compose --env-file ../backend/.env -f compose-dev-services.yaml up
   ```

   Wait until the logs settle before going on.

2. In the second terminal, start the backend (from `backend/`) and leave it
   running:

   ```bash
   uv run manta
   ```

3. In the third terminal, log in as the dev user and keep the token (from
   `backend/`). This also registers the user with Manta, which every other
   request needs:

   ```bash
   export TOKEN=$(uv run python -c "
   import base64, json, urllib.request

   def post(path, body):
       request = urllib.request.Request(
           f'http://localhost:8000{path}',
           data=json.dumps(body).encode(),
           headers={'Content-Type': 'application/json'},
       )
       return json.load(urllib.request.urlopen(request))

   token = post('/v1/auth/login', {'username': 'manta-admin', 'password': 'manta-admin'})['access_token']
   payload = token.split('.')[1]
   claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
   post('/v1/auth/register', {'username': 'manta-admin', 'idp_subject': claims['sub'], 'idp_source': claims['iss']})
   print(token)
   ")
   ```

   The token expires after 5 minutes. Repeat this step when a request returns
   `401`.

4. Create a project:

   ```bash
   curl -s -X POST http://localhost:8000/v1/projects \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "Manual test", "description": "Manual test project"}'
   ```

   Copy the returned `uuid` as `PROJECT_UUID`.

5. Copy a starting datarecord store into the project's own storage. A run is
   refused unless its store is under the project's prefix and the revision
   exists. This copies `ac-dc-meshed` the same way the example data is seeded
   (see [Example data](#example-data)) and prints its `store_url` and `inputs`
   revision:

   ```bash
   uv run python -c "
   from uuid import UUID
   import httpx2
   from manta.config.s3_config import get_s3_client, s3_bucket_name
   from manta.services.example_data_service import ExampleDataService
   from manta.services.s3_file_storage_service import S3FileStorageService
   storage = S3FileStorageService(client=get_s3_client(), bucket=s3_bucket_name())
   print(ExampleDataService(storage, httpx2.Client()).copy_store('ac-dc-meshed', UUID('PROJECT_UUID')))
   "
   ```

6. List the playbooks you can run, then look at one in detail. The detail
   shows each step's block, its settings schema, and the playbook's
   `default_config`:

   ```bash
   curl -s http://localhost:8000/v1/playbooks -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/v1/playbooks/expand -H "Authorization: Bearer $TOKEN"
   ```

7. Check a config before running it. The answer lists every issue, each naming
   its step and, where there is one, the setting at fault. This config switches
   the playbook to its myopic branch, which needs a `period`
   dimension the playbook's data does not have. The answer has `"valid": false`
   and one `dims` issue on `expansion_myopic`:

   ```bash
   curl -s -X POST http://localhost:8000/v1/playbooks/expand/validate \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"config": {"globals": {"expansion_mode": "myopic"}}}'
   ```

   Sending `{}` instead checks the `default_config`, which has no issues.

8. Create a run from a revision of the uploaded store. Each step writes its
   output as a new revision into that same store. Leaving out `playbook.config`
   runs the playbook with its `default_config`. A config with issues is refused with a
   `422` listing the same issues the check above returns:

   ```bash
   curl -s -X POST http://localhost:8000/v1/runs \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"project_uuid": "PROJECT_UUID", "playbook": {"name": "expand"}, "data_record": {"store_url": "s3://manta/PROJECT_UUID/ac-dc-meshed", "revision_uuid": "e5f2eacd-ba5c-463c-a663-3017ef904d1d"}}'
   ```

   Copy the returned `uuid` as `RUN_UUID`.

9. Follow the run. The first request returns the run's overall `status`, and the
   `config` and `data_record` it was started with. The second returns each step's `status`:
   `SKIPPED` when the run's config turns the step off, `NOT_STARTED` before it
   begins, and Prefect's own state from then on, plus its `output` record once
   it has completed, or the `message` with its error if it failed. The third returns the run's
   logs:

   ```bash
   curl -s http://localhost:8000/v1/runs/RUN_UUID -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/v1/runs/RUN_UUID/steps -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/v1/runs/RUN_UUID/logs -H "Authorization: Bearer $TOKEN"
   ```

   Repeat them until the run's `status` is `COMPLETED`.

10. Each step that ran wrote a new revision into the uploaded store, under
    `PROJECT_UUID/ac-dc-meshed/revisions/`. The steps response names it as the step's
    `output` (`store_url` and `revision_uuid`). The last step that ran holds the
    run's final record.

11. Tear down (from `docker/`, in the third terminal). This also stops the
    stack in the first terminal. Stop the backend in the second terminal with
    `Ctrl+C`:

    ```bash
    docker compose --env-file ../backend/.env -f compose-dev-services.yaml down -v
    ```
