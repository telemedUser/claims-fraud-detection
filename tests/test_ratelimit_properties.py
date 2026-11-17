"""Property test for the lookup rate limiter (requirement 7.9)."""
from hypothesis import given, settings, strategies as st

from app.ratelimit import SlidingWindowLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


KEYS = ["ip:1", "ip:2", "pol:A", "pol:B"]
attempts = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=30),
        st.lists(st.sampled_from(KEYS), min_size=1, max_size=3),
    ),
    max_size=60,
)


# Feature: claims-fraud-detection-service, Property 25: Lookup rate limiting
# **Validates: Requirements 7.9**
@settings(max_examples=100)
@given(limit=st.integers(1, 6), window=st.integers(1, 40), seq=attempts)
def test_lookup_rate_limiting(limit, window, seq):
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit, float(window), clock)
    admitted: list[tuple[float, set[str]]] = []

    def count(key, now):
        return sum(1 for t, ks in admitted if key in ks and t > now - window)

    for advance, keys in seq:
        clock.now += advance
        now = clock.now
        expected_ok = all(count(k, now) < limit for k in keys)
        result = limiter.acquire(keys)

        assert (result is None) == expected_ok
        if result is None:
            admitted.append((now, set(keys)))
        else:
            assert result > 0
            # Rejected attempts are not counted: after waiting, a lone retry is admitted
            # (checked on a copy of the state so the main sequence is unaffected).
            probe = SlidingWindowLimiter(limit, float(window), lambda: now + result)
            for t, ks in admitted:
                for k in ks:
                    probe._hits.setdefault(k, __import__("collections").deque()).append(t)
            assert probe.acquire(keys) is None

        # Invariant: no key exceeds the limit in any window ending at an admitted time.
        for k in KEYS:
            for t, _ in admitted:
                in_window = [u for u, ks in admitted if k in ks and t - window < u <= t]
                assert len(in_window) <= limit
