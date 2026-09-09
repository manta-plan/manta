import pytest
from keycloak.exceptions import KeycloakError

from manta.entities import User, UserCredential
from manta.errors.authentication_error import AuthenticationError
from manta.services.auth_service import AuthService

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
    user = service.get_current_user("some-token")

    # Then
    assert user.username == "alice"
    assert mock_db.add.call_count == 2  # the new User, then its UserCredential
    mock_db.commit.assert_called_once()


def test_get_current_user_returns_existing_user(mock_db_class, mock_kc_client) -> None:
    # Given
    existing_user = User(username="alice")
    existing_user.id = 1
    existing_credential = UserCredential(user_id=1, idp_subject="abc-123", idp_source=ISSUER)
    mock_db = mock_db_class(
        query_results={UserCredential: existing_credential, User: existing_user}
    )
    mock_kc_client.decode_token.return_value = {
        "sub": "abc-123",
        "iss": ISSUER,
        "preferred_username": "alice",
    }
    service = AuthService(db=mock_db, kc_client=mock_kc_client)

    # When
    user = service.get_current_user("some-token")

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
        service.get_current_user("some-token")


def test_get_current_user_rejects_invalid_token(mock_db, mock_kc_client) -> None:
    # Given
    mock_kc_client.decode_token.side_effect = KeycloakError("bad token")
    service = AuthService(db=mock_db, kc_client=mock_kc_client)

    # When / Then
    with pytest.raises(AuthenticationError):
        service.get_current_user("bad-token")
