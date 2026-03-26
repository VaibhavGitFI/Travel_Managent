"""
TravelSync Pro — Currency Routes
Currency conversion and destination travel-info via Open Exchange Rates.
"""
import logging
from flask import Blueprint, request, jsonify
from auth import get_current_user
from services.currency_service import currency as currency_service
from extensions import limiter

logger = logging.getLogger(__name__)

currency_bp = Blueprint("currency", __name__, url_prefix="/api/currency")


@currency_bp.route("/convert", methods=["POST"])
@limiter.limit("30 per minute")
def convert():
    """POST /api/currency/convert — convert between any two currencies."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    amount = data.get("amount")
    from_currency = (data.get("from_currency") or data.get("from") or "").strip()
    to_currency = (data.get("to_currency") or data.get("to") or "").strip()

    if amount is None or not from_currency or not to_currency:
        return jsonify({
            "success": False,
            "error": "amount, from_currency, and to_currency are required",
        }), 400

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "amount must be a number"}), 400

    try:
        result = currency_service.convert(amount, from_currency, to_currency)
        if "error" in result:
            return jsonify({"success": False, **result}), 400
        return jsonify({"success": True, **result}), 200
    except Exception as e:
        logger.exception("Failed to convert currency")
        return jsonify({"success": False, "error": "Failed to convert currency"}), 500


@currency_bp.route("/travel-info", methods=["GET"])
def travel_info():
    """GET /api/currency/travel-info?destination=X — destination currency info."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    destination = request.args.get("destination", "").strip()
    if not destination:
        return jsonify({"success": False, "error": "destination query parameter is required"}), 400

    try:
        result = currency_service.get_travel_currencies(destination)
        return jsonify({"success": True, **result}), 200
    except Exception as e:
        logger.exception("Failed to get travel currency info")
        return jsonify({"success": False, "error": "Failed to get travel currency info"}), 500
