"""
TravelSync Pro — Webhook Delivery Service
Fires webhooks on key events. Signs payloads with HMAC-SHA256.
"""
import hmac
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from services.http_client import http as http_requests

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="webhook")

# Supported events
EVENTS = [
    "request.submitted", "request.approved", "request.rejected",
    "expense.submitted", "expense.approved",
    "meeting.created", "sos.triggered",
    "member.invited", "member.removed",
]


def fire_event(event_type: str, payload: dict, org_id: int = None) -> None:
    """Fire webhooks for a given event. Runs in background. Never raises."""
    if event_type not in EVENTS:
        logger.debug("[Webhook] Unknown event type: %s", event_type)
        return
    _executor.submit(_deliver_all, event_type, payload, org_id)


def _deliver_all(event_type, payload, org_id):
    from database import get_db
    db = get_db()
    try:
        query = "SELECT * FROM webhook_subscriptions WHERE event_type = ? AND active = 1"
        params = [event_type]
        if org_id:
            query += " AND org_id = ?"
            params.append(org_id)
        subs = db.execute(query, params).fetchall()
        for sub in subs:
            s = dict(sub)
            _deliver_one(s, event_type, payload, db)
    except Exception as exc:
        logger.warning("[Webhook] Delivery failed: %s", exc)
    finally:
        db.close()


def _deliver_one(sub, event_type, payload, db):
    body = json.dumps({
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    })
    # HMAC signature
    secret = sub.get("secret") or ""
    signature = hmac.new(
        secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-TravelSync-Event": event_type,
        "X-TravelSync-Signature": f"sha256={signature}",
    }
    # Merge custom headers
    try:
        custom = json.loads(sub.get("headers_json") or "{}")
        headers.update(custom)
    except Exception:
        pass

    try:
        resp = http_requests.post(sub["target_url"], data=body, headers=headers, timeout=10)
        now = datetime.now(timezone.utc).isoformat()
        if resp.status_code < 300:
            db.execute(
                "UPDATE webhook_subscriptions SET last_triggered=?, last_status=?, failure_count=0 WHERE id=?",
                (now, resp.status_code, sub["id"]))
        else:
            fc = sub.get("failure_count", 0) + 1
            active = 0 if fc >= 10 else 1
            db.execute(
                "UPDATE webhook_subscriptions SET last_triggered=?, last_status=?, failure_count=?, active=? WHERE id=?",
                (now, resp.status_code, fc, active, sub["id"]))
        db.commit()
        logger.info("[Webhook] %s -> %s: HTTP %s", event_type, sub["target_url"][:50], resp.status_code)
    except Exception as exc:
        fc = sub.get("failure_count", 0) + 1
        active = 0 if fc >= 10 else 1
        db.execute(
            "UPDATE webhook_subscriptions SET failure_count=?, active=? WHERE id=?",
            (fc, active, sub["id"]))
        db.commit()
        logger.warning("[Webhook] %s -> %s failed: %s", event_type, sub["target_url"][:50], exc)
