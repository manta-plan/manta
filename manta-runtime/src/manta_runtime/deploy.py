"""Make everything Prefect needs to run playbooks exist: pool and deployments.

    python -m manta_runtime.deploy

Run automatically when the dev stack boots (see docker/compose-dev-services.yaml:
the prefect-deployer service runs this from inside the blocks runner image, before
the worker starts). It is idempotent - creating the same pool or deployment again
just updates it - so booting the stack repeatedly is harmless.

What it creates:
- one docker work pool: every dispatched flow run becomes its own container from the
  blocks runner image. Moving execution to k8s later means creating a kubernetes
  work pool here (and a worker for it) - nothing above this layer changes.
- two static deployments, `run-playbook` and `run-block`. Playbooks and their
  configs travel as flow-run *parameters*, so nothing is ever deployed per playbook
  or per block.

The deployments point at this package as installed in the runner image (module-path
entrypoints): that is the proposal's "fetch the code locally from the manta-blocks
module". Fetching from git later means swapping the `.deploy(...)` calls below for
`flow.from_source("https://github.com/.../manta-blocks", ...).deploy(...)`.
"""

import logging
import os

from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import WorkPoolCreate
from prefect.deployments.runner import EntrypointType
from prefect.exceptions import ObjectAlreadyExists
from prefect_docker.worker import DockerWorker

from manta_runtime.flows import run_block, run_playbook

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

WORK_POOL = os.environ.get("MANTA_BLOCKS_WORK_POOL", "manta-blocks")
"""The docker work pool block/playbook runs are dispatched to."""

IMAGE = os.environ.get("MANTA_BLOCKS_IMAGE", "manta-blocks-runner:latest")
"""The one image every block runs in (built by docker/blocks-runner.Dockerfile)."""

NETWORK = os.environ.get("MANTA_DOCKER_NETWORK", "manta_default")
"""The docker network job containers join, so they can reach Prefect and S3."""

_JOB_ENV_KEYS = (
    # How a job container reaches the Prefect API and the object store. These are
    # the compose-internal addresses, taken from this process's own environment
    # (the deployer runs on the same network the jobs will).
    "PREFECT_API_URL",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ENDPOINT_URL",
    "AWS_DEFAULT_REGION",
)


def job_environment() -> dict[str, str]:
    """The environment every job container is started with."""
    return {key: os.environ[key] for key in _JOB_ENV_KEYS if os.environ.get(key)}


def ensure_work_pool() -> None:
    """Create the docker work pool if it does not exist yet."""
    with get_client(sync_client=True) as client:
        try:
            client.create_work_pool(
                WorkPoolCreate(
                    name=WORK_POOL,
                    type=DockerWorker.type,
                    description="Runs Manta blocks, one container per block run.",
                    base_job_template=DockerWorker.get_default_base_job_template(),
                )
            )
            logger.info("Created work pool %r", WORK_POOL)
        except ObjectAlreadyExists:
            logger.info("Work pool %r already exists", WORK_POOL)


def deploy() -> None:
    """Create or update the two deployments playbook runs are made of."""
    job_variables = {
        "image_pull_policy": "Never",  # the image is built locally, never pulled
        "networks": [NETWORK],
        "auto_remove": True,  # logs live in Prefect; spent containers just pile up
        "env": job_environment(),
    }
    for entrypoint_flow in (run_playbook, run_block):
        entrypoint_flow.deploy(
            name=entrypoint_flow.name,
            work_pool_name=WORK_POOL,
            image=IMAGE,
            build=False,
            push=False,
            # The code is already installed in the image as a package, so the
            # deployment records `manta_runtime.flows.<flow>` rather than a file path.
            entrypoint_type=EntrypointType.MODULE_PATH,
            job_variables=job_variables,
            print_next_steps=False,
            ignore_warnings=True,
        )
        logger.info(
            "Deployed %s/%s onto pool %r (image %r, network %r)",
            entrypoint_flow.name,
            entrypoint_flow.name,
            WORK_POOL,
            IMAGE,
            NETWORK,
        )


def main() -> None:
    ensure_work_pool()
    deploy()


if __name__ == "__main__":
    main()
