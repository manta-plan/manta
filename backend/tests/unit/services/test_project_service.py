import pytest

from manta.services.project_service import ProjectService


@pytest.mark.parametrize(
    "description",
    [None, "Offshore wind buildout scenario"],
    ids=["no_description", "with_description"],
)
def test_create_project(description, mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db)

    # When
    result = service.create_project(name="North Sea Wind", description=description)

    # Then
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    assert result.name == "North Sea Wind"
    assert result.description == description
    assert result.uuid == mock_db.uuid
    assert result.created_at == mock_db.created_at
