import pytest
from fastapi import HTTPException
from starlette.requests import Request

from manta.routes.v1.auth_route import _guest_limiters, limit_guest_logins


@pytest.fixture(autouse=True)
def _fresh_limiters():
    # The limiters are built once per process from the env, so each test needs new ones.
    _guest_limiters.cache_clear()
    yield
    _guest_limiters.cache_clear()


def _request_from(host: str) -> Request:
    return Request({"type": "http", "client": (host, 12345), "headers": []})


def test_limits_guest_logins_per_client(monkeypatch) -> None:
    # Given
    monkeypatch.setenv("GUEST_LOGINS_PER_CLIENT_PER_HOUR", "2")
    monkeypatch.setenv("GUEST_LOGINS_PER_HOUR", "100")
    limit_guest_logins(_request_from("1.1.1.1"))
    limit_guest_logins(_request_from("1.1.1.1"))

    # When / Then
    with pytest.raises(HTTPException) as refused:
        limit_guest_logins(_request_from("1.1.1.1"))
    assert refused.value.status_code == 429
    assert refused.value.headers == {"Retry-After": "3600"}

    # ...while other clients can still log in as guests
    limit_guest_logins(_request_from("2.2.2.2"))


def test_limits_guest_logins_across_all_clients(monkeypatch) -> None:
    # Given
    monkeypatch.setenv("GUEST_LOGINS_PER_CLIENT_PER_HOUR", "5")
    monkeypatch.setenv("GUEST_LOGINS_PER_HOUR", "2")
    limit_guest_logins(_request_from("1.1.1.1"))
    limit_guest_logins(_request_from("2.2.2.2"))

    # When / Then
    with pytest.raises(HTTPException) as refused:
        limit_guest_logins(_request_from("3.3.3.3"))
    assert refused.value.status_code == 429
