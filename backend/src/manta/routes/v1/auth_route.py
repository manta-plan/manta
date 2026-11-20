from fastapi import APIRouter, Depends, status

from manta.routes.v1.requests.login_request import LoginRequest
from manta.routes.v1.requests.refresh_token_request import RefreshTokenRequest
from manta.routes.v1.requests.register_request import RegisterRequest
from manta.services.auth_service import AuthService
from manta.services.results.login_result import LoginResult
from manta.services.results.register_result import RegisterResult

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResult)
def login(request: LoginRequest, service: AuthService = Depends()) -> LoginResult:
    return service.login(request.username, request.password)


@router.post("/refresh", response_model=LoginResult)
def refresh(request: RefreshTokenRequest, service: AuthService = Depends()) -> LoginResult:
    return service.refresh(request.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: RefreshTokenRequest, service: AuthService = Depends()) -> None:
    service.logout(request.refresh_token)


@router.post("/guest", response_model=LoginResult, status_code=status.HTTP_201_CREATED)
def login_as_guest(service: AuthService = Depends()) -> LoginResult:
    # Unauthenticated by design: it backs the "Continue as guest" button.
    # Each call creates a new Keycloak user, so anyone who can reach this
    # endpoint can create accounts in bulk - rate limit it before exposing
    # it publicly.
    return service.login_as_guest()


@router.post("/register", response_model=RegisterResult, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, service: AuthService = Depends()) -> RegisterResult:
    # No bearer token required here - idp_subject/idp_source are trusted as given,
    # not verified against a real token. Anyone can currently register any identity
    # pair. Fine only if something else (network boundary, a later re-add of token
    # verification, a trusted caller) is guarding this endpoint.
    return service.register(request.username, request.idp_subject, request.idp_source)
