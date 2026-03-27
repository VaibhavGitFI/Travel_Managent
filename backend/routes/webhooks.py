"""TravelSync Pro — Webhook Management Routes"""
import secrets
import logging
from flask import Blueprint, request, jsonify
from auth import get_current_user, get_current_org, org_admin_required
from database import get_db
from services.webhook_service import EVENTS
from extensions import limiter

logger = logging.getLogger(__name__)
webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")


@webhooks_bp.route("", methods=["GET"])
def list_webhooks():
    """GET /api/webhooks — list org's webhook subscriptions."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    org = get_current_org()
    if not org:
        return jsonify({"success": False, "error": "Organization required"}), 403
    db = get_db()
    rows = db.execute(
        "SELECT * FROM webhook_subscriptions WHERE org_id = ? ORDER BY created_at DESC",
        (org["org_id"],)
    ).fetchall()
    db.close()
    # Mask secrets
    subs = []
    for r in rows:
        d = dict(r)
        d["secret"] = d["secret"][:4] + "****" if d.get("secret") else None
        subs.append(d)
    return jsonify({"success": True, "webhooks": subs, "available_events": EVENTS}), 200


@webhooks_bp.route("", methods=["POST"])
@limiter.limit("10 per minute")
@org_admin_required
def create_webhook():
    """POST /api/webhooks — create a webhook subscription."""
    org = get_current_org()
    data = request.get_json(silent=True) or {}
    event_type = data.get("event_type", "").strip()
    target_url = data.get("target_url", "").strip()
    if event_type not in EVENTS:
        return jsonify({"success": False, "error": f"Invalid event. Must be one of: {', '.join(EVENTS)}"}), 400
    if not target_url.startswith("https://"):
        return jsonify({"success": False, "error": "target_url must use HTTPS"}), 400
    secret = secrets.token_hex(32)
    db = get_db()
    db.execute(
        "INSERT INTO webhook_subscriptions (org_id, event_type, target_url, secret) VALUES (?,?,?,?)",
        (org["org_id"], event_type, target_url, secret),
    )
    db.commit()
    db.close()
    return jsonify({"success": True, "secret": secret,
                    "message": f"Webhook created for {event_type}. Save the secret — it won't be shown again."}), 201


@webhooks_bp.route("/<int:webhook_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
@org_admin_required
def delete_webhook(webhook_id):
    """DELETE /api/webhooks/:id — remove a webhook."""
    org = get_current_org()
    db = get_db()
    db.execute("DELETE FROM webhook_subscriptions WHERE id = ? AND org_id = ?",
               (webhook_id, org["org_id"]))
    db.commit()
    db.close()
    return jsonify({"success": True, "message": "Webhook deleted"}), 200


@webhooks_bp.route("/events", methods=["GET"])
def list_events():
    """GET /api/webhooks/events — list all supported webhook events."""
    return jsonify({"success": True, "events": EVENTS}), 200
