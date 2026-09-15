import logging
from functools import lru_cache

from fastapi import Depends
from fastapi.requests import Request
from fastapi.security import OAuth2PasswordBearer
from keycloak import KeycloakConnectionError, KeycloakOpenID
from keycloak.exceptions import KeycloakError
from keycloak.keycloak_openid import KeycloakAuthenticationError
from keycloak.openid_connection import KeycloakPostError
from sqlalchemy.orm import Session
from starlette.authentication import BaseUser

from manta.config.database_config import get_db_session
from manta.config.keycloak_config import get_keycloak_openid
from manta.entities import User
from manta.services.errors import AuthenticationError, BackendError
from manta.services.results.login_result import LoginResult

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="v1/auth/login")


@lru_cache
def _expected_issuer(kc_client: KeycloakOpenID) -> str:
    # Ask Keycloak what its issuer actually is, rather than constructing it from
    # KEYCLOAK_HOST/KEYCLOAK_PORT (the address *we* connect on) - those can differ
    # from Keycloak's own KC_HOSTNAME-derived issuer (e.g. testcontainers resolving
    # "0.0.0.0" as the connect host while Keycloak reports "localhost"). Cached
    # since get_keycloak_openid() always returns the same client instance and this
    # value is stable for the process lifetime.
    return kc_client.well_known()["issuer"]


class AuthService:
    def __init__(
        self,
        db: Session = Depends(get_db_session),
        kc_client: KeycloakOpenID = Depends(get_keycloak_openid),
    ) -> None:
        self.db = db
        self.kc_client = kc_client

    def login(self, username: str, password: str) -> LoginResult:
        try:
            token = self.kc_client.token(username, password)
        except KeycloakAuthenticationError as request_error:  # authentication failed, keycloak side
            raise AuthenticationError from request_error
        except (
            KeycloakConnectionError,
            KeycloakPostError,
        ) as transient_error:  # Transient or configuration-based connection error
            raise BackendError from transient_error
        except (TypeError, AttributeError) as config_error:  # configuration-based connection error
            raise BackendError from config_error
        return LoginResult(access_token=token["access_token"])

    def authenticate(self, token: str) -> User:
        try:
            claims = self.kc_client.decode_token(token, validate=True)
        except (KeycloakAuthenticationError, ValueError) as e:
            # ValueError: jwcrypto raises this (not a KeycloakError) for input
            # that isn't even well-formed JWT/JWS, e.g. a garbage bearer token.
            raise AuthenticationError from e
        except KeycloakError as e:  # catch-all for non-user errors
            raise BackendError from e

        # decode_token(validate=True) checks the signature (via JWKS) and exp/nbf,
        # but NOT iss or aud - check iss explicitly against our single known realm.
        # aud is intentionally not checked: manta-client has no audience mapper
        # configured yet, so the claim isn't meaningful. Known gap, not an oversight.
        expected_issuer = _expected_issuer(self.kc_client)
        if claims.get("iss") != expected_issuer:
            raise AuthenticationError(
                detail=f"unexpected issuer: got {claims.get('iss')!r}, expected {expected_issuer!r}"
            )

        idp_subject = claims["sub"]
        idp_source = claims["iss"]

        user = (
            self.db.query(User)
            .filter(User.idp_subject == idp_subject, User.idp_source == idp_source)
            .one_or_none()
        )
        if user is not None:
            return user

        # First time we've seen this identity - manta offloads user management to
        # the IdP entirely, so any validly-signed token JIT-provisions a local user.
        user = User(
            username=claims.get("preferred_username", idp_subject),
            idp_subject=idp_subject,
            idp_source=idp_source,
        )
        self.db.add(user)
        self.db.commit()

        logger.info("Provisioned new user %r (uuid=%s)", user.username, user.uuid)

        return user


def require_authenticated(request: Request):
    if request.state["manta_user"] is None:
        raise AuthenticationError(detail="authentication information not loaded")
    user: BaseUser = request.state.manta_user
    if not user.is_authenticated:
        raise AuthenticationError(detail="endpoint requires authentication")


def get_current_user(token: str = Depends(oauth2_scheme), auth: AuthService = Depends()) -> User:
    try:
        return auth.authenticate(token)
    except AuthenticationError as e:
        logger.warning("Rejected token: %s", e)
        raise
