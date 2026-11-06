import os
from uuid import UUID

from dotenv import load_dotenv

EXAMPLE_PROJECT_UUID = UUID("33b9abe3-2f25-4824-89e2-5a3d93671b6c")
"""The project the example datarecord stores are copied under on startup."""


def example_data_seed_enabled() -> bool:
    load_dotenv()
    return os.environ.get("EXAMPLE_DATA_SEED", "false").lower() == "true"


def example_data_excluded_stores() -> set[str]:
    load_dotenv()
    return {s for s in os.environ.get("EXAMPLE_DATA_EXCLUDED_STORES", "").split(",") if s}
