# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Merging the settings a run gives into the `with` of the steps of a playbook."""

from copy import deepcopy

import pytest

from playbook.playbooks.issues import PlaybookHasIssuesError
from playbook.playbooks.settings import apply_settings

DOC = {
    "name": "outer",
    "inputs": {"size": {"type": "number", "default": 1}},
    "steps": [
        {
            "id": "grouped",
            "block": "fake_nested_settings",
            "with": {"group": {"size": "${{ inputs.size }}"}},
        },
        {"id": "label", "block": "fake_passthrough"},
        {
            "id": "inner",
            "playbook": {"name": "child", "steps": [{"id": "leaf", "block": "fake_passthrough"}]},
        },
    ],
}
SETTINGS = {
    "grouped": {"group": {"extra": 2}, "other": [1]},
    "label": {"label": "x"},
    "inner": {"leaf": {"label": "y"}},
}


def test_settings_are_merged_into_with_and_written_out(build_playbook):
    applied = apply_settings(build_playbook(DOC), SETTINGS)
    written = applied.to_doc().model_dump(mode="json", by_alias=True, exclude_unset=True)
    grouped, label, inner = written["steps"]
    assert grouped["with"] == {"group": {"size": "${{ inputs.size }}", "extra": 2}, "other": [1]}
    assert label["with"] == {"label": "x"}
    assert inner["playbook"]["steps"][0]["with"] == {"label": "y"}


def test_applying_settings_leaves_the_playbook_and_the_settings_as_they_were(build_playbook):
    pb = build_playbook(DOC)
    settings = {"grouped": deepcopy(SETTINGS["grouped"])}
    grouped, label, _ = apply_settings(pb, settings).steps
    grouped.with_["other"].append(2)
    grouped.with_["group"]["size"] = 0
    label.with_["label"] = "z"
    assert pb == build_playbook(DOC)
    assert settings == {"grouped": SETTINGS["grouped"]}


@pytest.mark.parametrize(
    ("settings", "step_path", "setting_path", "message"),
    [
        ({"nope": {}}, (), ("nope",), "there is no step called 'nope'"),
        ({"inner": {"nope": {}}}, ("inner",), ("nope",), "there is no step called 'nope'"),
        ({"label": None}, ("label",), (), "not None"),
        ({"label": [1]}, ("label",), (), "not [1]"),
        ({"inner": None}, ("inner",), (), "not None"),
        (
            {"grouped": {"group": {"size": 3}}},
            ("grouped",),
            ("group", "size"),
            "sets this to '${{ inputs.size }}'",
        ),
        ({"grouped": {"group": None}}, ("grouped",), ("group",), "sets this to {"),
        ({"label": {"label": "${{ oops"}}, ("label",), ("label",), "contains an expression"),
        (
            {"inner": {"leaf": {"label": ["${{ inputs.size }}"]}}},
            ("inner", "leaf"),
            ("label", 0),
            "contains an expression",
        ),
    ],
)
def test_a_setting_that_cannot_be_applied_is_reported(
    build_playbook, settings, step_path, setting_path, message
):
    with pytest.raises(PlaybookHasIssuesError) as raised:
        apply_settings(build_playbook(DOC), settings)
    [issue] = raised.value.issues
    assert (issue.kind, issue.step_path, issue.setting_path) == ("config", step_path, setting_path)
    assert message in issue.message


def test_every_setting_that_cannot_be_applied_is_reported_at_once(build_playbook):
    with pytest.raises(PlaybookHasIssuesError) as raised:
        apply_settings(build_playbook(DOC), {"nope": {}, "label": None})
    assert [issue.step_path for issue in raised.value.issues] == [(), ("label",)]
