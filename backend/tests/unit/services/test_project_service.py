from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from manta.entities import Project, Run, User
from manta.services.errors import AuthorizationError
from manta.services.project_service import ProjectService, UpdateProjectChanges
from manta.services.s3_file_storage_service import S3StorageError
from manta.services.user_service import UserService


@pytest.mark.parametrize(
    "description",
    [None, "Offshore wind buildout scenario"],
    ids=["no_description", "with_description"],
)
def test_create_project(description, mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))
    owner = User(username="alice")
    owner.id = 1

    # When
    result = service.create_project(name="North Sea Wind", description=description, owner=owner)

    # Then
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    assert result.name == "North Sea Wind"
    assert result.description == description
    assert result.uuid == mock_db.uuid
    assert result.created_at == mock_db.created_at
    assert result.updated_at == mock_db.created_at


def _project(owner_id: int = 1, name: str = "North Sea Wind", description: str | None = None):
    project = Project(name=name, description=description, owner_id=owner_id)
    project.id = 10
    project.uuid = uuid4()
    project.created_at = datetime.now(UTC)
    project.updated_at = project.created_at
    return project


def _user(user_id: int = 1) -> User:
    user = User(username="alice")
    user.id = user_id
    return user


def test_list_projects_returns_the_users_projects(mock_db_class) -> None:
    # Given
    projects = [_project(name="First one"), _project(name="Second one")]
    db = mock_db_class({Project: projects})
    service = ProjectService(db=db, user_service=UserService(db))

    # When
    result = service.list_projects(limit=10, offset=0, user=_user())

    # Then
    assert [item.name for item in result.items] == ["First one", "Second one"]
    assert (result.total, result.limit, result.offset) == (2, 10, 0)


def test_list_projects_returns_an_empty_page_without_projects(mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))

    # When
    result = service.list_projects(limit=10, offset=0, user=_user())

    # Then
    assert result.items == []
    assert result.total == 0


def _clause_values(clause) -> list:
    return list(clause.compile().params.values())


def test_list_projects_without_filters_only_scopes_to_the_owner(mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))

    # When
    service.list_projects(limit=10, offset=0, user=_user(user_id=7))

    # Then
    filters = mock_db.last_query.filters
    assert len(filters) == 1
    assert str(filters[0]) == "projects.owner_id = :owner_id_1"
    assert _clause_values(filters[0]) == [7]


def test_list_projects_passes_limit_and_offset_to_the_query(mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))

    # When
    result = service.list_projects(limit=5, offset=10, user=_user())

    # Then
    assert (mock_db.last_query.limit_value, mock_db.last_query.offset_value) == (5, 10)
    assert (result.limit, result.offset) == (5, 10)


@pytest.mark.parametrize("field", ["name", "description"])
def test_list_projects_filters_a_text_field_by_case_insensitive_substring(field, mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))

    # When
    service.list_projects(limit=10, offset=0, user=_user(), **{field: "Wind"})

    # Then
    filters = mock_db.last_query.filters
    assert len(filters) == 2
    assert f"projects.{field}" in str(filters[1])
    assert "LIKE" in str(filters[1])
    assert _clause_values(filters[1]) == ["%Wind%"]


def test_list_projects_treats_like_wildcards_in_a_filter_literally(mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))

    # When
    service.list_projects(limit=10, offset=0, user=_user(), name="50%_off\\")

    # Then
    assert _clause_values(mock_db.last_query.filters[1]) == ["%50\\%\\_off\\\\%"]


@pytest.mark.parametrize(
    ("bound", "expected_sql"),
    [
        ("created_from", "projects.created_at >= :created_at_1"),
        ("created_to", "projects.created_at <= :created_at_1"),
        ("updated_from", "projects.updated_at >= :updated_at_1"),
        ("updated_to", "projects.updated_at <= :updated_at_1"),
    ],
)
def test_list_projects_filters_by_an_inclusive_date_bound(bound, expected_sql, mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))
    moment = datetime(2026, 11, 6, tzinfo=UTC)

    # When
    service.list_projects(limit=10, offset=0, user=_user(), **{bound: moment})

    # Then
    filters = mock_db.last_query.filters
    assert len(filters) == 2
    assert str(filters[1]) == expected_sql
    assert _clause_values(filters[1]) == [moment]


def test_list_projects_applies_every_filter_given(mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))
    moment = datetime(2026, 11, 6, tzinfo=UTC)

    # When
    service.list_projects(
        limit=10,
        offset=0,
        user=_user(),
        name="wind",
        description="offshore",
        created_from=moment,
        created_to=moment,
        updated_from=moment,
        updated_to=moment,
    )

    # Then
    assert len(mock_db.last_query.filters) == 7


def test_list_projects_orders_by_newest_first_by_default(mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))

    # When
    service.list_projects(limit=10, offset=0, user=_user())

    # Then
    primary, tie_break = mock_db.last_query.order_by_args
    assert str(primary) == "projects.created_at DESC"
    assert str(tie_break) == "Project.id"


@pytest.mark.parametrize("order_by", ["name", "created_at", "updated_at"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_list_projects_orders_by_the_requested_column_and_direction(
    order_by, order, mock_db
) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))

    # When
    service.list_projects(limit=10, offset=0, user=_user(), order_by=order_by, order=order)

    # Then
    primary, tie_break = mock_db.last_query.order_by_args
    assert str(primary) == f"projects.{order_by} {order.upper()}"
    assert str(tie_break) == "Project.id"


def test_get_project(mock_db_class) -> None:
    # Given
    project = _project(description="Offshore wind buildout scenario")
    db = mock_db_class({Project: project})
    service = ProjectService(db=db, user_service=UserService(db))

    # When
    result = service.get_project(project.uuid, user=_user())

    # Then
    assert result.uuid == project.uuid
    assert result.name == project.name
    assert result.description == "Offshore wind buildout scenario"
    assert result.created_at == project.created_at
    assert result.updated_at == project.updated_at


def test_get_project_that_does_not_exist_is_a_404(mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.get_project(uuid4(), user=_user())
    assert exc_info.value.status_code == 404


def test_get_project_of_another_owner_is_a_403(mock_db_class) -> None:
    # Given
    project = _project(owner_id=2)
    db = mock_db_class({Project: project})
    service = ProjectService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(AuthorizationError) as exc_info:
        service.get_project(project.uuid, user=_user(user_id=1))
    assert exc_info.value.status_code == 403


def test_update_project_changes_only_the_given_fields(mock_db_class) -> None:
    # Given
    project = _project(description="Old description")
    db = mock_db_class({Project: project})
    service = ProjectService(db=db, user_service=UserService(db))

    # When
    result = service.update_project(
        project.uuid, changes=UpdateProjectChanges(name="New name"), user=_user()
    )

    # Then
    db.commit.assert_called_once()
    assert result.name == "New name"
    assert result.description == "Old description"


def test_update_project_can_clear_the_description(mock_db_class) -> None:
    # Given
    project = _project(description="Old description")
    db = mock_db_class({Project: project})
    service = ProjectService(db=db, user_service=UserService(db))

    # When
    result = service.update_project(
        project.uuid, changes=UpdateProjectChanges(description=None), user=_user()
    )

    # Then
    assert result.description is None
    assert result.name == "North Sea Wind"


def test_update_project_that_does_not_exist_is_a_404(mock_db) -> None:
    # Given
    service = ProjectService(db=mock_db, user_service=UserService(mock_db))

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.update_project(uuid4(), changes=UpdateProjectChanges(name="New name"), user=_user())
    assert exc_info.value.status_code == 404
    mock_db.commit.assert_not_called()


def test_update_project_of_another_owner_is_a_403(mock_db_class) -> None:
    # Given
    project = _project(owner_id=2)
    db = mock_db_class({Project: project})
    service = ProjectService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(AuthorizationError):
        service.update_project(
            project.uuid, changes=UpdateProjectChanges(name="New name"), user=_user(user_id=1)
        )
    assert project.name == "North Sea Wind"
    db.commit.assert_not_called()


def test_delete_project(mock_db_class) -> None:
    # Given a project with two runs
    project = _project()
    runs = [Run(project_id=10, prefect_flow_run_id=uuid4(), playbook="expand") for _ in range(2)]
    db = mock_db_class({Project: project, Run: runs})
    storage = MagicMock()
    run_service = MagicMock()
    service = ProjectService(
        db=db, storage=storage, run_service=run_service, user_service=UserService(db)
    )
    user = _user()

    # When
    service.delete_project(project.uuid, user=user)

    # Then the runs' Prefect flow runs and the project's S3 files are cleaned up,
    # and the project row is deleted
    run_service.ensure_no_active_runs.assert_called_once_with(project, user)
    run_service.delete_flow_runs.assert_called_once_with(project, user)
    storage.delete_project_files.assert_called_once_with(project.uuid, user)
    db.delete.assert_called_once_with(project)
    db.commit.assert_called_once()


def test_delete_project_with_active_runs_is_a_409_and_cleans_up_nothing(mock_db_class) -> None:
    # Given
    project = _project()
    db = mock_db_class({Project: project})
    storage = MagicMock()
    run_service = MagicMock()
    run_service.ensure_no_active_runs.side_effect = HTTPException(status_code=409)
    service = ProjectService(
        db=db, storage=storage, run_service=run_service, user_service=UserService(db)
    )

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.delete_project(project.uuid, user=_user())
    assert exc_info.value.status_code == 409
    run_service.delete_flow_runs.assert_not_called()
    storage.delete_project_files.assert_not_called()
    db.delete.assert_not_called()


def test_delete_project_keeps_the_project_when_prefect_cleanup_fails(mock_db_class) -> None:
    # Given
    project = _project()
    db = mock_db_class({Project: project})
    storage = MagicMock()

    run_service = MagicMock()
    run_service.delete_flow_runs.side_effect = RuntimeError("prefect down")
    service = ProjectService(
        db=db, storage=storage, run_service=run_service, user_service=UserService(db)
    )

    # When / Then
    with pytest.raises(RuntimeError):
        service.delete_project(project.uuid, user=_user())
    storage.delete_project_files.assert_not_called()
    db.delete.assert_not_called()


def test_delete_project_keeps_the_project_when_s3_cleanup_fails(mock_db_class) -> None:
    # Given
    project = _project()
    db = mock_db_class({Project: project})
    storage = MagicMock()
    storage.delete_project_files.side_effect = S3StorageError("s3 down")
    service = ProjectService(
        db=db, storage=storage, run_service=MagicMock(), user_service=UserService(db)
    )

    # When / Then
    with pytest.raises(S3StorageError):
        service.delete_project(project.uuid, user=_user())
    db.delete.assert_not_called()
    db.commit.assert_not_called()


def test_delete_project_that_does_not_exist_is_a_404(mock_db) -> None:
    # Given
    storage = MagicMock()
    service = ProjectService(db=mock_db, storage=storage, user_service=UserService(mock_db))

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.delete_project(uuid4(), user=_user())
    assert exc_info.value.status_code == 404
    mock_db.delete.assert_not_called()
    storage.delete_project_files.assert_not_called()


def test_delete_project_of_another_owner_is_a_403(mock_db_class) -> None:
    # Given
    project = _project(owner_id=2)
    db = mock_db_class({Project: project})
    storage = MagicMock()
    service = ProjectService(db=db, storage=storage, user_service=UserService(db))

    # When/Then
    with pytest.raises(AuthorizationError):
        service.delete_project(project.uuid, user=_user(user_id=1))
    db.delete.assert_not_called()
    storage.delete_project_files.assert_not_called()
