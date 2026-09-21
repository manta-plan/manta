import logging
import os
import subprocess
import sys

import uvicorn
from fastapi import FastAPI

from manta.config.logging_config import configure_logging
from manta.config.s3_config import get_s3_client, s3_bucket_name
from manta.migrations.runner import run_migrations
from manta.routes.v1 import router as v1_router
from manta.services.s3_file_storage_service import S3FileStorageService

logger = logging.getLogger(__name__)

BANNER = r"""
 __  __     _    _   _  _____  _
|  \/  |   / \  | \ | ||_   _|/ \
| |\/| |  / _ \ |  \| |  | | / _ \
| |  | | / ___ \| |\  |  | |/ ___ \
|_|  |_|/_/   \_\_| \_|  |_/_/   \_\
"""


def create_app() -> FastAPI:
    configure_logging()
    print(BANNER, flush=True)
    logger.info("Manta starting up...")
    logger.info("Running database migrations...")
    run_migrations()
    logger.info("Ensuring S3 bucket exists...")
    S3FileStorageService(client=get_s3_client(), bucket=s3_bucket_name()).ensure_bucket_exists()

    logger.info("Starting the Prefect flow-serving process...")
    # manta-runtime registers the run-playbook deployment with the Prefect server
    # and executes its runs. Its console output goes to /dev/null on purpose: the
    # app's stdout stays Manta's own, and everything it logs ships to the Prefect
    # API anyway (UI, and /v1/runs/{uuid}/logs). Never swap this for
    # subprocess.PIPE — an unread pipe fills up (Prefect echoes every flow/task
    # log line, block-container output included) and a full pipe blocks the next
    # write, freezing runs mid-step. TODO(post-MVP): run this as its own
    # long-lived service so in-flight runs survive app restarts.
    try:
        subprocess.Popen(  # noqa: S603 — fixed args, no untrusted input
            [sys.executable, "-m", "manta_runtime.serve"],
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Prefect flow-serving process started")
    except Exception as e:
        logger.error(f"Failed to start the Prefect flow-serving process: {e}")
        # Non-fatal: app continues, runs just won't execute

    app = FastAPI(title="Manta")
    app.frontend("/", directory="../frontend/dist")
    app.include_router(v1_router)
    # Mounting the frontend needs to be sequenced after all other routes so as
    # to not accidentally shadow any api endpoints.
    return app


app = create_app()


def main():
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
