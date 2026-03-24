"""
TravelSync Pro — Health Check Route
Returns service status for all configured APIs.
"""
from datetime import datetime
from flask import Blueprint, jsonify
from config import Config

health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.route("/health", methods=["GET"])
def health():
    """GET /api/health — service status for all configured APIs."""
    try:
        status = Config.services_status()

        # Include cache status
        try:
            from services.cache_service import get_cache_status
            status["cache"] = get_cache_status()
        except Exception:
            pass

        status.update({
            "status": "ok",
            "version": "3.0.0",
            "timestamp": datetime.utcnow().isoformat(),
        })
        return jsonify(status), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
