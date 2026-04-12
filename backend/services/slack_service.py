"""
TravelSync Pro — Slack Notification Service
Posts rich messages to a Slack channel via Incoming Webhook or Bot Token.
Supports Block Kit for approval action buttons.
Falls back silently when not configured.
"""
import os
import logging
from services.http_client import http as http_requests

logger = logging.getLogger(__name__)

_TYPE_TO_EMOJI = {
    "approval_request": ":clipboard:",
    "status_update":    ":arrows_counterclockwise:",
    "approval":         ":white_check_mark:",
    "trip_plan_ready":  ":world_map:",
    "rejection":        ":x:",
    "sos_alert":        ":rotating_light:",
    "info":             ":bell:",
    "org_invite":       ":tada:",
    "expense_submitted": ":receipt:",
}

_TYPE_TO_COLOR = {
    "approval_request": "#3B82F6",  # blue
    "status_update":    "#6366F1",  # indigo
    "approval":         "#10B981",  # green
    "trip_plan_ready":  "#10B981",
    "rejection":        "#EF4444",  # red
    "sos_alert":        "#EF4444",
    "info":             "#6B7280",  # gray
    "org_invite":       "#8B5CF6",  # purple
    "expense_submitted": "#F59E0B", # amber
}


class SlackService:
    """Slack notification client. Uses webhook URL or Bot Token + channel."""

    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.channel = os.getenv("SLACK_CHANNEL", "#travel-notifications")

        self.configured = bool(self.webhook_url or self.bot_token)

        if self.configured:
            mode = "Webhook" if self.webhook_url else f"Bot → {self.channel}"
            logger.info("[Slack] Configured: %s", mode)
        else:
            logger.debug("[Slack] Not configured — set SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN")

    def send(self, title: str, message: str, notification_type: str = "info",
             action_url: str | None = None) -> bool:
        """Post a rich message to Slack. Returns True on success. Never raises."""
        if not self.configured:
            return False
        try:
            emoji = _TYPE_TO_EMOJI.get(notification_type, ":bell:")
            color = _TYPE_TO_COLOR.get(notification_type, "#6B7280")

            # Build Block Kit message
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *{title}*\n{message}",
                    },
                },
            ]

            # Add action button if URL provided
            if action_url:
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View in TravelSync"},
                            "url": action_url,
                            "style": "primary",
                        }
                    ],
                })

            payload = {
                "text": f"{emoji} {title}: {message}",  # Fallback for notifications
                "attachments": [{"color": color, "blocks": blocks}],
            }

            if self.webhook_url:
                resp = http_requests.post(self.webhook_url, json=payload, timeout=5)
            else:
                payload["channel"] = self.channel
                resp = http_requests.post(
                    "https://slack.com/api/chat.postMessage",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    timeout=5,
                )

            if resp.status_code == 200:
                logger.info("[Slack] Posted: %s", title)
                return True
            else:
                logger.warning("[Slack] HTTP %s: %s", resp.status_code, resp.text[:200])
                return False
        except Exception as exc:
            logger.warning("[Slack] Failed: %s — %s", title, exc)
            return False

    def send_approval_request(self, request_id: str, requester_name: str,
                               destination: str, amount: float,
                               approver_name: str = None) -> bool:
        """Send a rich approval request card with approve/reject context."""
        title = "New Travel Approval Request"
        message = (
            f"*{requester_name}* has submitted a trip request\n"
            f"> :airplane: *Destination:* {destination}\n"
            f"> :moneybag: *Estimated:* Rs. {amount:,.0f}\n"
            f"> :label: *Request ID:* `{request_id}`"
        )
        if approver_name:
            message += f"\n> :bust_in_silhouette: *Assigned to:* {approver_name}"

        return self.send(title, message, "approval_request", action_url="/approvals")

    def send_approval_result(self, request_id: str, destination: str,
                              action: str, comments: str = "") -> bool:
        """Notify about approval/rejection."""
        is_approved = action == "approved"
        title = f"Trip {action.title()}"
        emoji = ":white_check_mark:" if is_approved else ":x:"
        message = f"{emoji} Trip to *{destination}* (`{request_id}`) has been *{action}*."
        if comments:
            message += f"\n> _{comments}_"
        ntype = "approval" if is_approved else "rejection"
        return self.send(title, message, ntype, action_url="/requests")

    def send_expense_alert(self, user_name: str, amount: float,
                            category: str, request_id: str = "") -> bool:
        """Notify about expense submission."""
        title = "Expense Submitted"
        message = (
            f"*{user_name}* submitted a *{category}* expense\n"
            f"> :moneybag: *Amount:* Rs. {amount:,.0f}"
        )
        if request_id:
            message += f"\n> :label: *Trip:* `{request_id}`"
        return self.send(title, message, "expense_submitted", action_url="/expenses")

    def send_sos_alert(self, user_name: str, location: str,
                        emergency_type: str) -> bool:
        """Urgent SOS broadcast."""
        title = "SOS EMERGENCY ALERT"
        message = (
            f":rotating_light: *{user_name}* triggered an SOS alert!\n"
            f"> :round_pushpin: *Location:* {location}\n"
            f"> :warning: *Type:* {emergency_type}"
        )
        return self.send(title, message, "sos_alert")


# Module-level singleton
slack_service = SlackService()
