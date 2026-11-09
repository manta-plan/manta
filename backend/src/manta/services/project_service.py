import logging
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.entities import Project, Run, User
from manta.services.errors import AuthorizationError
from manta.services.results.project_result import (
    CreateProjectResult,
    GetProjectResult,
    ListProjectsResult,
    UpdateProjectResult,
)
from manta.services.run_service import delete_flow_runs
from manta.services.s3_file_storage_service import S3FileStorageService

logger = logging.getLogger(__name__)


class ProjectService:
    def __init__(
        self,
        db: Session = Depends(get_db_session),
        storage: S3FileStorageService = Depends(),
    ) -> None:
        self.db = db
        self.storage = storage

    def create_project(
        self, name: str, description: str | None, owner: User
    ) -> CreateProjectResult:
        project = Project(name=name, description=description, owner_id=owner.id)
        self.db.add(project)
        self.db.commit()

        logger.info("Created project %r (uuid=%s)", project.name, project.uuid)

        return CreateProjectResult(
            uuid=project.uuid,
            name=project.name,
            description=project.description,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

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
            items=[_to_get_result(project) for project in projects],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_project(self, project_uuid: UUID, user: User) -> GetProjectResult:
        return _to_get_result(self._get_owned_project(project_uuid, user))

    def update_project(
        self, project_uuid: UUID, changes: dict[str, Any], user: User
    ) -> UpdateProjectResult:
        """Applies `changes` (field name -> new value); fields not in it stay as they are."""
        project = self._get_owned_project(project_uuid, user)
        for field, value in changes.items():
            setattr(project, field, value)
        self.db.commit()

        logger.info("Updated project %r (uuid=%s)", project.name, project.uuid)

        return UpdateProjectResult(
            uuid=project.uuid,
            name=project.name,
            description=project.description,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    def delete_project(self, project_uuid: UUID, user: User) -> None:
        """Deletes the project and everything it owns: its runs' Prefect flow runs, its
        files in S3, then the project row (its runs' rows go with it, ON DELETE CASCADE).

        The external cleanup runs first, so a failure there leaves the project in
        place and the delete can simply be retried.
        """
        project = self._get_owned_project(project_uuid, user)
        runs = self.db.query(Run).filter(Run.project_id == project.id).all()
        delete_flow_runs([run.prefect_flow_run_id for run in runs])
        self.storage.delete_project_files(project.uuid)
        self.db.delete(project)
        self.db.commit()

        logger.info("Deleted project %r (uuid=%s)", project.name, project.uuid)

    def _get_owned_project(self, project_uuid: UUID, user: User) -> Project:
        project = self.db.query(Project).filter(Project.uuid == project_uuid).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_uuid} not found")
        if project.owner_id != user.id:
            raise AuthorizationError(detail="not the project owner")
        return project


def _contains(term: str) -> str:
    """LIKE pattern matching `term` as a literal substring."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _to_get_result(project: Project) -> GetProjectResult:
    return GetProjectResult(
        uuid=project.uuid,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
