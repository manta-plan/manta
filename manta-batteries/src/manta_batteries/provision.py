# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Make a Prefect installation ready to run any playbook of this library's blocks.

    pixi run -e pypsa python -m manta_batteries.provision

Run it inside the `pypsa` environment, so every block can be imported and described.
It creates the work pools and registers one deployment per block plus the playbook
orchestrator, against the Prefect server at `PREFECT_API_URL`. Running it again is
harmless: pools and deployments are created or updated, never duplicated.

Two kinds of pool, chosen by `MANTA_POOL_TYPE`:

- `docker` (the default, what Manta's dev stack uses): every job - each playbook
  run and each block run - executes in its own container, spawned by a docker
  worker from `MANTA_JOB_IMAGE`. The pool's job template carries the network,
  volumes, and environment the containers need (see the MANTA_JOB_* variables
  below), defaulting to the names Manta's docker compose produces.
- `process`: jobs run as subprocesses of a worker started inside the matching
  pixi environment - the no-docker path for power users running against their
  own Prefect server.

Kubernetes work pools are the same seam later (the future `manta-infra` repo);
nothing here needs to change for that beyond another pool factory.

This is what the `playbooks-provision` one-shot container in Manta's docker compose
runs at start-up.
"""

import os
import sys

from manta_blocks import catalogue
from manta_playbooks import docker_job_template, ensure_docker_pool, provision_catalogue

DEFAULT_ORCHESTRATOR_ENV = "orchestrator"
"""The environment the playbook orchestrator runs in.

Kept in step with `MANTA_ORCHESTRATOR_ENV` in the Manta backend and the
`prefect-worker-orchestrator` service in docker/compose-dev-services.yaml: the
backend starts runs on the deployment this name produces, and that worker's pool
name decides which queue it drains.
"""

RESULTS_PATH = "/prefect-results"
"""Where job containers persist flow results (the record pointers blocks return).

The orchestrator's job container reads a block's result from here, so every pool
mounts the same volume at this path; `MANTA_JOB_VOLUMES` must stay consistent
with it.
"""

_JOB_ENV_PASSTHROUGH = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ENDPOINT_URL",
)
"""Handed from this process to every job container: where records live in S3."""


def _docker_pool_factory():
    """A pool factory running each job in its own container, configured from env.

    Defaults match what `docker compose --profile playbooks` produces: the image
    built by docker/worker.Dockerfile, the compose project's network, and its
    shared results volume.
    """
    image = os.environ.get("MANTA_JOB_IMAGE", "manta-playbooks-worker")
    network = os.environ.get("MANTA_JOB_NETWORK", "manta_default")
    volumes = [
        volume.strip()
        for volume in os.environ.get(
            "MANTA_JOB_VOLUMES", f"manta_prefect-results:{RESULTS_PATH}"
        ).split(",")
        if volume.strip()
    ]
    job_env = {
        "MANTA_BLOCK_SOURCES": "manta_batteries",
        "PREFECT_LOCAL_STORAGE_PATH": RESULTS_PATH,
        **{
            name: os.environ[name]
            for name in _JOB_ENV_PASSTHROUGH
            if name in os.environ
        },
    }

    def factory(pool: str, env_name: str) -> None:
        template = docker_job_template(
            env_name, image=image, env=job_env, network=network, volumes=volumes
        )
        ensure_docker_pool(pool, template)

    return factory


def main() -> int:
    described = catalogue()
    if not described.blocks:
        print(
            "No blocks could be imported here, so there is nothing to provision. "
            "Run this in the `pypsa` environment.",
            file=sys.stderr,
        )
        return 1

    pool_type = os.environ.get("MANTA_POOL_TYPE", "docker")
    if pool_type not in ("docker", "process"):
        print(
            f"MANTA_POOL_TYPE must be 'docker' or 'process', not {pool_type!r}",
            file=sys.stderr,
        )
        return 1
    pool_factory = _docker_pool_factory() if pool_type == "docker" else None

    orchestrator_env = os.environ.get(
        "MANTA_ORCHESTRATOR_ENV", DEFAULT_ORCHESTRATOR_ENV
    )
    ids = provision_catalogue(
        described, orchestrator_env=orchestrator_env, pool_factory=pool_factory
    )
    print(
        f"Provisioned {len(described.blocks)} block(s) and the orchestrator "
        f"({len(ids)} deployment(s)) on {pool_type} pools"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
