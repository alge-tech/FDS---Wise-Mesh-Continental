"""Login rate limiting: sliding window per IP and per email."""

import pytest

from app.core import ratelimit
from app.core.ratelimit import RateLimited, SlidingWindow


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(ratelimit.time, "monotonic", c)
    return c


def test_window_allows_up_to_the_limit_per_key(clock: Clock) -> None:
    w = SlidingWindow(limit=3, window_seconds=60)
    assert [w.hit("a") for _ in range(4)] == [True, True, True, False]
    assert w.hit("b")  # keys are independent


def test_window_slides(clock: Clock) -> None:
    w = SlidingWindow(limit=2, window_seconds=60)
    assert w.hit("a")
    clock.now += 30
    assert w.hit("a")
    assert not w.hit("a")
    clock.now += 31  # the first hit has left the window
    assert w.hit("a")
    assert not w.hit("a")


def test_refused_hits_do_not_extend_the_lockout(clock: Clock) -> None:
    w = SlidingWindow(limit=1, window_seconds=60)
    assert w.hit("a")
    for _ in range(10):
        clock.now += 5
        assert not w.hit("a")
    clock.now += 11
    assert w.hit("a")


def test_reset_clears_every_key(clock: Clock) -> None:
    w = SlidingWindow(limit=1, window_seconds=60)
    w.hit("a")
    w.reset()
    assert w.hit("a")


def test_login_limit_is_per_email_case_insensitive(
    clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ratelimit, "login_by_ip", SlidingWindow(limit=100, window_seconds=60))
    monkeypatch.setattr(ratelimit, "login_by_email", SlidingWindow(limit=2, window_seconds=60))
    ratelimit.check_login_allowed("1.1.1.1", "Ops@Wise.test")
    ratelimit.check_login_allowed("2.2.2.2", "ops@wise.test")
    with pytest.raises(RateLimited) as exc:
        ratelimit.check_login_allowed("3.3.3.3", "OPS@WISE.TEST")
    assert exc.value.status_code == 429 and exc.value.code == "RATE_LIMITED"
    ratelimit.check_login_allowed("3.3.3.3", "other@wise.test")


def test_login_limit_is_per_ip(clock: Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ratelimit, "login_by_ip", SlidingWindow(limit=2, window_seconds=60))
    monkeypatch.setattr(ratelimit, "login_by_email", SlidingWindow(limit=100, window_seconds=60))
    ratelimit.check_login_allowed("1.1.1.1", "a@x.test")
    ratelimit.check_login_allowed("1.1.1.1", "b@x.test")
    with pytest.raises(RateLimited):
        ratelimit.check_login_allowed("1.1.1.1", "c@x.test")
