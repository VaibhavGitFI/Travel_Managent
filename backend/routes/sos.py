"""
TravelSync Pro — SOS Emergency Routes
Reverse-geocode GPS location, return local emergency numbers, nearby hospitals/police,
log to sos_events table, and broadcast alerts to managers.
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from auth import get_current_user
from extensions import limiter
from agents.sos_agent import (
    get_emergency_contacts, find_nearby_hospitals, find_nearby_police,
    reverse_geocode_location,
)
from database import get_db

logger = logging.getLogger(__name__)

sos_bp = Blueprint("sos", __name__, url_prefix="/api/sos")


def _emit_sos_alert(user: dict, city: str, message: str, lat=None, lng=None) -> None:
    """Broadcast SOS alert to all managers/admins via all configured channels. Silent on failure."""
    try:
        from services.notification_service import notify
        location_str = city or "Unknown"
        if lat and lng:
            location_str += f" ({lat:.4f}, {lng:.4f})"
        notify(
            user_id=None,
            title=f"🚨 SOS Alert from {user.get('full_name') or user.get('username')}",
            message=f"Location: {location_str}. {message or 'Needs immediate assistance.'}",
            notification_type="sos_alert",
            broadcast_to_role="manager",
            extra={
                "user_id": user["id"],
                "user_name": user.get("full_name") or user.get("username"),
                "city": city,
                "latitude": lat,
                "longitude": lng,
            },
        )
    except Exception:
        logger.debug("[SOS] _emit_sos_alert failed silently")


@sos_bp.route("", methods=["POST"])
@limiter.limit("5 per minute")
def trigger_sos():
    """
    POST /api/sos
    Body: { "city": "Mumbai", "message": "...", "latitude": 19.0, "longitude": 72.8,
            "emergency_type": "medical", "country": "India" }
    Logs the SOS event, broadcasts to managers, returns emergency contacts and nearby help.
    """
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    city = (data.get("city") or "").strip()
    country = (data.get("country") or "").strip()
    message = (data.get("message") or "").strip()
    emergency_type = (data.get("emergency_type") or "general").strip()
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    # If we have coordinates but no city, reverse-geocode
    if latitude and longitude and not city:
        try:
            geo = reverse_geocode_location(latitude, longitude)
            city = geo.get("city") or city
            country = country or geo.get("country", "")
        except Exception:
            pass

    # Log to sos_events table
    try:
        db = get_db()
        db.execute("""
            INSERT INTO sos_events (user_id, destination, location, emergency_type, message, resolved, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (
            user["id"],
            city or "Unknown",
            f"{latitude},{longitude}" if latitude and longitude else city or "Unknown",
            emergency_type,
            message,
            datetime.now().isoformat(),
        ))
        db.commit()
        db.close()
    except Exception:
        logger.warning("[SOS] Failed to log SOS event to database")  # DB failure must not block emergency response

    # Broadcast to managers
    _emit_sos_alert(user, city, message, latitude, longitude)

    # Get emergency contacts based on detected city/country
    emergency = get_emergency_contacts(city, country)

    # Get nearby hospitals and police using coordinates if available
    hospitals = find_nearby_hospitals(city=city, lat=latitude, lng=longitude, limit=5)
    police = find_nearby_police(lat=latitude, lng=longitude, city=city, limit=3)

    return jsonify({
        "success": True,
        "message": "SOS alert sent to your manager.",
        "emergency_numbers": emergency.get("numbers", {}),
        "embassy": emergency.get("embassy"),
        "nearby_hospitals": hospitals,
        "nearby_police": police,
        "city": city or "Unknown",
        "country": country or emergency.get("country", ""),
        "timestamp": datetime.now().isoformat(),
    }), 200


@sos_bp.route("/contacts", methods=["GET"])
def emergency_contacts():
    """
    GET /api/sos/contacts?city=Mumbai&country=India&lat=19.0&lng=72.8
    Return local emergency numbers, hospitals, police stations, and embassy info.
    """
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    city = (request.args.get("city") or "").strip()
    country = (request.args.get("country") or "").strip()
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)

    # Reverse geocode if coordinates provided but no city
    if lat and lng and not city:
        try:
            geo = reverse_geocode_location(lat, lng)
            city = geo.get("city") or city
            country = country or geo.get("country", "")
        except Exception:
            pass

    try:
        result = get_emergency_contacts(city, country)
        result["nearby_hospitals"] = find_nearby_hospitals(city=city, lat=lat, lng=lng, limit=5)
        result["nearby_police"] = find_nearby_police(lat=lat, lng=lng, city=city, limit=3)
        return jsonify(result), 200
    except Exception:
        logger.exception("Failed to load emergency contacts")
        return jsonify({"success": False, "error": "Failed to load emergency contacts"}), 500


@sos_bp.route("/reverse-geocode", methods=["POST"])
def reverse_geocode():
    """
    POST /api/sos/reverse-geocode
    Body: { "latitude": 19.076, "longitude": 72.877 }
    Returns city, country, and formatted address from GPS coordinates.
    """
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    lat = data.get("latitude")
    lng = data.get("longitude")

    if not lat or not lng:
        return jsonify({"success": False, "error": "latitude and longitude are required"}), 400

    geo = reverse_geocode_location(lat, lng)
    # Also return emergency contacts for the detected location
    contacts = get_emergency_contacts(geo.get("city", ""), geo.get("country", ""))

    return jsonify({
        "success": True,
        **geo,
        "emergency_numbers": contacts.get("numbers", {}),
        "embassy": contacts.get("embassy"),
    }), 200
