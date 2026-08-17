from fastapi import APIRouter, Depends
from pydantic import BaseModel
from starlette.responses import JSONResponse

from manta.services.auth_service import MantaAuthenticationService

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResult(BaseModel):
    token: str
    """The authentication token if login is successful."""
    errors: list[str] = []
    """A list of errors that occurred during the login attempt."""


@router.post("/login")
def login(request: LoginRequest, service: MantaAuthenticationService = Depends()) -> JSONResponse:
    return service.login(request.username, request.password)
