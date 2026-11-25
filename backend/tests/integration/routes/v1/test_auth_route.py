from collections.abc import Callable
from uuid import uuid4

import httpx2
import psycopg
from keycloak import KeycloakAdmin
from keycloak.openid_connection import KeycloakOpenID

from manta.config.example_data_config import (
    ADMIN_EXAMPLE_PROJECT_UUID,
    ADMIN_IDP_SUBJECT,
    EXAMPLE_PROJECT_NAME,
)


def test_register_is_not_available(app_server: str) -> None:
    # When
    response = httpx2.post(
        f"{app_server}/v1/auth/register",
        json={"username": "mallory", "idp_subject": "abc-123", "idp_source": "http://idp"},
    )

    # Then
    assert response.status_code == 404


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


def test_first_login_creates_the_user_with_an_example_project(
    app_server: str,
    db_connection: psycopg.Connection,
    kc_admin_client: KeycloakAdmin,
    example_store_exists: Callable[[str], bool],
) -> None:
    # Given - an account that exists in Keycloak only
    username = f"beta-{uuid4()}"
    password = "beta-password"  # noqa: S105 — test-only, ephemeral Keycloak instance
    idp_subject = kc_admin_client.create_user(
        {
            "username": username,
            "enabled": True,
            "emailVerified": True,
            "email": f"{username}@example.com",
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        }
    )

    # When
    first = httpx2.post(
        f"{app_server}/v1/auth/login", json={"username": username, "password": password}
    )
    second = httpx2.post(
        f"{app_server}/v1/auth/login", json={"username": username, "password": password}
    )

    # Then - the user and its example project are created once
    assert first.status_code == 200
    assert second.status_code == 200
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT username FROM users WHERE idp_subject = %s", (idp_subject,))
        users = cursor.fetchall()
        cursor.execute(
            """
            SELECT p.uuid FROM projects p JOIN users u ON u.id = p.owner_id
            WHERE u.idp_subject = %s AND p.name = %s
            """,
            (idp_subject, EXAMPLE_PROJECT_NAME),
        )
        projects = cursor.fetchall()
    assert users == [(username,)]
    assert len(projects) == 1
    assert example_store_exists(str(projects[0][0]))

    # ...and the token is accepted by authenticated routes
    response = httpx2.get(
        f"{app_server}/v1/projects",
        headers={"Authorization": f"Bearer {first.json()['access_token']}"},
    )
    assert response.status_code == 200


def test_login_updates_username_renamed_in_keycloak(
    app_server: str, db_connection: psycopg.Connection, kc_admin_client: KeycloakAdmin
) -> None:
    # Given - a user who logged in before being renamed in Keycloak
    username = f"beta-{uuid4()}"
    password = "beta-password"  # noqa: S105 — test-only, ephemeral Keycloak instance
    idp_subject = kc_admin_client.create_user(
        {
            "username": username,
            "enabled": True,
            "emailVerified": True,
            "email": f"{username}@example.com",
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        }
    )
    httpx2.post(f"{app_server}/v1/auth/login", json={"username": username, "password": password})
    renamed = f"renamed-{uuid4()}"
    kc_admin_client.update_user(idp_subject, {"username": renamed})

    # When
    response = httpx2.post(
        f"{app_server}/v1/auth/login", json={"username": renamed, "password": password}
    )

    # Then
    assert response.status_code == 200
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT username FROM users WHERE idp_subject = %s", (idp_subject,))
        rows = cursor.fetchall()
    assert rows == [(renamed,)]


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
    # When
    login = httpx2.post(
        f"{app_server}/v1/auth/login",
        json={"username": "manta-admin", "password": "manta-admin"},
    ).json()

    # Then
    claims = kc_oidc_client.decode_token(login["access_token"], validate=False)
    assert claims["sub"] == ADMIN_IDP_SUBJECT
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT u.idp_subject, u.idp_source FROM projects p
            JOIN users u ON u.id = p.owner_id WHERE p.uuid = %s
            """,
            (ADMIN_EXAMPLE_PROJECT_UUID,),
        )
        row = cursor.fetchone()
    assert row == (claims["sub"], claims["iss"])
    assert example_store_exists(str(ADMIN_EXAMPLE_PROJECT_UUID))


def test_guest_login_returns_working_tokens_for_a_new_user(
    app_server: str, db_connection: psycopg.Connection, kc_oidc_client: KeycloakOpenID
) -> None:
    # When
    response = httpx2.post(f"{app_server}/v1/auth/guest")

    # Then
    assert response.status_code == 201
    body = response.json()
    claims = kc_oidc_client.decode_token(body["access_token"], validate=True)
    assert claims["preferred_username"].startswith("guest-")

    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT username, idp_source FROM users WHERE idp_subject = %s", (claims["sub"],)
        )
        row = cursor.fetchone()
    assert row == (claims["preferred_username"], claims["iss"])

    # ...and the token is accepted by authenticated routes
    projects = httpx2.get(
        f"{app_server}/v1/projects", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert projects.status_code == 200

    # ...and can be refreshed like any other session
    refreshed = httpx2.post(
        f"{app_server}/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert refreshed.status_code == 200


def test_each_guest_login_creates_a_different_user(app_server: str) -> None:
    # When
    first = httpx2.post(f"{app_server}/v1/auth/guest").json()
    second = httpx2.post(f"{app_server}/v1/auth/guest").json()

    # Then
    assert first["access_token"] != second["access_token"]
