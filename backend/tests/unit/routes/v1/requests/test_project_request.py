from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from manta.routes.v1.requests.project_request import (
    CreateProjectRequest,
    ListProjectsRequest,
    UpdateProjectRequest,
)


def test_create_project_request_requires_a_name() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateProjectRequest()


@pytest.mark.parametrize("name", ["", "a", "ab"], ids=["empty", "1_char", "2_chars"])
def test_create_project_request_rejects_a_name_shorter_than_3_chars(name) -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateProjectRequest(name=name)


def test_create_project_request_rejects_a_name_longer_than_128_chars() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        CreateProjectRequest(name="a" * 129)


@pytest.mark.parametrize("name", ["abc", "a" * 128], ids=["min_length", "max_length"])
def test_create_project_request_accepts_a_name_within_bounds(name) -> None:
    # When
    request = CreateProjectRequest(name=name)

    # Then
    assert request.name == name


def test_create_project_request_defaults_description_to_none() -> None:
    # When
    request = CreateProjectRequest(name="North Sea Wind")

    # Then
    assert request.description is None


def test_create_project_request_accepts_a_description() -> None:
    # When
    request = CreateProjectRequest(
        name="North Sea Wind", description="Offshore wind buildout scenario"
    )

    # Then
    assert request.description == "Offshore wind buildout scenario"


def test_update_project_request_requires_a_field() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        UpdateProjectRequest()


def test_update_project_request_rejects_a_null_name() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        UpdateProjectRequest(name=None)


@pytest.mark.parametrize("name", ["", "ab", "a" * 129], ids=["empty", "2_chars", "129_chars"])
def test_update_project_request_rejects_a_name_out_of_bounds(name) -> None:
    # When/Then
    with pytest.raises(ValidationError):
        UpdateProjectRequest(name=name)


def test_update_project_request_keeps_only_the_fields_sent() -> None:
    # When
    request = UpdateProjectRequest(name="New name")

    # Then
    assert request.model_dump(exclude_unset=True) == {"name": "New name"}


def test_update_project_request_accepts_a_null_description() -> None:
    # When
    request = UpdateProjectRequest(description=None)

    # Then
    assert request.model_dump(exclude_unset=True) == {"description": None}


@pytest.mark.parametrize("limit", [0, 101], ids=["below_min", "above_max"])
def test_list_projects_request_rejects_a_limit_out_of_bounds(limit) -> None:
    # When/Then
    with pytest.raises(ValidationError):
        ListProjectsRequest(limit=limit)


def test_list_projects_request_rejects_a_negative_offset() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        ListProjectsRequest(offset=-1)


@pytest.mark.parametrize("limit", [1, 100], ids=["min_limit", "max_limit"])
def test_list_projects_request_accepts_a_limit_within_bounds(limit) -> None:
    # When
    request = ListProjectsRequest(limit=limit)

    # Then
    assert request.limit == limit


def test_list_projects_request_defaults() -> None:
    # When
    request = ListProjectsRequest()

    # Then
    assert (request.limit, request.offset) == (10, 0)
    assert (request.order_by, request.order) == ("created_at", "desc")
    assert request.name is None
    assert request.description is None
    assert request.created_from is None
    assert request.created_to is None
    assert request.updated_from is None
    assert request.updated_to is None


@pytest.mark.parametrize("field", ["name", "description"])
def test_list_projects_request_rejects_an_empty_text_filter(field) -> None:
    # When/Then
    with pytest.raises(ValidationError):
        ListProjectsRequest(**{field: ""})


def test_list_projects_request_rejects_a_name_filter_longer_than_128_chars() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        ListProjectsRequest(name="a" * 129)


@pytest.mark.parametrize("order_by", ["name", "created_at", "updated_at"])
def test_list_projects_request_accepts_a_known_order_by(order_by) -> None:
    # When
    request = ListProjectsRequest(order_by=order_by)

    # Then
    assert request.order_by == order_by


@pytest.mark.parametrize(
    "order_by", ["uuid", "description", ""], ids=["uuid", "description", "empty"]
)
def test_list_projects_request_rejects_an_unknown_order_by(order_by) -> None:
    # When/Then
    with pytest.raises(ValidationError):
        ListProjectsRequest(order_by=order_by)


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_list_projects_request_accepts_a_known_order(order) -> None:
    # When
    request = ListProjectsRequest(order=order)

    # Then
    assert request.order == order


def test_list_projects_request_rejects_an_unknown_order() -> None:
    # When/Then
    with pytest.raises(ValidationError):
        ListProjectsRequest(order="sideways")


@pytest.mark.parametrize("prefix", ["created", "updated"])
def test_list_projects_request_rejects_a_range_that_ends_before_it_starts(prefix) -> None:
    # Given
    bounds = {
        f"{prefix}_from": datetime(2026, 11, 6, tzinfo=UTC),
        f"{prefix}_to": datetime(2026, 11, 5, tzinfo=UTC),
    }

    # When/Then
    with pytest.raises(ValidationError):
        ListProjectsRequest(**bounds)


@pytest.mark.parametrize("prefix", ["created", "updated"])
def test_list_projects_request_accepts_a_range_with_equal_bounds(prefix) -> None:
    # Given
    moment = datetime(2026, 11, 6, tzinfo=UTC)

    # When
    request = ListProjectsRequest(**{f"{prefix}_from": moment, f"{prefix}_to": moment})

    # Then
    assert getattr(request, f"{prefix}_from") == moment
    assert getattr(request, f"{prefix}_to") == moment


def test_list_projects_request_accepts_an_open_ended_range() -> None:
    # When
    request = ListProjectsRequest(updated_from=datetime(2026, 11, 6, tzinfo=UTC))

    # Then
    assert request.updated_to is None


def test_list_projects_request_parses_iso_datetimes() -> None:
    # When
    request = ListProjectsRequest(created_from="2026-11-06T10:00:00Z")

    # Then
    assert request.created_from == datetime(2026, 11, 6, 10, tzinfo=UTC)


def test_update_project_request_schema_does_not_advertise_a_null_name() -> None:
    # Given / When
    properties = UpdateProjectRequest.model_json_schema()["properties"]

    # Then
    assert properties["name"]["type"] == "string"
    assert "anyOf" not in properties["name"]
    assert "default" not in properties["name"]
