# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Where a record's bytes live, and how blocks get at them.

A `DataRecord` only ever points at data: a local path, or an `s3://bucket/key`
address. Blocks work on local files, so this module turns a record into a local file
for the duration of a `with` block, and turns a freshly written local file back into
a record.

S3 access is configured entirely through the standard AWS environment variables
(`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL`, ...), so nothing
here is specific to any one deployment of Manta - the same block runs against real
S3, a local SeaweedFS/MinIO, or plain files.
"""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from playbook.blocks.core import DataRecord

S3_SCHEME = "s3"


class StorageError(Exception):
    """Raised when a record's bytes cannot be read or written."""


def is_s3_url(url: str) -> bool:
    return urlparse(url).scheme == S3_SCHEME


def split_s3_url(url: str) -> tuple[str, str]:
    """The `(bucket, key)` an `s3://bucket/key` URL points at."""
    parsed = urlparse(url)
    bucket, key = parsed.netloc, parsed.path.lstrip("/")
    if parsed.scheme != S3_SCHEME or not bucket or not key:
        raise StorageError(f"{url!r} is not an s3://bucket/key URL")
    return bucket, key


def _s3_client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover - a packaging mistake, not a code path
        raise StorageError(
            "This record lives in S3, which needs boto3. Install the `playbook` package with "
            "the `s3` extra."
        ) from exc

    endpoint = os.environ.get("AWS_ENDPOINT_URL")
    # Path-style addressing whenever a custom endpoint is set: S3-compatible stores
    # like SeaweedFS or MinIO have no bucket-subdomain DNS. Real AWS (no endpoint
    # override) keeps boto3's defaults.
    config = Config(s3={"addressing_style": "path"}) if endpoint else None
    return boto3.client("s3", endpoint_url=endpoint, config=config)


@contextmanager
def local_copy(record: DataRecord) -> Iterator[Path]:
    """A local path holding the record's bytes, for the duration of the context.

    A record that already points at a local file is handed through as-is; an S3
    record is downloaded into a temporary file that is cleaned up on exit.
    """
    if not is_s3_url(record.url):
        yield Path(record.url)
        return

    bucket, key = split_s3_url(record.url)
    suffix = Path(key).suffix
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"record{suffix}"
        try:
            _s3_client().download_file(bucket, key, str(path))
        except Exception as exc:
            raise StorageError(f"could not fetch record {record.url!r}: {exc}") from exc
        yield path


@contextmanager
def local_target(url: str) -> Iterator[Path]:
    """A local path to write to; the bytes land at `url` when the context closes.

    Writing to a local URL writes the file directly (creating parent directories);
    writing to an S3 URL stages the file in a temporary directory and uploads it on
    exit.
    """
    if not is_s3_url(url):
        path = Path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        yield path
        return

    bucket, key = split_s3_url(url)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(key).name
        yield path
        if not path.exists():
            raise StorageError(f"nothing was written for {url!r}")
        try:
            _s3_client().upload_file(str(path), bucket, key)
        except Exception as exc:
            raise StorageError(f"could not store record at {url!r}: {exc}") from exc


def put_text(url: str, text: str) -> None:
    """Write a small text document (e.g. a serialized record) at `url`."""
    if is_s3_url(url):
        bucket, key = split_s3_url(url)
        try:
            _s3_client().put_object(Bucket=bucket, Key=key, Body=text.encode("utf-8"))
        except Exception as exc:
            raise StorageError(f"could not write {url!r}: {exc}") from exc
        return
    path = Path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def get_text(url: str) -> str:
    """Read back a small text document written with `put_text`."""
    if is_s3_url(url):
        bucket, key = split_s3_url(url)
        try:
            return _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        except Exception as exc:
            raise StorageError(f"could not read {url!r}: {exc}") from exc
    try:
        return Path(url).read_text()
    except OSError as exc:
        raise StorageError(f"could not read {url!r}: {exc}") from exc
