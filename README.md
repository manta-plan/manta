# Manta

Manta is an open-source energy modeling tool, designed to make cutting-edge
energy models accessible to all.

More to come, soon!

## Repository Structure

This is a monorepo containing the backend, frontend, and local deployment
tooling:

```
manta/
├── backend/    # Python/FastAPI backend — see backend/README.md
├── frontend/   # React/Vite frontend — see frontend/README.md
└── docker/     # local dev services (Postgres, SeaweedFS) — see docker/README.md
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for coding standards and architecture, and
the package-level READMEs for setup instructions:

- [backend/README.md](backend/README.md) for the FastAPI backend.
- [frontend/README.md](frontend/README.md) for the React frontend.
- [docker/README.md](docker/README.md) for local services and Docker notes.

## Deployment

Currently a test instance is deployed for internal purposes, in `europe-north2`
(Stockholm). Its container name is `manta-adhoc-2` (no points for creativity).

### Setup

On a base Debian image, we begin by refreshing the system and installing docker. See [the official docs](https://docs.docker.com/engine/install/debian/).

```bash
sudo apt update # update repositories
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

You need to additionally, explicitly pull down manta afterwards.

```bash
git clone https://github.com/manta-plan/manta
```

Now we can spin up the dependencies:

```bash
cd manta
docker compose -f docker/compose-dev-services.yaml --env-file backend/.env up -d
```

Now that the dependencies are running, it's time to spin up a runtime instance.

Install python, nodejs, pnpm, and uv, to allow for building and running the application.

```bash
sudo apt install nodejs npm
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv python install
curl -fsSL https://get.pnpm.io/install.sh | sh -
source ~/.bashrc # reload to get access to pnpm
```

Build the frontend files

```bash
cd frontend
pnpm install && pnpm build
```

Spin up the backend

```bash
cd ../backend
uv sync
uv run uvicorn manta.main:app --host 0.0.0.0 --port 8000
```

This runs in an attached mode, you can use `ctrl-z` to pause it and then `bg` to
background the task, or use `nohup` / `disown` to detach it from your ssh process and let it live on. 

### Summary

This is a very quick and dirty guide to spinning up an instance of manta. There
are many many issues with this right now, but a proper deployment with terraform
etc. is on the way.
