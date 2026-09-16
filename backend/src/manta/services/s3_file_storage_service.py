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


class S3FileNotFoundError(S3StorageError):
    """A requested source object does not exist, as opposed to storage failing."""


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

    def copy_file(
        self, source_key: str, project_uuid: UUID, dest_filename: str
    ) -> UploadS3FileResult:
        """Copy an existing object to `{project_uuid}/{dest_filename}`.

        The source is any key in the app bucket (it need not belong to the project);
        the destination always lands under the project's prefix. A missing source is
        the caller's mistake and raised apart from storage failures.
        """
        dest_key = f"{project_uuid}/{dest_filename}"

        try:
            head_response = self.client.head_object(Bucket=self.bucket, Key=source_key)
        except ClientError as e:
            if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                raise S3FileNotFoundError(
                    f"Source {source_key!r} does not exist in bucket {self.bucket!r}"
                ) from e
            raise S3StorageError(f"Failed to check {source_key!r} in bucket {self.bucket!r}") from e
        except BotoCoreError as e:
            raise S3StorageError(f"Failed to check {source_key!r} in bucket {self.bucket!r}") from e

        try:
            self.client.copy_object(
                Bucket=self.bucket,
                Key=dest_key,
                CopySource={"Bucket": self.bucket, "Key": source_key},
            )
        except (ClientError, BotoCoreError) as e:
            raise S3StorageError(
                f"Failed to copy {source_key!r} to {dest_key!r} in bucket {self.bucket!r}"
            ) from e

        size = head_response["ContentLength"]
        logger.info("Copied %r to %r (%d bytes)", source_key, dest_key, size)

        return UploadS3FileResult(key=dest_key, size=size)

    def list_files(self, project_uuid: UUID, prefix: str = "") -> list[GetS3FileResult]:
        # TODO: only lists everything under the project's prefix (optionally
        # narrowed by `prefix` inside it) for now — extend with args for
        # filtering by file type or other business logic once there's a
        # concrete need.
        prefix = f"{project_uuid}/{prefix}"

        try:
            paginator = self.client.get_paginator("list_objects_v2")
            objects = [
                obj
                for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix)
                for obj in page.get("Contents", [])
            ]
        except (ClientError, BotoCoreError) as e:
            raise S3StorageError(f"Failed to list {prefix!r} in bucket {self.bucket!r}") from e

        logger.info("Listed %d file(s) under %r", len(objects), prefix)

        return [
            GetS3FileResult(key=obj["Key"], size=obj["Size"], last_modified=obj["LastModified"])
            for obj in objects
        ]

    def delete_file(self, project_uuid: UUID, filename: str) -> None:
        # TODO: deleting a key that doesn't exist succeeds silently (S3's own
        # convention — delete is idempotent) — revisit if callers need to
        # distinguish "deleted" from "was already gone".
        key = f"{project_uuid}/{filename}"

        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as e:
            raise S3StorageError(f"Failed to delete {key!r} from bucket {self.bucket!r}") from e

        logger.info("Deleted %r", key)

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
