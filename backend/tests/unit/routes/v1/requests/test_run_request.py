from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from manta.routes.v1.requests.run_request import CreateRunRequest

_PLAYBOOK = {"name": "expand"}
_DATA_RECORD = {
    "store_url": "s3://bucket/store",
    "revision_uuid": UUID("3de02051-8918-45ab-a61b-980b3da170c4"),
}


def test_create_run_request_requires_a_project_uuid() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(playbook=_PLAYBOOK, data_record=_DATA_RECORD)


def test_create_run_request_rejects_an_invalid_project_uuid() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(project_uuid="not-a-uuid", playbook=_PLAYBOOK, data_record=_DATA_RECORD)


@pytest.mark.parametrize(
    "playbook",
    [None, {}, {"name": "expand", "config": "not-a-mapping"}],
    ids=["no_playbook", "no_name", "invalid_config"],
)
def test_create_run_request_requires_a_valid_playbook(playbook: dict | None) -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(project_uuid=uuid4(), playbook=playbook, data_record=_DATA_RECORD)


@pytest.mark.parametrize(
    "data_record",
    [
        None,
        {"revision_uuid": _DATA_RECORD["revision_uuid"]},
        {"store_url": _DATA_RECORD["store_url"]},
        {**_DATA_RECORD, "revision_uuid": "not-a-uuid"},
    ],
    ids=["no_data_record", "no_store_url", "no_revision_uuid", "invalid_revision_uuid"],
)
def test_create_run_request_requires_a_valid_data_record(data_record: dict | None) -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateRunRequest(project_uuid=uuid4(), playbook=_PLAYBOOK, data_record=data_record)


def test_create_run_request_accepts_the_required_fields() -> None:
    # Given
    project_uuid = uuid4()

    # When
    request = CreateRunRequest(
        project_uuid=project_uuid, playbook=_PLAYBOOK, data_record=_DATA_RECORD
    )

    # Then
    assert request.project_uuid == project_uuid
    assert request.playbook.name == "expand"
    assert request.data_record.store_url == _DATA_RECORD["store_url"]
    assert request.data_record.revision_uuid == _DATA_RECORD["revision_uuid"]


def test_create_run_request_defaults_config_to_none() -> None:
    # When
    request = CreateRunRequest(project_uuid=uuid4(), playbook=_PLAYBOOK, data_record=_DATA_RECORD)

    # Then: None, not {} — RunService tells apart "nothing supplied" (use the
    # library's own default_config) from "explicitly no overrides".
    assert request.playbook.config is None


def test_create_run_request_accepts_an_explicit_config() -> None:
    # When
    request = CreateRunRequest(
        project_uuid=uuid4(),
        playbook={**_PLAYBOOK, "config": {"globals": {"expansion_mode": "overnight"}}},
        data_record=_DATA_RECORD,
    )

    # Then
    assert request.playbook.config == {"globals": {"expansion_mode": "overnight"}}
