"""
TravelSync Pro — Request Tracing & Structured Logging Middleware
Adds request_id, duration tracking, and JSON log formatting.
"""
import time
import uuid
import logging
import json as _json
from flask import request, g


class RequestTracer:
    """Flask middleware that assigns a unique request_id and tracks duration."""

    def __init__(self, app=None):
        if app:
            self.init_app(app)

    def init_app(self, app):
        app.before_request(self._before)
        app.after_request(self._after)

    @staticmethod
    def _before():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        g.request_start = time.time()

    @staticmethod
    def _after(response):
        duration_ms = round((time.time() - getattr(g, "request_start", time.time())) * 1000, 1)
        request_id = getattr(g, "request_id", "-")

        # Inject request_id into response headers for client-side correlation
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # Log the request (skip health checks and static files to reduce noise)
        if request.path.startswith("/api/") and request.path != "/api/health":
            logger = logging.getLogger("access")
            logger.info(
                "[%s] %s %s %d %.0fms",
                request_id, request.method, request.path,
                response.status_code, duration_ms,
            )

        return response


class StructuredFormatter(logging.Formatter):
    """JSON log formatter for production (Cloud Run / GCP Cloud Logging)."""

    def format(self, record):
        from flask import has_request_context
        log_entry = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": self.formatTime(record),
        }
        if has_request_context():
            log_entry["request_id"] = getattr(g, "request_id", None)
            log_entry["path"] = request.path
            log_entry["method"] = request.method
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return _json.dumps(log_entry)


def configure_logging(app):
    """Set up logging: JSON in production, readable in dev."""
    is_prod = not app.config.get("DEBUG", True)
    root = logging.getLogger()

    if is_prod:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        root.handlers = [handler]
        root.setLevel(logging.INFO)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    # Quiet down noisy libraries
    for lib in ("engineio", "socketio", "urllib3", "werkzeug"):
        logging.getLogger(lib).setLevel(logging.WARNING)
