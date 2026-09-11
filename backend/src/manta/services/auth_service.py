import logging
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from keycloak import KeycloakOpenID
from keycloak.exceptions import KeycloakError
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.config.keycloak_config import get_keycloak_openid
from manta.entities import User, UserCredential
from manta.errors.authentication_error import AuthenticationError
from manta.services.results.login_result import LoginResult

logger = logging.getLogger(__name__)

# Registers the bearer scheme (and its tokenUrl) with FastAPI's OpenAPI docs, so
# Swagger UI's "Authorize" button works — this is what routes depend on to extract
# the `Authorization: Bearer <token>` header, not just a plain string param.
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
        except KeycloakError as ke:
            raise AuthenticationError from ke
        return LoginResult(access_token=token["access_token"])

    def get_current_user(self, token: str) -> User:
        try:
            claims = self.kc_client.decode_token(token, validate=True)
        except (KeycloakError, ValueError) as e:
            # ValueError: jwcrypto raises this (not a KeycloakError) for input
            # that isn't even well-formed JWT/JWS, e.g. a garbage bearer token.
            raise AuthenticationError from e

        # decode_token(validate=True) checks the signature (via JWKS) and exp/nbf,
        # but NOT iss or aud - check iss explicitly against our single known realm.
        # aud is intentionally not checked: manta-client has no audience mapper
        # configured yet, so the claim isn't meaningful. Known gap, not an oversight.
        expected_issuer = _expected_issuer(self.kc_client)
        if claims.get("iss") != expected_issuer:
            raise AuthenticationError(
                f"unexpected issuer: got {claims.get('iss')!r}, expected {expected_issuer!r}"
            )

        idp_subject = claims["sub"]
        idp_source = claims["iss"]

        credential = (
            self.db.query(UserCredential)
            .filter(
                UserCredential.idp_subject == idp_subject, UserCredential.idp_source == idp_source
            )
            .one_or_none()
        )
        if credential is not None and credential.user_id is not None:
            user = self.db.query(User).filter(User.id == credential.user_id).one_or_none()
            if user is not None:
                return user

        # First time we've seen this identity - manta offloads user management to
        # the IdP entirely, so any validly-signed token JIT-provisions a local user.
        user = User(username=claims.get("preferred_username", idp_subject))
        self.db.add(user)
        self.db.flush()  # populate user.id before the credential references it
        self.db.add(UserCredential(user_id=user.id, idp_subject=idp_subject, idp_source=idp_source))
        self.db.commit()

        logger.info("Provisioned new user %r (uuid=%s)", user.username, user.uuid)

        return user


def get_current_user(token: str = Depends(oauth2_scheme), auth: AuthService = Depends()) -> User:
    try:
        return auth.get_current_user(token)
    except AuthenticationError as e:
        logger.warning("Rejected token: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from e
