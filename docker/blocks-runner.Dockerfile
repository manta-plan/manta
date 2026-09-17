# The one image every block runs in (see playbook-proposal.md): the docker work
# pool spawns a fresh container from this image per dispatched flow run — one for
# the playbook orchestrator, one per block step.
#
# Built from the repo root (see compose-dev-services.yaml), with the repo-root
# .dockerignore keeping the context down to the two packages copied below.
#
# For the MVP the block/runtime code is baked in ("fetched locally from the
# manta-blocks module") and deployments point at it by module path; post-MVP the
# deployments can fetch from the manta-blocks git repo instead, at which point
# this image becomes dependencies-only. One image also implies one dependency
# environment — when blocks with conflicting environments appear, this grows
# into an image per environment (manta_runtime/deploy.py documents that seam).
FROM python:3.12-slim

WORKDIR /opt/manta

COPY manta-blocks ./manta-blocks
COPY manta-runtime ./manta-runtime

# One resolve for both: manta-runtime's manta-blocks[s3] dependency is satisfied
# by the local directory installed alongside it.
RUN pip install --no-cache-dir "./manta-blocks[s3,pypsa]" "./manta-runtime"

# The environment the library blocks declare (ENV = "pypsa"); used by the block
# catalogue and error messages, not for dependency resolution.
ENV MANTA_ENV=pypsa
