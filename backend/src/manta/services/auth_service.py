import logging

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from keycloak import KeycloakConnectionError, KeycloakOpenID
from keycloak.exceptions import KeycloakError
from keycloak.keycloak_openid import KeycloakAuthenticationError
from keycloak.openid_connection import KeycloakPostError
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.config.keycloak_config import get_keycloak_openid, well_known
from manta.entities import User
from manta.services.errors import AuthenticationError, BackendError
from manta.services.results.login_result import LoginResult
from manta.services.results.register_result import RegisterResult

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="v1/auth/login")


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
    ) -> None:
        self.db = db
        self.kc_client = kc_client

    def login(self, username: str, password: str) -> LoginResult:
        # This doesn't currently update the user object if the Identity Provider
        # has new claims regarding the entity.
        # TODO: fix update functionality here
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

    def register(self, username: str, idp_subject: str, idp_source: str) -> RegisterResult:
        user = _find_user_by_credentials(self.db, idp_subject, idp_source)
        if user is None:
            # manta offloads user management to the IdP entirely - any identity
            # with a validly-signed token is eligible to register, no separate
            # approval step.
            user = User(username=username, idp_subject=idp_subject, idp_source=idp_source)
            self.db.add(user)
            self.db.commit()

            logger.info("Registered new user %r (uuid=%s)", user.username, user.uuid)
        # else: registering an already-registered identity is a no-op, not an error.

        return RegisterResult(
            uuid=user.uuid,
            username=user.username,
            idp_subject=user.idp_subject,
            idp_source=user.idp_source,
            created_at=user.created_at,
        )
