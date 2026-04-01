"""
TravelSync Pro v3.0 — Application Factory
Flask REST API + React SPA frontend
"""
import os
import logging
from datetime import datetime
from flask import Flask, send_from_directory, jsonify, request
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
    # instances (e.g. real-time notifications, OTIS events). Without Redis,
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

    with app.app_context():
        init_db(app)

    # Start the Supabase keep-alive thread here so it runs under every process
    # entry point (Gunicorn, run.py, tests). The old placement inside
    # `if __name__ == "__main__"` meant it never started under Gunicorn.
    _start_supabase_keepalive()

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
    from routes.otis import otis_bp

    for bp in (auth_bp, trips_bp, weather_bp, currency_bp, meetings_bp,
               expenses_bp, accommodation_bp, requests_bp, approvals_bp, analytics_bp,
               chat_bp, uploads_bp, health_bp, sos_bp, alerts_bp, notifications_bp,
               whatsapp_bp, cliq_bot_bp, expense_approvals_bp, users_bp, orgs_bp, agents_bp, docs_bp,
               audit_bp, webhooks_bp, exports_bp, admin_bp, otis_bp):
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

    # ── OTIS shared resources ────────────────────────────────────────────────
    # Shared thread pool for OTIS async tasks (transcription, command execution).
    # Replaces per-call ThreadPoolExecutor(max_workers=1) which created and
    # destroyed a thread pool on every voice command.
    import concurrent.futures as _cf
    _otis_executor = _cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="otis")

    # Audio buffers for sessions using the fallback (non-Gemini-Live) path.
    # Keyed by session_id. Cleaned up on session stop and by a TTL sweep.
    _audio_buffers: dict[str, bytes] = {}

    # ── OTIS Voice Assistant WebSocket Events (Gemini Live API) ──────────────
    #
    #  Audio pipeline (frontend unchanged):
    #    otis:audio_chunk → Gemini Live (real-time STT+LLM+TTS)
    #    otis:process_command → OtisAgentPool (text commands, no audio needed)
    #    otis:request_audio → Google Cloud TTS (on-demand TTS)
    #
    #  Live events emitted back to frontend (same names as before):
    #    otis:session_started, otis:audio_received, otis:transcript,
    #    otis:response, otis:audio_ready, otis:turn_complete, otis:barge_in,
    #    otis:error, otis:session_stopped

    def _build_otis_system_prompt(user: dict) -> str:
        """Build Gemini Live system instruction incorporating live user context."""
        from database import get_db
        now = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
        name  = user.get("full_name") or user.get("name", "there")
        role  = user.get("role", "employee")
        dept  = user.get("department") or ""
        org   = user.get("org_name") or ""

        context_lines = [f"Date/time: {now}"]
        try:
            db = get_db()
            # Pending expense approvals for managers/admins
            if role in ("admin", "manager", "super_admin"):
                row = db.execute(
                    "SELECT COUNT(*) as c FROM approvals WHERE approver_id = ? AND status='pending'",
                    (user["id"],)
                ).fetchone()
                if row:
                    context_lines.append(f"Pending travel approvals: {row['c']}")
            # User's own pending expenses
            row2 = db.execute(
                "SELECT COUNT(*) as c FROM expenses_db WHERE user_id=? AND COALESCE(approval_status,'draft') IN ('draft','submitted')",
                (user["id"],)
            ).fetchone()
            if row2 and row2["c"]:
                context_lines.append(f"User pending expenses: {row2['c']}")
            db.close()
        except Exception:
            pass

        ctx = "\n".join(context_lines)
        return f"""You are OTIS (Omniscient Travel Intelligence System), the voice AI assistant for TravelSync Pro.

You are speaking with {name}, {role}{f' in {dept}' if dept else ''}{f' at {org}' if org else ''}.

{ctx}

VOICE RESPONSE RULES — CRITICAL:
- Speak in clear, natural Indian English accent
- Be concise: 1-3 sentences maximum per response
- NO markdown, NO bullet points, NO tables in speech
- Use conversational numbers: "three trips" not "3 trips"
- Use Indian currency: "rupees fifty thousand" not "₹50,000"
- Always confirm actions: "I've approved John's Mumbai trip"
- If uncertain, ask ONE follow-up question
- End responses with what happens next or offer help

You have access to all TravelSync data for this user including trips, expenses, approvals, meetings, and analytics."""

    @socketio.on("otis:start_session")
    def handle_otis_start(data):
        """Start OTIS voice session and initialise Gemini Live API connection."""
        from auth import get_current_user
        from services.gemini_live_service import gemini_live
        user = get_current_user()
        if not user:
            emit("otis:error", {"error": "Authentication required"})
            return

        try:
            session_id = data.get("session_id")
            if not session_id:
                import uuid
                session_id = f"otis-{uuid.uuid4().hex[:12]}"

            user_room = f"user_{user['id']}"
            live_mode = False

            if gemini_live.live_available:
                system_prompt = _build_otis_system_prompt(user)
                voice = (data.get("voice") or "Puck").capitalize()

                def _on_live_event(event_type: str, ev_data: dict):
                    """Route Gemini Live events to the user's SocketIO room."""
                    try:
                        if event_type == "transcript":
                            socketio.emit("otis:transcript", {
                                "session_id": session_id,
                                "text": ev_data.get("text", ""),
                            }, room=user_room)

                        elif event_type in ("response", "text_token") and ev_data.get("text"):
                            socketio.emit("otis:response", {
                                "session_id": session_id,
                                "response":   ev_data.get("text", ""),
                                "streaming":  event_type == "text_token",
                            }, room=user_room)

                        elif event_type == "audio_chunk":
                            socketio.emit("otis:audio_ready", {
                                "session_id": session_id,
                                "audio_b64":  ev_data.get("audio_b64", ""),
                                "mime_type":  ev_data.get("mime_type", "audio/pcm;rate=24000"),
                                "streaming":  True,
                            }, room=user_room)

                        elif event_type == "turn_complete":
                            socketio.emit("otis:turn_complete", {"session_id": session_id}, room=user_room)

                        elif event_type == "barge_in":
                            socketio.emit("otis:barge_in", {"session_id": session_id}, room=user_room)

                        elif event_type == "error":
                            socketio.emit("otis:error", {
                                "session_id": session_id,
                                "error": ev_data.get("message", "Gemini Live error"),
                            }, room=user_room)
                    except Exception as cb_err:
                        logger.debug("[OTIS WS] Live event callback error: %s", cb_err)

                sess = gemini_live.create_session(
                    session_id=session_id,
                    system_prompt=system_prompt,
                    on_event=_on_live_event,
                    voice_name=voice,
                )
                if sess:
                    live_mode = True
                    logger.info("[OTIS WS] Gemini Live session created: %s", session_id)

            emit("otis:session_started", {
                "session_id": session_id,
                "status":     "ready",
                "mode":       "gemini_live" if live_mode else "text",
            })
        except Exception:
            logger.exception("[OTIS WS] Start session failed")
            emit("otis:error", {"error": "Failed to start session"})

    @socketio.on("otis:audio_chunk")
    def handle_otis_audio(data):
        """
        Stream audio chunk to Gemini Live API.
        Gemini handles STT + LLM + TTS in real time — no separate transcription step.
        Falls back to Gemini transcribe+command when Live not available.
        """
        import base64 as _b64
        from auth import get_current_user
        from services.gemini_live_service import gemini_live

        user = get_current_user()
        if not user:
            emit("otis:error", {"error": "Authentication required"})
            return

        try:
            session_id = data.get("session_id")
            audio_b64  = data.get("audio", "")
            is_final   = data.get("is_final", False)
            mime_type  = data.get("mime_type", "audio/pcm;rate=16000")

            if not audio_b64:
                return

            audio_bytes = _b64.b64decode(audio_b64)

            # ── Gemini Live path (real-time) ───────────────────────────────
            if gemini_live.session_alive(session_id):
                gemini_live.send_audio(session_id, audio_bytes)
                emit("otis:audio_received", {
                    "session_id": session_id,
                    "chunk_size": len(audio_bytes),
                    "is_final":   is_final,
                    "mode":       "gemini_live",
                })
                return

            # ── Fallback: accumulate then transcribe+process ───────────────
            buf = _audio_buffers.get(session_id, b"")
            _audio_buffers[session_id] = buf + audio_bytes

            emit("otis:audio_received", {
                "session_id": session_id,
                "chunk_size": len(audio_bytes),
                "is_final":   is_final,
                "mode":       "buffered",
            })

            if is_final:
                full_audio = _audio_buffers.pop(session_id, b"")
                if not full_audio:
                    return
                emit("otis:transcribing", {"session_id": session_id})

                def _transcribe_and_respond():
                    result = gemini_live.transcribe_audio(full_audio, mime_type)
                    return result.get("transcript", "")

                transcript = _otis_executor.submit(_transcribe_and_respond).result(timeout=15)

                if transcript:
                    emit("otis:transcript", {"session_id": session_id, "text": transcript})
                    # Trigger text command processing
                    socketio.emit("otis:process_command", {
                        "session_id": session_id,
                        "command":    transcript,
                    })

        except Exception:
            logger.exception("[OTIS WS] Audio chunk processing failed")
            emit("otis:error", {"error": "Audio processing failed"})

    @socketio.on("otis:process_command")
    def handle_otis_command(data):
        """
        Process a text command via OtisAgentPool (Gemini LLM + function calling).
        Used for text-mode and as fallback when Live API not available.
        """
        import asyncio
        from auth import get_current_user
        from services.gemini_live_service import gemini_live

        user = get_current_user()
        if not user:
            emit("otis:error", {"error": "Authentication required"})
            return

        try:
            session_id   = data.get("session_id")
            command_text = (data.get("command") or "").strip()

            if not command_text:
                emit("otis:error", {"error": "Command text required"})
                return

            # Security validation
            try:
                from otis_security import OtisCommandSecurity
                v = OtisCommandSecurity.validate(command_text)
                if not v["valid"]:
                    emit("otis:error", {"error": v["error"], "session_id": session_id})
                    return
                command_text = v["command"]
                if v.get("needs_confirmation"):
                    emit("otis:confirm_required", {
                        "session_id":  session_id,
                        "command":     command_text,
                        "risk_reason": v["risk_reason"],
                    })
                    return
                if session_id:
                    ok, quota_msg = OtisCommandSecurity.check_command_quota(user["id"], session_id)
                    if not ok:
                        emit("otis:error", {"error": quota_msg, "session_id": session_id})
                        return
            except ImportError:
                pass

            emit("otis:processing", {"session_id": session_id, "command": command_text})

            try:
                from agents.otis_agent import OtisAgentPool
                pool  = OtisAgentPool.instance()
                agent = pool.get_or_create(
                    user_id=user["id"],
                    org_id=user.get("org_id"),
                    session_id=session_id or f"ws-{user['id']}",
                )

                def _run():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(agent.process_command(command_text))
                    finally:
                        loop.close()

                response_text = _otis_executor.submit(_run).result(timeout=30)

                emit("otis:response", {
                    "session_id": session_id,
                    "command":    command_text,
                    "response":   response_text,
                    "timestamp":  datetime.now().isoformat(),
                })

                # Auto-generate TTS audio for the response (Google Cloud TTS)
                try:
                    audio_bytes = gemini_live.synthesize_speech(response_text)
                    if audio_bytes:
                        import base64 as _b64
                        emit("otis:audio_ready", {
                            "session_id": session_id,
                            "audio_b64":  _b64.b64encode(audio_bytes).decode(),
                            "mime_type":  "audio/mpeg",
                            "duration_ms": 0,
                        })
                except Exception:
                    pass  # TTS failure is non-fatal

            except ImportError:
                emit("otis:response", {
                    "session_id": session_id,
                    "response":   "OTIS is not fully configured.",
                    "error":      True,
                })
            except Exception:
                logger.exception("[OTIS WS] Agent command failed")
                emit("otis:response", {
                    "session_id": session_id,
                    "response":   "I encountered an error. Please try again.",
                    "error":      True,
                })

        except Exception:
            logger.exception("[OTIS WS] Command processing failed")
            emit("otis:error", {"error": "Failed to process command"})

    @socketio.on("otis:request_audio")
    def handle_otis_request_audio(data):
        """
        Generate TTS audio for a given text via Google Cloud TTS (Indian English).
        Returns base64-encoded MP3 in otis:audio_ready event.
        """
        import base64 as _b64
        from auth import get_current_user
        from services.gemini_live_service import gemini_live

        user = get_current_user()
        if not user:
            emit("otis:error", {"error": "Authentication required"})
            return

        try:
            session_id = data.get("session_id")
            text       = (data.get("text") or "").strip()[:2000]

            if not text:
                emit("otis:error", {"error": "Text required for audio generation"})
                return

            audio_bytes = gemini_live.synthesize_speech(text, language_code="en-IN")
            if audio_bytes:
                emit("otis:audio_ready", {
                    "session_id":  session_id,
                    "text":        text,
                    "audio_b64":   _b64.b64encode(audio_bytes).decode(),
                    "mime_type":   "audio/mpeg",
                    "duration_ms": 0,
                    "provider":    "google_cloud_tts",
                })
            else:
                emit("otis:audio_ready", {
                    "session_id":  session_id,
                    "text":        text,
                    "audio_b64":   None,
                    "mime_type":   None,
                    "duration_ms": 0,
                    "provider":    "unavailable",
                })
        except Exception:
            logger.exception("[OTIS WS] Audio generation failed")
            emit("otis:error", {"error": "Failed to generate audio"})

    @socketio.on("otis:stop_session")
    def handle_otis_stop(data):
        """Stop OTIS voice session — tears down Gemini Live connection and agent pool entry."""
        from auth import get_current_user
        from services.gemini_live_service import gemini_live

        user = get_current_user()
        if not user:
            emit("otis:error", {"error": "Authentication required"})
            return

        try:
            session_id = data.get("session_id")

            # Stop Gemini Live session
            if session_id:
                gemini_live.stop_session(session_id)

            # Clean up audio buffer (prevents memory leak on dropped sessions)
            _audio_buffers.pop(session_id, None)

            # Release agent pool entry
            try:
                from agents.otis_agent import OtisAgentPool
                OtisAgentPool.instance().release(session_id or f"ws-{user['id']}")
            except Exception:
                pass

            logger.info("[OTIS WS] Session %s stopped", session_id)
            emit("otis:session_stopped", {"session_id": session_id})
        except Exception:
            logger.exception("[OTIS WS] Stop session failed")
            emit("otis:error", {"error": "Failed to stop session"})

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
    socketio.run(app, host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
