# Manta

Manta is an open-source energy modeling tool, designed to make cutting-edge
energy models (especially PyPSA) accessible to all.

More to come, soon!

## Repository Structure

This is a monorepo containing the backend, frontend, and local deployment
tooling:

```
manta/
├── backend/           # Python/FastAPI backend — see backend/README.md
├── frontend/          # React/Vite frontend — see frontend/README.md
├── playbook/          # blocks and playbooks: the modelling framework
├── playbook-library/  # the blocks and playbooks Manta ships, built on PyPSA
└── docker/            # local dev services (Postgres, SeaweedFS) — see docker/README.md
```

`playbook/` and `playbook-library/` are standalone Python packages that know nothing
about the Manta app: the first defines what a block and a playbook are, the second is
the modelling content built on them. They live here for now, but are written to move
to their own repositories.

See [CONTRIBUTING.md](CONTRIBUTING.md) for coding standards and architecture, and
the package-level READMEs for setup instructions:

- [backend/README.md](backend/README.md) for the FastAPI backend.
- [frontend/README.md](frontend/README.md) for the React frontend.
- [playbook/README.md](playbook/README.md) for writing blocks and playbooks.
- [playbook-library/README.md](playbook-library/README.md) for the blocks and playbooks Manta ships.
- [docker/README.md](docker/README.md) for local services and Docker notes.
