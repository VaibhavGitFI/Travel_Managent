"""
TravelSync Pro — Weather Routes
Travel weather forecasts and current conditions via OpenWeatherMap.
"""
from flask import Blueprint, request, jsonify
from auth import get_current_user
from agents.weather_agent import get_travel_weather
from services.weather_service import weather as weather_service

weather_bp = Blueprint("weather", __name__, url_prefix="/api")


@weather_bp.route("/weather", methods=["POST"])
def forecast():
    """POST /api/weather — travel weather forecast for a city and date range."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    city = data.get("city", "").strip()
    travel_dates = data.get("travel_dates", "")

    if not city:
        return jsonify({"success": False, "error": "city is required"}), 400

    try:
        # Parse date range if provided
        start_date, end_date = "", ""
        if travel_dates:
            parts = travel_dates.split(" to ")
            start_date = parts[0].strip()
            end_date = parts[-1].strip()

        result = get_travel_weather(city, start_date, end_date)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@weather_bp.route("/weather/current", methods=["GET"])
def current_weather():
    """GET /api/weather/current?city=X — current weather widget data."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    city = request.args.get("city", "").strip()
    if not city:
        return jsonify({"success": False, "error": "city query parameter is required"}), 400

    try:
        result = weather_service.get_current(city)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
