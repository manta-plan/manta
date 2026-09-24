from fastapi import APIRouter, Depends

from manta.services.playbook_service import PlaybookService
from manta.services.results.playbook_result import ListPlaybooksResult, PlaybookDetailResult

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


@router.get("", response_model=ListPlaybooksResult)
def list_playbooks(service: PlaybookService = Depends()) -> ListPlaybooksResult:
    return service.list_playbooks()


@router.get("/{playbook_id}", response_model=PlaybookDetailResult)
def get_playbook(playbook_id: str, service: PlaybookService = Depends()) -> PlaybookDetailResult:
    return service.get_playbook(playbook_id)
