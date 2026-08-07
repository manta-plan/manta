import httpx2


def test_get_health_returns_ok(app_server: str) -> None:
    # When
    response = httpx2.get(f"{app_server}/v1/health")

    # Then
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
