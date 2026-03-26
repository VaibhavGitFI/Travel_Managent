"""TravelSync Pro — Audit Log Routes"""
import logging
from flask import Blueprint, request, jsonify
from auth import get_current_user, admin_required, get_current_org
from services.audit_service import get_audit_logs
from extensions import limiter

logger = logging.getLogger(__name__)
audit_bp = Blueprint("audit", __name__, url_prefix="/api/audit")


@audit_bp.route("", methods=["GET"])
@limiter.limit("30 per minute")
@admin_required
def list_audit_logs():
    """GET /api/audit — query audit logs (admin only)."""
    org = get_current_org()
    org_id = org["org_id"] if org else None
    entity = request.args.get("entity")
    entity_id = request.args.get("entity_id")
    actor_id = request.args.get("actor_id", type=int)
    limit = min(100, request.args.get("limit", 50, type=int))
    offset = request.args.get("offset", 0, type=int)

    logs = get_audit_logs(org_id=org_id, entity=entity, entity_id=entity_id,
                          actor_id=actor_id, limit=limit, offset=offset)
    return jsonify({"success": True, "logs": logs, "count": len(logs)}), 200
