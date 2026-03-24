"""
TravelSync Pro — Accommodation Routes
Hotel search and long-stay PG/serviced options.
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from auth import get_current_user
from agents.hotel_agent import search_hotels, search_pg_options

logger = logging.getLogger(__name__)

accommodation_bp = Blueprint("accommodation", __name__, url_prefix="/api/accommodation")


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _duration_days(check_in: str, check_out: str) -> int:
    if not check_in or not check_out:
        return 1
    try:
        start = datetime.strptime(check_in, "%Y-%m-%d")
        end = datetime.strptime(check_out, "%Y-%m-%d")
        return max((end - start).days, 1)
    except ValueError:
        return 1


@accommodation_bp.route("/search", methods=["GET"])
def search():
    """GET /api/accommodation/search — search hotels for destination/date range."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    destination = (
        request.args.get("city", "").strip()
        or request.args.get("destination", "").strip()
    )
    if not destination:
        return jsonify({"success": False, "error": "city (or destination) is required"}), 400

    check_in = request.args.get("check_in", "").strip()
    check_out = request.args.get("check_out", "").strip()
    duration_days = _duration_days(check_in, check_out)
    guests = max(_safe_int(request.args.get("guests"), 1), 1)

    payload = {
        "destination": destination,
        "start_date": check_in,
        "end_date": check_out,
        "duration_days": duration_days,
        "num_travelers": guests,
        "budget": request.args.get("budget", "moderate"),
        "require_veg": request.args.get("require_veg", "false").lower() == "true",
        "is_rural": request.args.get("is_rural", "false").lower() == "true",
        "client_address": request.args.get("client_address", ""),
    }

    try:
        result = search_hotels(payload)
        return jsonify(result), 200
    except Exception as e:
        logger.exception("[Accommodation] search failed for %s", destination)
        return jsonify({"success": False, "error": "Hotel search failed"}), 500


@accommodation_bp.route("/pg-options", methods=["POST"])
def pg_options():
    """POST /api/accommodation/pg-options — search PG/serviced options for long stays."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    destination = (data.get("destination") or data.get("city") or "").strip()
    duration_days = max(_safe_int(data.get("duration_days"), 1), 1)
    if not destination:
        return jsonify({"success": False, "error": "destination (or city) is required"}), 400

    try:
        options = search_pg_options({
            "destination": destination,
            "duration_days": duration_days,
            "budget": data.get("budget", "moderate"),
        })
        return jsonify({
            "success": True,
            "destination": destination,
            "duration_days": duration_days,
            "pg_options": options,
            "source": options[0].get("source", "fallback") if options else "fallback",
        }), 200
    except Exception as e:
        logger.exception("[Accommodation] pg_options failed for %s", destination)
        return jsonify({"success": False, "error": "PG search failed"}), 500
