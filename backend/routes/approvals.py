"""
TravelSync Pro — Approval Routes
Manager-facing approval queue: list pending, approve, reject.
"""
from flask import Blueprint, request, jsonify
from auth import get_current_user
from agents.request_agent import get_pending_approvals, process_approval

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
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
