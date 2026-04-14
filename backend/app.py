"""
TravelSync Pro v3.0 — Application Factory
Flask REST API + React SPA frontend
"""
import os
import logging
from datetime import datetime
from flask import Flask, send_from_directory, jsonify, request, session
from utils.response import error_response
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

    # CORS origins configurable via CORS_ORIGINS env var (comma-separated).
    # Never allow "*" with credentials — that's a security vulnerability.
    allowed_origins = Config.CORS_ORIGINS
    if "*" in allowed_origins:
        logger.warning("[CORS] Wildcard '*' is not allowed with credentials — removing it")
        allowed_origins = [o for o in allowed_origins if o != "*"]
    CORS(app, supports_credentials=True, origins=allowed_origins)

    # async_mode must match the Gunicorn worker class (--worker-class eventlet in
    # the Dockerfile). Setting it explicitly avoids non-deterministic auto-detection
    # when multiple async libraries are installed.
    #
    # When REDIS_URL is set, SocketIO uses it as a message queue so events
    # emitted on one Cloud Run instance are broadcast to users connected to other
    # instances (e.g. real-time notifications). Without Redis,
    # cross-instance delivery silently fails (acceptable for single-instance dev).
    import os as _os
    _redis_url = _os.getenv("REDIS_URL", "").strip() or None
    socketio.init_app(
        app,
        cors_allowed_origins=allowed_origins,
        async_mode="eventlet",
        message_queue=_redis_url,
        logger=False,
        engineio_logger=False,
    )
    
    # Rate limiter
    limiter.init_app(app)

    # Gzip compression — applied automatically to all responses above 500 bytes
    # whose Content-Type is JSON, HTML, CSS, or JS. Reduces API payload sizes
    # by 70-85% with no code changes to routes. Skips WebSocket frames (SocketIO
    # handles its own framing outside Flask's response pipeline).
    from flask_compress import Compress
    Compress(app)

    # Request tracing + structured logging
    RequestTracer(app)
    configure_logging(app)

    # ── Session cookie security ───────────────────────────────────────────────
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = not Config.DEBUG  # Secure in prod
    app.config["SESSION_COOKIE_NAME"] = "ts_session"

    # ── Global auth enforcement (before_request) ───────────────────────────
    # Every /api/ route is protected by default. Public routes are listed in
    # _AUTH_EXEMPT_PREFIXES. This is a single enforcement point — a developer
    # adding a new route cannot accidentally forget authentication.
    _AUTH_EXEMPT_PREFIXES = (
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/verify-email",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/api/auth/refresh",
        "/api/health",
        "/api/cliq/bot",
        "/api/whatsapp/webhook",
        "/api/docs",
        "/api/accommodation/photo",   # open photo proxy — <img> tags can't send session cookies
    )

    @app.before_request
    def require_auth():
        """Enforce authentication on all /api/ routes except explicitly public ones."""
        if not request.path.startswith("/api/"):
            return None
        if request.method == "OPTIONS":
            return None  # CORS preflight
        if any(request.path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
            return None
        from auth import get_current_user
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        return None

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
        """Ensure CSRF cookie and response header stay in sync with session on every response."""
        from flask import session as flask_session
        csrf_token = flask_session.get("_csrf_token")
        if csrf_token and "user_id" in flask_session:
            response.set_cookie(
                "csrf_token", csrf_token,
                httponly=False, samesite="Lax",
                secure=not Config.DEBUG, max_age=86400,
            )
            # Also expose token as a response header so the frontend can cache it
            # in memory without relying on cookie availability
            response.headers["X-CSRF-Token"] = csrf_token
        return response

    # ── DB init in background thread ──────────────────────────────────────────
    # init_db() runs 80+ SQL statements (CREATE TABLE IF NOT EXISTS, ALTER TABLE,
    # CREATE INDEX) against Supabase. Running this synchronously — even deferred
    # to the first request — blocks that request for 5-60s while schema checks
    # complete over the cross-cloud link, causing client-visible timeouts.
    #
    # Fix: run init_db() in a daemon background thread immediately at startup.
    # The psycopg2 connection pool is created lazily (first get_db() call), so
    # the DB is usable as soon as that first connection succeeds (~1-2s).
    # init_db() schema migrations run concurrently without blocking HTTP traffic.
    #
    # In development (SQLite) init_db() is instant so the thread is a no-op cost.
    import threading as _threading

    def _bg_init_db():
        try:
            init_db()
            logger.info("[DB] Background init complete — schema ready")
        except Exception as exc:
            logger.error("[DB] Background init failed: %s", exc)

    _init_thread = _threading.Thread(target=_bg_init_db, daemon=True, name="db-init")
    _init_thread.start()

    # Background threads: keep-alive + analytics warmup.
    _start_supabase_keepalive()

    from services.analytics_warmup import start_analytics_warmup
    start_analytics_warmup()

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
        return error_response(str(e.description) if hasattr(e, "description") else "Bad request", 400)

    @app.errorhandler(401)
    def unauthorized(e):
        return error_response("Authentication required", 401)

    @app.errorhandler(403)
    def forbidden(e):
        return error_response("Access denied", 403)

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return error_response("Endpoint not found", 404)
        # Let SPA handle non-API 404s
        index_html = os.path.join(Config.REACT_BUILD, "index.html")
        if os.path.isfile(index_html):
            return send_from_directory(Config.REACT_BUILD, "index.html")
        return error_response("Not found", 404)

    @app.errorhandler(405)
    def method_not_allowed(e):
        return error_response("Method not allowed", 405)

    @app.errorhandler(413)
    def payload_too_large(e):
        return error_response("File too large. Maximum upload size is 20MB.", 413)

    @app.errorhandler(429)
    def rate_limited(e):
        return error_response("Too many requests. Please slow down.", 429)

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception("Internal server error: %s", e)
        return error_response("Internal server error", 500)

    # ── SocketIO Events ────────────────────────────────────────────────────────
    @socketio.on("connect")
    def handle_connect(auth=None):
        from auth import get_current_user, verify_token, get_user_org

        token = None
        if isinstance(auth, dict):
            token = (auth.get("token") or "").strip()

        if token:
            user_id = verify_token(token, "access")
            if user_id:
                session["user_id"] = user_id
                membership = get_user_org(user_id)
                if membership:
                    session["org_id"] = membership.get("org_id")
                    session["org_role"] = membership.get("org_role")

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
    _SPA_DIR = os.path.abspath(Config.REACT_BUILD)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_react(path):
        # Don't intercept /api or /socket.io routes
        if path.startswith("api/") or path.startswith("socket.io"):
            return jsonify({"success": False, "error": "Not found"}), 404

        # Serve static asset from React build if it exists.
        # Path traversal protection: resolve absolute path THEN verify it
        # is still inside _SPA_DIR. Also reject null bytes.
        if path:
            if "\x00" in path:
                return jsonify({"success": False, "error": "Not found"}), 404
            safe_path = os.path.abspath(os.path.join(_SPA_DIR, path))
            if not (safe_path.startswith(_SPA_DIR + os.sep) or safe_path == _SPA_DIR):
                return jsonify({"success": False, "error": "Not found"}), 404
            if os.path.isfile(safe_path):
                return send_from_directory(_SPA_DIR, path)

        # SPA fallback — always serve index.html for client-side routing
        index_html = os.path.join(_SPA_DIR, "index.html")
        if os.path.isfile(index_html):
            return send_from_directory(_SPA_DIR, "index.html")
        # Dev mode — React runs on port 5173
        return jsonify({
            "message": "TravelSync Pro API v3.0",
            "react_dev_server": "http://localhost:5173",
            "api_docs": "/api/health",
        }), 200

    # Fail fast if critical production config is missing
    Config.validate()

    return app


def log_startup_banner() -> None:
    status = Config.services_status()
    lines = [
        "",
        "=" * 62,
        "  TravelSync Pro v3.0 — AI-Powered Corporate Travel",
        "=" * 62,
    ]
    for svc, live in status.items():
        icon = "[LIVE]    " if live else "[FALLBACK]"
        lines.append(f"  {svc:<28} {icon}")
    lines.extend([
        "-" * 62,
        f"  API     : http://localhost:{Config.PORT}/api",
        "  React   : http://localhost:5173  (cd frontend && npm run dev)",
        f"  Debug   : {Config.DEBUG}",
        "=" * 62,
    ])
    # Print directly to bypass JSON formatter for clean startup banner
    print("\n".join(lines))


# ── Supabase Keep-Alive ───────────────────────────────────────────────────────
def _start_supabase_keepalive():
    """Background thread that pings Supabase every 4 minutes to prevent free-tier
    pausing. Also purges expired rows from token_blacklist and auth_codes tables so
    they do not grow unboundedly."""
    import threading
    import time as _time
    from datetime import datetime as _dt

    if not Config.DATABASE_URL:
        return  # SQLite in dev — no keep-alive needed

    def _ping_loop():
        while True:
            _time.sleep(240)  # 4 minutes
            try:
                from database import get_db
                db = get_db()
                # Keep connection alive
                db.execute("SELECT 1")
                # Purge expired auth tokens — prevents table bloat
                now_iso = _dt.utcnow().isoformat()
                db.execute(
                    "DELETE FROM token_blacklist WHERE expires_at < ?", (now_iso,)
                )
                db.execute(
                    "DELETE FROM auth_codes WHERE expires_at < ?", (now_iso,)
                )
                db.commit()
                db.close()
            except Exception as e:
                logger.warning("[KeepAlive] Supabase ping/cleanup failed: %s", e)

    t = threading.Thread(target=_ping_loop, daemon=True, name="supabase-keepalive")
    t.start()
    logger.info("[KeepAlive] Supabase keep-alive thread started (ping + cleanup every 4 min)")


# ── Module-level app for Gunicorn ─────────────────────────────────────────────
# Gunicorn imports this module and looks up the `app` variable directly:
#   gunicorn --worker-class eventlet -w 1 app:app
# `create_app()` is called exactly ONCE here. run.py imports this `app` variable
# directly rather than calling create_app() again, which previously caused double
# blueprint registration, double init_db(), and duplicate SocketIO event handlers.
app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log_startup_banner()
    socketio.run(app, host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG, use_reloader=False)
