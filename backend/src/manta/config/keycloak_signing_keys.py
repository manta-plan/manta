import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from jwcrypto import jwk, jwt
from keycloak.exceptions import KeycloakError

logger = logging.getLogger(__name__)


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
        self._ttl_seconds = ttl_seconds
        self._refetch_cooldown_seconds = refetch_cooldown_seconds
        self._clock = clock
        # authenticated_user() is a sync def, so FastAPI calls it from several
        # threadpool workers at once. The lock is held during a fetch, so requests
        # that arrive meanwhile wait for its result instead of fetching too.
        self._lock = threading.Lock()
        self._keys: jwk.JWKSet | None = None
        self._fetched_at = 0.0  # last successful fetch
        self._attempted_at = 0.0  # last fetch, successful or not

    def keys_for(self, token: str) -> jwk.JWKSet:
        """Returns the keys to validate `token` with, fetching them if needed.

        Raises ValueError (or another jwcrypto error) if `token` isn't a JWT, as
        KeycloakOpenID.decode_token() would, and KeycloakError if no keys have
        been fetched yet and fetching them fails.
        """
        kid = jwt.JWT(jwt=token).token.jose_header.get("kid")
        with self._lock:
            now = self._clock()
            if self._keys is None:
                return self._fetch(now)  # nothing cached to fall back on
            if self._needs_fetch(self._keys, now, kid):
                try:
                    return self._fetch(now)
                except KeycloakError:
                    logger.warning(
                        "Could not fetch Keycloak's signing keys; using the cached ones",
                        exc_info=True,
                    )
            return self._keys

    def _needs_fetch(self, keys: jwk.JWKSet, now: float, kid: str | None) -> bool:
        if now - self._attempted_at < self._refetch_cooldown_seconds:
            return False
        expired = now - self._fetched_at >= self._ttl_seconds
        unknown_kid = kid is not None and keys.get_key(kid) is None
        return expired or unknown_kid

    def _fetch(self, now: float) -> jwk.JWKSet:
        self._attempted_at = now
        keys = jwk.JWKSet()
        for key in self._fetch_jwks()["keys"]:
            keys.add(jwk.JWK(**key))
        self._keys = keys
        self._fetched_at = now
        return keys
