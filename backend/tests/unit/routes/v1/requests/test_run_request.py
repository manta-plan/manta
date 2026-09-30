from uuid import uuid4

import pytest
from pydantic import ValidationError

from manta.routes.v1.requests.run_request import CreateRunRequest


def test_create_run_request_requires_a_project_uuid_name_and_playbook_id() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest()


def test_create_run_request_rejects_an_invalid_project_uuid() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(
            project_uuid="not-a-uuid", name="My First Run", playbook_id="pi-digit-statistics"
        )


def test_create_run_request_rejects_an_empty_name() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(project_uuid=uuid4(), name="", playbook_id="pi-digit-statistics")


def test_create_run_request_defaults_playbook_config_to_empty() -> None:
    # When
    request = CreateRunRequest(
        project_uuid=uuid4(), name="My First Run", playbook_id="pi-digit-statistics"
    )

    # Then
    assert request.playbook_config == []


def test_create_run_request_accepts_a_name_playbook_id_and_playbook_config() -> None:
    # Given
    project_uuid = uuid4()

    # When
    request = CreateRunRequest(
        project_uuid=project_uuid,
        name="My First Run",
        playbook_id="pi-digit-statistics",
        playbook_config=[{"num_digits": 500}],
    )

    # Then
    assert request.project_uuid == project_uuid
    assert request.name == "My First Run"
    assert request.playbook_id == "pi-digit-statistics"
    assert request.playbook_config == [{"num_digits": 500}]
