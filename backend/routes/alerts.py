"""
TravelSync Pro — Smart Alerts Routes
Returns proactive, user-specific alerts for the dashboard.
"""
import logging
from flask import Blueprint, jsonify
from auth import get_current_user
from agents.alerts_agent import get_user_alerts

logger = logging.getLogger(__name__)

alerts_bp = Blueprint("alerts", __name__, url_prefix="/api/alerts")


@alerts_bp.route("", methods=["GET"])
def list_alerts():
    """GET /api/alerts — smart alerts for the current user."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        alerts = get_user_alerts(user)
        return jsonify({"success": True, "alerts": alerts, "total": len(alerts)}), 200
    except Exception as e:
        logger.exception("Failed to generate alerts")
        return jsonify({"success": False, "error": "Failed to generate alerts", "alerts": []}), 500
