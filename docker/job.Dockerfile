# The image a block actually runs in: one throwaway container per block run, spawned
# by the docker work pool's worker. Also the image of the long-lived orchestrator
# worker, which runs `run_playbook` in-process and so needs the same packages.
#
# Build context is the repo root, since the image needs manta-blocks as well as
# manta-batteries. Nothing docker-specific is installed here — the worker that talks
# to the docker daemon is a separate, slim image (control.Dockerfile).
#
# One image carries both pixi environments and each container activates one with
# `pixi run -e <env>`; per the playbooks requirements proposal, the eventual shape is
# one image per block environment built in CI (and `manta-infra` for production
# Kubernetes), but a single dev image keeps the local stack to one build.
FROM ghcr.io/prefix-dev/pixi:0.70.2

COPY manta-blocks/ /app/manta-blocks/
COPY manta-batteries/ /app/manta-batteries/

WORKDIR /app/manta-batteries

# Bake the environments at build time so workers start instantly; --locked insists
# the committed pixi.lock is in step with pixi.toml instead of quietly re-solving.
RUN pixi install --locked -e orchestrator -e pypsa
