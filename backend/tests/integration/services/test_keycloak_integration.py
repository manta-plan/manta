import logging

from keycloak import KeycloakAdmin, KeycloakOpenID
from keycloak.exceptions import KeycloakGetError
from pydantic import ValidationError

logger = logging.getLogger(__name__)


def test_connect(app_server: str, kc_oidc_client: KeycloakOpenID) -> None:
    # Given

    # When
    result = kc_oidc_client.well_known()

    # Then
    assert result is not None


def test_admin_connect(app_server: str, kc_admin_client: KeycloakAdmin) -> None:
    # Given

    # When
    result = kc_admin_client.get_admin_events()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    # Then
    assert result is not None


def test_validate_user_token(
    app_server: str, kc_admin_client: KeycloakAdmin, kc_oidc_client: KeycloakOpenID
) -> None:
    # Given
    try:
        alice_user_id = kc_admin_client.create_user(
            {
                "username": "alice",
                "email": "alice@manta.private",
                "enabled": "true",
                "emailVerified": "true",
            }
        )
        something = kc_admin_client.set_user_password(alice_user_id, "alex", temporary=False)
    except KeycloakGetError as kge:
        raise ValidationError from kge

    # When
    token = kc_oidc_client.token("alice", "alex")

    # Then
    assert something is not None
    assert token is not None
