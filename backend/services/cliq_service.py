"""
TravelSync Pro — Zoho Cliq Notification Service
Posts messages to a Zoho Cliq channel via the Cliq REST API with OAuth2.
Auto-refreshes the access token when it expires.
Falls back silently when not configured.
"""
import os
import time
import logging
import requests as http_requests

logger = logging.getLogger(__name__)

# ── Notification type → Cliq card theme ──────────────────────────────────────

_TYPE_TO_THEME = {
    "approval_request": "prompt",   # blue
    "status_update":    "prompt",
    "approval":         "modern",   # green
    "trip_plan_ready":  "modern",
    "rejection":        "poll",     # red
    "sos_alert":        "poll",
    "info":             "prompt",
}

_TYPE_TO_EMOJI = {
    "approval_request": "\U0001f4cb",  # clipboard
    "status_update":    "\U0001f504",  # arrows
    "approval":         "\u2705",      # check
    "trip_plan_ready":  "\U0001f5fa",  # map
    "rejection":        "\u274c",      # cross
    "sos_alert":        "\U0001f6a8",  # siren
    "info":             "\U0001f514",  # bell
}


class CliqService:
    """Zoho Cliq API client with OAuth2 token refresh. Follows the self.configured fallback pattern."""

    def __init__(self):
        self.api_endpoint = os.getenv("ZOHO_CLIQ_API_ENDPOINT")
        self.client_id = os.getenv("ZOHO_CLIQ_CLIENT_ID")
        self.client_secret = os.getenv("ZOHO_CLIQ_CLIENT_SECRET")
        self.refresh_token = os.getenv("ZOHO_CLIQ_REFRESH_TOKEN")
        self._access_token = os.getenv("ZOHO_CLIQ_ACCESS_TOKEN")
        self._token_expiry = time.time() + 3500 if self._access_token else 0

        self.configured = bool(
            self.api_endpoint and self.client_id and self.client_secret and self.refresh_token
        )

        if self.configured:
            logger.info("[Cliq] Configured: %s", self.api_endpoint)
        else:
            logger.debug("[Cliq] Not configured — Zoho Cliq notifications disabled")

    def _get_access_token(self) -> str | None:
        """Return a valid access token, refreshing if expired."""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        try:
            resp = http_requests.post(
                "https://accounts.zoho.in/oauth/v2/token",
                params={
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data["access_token"]
                self._token_expiry = time.time() + data.get("expires_in", 3600) - 60
                logger.info("[Cliq] Access token refreshed")
                return self._access_token
            else:
                logger.warning("[Cliq] Token refresh failed: HTTP %s — %s", resp.status_code, resp.text[:200])
                return None
        except Exception as exc:
            logger.warning("[Cliq] Token refresh error: %s", exc)
            return None

    def send(self, title: str, message: str, notification_type: str = "info",
             action_url: str | None = None) -> bool:
        """Post a message to the Zoho Cliq channel. Returns True on success. Never raises."""
        if not self.configured:
            logger.debug("[Cliq] Skipped (not configured): %s", title)
            return False
        try:
            token = self._get_access_token()
            if not token:
                return False

            emoji = _TYPE_TO_EMOJI.get(notification_type, _TYPE_TO_EMOJI["info"])

            payload = {
                "text": f"{emoji} *{title}*\n{message}",
            }

            resp = http_requests.post(
                self.api_endpoint,
                json=payload,
                headers={"Authorization": f"Zoho-oauthtoken {token}"},
                timeout=5,
            )
            if resp.status_code in (200, 201, 204):
                logger.info("[Cliq] Posted: %s", title)
                return True
            else:
                logger.warning("[Cliq] HTTP %s: %s", resp.status_code, resp.text[:200])
                return False
        except Exception as exc:
            logger.warning("[Cliq] Failed to post: %s — %s", title, exc)
            return False


# Module-level singleton
cliq_service = CliqService()
