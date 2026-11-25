# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The single-block command line, which is all a block container ever runs.

The contract a driver relies on is pinned here: arguments in, a RESULT_MARKER
line out on success, an exception (non-zero exit) on failure, and the
parser/printer pair staying in step.
"""

import json
from uuid import UUID

import pytest

from playbook.blocks.core import DataRecordError, RevisionRef
from playbook.blocks.registry import BlockNotRegisteredError
from playbook.blocks.run_one import RESULT_MARKER, main, parse_result_line, result_line
from playbook.blocks.tests.fakes import steps


def _result_from(capsys) -> RevisionRef:
    lines = capsys.readouterr().out.splitlines()
    results = [ref for ref in map(parse_result_line, lines) if ref is not None]
    assert len(results) == 1, f"expected exactly one result line in {lines}"
    return results[0]


@pytest.mark.parametrize("source", [[], ["--source", "playbook.blocks.tests.fakes"]])
def test_a_block_runs_and_reports_where_its_result_went(capsys, initial_revision, source):
    # The library holding a block can be named on the command line (or in
    # MANTA_BLOCK_SOURCES); either way it is loaded before the block is looked up.
    exit_code = main(
        [
            "fake_passthrough",
            *source,
            "--revision",
            json.dumps(initial_revision.to_dict()),
            "--config",
            json.dumps({"label": "ran"}),
        ]
    )

    assert exit_code == 0
    result = _result_from(capsys)
    assert result.store == initial_revision.store
    assert steps(result) == ["ran"]


def test_an_unknown_block_fails_rather_than_guessing():
    with pytest.raises(BlockNotRegisteredError):
        main(["no_such_block", "--revision", "{}"])


def test_an_unknown_block_library_is_reported_rather_than_ignored(initial_revision):
    with pytest.raises(ModuleNotFoundError):
        main(
            [
                "fake_passthrough",
                "--source",
                "not_a_real_library",
                "--revision",
                json.dumps(initial_revision.to_dict()),
            ]
        )


@pytest.mark.parametrize(
    ("suffix", "revision_id"),
    [("missing-store", None), ("", UUID(int=0))],
    ids=["missing-store", "missing-revision"],
)
def test_a_revision_pointing_at_nothing_raises_a_datarecord_error(
    initial_revision, suffix, revision_id
):
    ref = RevisionRef(store=initial_revision.store + suffix, id=revision_id or initial_revision.id)
    with pytest.raises(DataRecordError, match="No revision"):
        main(["fake_passthrough", "--revision", json.dumps(ref.to_dict())])


def test_the_result_line_round_trips_through_its_parser(initial_revision):
    assert parse_result_line(result_line(initial_revision)) == initial_revision


def test_ordinary_log_lines_are_not_mistaken_for_results():
    assert parse_result_line("INFO solving 24 snapshots") is None
    assert parse_result_line("") is None
    # Even a line that merely mentions the marker mid-sentence is not a result.
    assert parse_result_line(f"saw {RESULT_MARKER} somewhere") is None
