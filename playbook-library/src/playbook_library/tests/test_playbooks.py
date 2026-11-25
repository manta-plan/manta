# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The playbooks that ship with the library, found, read and checked without PyPSA.

Anything driving Manta - the backend, a UI - lists playbooks from here, in an
environment that cannot import the blocks they name. So most tests here only read
documents, and check each playbook against the committed catalogue, the way the
backend does. The few that need the blocks themselves carry the pypsa marker.
"""

import pytest
from playbook.blocks import BlockSpec
from playbook.playbooks import Playbook, plan
from playbook.playbooks.planner import PlannedBlock, walk_planned

from playbook_library import library_catalogue
from playbook_library.playbooks import library_playbooks

SHIPPED_PLAYBOOKS = sorted(library_playbooks())


def described_only(playbook: Playbook) -> Playbook:
    """`playbook` with every block known only from the committed catalogue.

    That is all Manta's backend has, since it cannot import the blocks. Swapping each
    block for its catalogue entry makes it so here too, even where PyPSA is installed,
    so settings are checked against the blocks' JSON schemas, as the backend checks
    them.
    """
    catalogue = library_catalogue()
    return playbook.model_copy(
        update={
            "steps": [
                step.model_copy(update={"block": BlockSpec(catalogue.blocks[step.block.name])})
                for step in playbook.steps
            ]
        }
    )


@pytest.fixture
def as_the_backend_sees_it(tuned_playbook):
    """Build a shipped playbook with its default settings and every block described only."""

    def build(name: str) -> Playbook:
        return described_only(tuned_playbook(name))

    return build


@pytest.mark.parametrize(
    ("name", "steps"),
    [
        ("expand", ["expansion_overnight", "expansion_myopic", "expansion_perfect"]),
        (
            "cluster-expand-dispatch",
            ["cluster", "expansion_overnight", "expansion_myopic", "dispatch"],
        ),
    ],
)
def test_the_library_ships_the_playbook(name, steps):
    playbooks = library_playbooks()
    assert name in playbooks
    assert [step.id for step in playbooks[name].doc.steps] == steps


@pytest.mark.parametrize(
    ("name", "default_settings"),
    [
        ("expand", {}),
        (
            "cluster-expand-dispatch",
            {
                "cluster": {"n_hours": 3},
                "dispatch": {"optimize_config": {"horizon": 168, "overlap": 24}},
            },
        ),
    ],
)
def test_a_shipped_playbook_comes_with_its_default_settings(name, default_settings):
    assert library_playbooks()[name].default_settings == default_settings


@pytest.mark.parametrize("name", SHIPPED_PLAYBOOKS)
@pytest.mark.parametrize("inputs", [None, {}])
def test_a_shipped_playbook_has_no_issues_with_its_default_settings(
    as_the_backend_sees_it, name, inputs
):
    assert as_the_backend_sees_it(name).find_issues(inputs) == []


@pytest.mark.pypsa
@pytest.mark.parametrize("name", SHIPPED_PLAYBOOKS)
def test_a_shipped_playbook_has_no_issues_with_its_default_settings_where_its_blocks_import(
    tuned_playbook, name
):
    pytest.importorskip("pypsa", reason="checking with the blocks' own models means importing them")
    playbook = tuned_playbook(name)
    assert all(step.block.config_model() is not None for step in playbook.steps)
    assert playbook.find_issues({}) == []


@pytest.mark.parametrize(
    ("mode", "settings"),
    [
        (
            "overnight",
            {
                "cluster": {"n_hours": 3},
                "expansion_overnight": {"optimize_config": {"solver_name": "highs"}},
                "dispatch": {
                    "optimize_config": {"solver_name": "highs", "horizon": 168, "overlap": 24}
                },
            },
        ),
        (
            "myopic",
            {
                "cluster": {"n_hours": 3},
                "expansion_myopic": {"optimize_config": {"solver_name": "highs"}},
            },
        ),
    ],
)
def test_cluster_expand_dispatch_plans_its_default_settings_and_the_solver(
    as_the_backend_sees_it, mode, settings
):
    planned = plan(as_the_backend_sees_it("cluster-expand-dispatch"), {"expansion_mode": mode})
    blocks = [step for step in walk_planned(planned) if isinstance(step, PlannedBlock)]
    assert {step.path[-1]: step.settings for step in blocks} == settings


@pytest.mark.parametrize("name", ["expand", "cluster-expand-dispatch"])
def test_the_myopic_branch_is_reported_as_missing_the_period(as_the_backend_sees_it, name):
    # Myopic expansion works one investment period at a time, so it needs that
    # dimension, but this playbook's data starts with `snapshot` alone and no step
    # before it adds one. Run anyway, the branch would quietly do nothing.
    issues = as_the_backend_sees_it(name).find_issues({"expansion_mode": "myopic"})
    assert [(i.kind, i.step_path) for i in issues] == [("dims", ("expansion_myopic",))]
    assert "needs the 'period' dimension" in issues[0].message


@pytest.mark.parametrize(
    ("inputs", "input_path"),
    [
        ({"expansion_mode": "perfect"}, ("expansion_mode",)),
        ({"solver_name": "cplex"}, ("solver_name",)),
    ],
)
def test_an_input_value_the_playbook_does_not_offer_is_reported(
    as_the_backend_sees_it, inputs, input_path
):
    issues = as_the_backend_sees_it("cluster-expand-dispatch").find_issues(inputs)
    assert [(i.kind, i.input_path) for i in issues] == [("inputs", input_path)]


@pytest.mark.pypsa
def test_a_rule_a_block_writes_in_code_is_only_checked_where_the_block_imports(tuned_playbook):
    # `cluster_time` needs exactly one of `n_hours` and `segments`: a rule written in
    # Python, which its JSON schema cannot carry. So the backend, knowing the block
    # only from the catalogue, lets this through; the block refuses it when it runs.
    pytest.importorskip("pypsa", reason="checking with the blocks' own models means importing them")
    tuned = tuned_playbook("cluster-expand-dispatch", {"cluster": {"n_hours": None}})

    assert described_only(tuned).find_issues({}) == []

    issues = tuned.find_issues({})
    assert [(i.kind, i.step_path) for i in issues] == [("config", ("cluster",))]
