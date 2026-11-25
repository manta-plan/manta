import json
import logging

import pytest
from jwcrypto import jwk, jwt
from keycloak.exceptions import KeycloakConnectionError

from manta.config.keycloak_signing_keys import SigningKeyCache

TTL_SECONDS = 600
COOLDOWN_SECONDS = 30


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _FakeKeycloak:
    """Serves a JWKS from `certs()`, the way KeycloakOpenID.certs() does, and
    counts how often it was asked."""

    def __init__(self, *keys: jwk.JWK) -> None:
        self.keys = list(keys)
        self.error: Exception | None = None
        self.fetches = 0

    def certs(self) -> dict:
        self.fetches += 1
        if self.error is not None:
            raise self.error
        return {"keys": [json.loads(key.export_public()) for key in self.keys]}


def _key(kid: str) -> jwk.JWK:
    return jwk.JWK.generate(kty="EC", crv="P-256", kid=kid)


def _token(signed_with: jwk.JWK) -> str:
    token = jwt.JWT(
        header={"alg": "ES256", "kid": signed_with.get("kid")}, claims={"sub": "abc-123"}
    )
    token.make_signed_token(signed_with)
    return token.serialize()


def _kids(keys: jwk.JWKSet) -> set[str]:
    return {key.get("kid") for key in keys}


@pytest.fixture
def clock() -> _FakeClock:
    return _FakeClock()


def _cache(keycloak: _FakeKeycloak, clock: _FakeClock) -> SigningKeyCache:
    return SigningKeyCache(
        fetch_jwks=keycloak.certs,
        ttl_seconds=TTL_SECONDS,
        refetch_cooldown_seconds=COOLDOWN_SECONDS,
        clock=clock,
    )


def test_reuses_cached_keys(clock) -> None:
    # Given
    key = _key("k1")
    keycloak = _FakeKeycloak(key)
    cache = _cache(keycloak, clock)
    cache.keys_for(_token(key))
    clock.now += TTL_SECONDS - 1

    # When
    keys = cache.keys_for(_token(key))

    # Then
    assert _kids(keys) == {"k1"}
    assert keycloak.fetches == 1


def test_fetches_keys_again_once_ttl_has_passed(clock) -> None:
    # Given
    old_key, new_key = _key("k1"), _key("k2")
    keycloak = _FakeKeycloak(old_key)
    cache = _cache(keycloak, clock)
    cache.keys_for(_token(old_key))
    keycloak.keys.append(new_key)
    clock.now += TTL_SECONDS

    # When
    keys = cache.keys_for(_token(old_key))

    # Then
    assert _kids(keys) == {"k1", "k2"}
    assert keycloak.fetches == 2


def test_fetches_keys_again_for_a_token_signed_with_an_unknown_key(clock) -> None:
    # Given: Keycloak rotates its signing key after the keys were cached
    old_key, new_key = _key("k1"), _key("k2")
    keycloak = _FakeKeycloak(old_key)
    cache = _cache(keycloak, clock)
    cache.keys_for(_token(old_key))
    keycloak.keys = [new_key]
    clock.now += COOLDOWN_SECONDS

    # When
    keys = cache.keys_for(_token(new_key))

    # Then
    assert _kids(keys) == {"k2"}
    assert keycloak.fetches == 2


def test_limits_fetches_for_tokens_signed_with_unknown_keys(clock) -> None:
    # Given
    key = _key("k1")
    keycloak = _FakeKeycloak(key)
    cache = _cache(keycloak, clock)
    cache.keys_for(_token(key))
    clock.now += COOLDOWN_SECONDS
    cache.keys_for(_token(_key("unknown-1")))
    clock.now += COOLDOWN_SECONDS - 1

    # When
    cache.keys_for(_token(_key("unknown-2")))

    # Then
    assert keycloak.fetches == 2

    # When the cooldown has passed
    clock.now += 1
    cache.keys_for(_token(_key("unknown-3")))

    # Then
    assert keycloak.fetches == 3


def test_keeps_cached_keys_when_a_fetch_fails(clock, caplog) -> None:
    # Given
    key = _key("k1")
    keycloak = _FakeKeycloak(key)
    cache = _cache(keycloak, clock)
    cache.keys_for(_token(key))
    keycloak.error = KeycloakConnectionError("keycloak unavailable")
    clock.now += TTL_SECONDS

    # When
    with caplog.at_level(logging.WARNING):
        keys = cache.keys_for(_token(key))

    # Then
    assert _kids(keys) == {"k1"}
    assert "Could not fetch Keycloak's signing keys" in caplog.text

    # When asked again before the cooldown has passed, it doesn't retry the fetch
    clock.now += COOLDOWN_SECONDS - 1
    cache.keys_for(_token(key))

    # Then
    assert keycloak.fetches == 2

    # When Keycloak is back and the cooldown has passed
    keycloak.error = None
    clock.now += 1
    cache.keys_for(_token(key))

    # Then
    assert keycloak.fetches == 3


def test_raises_when_the_first_fetch_fails(clock) -> None:
    # Given
    keycloak = _FakeKeycloak()
    keycloak.error = KeycloakConnectionError("keycloak unavailable")
    cache = _cache(keycloak, clock)

    # When / Then
    with pytest.raises(KeycloakConnectionError):
        cache.keys_for(_token(_key("k1")))


def test_rejects_a_malformed_token_without_fetching(clock) -> None:
    # Given
    keycloak = _FakeKeycloak(_key("k1"))
    cache = _cache(keycloak, clock)

    # When / Then
    # _authenticate() treats ValueError as an invalid token, not a backend error
    with pytest.raises(ValueError):
        cache.keys_for("not-a-jwt")
    assert keycloak.fetches == 0
