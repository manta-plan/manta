# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pytest

from playbook.blocks.tests.fakes import steps
from playbook.playbooks.tests.specs import SPEC_REQUIRED_INPUTS


def labelled(*labels: str, **step: object) -> list[dict]:
    return [
        {"id": f"step{index}", "block": "fake_passthrough", "with": {"label": label}, **step}
        for index, label in enumerate(labels)
    ]


def test_settings_reach_the_block_that_needs_them(build_playbook, initial_revision):
    pb = build_playbook({"name": "p", "steps": labelled("one", "two")})
    assert steps(pb.run(initial_revision, {})) == ["one", "two"]


@pytest.mark.parametrize(("mode", "label"), [("a", "A"), ("b", "B")])
def test_only_the_step_the_inputs_pick_runs(build_playbook, initial_revision, mode, label):
    pb = build_playbook(
        {
            "name": "p",
            "inputs": {"mode": {"type": "choice", "options": ["a", "b"], "default": "a"}},
            "steps": [
                {**labelled("A")[0], "id": "a", "if": "${{ inputs.mode == 'a' }}"},
                {**labelled("B")[0], "id": "b", "if": "${{ inputs.mode == 'b' }}"},
            ],
        }
    )
    assert steps(pb.run(initial_revision, {"mode": mode})) == [label]


def test_an_input_reaches_a_blocks_setting(build_playbook, initial_revision):
    pb = build_playbook(
        {
            "name": "p",
            "inputs": {"label": {"type": "string", "default": "x"}},
            "steps": labelled("${{ inputs.label }}"),
        }
    )
    assert steps(pb.run(initial_revision, {"label": "given"})) == ["given"]


def test_a_step_that_does_not_run_passes_the_revision_straight_on(build_playbook, initial_revision):
    pb = build_playbook({"name": "p", "steps": labelled("never", **{"if": "${{ false }}"})})
    assert pb.run(initial_revision, {}) == initial_revision


def test_the_same_playbook_can_be_run_more_than_once(build_playbook, initial_revision):
    pb = build_playbook({"name": "p", "steps": labelled("a")})
    first, second = (pb.run(initial_revision, {}) for _ in range(2))
    assert steps(first) == steps(second) == ["a"]
    assert first != second


def test_a_steps_result_is_a_new_revision_in_its_inputs_store(build_playbook, initial_revision):
    result = build_playbook({"name": "p", "steps": labelled("a")}).run(initial_revision, {})
    assert result.store == initial_revision.store
    assert result.id != initial_revision.id


def test_a_failing_step_stops_the_run(build_playbook, initial_revision):
    pb = build_playbook({"name": "p", "steps": [{"id": "boom", "block": "fake_explodes"}]})
    with pytest.raises(AssertionError, match="never have been run"):
        pb.run(initial_revision, {})


def test_the_capacity_expansion_playbook_runs_its_steps_in_turn(
    capacity_expansion, recording_runner, initial_revision
):
    result = capacity_expansion.run(
        initial_revision, {"snapshot": "resampled", "bus": "busmap_country"}, recording_runner
    )

    partition, expand = recording_runner.calls
    assert partition["config"] == {
        "method": "resample",
        "resolution": "3h",
        "property": "resampled",
    }
    assert expand["revision"].store == f"{initial_revision.store}/partition"
    assert expand["config"]["aggregation"] == {"snapshot": "resampled", "bus": "busmap_country"}
    assert result.store == f"{initial_revision.store}/partition/expand"


@pytest.mark.parametrize(("name", "inputs"), SPEC_REQUIRED_INPUTS.items())
def test_the_partition_is_skipped_without_a_snapshot_property(
    request, name, inputs, recording_runner, initial_revision
):
    request.getfixturevalue(name).run(initial_revision, inputs, recording_runner)
    [expand] = [call for call in recording_runner.calls if call["step_path"][-1] == "expand"]
    assert expand["revision"] == initial_revision
