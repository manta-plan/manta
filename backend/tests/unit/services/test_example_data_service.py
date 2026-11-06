import io
import json
from unittest.mock import MagicMock
from uuid import uuid4

import httpx2
import pytest
from botocore.exceptions import BotoCoreError

from manta.config.example_data_config import ADMIN_IDP_SUBJECT, ADMIN_USERNAME
from manta.entities import User
from manta.services import example_data_service
from manta.services.example_data_service import PUBLIC_OBJECTS_URL, ExampleDataService

ISSUER = "http://localhost:8080/realms/manta"
INPUTS = "e5f2eacd-ba5c-463c-a663-3017ef904d1d"

FILES = {
    "small/manifest.json": b"{}",
    "small/revisions.json": json.dumps({"inputs": INPUTS}).encode(),
    "small/layers/a.parquet": b"data",
}


def _public_bucket(request: httpx2.Request) -> httpx2.Response:
    if str(request.url).startswith(PUBLIC_OBJECTS_URL):
        if request.url.params.get("delimiter") == "/":
            return httpx2.Response(200, json={"prefixes": ["small/"]})
        items = [{"name": name, "mediaLink": f"https://media/{name}"} for name in FILES]
        return httpx2.Response(200, json={"items": items})
    return httpx2.Response(200, content=FILES[request.url.path.removeprefix("/")])


@pytest.fixture
def s3_client() -> MagicMock:
    """An S3 client whose bucket holds the downloaded example store, and nothing else."""
    client = MagicMock()
    client.list_objects_v2.return_value = {"KeyCount": 0}
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": f"example-data/{name}"} for name in FILES]}
    ]
    return client


def _service(mock_db, s3_client) -> ExampleDataService:
    return ExampleDataService(mock_db, s3_client, "manta")


def test_seed_downloads_every_store_into_the_example_data(mock_db, s3_client, monkeypatch) -> None:
    # Given
    monkeypatch.setattr(
        example_data_service,
        "_http_client",
        lambda: httpx2.Client(transport=httpx2.MockTransport(_public_bucket)),
    )

    # When
    _service(mock_db, s3_client).seed()

    # Then
    uploads = [call.kwargs for call in s3_client.put_object.call_args_list]
    assert sorted(upload["Key"] for upload in uploads) == sorted(
        f"example-data/{name}" for name in FILES
    )
    assert uploads[-1]["Key"] == "example-data/small/manifest.json"


def test_seed_does_not_raise_when_the_public_bucket_is_unreachable(
    mock_db, s3_client, monkeypatch
) -> None:
    # Given
    def unreachable(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("offline", request=request)

    monkeypatch.setattr(
        example_data_service,
        "_http_client",
        lambda: httpx2.Client(transport=httpx2.MockTransport(unreachable)),
    )

    # When
    _service(mock_db, s3_client).seed()

    # Then
    s3_client.put_object.assert_not_called()


def test_ensure_admin_project_creates_the_admin_and_its_project_with_the_example_data(
    mock_db, s3_client
) -> None:
    # When
    _service(mock_db, s3_client).ensure_admin_project(idp_source=ISSUER)

    # Then
    user, project = [call.args[0] for call in mock_db.add.call_args_list]
    assert (user.username, user.idp_subject, user.idp_source) == (
        ADMIN_USERNAME,
        ADMIN_IDP_SUBJECT,
        ISSUER,
    )
    assert project.owner_id == user.id
    copies = [call.kwargs for call in s3_client.copy_object.call_args_list]
    assert sorted(copy["Key"] for copy in copies) == sorted(
        f"{project.uuid}/{name}" for name in FILES
    )
    assert copies[-1]["CopySource"] == {
        "Bucket": "manta",
        "Key": "example-data/small/manifest.json",
    }


def test_create_project_keeps_the_project_when_copying_the_example_data_fails(
    mock_db, s3_client
) -> None:
    # Given
    s3_client.copy_object.side_effect = BotoCoreError()

    # When
    _service(mock_db, s3_client).create_project(User(username="alice"))

    # Then
    mock_db.commit.assert_called_once()


def test_data_record_is_the_stores_inputs_revision(mock_db, s3_client) -> None:
    # Given
    s3_client.get_object.return_value = {"Body": io.BytesIO(FILES["small/revisions.json"])}
    project_uuid = uuid4()

    # When
    record = _service(mock_db, s3_client).data_record(project_uuid, "small")

    # Then
    assert record.store_url == f"s3://manta/{project_uuid}/small"
    assert str(record.revision_uuid) == INPUTS
