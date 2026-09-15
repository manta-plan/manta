from fastapi import APIRouter, Depends

from manta.routes.v1.requests.login_request import LoginRequest
from manta.routes.v1.requests.register_request import RegisterRequest
from manta.services.auth_service import AuthService
from manta.services.results.login_result import LoginResult
from manta.services.results.register_result import RegisterResult

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResult)
def login(request: LoginRequest, service: AuthService = Depends()) -> LoginResult:
    return service.login(request.username, request.password)


@router.post("/register", response_model=RegisterResult)
def register(request: RegisterRequest, service: AuthService = Depends()) -> RegisterResult:
    # No bearer token required here - idp_subject/idp_source are trusted as given,
    # not verified against a real token. Anyone can currently register any identity
    # pair. Fine only if something else (network boundary, a later re-add of token
    # verification, a trusted caller) is guarding this endpoint.
    return service.register(request.username, request.idp_subject, request.idp_source)
