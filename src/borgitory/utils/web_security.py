"""
HTTP-layer security helpers: CSRF protection, login throttling, session token
hashing and redirect validation.
"""

import hashlib
import logging
import os
import time
from collections import deque
from typing import Deque, Dict, Iterable, Optional
from urllib.parse import urlparse

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def hash_session_token(token: str) -> str:
    """Hash a session token for storage.

    Tokens are 256-bit random values, so a fast unsalted hash is sufficient: the
    goal is that a leaked database does not hand out usable session cookies.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def safe_redirect_target(target: Optional[str], default: str = "/repositories") -> str:
    """Return ``target`` if it is a same-site relative path, else ``default``."""
    if not target:
        return default
    cleaned = target.replace("\\", "")
    parsed = urlparse(cleaned)
    if parsed.scheme or parsed.netloc or not cleaned.startswith("/"):
        return default
    return cleaned


def use_secure_cookies(request: Request) -> bool:
    """Decide whether to set the ``Secure`` cookie attribute.

    ``BORGITORY_SECURE_COOKIES=true|false`` forces the behaviour (needed when TLS
    terminates at a reverse proxy that uvicorn does not trust for forwarded
    headers); otherwise the request scheme decides.
    """
    override = os.getenv("BORGITORY_SECURE_COOKIES", "").strip().lower()
    if override in {"1", "true", "yes"}:
        return True
    if override in {"0", "false", "no"}:
        return False
    return request.url.scheme == "https"


class CrossSiteRequestMiddleware:
    """Reject cross-site state-changing requests (CSRF protection).

    Uses the browser-supplied ``Sec-Fetch-Site`` header when present (all
    current browsers send it), falling back to comparing ``Origin`` with the
    request host. Requests with neither header come from non-browser clients,
    which cannot be driven by CSRF, and are allowed.

    Unlike ``SameSite=Lax`` cookies alone, this also blocks *same-site*
    cross-origin requests, e.g. from another service on a different port of the
    same host.
    """

    def __init__(self, app: ASGIApp, trusted_origins: Iterable[str] = ()) -> None:
        self.app = app
        self.trusted_origins = {o.rstrip("/").lower() for o in trusted_origins if o}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS:
            headers = Headers(scope=scope)
            if self._is_cross_site(headers):
                logger.warning(
                    "Rejected cross-site %s %s (origin=%s, sec-fetch-site=%s)",
                    scope["method"],
                    scope.get("path"),
                    headers.get("origin"),
                    headers.get("sec-fetch-site"),
                )
                response = PlainTextResponse(
                    "Cross-site request rejected", status_code=403
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

    def _is_cross_site(self, headers: Headers) -> bool:
        origin = headers.get("origin")
        if origin and origin.rstrip("/").lower() in self.trusted_origins:
            return False

        fetch_site = headers.get("sec-fetch-site")
        if fetch_site is not None:
            # "none" means user-initiated (e.g. typed URL / bookmark)
            return fetch_site not in {"same-origin", "none"}

        if origin is None:
            return False
        if origin == "null":
            return True

        host = headers.get("x-forwarded-host") or headers.get("host") or ""
        return urlparse(origin).netloc.lower() != host.lower()


def trusted_origins_from_env() -> list[str]:
    """Comma-separated extra origins allowed to make state-changing requests."""
    raw = os.getenv("BORGITORY_TRUSTED_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]


class LoginThrottle:
    """In-memory sliding-window limiter for failed login attempts per client."""

    def __init__(
        self,
        max_failures: int = 10,
        window_seconds: float = 15 * 60,
        max_tracked_clients: int = 10_000,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.max_tracked_clients = max_tracked_clients
        self._failures: Dict[str, Deque[float]] = {}

    def _prune(self, key: str, now: float) -> Deque[float]:
        attempts = self._failures.get(key)
        if attempts is None:
            return deque()
        while attempts and now - attempts[0] > self.window_seconds:
            attempts.popleft()
        if not attempts:
            del self._failures[key]
        return attempts

    def retry_after(self, key: str) -> Optional[int]:
        """Seconds until ``key`` may try again, or ``None`` if not blocked."""
        now = time.monotonic()
        attempts = self._prune(key, now)
        if len(attempts) < self.max_failures:
            return None
        return max(1, int(self.window_seconds - (now - attempts[0])))

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        attempts = self._prune(key, now)
        if key not in self._failures:
            if len(self._failures) >= self.max_tracked_clients:
                self._failures.pop(next(iter(self._failures)))
            self._failures[key] = attempts
        attempts.append(now)

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)

    def clear(self) -> None:
        self._failures.clear()
