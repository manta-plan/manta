import os
from functools import lru_cache
from typing import Any

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
    # Cached so repeated calls reuse the same client (avoids rebuilding config/
    # connection state each time). This does NOT cache JWKS: python-keycloak's
    # decode_token(validate=True) calls certs() on every invocation, which does
    # a synchronous HTTP GET to Keycloak's /certs endpoint with no caching of
    # its own. authenticate()/authenticated_user() are sync defs, so FastAPI
    # runs this in a threadpool worker per request — every authenticated
    # request ties up a worker thread for a live network round trip to
    # Keycloak just to re-fetch the same signing keys, before the token
    # signature is even checked.
    # See https://github.com/marcospereirampj/python-keycloak/blob/v7.1.1/src/keycloak/keycloak_openid.py#L587
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
