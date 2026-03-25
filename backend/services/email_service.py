"""
TravelSync Pro — Email Notification Service (SMTP)
Sends branded HTML emails for approvals, SOS alerts, trip updates, expenses, etc.
Falls back silently when SMTP is not configured.
"""
import os
import ssl
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# ── Notification type → metadata ─────────────────────────────────────────────
# (label, color, color_bg, color_dark, emoji, action_label)

_TYPE_META = {
    "approval_request":  ("Approval Request",   "#6366f1", "#eef2ff", "#4f46e5", "\U0001f4cb", "Review Request"),
    "status_update":     ("Status Update",      "#0ea5e9", "#f0f9ff", "#0284c7", "\U0001f504", "View Trip"),
    "approval":          ("Approved",           "#10b981", "#ecfdf5", "#059669", "\u2705",     "View Details"),
    "rejection":         ("Rejected",           "#ef4444", "#fef2f2", "#dc2626", "\u274c",     "View Details"),
    "trip_plan_ready":   ("Trip Plan Ready",    "#8b5cf6", "#f5f3ff", "#7c3aed", "\U0001f5fa\ufe0f", "View Plan"),
    "sos_alert":         ("Emergency Alert",    "#ef4444", "#fef2f2", "#dc2626", "\U0001f6a8", "View Alert"),
    "expense_submitted": ("Expense Submitted",  "#f59e0b", "#fffbeb", "#d97706", "\U0001f4b0", "Review Expense"),
    "expense_approved":  ("Expense Approved",   "#10b981", "#ecfdf5", "#059669", "\u2705",     "View Expenses"),
    "expense_rejected":  ("Expense Rejected",   "#ef4444", "#fef2f2", "#dc2626", "\u274c",     "View Expenses"),
    "meeting_reminder":  ("Meeting Reminder",   "#0ea5e9", "#f0f9ff", "#0284c7", "\U0001f4c5", "View Meeting"),
    "info":              ("Notification",       "#6366f1", "#eef2ff", "#4f46e5", "\U0001f514", "Open TravelSync"),
}

# ── HTML email template ──────────────────────────────────────────────────────

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
            <td style="padding:0 0 20px;text-align:center;">
              <table cellpadding="0" cellspacing="0" role="presentation" style="margin:0 auto;">
                <tr>
                  <td style="background:linear-gradient(135deg,#1a56db 0%%,#0891b2 100%%);
                             width:38px;height:38px;border-radius:10px;text-align:center;
                             vertical-align:middle;font-size:18px;color:#fff;line-height:38px;">
                    &#9992;
                  </td>
                  <td style="padding-left:12px;font-size:19px;font-weight:700;color:#1f2937;
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

              <!-- Badge + Timestamp -->
              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation"
                     style="padding:24px 32px 0;">
                <tr>
                  <td>
                    <table cellpadding="0" cellspacing="0" role="presentation">
                      <tr>
                        <td style="background:{color_bg};border:1px solid {color}22;border-radius:20px;padding:5px 14px;">
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

              <!-- Title -->
              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation"
                     style="padding:16px 32px 0;">
                <tr>
                  <td>
                    <h1 style="margin:0 0 8px;font-size:21px;font-weight:700;color:#111827;
                               line-height:1.35;letter-spacing:-0.3px;">{title}</h1>
                  </td>
                </tr>
              </table>

              <!-- Message Body -->
              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation"
                     style="padding:0 32px;">
                <tr>
                  <td>
                    <p style="margin:0;font-size:15px;line-height:1.7;color:#4b5563;">{message}</p>
                  </td>
                </tr>
              </table>

              {detail_block}

              <!-- Divider + Action -->
              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation"
                     style="padding:20px 32px 28px;">
                <tr><td style="height:1px;background:#f3f4f6;"></td></tr>
                <tr>
                  <td style="padding-top:20px;text-align:center;">
                    {action_block}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 16px 0;text-align:center;">
              <p style="margin:0 0 4px;font-size:12px;color:#9ca3af;">
                Sent by <strong>TravelSync Pro</strong> &mdash; Fristine Infotech
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
    'color:#fff;padding:12px 32px;border-radius:10px;text-decoration:none;font-weight:600;'
    'font-size:14px;letter-spacing:0.2px;box-shadow:0 2px 8px {color}30;">{label}</a>'
)

_DETAIL_ROW = (
    '<tr>'
    '<td style="padding:4px 0;font-size:13px;color:#9ca3af;width:110px;vertical-align:top;">{label}</td>'
    '<td style="padding:4px 0;font-size:13px;color:#374151;font-weight:500;">{value}</td>'
    '</tr>'
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

    def _build_detail_block(self, details: dict | None) -> str:
        """Build an optional key-value detail table for the email body."""
        if not details:
            return ""
        rows = ""
        for label, value in details.items():
            if value:
                rows += _DETAIL_ROW.format(label=label, value=value)
        if not rows:
            return ""
        return (
            '<table width="100%%" cellpadding="0" cellspacing="0" role="presentation"'
            ' style="padding:14px 32px 0;">'
            '<tr><td>'
            '<table width="100%%" cellpadding="0" cellspacing="0" role="presentation"'
            ' style="background:#f9fafb;border-radius:10px;padding:14px 16px;border:1px solid #f3f4f6;">'
            f'{rows}'
            '</table>'
            '</td></tr></table>'
        )

    def _build_html(self, title: str, message: str, notification_type: str,
                    action_url: str | None = None, details: dict | None = None) -> str:
        """Build a branded HTML email body."""
        meta = _TYPE_META.get(notification_type, _TYPE_META["info"])
        type_label, color, color_bg, color_dark, emoji, default_action_label = meta

        action_block = ""
        if action_url:
            action_block = _ACTION_BUTTON.format(
                url=action_url, color=color, color_dark=color_dark,
                label=default_action_label,
            )

        detail_block = self._build_detail_block(details)

        return _HTML_TEMPLATE.format(
            color=color,
            color_bg=color_bg,
            color_dark=color_dark,
            emoji=emoji,
            type_label=type_label,
            title=title,
            message=message,
            action_block=action_block,
            detail_block=detail_block,
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
                          action_url: str | None = None,
                          details: dict | None = None) -> bool:
        """Build HTML and send a notification email. Convenience wrapper."""
        meta = _TYPE_META.get(notification_type, _TYPE_META["info"])
        emoji = meta[4]
        subject = f"{emoji} TravelSync — {title}"
        html = self._build_html(title, message, notification_type, action_url, details)
        return self.send(to_email, subject, html)


# Module-level singleton
email_service = EmailService()
