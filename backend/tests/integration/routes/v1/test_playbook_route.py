import httpx2
from keycloak.openid_connection import KeycloakOpenID
from playbook_library import library_catalogue
from playbook_library.playbooks import library_playbooks

_LIBRARY_PLAYBOOK = "cluster-expand-dispatch"


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


def test_list_playbooks(app_server: str, kc_oidc_client: KeycloakOpenID) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)

    # When
    response = httpx2.get(f"{app_server}/v1/playbooks", headers=headers)

    # Then every library playbook is listed, each with its steps and their blocks
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == len(library_playbooks())
    playbook = next(item for item in body["items"] if item["name"] == _LIBRARY_PLAYBOOK)
    assert playbook["steps"] == [
        {"name": "cluster", "block": "cluster_time"},
        {"name": "expansion_overnight", "block": "overnight_capacity_expansion"},
        {"name": "expansion_myopic", "block": "myopic_capacity_expansion"},
        {"name": "dispatch", "block": "rolling_horizon_dispatch"},
    ]


def test_get_playbook(app_server: str, kc_oidc_client: KeycloakOpenID) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)

    # When
    response = httpx2.get(f"{app_server}/v1/playbooks/{_LIBRARY_PLAYBOOK}", headers=headers)

    # Then it carries everything needed to build a config: the defaults, each
    # step's block settings schema, and the conditions deciding which steps run
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == _LIBRARY_PLAYBOOK
    assert body["default_config"] == library_playbooks()[_LIBRARY_PLAYBOOK].default_config
    catalogue = library_catalogue()
    steps = {step["name"]: step for step in body["steps"]}
    for step in body["steps"]:
        block = catalogue.blocks[step["block"]]
        assert step["block_summary"] == block.doc
        assert step["block_config_schema"] == block.config_schema
    assert steps["cluster"]["when"] is None
    assert steps["expansion_overnight"]["when"] == {
        "config": "globals.expansion_mode",
        "equals": "overnight",
    }
    assert steps["dispatch"]["inputs"] == {"capacity_source": "${steps.expansion_overnight.output}"}


def test_get_playbook_with_unknown_name_returns_404(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)

    # When
    response = httpx2.get(f"{app_server}/v1/playbooks/does-not-exist", headers=headers)

    # Then
    assert response.status_code == 404


def test_validate_playbook_config_without_a_config_checks_the_default(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)

    # When
    response = httpx2.post(
        f"{app_server}/v1/playbooks/{_LIBRARY_PLAYBOOK}/validate", json={}, headers=headers
    )

    # Then the playbook's own default_config can run as it is
    assert response.status_code == 200
    assert response.json() == {"valid": True, "issues": []}


def test_validate_playbook_config_lists_every_issue_with_a_200(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given the default config switched to its myopic branch, which needs a dimension
    # the playbook's data does not have, and with a misspelt setting
    headers = _auth_headers(app_server, kc_oidc_client)
    default_config = library_playbooks()[_LIBRARY_PLAYBOOK].default_config
    config = {
        **default_config,
        "globals": {"expansion_mode": "myopic"},
        "cluster": {"n_hours": 3, "n_hour": 6},
    }

    # When
    response = httpx2.post(
        f"{app_server}/v1/playbooks/{_LIBRARY_PLAYBOOK}/validate",
        json={"config": config},
        headers=headers,
    )

    # Then both are reported as data, each pointing at its step, and the setting
    # where there is one
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert [
        (issue["kind"], issue["step_path"], issue["config_path"]) for issue in body["issues"]
    ] == [
        ("dims", ["expansion_myopic"], None),
        ("config", ["cluster"], ["cluster", "n_hour"]),
    ]


def test_validate_playbook_config_with_unknown_name_returns_404(
    app_server: str, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    headers = _auth_headers(app_server, kc_oidc_client)

    # When
    response = httpx2.post(
        f"{app_server}/v1/playbooks/does-not-exist/validate", json={}, headers=headers
    )

    # Then
    assert response.status_code == 404


def test_playbooks_require_authentication(app_server: str) -> None:
    # When
    list_response = httpx2.get(f"{app_server}/v1/playbooks")
    get_response = httpx2.get(f"{app_server}/v1/playbooks/{_LIBRARY_PLAYBOOK}")
    validate_response = httpx2.post(
        f"{app_server}/v1/playbooks/{_LIBRARY_PLAYBOOK}/validate", json={}
    )

    # Then
    assert list_response.status_code == 401
    assert get_response.status_code == 401
    assert validate_response.status_code == 401
