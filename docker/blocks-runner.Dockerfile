# One block environment, as an image: manta-blocks plus the dependencies the
# blocks of that environment need, and nothing else — no Prefect, no Manta.
#
# This is exactly the environment an outside block author tests against, so
# passing their suite here means passing in Manta. Manta layers its own execution
# image on top of it rather than into it (see exec.Dockerfile), which is what
# keeps that true.
#
# A block declares the environment it needs as a name (`ENV = "pypsa"`), and one
# image is built per environment, so two frameworks that could never share a
# virtualenv can both appear in a playbook. BLOCK_EXTRAS names the manta-blocks
# extras that environment's blocks need; ENV_NAME is the name they declare.
#
# Built from the repo root (see compose-dev-services.yaml), with the repo-root
# .dockerignore keeping the context down to the one package copied below.
FROM python:3.12-slim

ARG BLOCK_EXTRAS=s3,pypsa
ARG ENV_NAME=pypsa

WORKDIR /opt/manta

COPY manta-blocks ./manta-blocks

RUN pip install --no-cache-dir "./manta-blocks[${BLOCK_EXTRAS}]"

# Used by the block catalogue and error messages, not for dependency resolution.
ENV MANTA_ENV=${ENV_NAME}
