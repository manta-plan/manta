from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from manta.routes.v1.auth_route import _guest_limiters, router
from manta.services.auth_service import AuthService


class _NoAuthService:
    def login_as_guest(self) -> dict:
        return {"access_token": "a", "refresh_token": "r", "expires_in": 1, "refresh_expires_in": 1}


@pytest.fixture
def client() -> Iterator[TestClient]:
    _guest_limiters.cache_clear()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[AuthService] = _NoAuthService
    yield TestClient(app)
    _guest_limiters.cache_clear()


def test_guest_login_is_refused_when_disabled(monkeypatch, client: TestClient) -> None:
    # Given
    monkeypatch.setenv("GUEST_LOGIN_ENABLED", "false")

    # When
    response = client.post("/auth/guest")

    # Then
    assert response.status_code == 404


def test_refused_guest_logins_are_not_rate_limited(monkeypatch, client: TestClient) -> None:
    # Given
    monkeypatch.setenv("GUEST_LOGIN_ENABLED", "false")
    monkeypatch.setenv("GUEST_LOGINS_PER_CLIENT_PER_HOUR", "1")
    client.post("/auth/guest")
    client.post("/auth/guest")

    # When
    monkeypatch.setenv("GUEST_LOGIN_ENABLED", "true")
    response = client.post("/auth/guest")

    # Then
    assert response.status_code != 429
