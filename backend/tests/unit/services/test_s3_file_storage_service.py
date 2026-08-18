import io
from uuid import uuid4

import pytest
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError

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
