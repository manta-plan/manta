import base64
import binascii
import hashlib
import hmac
import logging
import secrets
from enum import Enum

from fastapi import Depends
from fastapi.applications import FastAPI
from starlette import status
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
    BaseUser,
    UnauthenticatedUser,
)
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from manta.config.auth_config import MantaAuthConfig, get_auth_config

logger = logging.getLogger(__name__)


# OAuth2 scopes for API Requests
class AuthScopes(Enum):
    AUTHENTICATED = "authenticated"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


# basic API authentication flow:
#
# Login Endpoint
# POST /auth -> AuthResponse { "access_token": "" }
#
# Session Cookie -> create initial session
# Login -> Create a new session
# Logout -> Create a new session
# Session Data:
# (client side: cookie + access_token)
# expiration date
# 200 -> {"token": ""}
#
# Bearer Token (version 1):
# Base64-encoded version of the following binary format:
# | Byte Offset | Length | Description |
# | 0 | 2 | version, 0x0001 (unsigned, big-endian) |
# | 2 | 12 | salt (unsigned, big-endian) |
# | 14 | 2 | 2-byte payload_length (unsigned, big-endian), value > 0 and < 3072 |
# | 16 | payload_length | payload (utf-8 encoded username) |
# | 16+payload_length | 32 | signature (hmac-sha256)|
#
# The signature is computed of the preceding byte sequence (the token data minus
# the last 32 bytes)


def _generate_bearer_token(secret: bytes, user: str) -> str:
    payload: bytes = user.encode("utf-8")
    if len(secret) < 32 or len(secret) >= 3072:
        raise ValueError("signing key must be between 32 and 3072 bytes")
    if len(payload) <= 0 or len(payload) >= 3072:
        raise ValueError("payload must be between 1 and 3072 bytes")
    salt: bytes = secrets.token_bytes(12)
    token = bytearray()
    token.extend(b"\x00\x01")  # Version 1 Header
    token.extend(salt)
    logger.warning(f"salt: {salt.hex()}")
    token.extend(len(payload).to_bytes(2, byteorder="big"))
    token.extend(payload)
    signature = hmac.new(secret, token, hashlib.sha256).digest()
    token.extend(signature)
    return base64.b64encode(token).decode("utf-8")


def _parse_bearer_token(
    secret: bytes, bearer_token: str
) -> tuple[AuthCredentials, MantaUser] | None:
    try:
        token_bytes = base64.b64decode(bearer_token)
        version = int.from_bytes(token_bytes[0:2], byteorder="big")
        if version != 1:
            logger.error(f"Invalid version: {version}")
            raise ValueError("invalid version")
        logger.warning(f"salt: {token_bytes[2:14].hex()}")
        logger.warning(f"payload_length: {token_bytes[14:16].hex()}")
        expected_signature = hmac.new(secret, token_bytes[:-32], hashlib.sha256).digest()
        provided_signature = token_bytes[-32:]
        logger.warning(f"expected: {expected_signature.hex()}")
        logger.warning(f"provided: {provided_signature.hex()}")
        # compare_digest avoids timing attacks
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise ValueError("bad signature")  # TODO audit log this
        payload_length = int.from_bytes(token_bytes[14:16], byteorder="big")
        username = token_bytes[16 : 16 + payload_length].decode("utf-8")
    except ValueError as exc:
        logger.error("Error parsing bearer token", exc_info=exc)
        return None
    return AuthCredentials(["authenticated"]), MantaUser(user_id=1, user=username)


class MantaUser(BaseUser):
    """
    Represents a user authenticated via Manta.

    **Not** the same thing as the database record of a user - this is a
    lightweight representation specifically for the authentication domain.
    """

    # TODO: should user_id be a string? probably not.
    def __init__(self, user_id: int, user: str):
        self._user_id = user_id
        self._user = user

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return self._user

    # TODO: should this be a uuid?
    @property
    def identity(self) -> str:
        return str(self._user_id)


# starlette.authentication compatible backend
class MantaAuthenticationBackend(AuthenticationBackend):
    def __init__(self, auth_config: MantaAuthConfig):
        self._auth_config = auth_config

    async def authenticate(self, conn: HTTPConnection) -> tuple[AuthCredentials, BaseUser]:
        if "Authorization" not in conn.headers:
            return AuthCredentials([]), UnauthenticatedUser()
        auth_header = conn.headers["Authorization"]
        try:
            scheme, credentials = auth_header.split(" ")
            if scheme.lower() != "bearer":
                raise ValueError("Unsupported auth scheme")
            token = _parse_bearer_token(self._auth_config.api_signing_key, credentials)
            if token is None:
                return AuthCredentials([]), UnauthenticatedUser()
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            logger.error("Invalid bearer token", exc_info=exc)
            raise AuthenticationError("Invalid bearer token") from exc
        return token


def on_auth_error(conn: HTTPConnection, exc: Exception) -> JSONResponse:
    """Error-handling callback for starlette AuthenticationMiddleware"""
    return JSONResponse({"error": str(exc)}, status_code=status.HTTP_401_UNAUTHORIZED)


class MantaAuthenticationService:
    """Manages authentication/authorization for Manta requests."""

    def __init__(self, auth_config: MantaAuthConfig = Depends(get_auth_config)):
        self._auth_config = auth_config
        self._auth_backend = MantaAuthenticationBackend(auth_config)

    @property
    def auth_backend(self) -> MantaAuthenticationBackend:
        return self._auth_backend

    def add_middleware(self, app: FastAPI):
        app.add_middleware(
            AuthenticationMiddleware, backend=self._auth_backend, on_error=on_auth_error
        )

    def login(self, username: str, password: str) -> JSONResponse:
        # TODO: check credentials for real
        if (
            username != "alice" and password != "bob"  # noqa: S105
        ):  # TODO: replace this with a database-backed solution
            return JSONResponse(
                {"error": "Invalid credentials"}, status_code=status.HTTP_401_UNAUTHORIZED
            )
        return JSONResponse(
            {"token": _generate_bearer_token(self._auth_config.api_signing_key, username)}
        )
