from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from manta.entities import Project, User
from manta.services.errors import AuthorizationError

NOT_PROJECT_OWNER_MESSAGE = "The user does not own the selected project"


def ensure_project_owner(project: Project, user: User) -> None:
    if project.owner_id != user.id:
        raise AuthorizationError(detail=NOT_PROJECT_OWNER_MESSAGE)


def get_owned_project(db: Session, project_uuid: UUID, user: User) -> Project:
    project = db.query(Project).filter(Project.uuid == project_uuid).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_uuid} not found")
    ensure_project_owner(project, user)
    return project
