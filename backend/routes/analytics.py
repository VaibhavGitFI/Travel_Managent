"""
TravelSync Pro — Analytics Routes
Dashboard stats, spend analysis, and policy compliance scorecard from real DB data.
"""
from flask import Blueprint, jsonify
from auth import get_current_user
from agents.analytics_agent import (
    get_dashboard_stats,
    get_spend_analysis,
    get_policy_compliance_scorecard,
)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


@analytics_bp.route("/dashboard", methods=["GET"])
def dashboard():
    """GET /api/analytics/dashboard — real-time dashboard statistics."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        result = get_dashboard_stats(user_id=user["id"])
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analytics_bp.route("/spend", methods=["GET"])
def spend():
    """GET /api/analytics/spend — monthly trend and category breakdown of expenses."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        result = get_spend_analysis()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analytics_bp.route("/compliance", methods=["GET"])
def compliance():
    """GET /api/analytics/compliance — policy compliance scorecard."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        result = get_policy_compliance_scorecard()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
