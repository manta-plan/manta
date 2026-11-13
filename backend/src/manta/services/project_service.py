import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.entities import Project, User
from manta.services.results.project_result import ListProjectsResult, ProjectResult
from manta.services.run_service import RunService
from manta.services.s3_file_storage_service import S3FileStorageService
from manta.services.user_service import UserService

logger = logging.getLogger(__name__)


class _Unset:
    """Marks a field that was not sent, as opposed to `None`, which clears it."""


UNSET = _Unset()


@dataclass(frozen=True)
class UpdateProjectChanges:
    name: str | _Unset = UNSET
    description: str | None | _Unset = UNSET


class ProjectService:
    def __init__(
        self,
        db: Session = Depends(get_db_session),
        storage: S3FileStorageService = Depends(),
        run_service: RunService = Depends(),
        user_service: UserService = Depends(),
    ) -> None:
        self.db = db
        self.storage = storage
        self.run_service = run_service
        self.user_service = user_service

    def create_project(self, name: str, description: str | None, owner: User) -> ProjectResult:
        project = Project(name=name, description=description, owner_id=owner.id)
        self.db.add(project)
        self.db.commit()

        logger.info("Created project %r (uuid=%s)", project.name, project.uuid)

        return _to_result(project)

    def list_projects(
        self,
        limit: int,
        offset: int,
        user: User,
        name: str | None = None,
        description: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        updated_from: datetime | None = None,
        updated_to: datetime | None = None,
        order_by: Literal["name", "created_at", "updated_at"] = "created_at",
        order: Literal["asc", "desc"] = "desc",
    ) -> ListProjectsResult:
        """The user's own projects. `name` and `description` are case-insensitive
        substring filters; the `*_from`/`*_to` bounds are inclusive. All filters
        are ANDed when several are given. Default: newest first."""
        query = self.db.query(Project).filter(Project.owner_id == user.id)
        if name is not None:
            query = query.filter(Project.name.ilike(_contains(name), escape="\\"))
        if description is not None:
            query = query.filter(Project.description.ilike(_contains(description), escape="\\"))
        if created_from is not None:
            query = query.filter(Project.created_at >= created_from)
        if created_to is not None:
            query = query.filter(Project.created_at <= created_to)
        if updated_from is not None:
            query = query.filter(Project.updated_at >= updated_from)
        if updated_to is not None:
            query = query.filter(Project.updated_at <= updated_to)
        total = query.count()

        column = {
            "name": Project.name,
            "created_at": Project.created_at,
            "updated_at": Project.updated_at,
        }[order_by]
        direction = column.asc() if order == "asc" else column.desc()
        # Project.id tie-break keeps offset pagination stable across equal values.
        projects = query.order_by(direction, Project.id).offset(offset).limit(limit).all()

        return ListProjectsResult(
            items=[_to_result(project) for project in projects],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_project(self, project_uuid: UUID, user: User) -> ProjectResult:
        return _to_result(self.user_service.get_owned_project(project_uuid, user))

    def update_project(
        self, project_uuid: UUID, changes: UpdateProjectChanges, user: User
    ) -> ProjectResult:
        project = self.user_service.get_owned_project(project_uuid, user)
        if changes.name is not UNSET:
            project.name = changes.name
        if changes.description is not UNSET:
            project.description = changes.description
        self.db.commit()

        logger.info("Updated project %r (uuid=%s)", project.name, project.uuid)

        return _to_result(project)

    def delete_project(self, project_uuid: UUID, user: User) -> None:
        """Deletes the project and everything it owns: its runs' Prefect flow runs, its
        files in S3, then the project row (its runs' rows go with it, ON DELETE CASCADE).
        Refused with a 409 while any of its runs is still active.

        The external cleanup runs first, so a failure there leaves the project in
        place and the delete can simply be retried.
        """
        project = self.user_service.get_owned_project(project_uuid, user)
        self.run_service.ensure_no_active_runs(project, user)
        self.run_service.delete_flow_runs(project, user)
        self.storage.delete_project_files(project_uuid, user)
        self.db.delete(project)
        self.db.commit()

        logger.info("Deleted project %r (uuid=%s)", project.name, project.uuid)


def _contains(term: str) -> str:
    """LIKE pattern matching `term` as a literal substring."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _to_result(project: Project) -> ProjectResult:
    return ProjectResult(
        uuid=project.uuid,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
