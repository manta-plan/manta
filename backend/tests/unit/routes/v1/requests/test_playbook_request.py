from uuid import uuid4

import pytest
from pydantic import ValidationError

from manta.routes.v1.requests.playbook_request import (
    CreatePlaybookRunRequest,
    ValidatePlaybookRequest,
)


def test_validate_playbook_request_defaults_to_an_empty_config() -> None:
    # When
    request = ValidatePlaybookRequest()

    # Then
    assert request.config == {}


def test_validate_playbook_request_accepts_a_config_mapping() -> None:
    # When
    request = ValidatePlaybookRequest(config={"globals": {"expansion_mode": "overnight"}})

    # Then
    assert request.config["globals"]["expansion_mode"] == "overnight"


def test_create_playbook_run_request_requires_project_uuid_and_input_key() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreatePlaybookRunRequest()
    with pytest.raises(ValidationError):
        CreatePlaybookRunRequest(project_uuid=uuid4())
    with pytest.raises(ValidationError):
        CreatePlaybookRunRequest(input_key="examples/network.nc")


def test_create_playbook_run_request_rejects_an_empty_input_key() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreatePlaybookRunRequest(project_uuid=uuid4(), input_key="")


def test_create_playbook_run_request_defaults_config_to_none() -> None:
    # When
    request = CreatePlaybookRunRequest(project_uuid=uuid4(), input_key="examples/network.nc")

    # Then — "no config given" is distinct from "an empty config": the service
    # falls back to the playbook's default_config only for the former.
    assert request.config is None


def test_create_playbook_run_request_accepts_an_explicit_config() -> None:
    # When
    request = CreatePlaybookRunRequest(
        project_uuid=uuid4(),
        input_key="examples/network.nc",
        config={"cluster": {"n_hours": 4}},
    )

    # Then
    assert request.config == {"cluster": {"n_hours": 4}}
