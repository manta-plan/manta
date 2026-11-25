# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A playbook used as a single step inside a longer one.

The outer playbook sets the inner one's inputs with `with`, or promotes those it leaves
unset to inputs of its own with `inputs: inherit`.
"""

import pytest

from playbook.blocks.tests.fakes import steps
from playbook.playbooks.inputs import effective_inputs
from playbook.playbooks.issues import PlaybookHasIssuesError
from playbook.playbooks.playbook import PlaybookStep

CHILD = {
    "name": "child",
    "inputs": {
        "label": {"type": "string", "default": "inner"},
        "on": {"type": "boolean", "default": True},
    },
    "steps": [
        {
            "id": "inner",
            "block": "fake_passthrough",
            "if": "${{ inputs.on }}",
            "with": {"label": "${{ inputs.label }}"},
        }
    ],
}


def nesting(**step: object) -> dict:
    return {
        "name": "outer",
        "steps": [
            {"id": "before", "block": "fake_passthrough", "with": {"label": "before"}},
            {"id": "nested", "playbook": CHILD, **step},
            {"id": "after", "block": "fake_passthrough", "with": {"label": "after"}},
        ],
    }


def test_a_nested_playbook_runs_within_the_outer_run(build_playbook, initial_revision):
    result = build_playbook(nesting()).run(initial_revision, {})
    assert steps(result) == ["before", "inner", "after"]


def test_with_sets_the_inputs_of_a_nested_playbook(build_playbook, initial_revision):
    pb = build_playbook(nesting(**{"with": {"label": "set"}}))
    assert steps(pb.run(initial_revision, {})) == ["before", "set", "after"]


def test_without_inherit_a_nested_playbook_adds_no_inputs(build_playbook):
    assert effective_inputs(build_playbook(nesting())) == {}


def test_inherit_promotes_the_inputs_a_nested_playbook_leaves_unset(
    build_playbook, initial_revision
):
    pb = build_playbook(nesting(inputs="inherit", **{"with": {"label": "set"}}))
    assert list(effective_inputs(pb)) == ["on"]
    assert steps(pb.run(initial_revision, {"on": False})) == ["before", "after"]


def test_expand_and_dispatch_inherits_the_inputs_of_the_capacity_expansion_it_nests(
    expand_and_dispatch,
):
    assert list(effective_inputs(expand_and_dispatch)) == [
        "dispatch_resolution",
        "snapshot",
        "bus",
        "resolution",
        "expansion_method",
        "solver",
    ]


def test_an_inherited_input_clashing_with_one_of_the_playbook_is_refused(build_playbook):
    doc = {**nesting(inputs="inherit"), "inputs": {"on": {"type": "boolean", "default": False}}}
    with pytest.raises(PlaybookHasIssuesError) as raised:
        effective_inputs(build_playbook(doc))
    [issue] = raised.value.issues
    assert (issue.kind, issue.step_path, issue.input_path) == ("structure", ("nested",), ("on",))


@pytest.mark.parametrize("inputs", [None, {}])
def test_a_nested_issue_names_the_step_it_came_from(build_playbook, inputs):
    child = {**CHILD, "steps": [*CHILD["steps"], *CHILD["steps"]]}
    pb = build_playbook({"name": "outer", "steps": [{"id": "regional", "playbook": child}]})
    assert [(i.kind, i.step_path) for i in pb.find_issues(inputs)] == [
        ("structure", ("regional", "inner"))
    ]


def test_a_nested_steps_settings_are_addressed_by_its_path(build_playbook):
    child = {"name": "child", "steps": [{"id": "strict", "block": "fake_strict_config"}]}
    pb = build_playbook({"name": "outer", "steps": [{"id": "regional", "playbook": child}]})
    [issue] = pb.find_issues({})
    assert (issue.step_path, issue.setting_path) == (("regional", "strict"), ("required_field",))


@pytest.mark.parametrize("inputs", [None, {}])
def test_a_playbook_that_contains_itself_is_reported_not_hung(build_playbook, inputs):
    pb = build_playbook({"name": "a", "steps": [{"id": "leaf", "block": "fake_passthrough"}]})
    pb.steps.append(PlaybookStep(id="loop", playbook=pb))
    [issue] = pb.find_issues(inputs)
    assert (issue.kind, issue.step_path) == ("structure", ("loop",))
    assert "never finish" in issue.message
