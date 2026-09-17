import httpx2
import psycopg
from keycloak.openid_connection import KeycloakOpenID


def _idp_claims(kc_oidc_client: KeycloakOpenID) -> tuple[str, str]:
    token = kc_oidc_client.token("manta-admin", "manta-admin")
    claims = kc_oidc_client.decode_token(token["access_token"], validate=False)
    return claims["sub"], claims["iss"]


def test_register_creates_new_user(
    app_server: str, db_connection: psycopg.Connection, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    idp_subject, idp_source = _idp_claims(kc_oidc_client)

    # When
    response = httpx2.post(
        f"{app_server}/v1/auth/register",
        json={"username": "manta-admin", "idp_subject": idp_subject, "idp_source": idp_source},
    )

    # Then
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "manta-admin"
    assert body["idp_subject"] == idp_subject
    assert body["idp_source"] == idp_source
    assert body["created_at"]

    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT username, idp_subject, idp_source FROM users WHERE uuid = %s", (body["uuid"],)
        )
        row = cursor.fetchone()
    assert row == (body["username"], body["idp_subject"], body["idp_source"])


def test_register_is_idempotent(app_server: str, kc_oidc_client: KeycloakOpenID) -> None:
    # Given
    idp_subject, idp_source = _idp_claims(kc_oidc_client)
    payload = {"username": "manta-admin", "idp_subject": idp_subject, "idp_source": idp_source}

    # When
    first = httpx2.post(f"{app_server}/v1/auth/register", json=payload)
    second = httpx2.post(f"{app_server}/v1/auth/register", json=payload)

    # Then
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["uuid"] == second.json()["uuid"]


def test_register_with_missing_fields_is_rejected(app_server: str) -> None:
    # When
    response = httpx2.post(f"{app_server}/v1/auth/register", json={"username": "manta-admin"})

    # Then
    assert response.status_code == 422
