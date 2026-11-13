from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.entities import Project, User
from manta.services.errors import AuthorizationError

NOT_PROJECT_OWNER_MESSAGE = "The user does not own the selected project"


class UserService:
    """What a user may access. Depends on the database only, so any service can
    inject it without an import cycle."""

    def __init__(self, db: Session = Depends(get_db_session)) -> None:
        self.db = db

    def ensure_project_owner(self, project: Project, user: User) -> None:
        if project.owner_id != user.id:
            raise AuthorizationError(detail=NOT_PROJECT_OWNER_MESSAGE)

    def get_owned_project(self, project_uuid: UUID, user: User) -> Project:
        project = self.db.query(Project).filter(Project.uuid == project_uuid).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_uuid} not found")
        self.ensure_project_owner(project, user)
        return project
