import pytest
from fastapi import HTTPException
from playbook.playbooks.yaml_io import parse_doc
from playbook_library import library_catalogue
from playbook_library.playbooks import LibraryPlaybook, library_playbooks

from manta.services.playbook_service import PlaybookService
from manta.services.results.playbook_result import PlaybookIssueResult

_LIBRARY_PLAYBOOK = "cluster-expand-dispatch"


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
        ("cluster", "cluster_time"),
        ("expansion_overnight", "overnight_capacity_expansion"),
        ("expansion_myopic", "myopic_capacity_expansion"),
        ("dispatch", "rolling_horizon_dispatch"),
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
    assert result.default_config == library_playbooks()[_LIBRARY_PLAYBOOK].default_config

    # ...and every step carries its block's description and settings schema
    # straight from the catalogue.
    steps = {step.name: step for step in result.steps}
    assert list(steps) == ["cluster", "expansion_overnight", "expansion_myopic", "dispatch"]
    for step in result.steps:
        block = catalogue.blocks[step.block]
        assert step.block_summary == block.doc
        assert step.block_config_schema == block.config_schema

    # And the step-level parts — conditions and wiring — are reported per step.
    assert steps["cluster"].when is None
    assert steps["expansion_overnight"].when.config == "globals.expansion_mode"
    assert steps["expansion_overnight"].when.equals == "overnight"
    assert steps["expansion_myopic"].when.equals == "myopic"
    assert steps["dispatch"].inputs == {"capacity_source": "${steps.expansion_overnight.output}"}
    assert steps["cluster"].inputs == {}
    # A setting fed by another step stays tagged as such, so a form can skip it.
    capacity_source = steps["dispatch"].block_config_schema["properties"]["capacity_source"]
    assert capacity_source["x-manta-input"] is True


def test_get_playbook_describes_a_block_used_by_two_steps_once_per_step() -> None:
    # Given a playbook using the same block twice, under two step names
    doc = parse_doc(
        {
            "name": "two-dispatches",
            "steps": [
                {"name": "dispatch_2030", "block": "rolling_horizon_dispatch"},
                {"name": "dispatch_2040", "block": "rolling_horizon_dispatch"},
            ],
        }
    )
    service = PlaybookService(
        playbooks={"two-dispatches": LibraryPlaybook(doc=doc, default_config={})},
        catalogue=library_catalogue(),
    )

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
                {"name": "cluster", "block": "cluster_time"},
                {"name": "inner", "playbook": {"name": "inner", "steps": []}},
            ],
        }
    )
    service = PlaybookService(
        playbooks={"outer": LibraryPlaybook(doc=doc, default_config={})},
        catalogue=library_catalogue(),
    )

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
    default_config = library_playbooks()[_LIBRARY_PLAYBOOK].default_config

    # When
    issues = service.find_config_issues(_LIBRARY_PLAYBOOK, default_config)

    # Then
    assert issues == []


def test_find_config_issues_points_each_issue_at_the_exact_setting() -> None:
    # Given the default config with a setting of the wrong type, and a misspelt one
    service = _library_service()
    default_config = library_playbooks()[_LIBRARY_PLAYBOOK].default_config
    config = {
        **default_config,
        "cluster": {"n_hours": 3, "n_hour": 6},
        "dispatch": {"optimize_config": {"horizon": "long"}},
    }

    # When
    issues = service.find_config_issues(_LIBRARY_PLAYBOOK, config)

    # Then each is reported on its own, with the path to that setting from the top of
    # the config, so a form can mark that one field
    assert issues == [
        PlaybookIssueResult(
            kind="config",
            message="there is no setting called 'n_hour'",
            step_path=["cluster"],
            config_path=["cluster", "n_hour"],
            input=None,
        ),
        PlaybookIssueResult(
            kind="config",
            message="'long' is not of type 'integer'",
            step_path=["dispatch"],
            config_path=["dispatch", "optimize_config", "horizon"],
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
    default_config = library_playbooks()[_LIBRARY_PLAYBOOK].default_config
    config = {**default_config, "not_a_step": {}}

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
