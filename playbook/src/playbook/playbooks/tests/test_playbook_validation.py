# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Checking a playbook, and the inputs it is about to run with, before anything runs.

Settings are checked two ways: by the block's own settings model where the block can
be imported, and by its catalogue description where it cannot - the ordinary case for
anything driving playbooks from outside. Where both apply, they have to agree.
"""

import pytest

from playbook.blocks import Catalogue, describe_block
from playbook.blocks.tests.fakes import (
    FakeNestedSettings,
    FakeOtherEnv,
    FakePassthrough,
    FakeStrictConfig,
)
from playbook.playbooks.tests.specs import SPEC_PLAYBOOKS, SPEC_REQUIRED_INPUTS
from playbook.playbooks.validation import find_playbook_issues

DESCRIBED = Catalogue(
    blocks={
        f"described_{block.name}": block.description.model_copy(
            update={"name": f"described_{block.name}"}
        )
        for block in map(describe_block, [FakeStrictConfig, FakePassthrough, FakeNestedSettings])
    }
)
IMPORTED_OR_DESCRIBED = pytest.mark.parametrize("prefix", ["", "described_"])


def steps(*listed: dict, **inputs: dict) -> dict:
    return {"name": "p", "inputs": inputs, "steps": list(listed)}


def with_period(doc: dict) -> dict:
    return {**doc, "initial_data": {"dims": ["period"]}}


def block(step_id: str, name: str = "fake_passthrough", **extra: object) -> dict:
    return {"id": step_id, "block": name, **extra}


def found(pb, inputs: dict | None) -> list[tuple]:
    return [(i.kind, i.step_path) for i in find_playbook_issues(pb, inputs)]


@pytest.mark.parametrize("name", SPEC_PLAYBOOKS)
@pytest.mark.parametrize("given", [None, {}, {"snapshot": "resampled"}])
def test_a_spec_playbook_has_no_issues(request, name, given):
    inputs = None if given is None else {**SPEC_REQUIRED_INPUTS[name], **given}
    assert request.getfixturevalue(name).find_issues(inputs) == []


def test_the_function_and_the_method_find_the_same_issues(build_playbook):
    pb = build_playbook(steps(block("a"), block("a")))
    assert find_playbook_issues(pb, {}) == pb.find_issues({}) != []


@pytest.mark.parametrize(
    ("doc", "issues"),
    [
        pytest.param(steps(block("a"), block("a")), [("structure", ("a",))], id="duplicate-id"),
        pytest.param(
            steps(
                {"id": "plan", "playbook": "capacity_expansion", "inputs": "inherit"},
                solver={"type": "string", "default": "highs"},
            ),
            [("structure", ("plan",))],
            id="inherited-input-clash",
        ),
    ],
)
def test_a_problem_with_the_playbook_itself_is_found_without_inputs(
    build_playbook, spec_catalogue, doc, issues
):
    pb = build_playbook(doc, spec_catalogue)
    assert found(pb, None) == found(pb, {}) == issues


@pytest.mark.parametrize(
    ("step", "message"),
    [
        (block("a", **{"if": "${{ inputs.nope }}"}), "no input 'nope'"),
        (block("a", **{"with": {"label": "${{ inputs.mode.x }}"}}), "does not have"),
        (block("a", **{"with": {"label": "${{ inputs }}"}}), "as a whole"),
    ],
)
def test_an_expression_reading_something_that_does_not_exist_is_reported(
    build_playbook, step, message
):
    pb = build_playbook(steps(step, mode={"type": "string", "default": "a"}))
    [issue] = pb.find_issues()
    assert (issue.kind, issue.step_path) == ("reference", ("a",))
    assert message in issue.message


def test_a_nested_playbook_given_an_input_it_does_not_have_is_reported(
    build_playbook, spec_catalogue
):
    nested = {"id": "plan", "playbook": "capacity_expansion", "with": {"solvr": "highs"}}
    [issue] = build_playbook(steps(nested), spec_catalogue).find_issues()
    assert (issue.kind, issue.step_path, issue.input_path) == ("reference", ("plan",), ("solvr",))


def test_input_values_that_do_not_fit_are_reported_before_anything_else(capacity_expansion):
    issues = capacity_expansion.find_issues({"solver": "cplex", "region": "x"})
    assert {(i.kind, i.input_path) for i in issues} == {
        ("inputs", ("solver",)),
        ("inputs", ("region",)),
    }


@IMPORTED_OR_DESCRIBED
@pytest.mark.parametrize(
    ("name", "settings", "expected"),
    [
        (
            "fake_strict_config",
            {"required_field": "not a number"},
            [("required_field",)],
        ),
        ("fake_strict_config", {}, [("required_field",)]),
        ("fake_passthrough", {"lable": "typo"}, [("lable",)]),
        ("fake_nested_settings", {"group": {"size": "big"}}, [("group", "size")]),
        ("fake_passthrough", {"label": [], "lable": 7}, [("label",), ("lable",)]),
    ],
)
def test_a_settings_problem_points_at_the_exact_setting(
    build_playbook, prefix, name, settings, expected
):
    pb = build_playbook(steps(block("a", f"{prefix}{name}", **{"with": settings})), DESCRIBED)
    issues = pb.find_issues({})
    assert {(i.kind, i.step_path) for i in issues} == {("config", ("a",))}
    assert sorted(i.setting_path for i in issues) == expected


@IMPORTED_OR_DESCRIBED
@pytest.mark.parametrize(
    ("settings", "message"),
    [({}, "this setting is required"), ({"required_field": 1, "x": 1}, "no setting called 'x'")],
)
def test_a_settings_problem_reads_the_same_imported_or_described(
    build_playbook, prefix, settings, message
):
    doc = steps(block("a", f"{prefix}fake_strict_config", **{"with": settings}))
    [issue] = build_playbook(doc, DESCRIBED).find_issues({})
    assert message in issue.message


def test_settings_come_from_the_inputs_before_they_are_checked(build_playbook):
    doc = steps(
        block("a", "fake_strict_config", **{"with": {"required_field": "${{ inputs.size }}"}}),
        size={"type": "number", "default": 1},
    )
    pb = build_playbook(doc)
    assert pb.find_issues({}) == []
    assert [i.setting_path for i in pb.find_issues({"size": 1.5})] == [("required_field",)]


UNEVALUABLE_IF = block("a", **{"if": "${{ inputs.hours > 1 }}"})


@pytest.mark.parametrize(
    ("listed", "step_paths"),
    [
        ([UNEVALUABLE_IF], [("a",)]),
        ([block("a", **{"with": {"label": "${{ inputs.hours < 1 }}"}})], [("a",)]),
        (
            [{"id": "n", "playbook": steps(UNEVALUABLE_IF, hours={"type": "number"})}],
            [("n", "a")],
        ),
        (
            [
                UNEVALUABLE_IF,
                {
                    "id": "n",
                    "playbook": steps(block("b"), m={"type": "number", "required": True}),
                },
            ],
            [("a",), ("n",)],
        ),
    ],
)
def test_an_expression_that_cannot_be_evaluated_is_reported(build_playbook, listed, step_paths):
    pb = build_playbook(steps(*listed, hours={"type": "number"}))
    issues = pb.find_issues({})
    assert [(issue.kind, issue.step_path) for issue in issues] == [
        ("inputs", path) for path in step_paths
    ]
    assert "cannot be evaluated" in issues[0].message


def test_a_step_removed_by_its_if_is_not_checked(build_playbook):
    removed = block("a", "fake_strict_config", **{"if": "${{ inputs.on }}"})
    pb = build_playbook(steps(removed, on={"type": "boolean", "default": False}))
    assert pb.find_issues({}) == []
    assert found(pb, {"on": True}) == [("config", ("a",))]


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        pytest.param(steps(block("needs", "fake_requires_period")), "(it has: [])", id="never"),
        pytest.param(
            with_period(
                steps(
                    block("collapse", "fake_removes_period"),
                    block("needs", "fake_requires_period"),
                )
            ),
            "step 'collapse' removed it",
            id="removed",
        ),
        pytest.param(
            with_period(
                steps(
                    {
                        "id": "nested",
                        "playbook": with_period(steps(block("c", "fake_removes_period"))),
                    },
                    block("needs", "fake_requires_period"),
                )
            ),
            "step 'nested' removed it",
            id="removed-by-a-nested-playbook",
        ),
        pytest.param(
            with_period(
                steps(
                    {"id": "nested", "playbook": steps(block("c", "fake_removes_period"))},
                    block("needs", "fake_requires_period"),
                )
            ),
            "step 'nested' removed it",
            id="removed-by-a-nested-playbook-that-does-not-state-it",
        ),
    ],
)
def test_a_dimension_the_data_lacks_when_a_step_runs_is_reported(build_playbook, doc, message):
    [issue] = build_playbook(doc).find_issues({})
    assert (issue.kind, issue.step_path) == ("dims", ("needs",))
    assert message in issue.message


def test_a_dimension_the_data_starts_with_is_there(build_playbook):
    pb = build_playbook(with_period(steps(block("needs", "fake_requires_period"))))
    assert pb.find_issues({}) == []


def test_a_nested_playbook_needs_the_dimensions_its_data_starts_with(build_playbook):
    pb = build_playbook(steps({"id": "nested", "playbook": with_period(steps(block("a")))}))
    [issue] = pb.find_issues({})
    assert (issue.kind, issue.step_path) == ("dims", ("nested",))


def test_blocks_disagreeing_about_an_environment_are_reported(build_playbook):
    relocated = describe_block(FakeOtherEnv).description.model_copy(
        update={"name": "relocated", "manifest": "other/pixi.toml"}
    )
    catalogue = Catalogue(blocks={"relocated": relocated})
    pb = build_playbook(
        steps(block("first", "fake_other_env"), block("second", "relocated")), catalogue
    )
    assert found(pb, {}) == [("environment", ("second",))]


def test_an_issue_reads_well_when_printed(build_playbook):
    [issue] = build_playbook(steps(block("strict", "fake_strict_config"))).find_issues({})
    assert str(issue) == (
        "[config] step 'strict', setting 'required_field': this setting is required"
    )
