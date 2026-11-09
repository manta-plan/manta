from fastapi import APIRouter, Depends, Security

from manta.services.auth_service import authenticated_user
from manta.services.playbook_service import PlaybookService
from manta.services.results.playbook_result import GetPlaybookResult, ListPlaybooksResult

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


@router.get("", response_model=ListPlaybooksResult, dependencies=[Security(authenticated_user)])
def list_playbooks(service: PlaybookService = Depends()) -> ListPlaybooksResult:
    return service.list_playbooks()


@router.get(
    "/{playbook_name}",
    response_model=GetPlaybookResult,
    dependencies=[Security(authenticated_user)],
)
def get_playbook(playbook_name: str, service: PlaybookService = Depends()) -> GetPlaybookResult:
    return service.get_playbook(playbook_name)
