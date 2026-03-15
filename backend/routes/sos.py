"""
TravelSync Pro — SOS Emergency Routes
Log SOS events, broadcast to manager, return local emergency numbers and nearby hospitals.
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from auth import get_current_user
from agents.sos_agent import get_emergency_contacts, find_nearby_hospitals
from database import get_db

sos_bp = Blueprint("sos", __name__, url_prefix="/api/sos")


def _emit_sos_alert(user: dict, city: str, message: str) -> None:
    """Broadcast SOS alert to all managers/admins via SocketIO. Silent on failure."""
    try:
        from extensions import socketio
        db = get_db()
        managers = db.execute(
            "SELECT id FROM users WHERE role IN ('manager','admin')"
        ).fetchall()
        db.close()

        payload = {
            "type": "sos_alert",
            "title": f"🚨 SOS Alert from {user.get('full_name') or user.get('username')}",
            "message": f"Location: {city or 'Unknown'}. {message or 'Needs immediate assistance.'}",
            "user_id": user["id"],
            "user_name": user.get("full_name") or user.get("username"),
            "city": city,
            "timestamp": datetime.now().isoformat(),
        }
        for mgr in managers:
            socketio.emit("notification", payload, to=f"user_{mgr['id']}", namespace="/")
    except Exception:
        pass


@sos_bp.route("", methods=["POST"])
def trigger_sos():
    """
    POST /api/sos
    Body: { "city": "Mumbai", "message": "Optional description", "latitude": 19.0, "longitude": 72.8 }
    Logs the SOS event and broadcasts to all managers via SocketIO.
    """
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    city = (data.get("city") or "").strip()
    message = (data.get("message") or "").strip()
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    try:
        # Log to DB
        db = get_db()
        db.execute("""
            INSERT INTO notifications (user_id, type, title, message, created_at)
            VALUES (?, 'sos', ?, ?, ?)
        """, (
            user["id"],
            f"SOS triggered by {user.get('full_name') or user.get('username')}",
            f"City: {city or 'Unknown'}. {message}",
            datetime.now().isoformat(),
        ))
        db.commit()
        db.close()
    except Exception:
        pass  # DB log failure must not block emergency response

    # Broadcast to managers
    _emit_sos_alert(user, city, message)

    # Get emergency contacts
    emergency = get_emergency_contacts(city)

    # Get nearby hospitals (async lookup; non-blocking)
    hospitals = find_nearby_hospitals(city, limit=3) if city else []

    return jsonify({
        "success": True,
        "message": "SOS alert sent to your manager.",
        "emergency_numbers": emergency.get("numbers", {}),
        "nearby_hospitals": hospitals,
        "city": city or "Unknown",
        "timestamp": datetime.now().isoformat(),
    }), 200


@sos_bp.route("/contacts", methods=["GET"])
def emergency_contacts():
    """GET /api/sos/contacts?city=Mumbai — return local emergency numbers."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    city = (request.args.get("city") or "").strip()

    try:
        result = get_emergency_contacts(city)
        hospitals = find_nearby_hospitals(city, limit=5) if city else []
        result["nearby_hospitals"] = hospitals
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
