import logging
from typing import IO
from uuid import UUID

from boto3.exceptions import S3TransferFailedError, S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends
from mypy_boto3_s3.client import S3Client

from manta.config.s3_config import get_s3_client, s3_bucket_name
from manta.services.results.s3_file_result import GetS3FileResult, UploadS3FileResult

logger = logging.getLogger(__name__)


class S3StorageError(Exception):
    pass


class S3FileStorageService:
    def __init__(
        self,
        client: S3Client = Depends(get_s3_client),
        bucket: str = Depends(s3_bucket_name),
    ) -> None:
        self.client = client
        self.bucket = bucket

    def upload_file(
        self, project_uuid: UUID, filename: str, content: IO[bytes]
    ) -> UploadS3FileResult:
        key = f"{project_uuid}/{filename}"

        try:
            self.client.upload_fileobj(content, self.bucket, key)
            head_response = self.client.head_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError, S3UploadFailedError) as e:
            raise S3StorageError(f"Failed to upload {key!r} to bucket {self.bucket!r}") from e

        size = head_response["ContentLength"]
        logger.info("Uploaded %r (%d bytes)", key, size)

        return UploadS3FileResult(key=key, size=size)

    def get_file(
        self, project_uuid: UUID, filename: str, destination: IO[bytes]
    ) -> GetS3FileResult:
        key = f"{project_uuid}/{filename}"

        try:
            self.client.download_fileobj(self.bucket, key, destination)
            head_response = self.client.head_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError, S3TransferFailedError) as e:
            raise S3StorageError(f"Failed to download {key!r} from bucket {self.bucket!r}") from e

        size = head_response["ContentLength"]
        logger.info("Downloaded %r (%d bytes)", key, size)

        return GetS3FileResult(key=key, size=size, last_modified=head_response["LastModified"])

    def ensure_bucket_exists(self) -> None:
        """Called once at app startup (see create_app()) — CRUD methods assume
        the bucket already exists and let a missing one surface as a normal
        S3StorageError, the same as any other storage failure."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            if e.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
                raise S3StorageError(f"Failed to check bucket {self.bucket!r}") from e
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except (ClientError, BotoCoreError) as e:
                raise S3StorageError(f"Failed to create bucket {self.bucket!r}") from e
        except BotoCoreError as e:
            raise S3StorageError(f"Failed to check bucket {self.bucket!r}") from e
