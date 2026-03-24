"""
TravelSync Pro — Notifications Routes
Persistent notification history: list, mark-read, count.
"""
import logging
from flask import Blueprint, request, jsonify
from auth import get_current_user
from database import get_db

logger = logging.getLogger(__name__)

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@notifications_bp.route("", methods=["GET"])
def list_notifications():
    """GET /api/notifications?limit=20&unread_only=false — list user's notifications."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    limit = min(int(request.args.get("limit", 30)), 100)
    unread_only = request.args.get("unread_only", "false").lower() == "true"

    try:
        db = get_db()
        if unread_only:
            rows = db.execute(
                "SELECT * FROM notifications WHERE user_id = ? AND read = 0 ORDER BY created_at DESC LIMIT ?",
                (user["id"], limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user["id"], limit),
            ).fetchall()

        unread_count = db.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND read = 0",
            (user["id"],),
        ).fetchone()
        db.close()

        notifications = []
        for r in rows:
            row = dict(r)
            notifications.append({
                "id": row["id"],
                "type": row.get("type", "info"),
                "title": row["title"],
                "message": row.get("message", ""),
                "read": bool(row.get("read", 0)),
                "link": row.get("link"),
                "time": row.get("created_at", ""),
            })

        cnt = unread_count["cnt"] if isinstance(unread_count, dict) else unread_count[0]

        return jsonify({
            "success": True,
            "notifications": notifications,
            "unread_count": cnt,
            "total": len(notifications),
        }), 200
    except Exception as e:
        logger.exception("[Notifications] list failed")
        return jsonify({"success": False, "error": "Failed to load notifications"}), 500


@notifications_bp.route("/<int:notif_id>/read", methods=["POST"])
def mark_read(notif_id):
    """POST /api/notifications/<id>/read — mark a single notification as read."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        db = get_db()
        db.execute(
            "UPDATE notifications SET read = 1 WHERE id = ? AND user_id = ?",
            (notif_id, user["id"]),
        )
        db.commit()
        db.close()
        return jsonify({"success": True}), 200
    except Exception as e:
        logger.exception("[Notifications] mark_read failed")
        return jsonify({"success": False, "error": "Failed to update notification"}), 500


@notifications_bp.route("/read-all", methods=["POST"])
def mark_all_read():
    """POST /api/notifications/read-all — mark all user's notifications as read."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        db = get_db()
        db.execute(
            "UPDATE notifications SET read = 1 WHERE user_id = ? AND read = 0",
            (user["id"],),
        )
        db.commit()
        db.close()
        return jsonify({"success": True}), 200
    except Exception as e:
        logger.exception("[Notifications] mark_all_read failed")
        return jsonify({"success": False, "error": "Failed to update notifications"}), 500
