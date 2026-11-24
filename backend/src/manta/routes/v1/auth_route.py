import math
from functools import cache

from fastapi import APIRouter, Depends, HTTPException, Request, status

from manta.config.rate_limit_config import guest_logins_per_client_per_hour, guest_logins_per_hour
from manta.routes.v1.requests.login_request import LoginRequest
from manta.routes.v1.requests.refresh_token_request import RefreshTokenRequest
from manta.routes.v1.requests.register_request import RegisterRequest
from manta.services.auth_service import AuthService
from manta.services.rate_limiter import RateLimiter
from manta.services.results.login_result import LoginResult
from manta.services.results.register_result import RegisterResult

router = APIRouter(prefix="/auth", tags=["auth"])

_HOUR_SECONDS = 60 * 60


@cache
def _guest_limiters() -> tuple[RateLimiter, RateLimiter]:
    return (
        RateLimiter(guest_logins_per_client_per_hour(), _HOUR_SECONDS),
        RateLimiter(guest_logins_per_hour(), _HOUR_SECONDS),
    )


def limit_guest_logins(request: Request) -> None:
    # Keyed on the direct peer's address. Behind a reverse proxy that's the
    # proxy, so run uvicorn with --proxy-headers and --forwarded-allow-ips set
    # to it; until then the global limit is what actually holds.
    client = request.client.host if request.client is not None else "unknown"
    per_client, everyone = _guest_limiters()

    retry_after = per_client.hit(client)
    if retry_after is None:
        retry_after = everyone.hit("*")
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many guest logins, try again later.",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )


@router.post("/login", response_model=LoginResult)
def login(request: LoginRequest, service: AuthService = Depends()) -> LoginResult:
    return service.login(request.username, request.password)


@router.post("/refresh", response_model=LoginResult)
def refresh(request: RefreshTokenRequest, service: AuthService = Depends()) -> LoginResult:
    return service.refresh(request.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: RefreshTokenRequest, service: AuthService = Depends()) -> None:
    service.logout(request.refresh_token)


@router.post(
    "/guest",
    response_model=LoginResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_guest_logins)],
)
def login_as_guest(service: AuthService = Depends()) -> LoginResult:
    # Unauthenticated by design: it backs the "Continue as guest" button. Each
    # call creates a new Keycloak user, hence the rate limit.
    return service.login_as_guest()


@router.post("/register", response_model=RegisterResult, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, service: AuthService = Depends()) -> RegisterResult:
    # No bearer token required here - idp_subject/idp_source are trusted as given,
    # not verified against a real token. Anyone can currently register any identity
    # pair. Fine only if something else (network boundary, a later re-add of token
    # verification, a trusted caller) is guarding this endpoint.
    return service.register(request.username, request.idp_subject, request.idp_source)
