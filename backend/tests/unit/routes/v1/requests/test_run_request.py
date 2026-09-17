from uuid import uuid4

import pytest
from pydantic import ValidationError

from manta.routes.v1.requests.run_request import CreateRunRequest


def test_create_run_request_requires_a_project_uuid() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest()


def test_create_run_request_rejects_an_invalid_project_uuid() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(project_uuid="not-a-uuid")


def test_create_run_request_accepts_a_valid_project_uuid() -> None:
    # Given
    project_uuid = uuid4()

    # When
    request = CreateRunRequest(project_uuid=project_uuid)

    # Then
    assert request.project_uuid == project_uuid


def test_create_run_request_defaults_num_pi_digits_to_100_000() -> None:
    # When
    request = CreateRunRequest(project_uuid=uuid4())

    # Then
    assert request.num_pi_digits == 100_000


@pytest.mark.parametrize("num_pi_digits", [0, -1, -100], ids=["zero", "negative_1", "negative_100"])
def test_create_run_request_rejects_a_non_positive_num_pi_digits(num_pi_digits) -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(project_uuid=uuid4(), num_pi_digits=num_pi_digits)


def test_create_run_request_accepts_a_positive_num_pi_digits() -> None:
    # When
    request = CreateRunRequest(project_uuid=uuid4(), num_pi_digits=500)

    # Then
    assert request.num_pi_digits == 500


def test_create_run_request_accepts_a_playbook_run() -> None:
    # When
    request = CreateRunRequest(
        project_uuid=uuid4(),
        playbook_name="cluster-expand-dispatch",
        config={"globals": {}},
        input_file="network.nc",
    )

    # Then
    assert request.playbook_name == "cluster-expand-dispatch"
    assert request.input_file == "network.nc"


def test_create_run_request_playbook_run_needs_an_input_file() -> None:
    # When/Then
    with pytest.raises(ValidationError, match="input_file"):
        CreateRunRequest(project_uuid=uuid4(), playbook_name="cluster-expand-dispatch")


def test_create_run_request_config_alone_makes_no_sense() -> None:
    # When/Then
    with pytest.raises(ValidationError, match="playbook_name"):
        CreateRunRequest(project_uuid=uuid4(), config={"globals": {}})


def test_create_run_request_input_file_alone_makes_no_sense() -> None:
    # When/Then
    with pytest.raises(ValidationError, match="playbook_name"):
        CreateRunRequest(project_uuid=uuid4(), input_file="network.nc")


def test_create_run_request_playbook_config_may_be_omitted() -> None:
    # When: defaults are used server-side when config is not given.
    request = CreateRunRequest(
        project_uuid=uuid4(), playbook_name="cluster-expand-dispatch", input_file="a.nc"
    )

    # Then
    assert request.config is None
