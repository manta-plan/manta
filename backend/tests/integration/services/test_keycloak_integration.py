"""Covers the Keycloak dev/test stack itself — realm import, client
configuration, and token contents. There's no app-side auth code yet; these
pin down the identity provider's configuration so the middleware that comes
next has something trustworthy to build on."""

import psycopg
import pytest
from keycloak import KeycloakAdmin, KeycloakOpenID, KeycloakOpenIDConnection
from keycloak.exceptions import KeycloakPostError

# Test-only client: it's the one place direct access grants (ROPC) are enabled,
# so the suite can mint a token without driving a browser through the code flow.
TEST_CLIENT_ID = "manta-test"
DEV_USERNAME = "alice"
DEV_PASSWORD = "alice"  # noqa: S105 — committed dev credential, see docker/keycloak/manta-realm.json


@pytest.fixture(scope="session")
def kc_url(keycloak_service: dict[str, str]) -> str:
    return f"http://{keycloak_service['host']}:{keycloak_service['port']}"


@pytest.fixture(scope="session")
def kc_admin(kc_url: str, backend_env: dict[str, str]) -> KeycloakAdmin:
    """Admin client scoped to the manta realm, authenticating as the bootstrap
    admin (which lives in master)."""
    connection = KeycloakOpenIDConnection(
        server_url=kc_url,
        realm_name=backend_env["KEYCLOAK_REALM"],
        user_realm_name="master",
        client_id="admin-cli",
        username=backend_env["KC_BOOTSTRAP_ADMIN_USERNAME"],
        password=backend_env["KC_BOOTSTRAP_ADMIN_PASSWORD"],
    )
    return KeycloakAdmin(connection=connection)


@pytest.fixture(scope="session")
def test_client(kc_url: str, backend_env: dict[str, str]) -> KeycloakOpenID:
    return KeycloakOpenID(
        server_url=kc_url,
        realm_name=backend_env["KEYCLOAK_REALM"],
        client_id=TEST_CLIENT_ID,
    )


def test_realm_discovery_is_available(kc_url: str, backend_env: dict[str, str]) -> None:
    # Given
    realm = backend_env["KEYCLOAK_REALM"]
    kc = KeycloakOpenID(
        server_url=kc_url,
        realm_name=realm,
        client_id=backend_env["KEYCLOAK_FRONTEND_CLIENT_ID"],
    )

    # When
    well_known = kc.well_known()

    # Then
    assert well_known["issuer"].endswith(f"/realms/{realm}")
    assert "S256" in well_known["code_challenge_methods_supported"]


def test_frontend_client_is_configured_for_code_flow_with_pkce(
    kc_admin: KeycloakAdmin, backend_env: dict[str, str]
) -> None:
    """Every field here defaults to the wrong value for a browser client, and a
    wrong default fails silently rather than at import time."""
    # Given
    clients = kc_admin.get_clients()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    # When
    frontend = next(  # pyright: ignore[reportUnknownVariableType]
        c for c in clients if c["clientId"] == backend_env["KEYCLOAK_FRONTEND_CLIENT_ID"]
    )

    # Then
    assert frontend["publicClient"] is True
    assert frontend["standardFlowEnabled"] is True
    # ROPC belongs only on the test client — see RFC 9700.
    assert frontend["directAccessGrantsEnabled"] is False
    assert frontend["attributes"]["pkce.code.challenge.method"] == "S256"
    assert frontend["redirectUris"]


def test_access_token_carries_api_audience(
    test_client: KeycloakOpenID, backend_env: dict[str, str]
) -> None:
    """The backend's audience check is only meaningful if the audience mapper
    actually puts manta-api in `aud`."""
    # Given
    token = test_client.token(DEV_USERNAME, DEV_PASSWORD)

    # When
    claims = test_client.decode_token(token["access_token"])

    # Then
    audience = claims["aud"]
    assert backend_env["KEYCLOAK_API_AUDIENCE"] in (
        [audience] if isinstance(audience, str) else audience
    )
    assert claims["iss"].endswith(f"/realms/{backend_env['KEYCLOAK_REALM']}")


def test_dev_user_can_authenticate(test_client: KeycloakOpenID) -> None:
    # Given / When
    token = test_client.token(DEV_USERNAME, DEV_PASSWORD)

    # Then
    assert token["access_token"]

    # When / Then — a wrong password is rejected, not silently accepted.
    # Keycloak answers a bad password with 400 invalid_grant rather than 401,
    # so python-keycloak surfaces it as KeycloakPostError.
    with pytest.raises(KeycloakPostError, match="invalid_grant"):
        test_client.token(DEV_USERNAME, "wrong-password")


def test_keycloak_uses_postgres_not_h2(kc_db_connection: psycopg.Connection) -> None:
    """Keycloak ignores unrecognised KC_DB_* names and falls back to embedded
    H2 without complaining, so assert its schema really landed in Postgres."""
    # Given / When
    with kc_db_connection.cursor() as cursor:
        _ = cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {row[0].lower() for row in cursor.fetchall()}

    # Then
    assert {"realm", "client"} <= tables
