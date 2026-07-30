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
