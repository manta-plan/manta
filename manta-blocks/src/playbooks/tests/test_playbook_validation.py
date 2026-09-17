# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

import pytest

from blocks import BlockSpec, describe_block
from blocks.tests.fakes import (
    FakeAddsClustered,
    FakeNeedsUpstream,
    FakePassthrough,
    FakeRemovesInvestmentPeriod,
    FakeRequiresInvestmentPeriod,
    FakeStrictConfig,
)
from playbooks.playbook import Playbook, When
from playbooks.validation import PlaybookValidationError


def _issue_kinds(exc) -> set[str]:
    return {issue.kind for issue in exc.value.issues}


def test_happy_path_no_issues():
    pb = Playbook(name="happy")
    pb.add("cluster", FakeAddsClustered)
    a = pb.add("expand", FakePassthrough)
    pb.add("dispatch", FakeNeedsUpstream, inputs={"source": a.output})
    pb.validate_playbook()  # structure and wiring only, no settings given
    pb.validate_playbook(config={})  # everything, still nothing wrong


def test_config_independent_checks_run_without_config():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    pb.add("a", FakePassthrough)  # duplicate name
    with pytest.raises(PlaybookValidationError) as exc:
        pb.validate_playbook()
    assert "structure" in _issue_kinds(exc)


def test_duplicate_step_names():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    pb.add("a", FakePassthrough)
    with pytest.raises(PlaybookValidationError) as exc:
        pb.validate_playbook()
    assert any(
        i.kind == "structure" and "duplicate" in i.message for i in exc.value.issues
    )


def test_forward_ref_is_rejected():
    pb = Playbook(name="p")
    pb.add("a", FakeNeedsUpstream, inputs={"source": {"step": "b", "output": "output"}})
    pb.add("b", FakePassthrough)
    with pytest.raises(PlaybookValidationError) as exc:
        pb.validate_playbook()
    assert any(
        i.kind == "ref" and "does not come before" in i.message
        for i in exc.value.issues
    )


def test_ref_to_unknown_step():
    pb = Playbook(name="p")
    pb.add(
        "a", FakeNeedsUpstream, inputs={"source": {"step": "nope", "output": "output"}}
    )
    with pytest.raises(PlaybookValidationError) as exc:
        pb.validate_playbook()
    assert any(
        i.kind == "ref" and "does not exist" in i.message for i in exc.value.issues
    )


def test_ref_to_unknown_output_name():
    pb = Playbook(name="p")
    a = pb.add("a", FakePassthrough)
    pb.add("b", FakeNeedsUpstream, inputs={"source": a.out("bogus")})
    with pytest.raises(PlaybookValidationError) as exc:
        pb.validate_playbook()
    assert any(i.kind == "ref" and "bogus" in i.message for i in exc.value.issues)


def test_input_name_not_declared_on_block():
    pb = Playbook(name="p")
    a = pb.add("a", FakePassthrough)
    pb.add("b", FakePassthrough, inputs={"not_a_real_input": a.output})
    with pytest.raises(PlaybookValidationError) as exc:
        pb.validate_playbook()
    assert any(
        i.kind == "ref" and "no input called" in i.message for i in exc.value.issues
    )


def test_an_issue_says_which_input_it_is_about():
    pb = Playbook(name="p")
    a = pb.add("a", FakePassthrough)
    pb.add("b", FakePassthrough, inputs={"not_a_real_input": a.output})
    issues = pb.issues()
    assert any(i.input == "not_a_real_input" and i.path == ("b",) for i in issues)


def test_missing_dim_reports_which_step_removed_it():
    pb = Playbook(name="p", initial_dims=frozenset({"investment_period"}))
    pb.add("collapse", FakeRemovesInvestmentPeriod)
    pb.add("needs_it", FakeRequiresInvestmentPeriod)
    with pytest.raises(PlaybookValidationError) as exc:
        pb.validate_playbook(config={})
    dims_issues = [i for i in exc.value.issues if i.kind == "dims"]
    assert len(dims_issues) == 1
    assert "step 'collapse' removed it" in dims_issues[0].message


def test_same_block_class_twice_with_different_config_is_fine():
    pb = Playbook(name="p")
    pb.add("first", FakePassthrough)
    pb.add("second", FakePassthrough)
    pb.validate_playbook(config={"first": {"label": "one"}, "second": {"label": "two"}})


def test_unknown_config_key():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    with pytest.raises(PlaybookValidationError) as exc:
        pb.validate_playbook(config={"a": {}, "not_a_step": {}})
    assert any(
        i.kind == "config" and "no step called" in i.message for i in exc.value.issues
    )


def test_a_settings_problem_points_at_the_exact_setting():
    pb = Playbook(name="p")
    pb.add("strict", FakeStrictConfig)
    issues = pb.issues(config={"strict": {}})  # required_field is missing
    config_issues = [i for i in issues if i.kind == "config"]
    assert len(config_issues) == 1
    # A user interface can mark this one field, rather than the whole step.
    assert config_issues[0].path == ("strict",)
    assert config_issues[0].field == ("required_field",)


def test_each_settings_problem_is_reported_separately():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough)
    issues = pb.issues(config={"a": {"label": [], "source": 7}})
    assert {i.field for i in issues if i.kind == "config"} == {("label",), ("source",)}


def test_conditional_branch_has_different_dims_validity():
    pb = Playbook(name="p")
    pb.add(
        "needs_period",
        FakeRequiresInvestmentPeriod,
        when=When(config="globals.mode", equals="a"),
    )
    pb.add(
        "no_requirement", FakePassthrough, when=When(config="globals.mode", equals="b")
    )

    with pytest.raises(PlaybookValidationError) as exc:
        pb.validate_playbook(config={"globals": {"mode": "a"}})
    assert any(i.kind == "dims" for i in exc.value.issues)

    pb.validate_playbook(config={"globals": {"mode": "b"}})  # nothing wrong


def test_a_step_that_runs_cannot_be_fed_by_one_that_does_not():
    pb = Playbook(name="p")
    a = pb.add("a", FakePassthrough, when=When(config="globals.mode", equals="b"))
    pb.add("b", FakeNeedsUpstream, inputs={"source": a.output})

    with pytest.raises(PlaybookValidationError) as exc:
        pb.validate_playbook(config={"globals": {"mode": "a"}})  # a does not run
    assert any(
        i.kind == "ref" and "does not run" in i.message for i in exc.value.issues
    )


def test_settings_for_a_branch_that_does_not_run_are_still_allowed():
    pb = Playbook(name="p")
    pb.add("branch_a", FakePassthrough, when=When(config="globals.mode", equals="a"))
    pb.add("branch_b", FakePassthrough, when=When(config="globals.mode", equals="b"))
    # One settings file carries both branches; only "a" runs here.
    pb.validate_playbook(
        config={
            "globals": {"mode": "a"},
            "branch_a": {"label": "A"},
            "branch_b": {"label": "B"},
        }
    )


def test_a_condition_on_a_setting_nobody_set_is_reported():
    pb = Playbook(name="p")
    pb.add("a", FakePassthrough, when=When(config="globals.does_not_exist", equals="x"))
    with pytest.raises(PlaybookValidationError) as exc:
        pb.validate_playbook(config={"globals": {}})
    when_issues = [i for i in exc.value.issues if i.kind == "when"]
    assert when_issues[0].field == ("globals", "does_not_exist")


def test_settings_are_checked_even_for_a_block_that_cannot_be_imported_here():
    # This is the ordinary case for anything driving playbooks from outside: the
    # blocks live in environments the caller has not got, so their settings have to
    # be checked from their description instead.
    described = describe_block(FakeStrictConfig)
    elsewhere = BlockSpec(described.description)  # no class, as if from a catalogue
    assert elsewhere.config_model() is None

    pb = Playbook(name="p")
    pb.add("strict", elsewhere)

    issues = pb.issues(config={"strict": {"required_field": "not a number"}})
    config_issues = [i for i in issues if i.kind == "config"]
    assert config_issues[0].path == ("strict",)
    assert config_issues[0].field == ("required_field",)


def test_a_described_block_with_acceptable_settings_has_no_issues():
    elsewhere = BlockSpec(describe_block(FakeStrictConfig).description)
    pb = Playbook(name="p")
    pb.add("strict", elsewhere)
    pb.validate_playbook(config={"strict": {"required_field": 3}})


def test_an_issue_reads_well_when_printed():
    pb = Playbook(name="p")
    pb.add("strict", FakeStrictConfig)
    issue = next(i for i in pb.issues(config={"strict": {}}) if i.kind == "config")
    assert "step 'strict'" in str(issue)
    assert "required_field" in str(issue)
