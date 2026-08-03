from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = Path(__file__).resolve().parent


def run_migrations() -> None:
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    command.upgrade(config, "head")
