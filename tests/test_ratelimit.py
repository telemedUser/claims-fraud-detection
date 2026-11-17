"""Policy lookup rate limiting (requirement 7.9)."""
from app import ratelimit
from app.ratelimit import SlidingWindowLimiter, parse_rate

LOOKUP = {"policy_number": "pol-1001", "date_of_birth": "1992-04-18"}


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_parse_rate():
    assert parse_rate("5/minute") == (5, 60.0)
    assert parse_rate("2/hour") == (2, 3600.0)
    assert parse_rate("garbage") == (5, 60.0)
    assert parse_rate("0/minute") == (5, 60.0)


def test_window_slides():
    clock = FakeClock()
    lim = SlidingWindowLimiter(2, 60, clock)
    assert lim.acquire(["a"]) is None
    clock.t += 10
    assert lim.acquire(["a"]) is None
    wait = lim.acquire(["a"])
    assert wait is not None and round(wait) == 50
    clock.t += 50  # first attempt leaves the window
    assert lim.acquire(["a"]) is None


def test_keys_are_independent_but_all_must_pass():
    lim = SlidingWindowLimiter(1, 60, FakeClock())
    assert lim.acquire(["ip:1", "pol:A"]) is None
    assert lim.acquire(["ip:2", "pol:A"]) is not None  # policy key exhausted
    assert lim.acquire(["ip:2", "pol:B"]) is None  # rejected attempt did not consume ip:2


def test_lookup_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setenv("LOOKUP_RATE", "2/minute")
    ratelimit.reset_lookup_limiter()
    assert client.post("/api/policies/lookup", json=LOOKUP).status_code == 200
    assert client.post("/api/policies/lookup", json={**LOOKUP, "policy_number": " POL-1001 "}).status_code == 200
    r = client.post("/api/policies/lookup", json=LOOKUP)
    assert r.status_code == 429
    assert 1 <= int(r.headers["Retry-After"]) <= 60
    assert isinstance(r.json()["error"]["message"], str)


def test_failed_lookups_count_too(client, monkeypatch):
    monkeypatch.setenv("LOOKUP_RATE", "1/minute")
    ratelimit.reset_lookup_limiter()
    assert client.post("/api/policies/lookup", json={**LOOKUP, "date_of_birth": "1990-01-01"}).status_code == 404
    assert client.post("/api/policies/lookup", json=LOOKUP).status_code == 429
