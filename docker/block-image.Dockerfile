# The image a block's flow run actually executes in, built in two stages.
#
# Stage 1, `bare`: one block environment, as an image — playbook-library plus
# the dependencies the blocks of that environment need, and nothing else. No
# Prefect, no orchestration code. This is exactly the environment an outside
# block author writes and tests against, so passing their suite here means
# passing in Manta.
#
# Stage 2, `block-prefect-runtime`: a thin layer on top adding Prefect and
# `runner`. Named for what it specifically is — the Prefect-flavored runtime a
# block executes under, not "the" runtime a block needs in general; `playbook`
# itself has no opinion about Prefect at all, and a caller using
# `LocalStepRunner` directly needs none of this. One throwaway container per
# block step of a playbook run is started from it by the docker work pool's
# worker; those containers are siblings of the compose stack (they won't
# appear in `docker compose ps`), joined to its network so they can reach
# seaweedfs, and removed when they finish.
#
# Why it cannot simply be `bare`: a Prefect worker never marks a flow run
# COMPLETED itself — it only reports CRASHED on a non-zero exit. The terminal
# state and the result are reported by the Prefect engine running *inside* the
# container. A `bare` container would run the block correctly, exit 0, and
# leave the flow run PENDING forever.
#
# Only one stage is ever compose-managed (see `block-image-builder-pypsa` in
# compose-dev-services.yaml, which builds `block-prefect-runtime` and tags it
# as MANTA_BLOCK_PREFECT_RUNTIME_IMAGE_PYPSA): `bare` exists so the split above
# is real and testable, not so anyone builds and runs it on its own. Reach it
# directly with `docker build --target bare` if you ever need to.
#
# TODO(post-MVP): this whole file — not just the runtime image-name mapping in
# `runner.config.exec_image` — is a build-time shortcut that couples Manta's
# own repo to one specific block library (`playbook-library`, hardcoded below).
# Once `playbook` is published and playbook-library is extracted to its own
# repo, the `bare` stage belongs there: the library should build and publish
# its own bare image, and this file should only build `block-prefect-runtime`,
# `FROM` whatever the library publishes. Not done now because `playbook` isn't
# published yet — `bare` still needs playbook's source copied in alongside
# playbook-library's, so the two can't really be built independently until
# that changes.
#
# Built from the repo root (see compose-dev-services.yaml), with the repo-root
# .dockerignore keeping the context down to the packages copied below.

FROM python:3.12-slim AS bare

ARG LIBRARY_EXTRAS=pypsa
ARG ENV_NAME=pypsa

WORKDIR /opt/manta

COPY playbook ./playbook
COPY playbook-library ./playbook-library

# playbook-library depends on playbook by a local path (see its pyproject.toml),
# which means nothing to plain pip — installing it first is what makes pip
# resolve that dependency against what's already on disk instead of an index.
RUN pip install --no-cache-dir "./playbook[s3]" \
    && pip install --no-cache-dir "./playbook-library[${LIBRARY_EXTRAS}]"

# Used by the block catalogue and error messages, not for dependency resolution.
ENV MANTA_ENV=${ENV_NAME}

FROM bare AS block-prefect-runtime

# Matches CODE_PATH in runner.deploy: the deployment points Prefect at a
# directory the container already has, so starting a flow run is a `cd` rather
# than a copy.
WORKDIR /app

COPY runner ./runner

# playbook is already installed by the `bare` stage, so pip resolves runner's
# dependency on it against what's present rather than an index (it isn't
# published, and tool.uv.sources means nothing to pip). The `docker` extra is
# deliberately absent: nothing here talks to the Docker daemon.
RUN pip install --no-cache-dir ./runner
