"""The realm file is applied by Keycloak at container startup, so a malformed
one surfaces as a ~30s boot failure in the integration suite. Parsing it here
fails in milliseconds instead."""

import json
from pathlib import Path

REALM_FILE = Path(__file__).resolve().parents[2].parent / "docker" / "keycloak" / "manta-realm.json"


def test_realm_file_declares_expected_clients() -> None:
    # Given / When
    realm = json.loads(REALM_FILE.read_text())
    clients = {c["clientId"]: c for c in realm["clients"]}

    # Then
    assert realm["realm"] == "manta"
    assert {"manta-frontend", "manta-api", "manta-test"} == set(clients)


def test_only_the_test_client_enables_direct_access_grants() -> None:
    """ROPC is what makes the test fixtures possible, and what RFC 9700 says
    must not be used for real logins — so it stays confined to manta-test."""
    # Given / When
    realm = json.loads(REALM_FILE.read_text())
    with_ropc = {c["clientId"] for c in realm["clients"] if c.get("directAccessGrantsEnabled")}

    # Then
    assert with_ropc == {"manta-test"}


def test_dev_user_passwords_are_not_temporary() -> None:
    """A temporary password forces a reset on first login, which would break
    token minting in the integration suite."""
    # Given / When
    realm = json.loads(REALM_FILE.read_text())

    # Then
    for user in realm["users"]:
        for credential in user["credentials"]:
            assert credential["temporary"] is False
