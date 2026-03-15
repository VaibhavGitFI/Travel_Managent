"""
TravelSync Pro — Client Meetings Routes
CRUD for client meetings plus AI schedule optimization and venue suggestions.
Meetings can originate from any source: manual, email, WhatsApp, phone, calendar, LinkedIn.
"""
from flask import Blueprint, request, jsonify
from auth import get_current_user
from agents.meeting_agent import (
    add_meeting,
    get_all_meetings,
    update_meeting,
    delete_meeting,
    optimize_meeting_schedule,
    suggest_nearby_venues,
)

meetings_bp = Blueprint("meetings", __name__, url_prefix="/api/meetings")


def _normalize_meeting_payload(data: dict) -> dict:
    out = dict(data)
    if "trip_id" in out and "destination" not in out:
        out["destination"] = out.get("trip_id")
    if out.get("location") and not out.get("venue"):
        out["venue"] = out.get("location")
    if out.get("contact_info"):
        info = str(out.get("contact_info"))
        if "@" in info and not out.get("email"):
            out["email"] = info
        elif not out.get("contact_number"):
            out["contact_number"] = info
    return out


@meetings_bp.route("", methods=["GET"])
def list_meetings():
    """GET /api/meetings?trip_id=X — list meetings for the current user."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    destination = request.args.get("trip_id", "").strip() or request.args.get("destination", "").strip()
    meeting_date = request.args.get("date", "").strip()

    try:
        meetings = get_all_meetings(
            user_id=user["id"],
            destination=destination or None,
            meeting_date=meeting_date or None,
        )
        return jsonify({"success": True, "meetings": meetings, "total": len(meetings)}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@meetings_bp.route("", methods=["POST"])
def create_meeting():
    """POST /api/meetings — create a new client meeting."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = _normalize_meeting_payload(request.get_json(silent=True) or {})

    try:
        result = add_meeting(data, user_id=user["id"])
        status = 201 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@meetings_bp.route("/<int:meeting_id>", methods=["PUT"])
def edit_meeting(meeting_id):
    """PUT /api/meetings/<id> — update a meeting."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = _normalize_meeting_payload(request.get_json(silent=True) or {})

    try:
        result = update_meeting(meeting_id, data, user_id=user["id"])
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@meetings_bp.route("/<int:meeting_id>", methods=["DELETE"])
def remove_meeting(meeting_id):
    """DELETE /api/meetings/<id> — delete a meeting."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        result = delete_meeting(meeting_id, user_id=user["id"])
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@meetings_bp.route("/suggest-schedule", methods=["POST"])
def suggest_schedule():
    """POST /api/meetings/suggest-schedule — Gemini-powered schedule optimization."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    meetings = data.get("meetings", [])
    preferences = data.get("preferences", {})
    destination = preferences.get("destination", data.get("destination", ""))

    if not meetings:
        return jsonify({"success": False, "error": "meetings list is required"}), 400

    try:
        result = optimize_meeting_schedule(meetings, destination)
        if result is None:
            return jsonify({
                "success": False,
                "error": "Schedule optimization unavailable. Set GEMINI_API_KEY to enable.",
            }), 503
        suggestions = []
        if isinstance(result, dict):
            for day in result.get("optimized_schedule", []):
                date_label = day.get("date") or f"Day {day.get('day', '')}"
                summary = day.get("day_summary") or ""
                if summary:
                    suggestions.append({"suggestion": f"{date_label}: {summary}"})
        return jsonify({"success": True, "schedule": result, "suggestions": suggestions}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@meetings_bp.route("/nearby-venues", methods=["POST"])
def nearby_venues():
    """POST /api/meetings/nearby-venues — Google Maps venue suggestions near client offices."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    location = data.get("location", "")
    meeting_type = data.get("meeting_type", "")
    client_locations = data.get("client_locations", [])

    if not location:
        return jsonify({"success": False, "error": "location is required"}), 400

    # Treat location as both the destination and a client location seed
    if not client_locations:
        client_locations = [location]

    try:
        result = suggest_nearby_venues(location, client_locations)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
