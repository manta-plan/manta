from collections.abc import Callable
from uuid import UUID

import httpx2
import psycopg
from keycloak.openid_connection import KeycloakOpenID

from manta.config.example_data_config import (
    ADMIN_EXAMPLE_PROJECT_UUID,
    ADMIN_IDP_SUBJECT,
    EXAMPLE_PROJECT_NAME,
)


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
    assert response.status_code == 201
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
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["uuid"] == second.json()["uuid"]


def test_register_with_missing_fields_is_rejected(app_server: str) -> None:
    # When
    response = httpx2.post(f"{app_server}/v1/auth/register", json={"username": "manta-admin"})

    # Then
    assert response.status_code == 422


def test_login_with_valid_credentials_returns_token(app_server: str) -> None:
    # When
    response = httpx2.post(
        f"{app_server}/v1/auth/login",
        json={"username": "manta-admin", "password": "manta-admin"},
    )

    # Then
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"  # noqa: S105 It's not a password
    assert body["refresh_token"]
    assert body["expires_in"] > 0
    assert body["refresh_expires_in"] > 0


def test_login_with_wrong_password_is_unauthorized(app_server: str) -> None:
    # When
    response = httpx2.post(
        f"{app_server}/v1/auth/login",
        json={"username": "manta-admin", "password": "wrong-password"},
    )

    # Then
    assert response.status_code == 401


def test_refresh_with_valid_refresh_token_returns_new_tokens(app_server: str) -> None:
    # Given
    login = httpx2.post(
        f"{app_server}/v1/auth/login",
        json={"username": "manta-admin", "password": "manta-admin"},
    ).json()

    # When
    response = httpx2.post(
        f"{app_server}/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )

    # Then
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"  # noqa: S105 It's not a password
    assert body["refresh_token"]
    assert body["refresh_token"] != login["refresh_token"]
    assert body["expires_in"] > 0
    assert body["refresh_expires_in"] > 0


def test_refresh_with_invalid_refresh_token_is_unauthorized(app_server: str) -> None:
    # When
    response = httpx2.post(
        f"{app_server}/v1/auth/refresh",
        json={"refresh_token": "not-a-refresh-token"},
    )

    # Then
    assert response.status_code == 401


def test_logout_ends_the_session(app_server: str) -> None:
    # Given
    login = httpx2.post(
        f"{app_server}/v1/auth/login",
        json={"username": "manta-admin", "password": "manta-admin"},
    ).json()

    # When
    response = httpx2.post(
        f"{app_server}/v1/auth/logout",
        json={"refresh_token": login["refresh_token"]},
    )

    # Then
    assert response.status_code == 204
    refresh = httpx2.post(
        f"{app_server}/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert refresh.status_code == 401


def test_logout_twice_is_not_an_error(app_server: str) -> None:
    # Given
    login = httpx2.post(
        f"{app_server}/v1/auth/login",
        json={"username": "manta-admin", "password": "manta-admin"},
    ).json()
    httpx2.post(f"{app_server}/v1/auth/logout", json={"refresh_token": login["refresh_token"]})

    # When
    response = httpx2.post(
        f"{app_server}/v1/auth/logout",
        json={"refresh_token": login["refresh_token"]},
    )

    # Then
    assert response.status_code == 204


def test_logout_with_invalid_refresh_token_is_unauthorized(app_server: str) -> None:
    # When
    response = httpx2.post(
        f"{app_server}/v1/auth/logout",
        json={"refresh_token": "not-a-refresh-token"},
    )

    # Then
    assert response.status_code == 401


def test_admin_owns_the_example_project_seeded_on_startup(
    app_server: str,
    db_connection: psycopg.Connection,
    kc_oidc_client: KeycloakOpenID,
    example_store_exists: Callable[[str], bool],
) -> None:
    # Given
    idp_subject, idp_source = _idp_claims(kc_oidc_client)

    # When
    response = httpx2.post(
        f"{app_server}/v1/auth/register",
        json={"username": "manta-admin", "idp_subject": idp_subject, "idp_source": idp_source},
    )

    # Then
    assert idp_subject == ADMIN_IDP_SUBJECT
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT u.uuid FROM projects p JOIN users u ON u.id = p.owner_id WHERE p.uuid = %s",
            (ADMIN_EXAMPLE_PROJECT_UUID,),
        )
        row = cursor.fetchone()
    assert row == (UUID(response.json()["uuid"]),)
    assert example_store_exists(str(ADMIN_EXAMPLE_PROJECT_UUID))


def test_register_creates_an_example_project_for_a_new_user(
    second_user_headers: dict[str, str],
    db_connection: psycopg.Connection,
    kc_oidc_client: KeycloakOpenID,
    example_store_exists: Callable[[str], bool],
) -> None:
    # Given - second_user_headers registered a brand-new user
    token = second_user_headers["Authorization"].removeprefix("Bearer ")
    idp_subject = kc_oidc_client.decode_token(token, validate=False)["sub"]

    # When
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.uuid FROM projects p JOIN users u ON u.id = p.owner_id
            WHERE u.idp_subject = %s AND p.name = %s
            """,
            (idp_subject, EXAMPLE_PROJECT_NAME),
        )
        rows = cursor.fetchall()

    # Then
    assert len(rows) == 1
    assert example_store_exists(str(rows[0][0]))
