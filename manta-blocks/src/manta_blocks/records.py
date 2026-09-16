# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Reading and writing the data a record points at.

A record's url is either a local filesystem path or an `s3://bucket/key` url. Blocks
work on local files - model libraries read and write paths, not object stores - so
this module stages S3 data to a local file on the way in and publishes local files on
the way out. For a local url both directions are free: the path is simply handed over.

S3 access uses boto3's own configuration: credentials and endpoint come from the usual
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_ENDPOINT_URL` environment
variables (the last one is how a non-AWS store such as SeaweedFS or MinIO is pointed
at). boto3 itself is only needed - and only imported - when an s3 url actually turns
up, so everything else here works without it installed.
"""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

S3_SCHEME = "s3"


class RecordStorageError(Exception):
    """Raised when a record's data cannot be reached or written."""


def is_s3_url(url: str) -> bool:
    """Whether `url` points into object storage rather than the local filesystem."""
    return urlparse(url).scheme == S3_SCHEME


def parse_s3_url(url: str) -> tuple[str, str]:
    """The bucket and key an `s3://bucket/key` url points at."""
    parsed = urlparse(url)
    bucket, key = parsed.netloc, parsed.path.lstrip("/")
    if parsed.scheme != S3_SCHEME or not bucket or not key:
        raise RecordStorageError(
            f"{url!r} is not an s3://<bucket>/<key> url with both a bucket and a key"
        )
    return bucket, key


def sibling_url(url: str, label: str) -> str:
    """A url next to `url`, named after it plus `label`.

    This is the naming every block output uses: `runs/1/start.nc` plus `cluster`
    becomes `runs/1/start-cluster.nc`, so a chain of blocks leaves a readable trail
    and everything a run produced sits under one prefix.
    """
    if is_s3_url(url):
        bucket, key = parse_s3_url(url)
        path = PurePosixPath(key)
        return f"{S3_SCHEME}://{bucket}/{path.with_name(f'{path.stem}-{label}{path.suffix}')}"
    path = Path(url)
    return str(path.with_name(f"{path.stem}-{label}{path.suffix}"))


@lru_cache
def _s3_client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover - a packaging problem, not logic
        raise RecordStorageError(
            "This record lives in S3, which needs boto3 installed "
            "(`pip install manta-blocks[s3]`)"
        ) from exc

    # Path-style addressing (http://host/bucket/key) whenever a custom endpoint is
    # configured: virtual-hosted style needs bucket-subdomain DNS, which local stores
    # like SeaweedFS behind `localhost` or a compose hostname do not have.
    config = (
        Config(s3={"addressing_style": "path"})
        if os.environ.get("AWS_ENDPOINT_URL")
        else None
    )
    return boto3.client("s3", config=config)


@contextmanager
def stage(url: str) -> Iterator[Path]:
    """A local path holding the data at `url`, for as long as the `with` block lasts.

    A local url is handed over as-is. An s3 url is downloaded to a temporary file that
    is gone once the block is done with it - the record stays the one source of truth.
    """
    if not is_s3_url(url):
        yield Path(url)
        return

    bucket, key = parse_s3_url(url)
    with tempfile.TemporaryDirectory(prefix="manta-record-") as staging_dir:
        local_path = Path(staging_dir) / PurePosixPath(key).name
        try:
            _s3_client().download_file(bucket, key, str(local_path))
        except Exception as exc:
            raise RecordStorageError(f"could not fetch {url!r}: {exc}") from exc
        yield local_path


@contextmanager
def stage_output(url: str) -> Iterator[Path]:
    """A local path to write the data for `url` to; leaving the block publishes it.

    For a local url the file is written in place and there is nothing to publish. For
    an s3 url the block writes to a temporary file, which is uploaded when the `with`
    block ends without an error.
    """
    if not is_s3_url(url):
        yield Path(url)
        return

    bucket, key = parse_s3_url(url)
    with tempfile.TemporaryDirectory(prefix="manta-record-") as staging_dir:
        local_path = Path(staging_dir) / PurePosixPath(key).name
        yield local_path
        if not local_path.exists():
            raise RecordStorageError(
                f"nothing was written for {url!r}: expected a file at {local_path}"
            )
        try:
            _s3_client().upload_file(str(local_path), bucket, key)
        except Exception as exc:
            raise RecordStorageError(f"could not publish {url!r}: {exc}") from exc
