# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The single-block command line, which is all a block container ever runs.

The contract a driver relies on is pinned here: arguments in, a RESULT_MARKER
line out on success, an exception (non-zero exit) on failure, and the
parser/printer pair staying in step.
"""

import json

import pytest

import playbook.blocks.tests.fakes  # noqa: F401 - registers the fake blocks used by name
from playbook.blocks.core import DataRecord
from playbook.blocks.registry import BlockNotFoundError
from playbook.blocks.run_one import RESULT_MARKER, main, parse_result_line, result_line


def _result_from(capsys) -> DataRecord:
    lines = capsys.readouterr().out.splitlines()
    results = [record for record in map(parse_result_line, lines) if record is not None]
    assert len(results) == 1, f"expected exactly one result line in {lines}"
    return results[0]


def test_a_block_runs_and_reports_where_its_result_went(capsys):
    exit_code = main(
        [
            "fake_writes_output",
            "--record",
            json.dumps({"url": "root"}),
            "--output-base",
            "out/cluster",
        ]
    )

    assert exit_code == 0
    assert _result_from(capsys).url == "out/cluster.txt"


def test_config_and_wired_inputs_reach_the_block(capsys):
    main(
        [
            "fake_needs_upstream",
            "--record",
            json.dumps({"url": "root"}),
            "--output-base",
            "out/dispatch",
            "--config",
            json.dumps({"label": "ignored-by-this-fake"}),
            "--inputs",
            json.dumps({"source": {"url": "upstream"}}),
        ]
    )

    assert _result_from(capsys).url == "root+needs(upstream)"


def test_an_unknown_block_fails_rather_than_guessing():
    with pytest.raises(BlockNotFoundError):
        main(["no_such_block", "--record", "{}", "--output-base", "out/x"])


def test_a_wrongly_wired_input_is_refused_before_the_block_runs():
    # `label` is text; a record cannot go there. The container exits non-zero
    # instead of running the block against nonsense.
    with pytest.raises(Exception, match="label"):
        main(
            [
                "fake_passthrough",
                "--record",
                json.dumps({"url": "root"}),
                "--output-base",
                "out/x",
                "--inputs",
                json.dumps({"label": {"url": "not-allowed"}}),
            ]
        )


def test_a_block_library_is_loaded_before_its_block_is_looked_up(capsys):
    # The library holding a block is named on the command line (or in
    # MANTA_BLOCK_SOURCES); without that, nothing would have registered it.
    main(
        [
            "fake_writes_output",
            "--source",
            "playbook.blocks.tests.fakes",
            "--record",
            json.dumps({"url": "root"}),
            "--output-base",
            "out/cluster",
        ]
    )

    assert _result_from(capsys).url == "out/cluster.txt"


def test_an_unknown_block_library_is_reported_rather_than_ignored():
    with pytest.raises(ModuleNotFoundError):
        main(
            [
                "fake_writes_output",
                "--source",
                "not_a_real_library",
                "--record",
                json.dumps({"url": "root"}),
                "--output-base",
                "out/cluster",
            ]
        )


def test_the_result_line_round_trips_through_its_parser():
    record = DataRecord(url="s3://bucket/run/step.nc")
    assert parse_result_line(result_line(record)) == record


def test_ordinary_log_lines_are_not_mistaken_for_results():
    assert parse_result_line("INFO solving 24 snapshots") is None
    assert parse_result_line("") is None
    # Even a line that merely mentions the marker mid-sentence is not a result.
    assert parse_result_line(f"saw {RESULT_MARKER} somewhere") is None
