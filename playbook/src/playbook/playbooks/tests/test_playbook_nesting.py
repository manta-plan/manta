# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""A playbook used as a single step inside a longer one.

The inner playbook keeps its own settings and its own step names; what it does not
wire up itself is offered to the outer playbook to feed, exactly like a block's own
inputs.
"""

import pytest
from pydantic import ValidationError

from playbook.blocks.tests.fakes import (
    FakeAddsClustered,
    FakeNeedsUpstream,
    FakePassthrough,
    FakeRemovesPeriod,
    FakeRequiresPeriod,
    FakeStrictConfig,
    RecordingRunner,
)
from playbook.playbooks.execution import execute_playbook
from playbook.playbooks.playbook import Playbook, When
from playbook.playbooks.validation import PlaybookHasIssuesError
from playbook.playbooks.yaml_io import StepDoc


def test_nested_playbook_unbound_inputs_are_namespaced():
    child = Playbook(name="child")
    child.add("inner_cluster", FakeAddsClustered)
    child.add("inner_dispatch", FakeNeedsUpstream)
    assert child.unbound_inputs() == {"inner_dispatch.source"}


def test_an_input_the_inner_playbook_wires_itself_is_not_asked_of_the_outer_one():
    child = Playbook(name="child")
    upstream = child.add("inner_cluster", FakePassthrough)
    child.add("inner_dispatch", FakeNeedsUpstream, inputs={"source": upstream.output})
    assert child.unbound_inputs() == frozenset()


def test_wiring_a_declared_unbound_input_has_no_issues():
    child = Playbook(name="child")
    child.add("inner_dispatch", FakeNeedsUpstream)

    outer = Playbook(name="outer")
    a = outer.add("upstream", FakePassthrough)
    outer.add_playbook("regional", child, inputs={"inner_dispatch.source": a.output})
    outer.raise_for_issues(config={"upstream": {}, "regional": {"inner_dispatch": {}}})


def test_wiring_an_undeclared_nested_input_is_reported():
    child = Playbook(name="child")
    child.add("inner_dispatch", FakeNeedsUpstream)

    outer = Playbook(name="outer")
    a = outer.add("upstream", FakePassthrough)
    outer.add_playbook("regional", child, inputs={"not_a_real_input": a.output})

    with pytest.raises(PlaybookHasIssuesError) as exc:
        outer.raise_for_issues()
    assert any(i.kind == "wiring" and "no input called" in i.message for i in exc.value.issues)


def test_a_nested_issue_names_the_step_it_came_from():
    child = Playbook(name="child")
    child.add("dup", FakePassthrough)
    child.add("dup", FakePassthrough)  # duplicate step name

    outer = Playbook(name="outer")
    outer.add_playbook("regional", child)

    # Found without any settings, since it does not depend on them - and only once
    # when there are some.
    for config in (None, {"regional": {}}):
        issues = outer.find_issues(config)
        assert [(i.kind, i.step_path) for i in issues] == [("structure", ("regional", "dup"))]


def test_a_nested_steps_settings_are_addressed_from_the_top_of_the_settings():
    child = Playbook(name="child")
    child.add("strict", FakeStrictConfig)

    outer = Playbook(name="outer")
    outer.add_playbook("regional", child)

    issues = outer.find_issues(config={"regional": {"strict": {}, "not_a_step": {}}})
    assert [(i.step_path, i.config_path) for i in issues] == [
        (("regional",), ("regional", "not_a_step")),
        (("regional", "strict"), ("regional", "strict", "required_field")),
    ]


def test_nested_dims_fold_into_a_single_net_effect():
    child = Playbook(name="child", initial_dims=frozenset({"period"}))
    child.add("collapse", FakeRemovesPeriod)

    outer = Playbook(name="outer", initial_dims=frozenset({"period"}))
    outer.add_playbook("regional", child)
    outer.add("needs_it", FakeRequiresPeriod)

    with pytest.raises(PlaybookHasIssuesError) as exc:
        outer.raise_for_issues(config={"regional": {}, "needs_it": {}})
    dims_issues = [i for i in exc.value.issues if i.kind == "dims"]
    assert len(dims_issues) == 1
    assert dims_issues[0].step_path == ("needs_it",)
    assert "step 'regional' removed it" in dims_issues[0].message


def test_a_nested_playbooks_own_requirement_is_reported_at_its_step():
    # The child says it needs `period` before it starts. If the outer
    # playbook has not got it, that belongs to the step that nests the child, not to
    # something deep inside it.
    child = Playbook(name="child", initial_dims=frozenset({"period"}))
    child.add("needs_it", FakeRequiresPeriod)

    outer = Playbook(name="outer")  # nothing to start from
    outer.add_playbook("regional", child)

    with pytest.raises(PlaybookHasIssuesError) as exc:
        outer.raise_for_issues(config={"regional": {"needs_it": {}}})
    dims_issues = [i for i in exc.value.issues if i.kind == "dims"]
    assert [i.step_path for i in dims_issues] == [("regional",)]


def test_a_playbook_that_contains_itself_is_reported_not_hung():
    a = Playbook(name="a")
    a.add_playbook("loop", a)

    # With settings too: those checks walk into nested playbooks, and must not
    # follow this one round forever.
    for config in (None, {"loop": {}}):
        issues = a.find_issues(config)
        assert len(issues) == 1
        assert issues[0].kind == "structure"
        assert "never finish" in issues[0].message


def test_a_nested_playbook_executes_within_the_outer_run(initial_record):
    child = Playbook(name="child")
    child.add("inner", FakePassthrough)

    outer = Playbook(name="outer")
    outer.add("before", FakePassthrough)
    outer.add_playbook("nested", child)
    outer.add("after", FakePassthrough)

    config = {
        "before": {"label": "before"},
        "nested": {"inner": {"label": "inner"}},
        "after": {"label": "after"},
    }
    result = outer.run(initial_record, config)
    assert result.url == "root+before+inner+after"


def test_a_nested_playbook_inherits_the_outer_globals(initial_record):
    # Shared settings do not have to be repeated at every level, so a condition
    # inside a nested playbook can read a global the outer playbook set.
    child = Playbook(name="child")
    child.add("inner", FakePassthrough, when=When(config="globals.mode", equals="on"))

    outer = Playbook(name="outer")
    outer.add_playbook("nested", child)

    on = {"globals": {"mode": "on"}, "nested": {"inner": {"label": "inner"}}}
    assert outer.run(initial_record, on).url == "root+inner"

    off = {"globals": {"mode": "off"}, "nested": {"inner": {"label": "inner"}}}
    assert outer.run(initial_record, off).url == "root"


def test_a_nested_playbook_can_have_globals_of_its_own(initial_record):
    child = Playbook(name="child")
    child.add("inner", FakePassthrough, when=When(config="globals.mode", equals="on"))

    outer = Playbook(name="outer")
    outer.add_playbook("nested", child)

    config = {
        "globals": {"mode": "off"},
        "nested": {"globals": {"mode": "on"}, "inner": {"label": "inner"}},
    }
    assert outer.run(initial_record, config).url == "root+inner"


def test_nested_steps_reach_the_runner_by_their_qualified_path(initial_record):
    inner = Playbook(name="inner")
    inner.add("leaf", FakePassthrough)
    middle = Playbook(name="middle")
    middle.add_playbook("region", inner)
    middle.add("cluster", FakePassthrough)
    outer = Playbook(name="outer")
    outer.add("before", FakePassthrough)
    outer.add_playbook("stage_2030", middle)

    runner = RecordingRunner()
    execute_playbook(outer, initial_record, {}, runner=runner)

    assert [call["step_name"] for call in runner.calls] == [
        "before",
        "stage_2030/region/leaf",
        "stage_2030/cluster",
    ]


@pytest.mark.parametrize(
    "add",
    [
        lambda: Playbook(name="p").add("a/b", FakePassthrough),
        lambda: Playbook(name="p").add_playbook("a/b", Playbook(name="child")),
        lambda: StepDoc(name="a/b", block="fake_passthrough"),
    ],
    ids=["block", "nested", "doc"],
)
def test_a_step_name_with_a_slash_is_rejected(add):
    with pytest.raises(ValidationError, match="name"):
        add()
