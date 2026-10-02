import logging
from collections.abc import Iterator
from typing import IO
from uuid import UUID

from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError
from botocore.response import StreamingBody
from fastapi import Depends
from mypy_boto3_s3.client import S3Client

from manta.config.s3_config import get_s3_client, s3_bucket_name
from manta.services.results.s3_file_result import (
    GetS3FileContentResult,
    GetS3FileResult,
    UploadS3FileResult,
)

logger = logging.getLogger(__name__)

_STREAM_CHUNK_SIZE = 1024 * 1024
"""How much of a file get_file() holds in memory at once while streaming it."""


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

    def get_file(self, project_uuid: UUID, filename: str) -> GetS3FileContentResult:
        """A file's metadata, plus its content as a stream.

        Only opening the file happens here, so a missing file or an unreachable S3
        fails straight away. The bytes themselves are only read as `content` is
        iterated, so a failure part-way through surfaces then instead.
        """
        key = f"{project_uuid}/{filename}"

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as e:
            raise S3StorageError(f"Failed to download {key!r} from bucket {self.bucket!r}") from e

        size = response["ContentLength"]
        logger.info("Streaming %r (%d bytes)", key, size)

        return GetS3FileContentResult(
            key=key,
            size=size,
            last_modified=response["LastModified"],
            content_type=response.get("ContentType", "application/octet-stream"),
            content=self._stream_body(key, response["Body"]),
        )

    def _stream_body(self, key: str, body: StreamingBody) -> Iterator[bytes]:
        try:
            yield from body.iter_chunks(_STREAM_CHUNK_SIZE)
        except (ClientError, BotoCoreError) as e:
            raise S3StorageError(f"Failed to download {key!r} from bucket {self.bucket!r}") from e
        finally:
            # Also reached when the caller stops early (e.g. a client hanging up
            # mid-download), so the S3 connection is always handed back.
            body.close()

    def list_files(self, project_uuid: UUID, prefix: str = "") -> list[GetS3FileResult]:
        """Every file under the project's own prefix, optionally narrowed to `prefix`
        within it, e.g. `runs/<run uuid>/output/`."""
        # TODO: extend with args for filtering by file type or other business
        # logic once there's a concrete need.
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
