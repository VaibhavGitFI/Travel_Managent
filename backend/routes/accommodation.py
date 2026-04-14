"""
TravelSync Pro — Accommodation Routes
Hotel search and long-stay PG/serviced options.
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, Response
from auth import get_current_user
from agents.hotel_agent import search_hotels, search_pg_options
from extensions import limiter
from services.http_client import http as requests_http

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


@accommodation_bp.route("/photo", methods=["GET"])
@limiter.limit("300 per minute")
def place_photo():
    """
    GET /api/accommodation/photo?ref=PHOTO_REFERENCE&max=600
    Open proxy for Google Places Photo API — no auth required so <img> tags
    load directly without session cookies.  API key stays server-side.
    Rate-limited to prevent abuse.
    """
    import re, urllib.parse

    try:
        max_width = min(int(request.args.get("max", 600)), 1600)
    except (ValueError, TypeError):
        max_width = 600

    # Two modes:
    #   ?ref=PHOTO_REFERENCE  → old Places API  (hotel photos)
    #   ?name=places/.../photos/...  → new Places API (New) (PG/long-stay photos)
    ref  = (request.args.get("ref")  or "").strip()
    name = (request.args.get("name") or "").strip()

    if not ref and not name:
        return Response(status=400)

    try:
        from services.maps_service import maps
        if not maps.configured:
            return Response(status=503)

        if ref:
            # Old Places API photo reference
            if not re.match(r'^[A-Za-z0-9_\-]+$', ref):
                return Response(status=400)
            resp = requests_http.get(
                "https://maps.googleapis.com/maps/api/place/photo",
                params={"maxwidth": max_width, "photo_reference": ref, "key": maps.api_key},
                timeout=10,
                allow_redirects=True,
            )
        else:
            # New Places API (New) photo resource name e.g. "places/ChIJ.../photos/AUc7..."
            # Validate: only path-safe chars, must start with "places/"
            decoded_name = urllib.parse.unquote(name)
            if not re.match(r'^places/[A-Za-z0-9_\-]+/photos/[A-Za-z0-9_\-]+$', decoded_name):
                return Response(status=400)
            resp = requests_http.get(
                f"https://places.googleapis.com/v1/{decoded_name}/media",
                params={"maxWidthPx": max_width, "key": maps.api_key, "skipHttpRedirect": "true"},
                timeout=10,
                allow_redirects=True,
            )
            # New API returns JSON with photoUri when skipHttpRedirect=true
            if resp.status_code == 200 and resp.headers.get("Content-Type", "").startswith("application/json"):
                photo_uri = resp.json().get("photoUri", "")
                if photo_uri:
                    resp = requests_http.get(photo_uri, timeout=10, allow_redirects=True)
                else:
                    return Response(status=404)

        if resp.status_code != 200:
            return Response(status=404)

        content_type = resp.headers.get("Content-Type", "image/jpeg")
        return Response(
            resp.content,
            status=200,
            headers={
                "Content-Type": content_type,
                "Cache-Control": "public, max-age=86400",
            },
        )
    except Exception:
        identifier = ref or name
        logger.exception("[Accommodation] photo proxy failed for %.30s", identifier)
        return Response(status=502)


@accommodation_bp.route("/verify-area", methods=["GET"])
@limiter.limit("60 per minute")
def verify_area():
    """
    GET /api/accommodation/verify-area?place_id=X&destination=Y

    Checks whether the Google place identified by place_id lies within the
    destination city using geocoded coordinates — no keyword matching.
    Returns { valid, distance_km, area_name, city_name }.
    Always returns valid=true when coordinates cannot be resolved (fail-open).
    """
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    place_id    = (request.args.get("place_id") or "").strip()
    destination = (request.args.get("destination") or "").strip()

    if not place_id or not destination:
        return jsonify({"valid": True, "distance_km": 0.0, "area_name": "", "city_name": destination}), 200

    try:
        from services.maps_service import maps
        result = maps.verify_area_in_city(place_id, destination)
        return jsonify(result), 200
    except Exception:
        logger.exception("[Accommodation] verify-area failed for place_id=%s, dest=%s", place_id, destination)
        return jsonify({"valid": True, "distance_km": 0.0, "area_name": "", "city_name": destination}), 200


@accommodation_bp.route("/autocomplete", methods=["GET"])
@limiter.limit("120 per minute")
def city_autocomplete():
    """GET /api/accommodation/autocomplete?q=mum — city/area suggestions for search inputs."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    query         = (request.args.get("q") or request.args.get("query") or "").strip()
    restrict_city = (request.args.get("city") or "").strip() or None
    place_search  = request.args.get("place") == "1"
    if len(query) < 2:
        return jsonify({"suggestions": []}), 200

    try:
        from services.maps_service import maps
        suggestions = maps.autocomplete_cities(
            query, restrict_city=restrict_city, place_search=place_search)
        return jsonify({"suggestions": suggestions}), 200
    except Exception:
        logger.exception("[Accommodation] autocomplete failed for %r", query)
        return jsonify({"suggestions": []}), 200


@accommodation_bp.route("/search", methods=["GET"])
@limiter.limit("30 per minute")
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
        "client_place_id": request.args.get("client_place_id", ""),
    }

    try:
        result = search_hotels(payload)
        return jsonify(result), 200
    except Exception as e:
        logger.exception("[Accommodation] search failed for %s", destination)
        return jsonify({"success": False, "error": "Hotel search failed"}), 500


@accommodation_bp.route("/pg-options", methods=["POST"])
@limiter.limit("20 per minute")
def pg_options():
    """POST /api/accommodation/pg-options — search PG/serviced options for long stays."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    destination   = (data.get("destination") or data.get("city") or "").strip()
    duration_days = max(_safe_int(data.get("duration_days"), 1), 1)
    client_place_id = (data.get("client_place_id") or "").strip()
    if not destination:
        return jsonify({"success": False, "error": "destination (or city) is required"}), 400

    # Resolve meeting location coordinates if a place_id was supplied.
    # This anchors the PG search to the actual meeting pin, not just city centre.
    meeting_coords = None
    if client_place_id:
        try:
            from services.maps_service import maps
            if maps.configured:
                resolved = maps.geocode_by_place_id(client_place_id)
                if resolved.get("source") != "fallback" and resolved.get("lat"):
                    meeting_coords = resolved
        except Exception:
            logger.warning("[Accommodation] pg_options: could not resolve place_id %s", client_place_id)

    try:
        options = search_pg_options({
            "destination":    destination,
            "duration_days":  duration_days,
            "budget":         data.get("budget", "moderate"),
            "meeting_coords": meeting_coords,
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
