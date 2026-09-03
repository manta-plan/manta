import logging

from keycloak import KeycloakAdmin, KeycloakOpenID, KeycloakOpenIDConnection
from keycloak.exceptions import KeycloakGetError
from pydantic import ValidationError

from manta.routes.v1.auth_route import get_user

logger = logging.getLogger(__name__)


def test_connect(app_server: str) -> None:
    # Given
    kc_connection = KeycloakOpenID(
        server_url="http://localhost:8080",  # TODO Replace
        realm_name="manta",  # TODO replace these parameters with the realm-specific ones
        client_id="manta-client",
        client_secret_key="im-so-secret",  # noqa: S106
    )

    # When
    result = kc_connection.well_known()

    # Then
    assert result is not None


def test_admin_connect(app_server: str) -> None:
    # Given
    kc_adm_connection = KeycloakOpenIDConnection(
        server_url="http://localhost:8080",  # TODO Replace
        realm_name="master",  # TODO replace these parameters with the realm-specific ones
        username="kcadmin",
        password="kcpassword",  # noqa: S106
    )
    kc_admin = KeycloakAdmin(connection=kc_adm_connection)

    # When
    result = kc_admin.get_admin_events()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    # Then
    assert result is not None


def test_validate_user_token(app_server: str) -> None:
    # Given
    kc_adm_connection = KeycloakOpenIDConnection(
        server_url="http://localhost:8080",  # TODO Replace
        realm_name="manta",  # TODO replace these parameters with the realm-specific ones
        user_realm_name="master",  # kcadmin only exists in master; target ops at manta
        username="kcadmin",
        password="kcpassword",  # noqa: S106
    )
    kc_admin = KeycloakAdmin(connection=kc_adm_connection)

    # When
    try:
        alice_user_id = kc_admin.create_user(
            {
                "username": "alice",
                "email": "alice@manta.private",
                "enabled": "true",
                "emailVerified": "true",
            }
        )
    except KeycloakGetError as kge:
        raise ValidationError from kge
    something = kc_admin.set_user_password(alice_user_id, "alex", temporary=False)

    thingy = kc_admin.get_users({"realm": "manta"})

    logger.error(f"DOOD {thingy}")
    response = get_user("alice", "alex")

    # Then
    assert something is not None
    assert response.status_code == 200
