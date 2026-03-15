"""
TravelSync Pro — Approval Routes
Manager-facing approval queue: list pending, approve, reject.
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from auth import get_current_user
from agents.request_agent import get_pending_approvals, process_approval


def _notify_requester(request_id: str, title: str, message: str, notif_type: str) -> None:
    """Emit a SocketIO notification to the request's owner. Silent on failure."""
    try:
        from extensions import socketio
        from database import get_db
        db = get_db()
        req = db.execute(
            "SELECT user_id, destination FROM travel_requests WHERE request_id = ?",
            (request_id,)
        ).fetchone()
        db.close()
        if req:
            socketio.emit(
                "notification",
                {
                    "type": notif_type,
                    "title": title,
                    "message": message,
                    "request_id": request_id,
                    "timestamp": datetime.now().isoformat(),
                },
                to=f"user_{req['user_id']}",
                namespace="/",
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
    """GET /api/approvals — list pending approval requests (manager/admin only)."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    err = _require_manager(user)
    if err:
        return err

    try:
        # Admins see all pending; managers see only those assigned to them
        if user.get("role") == "admin":
            rows = get_pending_approvals()
        else:
            rows = get_pending_approvals(approver_id=user["id"])

        serialized = [_serialize_approval(r) for r in rows]
        return jsonify({"success": True, "approvals": serialized, "total": len(serialized)}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
