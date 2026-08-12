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

## First-time Setup

Install the package managers used by each package:

- [uv](https://docs.astral.sh/uv/) for the Python backend.
- [pnpm](https://pnpm.io/) for the frontend. The frontend is pinned to pnpm
  `11.10.0` in `frontend/package.json`.
- [Docker](https://docs.docker.com/) if you need local services, integration
  tests, or the sample frontend static-serving image.

Backend dependencies:

```bash
cd backend
uv sync
```

Frontend dependencies:

```bash
cd frontend
pnpm install
```

## Running Locally

Backend:

```bash
cd backend
uv run manta
```

Frontend:

```bash
cd frontend
pnpm dev
```

The frontend dev server prints the local URL, usually
`http://localhost:5173`.

## Common Checks

Backend:

```bash
cd backend
uv run ruff check .
uv run ruff format .
uv run pytest
```

Frontend:

```bash
cd frontend
pnpm fmt:check
pnpm lint
pnpm build
```
