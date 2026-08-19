import io
from datetime import UTC, datetime
from uuid import uuid4

from mypy_boto3_s3.client import S3Client

from manta.config.s3_config import s3_bucket_name
from manta.services.s3_file_storage_service import S3FileStorageService


def test_upload_file(app_server: str, s3_client: S3Client) -> None:
    # Given
    bucket = s3_bucket_name()
    service = S3FileStorageService(client=s3_client, bucket=bucket)
    project_uuid = uuid4()
    content = b"energy model data"

    # When
    result = service.upload_file(project_uuid, "network.nc", io.BytesIO(content))

    # Then
    assert result.key == f"{project_uuid}/network.nc"
    assert result.size == len(content)

    stored = s3_client.get_object(Bucket=bucket, Key=result.key)["Body"].read()
    assert stored == content


def test_get_file(app_server: str, s3_client: S3Client) -> None:
    # Given
    bucket = s3_bucket_name()
    project_uuid = uuid4()
    key = f"{project_uuid}/network.nc"
    content = b"pypsa network data"
    s3_client.put_object(Bucket=bucket, Key=key, Body=content)
    service = S3FileStorageService(client=s3_client, bucket=bucket)
    destination = io.BytesIO()

    # When
    result = service.get_file(project_uuid, "network.nc", destination)

    # Then
    assert result.key == key
    assert result.size == len(content)
    assert destination.getvalue() == content
    assert (datetime.now(UTC) - result.last_modified).total_seconds() < 60
