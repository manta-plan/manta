# Manta Docker

Local development services, run via [Docker Compose](https://docs.docker.com/compose/).

**Not meant for production.** These compose files are for local dev only —
no restart policy (crashes should be visible, not silently healed), default
credentials, no backups/replication. Production deployment is a separate,
not-yet-addressed concern.

## Usage

```bash
docker compose --env-file ../backend/.env -f compose.services.yaml up -d
```

Configuration (credentials, port) lives in [`backend/.env`](../backend/.env)
— the same file the backend app reads — not here, so there's one source of
truth instead of two.

## Testing

`compose.test.yaml` is an overlay (not a standalone file) used only by the
backend's integration test suite — see
[backend/tests/integration/conftest.py](../backend/tests/integration/conftest.py).
It reuses `compose.services.yaml` for the actual service definitions, but
gives the stack its own project name and a random host port, so a test run
never clashes with a locally running dev stack. You don't need to run it
yourself; `uv run pytest tests/integration` boots and tears it down
automatically.
