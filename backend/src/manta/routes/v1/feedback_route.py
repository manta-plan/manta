from fastapi import APIRouter, Depends, Security, status

from manta.routes.v1.requests.feedback_request import FeedbackRequest
from manta.services.auth_service import authenticated_user
from manta.services.feedback_service import FeedbackService
from manta.services.results.authenticated_user_result import AuthenticatedUserResult
from manta.services.results.feedback_result import SubmitFeedbackResult

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=SubmitFeedbackResult, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    request: FeedbackRequest,
    user: AuthenticatedUserResult = Security(authenticated_user),
    service: FeedbackService = Depends(),
) -> SubmitFeedbackResult:
    return service.submit(request, user)
