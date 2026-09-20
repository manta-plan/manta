import pytest
from fastapi import HTTPException

from manta.services.playbook_service import PlaybookService


def test_list_playbooks_offers_the_library_playbooks() -> None:
    # Given
    service = PlaybookService()

    # When
    result = service.list_playbooks()

    # Then
    names = [playbook.name for playbook in result.items]
    assert "cluster-expand-dispatch" in names


def test_get_playbook_returns_its_document_and_default_config() -> None:
    # Given
    service = PlaybookService()

    # When
    result = service.get_playbook("cluster-expand-dispatch")

    # Then
    assert result.name == "cluster-expand-dispatch"
    assert [step["name"] for step in result.doc["steps"]] == [
        "cluster",
        "expansion_overnight",
        "expansion_myopic",
        "dispatch",
    ]
    assert result.default_config["globals"]["expansion_mode"] == "overnight"


def test_get_playbook_with_unknown_name_raises_404() -> None:
    # Given
    service = PlaybookService()

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.get_playbook("not-a-playbook")
    assert exc_info.value.status_code == 404


def test_a_playbook_validates_cleanly_with_its_default_config() -> None:
    # Given
    service = PlaybookService()
    doc, default_config = service.resolve("cluster-expand-dispatch")

    # When
    issues = service.validate(service.build(doc), default_config)

    # Then
    assert issues == []


def test_validation_needs_no_pypsa_and_points_at_the_broken_setting() -> None:
    # Given: the backend cannot import the pypsa blocks, so this exercises the
    # committed catalogue (json-schema) validation path.
    service = PlaybookService()
    doc, default_config = service.resolve("cluster-expand-dispatch")
    broken_config = {**default_config, "cluster": {"n_hours": "not-a-number"}}

    # When
    issues = service.validate(service.build(doc), broken_config)

    # Then
    assert len(issues) == 1
    assert issues[0].kind == "config"
    assert issues[0].step == "cluster"
    assert issues[0].field == ["n_hours"]


def test_validation_catches_a_missing_dimension_early() -> None:
    # Given: the myopic branch needs the investment_period dimension, which this
    # playbook's initial data does not declare (proposal requirement 6).
    service = PlaybookService()
    doc, default_config = service.resolve("cluster-expand-dispatch")
    myopic_config = {**default_config, "globals": {"expansion_mode": "myopic"}}

    # When
    issues = service.validate(service.build(doc), myopic_config)

    # Then
    assert any(issue.kind == "dims" and "investment_period" in issue.message for issue in issues)
