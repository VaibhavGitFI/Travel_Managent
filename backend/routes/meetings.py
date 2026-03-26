"""
TravelSync Pro — Client Meetings Routes
CRUD for client meetings plus AI schedule optimization and venue suggestions.
Meetings can originate from any source: manual, email, WhatsApp, phone, calendar, LinkedIn.
"""
import logging
from flask import Blueprint, request, jsonify
from auth import get_current_user, get_current_org
from agents.meeting_agent import (
    add_meeting,
    get_all_meetings,
    update_meeting,
    delete_meeting,
    optimize_meeting_schedule,
    suggest_nearby_venues,
    parse_meeting_text,
)
from extensions import limiter
from validators import ValidationError, validate_string, validate_email as v_email

logger = logging.getLogger(__name__)

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
    """GET /api/meetings?trip_id=X&page=1&per_page=20&search=X — list meetings with pagination and search."""
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
            role=user.get("role", "employee"),
        )

        # Search filter
        search = (request.args.get("search") or "").strip().lower()
        if search:
            meetings = [
                m for m in meetings
                if search in (m.get("client_name") or "").lower()
                or search in (m.get("company") or "").lower()
                or search in (m.get("location") or m.get("venue") or "").lower()
            ]

        total = len(meetings)

        # Pagination
        try:
            page = max(1, int(request.args.get("page", 1)))
            per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        except (ValueError, TypeError):
            page, per_page = 1, 20

        total_pages = max(1, -(-total // per_page))
        start = (page - 1) * per_page
        items = meetings[start:start + per_page]

        return jsonify({
            "success": True,
            "meetings": items,
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }), 200
    except Exception as e:
        logger.exception("Failed to list meetings")
        return jsonify({"success": False, "error": "Failed to load meetings"}), 500


@meetings_bp.route("", methods=["POST"])
@limiter.limit("20 per minute")
def create_meeting():
    """POST /api/meetings — create a new client meeting."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = _normalize_meeting_payload(request.get_json(silent=True) or {})

    try:
        validate_string(data, "client_name", min_len=2, max_len=100)
        validate_string(data, "company", max_len=100, required=False)
        validate_string(data, "agenda", max_len=500, required=False)
        v_email(data, "email", required=False)
    except ValidationError as e:
        return jsonify({"success": False, "error": e.message}), 400

    try:
        org = get_current_org()
        oid = org["org_id"] if org else None
        result = add_meeting(data, user_id=user["id"], org_id=oid)
        status = 201 if result.get("success") else 400
        if result.get("success"):
            try:
                from extensions import socketio
                socketio.emit("data_changed", {"entity": "meetings"}, namespace="/")
            except Exception:
                pass
        return jsonify(result), status
    except Exception as e:
        logger.exception("Failed to create meeting")
        return jsonify({"success": False, "error": "Failed to create meeting"}), 500


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
        if result.get("success"):
            try:
                from extensions import socketio
                socketio.emit("data_changed", {"entity": "meetings"}, namespace="/")
            except Exception:
                pass
        return jsonify(result), status
    except Exception as e:
        logger.exception("Failed to update meeting %s", meeting_id)
        return jsonify({"success": False, "error": "Failed to update meeting"}), 500


@meetings_bp.route("/<int:meeting_id>", methods=["DELETE"])
def remove_meeting(meeting_id):
    """DELETE /api/meetings/<id> — delete a meeting."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        result = delete_meeting(meeting_id, user_id=user["id"])
        status = 200 if result.get("success") else 400
        if result.get("success"):
            try:
                from extensions import socketio
                socketio.emit("data_changed", {"entity": "meetings"}, namespace="/")
            except Exception:
                pass
        return jsonify(result), status
    except Exception as e:
        logger.exception("Failed to delete meeting %s", meeting_id)
        return jsonify({"success": False, "error": "Failed to delete meeting"}), 500


@meetings_bp.route("/suggest-schedule", methods=["POST"])
@limiter.limit("10 per minute")
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
        logger.exception("Failed to optimize meeting schedule")
        return jsonify({"success": False, "error": "Failed to optimize meeting schedule"}), 500


@meetings_bp.route("/parse-text", methods=["POST"])
def parse_text():
    """
    POST /api/meetings/parse-text
    Body: { "text": "<raw email or WhatsApp text>", "source_type": "email"|"whatsapp" }
    Returns extracted meeting fields ready to pre-fill the create form.
    """
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    source_hint = data.get("source_type", "email")

    if not text:
        return jsonify({"success": False, "error": "text is required"}), 400

    try:
        result = parse_meeting_text(text, source_hint=source_hint)
        status = 200 if result.get("success") else 422
        return jsonify(result), status
    except Exception as e:
        logger.exception("Failed to parse meeting text")
        return jsonify({"success": False, "error": "Failed to parse meeting text"}), 500


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
        logger.exception("Failed to suggest nearby venues")
        return jsonify({"success": False, "error": "Failed to suggest nearby venues"}), 500
