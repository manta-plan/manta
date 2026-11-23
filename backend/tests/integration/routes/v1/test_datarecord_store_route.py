from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from datarecord import S3Credentials, Workspace
from dotenv import dotenv_values
from keycloak.openid_connection import KeycloakOpenID
from mypy_boto3_s3.client import S3Client

from manta.services.results.datarecord_store_result import ListDatarecordRevisionsResult

BACKEND_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


def _auth_headers(app_server: str, kc_oidc_client: KeycloakOpenID) -> dict[str, str]:
    token = kc_oidc_client.token("manta-admin", "manta-admin")
    claims = kc_oidc_client.decode_token(token["access_token"], validate=False)
    response = httpx2.post(
        f"{app_server}/v1/auth/register",
        json={"username": "manta-admin", "idp_subject": claims["sub"], "idp_source": claims["iss"]},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {token['access_token']}"}


def _create_project(app_server: str, headers: dict[str, str]) -> str:
    response = httpx2.post(
        f"{app_server}/v1/projects", json={"name": "Store listings"}, headers=headers
    )
    assert response.status_code == 201
    return response.json()["uuid"]


@pytest.fixture(scope="module")
def workspace(seaweedfs_service: dict[str, str]) -> Iterator[Workspace]:
    env = dotenv_values(BACKEND_ENV_FILE)
    workspace = Workspace(
        credentials=S3Credentials(
            key_id=env["S3_ACCESS_KEY"],
            secret=env["S3_SECRET_KEY"],
            endpoint=f"http://{seaweedfs_service['host']}:{seaweedfs_service['port']}",
            url_style="path",
        )
    )
    yield workspace
    workspace.close()


@pytest.fixture
def headers(app_server: str, kc_oidc_client: KeycloakOpenID) -> dict[str, str]:
    return _auth_headers(app_server, kc_oidc_client)


@pytest.fixture
def project_with_store(
    app_server: str,
    headers: dict[str, str],
    workspace: Workspace,
    s3_client: S3Client,
    build_datarecord_store,
) -> tuple[str, ListDatarecordRevisionsResult]:
    project_uuid = _create_project(app_server, headers)
    bucket = dotenv_values(BACKEND_ENV_FILE)["S3_BUCKET"]
    expected = build_datarecord_store(workspace, f"s3://{bucket}/{project_uuid}/store")
    s3_client.put_object(Bucket=bucket, Key=f"{project_uuid}/incomplete/layers/x", Body=b"")
    s3_client.put_object(Bucket=bucket, Key=f"{project_uuid}/notes.txt", Body=b"")
    return project_uuid, expected


def test_list_datarecord_stores(
    app_server: str, headers: dict[str, str], project_with_store
) -> None:
    # Given
    project_uuid, _ = project_with_store

    # When
    response = httpx2.get(
        f"{app_server}/v1/projects/{project_uuid}/datarecord-stores", headers=headers
    )

    # Then
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "name": "store",
                "label": "Test store",
                "description": "A base scenario and one result.",
            }
        ]
    }


def test_list_datarecord_revisions(
    app_server: str, headers: dict[str, str], project_with_store
) -> None:
    # Given
    project_uuid, expected = project_with_store

    # When
    response = httpx2.get(
        f"{app_server}/v1/projects/{project_uuid}/datarecord-stores/store/datarecord-revisions",
        headers=headers,
    )

    # Then
    assert response.status_code == 200
    assert ListDatarecordRevisionsResult.model_validate(response.json()) == expected


@pytest.mark.parametrize(
    ("store", "status_code"),
    [("incomplete", 404), ("missing", 404), (".hidden", 422), ("a%20b", 422), ("a%2Fb", 404)],
    ids=["without_store_file", "missing", "invalid_name", "encoded_space", "slash"],
)
def test_list_datarecord_revisions_of_no_store(
    store: str, status_code: int, app_server: str, headers: dict[str, str], project_with_store
) -> None:
    # Given
    project_uuid, _ = project_with_store

    # When
    response = httpx2.get(
        f"{app_server}/v1/projects/{project_uuid}/datarecord-stores/{store}/datarecord-revisions",
        headers=headers,
    )

    # Then
    assert response.status_code == status_code


LISTING_PATHS = ["datarecord-stores", "datarecord-stores/store/datarecord-revisions"]


@pytest.mark.parametrize("path", LISTING_PATHS, ids=["stores", "revisions"])
def test_listings_require_authentication(path: str, app_server: str) -> None:
    # When
    response = httpx2.get(f"{app_server}/v1/projects/{uuid4()}/{path}")

    # Then
    assert response.status_code == 401


@pytest.mark.parametrize("path", LISTING_PATHS, ids=["stores", "revisions"])
def test_listings_refuse_a_foreign_project(
    path: str, app_server: str, second_user_headers: dict[str, str], project_with_store
) -> None:
    # Given
    project_uuid, _ = project_with_store

    # When
    response = httpx2.get(
        f"{app_server}/v1/projects/{project_uuid}/{path}", headers=second_user_headers
    )

    # Then
    assert response.status_code == 403
