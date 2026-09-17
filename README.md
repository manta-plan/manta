# Manta

Manta is an open-source energy modeling tool, designed to make cutting-edge
energy models (especially PyPSA) accessible to all.

More to come, soon!

## Repository Structure

This is a monorepo containing the backend, frontend, the modeling-domain
packages, and local deployment tooling:

```
manta/
├── backend/        # Python/FastAPI backend — see backend/README.md
├── frontend/       # React/Vite frontend — see frontend/README.md
├── manta-blocks/   # blocks & playbooks: units of modeling work, orchestration-agnostic
│                   #   (destined for its own repository — see manta-blocks/README.md)
├── manta-runtime/  # the Prefect runtime that executes playbooks — see manta-runtime/README.md
└── docker/         # local dev services (Postgres, SeaweedFS, Prefect, ...) — see docker/README.md
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for coding standards and architecture, and
the package-level READMEs for setup instructions:

- [backend/README.md](backend/README.md) for the FastAPI backend.
- [frontend/README.md](frontend/README.md) for the React frontend.
- [manta-blocks/README.md](manta-blocks/README.md) for writing blocks and playbooks.
- [manta-runtime/README.md](manta-runtime/README.md) for how playbook runs execute.
- [docker/README.md](docker/README.md) for local services and Docker notes.
