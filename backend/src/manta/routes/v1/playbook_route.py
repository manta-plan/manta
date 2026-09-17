from fastapi import APIRouter, Depends

from manta.services.playbook_service import PlaybookService
from manta.services.results.playbook_result import GetPlaybookResult, ListPlaybooksResult

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


@router.get("", response_model=ListPlaybooksResult)
def list_playbooks(service: PlaybookService = Depends()) -> ListPlaybooksResult:
    return service.list_playbooks()


@router.get("/{name}", response_model=GetPlaybookResult)
def get_playbook(name: str, service: PlaybookService = Depends()) -> GetPlaybookResult:
    return service.get_playbook(name)
