"""
TravelSync Pro — Travel Request Routes
Create, list, and retrieve travel requests.
Status flow: draft -> submitted -> pending_approval -> approved -> booked -> in_progress -> completed
"""
from flask import Blueprint, request, jsonify
from auth import get_current_user
from agents.request_agent import (
    create_request,
    get_requests,
    get_request_detail,
    update_request,
    submit_request,
)

requests_bp = Blueprint("requests", __name__, url_prefix="/api/requests")


def _normalize_request_payload(data: dict) -> dict:
    origin = (data.get("origin") or data.get("from_city") or "").strip()
    destination = (data.get("destination") or data.get("to_city") or "").strip()
    start_date = (data.get("start_date") or data.get("travel_date") or "").strip()
    end_date = (data.get("end_date") or data.get("return_date") or start_date).strip()
    travel_dates = (data.get("travel_dates") or "").strip()
    if not travel_dates and start_date:
        travel_dates = f"{start_date} to {end_date}" if end_date else start_date

    out = dict(data)
    out["origin"] = origin
    out["destination"] = destination
    out["start_date"] = start_date
    out["end_date"] = end_date
    out["travel_dates"] = travel_dates
    if out.get("estimated_budget") is not None and out.get("estimated_total") is None:
        out["estimated_total"] = out.get("estimated_budget")
    return out


def _serialize_request(row: dict) -> dict:
    status = row.get("status", "draft")
    mapped_status = "pending" if status in ("submitted", "pending_approval") else status
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


@requests_bp.route("", methods=["GET"])
def list_requests():
    """GET /api/requests — list requests filtered by user role."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        # Admins and managers see all requests; employees see only their own
        if user.get("role") in ("admin", "manager"):
            status_filter = request.args.get("status")
            rows = get_requests(status=status_filter)
        else:
            status_filter = request.args.get("status")
            rows = get_requests(user_id=user["id"], status=status_filter)

        serialized = [_serialize_request(r) for r in rows]
        return jsonify({"success": True, "requests": serialized, "total": len(serialized)}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@requests_bp.route("", methods=["POST"])
def create_travel_request():
    """POST /api/requests — create a new travel request."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = _normalize_request_payload(request.get_json(silent=True) or {})

    # Support optional immediate submit action
    action = data.pop("action", "submit")

    try:
        result = create_request(data, user_id=user["id"])
        if not result.get("success"):
            return jsonify(result), 400

        # If caller requested submit in same call, run submit step
        if action == "submit" and result.get("request_id"):
            submit_result = submit_request(result["request_id"], user["id"])
            result.update(submit_result)

        return jsonify(result), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@requests_bp.route("/<string:request_id>", methods=["GET"])
def get_single_request(request_id):
    """GET /api/requests/<id> — get full detail for a single request."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        detail = get_request_detail(request_id)
        if not detail:
            return jsonify({"success": False, "error": "Request not found"}), 404
        return jsonify({"success": True, **detail}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@requests_bp.route("/<string:request_id>", methods=["PUT"])
def edit_request(request_id):
    """PUT /api/requests/<id> — update a draft request."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = _normalize_request_payload(request.get_json(silent=True) or {})

    try:
        result = update_request(request_id, data, user_id=user["id"])
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@requests_bp.route("/<string:request_id>/submit", methods=["POST"])
def submit_travel_request(request_id):
    """POST /api/requests/<id>/submit — submit a draft request for approval."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        result = submit_request(request_id, user_id=user["id"])
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
