"""
TravelSync Pro — WhatsApp Notification Service (Twilio)
Rich-formatted WhatsApp messages with AI-powered smart tips.
Falls back silently when not configured.
"""
import os
import logging
import requests as http_requests
from base64 import b64encode

logger = logging.getLogger(__name__)

# ── Rich WhatsApp templates per notification type ────────────────────────────

_TEMPLATES = {
    "approval": {
        "header": "\u2705 *TRIP APPROVED*",
        "divider": "\u2500" * 20,
        "footer_emoji": "\U0001f3e8",
        "footer_tip": "You can now proceed with bookings on TravelSync Pro.",
    },
    "rejection": {
        "header": "\u274c *TRIP REJECTED*",
        "divider": "\u2500" * 20,
        "footer_emoji": "\U0001f4dd",
        "footer_tip": "Revise your request and resubmit for approval.",
    },
    "approval_request": {
        "header": "\U0001f4cb *NEW APPROVAL REQUEST*",
        "divider": "\u2500" * 20,
        "footer_emoji": "\u23f3",
        "footer_tip": "Please review and respond at your earliest.",
    },
    "trip_plan_ready": {
        "header": "\U0001f5fa\ufe0f *TRIP PLAN READY*",
        "divider": "\u2500" * 20,
        "footer_emoji": "\U0001f4a1",
        "footer_tip": "Open TravelSync Pro to view the full plan.",
    },
    "sos_alert": {
        "header": "\U0001f6a8 *EMERGENCY SOS ALERT*",
        "divider": "\U0001f534" * 10,
        "footer_emoji": "\u260e\ufe0f",
        "footer_tip": "Respond immediately. Emergency: 112 | Ambulance: 108",
    },
    "status_update": {
        "header": "\U0001f504 *STATUS UPDATE*",
        "divider": "\u2500" * 20,
        "footer_emoji": "\U0001f4f1",
        "footer_tip": "Track your trip status on TravelSync Pro.",
    },
    "info": {
        "header": "\U0001f514 *NOTIFICATION*",
        "divider": "\u2500" * 20,
        "footer_emoji": "\U0001f4a1",
        "footer_tip": "Visit TravelSync Pro for more details.",
    },
}


def _build_rich_message(title: str, message: str, notification_type: str,
                        ai_tip: str | None = None) -> str:
    """Build a beautifully formatted WhatsApp message."""
    tmpl = _TEMPLATES.get(notification_type, _TEMPLATES["info"])

    lines = [
        tmpl["header"],
        tmpl["divider"],
        "",
        f"*{title}*",
        "",
        message,
        "",
    ]

    # AI Smart Tip section
    if ai_tip:
        lines.extend([
            tmpl["divider"],
            f"\U0001f9e0 *Smart Tip:*",
            ai_tip,
            "",
        ])

    # Footer
    lines.extend([
        tmpl["divider"],
        f"{tmpl['footer_emoji']} {tmpl['footer_tip']}",
        "",
        "\u2500" * 20,
        "\U00002708\ufe0f *TravelSync Pro*",
        "AI-Powered Corporate Travel",
    ])

    return "\n".join(lines)


def _get_ai_tip(title: str, message: str, notification_type: str) -> str | None:
    """Generate a short AI-powered contextual tip using Gemini, with Claude fallback."""
    type_context = {
        "approval": "a trip that was just approved",
        "rejection": "a trip that was rejected",
        "approval_request": "a new travel request awaiting approval",
        "trip_plan_ready": "an AI-generated trip plan",
        "sos_alert": "an emergency SOS situation",
        "status_update": "a trip status change",
    }
    context = type_context.get(notification_type, "a corporate travel notification")
    prompt = (
        f"Generate ONE short, actionable tip (max 25 words) for {context}.\n\n"
        f"Title: {title}\nDetails: {message}\n\n"
        f"Respond with ONLY the tip, no quotes, no prefix. Be specific and helpful."
    )
    system = "You are TravelSync Pro AI assistant for corporate travel."

    # Try Gemini
    try:
        from services.gemini_service import gemini
        import time
        if gemini.configured and not (hasattr(gemini, '_cooldown_until') and time.time() < gemini._cooldown_until):
            tip = gemini.generate(f"{system} {prompt}", model_type="flash")
            if tip and len(tip) < 200:
                return tip.strip().strip('"').strip("'")
    except Exception:
        pass

    # Fallback to Claude
    try:
        from services.anthropic_service import claude
        if claude.is_available:
            tip = claude.generate(prompt, system=system)
            if tip and len(tip) < 200:
                return tip.strip().strip('"').strip("'")
    except Exception:
        pass

    return None


class WhatsAppService:
    """Twilio WhatsApp sender with rich templates and AI tips."""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_WHATSAPP_FROM", "+14155238886")
        self.configured = bool(self.account_sid and self.auth_token)

        if self.configured:
            logger.info("[WhatsApp] Twilio configured (SID: %s...)", self.account_sid[:8])
        else:
            logger.debug("[WhatsApp] Twilio not configured — WhatsApp notifications disabled")

    def _auth_header(self) -> str:
        creds = b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        return f"Basic {creds}"

    def _normalize_number(self, number: str) -> str:
        """Normalize phone number to E.164 format."""
        clean = number.strip().replace(" ", "").replace("-", "")
        if not clean.startswith("+"):
            if clean.startswith("0"):
                clean = clean[1:]
            clean = f"+91{clean}"
        return clean

    def send(self, to_number: str, title: str, message: str,
             notification_type: str = "info", ai_tips: bool = True,
             raw_body: bool = False) -> bool:
        """Send a rich WhatsApp message with optional AI tip. Never raises."""
        if not self.configured:
            logger.debug("[WhatsApp] Skipped (not configured): %s", title)
            return False
        if not to_number:
            return False

        try:
            to_clean = self._normalize_number(to_number)

            if raw_body:
                # Send message as-is (for bot replies)
                body = message
            else:
                # Build rich template with optional AI tip
                ai_tip = None
                if ai_tips:
                    ai_tip = _get_ai_tip(title, message, notification_type)
                body = _build_rich_message(title, message, notification_type, ai_tip)

            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
            resp = http_requests.post(
                url,
                data={
                    "From": f"whatsapp:{self.from_number}",
                    "To": f"whatsapp:{to_clean}",
                    "Body": body,
                },
                headers={"Authorization": self._auth_header()},
                timeout=10,
            )

            if resp.status_code in (200, 201):
                sid = resp.json().get("sid", "")
                logger.info("[WhatsApp] Sent to %s: %s (SID: %s)", to_clean, title, sid)
                return True
            else:
                logger.warning("[WhatsApp] HTTP %s: %s", resp.status_code, resp.text[:300])
                return False
        except Exception as exc:
            logger.warning("[WhatsApp] Failed to send to %s: %s", to_number, exc)
            return False

    def send_to_multiple(self, phone_numbers: list[str], title: str, message: str,
                         notification_type: str = "info") -> int:
        """Send to multiple numbers. Returns count of successful sends."""
        sent = 0
        for num in phone_numbers:
            if self.send(num, title, message, notification_type):
                sent += 1
        return sent


# Module-level singleton
whatsapp_service = WhatsAppService()
