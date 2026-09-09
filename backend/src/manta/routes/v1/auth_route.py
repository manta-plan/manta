from fastapi import APIRouter, Depends, HTTPException, status

from manta.errors.authentication_error import AuthenticationError
from manta.routes.v1.requests.login_request import LoginRequest
from manta.services.auth_service import AuthService
from manta.services.results.login_result import LoginResult

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResult)
def login(request: LoginRequest, service: AuthService = Depends()) -> LoginResult:
    try:
        return service.login(request.username, request.password)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        ) from e
