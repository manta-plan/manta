# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Working out what a playbook will run from its input values, before any data is read."""

import pytest

from playbook.playbooks.issues import PlaybookHasIssuesError
from playbook.playbooks.planner import PlannedBlock, PlannedGroup, plan, walk_planned


def paths(planned: PlannedGroup) -> list[tuple[str, ...]]:
    return [step.path for step in walk_planned(planned)][1:]


def blocks(planned: PlannedGroup) -> dict[str, PlannedBlock]:
    return {
        "/".join(step.path): step
        for step in walk_planned(planned)
        if isinstance(step, PlannedBlock)
    }


def test_settings_are_worked_out_from_the_inputs(capacity_expansion):
    planned = blocks(plan(capacity_expansion, {"bus": "busmap_country", "solver": "gurobi"}))
    assert planned["partition"].settings == {
        "method": "resample",
        "resolution": "3h",
        "property": "resampled",
    }
    assert planned["expand"].settings == {
        "method": "overnight",
        "aggregation": {"snapshot": "resampled", "bus": "busmap_country"},
        "solver": "gurobi",
    }


def test_a_step_whose_if_is_false_is_removed(capacity_expansion):
    assert paths(plan(capacity_expansion, {"snapshot": None})) == [("expand",)]


def test_a_nested_playbook_becomes_a_group_of_its_steps_with_inherited_inputs(
    expand_and_dispatch,
):
    planned = plan(expand_and_dispatch, {"resolution": "1h", "dispatch_resolution": "1d"})
    assert paths(planned) == [
        ("plan",),
        ("plan", "partition"),
        ("plan", "expand"),
        ("partition_weekly",),
        ("dispatch",),
    ]
    settings = {path: step.settings for path, step in blocks(planned).items()}
    assert settings["plan/partition"]["resolution"] == "1h"
    assert settings["partition_weekly"]["resolution"] == "1d"


def test_with_sets_a_nested_playbooks_inputs(build_playbook, spec_catalogue):
    pb = build_playbook(
        {
            "name": "outer",
            "inputs": {"mode": {"type": "string", "default": "perfect"}},
            "steps": [
                {
                    "id": "plan",
                    "playbook": "capacity_expansion",
                    "with": {"expansion_method": "${{ inputs.mode }}", "solver": "gurobi"},
                }
            ],
        },
        spec_catalogue,
    )
    expand = blocks(plan(pb, {}))["plan/expand"]
    assert (expand.settings["method"], expand.settings["solver"]) == ("perfect", "gurobi")


def test_a_value_given_to_a_nested_playbook_is_checked_against_its_input(
    build_playbook, spec_catalogue
):
    pb = build_playbook(
        {
            "name": "outer",
            "steps": [
                {"id": "plan", "playbook": "capacity_expansion", "with": {"solver": "cplex"}}
            ],
        },
        spec_catalogue,
    )
    with pytest.raises(PlaybookHasIssuesError) as raised:
        plan(pb, {})
    [issue] = raised.value.issues
    assert (issue.kind, issue.step_path, issue.input_path) == ("inputs", ("plan",), ("solver",))
