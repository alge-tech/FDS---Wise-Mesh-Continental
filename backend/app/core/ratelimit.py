"""In-memory sliding-window limiter for login attempts, per IP and per email."""

import time
from collections import defaultdict, deque
from threading import Lock

from app.core.errors import AppError


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"


class SlidingWindow:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_by_ip = SlidingWindow(limit=30, window_seconds=60)
login_by_email = SlidingWindow(limit=10, window_seconds=60)


def check_login_allowed(ip: str, email: str) -> None:
    if not login_by_ip.hit(ip) or not login_by_email.hit(email.lower()):
        raise RateLimited("Too many login attempts. Wait a minute and try again.")
