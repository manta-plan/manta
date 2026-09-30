# The image for the `runner` package itself: everything that talks to the
# Prefect API and the Docker daemon but never runs a block — the one-shot
# provisioner, the worker draining the blocks work pool, and the worker running
# the playbook orchestration flow. Mirrors `block-image.Dockerfile` on the
# other side of the same boundary: one Dockerfile per side of the runner /
# block-library split this whole design is built around.
#
# It holds `runner` (the run-playbook flow and the container transport) and
# `playbook` (the playbook engine and the block catalogue types), and no block
# library at all — orchestration only ever moves record pointers around, and
# resolves blocks from the catalogue it is handed rather than importing them.
# That is what keeps this image slim while block images stay bare.
#
# Build context is the repo root.
FROM prefecthq/prefect:3.8.3-python3.12

# Matches CODE_PATH in runner.deploy: the deployment points Prefect at a
# directory the worker already has, so starting a flow run is a `cd` rather
# than a copy.
WORKDIR /app

COPY playbook ./playbook
COPY runner ./runner

# playbook first and on its own: runner depends on it by name, and pip resolves
# that against what is already installed rather than an index (the package is
# not published, and `tool.uv.sources` means nothing to pip).
#
# The `docker` extra adds prefect-docker, which is what builds the blocks work
# pool's job template and drains it. Only this image has it: block containers
# never talk to a daemon.
RUN pip install --no-cache-dir ./playbook \
    && pip install --no-cache-dir "./runner[docker]"
