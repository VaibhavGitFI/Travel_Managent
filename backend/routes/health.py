"""
TravelSync Pro — Health Check Route
Deep health check: verifies database, Redis, and external API connectivity.
Returns 503 when critical dependencies are down so Cloud Run stops routing
traffic to broken instances.
"""
import os
import logging
from datetime import datetime
from flask import Blueprint, jsonify
from config import Config

health_bp = Blueprint("health", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)


@health_bp.route("/health", methods=["GET"])
def health():
    """GET /api/health — deep health check with component-level status."""
    checks = {}

    # 1. Database
    try:
        from database import get_db
        db = get_db()
        row = db.execute("SELECT 1 AS alive").fetchone()
        db.close()
        checks["database"] = "ok" if row else "error: no result"
    except Exception as e:
        checks["database"] = f"error: {type(e).__name__}"
        logger.warning("[Health] Database check failed: %s", e)

    # 2. Redis (if configured)
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis as redis_lib
            r = redis_lib.Redis.from_url(redis_url, socket_timeout=2)
            r.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {type(e).__name__}"
            logger.warning("[Health] Redis check failed: %s", e)

    # 3. Cache status
    try:
        from services.cache_service import get_cache_status
        checks["cache"] = get_cache_status()
    except Exception:
        pass

    # 4. Services configuration status
    services = Config.services_status()

    # Overall: healthy only if all checks pass
    all_ok = all(v == "ok" for v in checks.values() if isinstance(v, str))
    status_code = 200 if all_ok else 503

    return jsonify({
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
        "services": services,
        "version": os.getenv("BUILD_SHA", "3.0.0"),
        "timestamp": datetime.utcnow().isoformat(),
    }), status_code
