# Manta

Manta is an open-source energy modeling tool, designed to make cutting-edge
energy models (especially PyPSA) accessible to all.

More to come, soon!

## Repository Structure

This is a monorepo containing the backend, frontend, and local deployment
tooling:

```
manta/
├── backend/    # Python/FastAPI backend — see backend/README.md
├── frontend/   # React/Vite frontend — see frontend/README.md
└── docker/     # local dev services (Postgres) — see docker/README.md
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for coding standards and architecture, and
the package-level READMEs for setup instructions:

- [backend/README.md](backend/README.md) for the FastAPI backend.
- [frontend/README.md](frontend/README.md) for the React frontend.
- [docker/README.md](docker/README.md) for local services and Docker notes.
