import logging

import uvicorn
from fastapi import FastAPI

from manta.config.logging_config import configure_logging
from manta.routes.health_route import router as health_router

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
    app = FastAPI(title="Manta")
    app.include_router(health_router)
    print(BANNER, flush=True)
    logger.info("Manta starting app...")
    return app


app = create_app()


def main():
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
