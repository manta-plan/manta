import psycopg
import pytest


def test_prefect_role_cannot_read_app_tables(
    app_server: str, prefect_role_app_db_connection: psycopg.Connection
) -> None:
    # Given a connection to the app's database, authenticated as Prefect's
    # own Postgres role (see docker/conf/postgres-init/create-prefect-db.sh)

    # When it tries to read one of the app's tables

    # Then Postgres denies it — table grants aren't implicit across roles, so
    # this holds without the init script needing to revoke anything
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        prefect_role_app_db_connection.cursor() as cursor,
    ):
        cursor.execute("SELECT 1 FROM projects")
