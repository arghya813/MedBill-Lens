"""Shared FastAPI dependencies: rate limiting, auth hook, settings."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.errors import MedBillError, RateLimitError
from app.core.logging import get_logger

logger = get_logger(__name__)

_WINDOW_SECONDS = 60.0
_HITS: dict[str, deque[float]] = defaultdict(deque)
_LOCK = Lock()


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, config: Settings = Depends(get_settings)) -> None:
    """In-process, per-IP token bucket. Replace with Redis for multi-worker use."""
    if not config.rate_limit_enabled:
        return
    key = _client_key(request)
    now = time.monotonic()
    with _LOCK:
        bucket = _HITS[key]
        while bucket and now - bucket[0] > _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= config.rate_limit_requests:
            retry_after = int(_WINDOW_SECONDS - (now - bucket[0])) + 1
            raise RateLimitError(
                f"Limit of {config.rate_limit_requests} requests per minute exceeded."
            )
        bucket.append(now)


def require_auth_if_enabled(
    request: Request, config: Settings = Depends(get_settings)
) -> None:
    """Authentication architecture stub.

    Disabled by default so the demo runs with zero setup. Set
    ``AUTH_ENABLED=true`` and ``API_KEY`` to require a shared key; this is the
    seam where a real user/session system would go.
    """
    if not config.auth_enabled:
        return
    provided = request.headers.get(config.api_key_header, "")
    if not config.api_key or provided != config.api_key:
        raise _unauthorized()


def _unauthorized() -> MedBillError:
    error = MedBillError("A valid API key is required.")
    error.status_code = 401
    error.code = "unauthorized"
    error.user_message = "Authentication is required. Provide a valid API key."
    return error
