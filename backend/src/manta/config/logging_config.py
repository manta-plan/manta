import logging
import os


def configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    # force=True: importing prefect (pulled in by the services) has already
    # installed prefect's own console handler on the root logger and left it at
    # WARNING by the time this runs — and basicConfig() silently does nothing
    # once root has a handler, which would swallow every INFO log of ours.
    # Replacing root's handlers makes this configuration win regardless of what
    # imports did first; prefect's records simply propagate into our handler.
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(asctime)s %(name)s - %(message)s",
        force=True,
    )
