import io
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError

from manta.entities import Project, User
from manta.services.errors import AuthorizationError
from manta.services.results.s3_file_result import GetS3FileResult
from manta.services.s3_file_storage_service import S3FileStorageService, S3StorageError


def _project_and_owner(project_uuid=None, owner_id: int = 1) -> tuple[Project, User]:
    project = Project(name="North Sea Wind", owner_id=owner_id)
    project.id = 10
    project.uuid = project_uuid if project_uuid is not None else uuid4()
    owner = User(username="alice")
    owner.id = 1
    return project, owner


def _client_error(status_code: int) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": str(status_code)},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        },
        "S3Operation",
    )


UPLOAD_FAILURES = [_client_error(500), BotoCoreError(), S3UploadFailedError("boom")]
UPLOAD_FAILURE_IDS = ["client_error", "botocore_error", "s3_upload_failed_error"]

GET_FAILURES = [_client_error(500), BotoCoreError()]
GET_FAILURE_IDS = ["client_error", "botocore_error"]

DELETE_FAILURES = [_client_error(500), BotoCoreError()]
DELETE_FAILURE_IDS = ["client_error", "botocore_error"]

LIST_FAILURES = [_client_error(500), BotoCoreError()]
LIST_FAILURE_IDS = ["client_error", "botocore_error"]


def test_upload_file_returns_key_and_size(mock_s3_client) -> None:
    # Given
    mock_s3_client.head_object.return_value = {"ContentLength": 42}
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")
    project_uuid = uuid4()

    # When
    result = service.upload_file(project_uuid, "network.nc", io.BytesIO(b"data"))

    # Then
    expected_key = f"{project_uuid}/network.nc"
    assert result.key == expected_key
    assert result.size == 42
    mock_s3_client.upload_fileobj.assert_called_once()
    mock_s3_client.head_object.assert_called_once_with(Bucket="manta", Key=expected_key)


@pytest.mark.parametrize("error", UPLOAD_FAILURES, ids=UPLOAD_FAILURE_IDS)
def test_upload_file_wraps_upload_fileobj_failures(mock_s3_client, error) -> None:
    # Given
    mock_s3_client.upload_fileobj.side_effect = error
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then
    with pytest.raises(S3StorageError):
        service.upload_file(uuid4(), "network.nc", io.BytesIO(b"data"))


@pytest.mark.parametrize("error", UPLOAD_FAILURES, ids=UPLOAD_FAILURE_IDS)
def test_upload_file_wraps_head_object_failures(mock_s3_client, error) -> None:
    # Given
    mock_s3_client.head_object.side_effect = error
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then
    with pytest.raises(S3StorageError):
        service.upload_file(uuid4(), "network.nc", io.BytesIO(b"data"))


def _fake_body(chunks: list[bytes] | Exception) -> MagicMock:
    """Stands in for the StreamingBody `get_object` returns."""
    body = MagicMock()
    if isinstance(chunks, Exception):
        body.iter_chunks.side_effect = chunks
    else:
        body.iter_chunks.return_value = iter(chunks)
    return body


def test_get_file_streams_the_content_only_once_it_is_iterated(mock_s3_client) -> None:
    # Given
    last_modified = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    body = _fake_body([b"pypsa ", b"network"])
    mock_s3_client.get_object.return_value = {
        "ContentLength": 13,
        "LastModified": last_modified,
        "ContentType": "application/x-netcdf",
        "Body": body,
    }
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")
    project_uuid = uuid4()

    # When
    result = service.get_file(project_uuid, "network.nc")

    # Then the file is opened and described, but nothing is read from it yet...
    expected_key = f"{project_uuid}/network.nc"
    mock_s3_client.get_object.assert_called_once_with(Bucket="manta", Key=expected_key)
    assert result.key == expected_key
    assert result.size == 13
    assert result.last_modified == last_modified
    assert result.content_type == "application/x-netcdf"
    body.iter_chunks.assert_not_called()

    # ...until the content is iterated, chunk by chunk, after which the
    # connection is handed back
    assert list(result.content) == [b"pypsa ", b"network"]
    body.close.assert_called_once()


def test_get_file_defaults_the_content_type_when_s3_has_none(mock_s3_client) -> None:
    # Given
    mock_s3_client.get_object.return_value = {
        "ContentLength": 0,
        "LastModified": datetime(2026, 8, 19, 12, 0, tzinfo=UTC),
        "Body": _fake_body([]),
    }
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When
    result = service.get_file(uuid4(), "network.nc")

    # Then
    assert result.content_type == "application/octet-stream"


@pytest.mark.parametrize("error", GET_FAILURES, ids=GET_FAILURE_IDS)
def test_get_file_wraps_get_object_failures(mock_s3_client, error) -> None:
    # Given
    mock_s3_client.get_object.side_effect = error
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then
    with pytest.raises(S3StorageError):
        service.get_file(uuid4(), "network.nc")


@pytest.mark.parametrize("error", GET_FAILURES, ids=GET_FAILURE_IDS)
def test_get_file_wraps_failures_while_streaming(mock_s3_client, error) -> None:
    # Given a file that opens fine, but fails part-way through reading
    body = _fake_body(error)
    mock_s3_client.get_object.return_value = {
        "ContentLength": 13,
        "LastModified": datetime(2026, 8, 19, 12, 0, tzinfo=UTC),
        "Body": body,
    }
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")
    result = service.get_file(uuid4(), "network.nc")

    # When / Then
    with pytest.raises(S3StorageError):
        list(result.content)
    body.close.assert_called_once()


def test_delete_file_deletes_the_object(mock_s3_client) -> None:
    # Given
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")
    project_uuid = uuid4()

    # When
    result = service.delete_file(project_uuid, "network.nc")

    # Then
    assert result is None
    mock_s3_client.delete_object.assert_called_once_with(
        Bucket="manta", Key=f"{project_uuid}/network.nc"
    )


@pytest.mark.parametrize("error", DELETE_FAILURES, ids=DELETE_FAILURE_IDS)
def test_delete_file_wraps_delete_object_failures(mock_s3_client, error) -> None:
    # Given
    mock_s3_client.delete_object.side_effect = error
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then
    with pytest.raises(S3StorageError):
        service.delete_file(uuid4(), "network.nc")


def test_list_files_returns_all_files_across_pages(mock_s3_client) -> None:
    # Given
    project_uuid = uuid4()
    last_modified = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    mock_s3_client.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {"Key": f"{project_uuid}/network.nc", "Size": 42, "LastModified": last_modified}
            ]
        },
        {
            "Contents": [
                {"Key": f"{project_uuid}/results.csv", "Size": 7, "LastModified": last_modified}
            ]
        },
    ]
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When
    results = service.list_files(project_uuid)

    # Then
    assert results == [
        GetS3FileResult(key=f"{project_uuid}/network.nc", size=42, last_modified=last_modified),
        GetS3FileResult(key=f"{project_uuid}/results.csv", size=7, last_modified=last_modified),
    ]
    mock_s3_client.get_paginator.assert_called_once_with("list_objects_v2")
    mock_s3_client.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket="manta", Prefix=f"{project_uuid}/"
    )


def test_list_files_narrows_the_listing_to_a_prefix_within_the_project(mock_s3_client) -> None:
    # Given
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")
    project_uuid = uuid4()

    # When
    service.list_files(project_uuid, prefix="runs/abc/output/")

    # Then the prefix is applied inside the project's own, never instead of it
    mock_s3_client.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket="manta", Prefix=f"{project_uuid}/runs/abc/output/"
    )


def test_list_files_returns_empty_list_when_no_files_match(mock_s3_client) -> None:
    # Given
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When
    results = service.list_files(uuid4())

    # Then
    assert results == []


@pytest.mark.parametrize("error", LIST_FAILURES, ids=LIST_FAILURE_IDS)
def test_list_files_wraps_paginator_failures(mock_s3_client, error) -> None:
    # Given
    mock_s3_client.get_paginator.return_value.paginate.side_effect = error
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then
    with pytest.raises(S3StorageError):
        service.list_files(uuid4())


def test_ensure_bucket_exists_when_bucket_already_exists(mock_s3_client) -> None:
    # Given
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When
    service.ensure_bucket_exists()

    # Then
    mock_s3_client.head_bucket.assert_called_once_with(Bucket="manta")
    mock_s3_client.create_bucket.assert_not_called()


def test_ensure_bucket_exists_creates_missing_bucket(mock_s3_client) -> None:
    # Given
    mock_s3_client.head_bucket.side_effect = _client_error(404)
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When
    service.ensure_bucket_exists()

    # Then
    mock_s3_client.create_bucket.assert_called_once_with(Bucket="manta")


def test_ensure_bucket_exists_raises_on_non_404_client_error(mock_s3_client) -> None:
    # Given
    mock_s3_client.head_bucket.side_effect = _client_error(403)
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then
    with pytest.raises(S3StorageError):
        service.ensure_bucket_exists()
    mock_s3_client.create_bucket.assert_not_called()


def test_ensure_bucket_exists_raises_when_create_bucket_fails(mock_s3_client) -> None:
    # Given
    mock_s3_client.head_bucket.side_effect = _client_error(404)
    mock_s3_client.create_bucket.side_effect = BotoCoreError()
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then
    with pytest.raises(S3StorageError):
        service.ensure_bucket_exists()


def test_ensure_bucket_exists_raises_on_connection_failure(mock_s3_client) -> None:
    # Given
    mock_s3_client.head_bucket.side_effect = BotoCoreError()
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then
    with pytest.raises(S3StorageError):
        service.ensure_bucket_exists()
    mock_s3_client.create_bucket.assert_not_called()


def _listing(mock_s3_client, keys: list[str]) -> None:
    last_modified = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    mock_s3_client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": k, "Size": 1, "LastModified": last_modified} for k in keys]}
    ]


def test_delete_project_files_deletes_everything_under_the_project_prefix(mock_s3_client) -> None:
    # Given
    project_uuid = uuid4()
    keys = [f"{project_uuid}/a.nc", f"{project_uuid}/runs/r1/output/b.nc"]
    _listing(mock_s3_client, keys)
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When
    service.delete_project_files(*_project_and_owner(project_uuid))

    # Then
    mock_s3_client.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket="manta", Prefix=f"{project_uuid}/"
    )
    mock_s3_client.delete_objects.assert_called_once_with(
        Bucket="manta",
        Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
    )


def test_delete_project_files_without_files_deletes_nothing(mock_s3_client) -> None:
    # Given
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When
    service.delete_project_files(*_project_and_owner())

    # Then
    mock_s3_client.delete_objects.assert_not_called()


def test_delete_project_files_deletes_in_batches_of_1000(mock_s3_client) -> None:
    # Given
    project_uuid = uuid4()
    _listing(mock_s3_client, [f"{project_uuid}/f{i}.nc" for i in range(2500)])
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When
    service.delete_project_files(*_project_and_owner(project_uuid))

    # Then
    batch_sizes = [
        len(call.kwargs["Delete"]["Objects"])
        for call in mock_s3_client.delete_objects.call_args_list
    ]
    assert batch_sizes == [1000, 1000, 500]


@pytest.mark.parametrize("error", DELETE_FAILURES, ids=DELETE_FAILURE_IDS)
def test_delete_project_files_wraps_delete_objects_failures(mock_s3_client, error) -> None:
    # Given
    project_uuid = uuid4()
    _listing(mock_s3_client, [f"{project_uuid}/a.nc"])
    mock_s3_client.delete_objects.side_effect = error
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then
    with pytest.raises(S3StorageError):
        service.delete_project_files(*_project_and_owner(project_uuid))


def test_delete_project_files_fails_when_s3_reports_per_object_errors(mock_s3_client) -> None:
    # Given
    project_uuid = uuid4()
    _listing(mock_s3_client, [f"{project_uuid}/a.nc"])
    mock_s3_client.delete_objects.return_value = {
        "Errors": [{"Key": "a.nc", "Code": "AccessDenied", "Message": "Access Denied"}]
    }
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then the message names the failing key and its error code
    with pytest.raises(S3StorageError, match=r"'a.nc' \(AccessDenied: Access Denied\)"):
        service.delete_project_files(*_project_and_owner(project_uuid))


def test_delete_project_files_rejects_non_owner(mock_s3_client) -> None:
    # Given a project owned by someone other than the requesting user
    project, _ = _project_and_owner(owner_id=2)
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When/Then nothing is listed or deleted
    with pytest.raises(AuthorizationError):
        service.delete_project_files(project, _project_and_owner()[1])
    mock_s3_client.get_paginator.assert_not_called()
    mock_s3_client.delete_objects.assert_not_called()
