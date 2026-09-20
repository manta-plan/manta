# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

import pytest

from blocks.tests.fakes import (
    FakeAddsClustered,
    FakeNeedsUpstream,
    FakePassthrough,
    FakeRemovesInvestmentPeriod,
    FakeRequiresInvestmentPeriod,
)
from playbooks.playbook import Playbook
from playbooks.validation import PlaybookValidationError


def test_nested_playbook_unbound_inputs_are_namespaced():
    child = Playbook(name="child")
    child.add("inner_cluster", FakeAddsClustered)
    child.add("inner_dispatch", FakeNeedsUpstream)
    assert child.unbound_inputs() == {"inner_dispatch.source"}


def test_wiring_a_declared_unbound_input_has_no_issues():
    child = Playbook(name="child")
    child.add("inner_dispatch", FakeNeedsUpstream)

    outer = Playbook(name="outer")
    a = outer.add("upstream", FakePassthrough)
    outer.add_playbook("regional", child, inputs={"inner_dispatch.source": a.output})
    outer.validate_playbook(config={"upstream": {}, "regional": {"inner_dispatch": {}}})


def test_wiring_an_undeclared_nested_input_is_reported():
    child = Playbook(name="child")
    child.add("inner_dispatch", FakeNeedsUpstream)

    outer = Playbook(name="outer")
    a = outer.add("upstream", FakePassthrough)
    outer.add_playbook("regional", child, inputs={"not_a_real_input": a.output})

    with pytest.raises(PlaybookValidationError) as exc:
        outer.validate_playbook()
    assert any(
        i.kind == "ref" and "no input called" in i.message for i in exc.value.issues
    )


def test_a_nested_issue_names_the_step_it_came_from():
    child = Playbook(name="child")
    child.add("dup", FakePassthrough)
    child.add("dup", FakePassthrough)  # duplicate step name

    outer = Playbook(name="outer")
    outer.add_playbook("regional", child)

    with pytest.raises(PlaybookValidationError) as exc:
        outer.validate_playbook(config={"regional": {}})
    issue = next(i for i in exc.value.issues if i.kind == "structure")
    assert issue.path == ("regional", "dup")
    assert issue.step == "regional/dup"


def test_nested_dims_fold_into_a_single_net_effect():
    child = Playbook(name="child", initial_dims=frozenset({"investment_period"}))
    child.add("collapse", FakeRemovesInvestmentPeriod)

    outer = Playbook(name="outer", initial_dims=frozenset({"investment_period"}))
    outer.add_playbook("regional", child)
    outer.add("needs_it", FakeRequiresInvestmentPeriod)

    with pytest.raises(PlaybookValidationError) as exc:
        outer.validate_playbook(config={"regional": {}, "needs_it": {}})
    dims_issues = [i for i in exc.value.issues if i.kind == "dims"]
    assert len(dims_issues) == 1
    assert dims_issues[0].step == "needs_it"


def test_a_nested_playbooks_own_requirement_is_reported_at_its_step():
    # The child says it needs `investment_period` before it starts. If the outer
    # playbook has not got it, that belongs to the step that nests the child, not to
    # something deep inside it.
    child = Playbook(name="child", initial_dims=frozenset({"investment_period"}))
    child.add("needs_it", FakeRequiresInvestmentPeriod)

    outer = Playbook(name="outer")  # nothing to start from
    outer.add_playbook("regional", child)

    with pytest.raises(PlaybookValidationError) as exc:
        outer.validate_playbook(config={"regional": {"needs_it": {}}})
    dims_issues = [i for i in exc.value.issues if i.kind == "dims"]
    assert any(i.step == "regional" for i in dims_issues)


def test_a_playbook_that_contains_itself_is_reported_not_hung():
    a = Playbook(name="a")
    a.add_playbook("loop", a)

    with pytest.raises(PlaybookValidationError) as exc:
        a.validate_playbook()
    assert any(
        i.kind == "structure" and "circular" in i.message for i in exc.value.issues
    )


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
    result = outer.run(initial_record, config, output_prefix="out")
    assert result.url == "root+before+inner+after"
