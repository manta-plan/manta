# The Prefect worker that watches the manta-blocks docker work pool and turns
# each dispatched flow run into its own container (via the host docker socket —
# see compose-dev-services.yaml). Same base image and Prefect version as the
# server; prefect-docker is what teaches it to drive docker work pools.
FROM prefecthq/prefect:3.8.3-python3.12

RUN pip install --no-cache-dir prefect-docker==0.6.6
