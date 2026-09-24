import pytest
from fastapi import HTTPException

from manta.services.playbook_service import PlaybookService


def test_list_playbooks_returns_summaries_without_nodes() -> None:
    # Given
    service = PlaybookService()

    # When
    result = service.list_playbooks()

    # Then
    assert [item.id for item in result.items] == [
        "pi-digit-statistics",
        "grid-demand-forecast",
        "renewable-dispatch-planning",
    ]
    assert [item.status for item in result.items] == [
        "available",
        "coming_soon",
        "coming_soon",
    ]
    assert not hasattr(result.items[0], "nodes")


def test_get_playbook_returns_detail_with_nodes() -> None:
    # Given
    service = PlaybookService()

    # When
    result = service.get_playbook("pi-digit-statistics")

    # Then
    assert result.id == "pi-digit-statistics"
    assert result.status == "available"
    assert len(result.nodes) == 1
    node = result.nodes[0]
    assert node.id == "pi-digit-statistics"
    assert len(node.config) == 1
    config_field = node.config[0]
    assert config_field.key == "num_pi_digits"
    assert config_field.required is True
    assert config_field.min == 1
    assert config_field.default == 10_000


def test_get_playbook_with_unknown_id_raises_404() -> None:
    # Given
    service = PlaybookService()

    # When / Then
    with pytest.raises(HTTPException) as exc_info:
        service.get_playbook("unknown-playbook")

    assert exc_info.value.status_code == 404
