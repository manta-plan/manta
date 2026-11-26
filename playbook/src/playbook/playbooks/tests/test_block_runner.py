# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The seam between a playbook and whatever actually runs its blocks.

An orchestrator plugs in a `BlockRunner` and receives one fully spelled-out block
invocation at a time; nothing else about running a playbook changes. These tests drive
the executor with a recording runner, the way Manta's own runner is driven, so the
contract an orchestrator relies on is pinned down here.
"""

import pytest

from playbook.playbooks.execution import execute_playbook
from playbook.playbooks.issues import PlaybookHasIssuesError


def test_every_step_reaches_the_runner_with_everything_spelled_out(
    build_playbook, recording_runner, initial_revision
):
    pb = build_playbook(
        {
            "name": "p",
            "steps": [
                {"id": "first", "block": "fake_passthrough", "with": {"label": "c"}},
                {"id": "second", "block": "fake_passthrough"},
            ],
        }
    )

    result = execute_playbook(pb, initial_revision, {}, runner=recording_runner)

    first, second = recording_runner.calls
    assert first == {
        "block": "fake_passthrough",
        "step_path": ("first",),
        "config": {"label": "c"},
        "revision": initial_revision,
    }
    assert second["step_path"] == ("second",)
    assert second["revision"].store == f"{initial_revision.store}/first"
    assert result.store == f"{initial_revision.store}/first/second"


def test_a_nested_playbooks_step_is_addressed_through_the_step_nesting_it(
    spec_catalogue, build_playbook, recording_runner, initial_revision
):
    pb = build_playbook(
        {
            "name": "p",
            "initial_data": {"dims": ["snapshot"]},
            "steps": [
                {
                    "id": "plan",
                    "playbook": "capacity_expansion",
                    "with": {"snapshot": "resampled"},
                }
            ],
        },
        spec_catalogue,
    )
    execute_playbook(pb, initial_revision, {}, runner=recording_runner)
    assert [call["step_path"] for call in recording_runner.calls] == [
        ("plan", "partition"),
        ("plan", "expand"),
    ]


def test_a_playbook_with_issues_never_reaches_the_runner(
    build_playbook, recording_runner, initial_revision
):
    pb = build_playbook(
        {
            "name": "p",
            "steps": [
                {"id": "first", "block": "fake_passthrough"},
                {"id": "second", "block": "fake_strict_config"},
            ],
        }
    )
    with pytest.raises(PlaybookHasIssuesError, match="required_field"):
        execute_playbook(pb, initial_revision, {}, runner=recording_runner)
    assert recording_runner.calls == []
