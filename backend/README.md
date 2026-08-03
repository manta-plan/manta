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

```bash
uv run manta
```

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

We use [pytest](https://docs.pytest.org/).

```bash
uv run pytest                     # everything
uv run pytest tests/unit          # unit tests only
uv run pytest tests/integration   # integration tests only
```

### Integration tests

Integration tests need a running [Docker](https://docs.docker.com/) daemon. 
`tests/integration/conftest.py` boots the required service
containers itself (via [testcontainers](https://testcontainers-python.readthedocs.io/),
reusing [`docker/compose.services.yaml`](../docker/compose.services.yaml)) and
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
