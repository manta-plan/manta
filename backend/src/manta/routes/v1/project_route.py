from fastapi import APIRouter, Depends, Security, status

from manta.entities import User
from manta.routes.v1.requests.project_request import CreateProjectRequest
from manta.services.auth_service import require_authenticated
from manta.services.project_service import ProjectService
from manta.services.results.project_result import CreateProjectResult

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post(
    "",
    response_model=CreateProjectResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(require_authenticated)],
)
def create_project(
    request: CreateProjectRequest,
    service: ProjectService = Depends(),
    current_user: User = Security(require_authenticated),
) -> CreateProjectResult:
    return service.create_project(
        name=request.name, description=request.description, owner=current_user
    )
