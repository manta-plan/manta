import io
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from boto3.exceptions import S3TransferFailedError, S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError

from manta.services.results.s3_file_result import GetS3FileResult
from manta.services.s3_file_storage_service import S3FileStorageService, S3StorageError


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

DOWNLOAD_FAILURES = [_client_error(500), BotoCoreError(), S3TransferFailedError("boom")]
DOWNLOAD_FAILURE_IDS = ["client_error", "botocore_error", "s3_transfer_failed_error"]

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


def test_get_file_returns_key_size_and_last_modified(mock_s3_client) -> None:
    # Given
    last_modified = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    mock_s3_client.head_object.return_value = {
        "ContentLength": 42,
        "LastModified": last_modified,
    }
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")
    project_uuid = uuid4()
    destination = io.BytesIO()

    # When
    result = service.get_file(project_uuid, "network.nc", destination)

    # Then
    expected_key = f"{project_uuid}/network.nc"
    assert result.key == expected_key
    assert result.size == 42
    assert result.last_modified == last_modified
    mock_s3_client.download_fileobj.assert_called_once_with("manta", expected_key, destination)
    mock_s3_client.head_object.assert_called_once_with(Bucket="manta", Key=expected_key)


@pytest.mark.parametrize("error", DOWNLOAD_FAILURES, ids=DOWNLOAD_FAILURE_IDS)
def test_get_file_wraps_download_fileobj_failures(mock_s3_client, error) -> None:
    # Given
    mock_s3_client.download_fileobj.side_effect = error
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then
    with pytest.raises(S3StorageError):
        service.get_file(uuid4(), "network.nc", io.BytesIO())


@pytest.mark.parametrize("error", DOWNLOAD_FAILURES, ids=DOWNLOAD_FAILURE_IDS)
def test_get_file_wraps_head_object_failures(mock_s3_client, error) -> None:
    # Given
    mock_s3_client.head_object.side_effect = error
    service = S3FileStorageService(client=mock_s3_client, bucket="manta")

    # When / Then
    with pytest.raises(S3StorageError):
        service.get_file(uuid4(), "network.nc", io.BytesIO())


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
