"""
TravelSync Pro — Email Notification Service (SMTP)
Sends branded HTML emails for approvals, SOS alerts, trip updates, etc.
Falls back silently when SMTP is not configured.
"""
import os
import ssl
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# ── Notification type → human label + color ──────────────────────────────────

_TYPE_META = {
    "approval_request": ("Approval Request",  "#6366f1", "#eef2ff", "#4f46e5", "\U0001f4cb"),
    "status_update":    ("Status Update",     "#0ea5e9", "#f0f9ff", "#0284c7", "\U0001f504"),
    "approval":         ("Approved",          "#10b981", "#ecfdf5", "#059669", "\u2705"),
    "trip_plan_ready":  ("Trip Plan Ready",   "#8b5cf6", "#f5f3ff", "#7c3aed", "\U0001f5fa\ufe0f"),
    "rejection":        ("Rejected",          "#ef4444", "#fef2f2", "#dc2626", "\u274c"),
    "sos_alert":        ("Emergency Alert",   "#ef4444", "#fef2f2", "#dc2626", "\U0001f6a8"),
    "info":             ("Notification",      "#6366f1", "#eef2ff", "#4f46e5", "\U0001f514"),
}

# ── Modern HTML email template ───────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;-webkit-font-smoothing:antialiased;background-color:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
  <table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="padding:32px 16px;">
    <tr>
      <td align="center">
        <table width="100%%" cellpadding="0" cellspacing="0" role="presentation"
               style="max-width:560px;margin:0 auto;">

          <!-- Logo Bar -->
          <tr>
            <td style="padding:0 0 24px;text-align:center;">
              <table cellpadding="0" cellspacing="0" role="presentation" style="margin:0 auto;">
                <tr>
                  <td style="background:linear-gradient(135deg,{color} 0%%,{color_dark} 100%%);
                             width:36px;height:36px;border-radius:10px;text-align:center;
                             vertical-align:middle;font-size:18px;color:#fff;line-height:36px;">
                    &#9992;
                  </td>
                  <td style="padding-left:12px;font-size:18px;font-weight:700;color:#1f2937;
                             letter-spacing:-0.3px;">
                    TravelSync Pro
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Card -->
          <tr>
            <td style="background:#ffffff;border-radius:16px;overflow:hidden;
                        box-shadow:0 4px 24px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);">

              <!-- Color Accent Bar -->
              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation">
                <tr><td style="height:4px;background:linear-gradient(90deg,{color} 0%%,{color_dark} 100%%);"></td></tr>
              </table>

              <!-- Badge -->
              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation"
                     style="padding:28px 32px 0;">
                <tr>
                  <td>
                    <table cellpadding="0" cellspacing="0" role="presentation">
                      <tr>
                        <td style="background:{color_bg};border-radius:20px;padding:6px 14px;">
                          <span style="font-size:12px;font-weight:600;color:{color};
                                       text-transform:uppercase;letter-spacing:0.8px;">
                            {emoji}&nbsp; {type_label}
                          </span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Title & Message -->
              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation"
                     style="padding:16px 32px 0;">
                <tr>
                  <td>
                    <h1 style="margin:0 0 12px;font-size:22px;font-weight:700;color:#111827;
                               line-height:1.3;letter-spacing:-0.3px;">{title}</h1>
                    <p style="margin:0;font-size:15px;line-height:1.7;color:#4b5563;">{message}</p>
                  </td>
                </tr>
              </table>

              <!-- Divider + Action -->
              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation"
                     style="padding:24px 32px 28px;">
                <tr><td style="height:1px;background:#f3f4f6;"></td></tr>
                <tr>
                  <td style="padding-top:24px;text-align:center;">
                    {action_block}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 16px 0;text-align:center;">
              <p style="margin:0 0 4px;font-size:12px;color:#9ca3af;">
                Sent by TravelSync Pro &mdash; Fristine Infotech
              </p>
              <p style="margin:0;font-size:11px;color:#d1d5db;">
                This is an automated notification. Please do not reply to this email.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

_ACTION_BUTTON = (
    '<a href="{url}" style="display:inline-block;background:linear-gradient(135deg,{color} 0%%,{color_dark} 100%%);'
    'color:#fff;padding:13px 32px;border-radius:10px;text-decoration:none;font-weight:600;'
    'font-size:14px;letter-spacing:0.2px;box-shadow:0 2px 8px {color}40;">{label}</a>'
)


class EmailService:
    """SMTP email sender. Follows the self.configured fallback pattern."""

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("SMTP_FROM_EMAIL") or self.smtp_user
        self.from_name = os.getenv("SMTP_FROM_NAME", "TravelSync Pro")
        self.configured = bool(self.smtp_host and self.smtp_user and self.smtp_password)

        if self.configured:
            logger.info("[Email] SMTP configured: %s:%s", self.smtp_host, self.smtp_port)
        else:
            logger.debug("[Email] SMTP not configured — email notifications disabled")

    def _build_html(self, title: str, message: str, notification_type: str,
                    action_url: str | None = None, action_label: str = "View in TravelSync") -> str:
        """Build a branded HTML email body."""
        meta = _TYPE_META.get(notification_type, _TYPE_META["info"])
        type_label, color, color_bg, color_dark, emoji = meta
        action_block = ""
        if action_url:
            action_block = _ACTION_BUTTON.format(
                url=action_url, color=color, color_dark=color_dark, label=action_label,
            )
        return _HTML_TEMPLATE.format(
            color=color,
            color_bg=color_bg,
            color_dark=color_dark,
            emoji=emoji,
            type_label=type_label,
            title=title,
            message=message,
            action_block=action_block,
        )

    def send(self, to_email: str, subject: str, html_body: str) -> bool:
        """Send an HTML email via SMTP. Returns True on success. Never raises."""
        if not self.configured:
            logger.debug("[Email] Skipped (not configured): %s", subject)
            return False
        if not to_email:
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            context = ssl.create_default_context()
            if self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context, timeout=10) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.from_email, to_email, msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.from_email, to_email, msg.as_string())

            logger.info("[Email] Sent to %s: %s", to_email, subject)
            return True
        except Exception as exc:
            logger.warning("[Email] Failed to send to %s: %s", to_email, exc)
            return False

    def send_notification(self, to_email: str, title: str, message: str,
                          notification_type: str = "info",
                          action_url: str | None = None) -> bool:
        """Build HTML and send a notification email. Convenience wrapper."""
        subject = f"TravelSync — {title}"
        html = self._build_html(title, message, notification_type, action_url)
        return self.send(to_email, subject, html)


# Module-level singleton
email_service = EmailService()
