from fastapi import APIRouter, Depends, Security

from manta.routes.v1.requests.playbook_request import ValidatePlaybookConfigRequest
from manta.services.auth_service import authenticated_user
from manta.services.playbook_service import PlaybookService
from manta.services.results.playbook_result import (
    GetPlaybookResult,
    ListPlaybooksResult,
    ValidatePlaybookConfigResult,
)

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


@router.post(
    "/{playbook_name}/validate",
    response_model=ValidatePlaybookConfigResult,
    dependencies=[Security(authenticated_user)],
)
def validate_playbook_config(
    playbook_name: str,
    request: ValidatePlaybookConfigRequest,
    service: PlaybookService = Depends(),
) -> ValidatePlaybookConfigResult:
    # Issues are the expected answer here, since an editor calls this as the user
    # edits: a config with issues is a 200 listing them, not an error status.
    return service.validate_playbook_config(playbook_name, config=request.config)
