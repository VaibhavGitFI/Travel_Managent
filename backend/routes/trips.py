"""
TravelSync Pro — Trip Planning Routes
Orchestrates all agents in parallel to produce a complete trip plan.
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from auth import get_current_user
from agents.orchestrator import plan_trip
from agents.recommendation_agent import get_recommendations
from database import get_db
from extensions import limiter
from services.task_queue import task_queue


logger = logging.getLogger(__name__)


def _emit_trip_update(user_id: int, destination: str, result: dict) -> None:
    """Notify user that their trip plan is ready via all configured channels. Silent on failure."""
    try:
        hotel_count = len(result.get("hotels", {}).get("results", []))
        mode_count = len(result.get("travel", {}).get("modes", {}).get("available", []))
        detail = []
        if hotel_count:
            detail.append(f"{hotel_count} hotel{'s' if hotel_count > 1 else ''}")
        if mode_count:
            detail.append(f"{mode_count} travel option{'s' if mode_count > 1 else ''}")
        summary = (", ".join(detail) + " found") if detail else "Plan is ready"

        from services.notification_service import notify
        notify(
            user_id=user_id,
            title=f"Trip Plan Ready — {destination}",
            message=summary,
            notification_type="trip_plan_ready",
            extra={"destination": destination},
        )
    except Exception:
        logger.debug("[Trips] _emit_trip_update failed silently")

trips_bp = Blueprint("trips", __name__, url_prefix="/api")


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_trip_input(data: dict, user: dict) -> dict:
    origin = (data.get("origin") or data.get("from_city") or "").strip()
    destination = (data.get("destination") or data.get("to_city") or data.get("city") or "").strip()
    start_date = (data.get("start_date") or data.get("travel_date") or "").strip()
    end_date = (data.get("end_date") or data.get("return_date") or start_date).strip()
    travel_dates = (data.get("travel_dates") or "").strip()
    if not travel_dates and start_date:
        travel_dates = f"{start_date} to {end_date}" if end_date else start_date

    duration_days = _safe_int(data.get("duration_days"), 0)
    if duration_days <= 0 and start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date or start_date, "%Y-%m-%d")
            duration_days = max((end_dt - start_dt).days + 1, 1)
        except ValueError:
            duration_days = 1
    if duration_days <= 0:
        duration_days = 1

    num_travelers = _safe_int(data.get("num_travelers"), 1)
    if num_travelers <= 0:
        num_travelers = 1

    purpose = (data.get("purpose") or "client meeting").replace("_", " ")

    return {
        "destination": destination,
        "origin": origin,
        "trip_type": data.get("trip_type", "domestic"),
        "purpose": purpose,
        "travelers": data.get("travelers", []),
        "traveler_names": data.get("traveler_names", []),
        "traveler_origins": data.get("traveler_origins", []),
        "num_travelers": num_travelers,
        "travel_dates": travel_dates,
        "start_date": start_date,
        "end_date": end_date,
        "duration_days": duration_days,
        "meeting_time": data.get("meeting_time", "10:00 AM"),
        "meeting_days": data.get("meeting_days", []),
        "budget": data.get("budget", "moderate"),
        "weather": data.get("weather", ""),
        "require_veg": bool(data.get("require_veg", False)),
        "long_stay_mode": bool(data.get("long_stay_mode", False)),
        "client_address": data.get("client_address", ""),
        "is_rural": bool(data.get("is_rural", False)),
        "user_id": user.get("id", 1),
    }


def _serialize_trip(row: dict) -> dict:
    origin = row.get("origin") or row.get("from_city") or ""
    destination = row.get("destination") or row.get("to_city") or ""
    start_date = row.get("start_date") or row.get("travel_date") or ""
    end_date = row.get("end_date") or row.get("return_date") or ""
    status = row.get("status") or "draft"
    return {
        **row,
        "from_city": origin,
        "to_city": destination,
        "travel_date": start_date,
        "return_date": end_date,
        "estimated_budget": row.get("estimated_total") or row.get("budget_inr") or 0,
        "status": "pending" if status in ("submitted", "pending_approval") else status,
        "raw_status": status,
    }


@trips_bp.route("/plan-trip", methods=["POST"])
@trips_bp.route("/trips/plan", methods=["POST"])
@limiter.limit("10 per minute")
def plan_trip_route():
    """POST /api/plan-trip and /api/trips/plan — run the A2A orchestrator."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    trip_input = _normalize_trip_input(data, user)

    if not trip_input["origin"] or not trip_input["destination"]:
        return jsonify({"success": False, "error": "origin and destination are required"}), 400

    try:
        result = plan_trip(trip_input)
        # Compatibility aliases for older frontend consumers.
        result["summary"] = result.get("summary") or result.get("trip_summary", {}).get("trip_type", "")
        result["travel_options"] = result.get("travel", {}).get("modes", {})
        result["source"] = (
            result.get("travel", {}).get("data_source")
            or result.get("hotels", {}).get("data_source")
            or "live"
        )
        _emit_trip_update(user["id"], trip_input["destination"], result)
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Failed to plan trip")
        return jsonify({"success": False, "error": "Failed to plan trip"}), 500


@trips_bp.route("/trips", methods=["GET"])
def list_trips():
    """GET /api/trips — list saved trip requests for dashboard and history views."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    limit = min(_safe_int(request.args.get("limit"), 50), 200)
    db = get_db()
    try:
        if user.get("role") in ("admin", "manager", "super_admin"):
            rows = db.execute(
                "SELECT * FROM travel_requests ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM travel_requests WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user["id"], limit)
            ).fetchall()

        trips = [_serialize_trip(dict(r)) for r in rows]
        return jsonify({"success": True, "trips": trips, "total": len(trips)}), 200
    except Exception as e:
        logger.exception("Failed to list trips")
        return jsonify({"success": False, "error": "Failed to load trips"}), 500
    finally:
        db.close()


@trips_bp.route("/trips/<string:trip_id>", methods=["GET"])
def get_trip(trip_id: str):
    """GET /api/trips/<id> — fetch a single trip by numeric id or request_id."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    db = get_db()
    try:
        if trip_id.isdigit():
            row = db.execute("SELECT * FROM travel_requests WHERE id = ?", (int(trip_id),)).fetchone()
        else:
            row = db.execute("SELECT * FROM travel_requests WHERE request_id = ?", (trip_id,)).fetchone()

        if not row:
            return jsonify({"success": False, "error": "Trip not found"}), 404

        trip = dict(row)
        if user.get("role") not in ("admin", "manager", "super_admin") and trip.get("user_id") != user.get("id"):
            return jsonify({"success": False, "error": "Forbidden"}), 403

        return jsonify({"success": True, "trip": _serialize_trip(trip)}), 200
    except Exception as e:
        logger.exception("Failed to get trip %s", trip_id)
        return jsonify({"success": False, "error": "Failed to load trip details"}), 500
    finally:
        db.close()


@trips_bp.route("/trips/recommendations", methods=["POST"])
def trip_recommendations():
    """POST /api/trips/recommendations — smart suggestions based on past trips + policy."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    destination = (data.get("destination") or "").strip()
    if not destination:
        return jsonify({"success": False, "error": "destination is required"}), 400

    duration_days = _safe_int(data.get("duration_days"), 3)

    try:
        result = get_recommendations(user["id"], destination, duration_days)
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Failed to get recommendations")
        return jsonify({"success": False, "error": "Failed to generate recommendations"}), 500


@trips_bp.route("/trips/plan-async", methods=["POST"])
@limiter.limit("10 per minute")
def plan_trip_async():
    """POST /api/trips/plan-async — submit trip planning as background task."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    trip_input = _normalize_trip_input(data, user)

    if not trip_input["origin"] or not trip_input["destination"]:
        return jsonify({"success": False, "error": "origin and destination are required"}), 400

    task_id = task_queue.submit(
        fn=plan_trip,
        args=(trip_input,),
        user_id=user["id"],
        task_type="plan_trip",
    )

    return jsonify({
        "success": True,
        "task_id": task_id,
        "message": f"Trip planning started for {trip_input['destination']}",
    }), 202


@trips_bp.route("/tasks/<string:task_id>", methods=["GET"])
def get_task_status(task_id):
    """GET /api/tasks/<id> — check status of a background task."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    status = task_queue.get_status(task_id)
    if status["status"] == "not_found":
        return jsonify({"success": False, "error": "Task not found"}), 404

    return jsonify({"success": True, **status}), 200


@trips_bp.route("/tasks/<string:task_id>/result", methods=["GET"])
def get_task_result(task_id):
    """GET /api/tasks/<id>/result — get result of a completed task."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    result = task_queue.get_result(task_id)
    status_code = 200 if result.get("success") else (202 if result.get("status") in ("pending", "running") else 500)
    return jsonify(result), status_code


@trips_bp.route("/tasks", methods=["GET"])
def list_tasks():
    """GET /api/tasks — list recent background tasks for current user."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    tasks = task_queue.list_tasks(user_id=user["id"])
    return jsonify({"success": True, "tasks": tasks, "total": len(tasks)}), 200
