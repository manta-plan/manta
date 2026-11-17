import logging
import os


def configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    # force: importing Prefect already put its own WARNING-level handler on the root
    # logger, which would otherwise make this a no-op and hide the app's own logs.
    logging.basicConfig(
        level=level, format="%(levelname)s: %(asctime)s %(name)s - %(message)s", force=True
    )
    # Both log every HTTP request at INFO: Prefect's client (httpx) and the example data
    # download (httpx2) would drown out everything else.
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)
