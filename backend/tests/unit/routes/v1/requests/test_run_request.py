from uuid import uuid4

import pytest
from pydantic import ValidationError

from manta.routes.v1.requests.run_request import CreateRunRequest


def test_create_run_request_requires_a_project_uuid() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(playbook="cluster-expand-dispatch", data_record_url="s3://bucket/in.nc")


def test_create_run_request_rejects_an_invalid_project_uuid() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(
            project_uuid="not-a-uuid",
            playbook="cluster-expand-dispatch",
            data_record_url="s3://bucket/in.nc",
        )


def test_create_run_request_requires_a_playbook() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(project_uuid=uuid4(), data_record_url="s3://bucket/in.nc")


def test_create_run_request_requires_a_data_record_url() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(project_uuid=uuid4(), playbook="cluster-expand-dispatch")


def test_create_run_request_accepts_the_required_fields() -> None:
    # Given
    project_uuid = uuid4()

    # When
    request = CreateRunRequest(
        project_uuid=project_uuid,
        playbook="cluster-expand-dispatch",
        data_record_url="s3://bucket/in.nc",
    )

    # Then
    assert request.project_uuid == project_uuid
    assert request.playbook == "cluster-expand-dispatch"
    assert request.data_record_url == "s3://bucket/in.nc"


def test_create_run_request_defaults_config_to_none() -> None:
    # When
    request = CreateRunRequest(
        project_uuid=uuid4(),
        playbook="cluster-expand-dispatch",
        data_record_url="s3://bucket/in.nc",
    )

    # Then: None, not {} — RunService tells apart "nothing supplied" (use the
    # library's own default_config) from "explicitly no overrides".
    assert request.config is None


def test_create_run_request_accepts_an_explicit_config() -> None:
    # When
    request = CreateRunRequest(
        project_uuid=uuid4(),
        playbook="cluster-expand-dispatch",
        data_record_url="s3://bucket/in.nc",
        config={"globals": {"expansion_mode": "overnight"}},
    )

    # Then
    assert request.config == {"globals": {"expansion_mode": "overnight"}}
