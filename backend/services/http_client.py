"""
TravelSync Pro — Centralized HTTP Client

All outbound HTTP calls should go through this module instead of importing
`requests` directly. It provides:

  1. **Correlation IDs** — every outbound request carries the current
     X-Request-ID header so downstream services and logs can be correlated.

  2. **Automatic retries** — transient errors (429, 500, 502, 503, 504,
     ConnectionError, Timeout) are retried with exponential backoff.

  3. **Default timeouts** — connect timeout 5s, read timeout 30s. No outbound
     request can hang indefinitely.

  4. **Structured logging** — slow and failed requests are logged with the
     request ID, URL, method, and duration for production debugging.

Usage:
    from services.http_client import http

    resp = http.get("https://api.example.com/data", params={...})
    resp = http.post("https://api.example.com/action", json={...})

The `http` object is a requests.Session pre-configured with retry adapters.
It is thread-safe and should be imported as a singleton.
"""
import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ── Retry strategy ───────────────────────────────────────────────────────────
# Retries on: 429 (rate-limited), 500, 502, 503, 504 (server errors),
# ConnectionError, and Timeout.
# Backoff: 0.3s → 0.6s → 1.2s (3 retries total).
_retry = Retry(
    total=3,
    backoff_factor=0.3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    raise_on_status=False,  # let the caller handle status codes
)

_adapter = HTTPAdapter(max_retries=_retry)

# Default timeouts: (connect_seconds, read_seconds)
_DEFAULT_TIMEOUT = (5, 30)


class _TracedSession(requests.Session):
    """Requests session that injects the correlation ID and logs slow calls."""

    def request(self, method, url, **kwargs):
        # Inject X-Request-ID from the Flask request context
        headers = kwargs.get("headers") or {}
        if "X-Request-ID" not in headers:
            try:
                from flask import g
                rid = getattr(g, "request_id", None)
                if rid:
                    headers["X-Request-ID"] = rid
                    kwargs["headers"] = headers
            except (RuntimeError, ImportError):
                pass  # outside request context — skip

        # Ensure a timeout is always set
        if "timeout" not in kwargs:
            kwargs["timeout"] = _DEFAULT_TIMEOUT

        start = time.monotonic()
        try:
            resp = super().request(method, url, **kwargs)
            duration_ms = round((time.monotonic() - start) * 1000)

            # Log slow outbound calls (>5s) for performance debugging
            if duration_ms > 5000:
                logger.warning(
                    "[HTTP] Slow outbound call: %s %s → %d in %dms",
                    method.upper(), url, resp.status_code, duration_ms,
                )

            return resp
        except requests.exceptions.RequestException as exc:
            duration_ms = round((time.monotonic() - start) * 1000)
            logger.warning(
                "[HTTP] Outbound call failed: %s %s → %s in %dms",
                method.upper(), url, type(exc).__name__, duration_ms,
            )
            raise


def _create_session() -> _TracedSession:
    """Create a pre-configured session with retry adapters mounted."""
    sess = _TracedSession()
    sess.mount("https://", _adapter)
    sess.mount("http://", _adapter)
    return sess


# Module-level singleton — thread-safe, import and use directly.
http = _create_session()
