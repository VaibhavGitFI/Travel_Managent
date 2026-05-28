"""
TravelSync Pro — Audit Log Service
Immutable log of all data-changing operations for compliance.
"""
import logging
import json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from flask import request, g

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="audit")


def log_action(action: str, entity: str, entity_id: str = None,
               actor_id: int = None, org_id: int = None,
               before: dict = None, after: dict = None,
               details: dict = None) -> None:
    """Record an audit event. Runs in background thread. Never raises."""
    diff = None
    if before and after:
        diff = {k: {"old": before.get(k), "new": after.get(k)}
                for k in set(list(before.keys()) + list(after.keys()))
                if before.get(k) != after.get(k)}
    elif details:
        diff = details

    ip = None
    ua = None
    try:
        ip = request.remote_addr
        ua = (request.headers.get("User-Agent") or "")[:200]
    except RuntimeError:
        pass

    actor_email = None
    try:
        from auth import get_current_user
        user = get_current_user()
        if user:
            if not actor_id:
                actor_id = user.get("id")
            actor_email = user.get("email")
            if not org_id:
                from auth import get_current_org
                org_ctx = get_current_org()
                if org_ctx:
                    org_id = org_ctx.get("org_id")
    except Exception:
        pass

    _executor.submit(_persist, action, entity, entity_id, actor_id,
                     actor_email, org_id, diff, ip, ua)


def _persist(action, entity, entity_id, actor_id, actor_email, org_id, diff, ip, ua):
    try:
        from database import get_db
        db = get_db()
        db.execute(
            """INSERT INTO audit_logs
               (org_id, actor_id, actor_email, action, entity, entity_id, diff_json, ip_address, user_agent)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (org_id, actor_id, actor_email, action, entity,
             str(entity_id) if entity_id else None,
             json.dumps(diff) if diff else None,
             ip, ua),
        )
        db.commit()
        db.close()
    except Exception as exc:
        logger.debug("[Audit] Persist failed: %s", exc)


def get_audit_logs(org_id: int = None, entity: str = None,
                   entity_id: str = None, actor_id: int = None,
                   limit: int = 50, offset: int = 0) -> list:
    """Query audit logs with optional filters."""
    from database import get_db
    db = get_db()
    query = "SELECT * FROM audit_logs WHERE 1=1"
    params = []
    if org_id:
        query += " AND org_id = ?"
        params.append(org_id)
    if entity:
        query += " AND entity = ?"
        params.append(entity)
    if entity_id:
        query += " AND entity_id = ?"
        params.append(entity_id)
    if actor_id:
        query += " AND actor_id = ?"
        params.append(actor_id)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = db.execute(query, params).fetchall()
    db.close()
    return [dict(r) for r in rows]
