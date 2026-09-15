from fastapi import APIRouter, Depends

from manta.routes.v1.requests.login_request import LoginRequest
from manta.services.auth_service import AuthService
from manta.services.results.login_result import LoginResult

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResult)
def login(request: LoginRequest, service: AuthService = Depends()) -> LoginResult:
    return service.login(request.username, request.password)
