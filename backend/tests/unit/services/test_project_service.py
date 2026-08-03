from unittest.mock import MagicMock

import pytest

from manta.services.project_service import ProjectService


@pytest.mark.parametrize(
    "description",
    [None, "Offshore wind buildout scenario"],
    ids=["no_description", "with_description"],
)
def test_create_project(description, stub_add) -> None:
    # Given
    db = MagicMock()
    db.add.side_effect = stub_add
    service = ProjectService(db=db)

    # When
    result = service.create_project(name="North Sea Wind", description=description)

    # Then
    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert result.name == "North Sea Wind"
    assert result.description == description
    assert result.uuid == stub_add.uuid
    assert result.created_at == stub_add.created_at
