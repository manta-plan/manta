from uuid import UUID

import httpx2
import psycopg


def test_create_project(app_server: str, db_connection: psycopg.Connection) -> None:
    # Given
    payload = {"name": "North Sea Wind", "description": "Offshore wind buildout scenario"}

    # When
    response = httpx2.post(f"{app_server}/v1/projects", json=payload)

    # Then
    assert response.status_code == 201
    body = response.json()
    assert UUID(body["uuid"])
    assert body["name"] == payload["name"]
    assert body["description"] == payload["description"]
    assert body["created_at"]

    with db_connection.cursor() as cursor:
        cursor.execute("SELECT name, description FROM projects WHERE uuid = %s", (body["uuid"],))
        row = cursor.fetchone()
    assert row == (payload["name"], payload["description"])
