"""
TravelSync Pro — Travel Request Routes
Create, list, and retrieve travel requests.
Status flow: draft -> submitted -> pending_approval -> approved -> booked -> in_progress -> completed
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from auth import get_current_user
from agents.request_agent import (
    create_request,
    get_requests,
    get_request_detail,
    update_request,
    submit_request,
    update_request_status,
    check_and_auto_transition,
    generate_trip_report,
)
from agents.budget_forecast_agent import forecast_budget

logger = logging.getLogger(__name__)


def _notify_manager_of_new_request(request_id: str, destination: str, requester_name: str) -> None:
    """Notify the assigned approver via all configured channels. Silent on failure."""
    try:
        from database import get_db
        db = get_db()
        approval = db.execute(
            "SELECT approver_id FROM approvals WHERE request_id = ? AND status = 'pending' LIMIT 1",
            (request_id,)
        ).fetchone()
        db.close()
        if approval and approval["approver_id"]:
            from services.notification_service import notify
            notify(
                user_id=approval["approver_id"],
                title="New Approval Request",
                message=f"{requester_name} requested a trip to {destination}. Awaiting your approval.",
                notification_type="approval_request",
                request_id=request_id,
                action_url="/approvals",
            )
    except Exception:
        pass

requests_bp = Blueprint("requests", __name__, url_prefix="/api/requests")

# Per diem rates (INR/day) by city tier
_PER_DIEM_TIERS = {
    "tier1": {  # Mumbai, Delhi, Bangalore, Hyderabad, Chennai, Kolkata, Pune
        "hotel": 6000, "meals": 1200, "local_transport": 800, "incidentals": 500,
        "cities": ["mumbai", "delhi", "bangalore", "bengaluru", "hyderabad",
                   "chennai", "kolkata", "pune", "gurgaon", "noida"],
    },
    "tier2": {  # Other major cities
        "hotel": 3500, "meals": 800, "local_transport": 500, "incidentals": 300,
        "cities": ["ahmedabad", "jaipur", "surat", "lucknow", "kochi", "nagpur",
                   "bhopal", "indore", "chandigarh", "goa", "vadodara"],
    },
    "tier3": {  # Smaller cities
        "hotel": 2000, "meals": 500, "local_transport": 300, "incidentals": 200,
        "cities": [],  # fallback
    },
    "international": {  # Flat international rate (USD equivalent in INR)
        "hotel": 15000, "meals": 3000, "local_transport": 2000, "incidentals": 1000,
        "cities": ["new york", "london", "singapore", "dubai", "tokyo", "paris",
                   "berlin", "sydney", "toronto", "san francisco"],
    },
}


def _get_per_diem(city: str, days: int) -> dict:
    city_lower = city.lower().strip()
    tier = "tier3"
    for tier_name, info in _PER_DIEM_TIERS.items():
        if any(c in city_lower for c in info.get("cities", [])):
            tier = tier_name
            break

    rates = {k: v for k, v in _PER_DIEM_TIERS[tier].items() if k != "cities"}
    daily_total = sum(rates.values())
    total = daily_total * days

    return {
        "city": city,
        "tier": tier,
        "days": days,
        "daily_rates": rates,
        "daily_total": daily_total,
        "total_allowance": total,
        "currency": "INR",
        "note": (
            "International rates converted at approximate INR values"
            if tier == "international" else
            "Rates as per company travel policy. Actual reimbursement subject to receipts."
        ),
    }


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


@requests_bp.route("/budget-forecast", methods=["POST"])
def budget_forecast():
    """POST /api/requests/budget-forecast — AI budget prediction for a proposed trip."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    destination = (data.get("destination") or "").strip()
    if not destination:
        return jsonify({"success": False, "error": "destination is required"}), 400

    origin = (data.get("origin") or "").strip()
    start_date = (data.get("start_date") or "").strip()
    end_date = (data.get("end_date") or start_date).strip()
    trip_type = (data.get("trip_type") or "domestic").strip()
    try:
        num_travelers = max(1, int(data.get("num_travelers", 1)))
    except (ValueError, TypeError):
        num_travelers = 1

    try:
        result = forecast_budget(
            origin=origin,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            trip_type=trip_type,
            num_travelers=num_travelers,
        )
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Failed to forecast budget")
        return jsonify({"success": False, "error": "Failed to forecast budget"}), 500


@requests_bp.route("/per-diem", methods=["GET"])
def per_diem():
    """GET /api/requests/per-diem?city=Mumbai&days=3 — city-tier based daily allowance."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    city = (request.args.get("city") or "").strip()
    try:
        days = max(1, int(request.args.get("days", 1)))
    except (ValueError, TypeError):
        days = 1

    if not city:
        return jsonify({"success": False, "error": "city query parameter is required"}), 400

    return jsonify({"success": True, **_get_per_diem(city, days)}), 200


@requests_bp.route("", methods=["GET"])
def list_requests():
    """GET /api/requests — list requests filtered by user role with optional pagination and search."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        # Silently auto-transition trips based on travel dates
        check_and_auto_transition()

        if user.get("role") in ("admin", "manager"):
            status_filter = request.args.get("status")
            rows = get_requests(status=status_filter)
        else:
            status_filter = request.args.get("status")
            rows = get_requests(user_id=user["id"], status=status_filter)

        serialized = [_serialize_request(r) for r in rows]

        # Search filter
        search = (request.args.get("search") or "").strip().lower()
        if search:
            serialized = [
                r for r in serialized
                if search in (r.get("from_city") or "").lower()
                or search in (r.get("to_city") or "").lower()
                or search in (r.get("purpose") or "").lower()
            ]

        total = len(serialized)

        # Pagination
        try:
            page = max(1, int(request.args.get("page", 1)))
            per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        except (ValueError, TypeError):
            page, per_page = 1, 20

        total_pages = max(1, -(-total // per_page))  # ceil division
        start = (page - 1) * per_page
        items = serialized[start:start + per_page]

        return jsonify({
            "success": True,
            "requests": items,
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }), 200
    except Exception as e:
        logger.exception("Failed to list travel requests")
        return jsonify({"success": False, "error": "Failed to load requests"}), 500


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
            if submit_result.get("status") == "pending_approval":
                _notify_manager_of_new_request(
                    result["request_id"],
                    data.get("destination", ""),
                    user.get("full_name") or user.get("name") or user.get("username", "Someone"),
                )

        # Notify all tabs that requests data changed
        try:
            from extensions import socketio
            socketio.emit("data_changed", {"entity": "requests"}, namespace="/")
            socketio.emit("data_changed", {"entity": "approvals"}, namespace="/")
        except Exception:
            pass

        return jsonify(result), 201
    except Exception as e:
        logger.exception("Failed to create travel request")
        return jsonify({"success": False, "error": "Failed to create request"}), 500


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
        logger.exception("Failed to get request detail for %s", request_id)
        return jsonify({"success": False, "error": "Failed to load request details"}), 500


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
        logger.exception("Failed to update request %s", request_id)
        return jsonify({"success": False, "error": "Failed to update request"}), 500


@requests_bp.route("/<string:request_id>/status", methods=["PUT"])
def update_status(request_id):
    """PUT /api/requests/<id>/status — manually transition a request status."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip()

    if not new_status:
        return jsonify({"success": False, "error": "status field is required"}), 400

    try:
        result = update_request_status(
            request_id,
            new_status,
            actor_user_id=user["id"],
            actor_role=user.get("role", "employee"),
        )
        if result.get("success"):
            # Broadcast data_changed for real-time auto-refresh
            try:
                from extensions import socketio
                socketio.emit("data_changed", {"entity": "requests"}, namespace="/")
                socketio.emit("data_changed", {"entity": "analytics"}, namespace="/")
            except Exception:
                pass
            # Notify the requester of the status change
            try:
                from database import get_db
                db = get_db()
                req = db.execute(
                    "SELECT user_id, destination FROM travel_requests WHERE request_id = ?",
                    (request_id,)
                ).fetchone()
                db.close()
                if req and req["user_id"] != user["id"]:
                    from services.notification_service import notify
                    notify(
                        user_id=req["user_id"],
                        title=f"Trip Status: {new_status.replace('_', ' ').title()}",
                        message=f"Your trip to {req['destination']} is now {new_status.replace('_', ' ')}.",
                        notification_type="status_update",
                        request_id=request_id,
                        action_url="/requests",
                    )
            except Exception:
                pass
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        logger.exception("Failed to update status for request %s", request_id)
        return jsonify({"success": False, "error": "Failed to update request status"}), 500


@requests_bp.route("/<string:request_id>/report", methods=["GET"])
def get_trip_report(request_id):
    """GET /api/requests/<id>/report — generate AI post-trip summary report."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        result = generate_trip_report(request_id)
        status = 200 if result.get("success") else 404
        return jsonify(result), status
    except Exception as e:
        logger.exception("Failed to generate trip report for %s", request_id)
        return jsonify({"success": False, "error": "Failed to generate trip report"}), 500


@requests_bp.route("/<string:request_id>/submit", methods=["POST"])
def submit_travel_request(request_id):
    """POST /api/requests/<id>/submit — submit a draft request for approval."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        result = submit_request(request_id, user_id=user["id"])
        if result.get("success"):
            try:
                from extensions import socketio
                socketio.emit("data_changed", {"entity": "requests"}, namespace="/")
                socketio.emit("data_changed", {"entity": "approvals"}, namespace="/")
            except Exception:
                pass
        if result.get("success") and result.get("status") == "pending_approval":
            # Get destination for the notification
            try:
                from database import get_db
                db = get_db()
                req = db.execute(
                    "SELECT destination FROM travel_requests WHERE request_id = ?",
                    (request_id,)
                ).fetchone()
                db.close()
                dest = req["destination"] if req else ""
            except Exception:
                dest = ""
            _notify_manager_of_new_request(
                request_id,
                dest,
                user.get("full_name") or user.get("name") or user.get("username", "Someone"),
            )
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        logger.exception("Failed to submit request %s for approval", request_id)
        return jsonify({"success": False, "error": "Failed to submit request for approval"}), 500
