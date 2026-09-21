"""How this runtime reaches the things it drives: the block image, the network
its containers join, and the object store as they see it from inside.

Values come from the environment (and the app's `.env`), never from code.
"""

import os

from dotenv import load_dotenv


def blocks_image() -> str:
    """The one image every block runs in (built by docker/blocks-runner.Dockerfile)."""
    load_dotenv()
    return os.environ.get("MANTA_BLOCKS_IMAGE", "manta-blocks-runner:latest")


def docker_network() -> str:
    """The compose network block containers join, so they can reach object storage."""
    load_dotenv()
    return os.environ.get("MANTA_DOCKER_NETWORK", "manta_default")


def job_environment() -> dict[str, str]:
    """The environment a block container is started with.

    Blocks read records via the standard AWS_* variables (see manta-blocks'
    storage module). The endpoint is the compose-internal one — job containers
    reach SeaweedFS by service name on the stack's network, unlike the backend,
    which talks to it through the published host port.
    """
    load_dotenv()
    return {
        "AWS_ACCESS_KEY_ID": os.environ["S3_ACCESS_KEY"],
        "AWS_SECRET_ACCESS_KEY": os.environ["S3_SECRET_KEY"],
        "AWS_ENDPOINT_URL": os.environ.get("MANTA_JOB_S3_ENDPOINT", "http://seaweedfs:8333"),
    }
