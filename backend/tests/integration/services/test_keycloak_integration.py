import logging

from keycloak import KeycloakAdmin, KeycloakOpenID, KeycloakOpenIDConnection

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
