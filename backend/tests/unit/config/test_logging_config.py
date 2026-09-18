import logging

from manta.config.logging_config import configure_logging


def test_configure_logging_takes_the_root_logger_back_from_import_side_effects() -> None:
    # Given a third-party import (prefect does this) has already claimed the root
    # logger with its own handler at WARNING
    root = logging.getLogger()
    previous_handlers, previous_level = root.handlers[:], root.level
    try:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        hijacker = logging.StreamHandler()
        root.addHandler(hijacker)
        root.setLevel(logging.WARNING)

        # When
        configure_logging()

        # Then Manta's configuration wins: INFO level, and the stray handler is gone
        assert root.level == logging.INFO
        assert hijacker not in root.handlers
        assert len(root.handlers) == 1
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in previous_handlers:
            root.addHandler(handler)
        root.setLevel(previous_level)
