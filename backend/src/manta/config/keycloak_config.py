import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from keycloak import KeycloakOpenID

from manta.config.keycloak_signing_keys import SigningKeyCache


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


def keycloak_jwks_ttl_seconds() -> float:
    load_dotenv()
    return float(os.environ.get("KEYCLOAK_JWKS_TTL_SECONDS", "600"))


@lru_cache
def get_keycloak_openid() -> KeycloakOpenID:
    # Cached so repeated calls reuse the same client (avoids rebuilding config/
    # connection state each time). The client doesn't cache Keycloak's signing
    # keys: decode_token(validate=True) fetches them from Keycloak on every call
    # unless it's given a key, so pass it one from get_signing_keys().
    # See https://github.com/marcospereirampj/python-keycloak/blob/v7.1.1/src/keycloak/keycloak_openid.py#L791
    return KeycloakOpenID(
        server_url=keycloak_server_url(),
        realm_name=keycloak_realm(),
        client_id=keycloak_client_id(),
        client_secret_key=keycloak_client_secret(),
    )


@lru_cache
def well_known(kc_client: KeycloakOpenID) -> dict[str, Any]:
    # Cache keycloak's openid configuration data
    return kc_client.well_known()


@lru_cache
def get_signing_keys() -> SigningKeyCache:
    # One cache per process, shared by every request.
    return SigningKeyCache(
        fetch_jwks=get_keycloak_openid().certs,
        ttl_seconds=keycloak_jwks_ttl_seconds(),
    )
