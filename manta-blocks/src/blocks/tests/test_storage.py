# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

"""Records turned into local files and back.

Only the local side and the URL handling run here; moving real bytes through S3 is
covered by Manta's integration tests, where an S3 service actually exists.
"""

import pytest

from blocks import storage
from blocks.core import DataRecord


def test_an_s3_url_splits_into_bucket_and_key():
    assert storage.split_s3_url("s3://manta/proj/runs/1/input.nc") == (
        "manta",
        "proj/runs/1/input.nc",
    )


@pytest.mark.parametrize(
    "url", ["not-a-url", "s3://only-bucket", "s3:///no-bucket", "http://manta/key"]
)
def test_anything_else_is_refused_as_an_s3_url(url):
    with pytest.raises(storage.StorageError):
        storage.split_s3_url(url)


def test_a_local_record_is_handed_through_without_copying(tmp_path):
    source = tmp_path / "data.nc"
    source.write_bytes(b"bytes")

    with storage.local_copy(DataRecord(url=str(source))) as path:
        assert path == source


def test_writing_a_local_target_creates_the_directories_on_the_way(tmp_path):
    url = str(tmp_path / "runs" / "1" / "cluster.nc")

    with storage.local_target(url) as path:
        path.write_bytes(b"result")

    assert (tmp_path / "runs" / "1" / "cluster.nc").read_bytes() == b"result"


def test_text_documents_round_trip_locally(tmp_path):
    url = str(tmp_path / "meta" / "step.result.json")
    storage.put_text(url, '{"url": "somewhere"}')
    assert storage.get_text(url) == '{"url": "somewhere"}'


def test_reading_a_missing_document_says_so(tmp_path):
    with pytest.raises(storage.StorageError):
        storage.get_text(str(tmp_path / "not-there.json"))
