import os
from uuid import UUID

from dotenv import load_dotenv

EXAMPLE_DATA_PREFIX = "example-data"
"""Where the downloaded example datarecord stores are kept, each under
`<prefix>/<store name>`, and copied into projects from."""

EXAMPLE_PROJECT_NAME = "Example project"

ADMIN_EXAMPLE_PROJECT_UUID = UUID("33b9abe3-2f25-4824-89e2-5a3d93671b6c")

ADMIN_USERNAME = "manta-admin"
ADMIN_IDP_SUBJECT = "0b7b2a6e-4c55-4b1e-9d0e-6f3c2a8e5d41"
"""manta-admin's Keycloak id, pinned in docker/conf/manta-realm.json so the user can be
created, and own its example project, before it ever logs in."""


def example_data_seed_enabled() -> bool:
    load_dotenv()
    return os.environ.get("EXAMPLE_DATA_SEED", "false").lower() == "true"


def example_data_stores() -> list[str]:
    """The stores to download from the public bucket. Empty means all of them."""
    load_dotenv()
    return [s for s in os.environ.get("EXAMPLE_DATA_STORES", "").split(",") if s]


def example_project_for_new_users_enabled() -> bool:
    load_dotenv()
    return os.environ.get("EXAMPLE_PROJECT_FOR_NEW_USERS", "true").lower() == "true"
