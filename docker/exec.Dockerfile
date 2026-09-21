# The image a block's flow run actually executes in: one throwaway container per
# step, started by the docker work pool's worker.
#
# It is a thin layer over the bare blocks runner image, and that split is the
# point. The base image is what a block author writes, tests and runs against —
# manta-blocks plus the block's own dependencies, no Prefect, no Manta. This
# layer adds only what the work pool requires: a Prefect that can report the flow
# run's state back to the server, and manta-runtime for the ~15-line `run-block`
# flow that looks a block up by name and calls it.
#
# Why the base image cannot simply be used directly: a Prefect worker never marks
# a flow run COMPLETED itself — it only reports CRASHED on a non-zero exit. The
# terminal state and the result come from the Prefect engine running inside the
# container. A container with no Prefect would run the block correctly, exit 0,
# and leave the flow run PENDING forever.
#
# Block authors neither build nor name this image. Build context is the repo root.
ARG BLOCKS_IMAGE=manta-blocks-runner:latest
FROM ${BLOCKS_IMAGE}

COPY manta-runtime/ /app/manta-runtime/

# manta-blocks is already installed in the base image, so pip resolves
# manta-runtime's dependency on it against what is present rather than an index
# (the package is not published, and `tool.uv.sources` means nothing to pip).
# The `docker` extra is deliberately absent: nothing here talks to a daemon.
RUN pip install --no-cache-dir /app/manta-runtime

# Matches CODE_PATH in manta_runtime.deploy: the deployment points Prefect at a
# directory the container already has, so starting a flow run is a `cd`.
WORKDIR /app
