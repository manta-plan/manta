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
from playbook.playbooks import Playbook, playbook_from_doc

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


def as_the_backend_sees_it(name: str) -> Playbook:
    """A shipped playbook with every block known only from the committed catalogue."""
    playbook = playbook_from_doc(library_playbooks()[name], catalogue=library_catalogue())
    return described_only(playbook)


def with_its_blocks_imported(name: str) -> Playbook:
    """A shipped playbook with its real blocks, so their own settings models check it."""
    playbook = playbook_from_doc(library_playbooks()[name])
    assert all(step.block.config_model() is not None for step in playbook.steps)
    return playbook


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
    assert [step.id for step in playbooks[name].steps] == steps


@pytest.mark.parametrize("name", SHIPPED_PLAYBOOKS)
@pytest.mark.parametrize("inputs", [None, {}])
def test_a_shipped_playbook_has_no_issues_with_its_default_settings(name, inputs):
    assert as_the_backend_sees_it(name).find_issues(inputs) == []


@pytest.mark.pypsa
@pytest.mark.parametrize("name", SHIPPED_PLAYBOOKS)
def test_a_shipped_playbook_has_no_issues_with_its_default_settings_where_its_blocks_import(
    name,
):
    pytest.importorskip("pypsa", reason="checking with the blocks' own models means importing them")
    assert with_its_blocks_imported(name).find_issues({}) == []


@pytest.mark.parametrize("name", ["expand", "cluster-expand-dispatch"])
def test_the_myopic_branch_is_reported_as_missing_the_period(name):
    # Myopic expansion works one investment period at a time, so it needs that
    # dimension, but this playbook's data starts with `snapshot` alone and no step
    # before it adds one. Run anyway, the branch would quietly do nothing.
    issues = as_the_backend_sees_it(name).find_issues({"expansion_mode": "myopic"})
    assert [(i.kind, i.step_path) for i in issues] == [("dims", ("expansion_myopic",))]
    assert "needs the 'period' dimension" in issues[0].message


def test_an_expansion_mode_the_playbook_does_not_offer_is_reported():
    issues = as_the_backend_sees_it("cluster-expand-dispatch").find_issues(
        {"expansion_mode": "perfect"}
    )
    assert [(i.kind, i.input_path) for i in issues] == [("inputs", ("expansion_mode",))]


@pytest.mark.pypsa
def test_a_rule_a_block_writes_in_code_is_only_checked_where_the_block_imports(tuned_playbook):
    # `cluster_time` needs exactly one of `n_hours` and `segments`: a rule written in
    # Python, which its JSON schema cannot carry. So the backend, knowing the block
    # only from the catalogue, lets this through; the block refuses it when it runs.
    pytest.importorskip("pypsa", reason="checking with the blocks' own models means importing them")
    settings = {"cluster": {"n_hours": None}}

    described = described_only(tuned_playbook("cluster-expand-dispatch", settings))
    assert described.find_issues({}) == []

    issues = tuned_playbook("cluster-expand-dispatch", settings).find_issues({})
    assert [(i.kind, i.step_path) for i in issues] == [("config", ("cluster",))]
