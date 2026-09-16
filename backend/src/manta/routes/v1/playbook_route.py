from uuid import UUID

from fastapi import APIRouter, Depends, status

from manta.routes.v1.requests.playbook_request import (
    CreatePlaybookRunRequest,
    ValidatePlaybookRequest,
)
from manta.services.playbook_service import PlaybookService
from manta.services.results.playbook_result import (
    CreatePlaybookRunResult,
    GetPlaybookResult,
    ListPlaybooksResult,
    ValidatePlaybookResult,
)

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


@router.get("", response_model=ListPlaybooksResult)
def list_playbooks(service: PlaybookService = Depends()) -> ListPlaybooksResult:
    return service.list_playbooks()


@router.get("/{playbook_uuid}", response_model=GetPlaybookResult)
def get_playbook(playbook_uuid: UUID, service: PlaybookService = Depends()) -> GetPlaybookResult:
    return service.get_playbook(playbook_uuid)


@router.post("/{playbook_uuid}/validate", response_model=ValidatePlaybookResult)
def validate_playbook(
    playbook_uuid: UUID,
    request: ValidatePlaybookRequest,
    service: PlaybookService = Depends(),
) -> ValidatePlaybookResult:
    # Problems are the expected answer here (an editor calls this as the user
    # types), so an invalid config is a 200 with issues, not an error status.
    return service.validate_playbook(playbook_uuid, config=request.config)


@router.post(
    "/{playbook_uuid}/runs",
    response_model=CreatePlaybookRunResult,
    status_code=status.HTTP_201_CREATED,
)
def create_playbook_run(
    playbook_uuid: UUID,
    request: CreatePlaybookRunRequest,
    service: PlaybookService = Depends(),
) -> CreatePlaybookRunResult:
    return service.create_run(
        playbook_uuid=playbook_uuid,
        project_uuid=request.project_uuid,
        input_key=request.input_key,
        config=request.config,
    )
