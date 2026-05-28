"""
TravelSync Pro - Email notification service (SMTP).
Sends branded HTML emails for approvals, alerts, trip updates, expenses, and auth codes.
Falls back silently when SMTP is not configured.
"""
import logging
import os
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

logger = logging.getLogger(__name__)

# Notification type -> metadata
# (label, color, color_bg, color_dark, icon_text, action_label)
_TYPE_META = {
    "approval_request":  ("Approval Request",    "#60a5fa", "#10284b", "#1d4ed8", "AR",  "Review Request"),
    "status_update":     ("Status Update",       "#38bdf8", "#0a2a3a", "#0369a1", "UP",  "View Trip"),
    "approval":          ("Approved",            "#34d399", "#0d2b23", "#059669", "OK",  "View Details"),
    "rejection":         ("Rejected",            "#f87171", "#341318", "#dc2626", "NO",  "View Details"),
    "trip_plan_ready":   ("Trip Plan Ready",     "#60a5fa", "#10284b", "#1d4ed8", "TR",  "View Plan"),
    "sos_alert":         ("Emergency Alert",     "#fb7185", "#39131d", "#e11d48", "SOS", "View Alert"),
    "expense_submitted": ("Expense Submitted",   "#f59e0b", "#36230d", "#d97706", "EX",  "Review Expense"),
    "expense_approved":  ("Expense Approved",    "#34d399", "#0d2b23", "#059669", "OK",  "View Expenses"),
    "expense_rejected":  ("Expense Rejected",    "#f87171", "#341318", "#dc2626", "NO",  "View Expenses"),
    "meeting_reminder":  ("Meeting Reminder",    "#38bdf8", "#0a2a3a", "#0369a1", "MT",  "View Meeting"),
    "org_invite":        ("Organization Invite", "#60a5fa", "#10284b", "#1d4ed8", "ORG", "Open Profile"),
    "verification_code": ("Email Verification",  "#60a5fa", "#10284b", "#1d4ed8", "ID",  "Open TravelSync"),
    "reset_code":        ("Password Reset",      "#f59e0b", "#36230d", "#d97706", "PW",  "Open TravelSync"),
    "info":              ("Notification",        "#60a5fa", "#10284b", "#1d4ed8", "TS",  "Open TravelSync"),
}

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <meta name="supported-color-schemes" content="dark">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;-webkit-font-smoothing:antialiased;background-color:#050b16;color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
    {preheader}
  </div>
  <table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="padding:16px 10px 28px;background-color:#050b16;">
    <tr>
      <td align="center">
        <table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="max-width:600px;margin:0 auto;">
          <tr>
            <td style="padding:0 0 12px;">
              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="background:#08111f;background-image:linear-gradient(135deg,#1b263b 0%%,#0d2244 55%%,#1a56db 100%%);border-radius:24px;overflow:hidden;border:1px solid #1e3a72;box-shadow:0 16px 40px rgba(0,0,0,.32);">
                <tr>
                  <td style="padding:18px 20px;">
                    <table width="100%%" cellpadding="0" cellspacing="0" role="presentation">
                      <tr>
                        <td style="vertical-align:top;">
                          <table cellpadding="0" cellspacing="0" role="presentation">
                            <tr>
                              <td style="width:40px;height:40px;border-radius:12px;background:rgba(96,165,250,0.16);border:1px solid rgba(191,219,254,0.22);text-align:center;vertical-align:middle;color:#f8fafc;font-size:14px;font-weight:800;letter-spacing:1.2px;line-height:40px;">
                                TS
                              </td>
                              <td style="padding-left:14px;vertical-align:middle;">
                                <div style="font-size:18px;font-weight:800;color:#f8fafc;letter-spacing:-0.3px;">TravelSync Pro</div>
                                <div style="padding-top:3px;font-size:11px;line-height:1.45;color:#cbd5e1;">Corporate travel, approvals, expense controls, and alerts in one workflow.</div>
                              </td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="background:#0d2244;border-radius:24px;overflow:hidden;border:1px solid #1e3a72;box-shadow:0 20px 48px rgba(0,0,0,.34),0 8px 20px rgba(2,6,23,.4);">
              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation">
                <tr><td style="height:4px;background:linear-gradient(90deg,{color} 0%%,{color_dark} 100%%);"></td></tr>
              </table>

              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="padding:20px 20px 0;">
                <tr>
                  <td>
                    <table width="100%%" cellpadding="0" cellspacing="0" role="presentation">
                      <tr>
                        <td style="vertical-align:middle;">
                          <table cellpadding="0" cellspacing="0" role="presentation">
                            <tr>
                              <td style="width:44px;height:44px;border-radius:14px;background:linear-gradient(135deg,{color} 0%%,{color_dark} 100%%);text-align:center;vertical-align:middle;color:#ffffff;font-size:13px;font-weight:800;letter-spacing:1.4px;line-height:44px;">
                                {icon_text}
                              </td>
                              <td style="padding-left:14px;vertical-align:middle;">
                                <div style="display:inline-block;background:{color_bg};border:1px solid {color}33;border-radius:999px;padding:5px 10px;font-size:10px;font-weight:700;color:{color};text-transform:uppercase;letter-spacing:0.9px;">
                                  {type_label}
                                </div>
                              </td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="padding:14px 20px 0;">
                <tr>
                  <td>
                    <h1 style="margin:0;font-size:22px;font-weight:800;color:#f8fafc;line-height:1.2;letter-spacing:-0.4px;">{title}</h1>
                  </td>
                </tr>
              </table>

              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="padding:12px 20px 0;">
                <tr>
                  <td>
                    {message_block}
                  </td>
                </tr>
              </table>

              {code_block}
              {detail_block}
              {note_block}

              <table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="padding:18px 20px 22px;">
                <tr><td style="height:1px;background:#1e3a72;"></td></tr>
                <tr>
                  <td style="padding-top:16px;text-align:center;">
                    {action_block}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:14px 12px 0;text-align:center;">
              <p style="margin:0 0 4px;font-size:11px;color:#cbd5e1;">
                Sent by <strong>TravelSync Pro</strong> - Fristine Infotech
              </p>
              <p style="margin:0;font-size:10px;color:#94a8c4;">
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
    'color:#fff;padding:11px 24px;border-radius:12px;text-decoration:none;font-weight:700;'
    'font-size:13px;letter-spacing:0.15px;box-shadow:0 10px 24px {color}26;">{label}</a>'
)

_DETAIL_ROW = (
    "<tr>"
    '<td style="padding:5px 0;font-size:12px;color:#94a8c4;width:110px;vertical-align:top;">{label}</td>'
    '<td style="padding:5px 0;font-size:12px;color:#f8fafc;font-weight:600;">{value}</td>'
    "</tr>"
)

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "\uFE0F"
    "]",
)


def _stringify(value) -> str:
    if value is None:
        return ""
    return _EMOJI_RE.sub("", str(value)).strip()


def _html_with_breaks(value) -> str:
    return escape(_stringify(value)).replace("\n", "<br>")


def _text_to_html_paragraphs(value: str) -> str:
    text = _stringify(value).replace("\r\n", "\n")
    if not text:
        return ""
    paragraphs = [part.strip() for part in _PARAGRAPH_SPLIT_RE.split(text) if part.strip()]
    html_parts = []
    for index, paragraph in enumerate(paragraphs):
        margin = "0" if index == len(paragraphs) - 1 else "0 0 14px"
        html_parts.append(
            f'<p style="margin:{margin};font-size:14px;line-height:1.65;color:#d6e2f5;">'
            f"{_html_with_breaks(paragraph)}"
            "</p>"
        )
    return "".join(html_parts)


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
            logger.debug("[Email] SMTP not configured - email notifications disabled")

    def _build_detail_block(self, details: dict | None) -> str:
        """Build an optional key-value detail table for the email body."""
        if not details:
            return ""
        rows = ""
        for label, value in details.items():
            safe_label = _stringify(label)
            safe_value = _stringify(value)
            if safe_label and safe_value:
                rows += _DETAIL_ROW.format(
                    label=escape(safe_label),
                    value=_html_with_breaks(safe_value),
                )
        if not rows:
            return ""
        return (
            '<table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="padding:14px 20px 0;">'
            "<tr><td>"
            '<table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="background:#08111f;border-radius:16px;padding:14px 16px;border:1px solid #1e3a72;">'
            f"{rows}"
            "</table>"
            "</td></tr></table>"
        )

    def _build_code_block(self, code: str | None, code_label: str | None) -> str:
        """Build a dedicated one-time-code panel when a code is provided."""
        safe_code = _stringify(code)
        if not safe_code:
            return ""
        label = escape(_stringify(code_label) or "Security Code")
        return (
            '<table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="padding:14px 20px 0;">'
            "<tr><td>"
            '<table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="background:#050b16;border-radius:16px;padding:16px 14px;border:1px solid #2a4e8e;">'
            '<tr><td style="text-align:center;">'
            f'<div style="font-size:10px;font-weight:700;letter-spacing:1.1px;text-transform:uppercase;color:#93c5fd;">{label}</div>'
            f'<div style="padding-top:8px;font-size:28px;line-height:1;font-weight:800;letter-spacing:6px;color:#ffffff;font-family:Consolas,Monaco,\'SFMono-Regular\',\'Roboto Mono\',monospace;">{escape(safe_code)}</div>'
            "</td></tr>"
            "</table>"
            "</td></tr></table>"
        )

    def _build_note_block(self, note: str | None, color: str) -> str:
        """Build a supporting note block."""
        safe_note = _stringify(note)
        if not safe_note:
            return ""
        return (
            '<table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="padding:14px 20px 0;">'
            "<tr><td>"
            f'<table width="100%%" cellpadding="0" cellspacing="0" role="presentation" style="background:#08111f;border-radius:14px;border:1px solid #1e3a72;border-left:4px solid {color};padding:12px 14px;">'
            '<tr><td style="font-size:12px;line-height:1.65;color:#d6e2f5;">'
            f"{_html_with_breaks(safe_note)}"
            "</td></tr></table>"
            "</td></tr></table>"
        )

    def _build_text_body(
        self,
        title: str,
        message: str,
        *,
        details: dict | None = None,
        action_url: str | None = None,
        code: str | None = None,
        code_label: str | None = None,
        note: str | None = None,
    ) -> str:
        """Build a plain-text alternative for clients that strip HTML."""
        safe_title = _stringify(title) or "Notification"
        lines = [self.from_name, "", safe_title, "=" * max(8, len(safe_title)), ""]

        safe_message = _stringify(message)
        if safe_message:
            lines.append(safe_message)

        safe_code = _stringify(code)
        if safe_code:
            lines.extend(["", f"{_stringify(code_label) or 'Security Code'}: {safe_code}"])

        if details:
            rows = []
            for label, value in details.items():
                safe_label = _stringify(label)
                safe_value = _stringify(value)
                if safe_label and safe_value:
                    rows.append(f"{safe_label}: {safe_value}")
            if rows:
                lines.extend(["", "Details:"])
                lines.extend(rows)

        safe_note = _stringify(note)
        if safe_note:
            lines.extend(["", safe_note])

        safe_url = _stringify(action_url)
        if safe_url:
            lines.extend(["", f"Open: {safe_url}"])

        return "\n".join(lines).strip() + "\n"

    def _build_html(
        self,
        title: str,
        message: str,
        notification_type: str,
        *,
        action_url: str | None = None,
        details: dict | None = None,
        code: str | None = None,
        code_label: str | None = None,
        note: str | None = None,
        action_label: str | None = None,
    ) -> str:
        """Build a branded HTML email body."""
        meta = _TYPE_META.get(notification_type, _TYPE_META["info"])
        type_label, color, color_bg, color_dark, icon_text, default_action_label = meta

        action_block = ""
        if action_url:
            action_block = _ACTION_BUTTON.format(
                url=escape(_stringify(action_url), quote=True),
                color=color,
                color_dark=color_dark,
                label=escape(_stringify(action_label) or default_action_label),
            )

        message_block = _text_to_html_paragraphs(message) or (
            '<p style="margin:0;font-size:14px;line-height:1.65;color:#d6e2f5;">'
            "TravelSync has an update for you."
            "</p>"
        )
        detail_block = self._build_detail_block(details)
        code_block = self._build_code_block(code, code_label)
        note_block = self._build_note_block(note, color)

        safe_title = escape(_stringify(title) or "TravelSync Notification")
        preheader_source = _stringify(note) or _stringify(message) or _stringify(title) or "TravelSync notification"
        preheader = escape(preheader_source[:140])

        return _HTML_TEMPLATE.format(
            title=safe_title,
            preheader=preheader,
            color=color,
            color_bg=color_bg,
            color_dark=color_dark,
            icon_text=escape(icon_text),
            type_label=escape(type_label),
            message_block=message_block,
            code_block=code_block,
            detail_block=detail_block,
            note_block=note_block,
            action_block=action_block,
        )

    def send(self, to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
        """Send a multipart email via SMTP. Returns True on success. Never raises."""
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
            if text_body:
                msg.attach(MIMEText(text_body, "plain", "utf-8"))
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

    def send_notification(
        self,
        to_email: str,
        title: str,
        message: str,
        notification_type: str = "info",
        action_url: str | None = None,
        details: dict | None = None,
        code: str | None = None,
        code_label: str | None = None,
        note: str | None = None,
        action_label: str | None = None,
    ) -> bool:
        """Build HTML and send a notification email."""
        subject = f"TravelSync | {_stringify(title) or 'Notification'}"
        html = self._build_html(
            title,
            message,
            notification_type,
            action_url=action_url,
            details=details,
            code=code,
            code_label=code_label,
            note=note,
            action_label=action_label,
        )
        text = self._build_text_body(
            title,
            message,
            details=details,
            action_url=action_url,
            code=code,
            code_label=code_label,
            note=note,
        )
        return self.send(to_email, subject, html, text)


email_service = EmailService()
