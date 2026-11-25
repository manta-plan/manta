import logging
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from keycloak import KeycloakAdmin, KeycloakConnectionError, KeycloakOpenID
from keycloak.exceptions import KeycloakError
from keycloak.keycloak_openid import KeycloakAuthenticationError
from keycloak.openid_connection import KeycloakPostError
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.config.example_data_config import example_project_for_new_users_enabled
from manta.config.keycloak_config import get_keycloak_admin, get_keycloak_openid, well_known
from manta.entities import User
from manta.services.errors import AuthenticationError, BackendError
from manta.services.example_data_service import ExampleDataService
from manta.services.results.login_result import LoginResult
from manta.services.results.register_result import RegisterResult

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="v1/auth/login")

GUEST_USERNAME_PREFIX = "guest-"
# Keycloak requires an email on our realm's user profile. `.invalid` is reserved
# (RFC 2606), so no mail can ever be delivered to a guest's made-up address.
GUEST_EMAIL_DOMAIN = "guest.manta.invalid"

# User fields that cache an IdP claim, refreshed on login.
_SYNCED_CLAIMS = {"username": "preferred_username"}


def _find_user_by_credentials(db: Session, idp_subject: str, idp_source: str) -> User | None:
    return (
        db.query(User)
        .filter(User.idp_subject == idp_subject, User.idp_source == idp_source)
        .one_or_none()
    )


def _authenticate(db: Session, kc_client: KeycloakOpenID, token: str) -> User:
    try:
        claims = kc_client.decode_token(token, validate=True)
    except (KeycloakAuthenticationError, ValueError) as e:
        # ValueError: jwcrypto raises this (not a KeycloakError) for input
        # that isn't even well-formed JWT/JWS, e.g. a garbage bearer token.
        raise AuthenticationError from e
    except KeycloakError as e:  # catch-all for non-user errors
        raise BackendError from e

    # decode_token(validate=True) checks the signature (via JWKS) and exp/nbf,
    # but NOT iss or aud - check iss explicitly against our single known realm.
    # aud is intentionally not checked: manta-client has no audience mapper
    # configured yet, so the claim isn't meaningful.
    # TODO: configure / add an auth mapper
    expected_issuer = well_known(kc_client)["issuer"]
    if claims.get("iss") != expected_issuer:
        raise AuthenticationError(
            detail=f"unexpected issuer: got {claims.get('iss')!r}, expected {expected_issuer!r}"
        )
    user = _find_user_by_credentials(db, claims["sub"], claims["iss"])
    if user is None:
        raise AuthenticationError(detail="user is not registered")

    return user


def authenticated_user(
    db: Session = Depends(get_db_session),
    kc_client: KeycloakOpenID = Depends(get_keycloak_openid),
    token: str = Depends(oauth2_scheme),
) -> User:
    try:
        return _authenticate(db, kc_client, token)
    except AuthenticationError as e:
        logger.warning("Rejected token: %s", e)
        raise


class AuthService:
    def __init__(
        self,
        db: Session = Depends(get_db_session),
        kc_client: KeycloakOpenID = Depends(get_keycloak_openid),
        example_data: ExampleDataService = Depends(),
        kc_admin: KeycloakAdmin = Depends(get_keycloak_admin),
    ) -> None:
        self.db = db
        self.kc_client = kc_client
        self.example_data = example_data
        self.kc_admin = kc_admin

    def login(self, username: str, password: str) -> LoginResult:
        with _translate_keycloak_errors():
            token = self.kc_client.token(username, password)
            # Keycloak issued this token to us directly, so its claims need no validation.
            claims = self.kc_client.decode_token(token["access_token"], validate=False)
        user = self._find_or_create_user(
            claims.get("preferred_username", username), claims["sub"], claims["iss"]
        )
        self._sync_user_data_with_idp(user, claims)
        return LoginResult(
            access_token=token["access_token"],
            expires_in=token["expires_in"],
            refresh_token=token["refresh_token"],
            refresh_expires_in=token["refresh_expires_in"],
        )

    def refresh(self, refresh_token: str) -> LoginResult:
        with _translate_keycloak_errors():
            token = self.kc_client.refresh_token(refresh_token)
        # Keycloak issues a new refresh token on every refresh. Callers must
        # replace the one they hold: if the realm's "Revoke Refresh Token"
        # setting is turned on, the old one stops working after one use.
        return LoginResult(
            access_token=token["access_token"],
            expires_in=token["expires_in"],
            refresh_token=token["refresh_token"],
            refresh_expires_in=token["refresh_expires_in"],
        )

    def logout(self, refresh_token: str) -> None:
        # Ends the Keycloak session the refresh token belongs to, so neither it
        # nor any other refresh token from that session can be used again.
        # Access tokens already issued stay valid until they expire: they are
        # verified by signature alone, without asking Keycloak.
        # Keycloak accepts a token whose session has already ended, so logging
        # out twice is not an error.
        with _translate_keycloak_errors():
            self.kc_client.logout(refresh_token)

    def login_as_guest(self) -> LoginResult:
        """Creates a throwaway account and logs it in, so people can try manta
        without signing up.

        The guest is a real Keycloak user with a random username and password,
        so its tokens are ordinary Keycloak tokens: refresh, logout and every
        authenticated route work for it unchanged. The password is never shown
        to anyone, so once the guest's session ends the account can't be
        logged in to again.
        """
        username = f"{GUEST_USERNAME_PREFIX}{secrets.token_hex(8)}"
        password = secrets.token_urlsafe(32)

        with _translate_keycloak_admin_errors():
            idp_subject = self.kc_admin.create_user(
                {
                    "username": username,
                    "email": f"{username}@{GUEST_EMAIL_DOMAIN}",
                    "emailVerified": True,
                    "enabled": True,
                    "credentials": [{"type": "password", "value": password, "temporary": False}],
                }
            )

        try:
            with _translate_keycloak_errors():
                token = self.kc_client.token(username, password)
                idp_source = well_known(self.kc_client)["issuer"]
            self._create_user(username, idp_subject, idp_source)
        except Exception:
            # Don't leave behind a Keycloak account nobody can use.
            self._delete_keycloak_user(idp_subject)
            raise

        return LoginResult(
            access_token=token["access_token"],
            expires_in=token["expires_in"],
            refresh_token=token["refresh_token"],
            refresh_expires_in=token["refresh_expires_in"],
        )

    def register(self, username: str, idp_subject: str, idp_source: str) -> RegisterResult:
        user = self._find_or_create_user(username, idp_subject, idp_source)
        return RegisterResult(
            uuid=user.uuid,
            username=user.username,
            idp_subject=user.idp_subject,
            idp_source=user.idp_source,
            created_at=user.created_at,
        )

    def _find_or_create_user(self, username: str, idp_subject: str, idp_source: str) -> User:
        user = _find_user_by_credentials(self.db, idp_subject, idp_source)
        if user is None:
            # Access is gated in Keycloak alone: every identity it authenticates
            # gets a Manta user.
            user = self._create_user(username, idp_subject, idp_source)
        return user

    def _sync_user_data_with_idp(self, user: User, claims: dict[str, Any]) -> None:
        changed = False
        for field, claim in _SYNCED_CLAIMS.items():
            value = claims.get(claim)
            if value is not None and getattr(user, field) != value:
                setattr(user, field, value)
                changed = True
        if changed:
            self.db.commit()

    def _create_user(self, username: str, idp_subject: str, idp_source: str) -> User:
        user = self._add_user(username, idp_subject, idp_source)
        if example_project_for_new_users_enabled():
            self.example_data.create_project(owner=user)
        return user

    def _add_user(self, username: str, idp_subject: str, idp_source: str) -> User:
        user = User(username=username, idp_subject=idp_subject, idp_source=idp_source)
        self.db.add(user)
        self.db.commit()
        logger.info("Registered new user %r (uuid=%s)", user.username, user.uuid)
        return user

    def _delete_keycloak_user(self, idp_subject: str) -> None:
        try:
            self.kc_admin.delete_user(idp_subject)
        except KeycloakError:
            logger.exception("Could not delete orphaned guest %s from Keycloak", idp_subject)


@contextmanager
def _translate_keycloak_errors() -> Iterator[None]:
    # Maps python-keycloak errors from calls made with user credentials or a
    # refresh token (login, refresh, logout) onto manta's error types.
    try:
        yield
    except KeycloakAuthenticationError as request_error:  # authentication failed, keycloak side
        raise AuthenticationError from request_error
    except KeycloakPostError as post_error:
        # Keycloak rejects wrong credentials, and invalid, expired or revoked
        # refresh tokens, with `400 invalid_grant`, which python-keycloak
        # raises as a generic KeycloakPostError.
        if _is_invalid_grant(post_error):
            raise AuthenticationError from post_error
        raise BackendError from post_error
    except (
        KeycloakConnectionError
    ) as transient_error:  # Transient or configuration-based connection error
        raise BackendError from transient_error
    except (TypeError, AttributeError) as config_error:  # configuration-based connection error
        raise BackendError from config_error


@contextmanager
def _translate_keycloak_admin_errors() -> Iterator[None]:
    # Admin API calls are made with manta's own admin credentials, never the
    # caller's, so any failure - including Keycloak rejecting those
    # credentials - is a backend problem, not the caller's.
    try:
        yield
    except (KeycloakError, TypeError, AttributeError) as error:
        raise BackendError from error


def _is_invalid_grant(error: KeycloakPostError) -> bool:
    return error.response_code == 400 and b'"invalid_grant"' in (error.response_body or b"")
