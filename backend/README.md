<!--
SPDX-FileCopyrightText: Manta contributors

SPDX-License-Identifier: Apache-2.0
-->

# Manta Backend

The Manta backend is built with [Python](https://www.python.org/) and
[FastAPI](https://fastapi.tiangolo.com/), using [uv](https://docs.astral.sh/uv/)
for dependency management. See the repo-level
[CONTRIBUTING.md](../CONTRIBUTING.md) for the architecture and coding standards
this package follows.

<!-- --8<-- [start:docs-setup] -->
## Setup

```bash
uv sync
```

## Running

The backend is served at `localhost:8000`, set by `APP_HOST` and `APP_PORT` in
`backend/.env`.

```bash
uv run manta
```
<!-- --8<-- [end:docs-setup] -->

<!-- --8<-- [start:docs-dev] -->
## Database migrations

We use [Alembic](https://alembic.sqlalchemy.org/) for Postgres DB migrations.
Scripts live in `src/manta/migrations/`

The app runs pending migrations automatically on startup (see
`src/manta/migrations/runner.py`), so `uv run manta` always starts against an
up-to-date schema — nothing to run by hand for normal development, beyond
having Postgres up (see [docker/README.md](https://github.com/manta-plan/manta/blob/main/docker/README.md)).

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
locally (see [docker/README.md](https://github.com/manta-plan/manta/blob/main/docker/README.md#services)), via
[`S3FileStorageService`](https://github.com/manta-plan/manta/blob/main/backend/src/manta/services/s3_file_storage_service.py) (boto3
under the hood). Config lives in `backend/.env`, read by
[`src/manta/config/s3_config.py`](https://github.com/manta-plan/manta/blob/main/backend/src/manta/config/s3_config.py). Like
migrations, the target bucket is provisioned automatically on startup (see
`ensure_bucket_exists()` in `main.py`) — nothing to run by hand, beyond having
SeaweedFS up.

### Example data

With `EXAMPLE_DATA_SEED=true` (the default in `backend/.env`), startup also:

1. Downloads the example datarecord stores listed in `EXAMPLE_DATA_STORES` (all
   of them when empty) from the `2026-11-11` folder of the public `manta-public-test-data` bucket, into
   `s3://manta/example-data/<store>`. That belongs to no project, so no run ever
   writes to it. Stores already there are skipped, so
   only a clean SeaweedFS volume pays for the download. Without internet
   access, the app logs a warning and starts without them.
2. Creates the `manta-admin` user, with its Keycloak id pinned in
   [manta-realm.json](https://github.com/manta-plan/manta/blob/main/docker/conf/manta-realm.json) (`0b7b2a6e-4c55-4b1e-9d0e-6f3c2a8e5d41`),
   and its "Example project" `33b9abe3-2f25-4824-89e2-5a3d93671b6c`, unless they
   exist.
3. Copies every downloaded store into that project, under
   `s3://manta/33b9abe3-2f25-4824-89e2-5a3d93671b6c/<store>`, within S3 itself.

With `EXAMPLE_PROJECT_FOR_NEW_USERS=true` (the default), every newly registered
user also gets an "Example project" of their own, with the same copies. A failed
copy only logs a warning: the project is still created, just without the data.

Projects get copies so their runs can write new revisions into them without
touching anyone else's. The stores, sizes and `inputs` revisions:

| Store | Size | `inputs` revision |
| --- | --- | --- |
| `ac-dc-meshed` | 0.1 MB | `1bad4cfd-9f32-4675-aa4b-6cd71660cbc1` |
| `model-energy` | 0.1 MB | `fc70f1c9-1082-46a9-8774-66bd5fad7297` |
| `BEL-pre-aggregated` | 0.5 MB | `8ff7a95a-8aed-42a3-9acb-a2e36906685f` |
| `BEL-pre-aggregated-hourly` | 3.5 MB | `8b7175d6-f540-4aa0-98c0-2df460693ff1` |
| `BEL-pre-aggregated-incl-patches-incl-results` | 13.2 MB | `9ec88f52-d2d7-4785-9cbb-0c9a1da9b827` |
| `BEL-full-res` | 36.3 MB | `0921e11f-1998-4983-9992-9a2f923ed392` |
| `europe-full-res-2030` | 124.4 MB | `2f276825-9deb-4abc-ad57-ceb08f57ea94` |

Each store's `revisions.json` names its revisions, `inputs` being the one a run
starts from. `europe-full-res-2030` is left out of `EXAMPLE_DATA_STORES` by
default for its size. The integration tests download only `ac-dc-meshed`.

Keycloak only imports the realm into a fresh database. If your Keycloak volume
predates the pinned `manta-admin` id, recreate it once with
`docker compose --env-file ../backend/.env -f compose-dev-services.yaml down -v`
(from `docker/`), or `manta-admin` won't own its example project.

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
reusing [`docker/compose-dev-services.yaml`](https://github.com/manta-plan/manta/blob/main/docker/compose-dev-services.yaml)) and
runs the app as a subprocess, all on random ports — so there's nothing to
start by hand first, and it won't clash with or affect a dev stack you might
already have running. Everything is torn down again once the test session
ends. See [docker/README.md](https://github.com/manta-plan/manta/blob/main/docker/README.md#testing) for how the
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

## Authentication

The backend proxies Keycloak's token calls. `manta-client` is a confidential
client, so clients can't call Keycloak directly.

### Refresh tokens

- `POST /v1/auth/login` returns `access_token`, `expires_in`, `refresh_token`
  and `refresh_expires_in`. Lifetimes are in seconds; in the dev realm, 300
  and 1800.
- `POST /v1/auth/refresh` with `{"refresh_token": ...}` returns the same
  fields. No `Authorization` header.
- Every refresh issues a new refresh token. Replace the stored one, as per the
  [OAuth2 spec](https://datatracker.ietf.org/doc/html/rfc6749#section-6): the
  old one keeps its original expiry, and stops working once the realm's
  "Revoke Refresh Token" setting is on.
- An invalid, expired or revoked refresh token returns `401`. Log in again.

### Logout

- `POST /v1/auth/logout` with `{"refresh_token": ...}` ends the Keycloak
  session and returns `204`. No `Authorization` header.
- The session's refresh tokens stop working. Access tokens already issued
  stay valid until they expire, since they're verified by signature alone.
- Logging out an already-ended session returns `204`. An invalid refresh
  token returns `401`.
<!-- --8<-- [end:docs-dev] -->

## Manually testing a run

To run a playbook on real model data through the REST API, follow [Run a playbook through the REST API](../docs/contributing/manual-run.md).
