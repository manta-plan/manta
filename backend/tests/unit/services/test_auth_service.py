import pytest
from keycloak.exceptions import KeycloakError

from manta.entities import User
from manta.services.auth_service import AuthService
from manta.services.errors import AuthenticationError, BackendError

ISSUER = "http://localhost:8080/realms/manta"


@pytest.fixture(autouse=True)
def _stub_well_known(mock_kc_client):
    # AuthService compares each token's `iss` against Keycloak's own discovery
    # document rather than reconstructed config, so that's what needs stubbing.
    mock_kc_client.well_known.return_value = {"issuer": ISSUER}


def test_get_current_user_provisions_new_user(mock_db, mock_kc_client) -> None:
    # Given
    mock_kc_client.decode_token.return_value = {
        "sub": "abc-123",
        "iss": ISSUER,
        "preferred_username": "alice",
    }
    service = AuthService(db=mock_db, kc_client=mock_kc_client)

    # When
    user = service.authenticate("some-token")

    # Then
    assert user.username == "alice"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


def test_get_current_user_returns_existing_user(mock_db_class, mock_kc_client) -> None:
    # Given
    existing_user = User(username="alice", idp_subject="abc-123", idp_source=ISSUER)
    existing_user.id = 1
    mock_db = mock_db_class(query_results={User: existing_user})
    mock_kc_client.decode_token.return_value = {
        "sub": "abc-123",
        "iss": ISSUER,
        "preferred_username": "alice",
    }
    service = AuthService(db=mock_db, kc_client=mock_kc_client)

    # When
    user = service.authenticate("some-token")

    # Then
    assert user is existing_user
    mock_db.add.assert_not_called()


def test_get_current_user_rejects_wrong_issuer(mock_db, mock_kc_client) -> None:
    # Given
    mock_kc_client.decode_token.return_value = {
        "sub": "abc-123",
        "iss": "http://evil.example/realms/other",
        "preferred_username": "alice",
    }
    service = AuthService(db=mock_db, kc_client=mock_kc_client)

    # When / Then
    with pytest.raises(AuthenticationError):
        service.authenticate("some-token")


def test_get_current_user_rejects_invalid_token(mock_db, mock_kc_client) -> None:
    # Given
    # ValueError is what jwcrypto actually raises for a malformed/garbage bearer
    # token - not a KeycloakError, but still a client-side authentication failure.
    mock_kc_client.decode_token.side_effect = ValueError("bad token")
    service = AuthService(db=mock_db, kc_client=mock_kc_client)

    # When / Then
    with pytest.raises(AuthenticationError):
        service.authenticate("bad-token")


def test_get_current_user_wraps_keycloak_error_as_backend_error(mock_db, mock_kc_client) -> None:
    # Given
    mock_kc_client.decode_token.side_effect = KeycloakError("keycloak unavailable")
    service = AuthService(db=mock_db, kc_client=mock_kc_client)

    # When / Then
    with pytest.raises(BackendError):
        service.authenticate("some-token")
