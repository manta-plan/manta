import logging
import os


def configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level, format="%(levelname)s: %(asctime)s %(name)s - %(message)s")
