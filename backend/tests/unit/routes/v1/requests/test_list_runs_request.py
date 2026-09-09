from uuid import uuid4

import pytest
from pydantic import ValidationError

from manta.routes.v1.requests.list_runs_request import ListRunsRequest


def test_list_runs_request_requires_a_project_uuid() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        ListRunsRequest()


def test_list_runs_request_rejects_an_invalid_project_uuid() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        ListRunsRequest(project_uuid="not-a-uuid")


def test_list_runs_request_defaults_pagination_and_statuses() -> None:
    # Given
    project_uuid = uuid4()

    # When
    request = ListRunsRequest(project_uuid=project_uuid)

    # Then
    assert request.project_uuid == project_uuid
    assert request.limit == 10
    assert request.offset == 0
    assert request.statuses is None


@pytest.mark.parametrize("limit", [0, -1, 101], ids=["zero", "negative", "above_max"])
def test_list_runs_request_rejects_a_limit_outside_bounds(limit: int) -> None:
    # When/Then
    with pytest.raises(ValidationError):
        ListRunsRequest(project_uuid=uuid4(), limit=limit)


def test_list_runs_request_rejects_a_negative_offset() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        ListRunsRequest(project_uuid=uuid4(), offset=-1)


def test_list_runs_request_accepts_status_alias() -> None:
    # When
    request = ListRunsRequest(project_uuid=uuid4(), status=["RUNNING", "COMPLETED"])

    # Then
    assert request.statuses == ["RUNNING", "COMPLETED"]


def test_list_runs_request_accepts_statuses_field_name() -> None:
    # When
    request = ListRunsRequest(project_uuid=uuid4(), statuses=["FAILED"])

    # Then
    assert request.statuses == ["FAILED"]
