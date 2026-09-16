# The image for everything that talks to the Prefect API and the docker daemon but
# never runs a block: the worker draining a docker work pool, and the one-shot
# provision container.
#
# A docker-type worker only spawns containers, so it needs neither pixi nor PyPSA —
# which is what keeps `prefect-docker` out of manta-blocks and manta-batteries.
# manta-blocks is installed because registering a deployment needs the flow object.
# Build context is the repo root.
FROM prefecthq/prefect:3.8.3-python3.12

COPY manta-blocks/ /app/manta-blocks/
COPY docker/provision.py /app/provision.py

RUN pip install --no-cache-dir /app/manta-blocks prefect-docker

WORKDIR /app
