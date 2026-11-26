import pytest
from fastapi import HTTPException
from playbook.playbooks import parse_doc
from playbook_library import library_catalogue
from playbook_library.playbooks import LibraryPlaybook, library_playbooks

from manta.services.playbook_service import PlaybookService, config_of_run
from manta.services.results.playbook_result import (
    PlaybookIssueResult,
    ValidatePlaybookConfigResult,
)

_LIBRARY_PLAYBOOK = "expand"


def _library_service() -> PlaybookService:
    return PlaybookService(playbooks=library_playbooks(), catalogue=library_catalogue())


def _service_of(raw: dict) -> PlaybookService:
    doc = parse_doc(raw)
    playbooks = {doc.name: LibraryPlaybook(doc=doc, default_settings={})}
    return PlaybookService(playbooks=playbooks, catalogue=library_catalogue())


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
        "inputs": {"expansion_mode": "overnight"},
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
    assert steps["expansion_overnight"].when.config == "inputs.expansion_mode"
    assert steps["expansion_overnight"].when.equals == "overnight"
    assert steps["expansion_myopic"].when.equals == "myopic"
    assert steps["expansion_perfect"].when.equals == "perfect"
    assert steps["expansion_overnight"].inputs == {}


def test_get_playbook_offers_the_default_settings_without_what_with_sets() -> None:
    # Given
    service = _library_service()

    # When
    result = service.get_playbook("cluster-expand-dispatch")

    # Then
    assert result.default_config == {
        "inputs": {"expansion_mode": "overnight", "solver_name": "highs"},
        "cluster": {"n_hours": 3},
        "expansion_overnight": {},
        "expansion_myopic": {},
        "dispatch": {"optimize_config": {"horizon": 168, "overlap": 24}},
    }


def test_default_config_leaves_out_a_required_input() -> None:
    # Given
    service = _service_of(
        {
            "name": "needs",
            "inputs": {"hours": {"type": "number", "required": True}, "on": {"type": "boolean"}},
            "steps": [{"id": "cluster", "block": "cluster_time"}],
        }
    )

    # When/Then
    assert service.default_config("needs") == {"inputs": {"on": None}, "cluster": {}}


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
    service = _service_of(
        {
            "name": "conditional",
            "inputs": {
                "on": {"type": "boolean", "default": True},
                "mode": {"type": "string", "default": "a"},
            },
            "steps": [{"id": "cluster", "block": "cluster_time", "if": condition}],
        }
    )

    # When/Then: it is still listed...
    assert [item.name for item in service.list_playbooks().items] == ["conditional"]
    # ...but any request needing its conditions is refused, naming the step and condition
    with pytest.raises(HTTPException) as exc_info:
        request_playbook(service)
    assert exc_info.value.status_code == 501
    assert "'conditional'" in exc_info.value.detail
    assert "'cluster'" in exc_info.value.detail
    assert condition in exc_info.value.detail


@pytest.mark.parametrize(
    "request_playbook",
    [
        lambda service: service.get_playbook("named"),
        lambda service: service.validate_playbook_config("named", config=None),
    ],
    ids=["detail", "validate"],
)
def test_a_step_called_inputs_is_refused_with_a_501(request_playbook) -> None:
    # Given a playbook with a step whose id is the key of the inputs in a config
    service = _service_of({"name": "named", "steps": [{"id": "inputs", "block": "cluster_time"}]})

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        request_playbook(service)
    assert exc_info.value.status_code == 501
    assert "'named'" in exc_info.value.detail
    assert "Rename the step" in exc_info.value.detail


def test_get_playbook_describes_a_block_used_by_two_steps_once_per_step() -> None:
    # Given a playbook using the same block twice, under two step names
    service = _service_of(
        {
            "name": "two-dispatches",
            "steps": [
                {"id": "dispatch_2030", "block": "rolling_horizon_dispatch"},
                {"id": "dispatch_2040", "block": "rolling_horizon_dispatch"},
            ],
        }
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
    service = _service_of(
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

    # When
    result = service.get_playbook("outer")

    # Then the nested step is listed by name, with nothing block-specific
    nested_step = result.steps[1]
    assert nested_step.name == "inner"
    assert nested_step.block is None
    assert nested_step.block_summary is None
    assert nested_step.block_config_schema is None


def test_config_of_run_keeps_a_skipped_step_as_written_and_lists_nested_settings() -> None:
    # Given a step that does not run and whose `with` cannot be evaluated, and a nested
    # playbook whose step gets a setting from the run
    child = {
        "name": "child",
        "initial_data": {"dims": ["snapshot"]},
        "steps": [{"id": "x", "block": "cluster_time"}],
    }
    skipped = {
        "id": "cluster",
        "block": "cluster_time",
        "if": "${{ inputs.mode == 'on' }}",
        "with": {"n_hours": "${{ inputs.mode < 5 }}"},
    }
    raw = {
        "name": "nesting",
        "initial_data": {"dims": ["snapshot"]},
        "inputs": {"mode": {"type": "string", "default": "off"}},
        "steps": [skipped, {"id": "inner", "playbook": child}],
    }
    playbook = _service_of(raw).run_playbook("nesting", {"inner": {"x": {"n_hours": 3}}})

    # When
    config = config_of_run(playbook, {})

    # Then
    assert config == {
        "inputs": {"mode": "off"},
        "cluster": {"n_hours": "${{ inputs.mode < 5 }}"},
        "inner": {"x": {"n_hours": 3}},
    }


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


@pytest.mark.parametrize(
    ("changed", "found", "message"),
    [
        ({"cluster": None}, [("config", ["cluster"], ["cluster"])], "not None"),
        ({"cluster": [1]}, [("config", ["cluster"], ["cluster"])], "not [1]"),
        (
            {"cluster": {"n_hours": "${{ oops"}},
            [("config", ["cluster"], ["cluster", "n_hours"])],
            "contains an expression",
        ),
        ({"inputs": None}, [("inputs", [], ["inputs"])], "not None"),
        ({"inputs": ["a"]}, [("inputs", [], ["inputs"])], "not ['a']"),
        (
            {"dispatch": {"optimize_config": {"solver_name": "x"}}},
            [("config", ["dispatch"], ["dispatch", "optimize_config", "solver_name"])],
            "${{ inputs.solver_name }}",
        ),
    ],
)
def test_find_config_issues_answers_a_config_that_cannot_apply_with_issues(
    changed, found, message
) -> None:
    # Given the default config with one entry replaced by something that cannot apply
    service = _library_service()
    config = {**service.default_config("cluster-expand-dispatch"), **changed}

    # When
    result = service.validate_playbook_config("cluster-expand-dispatch", config=config)

    # Then
    assert result.valid is False
    assert [(i.kind, i.step_path, i.config_path) for i in result.issues] == found
    assert message in result.issues[0].message


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
                "message": (
                    "there is no step called 'not_a_step'. Use one of "
                    "['expansion_overnight', 'expansion_myopic', 'expansion_perfect']"
                ),
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
        ("greenfield", [("inputs", [], ["inputs", "expansion_mode"])]),
    ],
    ids=["myopic-needs-a-period", "not-offered"],
)
def test_validate_playbook_config_answers_with_every_issue_instead_of_refusing(
    mode, issues
) -> None:
    # Given the default config switched to its myopic branch, which needs a period
    # dimension the playbook's data does not have, or to a mode it does not offer
    service = _library_service()
    config = {**service.default_config(_LIBRARY_PLAYBOOK), "inputs": {"expansion_mode": mode}}

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
