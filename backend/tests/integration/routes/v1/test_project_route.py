from datetime import datetime, timedelta
from uuid import UUID, uuid4

import httpx2
import psycopg
import pytest
from keycloak.openid_connection import KeycloakOpenID


def _auth_headers(app_server: str, kc_oidc_client: KeycloakOpenID) -> dict[str, str]:
    token = kc_oidc_client.token("manta-admin", "manta-admin")
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    claims = kc_oidc_client.decode_token(token["access_token"], validate=False)
    # authenticate() requires an already-registered user; register is idempotent,
    # so it's safe to call on every request rather than tracking first-use.
    response = httpx2.post(
        f"{app_server}/v1/auth/register",
        json={
            "username": "manta-admin",
            "idp_subject": claims["sub"],
            "idp_source": claims["iss"],
        },
    )
    assert response.status_code == 201
    return headers


def _unique_prefix() -> str:
    # The DB is shared by the whole test session, so each test tags its projects
    # with its own prefix and filters on it to ignore everyone else's.
    return uuid4().hex[:8]


def _create_project(
    app_server: str,
    headers: dict[str, str],
    name: str,
    description: str | None = None,
) -> dict:
    response = httpx2.post(
        f"{app_server}/v1/projects",
        json={"name": name, "description": description},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def _list_projects(app_server: str, headers: dict[str, str], **params) -> httpx2.Response:
    return httpx2.get(f"{app_server}/v1/projects", params=params, headers=headers)


def _as_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


# --- create -------------------------------------------------------------


def test_create_project(
    app_server: str, db_connection: psycopg.Connection, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    request_payload = {"name": "North Sea Wind", "description": "Offshore wind buildout scenario"}

    # When
    response = httpx2.post(
        f"{app_server}/v1/projects",
        json=request_payload,
        headers=_auth_headers(app_server, kc_oidc_client),
    )

    # Then
    assert response.status_code == 201
    body = response.json()
    assert UUID(body["uuid"])
    assert body["name"] == request_payload["name"]
    assert body["description"] == request_payload["description"]
    assert body["created_at"]
    assert body["updated_at"]

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


@pytest.mark.parametrize(
    "payload",
    [{}, {"name": "ab"}, {"name": "a" * 129}],
    ids=["missing_name", "name_too_short", "name_too_long"],
)
def test_create_project_with_an_invalid_body_is_rejected(
    payload: dict, app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # When
    response = httpx2.post(
        f"{app_server}/v1/projects",
        json=payload,
        headers=_auth_headers(app_server, kc_oidc_client),
    )

    # Then
    assert response.status_code == 422


# --- list ---------------------------------------------------------------


def test_list_projects_returns_the_users_projects(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    created = _create_project(app_server, headers, f"{prefix}-one", "first")

    # When
    response = _list_projects(app_server, headers, name=prefix)

    # Then
    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["limit"], body["offset"]) == (1, 10, 0)
    assert body["items"] == [
        {
            "uuid": created["uuid"],
            "name": f"{prefix}-one",
            "description": "first",
            "created_at": created["created_at"],
            "updated_at": created["updated_at"],
        }
    ]


def test_list_projects_paginates_with_limit_and_offset(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    for suffix in ("a", "b", "c"):
        _create_project(app_server, headers, f"{prefix}-{suffix}")

    # When
    first_page = _list_projects(
        app_server, headers, name=prefix, order_by="name", order="asc", limit=2, offset=0
    ).json()
    second_page = _list_projects(
        app_server, headers, name=prefix, order_by="name", order="asc", limit=2, offset=2
    ).json()

    # Then
    assert first_page["total"] == second_page["total"] == 3
    assert [item["name"] for item in first_page["items"]] == [f"{prefix}-a", f"{prefix}-b"]
    assert [item["name"] for item in second_page["items"]] == [f"{prefix}-c"]
    assert (second_page["limit"], second_page["offset"]) == (2, 2)


def test_list_projects_beyond_the_last_page_is_empty(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    _create_project(app_server, headers, f"{prefix}-a")

    # When
    body = _list_projects(app_server, headers, name=prefix, offset=50).json()

    # Then
    assert body["items"] == []
    assert body["total"] == 1


def test_list_projects_filters_by_name_ignoring_case(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    _create_project(app_server, headers, f"{prefix}-North Sea Wind")
    _create_project(app_server, headers, f"{prefix}-Baltic Solar")

    # When
    body = _list_projects(app_server, headers, name=f"{prefix}-north SEA").json()

    # Then
    assert [item["name"] for item in body["items"]] == [f"{prefix}-North Sea Wind"]


def test_list_projects_filters_by_description(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    _create_project(app_server, headers, f"{prefix}-a", f"{prefix} offshore wind")
    _create_project(app_server, headers, f"{prefix}-b", f"{prefix} rooftop solar")
    _create_project(app_server, headers, f"{prefix}-c", None)

    # When
    body = _list_projects(app_server, headers, description=f"{prefix} OFFSHORE").json()

    # Then
    assert [item["name"] for item in body["items"]] == [f"{prefix}-a"]


def test_list_projects_treats_like_wildcards_in_a_filter_literally(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    _create_project(app_server, headers, f"{prefix}-100%")
    _create_project(app_server, headers, f"{prefix}-1000")

    # When
    body = _list_projects(app_server, headers, name=f"{prefix}-100%").json()

    # Then
    assert [item["name"] for item in body["items"]] == [f"{prefix}-100%"]


def test_list_projects_filters_by_name_and_description_together(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    _create_project(app_server, headers, f"{prefix}-wind", "offshore")
    _create_project(app_server, headers, f"{prefix}-wind-2", "onshore")

    # When
    body = _list_projects(app_server, headers, name=f"{prefix}-wind", description="offshore").json()

    # Then
    assert [item["name"] for item in body["items"]] == [f"{prefix}-wind"]


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_list_projects_orders_by_name(
    order: str, app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    for suffix in ("b", "c", "a"):
        _create_project(app_server, headers, f"{prefix}-{suffix}")

    # When
    body = _list_projects(app_server, headers, name=prefix, order_by="name", order=order).json()

    # Then
    names = [item["name"] for item in body["items"]]
    expected = [f"{prefix}-{suffix}" for suffix in ("a", "b", "c")]
    assert names == (expected if order == "asc" else expected[::-1])


def test_list_projects_orders_newest_first_by_default(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    for suffix in ("first", "second", "third"):
        _create_project(app_server, headers, f"{prefix}-{suffix}")

    # When
    body = _list_projects(app_server, headers, name=prefix).json()

    # Then
    assert [item["name"] for item in body["items"]] == [
        f"{prefix}-third",
        f"{prefix}-second",
        f"{prefix}-first",
    ]


def test_list_projects_orders_by_created_at_ascending(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    for suffix in ("first", "second", "third"):
        _create_project(app_server, headers, f"{prefix}-{suffix}")

    # When
    body = _list_projects(
        app_server, headers, name=prefix, order_by="created_at", order="asc"
    ).json()

    # Then
    assert [item["name"] for item in body["items"]] == [
        f"{prefix}-first",
        f"{prefix}-second",
        f"{prefix}-third",
    ]


def test_list_projects_orders_by_updated_at(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    older = _create_project(app_server, headers, f"{prefix}-older")
    _create_project(app_server, headers, f"{prefix}-newer")
    httpx2.patch(
        f"{app_server}/v1/projects/{older['uuid']}",
        json={"description": "touched"},
        headers=headers,
    )

    # When
    body = _list_projects(
        app_server, headers, name=prefix, order_by="updated_at", order="desc"
    ).json()

    # Then
    assert [item["name"] for item in body["items"]] == [f"{prefix}-older", f"{prefix}-newer"]


def test_list_projects_filters_by_created_range(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    created = _create_project(app_server, headers, f"{prefix}-a")
    created_at = _as_datetime(created["created_at"])
    day = timedelta(days=1)

    # When
    inside = _list_projects(
        app_server,
        headers,
        name=prefix,
        created_from=(created_at - day).isoformat(),
        created_to=(created_at + day).isoformat(),
    ).json()
    before = _list_projects(
        app_server, headers, name=prefix, created_to=(created_at - day).isoformat()
    ).json()
    after = _list_projects(
        app_server, headers, name=prefix, created_from=(created_at + day).isoformat()
    ).json()

    # Then
    assert inside["total"] == 1
    assert before["total"] == 0
    assert after["total"] == 0


def test_list_projects_range_bounds_are_inclusive(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    created = _create_project(app_server, headers, f"{prefix}-a")

    # When
    body = _list_projects(
        app_server,
        headers,
        name=prefix,
        created_from=created["created_at"],
        created_to=created["created_at"],
        updated_from=created["updated_at"],
        updated_to=created["updated_at"],
    ).json()

    # Then
    assert body["total"] == 1


def test_list_projects_filters_by_updated_range(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    _create_project(app_server, headers, f"{prefix}-untouched")
    touched = _create_project(app_server, headers, f"{prefix}-touched")
    updated = httpx2.patch(
        f"{app_server}/v1/projects/{touched['uuid']}",
        json={"description": "touched"},
        headers=headers,
    ).json()

    # When: only the project updated at or after the patch is returned
    body = _list_projects(
        app_server, headers, name=prefix, updated_from=updated["updated_at"]
    ).json()

    # Then
    assert [item["name"] for item in body["items"]] == [f"{prefix}-touched"]


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"order_by": "uuid"},
        {"order": "sideways"},
        {"name": ""},
        {"created_from": "not-a-date"},
        {"created_from": "2026-11-06T00:00:00Z", "created_to": "2026-11-05T00:00:00Z"},
        {"updated_from": "2026-11-06T00:00:00Z", "updated_to": "2026-11-05T00:00:00Z"},
    ],
    ids=[
        "limit_below_min",
        "limit_above_max",
        "negative_offset",
        "unknown_order_by",
        "unknown_order",
        "empty_name",
        "bad_date",
        "created_range_reversed",
        "updated_range_reversed",
    ],
)
def test_list_projects_with_invalid_params_is_rejected(
    params: dict, app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # When
    response = _list_projects(app_server, _auth_headers(app_server, kc_oidc_client), **params)

    # Then
    assert response.status_code == 422


def test_list_projects_without_token_is_rejected(app_server: str) -> None:
    # When
    response = httpx2.get(f"{app_server}/v1/projects")

    # Then
    assert response.status_code == 401


# --- get by id ----------------------------------------------------------


def test_get_project(app_server: str, kc_oidc_client: KeycloakOpenID) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    created = _create_project(app_server, headers, "North Sea Wind", "Offshore wind")

    # When
    response = httpx2.get(f"{app_server}/v1/projects/{created['uuid']}", headers=headers)

    # Then
    assert response.status_code == 200
    assert response.json() == {
        "uuid": created["uuid"],
        "name": "North Sea Wind",
        "description": "Offshore wind",
        "created_at": created["created_at"],
        "updated_at": created["updated_at"],
    }


def test_get_project_that_does_not_exist_is_a_404(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # When
    response = httpx2.get(
        f"{app_server}/v1/projects/{uuid4()}", headers=_auth_headers(app_server, kc_oidc_client)
    )

    # Then
    assert response.status_code == 404


def test_get_project_with_a_malformed_uuid_is_a_422(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # When
    response = httpx2.get(
        f"{app_server}/v1/projects/not-a-uuid", headers=_auth_headers(app_server, kc_oidc_client)
    )

    # Then
    assert response.status_code == 422


def test_get_project_without_token_is_rejected(app_server: str) -> None:
    # When
    response = httpx2.get(f"{app_server}/v1/projects/{uuid4()}")

    # Then
    assert response.status_code == 401


# --- update -------------------------------------------------------------


def test_update_project_changes_only_the_fields_sent(
    app_server: str, db_connection: psycopg.Connection, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    created = _create_project(app_server, headers, "North Sea Wind", "Old description")

    # When
    response = httpx2.patch(
        f"{app_server}/v1/projects/{created['uuid']}",
        json={"name": "Baltic Wind"},
        headers=headers,
    )

    # Then
    assert response.status_code == 200
    body = response.json()
    assert body["uuid"] == created["uuid"]
    assert body["name"] == "Baltic Wind"
    assert body["description"] == "Old description"
    assert body["created_at"] == created["created_at"]

    with db_connection.cursor() as cursor:
        cursor.execute("SELECT name, description FROM projects WHERE uuid = %s", (created["uuid"],))
        assert cursor.fetchone() == ("Baltic Wind", "Old description")


def test_update_project_can_clear_the_description(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    created = _create_project(app_server, headers, "North Sea Wind", "Old description")

    # When
    response = httpx2.patch(
        f"{app_server}/v1/projects/{created['uuid']}",
        json={"description": None},
        headers=headers,
    )

    # Then
    assert response.status_code == 200
    assert response.json()["description"] is None
    assert response.json()["name"] == "North Sea Wind"


def test_update_project_refreshes_updated_at_but_not_created_at(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    created = _create_project(app_server, headers, "North Sea Wind")

    # When
    updated = httpx2.patch(
        f"{app_server}/v1/projects/{created['uuid']}",
        json={"name": "Baltic Wind"},
        headers=headers,
    ).json()
    fetched = httpx2.get(f"{app_server}/v1/projects/{created['uuid']}", headers=headers).json()

    # Then
    assert updated["created_at"] == created["created_at"]
    assert _as_datetime(updated["updated_at"]) > _as_datetime(created["updated_at"])
    assert fetched["updated_at"] == updated["updated_at"]


@pytest.mark.parametrize(
    "payload",
    [{}, {"name": None}, {"name": "ab"}, {"name": "a" * 129}],
    ids=["empty_body", "null_name", "name_too_short", "name_too_long"],
)
def test_update_project_with_an_invalid_body_is_rejected(
    payload: dict, app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    created = _create_project(app_server, headers, "North Sea Wind")

    # When
    response = httpx2.patch(
        f"{app_server}/v1/projects/{created['uuid']}", json=payload, headers=headers
    )

    # Then
    assert response.status_code == 422
    unchanged = httpx2.get(f"{app_server}/v1/projects/{created['uuid']}", headers=headers).json()
    assert unchanged["name"] == "North Sea Wind"


def test_update_project_that_does_not_exist_is_a_404(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # When
    response = httpx2.patch(
        f"{app_server}/v1/projects/{uuid4()}",
        json={"name": "Baltic Wind"},
        headers=_auth_headers(app_server, kc_oidc_client),
    )

    # Then
    assert response.status_code == 404


def test_update_project_without_token_is_rejected(app_server: str) -> None:
    # When
    response = httpx2.patch(f"{app_server}/v1/projects/{uuid4()}", json={"name": "Baltic Wind"})

    # Then
    assert response.status_code == 401


# --- delete -------------------------------------------------------------


def test_delete_project(
    app_server: str, db_connection: psycopg.Connection, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    created = _create_project(app_server, headers, "North Sea Wind")

    # When
    response = httpx2.delete(f"{app_server}/v1/projects/{created['uuid']}", headers=headers)

    # Then
    assert response.status_code == 204
    assert response.content == b""
    after = httpx2.get(f"{app_server}/v1/projects/{created['uuid']}", headers=headers)
    assert after.status_code == 404
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM projects WHERE uuid = %s", (created["uuid"],))
        assert cursor.fetchone() == (0,)


def test_delete_project_that_does_not_exist_is_a_404(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # When
    response = httpx2.delete(
        f"{app_server}/v1/projects/{uuid4()}", headers=_auth_headers(app_server, kc_oidc_client)
    )

    # Then
    assert response.status_code == 404


def test_delete_project_twice_is_a_404_the_second_time(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    created = _create_project(app_server, headers, "North Sea Wind")
    httpx2.delete(f"{app_server}/v1/projects/{created['uuid']}", headers=headers)

    # When
    response = httpx2.delete(f"{app_server}/v1/projects/{created['uuid']}", headers=headers)

    # Then
    assert response.status_code == 404


def test_deleted_project_is_gone_from_the_list(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)
    prefix = _unique_prefix()
    keep = _create_project(app_server, headers, f"{prefix}-keep")
    drop = _create_project(app_server, headers, f"{prefix}-drop")

    # When
    httpx2.delete(f"{app_server}/v1/projects/{drop['uuid']}", headers=headers)
    body = _list_projects(app_server, headers, name=prefix).json()

    # Then
    assert [item["uuid"] for item in body["items"]] == [keep["uuid"]]
    assert body["total"] == 1


def test_delete_project_without_token_is_rejected(app_server: str) -> None:
    # When
    response = httpx2.delete(f"{app_server}/v1/projects/{uuid4()}")

    # Then
    assert response.status_code == 401
