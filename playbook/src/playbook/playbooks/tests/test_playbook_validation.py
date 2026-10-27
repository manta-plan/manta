# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Checking a playbook, and the settings it is about to run with, before anything runs.

Settings are checked two ways: by the block's own settings model where the block can
be imported, and by its catalogue description where it cannot - the ordinary case for
anything driving playbooks from outside. Where both apply, they have to agree.
"""

import pytest

from playbook.blocks import BlockSpec, describe_block
from playbook.blocks.tests.fakes import (
    FakeAddsClustered,
    FakeNeedsUpstream,
    FakeNestedSettings,
    FakeOtherEnv,
    FakePassthrough,
    FakeRemovesInvestmentPeriod,
    FakeRequiresInvestmentPeriod,
    FakeStrictConfig,
)
from playbook.playbooks.playbook import Playbook, When
from playbook.playbooks.validation import PlaybookHasIssuesError, find_playbook_issues


def _issue_kinds(exc) -> set[str]:
    return {issue.kind for issue in exc.value.issues}


def _described(block) -> BlockSpec:
    """A block as a catalogue describes it: no class, as if it lived elsewhere."""
    return BlockSpec(describe_block(block).description)


IMPORTED_OR_DESCRIBED = pytest.mark.parametrize(
    "as_step_block", [lambda block: block, _described], ids=["imported", "described"]
)


def test_a_well_wired_playbook_has_no_issues():
    pb = Playbook(name="happy")
    pb.add("cluster", FakeAddsClustered)
    a = pb.add("expand", FakePassthrough)
    pb.add("dispatch", FakeNeedsUpstream, inputs={"source": a.output})
    pb.raise_for_issues()  # structure and wiring only, no settings given
    pb.raise_for_issues(config={})  # everything, still nothing wrong


def test_the_checks_that_need_no_settings_run_without_them():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    pb.add("a", FakePassthrough)  # duplicate name
    with pytest.raises(PlaybookHasIssuesError) as exc:
        pb.raise_for_issues()
    assert "structure" in _issue_kinds(exc)


def test_the_function_and_the_method_find_the_same_issues():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    pb.add("a", FakePassthrough)
    assert find_playbook_issues(pb, {}) == pb.find_issues({}) != []


def test_duplicate_step_names():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    pb.add("a", FakePassthrough)
    with pytest.raises(PlaybookHasIssuesError) as exc:
        pb.raise_for_issues()
    assert any(i.kind == "structure" and "duplicate" in i.message for i in exc.value.issues)


def test_a_step_cannot_be_called_globals():
    # Its settings would be filed under the same key as the settings every step sees.
    pb = Playbook(name="p")
    pb.add("globals", FakePassthrough)
    issues = pb.find_issues()
    assert [(i.kind, i.step_path) for i in issues] == [("structure", ("globals",))]


def test_a_step_fed_from_a_later_step_is_reported():
    pb = Playbook(name="p")
    pb.add("a", FakeNeedsUpstream, inputs={"source": {"step": "b", "output": "output"}})
    pb.add("b", FakePassthrough)
    with pytest.raises(PlaybookHasIssuesError) as exc:
        pb.raise_for_issues()
    assert any(i.kind == "wiring" and "does not come before" in i.message for i in exc.value.issues)


def test_a_step_fed_from_a_step_that_does_not_exist_is_reported():
    pb = Playbook(name="p")
    pb.add("a", FakeNeedsUpstream, inputs={"source": {"step": "nope", "output": "output"}})
    with pytest.raises(PlaybookHasIssuesError) as exc:
        pb.raise_for_issues(config={})
    # Once, as a wiring mistake - not again as a step that does not run.
    assert [(i.kind, i.message) for i in exc.value.issues if i.kind == "wiring"] == [
        ("wiring", "is fed from step 'nope', which does not exist (earlier steps: [])")
    ]


def test_a_step_fed_from_a_result_its_source_does_not_offer_is_reported():
    pb = Playbook(name="p")
    a = pb.add("a", FakePassthrough)
    pb.add("b", FakeNeedsUpstream, inputs={"source": a.out("bogus")})
    with pytest.raises(PlaybookHasIssuesError) as exc:
        pb.raise_for_issues()
    assert any(i.kind == "wiring" and "bogus" in i.message for i in exc.value.issues)


def test_wiring_an_input_the_block_does_not_have_is_reported():
    pb = Playbook(name="p")
    a = pb.add("a", FakePassthrough)
    pb.add("b", FakePassthrough, inputs={"not_a_real_input": a.output})
    with pytest.raises(PlaybookHasIssuesError) as exc:
        pb.raise_for_issues()
    assert any(i.kind == "wiring" and "no input called" in i.message for i in exc.value.issues)


def test_an_issue_says_which_input_it_is_about():
    pb = Playbook(name="p")
    a = pb.add("a", FakePassthrough)
    pb.add("b", FakePassthrough, inputs={"not_a_real_input": a.output})
    issues = pb.find_issues()
    assert any(i.input == "not_a_real_input" and i.step_path == ("b",) for i in issues)


def test_a_missing_dim_reports_which_step_removed_it():
    pb = Playbook(name="p", initial_dims=frozenset({"investment_period"}))
    pb.add("collapse", FakeRemovesInvestmentPeriod)
    pb.add("needs_it", FakeRequiresInvestmentPeriod)
    with pytest.raises(PlaybookHasIssuesError) as exc:
        pb.raise_for_issues(config={})
    dims_issues = [i for i in exc.value.issues if i.kind == "dims"]
    assert len(dims_issues) == 1
    assert dims_issues[0].step_path == ("needs_it",)
    assert "step 'collapse' removed it" in dims_issues[0].message


def test_the_same_block_twice_with_different_settings_is_fine():
    pb = Playbook(name="p")
    pb.add("first", FakePassthrough)
    pb.add("second", FakePassthrough)
    pb.raise_for_issues(config={"first": {"label": "one"}, "second": {"label": "two"}})


def test_settings_for_a_step_that_does_not_exist_are_reported():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    issues = pb.find_issues(config={"a": {}, "not_a_step": {}})
    assert [(i.kind, i.step_path, i.config_path) for i in issues] == [
        ("config", (), ("not_a_step",))
    ]
    assert "no step called" in issues[0].message


@IMPORTED_OR_DESCRIBED
def test_a_settings_problem_points_at_the_exact_setting(as_step_block):
    pb = Playbook(name="p")
    pb.add("strict", as_step_block(FakeStrictConfig))
    issues = pb.find_issues(config={"strict": {"required_field": "not a number"}})
    # A user interface can mark this one field, rather than the whole step. The path
    # counts from the top of the settings, so it can be followed without knowing which
    # step it belongs to.
    assert [(i.kind, i.step_path, i.config_path) for i in issues] == [
        ("config", ("strict",), ("strict", "required_field"))
    ]


@IMPORTED_OR_DESCRIBED
def test_a_missing_setting_is_reported_at_the_setting_itself(as_step_block):
    pb = Playbook(name="p")
    pb.add("strict", as_step_block(FakeStrictConfig))
    issues = pb.find_issues(config={"strict": {}})
    assert [(i.config_path, i.message) for i in issues] == [
        (("strict", "required_field"), "this setting is required")
    ]


@IMPORTED_OR_DESCRIBED
def test_a_misspelt_setting_is_reported_rather_than_ignored(as_step_block):
    # Ignoring it would quietly run the block with the default in its place.
    pb = Playbook(name="p")
    pb.add("a", as_step_block(FakePassthrough))
    issues = pb.find_issues(config={"a": {"lable": "typo"}})
    assert [(i.config_path, i.message) for i in issues] == [
        (("a", "lable"), "there is no setting called 'lable'")
    ]


@IMPORTED_OR_DESCRIBED
def test_a_problem_inside_an_optional_group_of_settings_points_at_the_setting(as_step_block):
    pb = Playbook(name="p")
    pb.add("a", as_step_block(FakeNestedSettings))
    issues = pb.find_issues(config={"a": {"group": {"size": "big"}}})
    assert [i.config_path for i in issues] == [("a", "group", "size")]


@IMPORTED_OR_DESCRIBED
def test_a_wired_in_setting_is_not_asked_of_the_settings(as_step_block):
    # The wiring fills it in, so leaving it out of the settings is not a mistake.
    pb = Playbook(name="p")
    a = pb.add("a", FakePassthrough)
    pb.add("b", as_step_block(FakeNeedsUpstream), inputs={"source": a.output})
    assert pb.find_issues(config={"a": {}, "b": {}}) == []


def test_each_settings_problem_is_reported_separately():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    issues = pb.find_issues(config={"a": {"label": [], "source": 7}})
    assert {i.config_path for i in issues if i.kind == "config"} == {
        ("a", "label"),
        ("a", "source"),
    }


def test_a_conditional_branch_can_have_different_dims_validity():
    pb = Playbook(name="p")
    pb.add(
        "needs_period",
        FakeRequiresInvestmentPeriod,
        when=When(config="globals.mode", equals="a"),
    )
    pb.add("no_requirement", FakePassthrough, when=When(config="globals.mode", equals="b"))

    with pytest.raises(PlaybookHasIssuesError) as exc:
        pb.raise_for_issues(config={"globals": {"mode": "a"}})
    assert any(i.kind == "dims" for i in exc.value.issues)

    pb.raise_for_issues(config={"globals": {"mode": "b"}})  # nothing wrong


def test_a_step_that_runs_cannot_be_fed_by_one_that_does_not():
    pb = Playbook(name="p")
    a = pb.add("a", FakePassthrough, when=When(config="globals.mode", equals="b"))
    pb.add("b", FakeNeedsUpstream, inputs={"source": a.output})

    with pytest.raises(PlaybookHasIssuesError) as exc:
        pb.raise_for_issues(config={"globals": {"mode": "a"}})  # a does not run
    assert any(i.kind == "wiring" and "does not run" in i.message for i in exc.value.issues)


def test_settings_for_a_branch_that_does_not_run_are_still_allowed():
    pb = Playbook(name="p")
    pb.add("branch_a", FakePassthrough, when=When(config="globals.mode", equals="a"))
    pb.add("branch_b", FakePassthrough, when=When(config="globals.mode", equals="b"))
    # One settings document carries both branches; only "a" runs here.
    pb.raise_for_issues(
        config={
            "globals": {"mode": "a"},
            "branch_a": {"label": "A"},
            "branch_b": {"label": "B"},
        }
    )


def test_a_condition_on_a_setting_nobody_set_is_reported():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough, when=When(config="globals.does_not_exist", equals="x"))
    with pytest.raises(PlaybookHasIssuesError) as exc:
        pb.raise_for_issues(config={"globals": {}})
    when_issues = [i for i in exc.value.issues if i.kind == "when"]
    assert when_issues[0].step_path == ("a",)
    assert when_issues[0].config_path == ("globals", "does_not_exist")


def test_a_described_block_with_acceptable_settings_has_no_issues():
    pb = Playbook(name="p")
    pb.add("strict", _described(FakeStrictConfig))
    assert _described(FakeStrictConfig).config_model() is None
    pb.raise_for_issues(config={"strict": {"required_field": 3}})


def test_blocks_disagreeing_about_an_environment_are_reported():
    # Same environment name, but one of them says it lives somewhere particular.
    elsewhere = describe_block(FakeOtherEnv).description
    relocated = BlockSpec(elsewhere.model_copy(update={"manifest": "other/pixi.toml"}))

    pb = Playbook(name="p")
    pb.add("first", FakeOtherEnv)
    pb.add("second", relocated)
    issues = pb.find_issues(config={})
    assert [(i.kind, i.step_path) for i in issues] == [("environment", ("second",))]


def test_an_issue_reads_well_when_printed():
    pb = Playbook(name="p")
    pb.add("strict", FakeStrictConfig)
    issue = next(i for i in pb.find_issues(config={"strict": {}}) if i.kind == "config")
    assert str(issue) == (
        "[config] step 'strict', setting 'strict.required_field': this setting is required"
    )
