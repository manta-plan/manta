import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from cachetools import TTLCache
from jwcrypto import jwk, jwt
from keycloak.exceptions import KeycloakError

logger = logging.getLogger(__name__)

# The single key each TTLCache below is used with.
_JWKS = "jwks"


class SigningKeyCache:
    """Keeps Keycloak's token signing keys (the realm's JWKS) in memory, so
    validating a token doesn't need a request to Keycloak.

    The keys are fetched again once they are `ttl_seconds` old, or when a token
    names a key (its `kid`) that isn't cached, which is how a key rotation in
    Keycloak shows up here. The `kid` is read before the signature is checked,
    so anyone can send a token naming a key that doesn't exist: fetches are
    limited to one per `refetch_cooldown_seconds` so that such tokens can't make
    every request call Keycloak.

    If a fetch fails after keys have been cached, the cached keys stay in use and
    a warning is logged, so requests keep working while Keycloak is briefly
    unavailable. A key Keycloak has removed is trusted until a fetch succeeds.
    """

    def __init__(
        self,
        fetch_jwks: Callable[[], dict[str, Any]],
        ttl_seconds: float,
        refetch_cooldown_seconds: float = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch_jwks = fetch_jwks
        # authenticated_user() is a sync def, so FastAPI calls it from several
        # threadpool workers at once. The lock is held during a fetch, so requests
        # that arrive meanwhile wait for its result instead of fetching too. It
        # also guards the TTLCaches, which aren't thread-safe.
        self._lock = threading.Lock()
        # Holds the keys until they are ttl_seconds old.
        self._fresh_keys: TTLCache[str, jwk.JWKSet] = TTLCache(
            maxsize=1, ttl=ttl_seconds, timer=clock
        )
        # Holds an entry for refetch_cooldown_seconds after each fetch,
        # successful or not.
        self._recent_fetch: TTLCache[str, bool] = TTLCache(
            maxsize=1, ttl=refetch_cooldown_seconds, timer=clock
        )
        # The last keys fetched, still used once they've expired if fetching
        # them again fails.
        self._last_keys: jwk.JWKSet | None = None

    def keys_for(self, token: str) -> jwk.JWKSet:
        """Returns the keys to validate `token` with, fetching them if needed.

        Raises ValueError (or another jwcrypto error) if `token` isn't a JWT, as
        KeycloakOpenID.decode_token() would, and KeycloakError if no keys have
        been fetched yet and fetching them fails.
        """
        kid = jwt.JWT(jwt=token).token.jose_header.get("kid")
        with self._lock:
            keys = self._fresh_keys.get(_JWKS)
            if keys is not None and (kid is None or keys.get_key(kid) is not None):
                return keys
            if self._last_keys is not None and _JWKS in self._recent_fetch:
                return self._last_keys
            try:
                return self._fetch()
            except KeycloakError:
                if self._last_keys is None:
                    raise  # nothing cached to fall back on
                logger.warning(
                    "Could not fetch Keycloak's signing keys; using the cached ones",
                    exc_info=True,
                )
                return self._last_keys

    def _fetch(self) -> jwk.JWKSet:
        self._recent_fetch[_JWKS] = True
        keys = jwk.JWKSet()
        for key in self._fetch_jwks()["keys"]:
            keys.add(jwk.JWK(**key))
        self._fresh_keys[_JWKS] = keys
        self._last_keys = keys
        return keys
