import pytest
from fastapi import HTTPException
from playbook.playbooks import parse_doc
from playbook_library import library_catalogue
from playbook_library.playbooks import library_playbooks

from manta.services.playbook_service import PlaybookService
from manta.services.results.playbook_result import (
    PlaybookIssueResult,
    ValidatePlaybookConfigResult,
)

_LIBRARY_PLAYBOOK = "expand"


def _library_service() -> PlaybookService:
    return PlaybookService(playbooks=library_playbooks(), catalogue=library_catalogue())


def test_list_playbooks_lists_every_library_playbook_with_its_steps() -> None:
    # Given
    service = _library_service()

    # When
    result = service.list_playbooks()

    # Then
    assert result.total == len(library_playbooks())
    assert [item.name for item in result.items] == list(library_playbooks())
    playbook = next(item for item in result.items if item.name == _LIBRARY_PLAYBOOK)
    assert [(step.name, step.block) for step in playbook.steps] == [
        ("expansion_overnight", "overnight_capacity_expansion"),
        ("expansion_myopic", "myopic_capacity_expansion"),
        ("expansion_perfect", "perfect_capacity_expansion"),
    ]


def test_get_playbook_describes_each_step_with_its_blocks_settings() -> None:
    # Given
    service = _library_service()
    catalogue = library_catalogue()

    # When
    result = service.get_playbook(_LIBRARY_PLAYBOOK)

    # Then: the playbook's own defaults come along, so a caller has a valid
    # starting config without reading the library's source...
    assert result.name == _LIBRARY_PLAYBOOK
    assert result.default_config == {
        "globals": {"expansion_mode": "overnight"},
        "expansion_overnight": {},
        "expansion_myopic": {},
        "expansion_perfect": {},
    }

    # ...and every step carries its block's description and settings schema
    # straight from the catalogue.
    steps = {step.name: step for step in result.steps}
    assert list(steps) == ["expansion_overnight", "expansion_myopic", "expansion_perfect"]
    for step in result.steps:
        block = catalogue.blocks[step.block]
        assert step.block_summary == block.doc
        assert step.block_config_schema == block.config_schema

    # And the step-level conditions are reported per step.
    assert steps["expansion_overnight"].when.config == "globals.expansion_mode"
    assert steps["expansion_overnight"].when.equals == "overnight"
    assert steps["expansion_myopic"].when.equals == "myopic"
    assert steps["expansion_perfect"].when.equals == "perfect"
    assert steps["expansion_overnight"].inputs == {}


def test_get_playbook_offers_each_steps_with_as_its_default_settings() -> None:
    # Given
    service = _library_service()

    # When
    result = service.get_playbook("cluster-expand-dispatch")

    # Then
    assert result.default_config["cluster"] == {"n_hours": 3}
    assert result.default_config["dispatch"] == {"optimize_config": {"horizon": 168, "overlap": 24}}


@pytest.mark.parametrize(
    "condition",
    ["${{ inputs.mode != 'a' }}", "${{ !inputs.on }}", "${{ inputs.on && inputs.mode == 'a' }}"],
)
@pytest.mark.parametrize(
    "request_playbook",
    [
        lambda service: service.get_playbook("conditional"),
        lambda service: service.validate_playbook_config("conditional", config=None),
        lambda service: service.find_config_issues("conditional", {}),
    ],
    ids=["detail", "validate", "check-before-run"],
)
def test_a_condition_the_web_app_cannot_show_is_refused_with_a_501(condition, request_playbook):
    # Given a playbook whose step condition is not one input compared with `==`
    doc = parse_doc(
        {
            "name": "conditional",
            "inputs": {
                "on": {"type": "boolean", "default": True},
                "mode": {"type": "string", "default": "a"},
            },
            "steps": [{"id": "cluster", "block": "cluster_time", "if": condition}],
        }
    )
    service = PlaybookService(playbooks={"conditional": doc}, catalogue=library_catalogue())

    # When/Then: it is still listed...
    assert [item.name for item in service.list_playbooks().items] == ["conditional"]
    # ...but any request needing its conditions is refused, naming the step and condition
    with pytest.raises(HTTPException) as exc_info:
        request_playbook(service)
    assert exc_info.value.status_code == 501
    assert "'conditional'" in exc_info.value.detail
    assert "'cluster'" in exc_info.value.detail
    assert condition in exc_info.value.detail


def test_get_playbook_describes_a_block_used_by_two_steps_once_per_step() -> None:
    # Given a playbook using the same block twice, under two step names
    doc = parse_doc(
        {
            "name": "two-dispatches",
            "steps": [
                {"id": "dispatch_2030", "block": "rolling_horizon_dispatch"},
                {"id": "dispatch_2040", "block": "rolling_horizon_dispatch"},
            ],
        }
    )
    service = PlaybookService(playbooks={"two-dispatches": doc}, catalogue=library_catalogue())

    # When
    result = service.get_playbook("two-dispatches")

    # Then each step is its own entry, with its own name but the same block
    assert [(step.name, step.block) for step in result.steps] == [
        ("dispatch_2030", "rolling_horizon_dispatch"),
        ("dispatch_2040", "rolling_horizon_dispatch"),
    ]
    assert result.steps[0].block_config_schema == result.steps[1].block_config_schema


def test_get_playbook_lists_a_nested_playbook_step_without_a_block() -> None:
    # Given a playbook with a step that runs another playbook rather than a block
    doc = parse_doc(
        {
            "name": "outer",
            "steps": [
                {"id": "cluster", "block": "cluster_time"},
                {
                    "id": "inner",
                    "playbook": {"name": "inner", "steps": [{"id": "x", "block": "cluster_time"}]},
                },
            ],
        }
    )
    service = PlaybookService(playbooks={"outer": doc}, catalogue=library_catalogue())

    # When
    result = service.get_playbook("outer")

    # Then the nested step is listed by name, with nothing block-specific
    nested_step = result.steps[1]
    assert nested_step.name == "inner"
    assert nested_step.block is None
    assert nested_step.block_summary is None
    assert nested_step.block_config_schema is None


def test_get_playbook_with_unknown_name_raises_404() -> None:
    # Given
    service = _library_service()

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.get_playbook("does-not-exist")
    assert exc_info.value.status_code == 404


def test_find_config_issues_finds_none_in_a_playbooks_own_default_config() -> None:
    # Given
    service = _library_service()
    default_config = service.default_config(_LIBRARY_PLAYBOOK)

    # When
    issues = service.find_config_issues(_LIBRARY_PLAYBOOK, default_config)

    # Then
    assert issues == []


def test_find_config_issues_points_each_issue_at_the_exact_setting() -> None:
    # Given the default config with a setting of the wrong type, and a misspelt one
    service = _library_service()
    default_config = service.default_config(_LIBRARY_PLAYBOOK)
    config = {
        **default_config,
        "expansion_overnight": {
            "perod": 2050,
            "optimize_config": {"linearized_unit_commitment": "yes"},
        },
    }

    # When
    issues = service.find_config_issues(_LIBRARY_PLAYBOOK, config)

    # Then each is reported on its own, with the path to that setting from the top of
    # the config, so a form can mark that one field
    assert issues == [
        PlaybookIssueResult(
            kind="config",
            message="there is no setting called 'perod'",
            step_path=["expansion_overnight"],
            config_path=["expansion_overnight", "perod"],
            input=None,
        ),
        PlaybookIssueResult(
            kind="config",
            message="'yes' is not of type 'boolean'",
            step_path=["expansion_overnight"],
            config_path=["expansion_overnight", "optimize_config", "linearized_unit_commitment"],
            input=None,
        ),
    ]


def test_find_config_issues_with_unknown_playbook_raises_404() -> None:
    # Given
    service = _library_service()

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.find_config_issues("does-not-exist", {})
    assert exc_info.value.status_code == 404


def test_raise_for_config_issues_refuses_with_422_listing_every_issue() -> None:
    # Given a config for a step the playbook does not have
    service = _library_service()
    config = {**service.default_config(_LIBRARY_PLAYBOOK), "not_a_step": {}}

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.raise_for_config_issues(_LIBRARY_PLAYBOOK, config)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == {
        "message": f"Playbook {_LIBRARY_PLAYBOOK!r} cannot run with this config",
        "issues": [
            {
                "kind": "config",
                "message": "there is no step called 'not_a_step', and it is not 'globals'",
                "step_path": [],
                "config_path": ["not_a_step"],
                "input": None,
            }
        ],
    }


def test_validate_playbook_config_without_a_config_checks_the_playbooks_default() -> None:
    # Given
    service = _library_service()

    # When
    result = service.validate_playbook_config(_LIBRARY_PLAYBOOK, config=None)

    # Then
    assert result == ValidatePlaybookConfigResult(valid=True, issues=[])


@pytest.mark.parametrize(
    ("mode", "issues"),
    [
        ("myopic", [("dims", ["expansion_myopic"], None)]),
        ("greenfield", [("inputs", [], ["globals", "expansion_mode"])]),
    ],
    ids=["myopic-needs-a-period", "not-offered"],
)
def test_validate_playbook_config_answers_with_every_issue_instead_of_refusing(
    mode, issues
) -> None:
    # Given the default config switched to its myopic branch, which needs a period
    # dimension the playbook's data does not have, or to a mode it does not offer
    service = _library_service()
    config = {**service.default_config(_LIBRARY_PLAYBOOK), "globals": {"expansion_mode": mode}}

    # When
    result = service.validate_playbook_config(_LIBRARY_PLAYBOOK, config=config)

    # Then the issues are the same ones a run with this config is refused with
    assert result.valid is False
    assert result.issues == service.find_config_issues(_LIBRARY_PLAYBOOK, config)
    found = [(issue.kind, issue.step_path, issue.config_path) for issue in result.issues]
    assert found == issues


def test_validate_playbook_config_with_unknown_playbook_raises_404() -> None:
    # Given
    service = _library_service()

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.validate_playbook_config("does-not-exist", config=None)
    assert exc_info.value.status_code == 404
