from uuid import uuid4

import pytest
from pydantic import ValidationError

from manta.routes.v1.requests.run_request import CreateRunRequest


def _request(**overrides) -> CreateRunRequest:
    return CreateRunRequest(
        **{
            "project_uuid": uuid4(),
            "playbook_name": "cluster-expand-dispatch",
            "input_file": "network.nc",
            **overrides,
        }
    )


def test_create_run_request_requires_a_project_uuid() -> None:
    # When/Then
    with pytest.raises(ValidationError, match="project_uuid"):
        CreateRunRequest(playbook_name="cluster-expand-dispatch", input_file="network.nc")


def test_create_run_request_rejects_an_invalid_project_uuid() -> None:
    # When/Then
    with pytest.raises(ValidationError, match="project_uuid"):
        _request(project_uuid="not-a-uuid")


def test_create_run_request_accepts_a_playbook_run() -> None:
    # Given
    project_uuid = uuid4()

    # When
    request = _request(project_uuid=project_uuid, config={"globals": {}})

    # Then
    assert request.project_uuid == project_uuid
    assert request.playbook_name == "cluster-expand-dispatch"
    assert request.input_file == "network.nc"


def test_create_run_request_needs_a_playbook_name() -> None:
    # When/Then
    with pytest.raises(ValidationError, match="playbook_name"):
        CreateRunRequest(project_uuid=uuid4(), input_file="network.nc")


def test_create_run_request_needs_an_input_file() -> None:
    # When/Then: a run always starts from a file already in the project's storage.
    with pytest.raises(ValidationError, match="input_file"):
        CreateRunRequest(project_uuid=uuid4(), playbook_name="cluster-expand-dispatch")


def test_create_run_request_playbook_config_may_be_omitted() -> None:
    # When: defaults are used server-side when config is not given.
    request = _request()

    # Then
    assert request.config is None
