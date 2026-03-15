"""
TravelSync Pro v3.0 — Application Factory
Flask REST API + React SPA frontend
"""
import os
import logging
from flask import Flask, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from config import Config
from database import init_db

socketio = SocketIO()
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

    socketio.init_app(app, cors_allowed_origins=allowed_origins, async_mode="eventlet",
                      logger=False, engineio_logger=False)

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

    for bp in (auth_bp, trips_bp, weather_bp, currency_bp, meetings_bp,
               expenses_bp, accommodation_bp, requests_bp, approvals_bp, analytics_bp,
               chat_bp, uploads_bp, health_bp):
        app.register_blueprint(bp)

    # ── SocketIO Events ────────────────────────────────────────────────────────
    @socketio.on("connect")
    def handle_connect():
        emit("connected", {"status": "connected", "version": "3.0.0"})

    @socketio.on("subscribe_updates")
    def handle_subscribe(data):
        emit("subscribed", {"message": "Subscribed to real-time updates"})

    # ── Serve React SPA (production) ───────────────────────────────────────────
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_react(path):
        # Don't intercept /api or /socket.io routes
        if path.startswith("api/") or path.startswith("socket.io"):
            return jsonify({"error": "Not found"}), 404
        # Serve static asset from React build if it exists
        build_file = os.path.join(Config.REACT_BUILD, path)
        if path and os.path.isfile(build_file):
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


# ── Entry Point ────────────────────────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log_startup_banner()
    socketio.run(app, host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
