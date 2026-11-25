# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

import pytest

from playbook.playbooks.inputs import resolve_inputs
from playbook.playbooks.issues import PlaybookHasIssuesError
from playbook.playbooks.syntax import PlaybookDoc
from playbook.playbooks.tests.specs import spec_doc

CAPACITY_EXPANSION_INPUTS = spec_doc("capacity_expansion").inputs
DEFAULTS = {
    "snapshot": None,
    "bus": None,
    "resolution": "3h",
    "expansion_method": "overnight",
    "solver": "highs",
}


@pytest.mark.parametrize(
    ("given", "changed"),
    [
        ({}, {}),
        ({"solver": "gurobi"}, {"solver": "gurobi"}),
        ({"bus": "busmap_country"}, {"bus": "busmap_country"}),
    ],
)
def test_given_values_are_merged_over_the_defaults(given, changed):
    assert resolve_inputs(CAPACITY_EXPANSION_INPUTS, given) == {**DEFAULTS, **changed}


@pytest.mark.parametrize(
    ("given", "input_path"),
    [
        ({"solvr": "highs"}, ("solvr",)),
        ({"bus": 3}, ("bus",)),
        ({"solver": "cplex"}, ("solver",)),
        ({"resolution": 3}, ("resolution",)),
    ],
)
def test_a_value_that_does_not_fit_is_reported_with_its_path(given, input_path):
    with pytest.raises(PlaybookHasIssuesError) as raised:
        resolve_inputs(CAPACITY_EXPANSION_INPUTS, given)
    [issue] = raised.value.issues
    assert (issue.kind, issue.input_path) == ("inputs", input_path)


def test_every_value_that_does_not_fit_is_reported_at_once():
    with pytest.raises(PlaybookHasIssuesError) as raised:
        resolve_inputs(CAPACITY_EXPANSION_INPUTS, {"solver": "cplex", "region": "x"})
    assert {issue.input_path for issue in raised.value.issues} == {("solver",), ("region",)}


SPECS = PlaybookDoc.model_validate(
    {
        "name": "typed",
        "inputs": {
            "count": {"type": "number", "required": True},
            "flag": {"type": "boolean", "default": False},
            "note": {"type": "string"},
            "level": {"type": "choice", "options": [1, 2], "default": 1},
        },
        "steps": [{"id": "a", "block": "b"}],
    }
).inputs
GIVEN = {"count": 2.5}


@pytest.mark.parametrize(
    ("given", "changed"),
    [
        ({}, {}),
        ({"note": None}, {}),
        ({"note": "x", "flag": True}, {"note": "x", "flag": True}),
    ],
)
def test_an_optional_input_left_out_takes_its_default_or_null(given, changed):
    resolved = resolve_inputs(SPECS, {**GIVEN, **given})
    assert resolved == {"count": 2.5, "flag": False, "note": None, "level": 1, **changed}


@pytest.mark.parametrize(
    ("given", "input_path"),
    [
        ({"count": None}, ("count",)),
        ({"count": True}, ("count",)),
        ({"flag": None}, ("flag",)),
        ({"flag": "yes"}, ("flag",)),
        ({"level": True}, ("level",)),
    ],
)
def test_a_missing_null_or_mistyped_value_is_reported(given, input_path):
    with pytest.raises(PlaybookHasIssuesError) as raised:
        resolve_inputs(SPECS, {**GIVEN, **given})
    assert [issue.input_path for issue in raised.value.issues] == [input_path]


def test_a_required_input_left_out_is_reported():
    with pytest.raises(PlaybookHasIssuesError, match="'count': is required"):
        resolve_inputs(SPECS, {})
