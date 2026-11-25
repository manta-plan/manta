import math
from functools import cache

from fastapi import APIRouter, Depends, HTTPException, Request, status

from manta.config.rate_limit_config import guest_logins_per_client_per_hour, guest_logins_per_hour
from manta.routes.v1.requests.login_request import LoginRequest
from manta.routes.v1.requests.refresh_token_request import RefreshTokenRequest
from manta.services.auth_service import AuthService
from manta.services.rate_limiter import RateLimiter
from manta.services.results.login_result import LoginResult

router = APIRouter(prefix="/auth", tags=["auth"])

_HOUR_SECONDS = 60 * 60


@cache
def _guest_limiters() -> tuple[RateLimiter, RateLimiter]:
    return (
        RateLimiter(guest_logins_per_client_per_hour(), _HOUR_SECONDS),
        RateLimiter(guest_logins_per_hour(), _HOUR_SECONDS),
    )


def limit_guest_logins(request: Request) -> None:
    # Keyed on the client address. Behind a reverse proxy, that is the end
    # user's address only if FORWARDED_ALLOW_IPS names the proxy (see main.py).
    # Otherwise every request has the proxy's address and shares one per-client
    # limit, which then refuses all guest logins before the global one is checked.
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


# There is no register endpoint for the MVP: login creates the user. See #273 for
# how one should be reintroduced.
