from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from manta.entities import Project, User
from manta.services.errors import AuthorizationError
from manta.services.user_service import NOT_PROJECT_OWNER_MESSAGE, UserService


def _project(owner_id: int = 1) -> Project:
    project = Project(name="North Sea Wind", owner_id=owner_id)
    project.id = 10
    project.uuid = uuid4()
    project.created_at = datetime.now(UTC)
    return project


def _user(user_id: int = 1) -> User:
    user = User(username="alice")
    user.id = user_id
    return user


def test_get_owned_project_returns_the_users_project(mock_db_class) -> None:
    # Given
    project = _project()
    service = UserService(db=mock_db_class({Project: project}))

    # When
    result = service.get_owned_project(project.uuid, _user())

    # Then
    assert result is project


def test_get_owned_project_that_does_not_exist_is_a_404(mock_db) -> None:
    # Given
    service = UserService(db=mock_db)

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.get_owned_project(uuid4(), _user())
    assert exc_info.value.status_code == 404


def test_get_owned_project_of_another_owner_is_a_403(mock_db_class) -> None:
    # Given
    project = _project(owner_id=2)
    service = UserService(db=mock_db_class({Project: project}))

    # When/Then
    with pytest.raises(AuthorizationError) as exc_info:
        service.get_owned_project(project.uuid, _user(user_id=1))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == NOT_PROJECT_OWNER_MESSAGE


def test_ensure_project_owner_accepts_the_owner(mock_db) -> None:
    # When/Then
    UserService(db=mock_db).ensure_project_owner(_project(owner_id=1), _user(user_id=1))


def test_ensure_project_owner_rejects_another_user(mock_db) -> None:
    # When/Then
    with pytest.raises(AuthorizationError):
        UserService(db=mock_db).ensure_project_owner(_project(owner_id=1), _user(user_id=2))
