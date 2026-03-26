"""
TravelSync Pro v3.0 — Application Factory
Flask REST API + React SPA frontend
"""
import os
import logging
from flask import Flask, send_from_directory, jsonify, request
from flask_socketio import emit, join_room
from flask_cors import CORS

from config import Config
from database import init_db
from extensions import socketio, limiter
from auth import validate_csrf
from middleware import RequestTracer, configure_logging

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__, static_folder=Config.REACT_BUILD, static_url_path="")
    app.secret_key = Config.SECRET_KEY
    app.config["UPLOAD_FOLDER"] = Config.UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH

    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

    # Allow React dev server (port 5173) and same-origin production
    allowed_origins = [
        "http://localhost:5173",
        "http://localhost:3399",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3399",
    ]
    CORS(app, supports_credentials=True, origins=allowed_origins)

    # socketio.init_app(app, cors_allowed_origins=allowed_origins, async_mode="eventlet",
    #                   logger=False, engineio_logger=False)


    socketio.init_app(
        app,
        cors_allowed_origins=allowed_origins,
        logger=False,
        engineio_logger=False,
    )
    
    # Rate limiter
    limiter.init_app(app)

    # Request tracing + structured logging
    RequestTracer(app)
    configure_logging(app)

    # ── Session cookie security ───────────────────────────────────────────────
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = not Config.DEBUG  # Secure in prod
    app.config["SESSION_COOKIE_NAME"] = "ts_session"

    # ── CSRF protection (global before_request) ──────────────────────────────
    @app.before_request
    def csrf_protect():
        """Validate CSRF token on state-changing requests using session auth."""
        # Skip safe methods
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        # Skip JWT-authenticated requests (no CSRF risk for bearer tokens)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return None
        # Skip endpoints that don't need CSRF
        csrf_exempt_prefixes = (
            "/api/auth/", "/api/health", "/api/cliq/bot", "/api/whatsapp/webhook",
        )
        if any(request.path.startswith(p) for p in csrf_exempt_prefixes):
            return None
        # Skip if no session (user not logged in via cookie)
        from flask import session as flask_session
        if "user_id" not in flask_session:
            return None
        # If session has no CSRF token (e.g. server restart), regenerate it
        # instead of blocking the user — they're already authenticated
        session_token = flask_session.get("_csrf_token", "")
        if not session_token:
            from auth import generate_csrf_token
            new_token = generate_csrf_token()
            logger.debug("[CSRF] Regenerated token for user %s after session restore", flask_session.get("user_id"))
            # Allow this request through — the response will set the new cookie
            # via after_request below, and subsequent requests will use it
            return None
        # Validate CSRF token
        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not csrf_token or csrf_token != session_token:
            return jsonify({"success": False, "error": "CSRF token missing or invalid"}), 403

    @app.after_request
    def set_csrf_cookie(response):
        """Ensure CSRF cookie stays in sync with session on every response."""
        from flask import session as flask_session
        csrf_token = flask_session.get("_csrf_token")
        if csrf_token and "user_id" in flask_session:
            response.set_cookie(
                "csrf_token", csrf_token,
                httponly=False, samesite="Lax",
                secure=not Config.DEBUG, max_age=86400,
            )
        return response

    with app.app_context():
        init_db(app)

    # ── Register Blueprints ────────────────────────────────────────────────────
    from routes.auth      import auth_bp
    from routes.trips     import trips_bp
    from routes.weather   import weather_bp
    from routes.currency  import currency_bp
    from routes.meetings  import meetings_bp
    from routes.expenses  import expenses_bp
    from routes.accommodation import accommodation_bp
    from routes.requests  import requests_bp
    from routes.approvals import approvals_bp
    from routes.analytics import analytics_bp
    from routes.chat      import chat_bp
    from routes.uploads   import uploads_bp
    from routes.health    import health_bp
    from routes.sos       import sos_bp
    from routes.alerts    import alerts_bp
    from routes.notifications import notifications_bp
    from routes.whatsapp import whatsapp_bp
    from routes.cliq_bot import cliq_bot_bp
    from routes.expense_approvals import expense_approvals_bp
    from routes.users import users_bp
    from routes.organizations import orgs_bp
    from routes.agents import agents_bp
    from routes.docs import docs_bp
    from routes.audit import audit_bp
    from routes.webhooks import webhooks_bp
    from routes.exports import exports_bp
    from routes.admin import admin_bp

    for bp in (auth_bp, trips_bp, weather_bp, currency_bp, meetings_bp,
               expenses_bp, accommodation_bp, requests_bp, approvals_bp, analytics_bp,
               chat_bp, uploads_bp, health_bp, sos_bp, alerts_bp, notifications_bp,
               whatsapp_bp, cliq_bot_bp, expense_approvals_bp, users_bp, orgs_bp, agents_bp, docs_bp,
               audit_bp, webhooks_bp, exports_bp, admin_bp):
        app.register_blueprint(bp)

    # ── Standardized Error Handlers ───────────────────────────────────────────
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"success": False, "error": str(e.description) if hasattr(e, 'description') else "Bad request"}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({"success": False, "error": "Authentication required"}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"success": False, "error": "Access denied"}), 403

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Endpoint not found"}), 404
        # Let SPA handle non-API 404s
        index_html = os.path.join(Config.REACT_BUILD, "index.html")
        if os.path.isfile(index_html):
            return send_from_directory(Config.REACT_BUILD, "index.html")
        return jsonify({"success": False, "error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"success": False, "error": "Method not allowed"}), 405

    @app.errorhandler(413)
    def payload_too_large(e):
        return jsonify({"success": False, "error": "File too large. Maximum upload size is 20MB."}), 413

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"success": False, "error": "Too many requests. Please slow down."}), 429

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception("Internal server error: %s", e)
        return jsonify({"success": False, "error": "Internal server error"}), 500

    # ── SocketIO Events ────────────────────────────────────────────────────────
    @socketio.on("connect")
    def handle_connect():
        from auth import get_current_user
        user = get_current_user()
        if user:
            room = f"user_{user['id']}"
            join_room(room)
            emit("connected", {"status": "connected", "version": "3.0.0", "room": room})
        else:
            emit("connected", {"status": "connected", "version": "3.0.0"})

    @socketio.on("join_user_room")
    def handle_join_room(data):
        """Explicit room join — client sends user_id after auth."""
        from auth import get_current_user
        user = get_current_user()
        if user:
            room = f"user_{user['id']}"
            join_room(room)
            emit("room_joined", {"room": room})

    # ── Serve React SPA (production) ───────────────────────────────────────────
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_react(path):
        # Don't intercept /api or /socket.io routes
        if path.startswith("api/") or path.startswith("socket.io"):
            return jsonify({"success": False, "error": "Not found"}), 404
        # Serve static asset from React build if it exists
        if path:
            build_file = os.path.normpath(os.path.join(Config.REACT_BUILD, path))
            if not build_file.startswith(os.path.normpath(Config.REACT_BUILD)):
                return jsonify({"success": False, "error": "Forbidden"}), 403
            if os.path.isfile(build_file):
                return send_from_directory(Config.REACT_BUILD, path)
        # SPA fallback — always serve index.html for client-side routing
        index_html = os.path.join(Config.REACT_BUILD, "index.html")
        if os.path.isfile(index_html):
            return send_from_directory(Config.REACT_BUILD, "index.html")
        # Dev mode — React runs on port 5173
        return jsonify({
            "message": "TravelSync Pro API v3.0",
            "react_dev_server": "http://localhost:5173",
            "api_docs": "/api/health",
        }), 200

    return app


def log_startup_banner() -> None:
    status = Config.services_status()
    lines = [
        "",
        "═" * 62,
        "  TravelSync Pro v3.0 — AI-Powered Corporate Travel",
        "═" * 62,
    ]
    for svc, live in status.items():
        icon = "✅ Live    " if live else "⚠️  Fallback"
        lines.append(f"  {svc:<28} {icon}")
    lines.extend([
        "─" * 62,
        f"  API     : http://localhost:{Config.PORT}/api",
        "  React   : http://localhost:5173  (cd frontend && npm run dev)",
        f"  Debug   : {Config.DEBUG}",
        "═" * 62,
    ])
    logger.info("\n".join(lines))


# ── Supabase Keep-Alive ───────────────────────────────────────────────────────
def _start_supabase_keepalive():
    """Background thread that pings Supabase every 4 minutes to prevent free-tier pausing."""
    import threading
    import time as _time

    if not Config.DATABASE_URL:
        return  # No Supabase configured

    def _ping_loop():
        while True:
            _time.sleep(240)  # 4 minutes
            try:
                from database import get_db
                db = get_db()
                db.execute("SELECT 1")
                db.close()
            except Exception as e:
                logger.warning("[KeepAlive] Supabase ping failed: %s", e)

    t = threading.Thread(target=_ping_loop, daemon=True, name="supabase-keepalive")
    t.start()
    logger.info("[KeepAlive] Supabase keep-alive thread started (ping every 4 min)")


# ── Entry Point ────────────────────────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log_startup_banner()
    _start_supabase_keepalive()
    socketio.run(app, host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
