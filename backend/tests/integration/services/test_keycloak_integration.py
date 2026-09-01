from keycloak import KeycloakAdmin, KeycloakOpenIDConnection


def test_connect(app_server: str) -> None:
    # Given
    kc_connection = KeycloakOpenIDConnection(
        server_url="http://localhost:8080",  # TODO Replace
        realm_name="manta",  # TODO replace these parameters with the realm-specific ones
        client_id="manta-client",
        client_secret_key="im-so-secret",  # noqa: S106
    )

    kc_admin = KeycloakAdmin(connection=kc_connection)

    # When
    result = kc_admin.get_admin_events()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    # Then
    assert result is not None
