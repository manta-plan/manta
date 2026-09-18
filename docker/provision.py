"""Make this stack able to run playbooks: create its work pools, register its deployments.

Run as the one-shot `playbooks-provision` service in compose-dev-services.yaml, before
the workers start. Running it again is harmless: pools and deployments are created or
updated, never duplicated, which is also how an image or wiring change rolls out.

Two kinds of pool, because the two kinds of work want different things:

- **docker**, one per block environment. Each block run gets its own throwaway
  container from `MANTA_JOB_IMAGE`, with the pool's job template carrying the network,
  volumes and environment those containers need.
- **process**, for the orchestrator. `run_playbook` blocks for the whole playbook, so
  it runs inside the long-lived orchestrator worker rather than in a container that
  would idle for hours waiting on its children.

This is Manta's local apply layer: `manta-blocks` works out *what* must exist (the
catalogue's blocks and environments, and the names they map to), and this file decides
*how* it exists here. Kubernetes is the same seam in the future `manta-infra` repo.

The catalogue is read from disk rather than built by importing blocks, so this
container needs neither pixi nor PyPSA. For the same reason `MANTA_BLOCK_SOURCES` is
deliberately not read here and must not be set on this container: `manta_blocks`
imports the libraries it names as soon as it is imported. What the *job* containers
should serve is passed as `MANTA_JOB_BLOCK_SOURCES` instead.
"""

import json
import os
import sys
from pathlib import Path

from manta_blocks import Catalogue, EnvironmentSpec
from manta_playbooks import ensure_process_pool, provision_catalogue
from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import WorkPoolCreate, WorkPoolUpdate
from prefect.exceptions import ObjectAlreadyExists
from prefect_docker.worker import DockerWorker

RESULTS_PATH = "/prefect-results"
"""Where job containers persist flow results (the record pointers blocks return).

The orchestrator reads a block's result from here, so it and every job container mount
the same volume at this path; `MANTA_JOB_VOLUMES` must stay consistent with it.
"""

_JOB_ENV_PASSTHROUGH = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENDPOINT_URL")
"""Handed from this process to every job container: where records live."""


def job_template(env_name: str, image: str, env: dict, network: str, volumes: list[str]) -> dict:
    """A docker work pool's job template: each job is a container running `image`.

    The container's command activates the pixi environment `env_name` before handing
    over to Prefect, which is what keeps "which environment does this pool run" a
    property of the pool rather than of any code. `env`, `network` and `volumes` become
    defaults for every job the pool runs; a deployment can still override any of them
    through its own job variables.
    """
    template = DockerWorker.get_default_base_job_template()
    defaults = {
        "image": image,
        "command": f"pixi run -e {env_name} prefect flow-run execute",
        # An image that only exists locally (built by compose, never pushed) must not
        # be pulled: for a `latest` tag the worker would otherwise try the registry
        # first and fail.
        "image_pull_policy": "IfNotPresent",
        # Job containers are throwaway by design; their logs live in Prefect.
        "auto_remove": True,
        "env": env,
        "networks": [network],
        "volumes": volumes,
    }
    variables = template["variables"]["properties"]
    for key, value in defaults.items():
        variables[key]["default"] = value
    return template


def ensure_docker_pool(name: str, base_job_template: dict) -> None:
    """Create the docker work pool `name`, or bring it up to date.

    Unlike a process pool, an existing pool is updated rather than left alone: the
    template carries the image and wiring, and re-provisioning is how changes to those
    roll out. A pool of another type under this name is recreated, since Prefect cannot
    change a pool's type in place - anything deployed onto it goes with it, which is
    fine here because the deployments are re-registered right after.
    """
    create = WorkPoolCreate(name=name, type="docker", base_job_template=base_job_template)
    with get_client(sync_client=True) as client:
        try:
            client.create_work_pool(create)
        except ObjectAlreadyExists:
            if client.read_work_pool(name).type == "docker":
                client.update_work_pool(
                    work_pool_name=name,
                    work_pool=WorkPoolUpdate(base_job_template=base_job_template),
                )
            else:
                client.delete_work_pool(name)
                client.create_work_pool(create)


def job_env() -> dict[str, str]:
    """The environment every job container starts with."""
    return {
        "MANTA_BLOCK_SOURCES": os.environ.get("MANTA_JOB_BLOCK_SOURCES", "manta_batteries"),
        "PREFECT_LOCAL_STORAGE_PATH": RESULTS_PATH,
        **{name: os.environ[name] for name in _JOB_ENV_PASSTHROUGH if name in os.environ},
    }


def create_pools(catalogue: Catalogue, orchestrator_env: str) -> None:
    """One docker pool per block environment, plus the orchestrator's process pool."""
    image = os.environ.get("MANTA_JOB_IMAGE", "manta-playbooks-job")
    network = os.environ.get("MANTA_JOB_NETWORK", "manta_default")
    volumes = [
        volume.strip()
        for volume in os.environ.get(
            "MANTA_JOB_VOLUMES", f"manta_prefect-results:{RESULTS_PATH}"
        ).split(",")
        if volume.strip()
    ]
    env = job_env()

    for spec in catalogue.environments.values():
        ensure_docker_pool(
            spec.resolved_work_pool(), job_template(spec.name, image, env, network, volumes)
        )
    ensure_process_pool(EnvironmentSpec(name=orchestrator_env).resolved_work_pool())


def main() -> int:
    catalogue_path = Path(os.environ.get("MANTA_CATALOGUE_PATH", "/catalogue.json"))
    try:
        catalogue = Catalogue.model_validate(json.loads(catalogue_path.read_text()))
    except OSError as exc:
        print(f"Could not read the block catalogue: {exc}", file=sys.stderr)
        return 1

    orchestrator_env = os.environ.get("MANTA_ORCHESTRATOR_ENV", "orchestrator")
    create_pools(catalogue, orchestrator_env)
    ids = provision_catalogue(
        catalogue,
        orchestrator_env=orchestrator_env,
        create_pools=False,
        # Matches job.Dockerfile's WORKDIR: the code every job container and the
        # orchestrator worker run is baked in there at build time, so deployments
        # can point straight at it instead of paying Prefect's default directory
        # copy (which would otherwise also re-copy the baked pixi environments).
        code_path=os.environ.get("MANTA_JOB_CODE_PATH", "/app/manta-batteries"),
    )
    print(
        f"Provisioned {len(catalogue.blocks)} block(s) and the orchestrator "
        f"({len(ids)} deployment(s)) from {catalogue_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
