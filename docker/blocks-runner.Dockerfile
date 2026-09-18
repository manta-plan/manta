# The one image every block runs in (see playbook-proposal.md): the backend
# spawns a fresh container from this image per block step of a playbook run,
# running the orchestration-agnostic `python -m blocks.run_one` entrypoint.
#
# Deliberately dumb: manta-blocks plus the blocks' own dependencies, and nothing
# else — no Prefect, no Manta. This is exactly the environment an outside block
# author tests against, so passing their suite here means passing in Manta.
#
# Built from the repo root (see compose-dev-services.yaml), with the repo-root
# .dockerignore keeping the context down to the one package copied below. One
# image also implies one dependency environment — when blocks with conflicting
# environments appear, this grows into an image per environment (the backend's
# playbook_flows.py documents that seam).
FROM python:3.12-slim

WORKDIR /opt/manta

COPY manta-blocks ./manta-blocks

RUN pip install --no-cache-dir "./manta-blocks[s3,pypsa]"

# The environment the library blocks declare (ENV = "pypsa"); used by the block
# catalogue and error messages, not for dependency resolution.
ENV MANTA_ENV=pypsa
