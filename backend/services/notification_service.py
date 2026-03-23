"""
TravelSync Pro — Unified Notification Service
Single entry point for all notifications. Dispatches to:
  1. Database (notifications table — persistent history)
  2. SocketIO (real-time in-app)
  3. Email (SMTP)
  4. Zoho Cliq (incoming webhook)

All channels are independently gated — unconfigured channels are silently skipped.
Dispatch runs in a background thread so it never blocks the HTTP response.
"""
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="notify")


def notify(
    user_id: int | None,
    title: str,
    message: str,
    notification_type: str = "info",
    *,
    channels: list[str] | None = None,
    request_id: str | None = None,
    broadcast_to_role: str | None = None,
    action_url: str | None = None,
    extra: dict | None = None,
) -> None:
    """
    Dispatch a notification to all configured channels.

    Args:
        user_id:            Target user (None when broadcasting to a role).
        title:              Short human-readable title.
        message:            Detailed message body.
        notification_type:  One of: approval_request, status_update, approval,
                            rejection, trip_plan_ready, sos_alert, info.
        channels:           Override which channels to use (e.g. ["email", "cliq"]).
                            None = all configured channels.
        request_id:         Linked travel request ID for deep linking.
        broadcast_to_role:  Send to all users with this role (e.g. "manager").
        action_url:         Link for email CTA button / Cliq action.
        extra:              Extra fields merged into the SocketIO payload.
    """
    _executor.submit(
        _dispatch,
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        channels=channels,
        request_id=request_id,
        broadcast_to_role=broadcast_to_role,
        action_url=action_url,
        extra=extra,
    )


def _dispatch(
    user_id, title, message, notification_type,
    channels, request_id, broadcast_to_role, action_url, extra,
):
    """Runs in a worker thread. Fans out to all channels."""
    use_all = channels is None
    ch = set(channels or [])

    # Resolve target user IDs for broadcast
    target_ids = []
    if broadcast_to_role:
        target_ids = _get_users_by_role(broadcast_to_role)
        if user_id and user_id not in target_ids:
            target_ids.append(user_id)
    elif user_id:
        target_ids = [user_id]

    # 1. Persist to DB
    if use_all or "db" in ch:
        for uid in target_ids:
            _persist(uid, title, message, notification_type, request_id, action_url)

    # 2. SocketIO (real-time in-app)
    if use_all or "socketio" in ch:
        _send_socketio(target_ids, title, message, notification_type, request_id, extra)

    # 3. Email
    if use_all or "email" in ch:
        _send_email(target_ids, title, message, notification_type, action_url)

    # 4. Zoho Cliq
    if use_all or "cliq" in ch:
        _send_cliq(title, message, notification_type, action_url)

    # 5. WhatsApp
    if use_all or "whatsapp" in ch:
        _send_whatsapp(target_ids, title, message, notification_type)


# ── Channel implementations ──────────────────────────────────────────────────

def _persist(user_id, title, message, notification_type, request_id, action_url):
    """INSERT into the notifications table. Silent on failure."""
    try:
        from database import get_db
        db = get_db()
        link = action_url or (f"/requests/{request_id}" if request_id else None)
        db.execute(
            "INSERT INTO notifications (user_id, type, title, message, link) VALUES (?, ?, ?, ?, ?)",
            (user_id, notification_type, title, message, link),
        )
        db.commit()
        db.close()
    except Exception as exc:
        logger.debug("[Notify] DB persist failed: %s", exc)


def _send_socketio(target_ids, title, message, notification_type, request_id, extra):
    """Emit via SocketIO to each target user's room."""
    try:
        from extensions import socketio
        payload = {
            "type": notification_type,
            "title": title,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }
        if request_id:
            payload["request_id"] = request_id
        if extra:
            payload.update(extra)

        for uid in target_ids:
            socketio.emit("notification", payload, to=f"user_{uid}", namespace="/")
    except Exception as exc:
        logger.debug("[Notify] SocketIO emit failed: %s", exc)


def _send_email(target_ids, title, message, notification_type, action_url):
    """Look up each user's email from DB and send."""
    try:
        from services.email_service import email_service
        if not email_service.configured:
            return
        from database import get_db
        db = get_db()
        for uid in target_ids:
            try:
                row = db.execute("SELECT email FROM users WHERE id = ?", (uid,)).fetchone()
                if row and row["email"]:
                    email_service.send_notification(
                        to_email=row["email"],
                        title=title,
                        message=message,
                        notification_type=notification_type,
                        action_url=action_url,
                    )
            except Exception as exc:
                logger.debug("[Notify] Email to user %s failed: %s", uid, exc)
        db.close()
    except Exception as exc:
        logger.debug("[Notify] Email channel failed: %s", exc)


def _send_cliq(title, message, notification_type, action_url):
    """Post to the Zoho Cliq channel (channel-level, not per-user)."""
    try:
        from services.cliq_service import cliq_service
        if not cliq_service.configured:
            return
        cliq_service.send(title, message, notification_type, action_url)
    except Exception as exc:
        logger.debug("[Notify] Cliq channel failed: %s", exc)


def _send_whatsapp(target_ids, title, message, notification_type):
    """Send WhatsApp message to each user's phone number."""
    try:
        from services.whatsapp_service import whatsapp_service
        if not whatsapp_service.configured:
            return
        from database import get_db
        db = get_db()
        for uid in target_ids:
            try:
                row = db.execute("SELECT phone FROM users WHERE id = ?", (uid,)).fetchone()
                if row and row.get("phone"):
                    whatsapp_service.send(row["phone"], title, message, notification_type)
            except Exception as exc:
                logger.debug("[Notify] WhatsApp to user %s failed: %s", uid, exc)
        db.close()
    except Exception as exc:
        logger.debug("[Notify] WhatsApp channel failed: %s", exc)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_users_by_role(role: str) -> list[int]:
    """Return user IDs matching the given role. Also includes admins."""
    try:
        from database import get_db
        db = get_db()
        rows = db.execute(
            "SELECT id FROM users WHERE role IN (?, 'admin')",
            (role,),
        ).fetchall()
        db.close()
        return [r["id"] for r in rows]
    except Exception:
        return []
