from fastapi import APIRouter, Depends, status

from manta.routes.v1.requests.project_request import CreateProjectRequest
from manta.services.project_service import ProjectService
from manta.services.results.project_result import CreateProjectResult

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=CreateProjectResult, status_code=status.HTTP_201_CREATED)
def create_project(
    request: CreateProjectRequest, service: ProjectService = Depends()
) -> CreateProjectResult:
    return service.create_project(name=request.name, description=request.description)
