from manta.services.rate_limiter import RateLimiter


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_hits_up_to_the_limit_then_refuses() -> None:
    # Given
    limiter = RateLimiter(limit=2, window_seconds=60, clock=_Clock())

    # When / Then
    assert limiter.hit("a") is None
    assert limiter.hit("a") is None
    assert limiter.hit("a") == 60


def test_counts_each_key_separately() -> None:
    # Given
    limiter = RateLimiter(limit=1, window_seconds=60, clock=_Clock())
    limiter.hit("a")

    # When / Then
    assert limiter.hit("b") is None


def test_allows_hits_again_once_the_oldest_leaves_the_window() -> None:
    # Given
    clock = _Clock()
    limiter = RateLimiter(limit=2, window_seconds=60, clock=clock)
    limiter.hit("a")
    clock.now += 30
    limiter.hit("a")

    # When - the first hit is 50s old, so it's still in the window
    clock.now += 20
    # Then
    assert limiter.hit("a") == 10

    # When - the first hit has left the window
    clock.now += 10
    # Then
    assert limiter.hit("a") is None


def test_refused_hits_do_not_extend_the_wait() -> None:
    # Given
    clock = _Clock()
    limiter = RateLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("a")

    # When - hammering while limited
    for _ in range(5):
        clock.now += 10
        limiter.hit("a")

    # Then - still allowed 60s after the one recorded hit
    clock.now += 10
    assert limiter.hit("a") is None


def test_forgets_keys_whose_hits_have_all_expired() -> None:
    # Given
    clock = _Clock()
    limiter = RateLimiter(limit=1, window_seconds=60, clock=clock)
    for client in range(100):
        limiter.hit(str(client))

    # When
    clock.now += 61
    limiter.hit("new")

    # Then
    assert list(limiter._hits) == ["new"]
