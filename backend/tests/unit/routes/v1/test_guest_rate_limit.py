# SPDX-FileCopyrightText: Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

import pytest
from fastapi import Depends, FastAPI, HTTPException
from starlette.requests import Request
from starlette.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

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


def _behind_proxy(proxy: str, trusted: str) -> TestClient:
    # What uvicorn.run(proxy_headers=True, forwarded_allow_ips=...) wraps the app in.
    app = FastAPI()

    @app.post("/guest", dependencies=[Depends(limit_guest_logins)])
    def guest() -> None:
        return None

    return TestClient(ProxyHeadersMiddleware(app, trusted_hosts=trusted), client=(proxy, 50000))


def test_limits_each_user_behind_a_trusted_proxy(monkeypatch) -> None:
    # Given
    monkeypatch.setenv("GUEST_LOGINS_PER_CLIENT_PER_HOUR", "1")
    monkeypatch.setenv("GUEST_LOGINS_PER_HOUR", "100")
    caddy = _behind_proxy("172.30.0.2", trusted="172.30.0.2")
    assert caddy.post("/guest", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200

    # When / Then: another user behind the same proxy has their own limit
    assert caddy.post("/guest", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
    assert caddy.post("/guest", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429


def test_ignores_forwarded_for_from_an_untrusted_peer(monkeypatch) -> None:
    # Given
    monkeypatch.setenv("GUEST_LOGINS_PER_CLIENT_PER_HOUR", "1")
    monkeypatch.setenv("GUEST_LOGINS_PER_HOUR", "100")
    direct = _behind_proxy("9.9.9.9", trusted="172.30.0.2")
    assert direct.post("/guest", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200

    # When / Then: a made-up X-Forwarded-For doesn't get it a fresh limit
    assert direct.post("/guest", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429
