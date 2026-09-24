import httpx2


def test_list_playbooks(app_server: str) -> None:
    # When
    response = httpx2.get(f"{app_server}/v1/playbooks")

    # Then
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["items"]]
    assert "pi-digit-statistics" in ids
    assert all("nodes" not in item for item in body["items"])


def test_get_playbook(app_server: str) -> None:
    # When
    response = httpx2.get(f"{app_server}/v1/playbooks/pi-digit-statistics")

    # Then
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "pi-digit-statistics"
    assert body["status"] == "available"
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["config"][0]["key"] == "num_pi_digits"


def test_get_playbook_with_unknown_id_returns_404(app_server: str) -> None:
    # When
    response = httpx2.get(f"{app_server}/v1/playbooks/unknown-playbook")

    # Then
    assert response.status_code == 404
