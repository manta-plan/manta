import os
from functools import lru_cache

from dotenv import load_dotenv
from keycloak import KeycloakOpenID


def keycloak_server_url() -> str:
    load_dotenv()
    # KEYCLOAK_* configures how manta talks to Keycloak as a client; KC_* (see
    # backend/.env) configures the Keycloak server process itself — don't mix them up.
    host = os.environ.get("KEYCLOAK_HOST", "localhost")
    port = os.environ["KEYCLOAK_PORT"]
    return f"http://{host}:{port}"


def keycloak_realm() -> str:
    load_dotenv()
    return os.environ["KEYCLOAK_REALM"]


def keycloak_client_id() -> str:
    load_dotenv()
    return os.environ["IDP_CLIENT_ID"]


def keycloak_client_secret() -> str:
    load_dotenv()
    return os.environ["IDP_CLIENT_SECRET"]


@lru_cache
def get_keycloak_openid() -> KeycloakOpenID:
    # Cached so repeated calls reuse the same client, including its internal
    # JWKS cache — token validation would otherwise refetch signing keys every time.
    return KeycloakOpenID(
        server_url=keycloak_server_url(),
        realm_name=keycloak_realm(),
        client_id=keycloak_client_id(),
        client_secret_key=keycloak_client_secret(),
    )
