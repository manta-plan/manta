from uuid import uuid4

import httpx2
import pytest
from datarecord_session_fake import FakeDatarecordSessionLauncher
from fastapi.testclient import TestClient

from manta.services import datarecord_session_service

STORE = "ac-dc-meshed"
REGISTRATION = {"kind": "view", "store": STORE, "revision": str(uuid4()), "packs": ["pypsa-eur"]}


@pytest.fixture
def session_url(app_server: str, admin_headers: dict[str, str]) -> str:
    response = httpx2.post(
        f"{app_server}/v1/projects", json={"name": "Sessions"}, headers=admin_headers
    )
    assert response.status_code == 201
    return f"/v1/projects/{response.json()['uuid']}/datarecord-session"


def test_open_starts_one_instance_and_returns_the_quack_connection(
    datarecord_session_api: TestClient,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    admin_headers: dict[str, str],
    session_url: str,
) -> None:
    # When the session is opened twice
    first = datarecord_session_api.post(session_url, headers=admin_headers)
    second = datarecord_session_api.post(session_url, headers=admin_headers)

    # Then one instance serves both, behind the app's own /quack route
    assert first.status_code == 200
    token = datarecord_session_launcher.started[0].quack_token
    assert first.json() == {
        "status": "active",
        "generation": 1,
        "quack": {"uri": "/quack", "token": token},
        "skipped_registrations": [],
    }
    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(datarecord_session_launcher.started) == 1


def test_registration_survives_a_suspend(
    datarecord_session_api: TestClient,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    admin_headers: dict[str, str],
    session_url: str,
) -> None:
    # Given a registration
    registration_url = f"{session_url}/registrations/base"
    put = datarecord_session_api.put(registration_url, json=REGISTRATION, headers=admin_headers)
    assert put.status_code == 200
    assert put.json() == {"name": "base", "prefix": 'manta."base"', **REGISTRATION}

    # When the session is suspended, and the registration read again
    suspended = datarecord_session_api.delete(session_url, headers=admin_headers)
    running_after_suspend = dict(datarecord_session_launcher.running)
    get = datarecord_session_api.get(registration_url, headers=admin_headers)
    reopened = datarecord_session_api.post(session_url, headers=admin_headers)

    # Then a new instance started with the registration replayed
    assert suspended.status_code == 204
    assert running_after_suspend == {}
    assert get.status_code == 200
    assert get.json() == put.json()
    assert reopened.status_code == 200
    assert reopened.json()["generation"] == 2
    assert reopened.json()["skipped_registrations"] == []
    [session] = datarecord_session_launcher.running.values()
    assert session.registrations == {"base": REGISTRATION}


def test_deleted_registration_is_gone(
    datarecord_session_api: TestClient,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    admin_headers: dict[str, str],
    session_url: str,
) -> None:
    # Given a registration
    registration_url = f"{session_url}/registrations/base"
    datarecord_session_api.put(registration_url, json=REGISTRATION, headers=admin_headers)

    # When it is deleted
    deleted = datarecord_session_api.delete(registration_url, headers=admin_headers)

    # Then neither the backend nor the session knows it
    assert deleted.status_code == 204
    assert datarecord_session_api.get(registration_url, headers=admin_headers).status_code == 404
    [session] = datarecord_session_launcher.running.values()
    assert session.registrations == {}


def test_registration_the_session_refuses_is_not_kept(
    datarecord_session_api: TestClient,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    admin_headers: dict[str, str],
    session_url: str,
) -> None:
    # Given a registration of a store the session does not find
    registration_url = f"{session_url}/registrations/base"
    body = {**REGISTRATION, "store": "missing"}

    # When it is put
    put = datarecord_session_api.put(registration_url, json=body, headers=admin_headers)

    # Then the session's answer is passed on, no row is left behind, and the instance
    # started for the request serves the next one
    assert put.status_code == 404
    assert put.json() == {"detail": "Store missing not found"}
    assert datarecord_session_api.get(registration_url, headers=admin_headers).status_code == 404
    assert datarecord_session_api.post(session_url, headers=admin_headers).json()["generation"] == 1
    assert len(datarecord_session_launcher.started) == 1


def test_put_of_an_existing_name_replaces_the_registration(
    datarecord_session_api: TestClient,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    admin_headers: dict[str, str],
    session_url: str,
) -> None:
    # Given a registration
    registration_url = f"{session_url}/registrations/base"
    datarecord_session_api.put(registration_url, json=REGISTRATION, headers=admin_headers)

    # When the name is put again with another revision and packs
    body = {**REGISTRATION, "revision": str(uuid4()), "packs": []}
    put = datarecord_session_api.put(registration_url, json=body, headers=admin_headers)

    # Then the backend and the session hold the new registration
    assert put.status_code == 200
    assert datarecord_session_api.get(registration_url, headers=admin_headers).json() == put.json()
    [session] = datarecord_session_launcher.running.values()
    assert session.registrations == {"base": body}


@pytest.mark.parametrize("suspend", [False, True], ids=["reopen", "suspend-and-reopen"])
def test_a_dead_instance_is_restarted_with_its_registrations(
    datarecord_session_api: TestClient,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    admin_headers: dict[str, str],
    session_url: str,
    suspend: bool,
) -> None:
    # Given a registration, and an instance that died and was removed
    registration_url = f"{session_url}/registrations/base"
    put = datarecord_session_api.put(registration_url, json=REGISTRATION, headers=admin_headers)
    datarecord_session_launcher.running.clear()

    # When the session is (suspended and) read again
    if suspend:
        assert datarecord_session_api.delete(session_url, headers=admin_headers).status_code == 204
    get = datarecord_session_api.get(registration_url, headers=admin_headers)
    reopened = datarecord_session_api.post(session_url, headers=admin_headers)

    # Then a new instance started with the registration replayed
    assert get.json() == put.json()
    assert reopened.json()["generation"] == 2
    [session] = datarecord_session_launcher.running.values()
    assert session.registrations == {"base": REGISTRATION}


def test_a_registration_that_fails_its_replay_can_be_deleted(
    datarecord_session_api: TestClient,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    admin_headers: dict[str, str],
    session_url: str,
) -> None:
    # Given a registration of a store that is gone after a suspend
    registration_url = f"{session_url}/registrations/base"
    datarecord_session_api.put(registration_url, json=REGISTRATION, headers=admin_headers)
    datarecord_session_api.delete(session_url, headers=admin_headers)
    datarecord_session_launcher.stores.clear()

    # When the session is opened, and the registration deleted
    reopened = datarecord_session_api.post(session_url, headers=admin_headers)
    deleted = datarecord_session_api.delete(registration_url, headers=admin_headers)

    # Then the session starts without the registration and names it, and the registration
    # is gone
    assert reopened.status_code == 207
    assert reopened.json()["generation"] == 2
    assert reopened.json()["skipped_registrations"] == ["base"]
    [session] = datarecord_session_launcher.running.values()
    assert session.registrations == {}
    assert deleted.status_code == 204
    assert datarecord_session_api.get(registration_url, headers=admin_headers).status_code == 404


def test_an_instance_that_does_not_become_healthy_is_removed(
    datarecord_session_api: TestClient,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    admin_headers: dict[str, str],
    session_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given instances that never answer, and a short health timeout
    datarecord_session_launcher.healthy = False
    monkeypatch.setattr(datarecord_session_service, "HEALTH_TIMEOUT", 0.5)

    # When the session is opened
    response = datarecord_session_api.post(session_url, headers=admin_headers)

    # Then the request fails, and the started instance is removed again
    assert response.status_code == 503
    assert len(datarecord_session_launcher.started) == 1
    assert datarecord_session_launcher.running == {}


@pytest.mark.parametrize("name", ["Upper", "_staged", "a.b", "x" * 64])
def test_put_registration_rejects_a_bad_name(
    datarecord_session_api: TestClient,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    admin_headers: dict[str, str],
    session_url: str,
    name: str,
) -> None:
    # When a registration with a name the session cannot use is put
    response = datarecord_session_api.put(
        f"{session_url}/registrations/{name}", json=REGISTRATION, headers=admin_headers
    )

    # Then it is refused before any session starts
    assert response.status_code == 422
    assert datarecord_session_launcher.started == []


ROUTES = [
    ("POST", ""),
    ("DELETE", ""),
    ("GET", "/registrations/base"),
    ("PUT", "/registrations/base"),
    ("DELETE", "/registrations/base"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_routes_require_authentication(
    datarecord_session_api: TestClient, session_url: str, method: str, path: str
) -> None:
    # When a route is called without credentials
    response = datarecord_session_api.request(method, f"{session_url}{path}", json=REGISTRATION)

    # Then it is refused as unauthenticated
    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_routes_reject_a_non_owner(
    datarecord_session_api: TestClient,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    second_user_headers: dict[str, str],
    session_url: str,
    method: str,
    path: str,
) -> None:
    # When another user calls a route on the project
    response = datarecord_session_api.request(
        method, f"{session_url}{path}", json=REGISTRATION, headers=second_user_headers
    )

    # Then they are refused, and no session starts
    assert response.status_code == 403
    assert datarecord_session_launcher.started == []


def test_open_unknown_project_returns_404(
    datarecord_session_api: TestClient, admin_headers: dict[str, str]
) -> None:
    # When a session is opened for a project that does not exist
    response = datarecord_session_api.post(
        f"/v1/projects/{uuid4()}/datarecord-session", headers=admin_headers
    )

    # Then it is not found
    assert response.status_code == 404
