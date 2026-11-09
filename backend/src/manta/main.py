import logging

import uvicorn
from fastapi import FastAPI
from sqlalchemy.orm import Session

from manta.config.app_config import app_host, app_port
from manta.config.database_config import get_engine
from manta.config.example_data_config import example_data_seed_enabled, example_data_stores
from manta.config.keycloak_config import get_keycloak_openid, well_known
from manta.config.logging_config import configure_logging
from manta.config.s3_config import get_s3_client, s3_bucket_name
from manta.migrations.runner import run_migrations
from manta.routes.v1 import router as v1_router
from manta.services.example_data_service import ExampleDataService
from manta.services.run_service import ensure_prefect_ready
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
    if example_data_seed_enabled():
        logger.info("Seeding example data...")
        with Session(get_engine()) as db:
            example_data = ExampleDataService(db, get_s3_client(), s3_bucket_name())
            example_data.seed(example_data_stores())
            example_data.ensure_admin_project(
                idp_source=well_known(get_keycloak_openid())["issuer"]
            )
    logger.info("Ensuring Prefect is ready...")
    ensure_prefect_ready()

    app = FastAPI(title="Manta")
    app.include_router(v1_router)
    return app


app = create_app()


def main():
    uvicorn.run(app, host=app_host(), port=app_port())


if __name__ == "__main__":
    main()
