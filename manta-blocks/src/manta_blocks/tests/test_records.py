# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

import pytest

from manta_blocks.records import (
    RecordStorageError,
    is_s3_url,
    parse_s3_url,
    sibling_url,
    stage,
    stage_output,
)


def test_a_plain_path_is_not_an_s3_url():
    assert not is_s3_url("/data/start.nc")
    assert not is_s3_url("relative/start.nc")


def test_an_s3_url_is_recognised_and_split():
    assert is_s3_url("s3://manta/runs/1/start.nc")
    assert parse_s3_url("s3://manta/runs/1/start.nc") == ("manta", "runs/1/start.nc")


@pytest.mark.parametrize(
    "url", ["s3://only-a-bucket", "s3:///only/a/key", "http://x/y"]
)
def test_an_incomplete_s3_url_is_refused(url):
    with pytest.raises(RecordStorageError):
        parse_s3_url(url)


def test_sibling_url_names_the_output_after_its_source_locally():
    assert sibling_url("/data/start.nc", "cluster") == "/data/start-cluster.nc"


def test_sibling_url_keeps_an_s3_output_under_the_same_prefix():
    assert (
        sibling_url("s3://manta/runs/1/start.nc", "cluster")
        == "s3://manta/runs/1/start-cluster.nc"
    )


def test_staging_a_local_url_hands_the_path_over(tmp_path):
    source = tmp_path / "start.nc"
    source.write_text("data")

    with stage(str(source)) as local_path:
        assert local_path == source
        assert local_path.read_text() == "data"


def test_staging_a_local_output_writes_in_place(tmp_path):
    target = tmp_path / "result.nc"

    with stage_output(str(target)) as local_path:
        local_path.write_text("result")

    assert target.read_text() == "result"


def test_an_s3_output_that_was_never_written_is_an_error():
    # The upload is skipped by failing before it: nothing was written, which has to
    # be reported rather than silently publishing nothing.
    with pytest.raises(RecordStorageError, match="nothing was written"):
        with stage_output("s3://manta/runs/1/result.nc"):
            pass
