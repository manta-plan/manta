from uuid import UUID

import httpx2
import psycopg
from keycloak.openid_connection import KeycloakOpenID


def _auth_headers(kc_oidc_client: KeycloakOpenID) -> dict[str, str]:
    token = kc_oidc_client.token("manta-admin", "manta-admin")
    return {"Authorization": f"Bearer {token['access_token']}"}


def test_create_project(
    app_server: str, db_connection: psycopg.Connection, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    request_payload = {"name": "North Sea Wind", "description": "Offshore wind buildout scenario"}

    # When
    response = httpx2.post(
        f"{app_server}/v1/projects", json=request_payload, headers=_auth_headers(kc_oidc_client)
    )

    # Then
    assert response.status_code == 201
    body = response.json()
    assert UUID(body["uuid"])
    assert body["name"] == request_payload["name"]
    assert body["description"] == request_payload["description"]
    assert body["created_at"]

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.name, p.description, u.username
            FROM projects p JOIN users u ON u.id = p.owner_id
            WHERE p.uuid = %s
            """,
            (body["uuid"],),
        )
        row = cursor.fetchone()
    assert row == (request_payload["name"], request_payload["description"], "manta-admin")


def test_create_project_without_token_is_rejected(app_server: str) -> None:
    # Given
    request_payload = {"name": "North Sea Wind", "description": None}

    # When
    response = httpx2.post(f"{app_server}/v1/projects", json=request_payload)

    # Then
    assert response.status_code == 401


def test_create_project_with_invalid_token_is_rejected(app_server: str) -> None:
    # Given
    request_payload = {"name": "North Sea Wind", "description": None}

    # When
    response = httpx2.post(
        f"{app_server}/v1/projects",
        json=request_payload,
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    # Then
    assert response.status_code == 401
