"""Make this stack able to run playbooks: create its work pools, register its deployments.

    python -m manta_runtime.deploy

Run as the one-shot `playbooks-provision` service in compose, before the workers
start. Running it again is harmless — pools and deployments are created or
updated, never duplicated, which is also how an image or wiring change rolls out.

Two kinds of pool, because the two kinds of work want different things:

- **docker**, for blocks. Each step gets its own throwaway container, with the
  pool's job template carrying the image, network and environment those
  containers need.
- **process**, for the orchestrator. `run_playbook` blocks for the whole
  playbook, so it runs inside a long-lived worker rather than in a container that
  would idle for hours waiting on its steps.

This is Manta's local apply layer: `manta-blocks` works out *what* a playbook
needs, and this file decides *how* it exists here. Kubernetes is the same seam in
a future `manta-infra`, and changes the pool's type rather than anything above it.
"""

import logging

from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import WorkPoolCreate, WorkPoolUpdate
from prefect.exceptions import ObjectAlreadyExists
from prefect.runner.storage import LocalStorage
from prefect.types.entrypoint import EntrypointType

from manta_runtime import config
from manta_runtime.flows import BLOCK_FLOW_NAME, PLAYBOOK_FLOW_NAME, run_block, run_playbook

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CODE_PATH = "/app"
"""Where the worker already has this package; matches control.Dockerfile's WORKDIR.

Prefect's default storage step copies a deployment's whole working directory
before every run. Pointing it at a directory that is already there makes starting
a run a `cd` rather than a copy.
"""


def register_result_storage() -> None:
    """Where a step's output record is persisted, so the orchestrator can read it.

    On the object store rather than a shared volume: a volume would be the one
    thing tying every container to a single machine. Only the small record
    pointers go here — model data never passes through Prefect at all.
    """
    from botocore.config import Config
    from prefect_aws import AwsCredentials, S3Bucket
    from prefect_aws.client_parameters import AwsClientParameters

    access_key, secret_key = config.s3_credentials()
    credentials = AwsCredentials(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        # SeaweedFS has no bucket-subdomain DNS, so path-style addressing — the
        # same reason manta-blocks' storage module uses it.
        aws_client_parameters=AwsClientParameters(
            endpoint_url=config.s3_endpoint(),
            config=Config(s3={"addressing_style": "path"}),
        ),
    )
    S3Bucket(
        bucket_name=config.s3_bucket(),
        bucket_folder="prefect-results",
        credentials=credentials,
    ).save(config.RESULT_STORAGE_BLOCK_NAME, overwrite=True)
    logger.info("Registered result storage %r", config.RESULT_STORAGE_BLOCK)


def docker_job_template() -> dict:
    """A docker work pool's job template: each job is a container running a block.

    The image, network and environment become defaults for every job the pool
    runs; a deployment, or a single run, can still override any of them through
    its own job variables — which is how a per-environment image is chosen.
    """
    from prefect_docker.worker import DockerWorker

    template = DockerWorker.get_default_base_job_template()
    defaults = {
        "image": config.exec_image(),
        # The image is built locally and never pushed, so a `latest` tag must not
        # send the worker to a registry first.
        "image_pull_policy": "Never",
        # Job containers are throwaway by design; their logs live in Prefect.
        "auto_remove": True,
        "env": config.job_environment(),
        "networks": [config.docker_network()],
    }
    variables = template["variables"]["properties"]
    for key, value in defaults.items():
        variables[key]["default"] = value
    return template


def ensure_docker_pool(name: str, base_job_template: dict) -> None:
    """Create the docker work pool `name`, or bring it up to date.

    Unlike a process pool, an existing pool is updated rather than left alone: the
    template carries the image and wiring, and re-provisioning is how changes to
    those roll out.
    """
    create = WorkPoolCreate(name=name, type="docker", base_job_template=base_job_template)
    with get_client(sync_client=True) as client:
        try:
            client.create_work_pool(create)
            logger.info("Created work pool %r", name)
        except ObjectAlreadyExists:
            client.update_work_pool(
                work_pool_name=name, work_pool=WorkPoolUpdate(base_job_template=base_job_template)
            )
            logger.info("Updated work pool %r", name)


def ensure_process_pool(name: str) -> None:
    """Create the process work pool `name`, or leave it be if it already exists."""
    with get_client(sync_client=True) as client:
        try:
            client.create_work_pool(WorkPoolCreate(name=name, type="process"))
            logger.info("Created work pool %r", name)
        except ObjectAlreadyExists:
            logger.info("Work pool %r already exists", name)


def deploy(flow, name: str, pool: str) -> str:
    """Create or update one of the two deployments a playbook run is made of."""
    deployment = flow.to_deployment(
        name=name,
        work_pool_name=pool,
        # Record `manta_runtime.flows:<flow>` rather than a file path: whatever
        # runs it finds the flow by importing it from its own installed packages.
        entrypoint_type=EntrypointType.MODULE_PATH,
    )
    deployment.storage = LocalStorage(path=CODE_PATH)
    deployment_id = str(deployment.apply())
    logger.info("Deployed %s/%s onto pool %r", name, name, pool)
    return deployment_id


def main() -> None:
    register_result_storage()

    blocks_pool = config.blocks_pool()
    ensure_docker_pool(blocks_pool, docker_job_template())
    deploy(run_block, BLOCK_FLOW_NAME, blocks_pool)

    orchestrator_pool = config.orchestrator_pool()
    ensure_process_pool(orchestrator_pool)
    deploy(run_playbook, PLAYBOOK_FLOW_NAME, orchestrator_pool)


if __name__ == "__main__":
    main()
