"""
TravelSync Pro — Approval Routes
Manager-facing approval queue: list pending, approve, reject.
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from auth import get_current_user
from agents.request_agent import get_pending_approvals, process_approval

logger = logging.getLogger(__name__)


def _notify_requester(request_id: str, title: str, message: str, notif_type: str) -> None:
    """Notify the request owner via all configured channels. Silent on failure."""
    try:
        from database import get_db
        db = get_db()
        req = db.execute(
            "SELECT user_id FROM travel_requests WHERE request_id = ?",
            (request_id,)
        ).fetchone()
        db.close()
        if req:
            from services.notification_service import notify
            notify(
                user_id=req["user_id"],
                title=title,
                message=message,
                notification_type=notif_type,
                request_id=request_id,
                action_url="/requests",
            )
    except Exception:
        pass

approvals_bp = Blueprint("approvals", __name__, url_prefix="/api/approvals")


def _serialize_approval(row: dict) -> dict:
    status = row.get("status", "pending")
    mapped_status = "pending" if status == "pending_approval" else status
    return {
        **row,
        "raw_status": status,
        "status": mapped_status,
        "from_city": row.get("origin", ""),
        "to_city": row.get("destination", ""),
        "travel_date": row.get("start_date") or "",
        "return_date": row.get("end_date") or "",
        "estimated_budget": row.get("estimated_total") or row.get("budget_inr") or 0,
        "employee_name": row.get("requester_name") or row.get("full_name") or "",
    }


def _require_manager(user):
    """Return a 403 response tuple if user is not a manager or admin, else None."""
    if user.get("role") not in ("admin", "manager"):
        return jsonify({"success": False, "error": "Manager or admin access required"}), 403
    return None


@approvals_bp.route("", methods=["GET"])
def list_approvals():
    """GET /api/approvals — managers see pending queue, employees see their own request statuses."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        role = user.get("role", "employee")

        # Managers/admins see the full approval queue
        if role in ("admin", "manager"):
            if role == "admin":
                rows = get_pending_approvals()
            else:
                rows = get_pending_approvals(approver_id=user["id"])
            serialized = [_serialize_approval(r) for r in rows]
            return jsonify({"success": True, "approvals": serialized, "total": len(serialized), "view": "manager"}), 200

        # Employees see their own requests with approval status
        from database import get_db
        db = get_db()
        rows = db.execute(
            """SELECT tr.request_id, tr.destination, tr.origin, tr.start_date, tr.end_date,
                      tr.purpose, tr.estimated_total, tr.status,
                      a.status as approval_status, a.comments, a.decided_at,
                      u.full_name as approver_name
               FROM travel_requests tr
               LEFT JOIN approvals a ON tr.request_id = a.request_id
               LEFT JOIN users u ON a.approver_id = u.id
               WHERE tr.user_id = ?
               ORDER BY tr.created_at DESC LIMIT 20""",
            (user["id"],),
        ).fetchall()
        db.close()

        items = []
        for r in rows:
            row = dict(r)
            items.append({
                "request_id": row.get("request_id"),
                "from_city": row.get("origin", ""),
                "to_city": row.get("destination", ""),
                "travel_date": row.get("start_date", ""),
                "return_date": row.get("end_date", ""),
                "purpose": row.get("purpose", ""),
                "estimated_budget": row.get("estimated_total", 0),
                "status": row.get("status", "draft"),
                "approval_status": row.get("approval_status"),
                "approver_name": row.get("approver_name"),
                "comments": row.get("comments"),
                "decided_at": row.get("decided_at"),
            })
        return jsonify({"success": True, "approvals": items, "total": len(items), "view": "employee"}), 200

    except Exception as e:
        logger.exception("[Approvals] list_approvals failed")
        return jsonify({"success": False, "error": "Failed to load approvals"}), 500


@approvals_bp.route("/<string:request_id>/approve", methods=["POST"])
def approve_request(request_id):
    """POST /api/approvals/<id>/approve — approve a travel request."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    err = _require_manager(user)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    comments = data.get("comments", "")

    try:
        result = process_approval(request_id, approver_id=user["id"],
                                  action="approve", comments=comments)
        if result.get("success"):
            # Look up destination for the notification message
            try:
                from database import get_db
                db = get_db()
                req = db.execute(
                    "SELECT destination FROM travel_requests WHERE request_id = ?",
                    (request_id,)
                ).fetchone()
                db.close()
                dest = req["destination"] if req else request_id
            except Exception:
                dest = request_id
            _notify_requester(
                request_id,
                title="Trip Request Approved ✅",
                message=f"Your trip to {dest} has been approved. You can now proceed with booking.",
                notif_type="approval",
            )
            try:
                from extensions import socketio
                from database import get_db as _get_db
                _db = _get_db()
                _req = _db.execute(
                    "SELECT user_id FROM travel_requests WHERE request_id = ?",
                    (request_id,)
                ).fetchone()
                _db.close()
                # Notify the requester specifically
                if _req:
                    socketio.emit("data_changed", {"entity": "requests"}, to=f"user_{_req['user_id']}", namespace="/")
                    socketio.emit("data_changed", {"entity": "approvals"}, to=f"user_{_req['user_id']}", namespace="/")
                # Also notify the approver
                socketio.emit("data_changed", {"entity": "approvals"}, to=f"user_{user['id']}", namespace="/")
            except Exception:
                pass
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        logger.exception("[Approvals] approve_request failed for %s", request_id)
        return jsonify({"success": False, "error": "Approval processing failed"}), 500


@approvals_bp.route("/<string:request_id>/reject", methods=["POST"])
def reject_request(request_id):
    """POST /api/approvals/<id>/reject — reject a travel request with a reason."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    err = _require_manager(user)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    reason = data.get("reason", data.get("comments", ""))

    try:
        result = process_approval(request_id, approver_id=user["id"],
                                  action="reject", comments=reason)
        if result.get("success"):
            try:
                from database import get_db
                db = get_db()
                req = db.execute(
                    "SELECT destination FROM travel_requests WHERE request_id = ?",
                    (request_id,)
                ).fetchone()
                db.close()
                dest = req["destination"] if req else request_id
            except Exception:
                dest = request_id
            _notify_requester(
                request_id,
                title="Trip Request Rejected ❌",
                message=f"Your trip to {dest} was not approved. Reason: {reason or 'See comments.'}",
                notif_type="rejection",
            )
            try:
                from extensions import socketio
                from database import get_db as _get_db
                _db = _get_db()
                _req = _db.execute(
                    "SELECT user_id FROM travel_requests WHERE request_id = ?",
                    (request_id,)
                ).fetchone()
                _db.close()
                if _req:
                    socketio.emit("data_changed", {"entity": "requests"}, to=f"user_{_req['user_id']}", namespace="/")
                    socketio.emit("data_changed", {"entity": "approvals"}, to=f"user_{_req['user_id']}", namespace="/")
                socketio.emit("data_changed", {"entity": "approvals"}, to=f"user_{user['id']}", namespace="/")
            except Exception:
                pass
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        logger.exception("[Approvals] reject_request failed for %s", request_id)
        return jsonify({"success": False, "error": "Rejection processing failed"}), 500
