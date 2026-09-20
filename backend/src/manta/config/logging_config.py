import logging
import os


def configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    # force=True: basicConfig silently no-ops if the root logger already has
    # handlers, and importing prefect (pulled in via the run routes) installs its
    # own root console handler at WARNING as an import side effect — which would
    # swallow all of Manta's INFO logging. Manta owns its process's root logger.
    logging.basicConfig(
        level=level, format="%(levelname)s: %(asctime)s %(name)s - %(message)s", force=True
    )
