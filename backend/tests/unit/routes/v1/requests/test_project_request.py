import pytest
from pydantic import ValidationError

from manta.routes.v1.requests.project_request import CreateProjectRequest


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
