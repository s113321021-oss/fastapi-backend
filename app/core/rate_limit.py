import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.password_auth import trust_proxy_headers


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        window_start = now - window_seconds
        events = self._events[key]
        while events and events[0] < window_start:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
        events.append(now)
        if not events:
            self._events.pop(key, None)


rate_limiter = InMemoryRateLimiter()


def client_ip(request: Request) -> str:
    if trust_proxy_headers():
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_rate_limit(request: Request, bucket: str, limit: int, window_seconds: int) -> None:
    rate_limiter.hit(f"{bucket}:{client_ip(request)}", limit, window_seconds)
