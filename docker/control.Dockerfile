# The image for everything that talks to the Prefect API and the docker daemon
# but never runs a block: the one-shot provisioner, and the long-lived worker
# that runs playbook orchestration.
#
# It holds manta-runtime (the run-playbook flow and the container transport) and
# manta-blocks (the playbook engine and the block catalogue), and neither PyPSA
# nor any block dependency — orchestration only ever moves record pointers
# around, and resolves blocks from the committed catalogue rather than importing
# them. That is what keeps this image slim while block images stay bare.
#
# Build context is the repo root.
FROM prefecthq/prefect:3.8.3-python3.12

COPY manta-blocks/ /app/manta-blocks/
COPY manta-runtime/ /app/manta-runtime/

# manta-blocks first and on its own: manta-runtime depends on it by name, and
# pip resolves that against what is already installed rather than an index (the
# package is not published, and `tool.uv.sources` means nothing to pip).
#
# The `docker` extra adds prefect-docker, which is what creates the blocks work
# pool's job template and drains it. Only this image has it: block containers
# never talk to a daemon.
RUN pip install --no-cache-dir /app/manta-blocks \
    && pip install --no-cache-dir "/app/manta-runtime[docker]"

# Matches MANTA_CODE_PATH: the deployment points Prefect at a directory the
# worker already has, so starting a flow run is a `cd` rather than a copy.
WORKDIR /app
