"""Make this stack able to run playbooks: create its work pool, register its deployment.

    python -m manta_runtime.deploy

Run as the one-shot `playbooks-provision` service in compose, before the worker
starts. Running it again is harmless — the pool is left alone if it exists and
the deployment is updated rather than duplicated, which is also how a code or
wiring change rolls out.

The orchestrator's pool is a **process** pool: `run_playbook` blocks for the
whole playbook while its steps run, so it belongs in a long-lived worker rather
than in a container that would idle for hours and take the run down with it if
it were evicted.

This is Manta's local apply layer. `manta-blocks` works out *what* a playbook
needs; this file decides *how* it exists here. Kubernetes is the same seam in a
future `manta-infra`.
"""

import logging
import os

from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import WorkPoolCreate
from prefect.exceptions import ObjectAlreadyExists
from prefect.runner.storage import LocalStorage
from prefect.types.entrypoint import EntrypointType

from manta_runtime.flows import PLAYBOOK_FLOW_NAME, run_playbook

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def orchestrator_pool() -> str:
    """The process work pool the playbook orchestrator runs on."""
    return os.environ.get("MANTA_ORCHESTRATOR_POOL", "manta-orchestrator")


def code_path() -> str:
    """Where the worker already has this package, so Prefect need not fetch it.

    Prefect's default storage step copies a deployment's whole working directory
    before every run. The worker runs the same image as this process, with the
    code installed, so point it at a directory that is already there: Prefect
    takes that as a `cd` rather than a copy.
    """
    return os.environ.get("MANTA_CODE_PATH", "/app")


def ensure_process_pool(name: str) -> None:
    """Create the process work pool `name`, or leave it be if it already exists."""
    with get_client(sync_client=True) as client:
        try:
            client.create_work_pool(WorkPoolCreate(name=name, type="process"))
            logger.info("Created work pool %r", name)
        except ObjectAlreadyExists:
            logger.info("Work pool %r already exists", name)


def deploy_orchestrator(pool: str) -> str:
    """Create or update the one deployment the backend starts playbook runs at."""
    deployment = run_playbook.to_deployment(
        name=PLAYBOOK_FLOW_NAME,
        work_pool_name=pool,
        # Record `manta_runtime.flows:run_playbook` rather than a file path: the
        # worker finds the flow by importing it from its own installed packages.
        entrypoint_type=EntrypointType.MODULE_PATH,
    )
    deployment.storage = LocalStorage(path=code_path())
    deployment_id = str(deployment.apply())
    logger.info("Deployed %s/%s onto pool %r", PLAYBOOK_FLOW_NAME, PLAYBOOK_FLOW_NAME, pool)
    return deployment_id


def main() -> None:
    pool = orchestrator_pool()
    ensure_process_pool(pool)
    deploy_orchestrator(pool)


if __name__ == "__main__":
    main()
