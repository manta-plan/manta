# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""The small files a store coordinates through, local or remote.

Tables go through DuckDB; everything else - the manifest, the revision files,
listing them, whether a layer exists - goes through a `Files`, picked by the
URI's scheme.

Notes
-----
- [files, local and remote](https://energy-models.github.io/datarecord/design/layers/#files-local-and-remote)
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NewType, Protocol

Version = NewType("Version", str)
"""What an object's content was when read: a local SHA-256, a remote ETag."""


class Absent:
    """The precondition that nothing is at the URI yet: a create-only write."""


class PreconditionFailedError(Exception):
    """A conditional write found the object other than `expect` said."""


class Files(Protocol):
    """Reading, writing and listing small files under one kind of URI.

    Notes
    -----
    - [files, local and remote](https://energy-models.github.io/datarecord/design/layers/#files-local-and-remote)
    """

    def read_text(self, uri: str) -> tuple[str, Version] | None:
        """The text at `uri` and its version, or `None` on a miss."""
        ...

    def write_text(
        self, uri: str, text: str, *, expect: Version | Absent | None
    ) -> Version:
        """Write `text` to `uri`, if `expect` holds.

        Parameters
        ----------
        expect
            `Absent` writes only if nothing is there, a `Version` only if the
            object is unchanged since it was read at that version, `None`
            unconditionally.

        Raises
        ------
        PreconditionFailedError
            If `expect` does not hold.
        """
        ...

    def list(self, prefix: str) -> list[str]:
        """The names directly under `prefix`, empty where there is nothing."""
        ...

    def exists(self, uri: str) -> bool: ...


def _version(text: str) -> Version:
    return Version(hashlib.sha256(text.encode()).hexdigest())


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on `path`'s sibling `<name>.lock`."""
    with open(path.with_name(path.name + ".lock"), "a+") as fh:
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fh, fcntl.LOCK_EX)
        yield


class LocalFiles:
    """`Files` on the local filesystem.

    Every write lands under a temporary name and is renamed or linked into
    place, so a reader sees a whole file or none.
    """

    def read_text(self, uri: str) -> tuple[str, Version] | None:
        try:
            text = Path(uri).read_text()
        except FileNotFoundError:
            return None
        return text, _version(text)

    def write_text(
        self, uri: str, text: str, *, expect: Version | Absent | None
    ) -> Version:
        path = Path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(text)
            if isinstance(expect, Absent):
                try:
                    os.link(tmp, path)
                except FileExistsError:
                    msg = f"{uri} already exists"
                    raise PreconditionFailedError(msg) from None
            elif expect is None:
                os.replace(tmp, path)
            else:
                with _locked(path):
                    current = self.read_text(uri)
                    if current is None or current[1] != expect:
                        msg = f"{uri} changed since it was read"
                        raise PreconditionFailedError(msg)
                    os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)
        return _version(text)

    def list(self, prefix: str) -> list[str]:
        path = Path(prefix)
        if not path.is_dir():
            return []
        return [p.name for p in path.iterdir()]

    def exists(self, uri: str) -> bool:
        return Path(uri).exists()


def _split(uri: str) -> tuple[str, str]:
    """`s3://bucket/key` as `(bucket, key)`."""
    bucket, _, key = uri.removeprefix("s3://").partition("/")
    return bucket, key


class RemoteFiles:
    """`Files` on S3, through boto3, configured by the AWS environment alone.

    `expect` maps to `put_object`'s conditional headers, `IfNoneMatch="*"` for
    `Absent` and `IfMatch` for a `Version`, which is the object's ETag. They
    hold only as far as the server honours them.

    Raises
    ------
    ImportError
        If boto3 is not installed: it comes with `datarecord[remote]`.

    Notes
    -----
    - [files, local and remote](https://energy-models.github.io/datarecord/design/layers/#files-local-and-remote)
    """

    def __init__(self) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            msg = (
                "an s3:// URI needs boto3; install it with "
                "`pip install datarecord[remote]`"
            )
            raise ImportError(msg) from e
        # A self-hosted endpoint (SeaweedFS, MinIO) has no bucket-subdomain DNS.
        style = "path" if os.environ.get("AWS_ENDPOINT_URL") else "auto"
        self._s3 = boto3.client("s3", config=Config(s3={"addressing_style": style}))
        self._error = self._s3.exceptions.ClientError

    @staticmethod
    def _status(e: Any) -> int:
        return e.response["ResponseMetadata"]["HTTPStatusCode"]

    def read_text(self, uri: str) -> tuple[str, Version] | None:
        bucket, key = _split(uri)
        try:
            got = self._s3.get_object(Bucket=bucket, Key=key)
        except self._error as e:
            # 403 too: S3 answers a missing key so without ListBucket.
            if self._status(e) in (403, 404):
                return None
            raise
        return got["Body"].read().decode(), Version(got["ETag"])

    def write_text(
        self, uri: str, text: str, *, expect: Version | Absent | None
    ) -> Version:
        bucket, key = _split(uri)
        condition: dict[str, str] = {}
        if isinstance(expect, Absent):
            condition["IfNoneMatch"] = "*"
        elif expect is not None:
            condition["IfMatch"] = expect
        try:
            put = self._s3.put_object(
                Bucket=bucket, Key=key, Body=text.encode(), **condition
            )
        except self._error as e:
            # 409 is a conditional write racing another on the same key.
            if self._status(e) in (409, 412):
                msg = f"{uri} is not as `expect` said: {e}"
                raise PreconditionFailedError(msg) from e
            raise
        return Version(put["ETag"])

    def list(self, prefix: str) -> list[str]:
        bucket, key = _split(prefix)
        if key and not key.endswith("/"):
            key += "/"
        names = []
        pages = self._s3.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=key, Delimiter="/"
        )
        for page in pages:
            names += [o["Key"][len(key) :] for o in page.get("Contents", [])]
            names += [
                p["Prefix"][len(key) :].rstrip("/")
                for p in page.get("CommonPrefixes", [])
            ]
        return [n for n in names if n]

    def exists(self, uri: str) -> bool:
        """An object at `uri`, or any under it, as a local directory exists."""
        bucket, key = _split(uri)
        try:
            self._s3.head_object(Bucket=bucket, Key=key)
            return True
        except self._error as e:
            if self._status(e) not in (403, 404):
                raise
        listed = self._s3.list_objects_v2(
            Bucket=bucket, Prefix=key.rstrip("/") + "/", MaxKeys=1
        )
        return listed.get("KeyCount", 0) > 0
