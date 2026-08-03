import logging

from fastapi import Depends
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.entities import Project
from manta.services.results.project_result import CreateProjectResult

logger = logging.getLogger(__name__)


class ProjectService:
    def __init__(self, db: Session = Depends(get_db_session)) -> None:
        self.db = db

    def create_project(self, name: str, description: str | None) -> CreateProjectResult:
        project = Project(name=name, description=description)
        self.db.add(project)
        self.db.commit()

        logger.info("Created project %r (uuid=%s)", project.name, project.uuid)

        return CreateProjectResult(
            uuid=project.uuid,
            name=project.name,
            description=project.description,
            created_at=project.created_at,
        )
