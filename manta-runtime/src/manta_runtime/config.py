"""How this runtime reaches the things it drives: the images blocks execute in,
the network their containers join, and the object store as they see it.

Values come from the environment (and the app's `.env`), never from code. Only
the provisioner reads most of this: once the work pool's job template carries it,
every block run inherits it without anything here being consulted again.
"""

import os

from dotenv import load_dotenv

RESULT_STORAGE_BLOCK_NAME = "manta-results"
"""The Prefect block naming where step results are stored, registered by deploy.py."""

RESULT_STORAGE_BLOCK = f"s3-bucket/{RESULT_STORAGE_BLOCK_NAME}"
"""What PREFECT_RESULTS_DEFAULT_STORAGE_BLOCK is set to, on both sides."""


class UnknownEnvironmentError(Exception):
    """Raised when a block needs an environment this installation has no image for."""


def exec_images() -> dict[str, str]:
    """Each block environment's execution image, from `MANTA_ENV_IMAGES`.

    Written as `pypsa=manta-exec:pypsa,other=manta-exec:other`. A block declares
    the environment it needs as a name; this is where a name becomes an image, so
    two frameworks that could never share a virtualenv can appear in one playbook.

    Deliberately not read from the catalogue, even though `EnvironmentSpec.image`
    exists there: the catalogue describes what a *block* needs and stays
    orchestration-agnostic, so any image it names is the bare environment image a
    block author publishes. A work pool needs the execution image derived from it,
    and that derivation is Manta's, not the block library's.
    """
    load_dotenv()
    raw = os.environ.get("MANTA_ENV_IMAGES", "")
    return dict(
        entry.split("=", 1) for entry in (part.strip() for part in raw.split(",")) if "=" in entry
    )


def exec_image(env: str) -> str:
    """The image a block declaring environment `env` executes in.

    A thin layer over that environment's bare blocks image: what a block author
    tests against, plus the Prefect the work pool needs in order to report the
    run's state (see docker/exec.Dockerfile). Block authors neither build nor
    name it.
    """
    images = exec_images()
    if env not in images:
        raise UnknownEnvironmentError(
            f"no execution image for environment {env!r}: add it to MANTA_ENV_IMAGES "
            f"(configured: {sorted(images) or 'none'})"
        )
    return images[env]


def blocks_pool() -> str:
    """The docker work pool block runs are dispatched to."""
    load_dotenv()
    return os.environ.get("MANTA_BLOCKS_POOL", "manta-blocks")


def orchestrator_pool() -> str:
    """The process work pool the playbook orchestrator runs on."""
    load_dotenv()
    return os.environ.get("MANTA_ORCHESTRATOR_POOL", "manta-orchestrator")


def docker_network() -> str:
    """The compose network block containers join, so they can reach object storage."""
    load_dotenv()
    return os.environ.get("MANTA_DOCKER_NETWORK", "manta_default")


def s3_endpoint() -> str:
    """The object store's address as seen from inside a container.

    Containers reach SeaweedFS by service name on the stack's network, unlike the
    backend, which talks to it through the published host port.
    """
    load_dotenv()
    return os.environ.get("MANTA_JOB_S3_ENDPOINT", "http://seaweedfs:8333")


def s3_credentials() -> tuple[str, str]:
    load_dotenv()
    return os.environ["S3_ACCESS_KEY"], os.environ["S3_SECRET_KEY"]


def s3_bucket() -> str:
    load_dotenv()
    return os.environ.get("S3_BUCKET", "manta")


def prefect_api_url() -> str:
    """The Prefect API as a block container reaches it, to report its own state."""
    load_dotenv()
    return os.environ.get("PREFECT_API_URL", "http://prefect-server:4200/api")


def block_loggers() -> str:
    """Which loggers inside a block container ship to the Prefect API.

    Prefect captures its own loggers and, with `log_prints`, anything printed;
    a modelling framework's own output is neither, so it must be named. Which
    names those are is a property of the installed block library, not of this
    runtime, so it is configuration rather than a constant here.
    """
    load_dotenv()
    return os.environ.get("MANTA_BLOCK_LOGGERS", "blocks")


def job_environment() -> dict[str, str]:
    """The environment every block container is started with.

    How to reach the Prefect API (the flow run reports its own state and ships
    its logs), how to reach the object store (blocks read and write records
    through the standard AWS_* variables), and where to persist the result record
    so the orchestrator can read it back. Nothing else: a container that runs
    modelling code — eventually third-party code — gets no route to the app
    database or the identity provider.
    """
    access_key, secret_key = s3_credentials()
    return {
        "PREFECT_API_URL": prefect_api_url(),
        "PREFECT_RESULTS_DEFAULT_STORAGE_BLOCK": RESULT_STORAGE_BLOCK,
        "PREFECT_LOGGING_EXTRA_LOGGERS": block_loggers(),
        "AWS_ACCESS_KEY_ID": access_key,
        "AWS_SECRET_ACCESS_KEY": secret_key,
        "AWS_ENDPOINT_URL": s3_endpoint(),
    }
