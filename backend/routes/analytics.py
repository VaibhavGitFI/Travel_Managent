"""
TravelSync Pro — Analytics Routes
Dashboard stats, spend analysis, and policy compliance scorecard from real DB data.
"""
import logging
from flask import Blueprint, jsonify
from auth import get_current_user, get_current_org
from flask import request as flask_request
from extensions import limiter
from agents.analytics_agent import (
    get_dashboard_stats,
    get_spend_analysis,
    get_policy_compliance_scorecard,
    get_carbon_analytics,
    get_budget_tracking,
)
from agents.travel_mode_agent import calculate_carbon
from services.maps_service import maps

logger = logging.getLogger(__name__)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


@analytics_bp.route("/dashboard", methods=["GET"])
@limiter.limit("30 per minute")
def dashboard():
    """GET /api/analytics/dashboard — real-time dashboard statistics."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        result = get_dashboard_stats(user_id=user["id"])
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Failed to load dashboard stats")
        return jsonify({"success": False, "error": "Failed to load dashboard statistics"}), 500


@analytics_bp.route("/spend", methods=["GET"])
def spend():
    """GET /api/analytics/spend — monthly trend and category breakdown of expenses."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        org = get_current_org()
        result = get_spend_analysis(
            user_id=user["id"],
            org_id=org["org_id"] if org else None,
            role=user.get("role", "employee"),
        )
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Failed to load spend analysis")
        return jsonify({"success": False, "error": "Failed to load spend analysis"}), 500


@analytics_bp.route("/compliance", methods=["GET"])
def compliance():
    """GET /api/analytics/compliance — policy compliance scorecard."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        org = get_current_org()
        result = get_policy_compliance_scorecard(
            user_id=user["id"],
            org_id=org["org_id"] if org else None,
            role=user.get("role", "employee"),
        )
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Failed to load compliance scorecard")
        return jsonify({"success": False, "error": "Failed to load compliance scorecard"}), 500


@analytics_bp.route("/carbon", methods=["GET"])
def carbon():
    """GET /api/analytics/carbon — CO₂ footprint trend, department comparison, greener alternatives."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        result = get_carbon_analytics(user_id=user["id"], role=user.get("role", "employee"))
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Failed to load carbon analytics")
        return jsonify({"success": False, "error": "Failed to load carbon analytics"}), 500


@analytics_bp.route("/budget", methods=["GET"])
def budget():
    """GET /api/analytics/budget?request_id=X — monthly or per-request budget vs actual."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        request_id = flask_request.args.get("request_id")
        result = get_budget_tracking(request_id=request_id)
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Failed to load budget tracking")
        return jsonify({"success": False, "error": "Failed to load budget data"}), 500


@analytics_bp.route("/carbon/estimate", methods=["GET"])
def carbon_estimate():
    """
    GET /api/analytics/carbon/estimate?origin=X&destination=Y&mode=flight&travelers=1
    Returns quick CO₂ estimate for a proposed trip.
    """
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    origin = flask_request.args.get("origin", "").strip()
    destination = flask_request.args.get("destination", "").strip()
    mode = flask_request.args.get("mode", "flight").strip().lower()
    try:
        num_travelers = max(1, int(flask_request.args.get("travelers", 1)))
    except (ValueError, TypeError):
        num_travelers = 1

    if not destination:
        return jsonify({"success": False, "error": "destination is required"}), 400

    try:
        dist_km = 0.0
        if origin and destination:
            dist_km = maps.get_distance_km(origin, destination) or 0.0
        if not dist_km:
            dist_km = 5000.0 if mode == "flight" else 700.0

        result = calculate_carbon(dist_km, mode, num_travelers)
        result["success"] = True
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Failed to estimate carbon footprint")
        return jsonify({"success": False, "error": "Failed to estimate carbon footprint"}), 500
