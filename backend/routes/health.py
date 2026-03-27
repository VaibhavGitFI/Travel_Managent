"""
TravelSync Pro — Health Check Route
Returns service status for all configured APIs.
Includes a Supabase keep-alive ping to prevent free-tier database pausing.
"""
import logging
from datetime import datetime
from flask import Blueprint, jsonify
from config import Config

health_bp = Blueprint("health", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)


@health_bp.route("/health", methods=["GET"])
def health():
    """GET /api/health — service status for all configured APIs + Supabase ping."""
    try:
        status = Config.services_status()

        # Include cache status
        try:
            from services.cache_service import get_cache_status
            status["cache"] = get_cache_status()
        except Exception:
            pass

        # Supabase database ping — keeps the free-tier DB awake
        db_ok = False
        try:
            from database import get_db
            db = get_db()
            row = db.execute("SELECT 1 AS alive").fetchone()
            db_ok = bool(row)
            db.close()
        except Exception as e:
            logger.warning("[Health] Supabase ping failed: %s", e)
        status["database"] = db_ok

        status.update({
            "status": "ok" if db_ok else "degraded",
            "version": "3.0.0",
            "timestamp": datetime.utcnow().isoformat(),
        })
        return jsonify(status), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
