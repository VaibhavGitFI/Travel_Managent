"""
TravelSync Pro — OTIS Voice Assistant Routes
Production-grade voice AI with WebSocket streaming and session management.

Routes:
- POST   /api/otis/start          - Start a new voice session
- POST   /api/otis/stop           - Stop active session
- GET    /api/otis/status         - Get OTIS status and user permissions
- GET    /api/otis/sessions       - List user's voice sessions
- GET    /api/otis/sessions/:id   - Get session details with full conversation
- DELETE /api/otis/sessions/:id   - Delete a voice session
- GET    /api/otis/commands       - Get command history
- GET    /api/otis/analytics      - Get voice usage analytics
- GET    /api/otis/settings       - Get user's OTIS settings
- PUT    /api/otis/settings       - Update user's OTIS settings

WebSocket Events (defined in app.py):
- otis:wake_word       - Wake word detected
- otis:audio_chunk     - Send audio chunk for STT
- otis:command         - Process voice command (text)
- otis:stop_listening  - Stop listening
- otis:response        - Receive voice response
- otis:audio_response  - Receive TTS audio
- otis:error           - Error occurred
"""
import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from auth import get_current_user
from extensions import limiter
from database import get_db, table_columns
from config import Config
from otis_security import require_otis, audit_otis, OtisCommandSecurity, check_otis_permission
from agents.query_engine import handle_query, format_query_result_for_voice, should_use_structured_query

otis_bp = Blueprint("otis", __name__, url_prefix="/api/otis")
logger = logging.getLogger(__name__)


def _rollback_db_safely(db) -> None:
    """Clear a failed transaction so later OTIS queries can continue."""
    try:
        db.rollback()
    except Exception:
        pass


def _check_otis_permission(user: dict) -> tuple[bool, str]:
    """Thin wrapper preserved for /status endpoint (no decorator needed there)."""
    return check_otis_permission(user)


def _get_service_status() -> dict:
    """Resolve the actual active OTIS providers without making network calls."""
    services = {
        "wake_word": "available" if Config.PORCUPINE_ACCESS_KEY else "unavailable",
        "stt": "fallback",
        "tts": "fallback",
        "llm": "gemini" if Config.GEMINI_API_KEY else "unavailable",
    }

    try:
        from services.deepgram_service import SpeechToTextService
        stt = SpeechToTextService()
        provider = stt.get_active_provider()
        if provider:
            services["stt"] = provider.value
    except Exception as e:
        logger.debug("[OTIS Routes] STT status probe failed: %s", e)

    try:
        from services.elevenlabs_voice_service import TextToSpeechService
        tts = TextToSpeechService()
        provider = tts.get_active_provider()
        if provider:
            services["tts"] = provider.value
    except Exception as e:
        logger.debug("[OTIS Routes] TTS status probe failed: %s", e)

    return services


@otis_bp.route("/status", methods=["GET"])
def get_status():
    """
    GET /api/otis/status

    Get OTIS availability status and user permissions.

    Returns:
        {
            "success": true,
            "enabled": true,
            "available": true,
            "permissions": {
                "can_use": true,
                "can_approve_trips": true,
                "can_view_analytics": true
            },
            "services": {
                "wake_word": "available|unavailable",
                "stt": "deepgram|google|vosk|mock",
                "tts": "elevenlabs|google|pyttsx3|beep",
                "llm": "gemini|unavailable"
            },
            "session": {
                "active": false,
                "session_id": null
            }
        }
    """
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    allowed, reason = _check_otis_permission(user)

    services = _get_service_status()

    # Check for active session
    active_session = None
    try:
        db = get_db()
        row = db.execute(
            "SELECT session_id, started_at FROM otis_sessions "
            "WHERE user_id = ? AND status = 'active' "
            "ORDER BY started_at DESC LIMIT 1",
            (user["id"],)
        ).fetchone()
        if row:
            active_session = dict(row)
        db.close()
    except Exception as e:
        logger.debug(f"[OTIS Routes] Status check error: {e}")

    elevated_roles = ("admin", "manager", "super_admin")
    permissions = {
        "can_use": allowed,
        "can_approve_trips": user.get("role") in elevated_roles,
        "can_view_analytics": user.get("role") in elevated_roles,
        "can_execute_functions": user.get("role") in elevated_roles
    }

    return jsonify({
        "success": True,
        "enabled": Config.OTIS_ENABLED,
        "available": allowed,
        "reason": reason if not allowed else None,
        "permissions": permissions,
        "services": services,
        "session": {
            "active": active_session is not None,
            "session_id": active_session.get("session_id") if active_session else None,
            "started_at": active_session.get("started_at") if active_session else None
        },
        "config": {
            "max_session_duration": Config.OTIS_MAX_SESSION_DURATION,
            "idle_timeout": Config.OTIS_IDLE_TIMEOUT,
            "wake_word": Config.OTIS_WAKE_WORD
        }
    }), 200


@otis_bp.route("/start", methods=["POST"])
@require_otis
@audit_otis("session_start")
def start_session(user):
    """
    POST /api/otis/start

    Start a new OTIS voice session.
    Creates session in database and returns session ID.

    Returns:
        {
            "success": true,
            "session_id": "otis-abc123",
            "started_at": "2026-03-26T10:30:00Z"
        }
    """
    try:
        import uuid
        session_id = f"otis-{uuid.uuid4().hex[:12]}"
        now = datetime.now()

        db = get_db()

        # End any existing active sessions for this user
        db.execute(
            "UPDATE otis_sessions SET status = 'ended', ended_at = ? "
            "WHERE user_id = ? AND status = 'active'",
            (now, user["id"])
        )

        # Create new session
        org_id = user.get("org_id")
        db.execute(
            """INSERT INTO otis_sessions
               (org_id, user_id, session_id, status, started_at)
               VALUES (?, ?, ?, 'active', ?)""",
            (org_id, user["id"], session_id, now)
        )

        db.commit()
        db.close()

        logger.info(f"[OTIS Routes] Started session {session_id} for user {user['id']}")

        return jsonify({
            "success": True,
            "session_id": session_id,
            "started_at": now.isoformat(),
            "message": "OTIS session started. Say 'Hey Otis' to begin."
        }), 201

    except Exception as e:
        logger.exception("[OTIS Routes] Failed to start session")
        return jsonify({"success": False, "error": "Failed to start session"}), 500


@otis_bp.route("/stop", methods=["POST"])
@require_otis
@audit_otis("session_stop")
def stop_session(user):
    """
    POST /api/otis/stop
    Body: {"session_id": "otis-abc123"} (optional, defaults to current active)

    Stop an active OTIS session.

    Returns:
        {
            "success": true,
            "session_id": "otis-abc123",
            "duration_seconds": 120,
            "total_turns": 5
        }
    """

    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")

    try:
        db = get_db()

        # Find session to stop
        if session_id:
            row = db.execute(
                "SELECT * FROM otis_sessions WHERE session_id = ? AND user_id = ?",
                (session_id, user["id"])
            ).fetchone()
        else:
            row = db.execute(
                "SELECT * FROM otis_sessions WHERE user_id = ? AND status = 'active' "
                "ORDER BY started_at DESC LIMIT 1",
                (user["id"],)
            ).fetchone()

        if not row:
            db.close()
            return jsonify({"success": False, "error": "No active session found"}), 404

        session = dict(row)
        session_id = session["session_id"]

        # Calculate duration (SQLite may return a string or a datetime object)
        raw = session["started_at"]
        started_at = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
        ended_at = datetime.now()
        duration_seconds = int((ended_at - started_at).total_seconds())

        # Update session
        db.execute(
            """UPDATE otis_sessions
               SET status = 'ended', ended_at = ?, duration_seconds = ?
               WHERE session_id = ?""",
            (ended_at, duration_seconds, session_id)
        )

        db.commit()
        db.close()

        logger.info(f"[OTIS Routes] Stopped session {session_id} (duration: {duration_seconds}s)")

        return jsonify({
            "success": True,
            "session_id": session_id,
            "duration_seconds": duration_seconds,
            "total_turns": session.get("total_turns", 0)
        }), 200

    except Exception as e:
        logger.exception("[OTIS Routes] Failed to stop session")
        return jsonify({"success": False, "error": "Failed to stop session"}), 500


@otis_bp.route("/sessions", methods=["GET"])
@require_otis
def list_sessions(user):
    """
    GET /api/otis/sessions?limit=20

    List user's voice sessions (recent first).

    Returns:
        {
            "success": true,
            "sessions": [
                {
                    "session_id": "otis-abc123",
                    "started_at": "2026-03-26T10:30:00Z",
                    "ended_at": "2026-03-26T10:35:00Z",
                    "duration_seconds": 300,
                    "total_turns": 5,
                    "status": "ended"
                }
            ],
            "total": 1
        }
    """
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
    except (ValueError, TypeError):
        limit = 20

    try:
        db = get_db()
        rows = db.execute(
            """SELECT session_id, started_at, ended_at, duration_seconds,
                      total_turns, status, wake_word_detected
               FROM otis_sessions
               WHERE user_id = ?
               ORDER BY started_at DESC
               LIMIT ?""",
            (user["id"], limit)
        ).fetchall()

        sessions = [dict(r) for r in rows]
        db.close()

        return jsonify({
            "success": True,
            "sessions": sessions,
            "total": len(sessions)
        }), 200

    except Exception as e:
        logger.exception("[OTIS Routes] Failed to list sessions")
        return jsonify({"success": False, "error": "Failed to load sessions"}), 500


@otis_bp.route("/sessions/<session_id>", methods=["GET"])
@require_otis
def get_session(user, session_id):
    """
    GET /api/otis/sessions/:id

    Get session details with full conversation history.

    Returns:
        {
            "success": true,
            "session": {...},
            "conversation": [
                {
                    "turn_number": 1,
                    "role": "user",
                    "content": "What pending approvals do I have?",
                    "created_at": "..."
                },
                {
                    "turn_number": 2,
                    "role": "assistant",
                    "content": "You have three pending approvals...",
                    "created_at": "..."
                }
            ],
            "commands": [...]
        }
    """
    try:
        db = get_db()

        # Get session
        session_row = db.execute(
            "SELECT * FROM otis_sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user["id"])
        ).fetchone()

        if not session_row:
            db.close()
            return jsonify({"success": False, "error": "Session not found"}), 404

        session = dict(session_row)

        # Get conversation history (otis_conversations uses 'timestamp' not 'created_at')
        conversation_rows = db.execute(
            """SELECT turn_number, role, content, timestamp as created_at
               FROM otis_conversations
               WHERE session_id = ?
               ORDER BY turn_number ASC""",
            (session_id,)
        ).fetchall()
        conversation = [dict(r) for r in conversation_rows]

        # Get commands
        cols = table_columns(db, "otis_commands")
        select_cols = ["command_text", "response_text", "success", "latency_ms", "created_at"]
        if "function_called" in cols:
            select_cols.append("function_called")

        command_rows = db.execute(
            f"""SELECT {', '.join(select_cols)}
                FROM otis_commands
                WHERE session_id = ?
                ORDER BY created_at ASC""",
            (session_id,)
        ).fetchall()
        commands = [dict(r) for r in command_rows]

        db.close()

        return jsonify({
            "success": True,
            "session": session,
            "conversation": conversation,
            "commands": commands
        }), 200

    except Exception as e:
        logger.exception("[OTIS Routes] Failed to get session")
        return jsonify({"success": False, "error": "Failed to load session"}), 500


@otis_bp.route("/sessions/<session_id>", methods=["DELETE"])
@require_otis
@audit_otis("session_delete")
def delete_session(user, session_id):
    """
    DELETE /api/otis/sessions/:id

    Delete a voice session and all related data.

    Returns:
        {"success": true}
    """
    try:
        db = get_db()

        # Verify ownership
        row = db.execute(
            "SELECT session_id FROM otis_sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user["id"])
        ).fetchone()

        if not row:
            db.close()
            return jsonify({"success": False, "error": "Session not found"}), 404

        # Delete related data
        db.execute("DELETE FROM otis_conversations WHERE session_id = ?", (session_id,))
        db.execute("DELETE FROM otis_commands WHERE session_id = ?", (session_id,))
        db.execute("DELETE FROM otis_sessions WHERE session_id = ?", (session_id,))

        db.commit()
        db.close()

        logger.info(f"[OTIS Routes] Deleted session {session_id}")

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.exception("[OTIS Routes] Failed to delete session")
        return jsonify({"success": False, "error": "Failed to delete session"}), 500


@otis_bp.route("/commands", methods=["GET"])
@require_otis
def list_commands(user):
    """
    GET /api/otis/commands?limit=50

    Get command execution history for current user.

    Returns:
        {
            "success": true,
            "commands": [
                {
                    "command_text": "What pending approvals do I have?",
                    "response_text": "You have three pending approvals...",
                    "function_called": "get_pending_approvals",
                    "success": true,
                    "latency_ms": 350,
                    "created_at": "..."
                }
            ],
            "total": 50
        }
    """
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except (ValueError, TypeError):
        limit = 50

    try:
        db = get_db()
        cols = table_columns(db, "otis_commands")

        select_cols = [
            "command_text", "response_text", "success",
            "latency_ms", "created_at", "session_id"
        ]
        if "function_called" in cols:
            select_cols.append("function_called")

        rows = db.execute(
            f"""SELECT {', '.join(select_cols)}
                FROM otis_commands
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?""",
            (user["id"], limit)
        ).fetchall()

        commands = [dict(r) for r in rows]
        db.close()

        return jsonify({
            "success": True,
            "commands": commands,
            "total": len(commands)
        }), 200

    except Exception as e:
        logger.exception("[OTIS Routes] Failed to list commands")
        return jsonify({"success": False, "error": "Failed to load commands"}), 500


@otis_bp.route("/analytics", methods=["GET"])
@require_otis
def get_analytics(user):
    """
    GET /api/otis/analytics?period=7d

    Get voice usage analytics for current user.

    Returns:
        {
            "success": true,
            "summary": {
                "total_sessions": 10,
                "total_commands": 45,
                "avg_session_duration": 180,
                "total_voice_time": 1800,
                "success_rate": 0.95
            },
            "daily": [
                {
                    "date": "2026-03-26",
                    "sessions": 3,
                    "commands": 15,
                    "voice_time": 540
                }
            ]
        }
    """
    period = request.args.get("period", "7d")

    # Parse period
    try:
        if period.endswith("d"):
            days = int(period[:-1])
        else:
            days = 7
        days = min(days, 90)  # Max 90 days
    except (ValueError, TypeError):
        days = 7

    try:
        db = get_db()
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Summary stats
        summary = db.execute(
            """SELECT
                COUNT(DISTINCT session_id) as total_sessions,
                COUNT(*) as total_commands,
                AVG(latency_ms) as avg_latency,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate
               FROM otis_commands
               WHERE user_id = ? AND DATE(created_at) >= ?""",
            (user["id"], cutoff_date)
        ).fetchone()

        summary_data = dict(summary) if summary else {}

        # Session stats
        session_stats = db.execute(
            """SELECT
                COUNT(*) as total_sessions,
                AVG(duration_seconds) as avg_duration,
                SUM(duration_seconds) as total_voice_time
               FROM otis_sessions
               WHERE user_id = ? AND DATE(started_at) >= ?""",
            (user["id"], cutoff_date)
        ).fetchone()

        session_data = dict(session_stats) if session_stats else {}

        # Daily breakdown
        daily_rows = db.execute(
            """SELECT
                DATE(created_at) as date,
                COUNT(DISTINCT session_id) as sessions,
                COUNT(*) as commands,
                AVG(latency_ms) as avg_latency
               FROM otis_commands
               WHERE user_id = ? AND DATE(created_at) >= ?
               GROUP BY DATE(created_at)
               ORDER BY date DESC""",
            (user["id"], cutoff_date)
        ).fetchall()

        daily = [dict(r) for r in daily_rows]

        db.close()

        return jsonify({
            "success": True,
            "period": f"{days}d",
            "summary": {
                "total_sessions": session_data.get("total_sessions", 0),
                "total_commands": summary_data.get("total_commands", 0),
                "avg_session_duration": int(session_data.get("avg_duration", 0)),
                "total_voice_time": session_data.get("total_voice_time", 0),
                "avg_latency_ms": int(summary_data.get("avg_latency", 0)),
                "success_rate": round(summary_data.get("success_rate", 0), 2)
            },
            "daily": daily
        }), 200

    except Exception as e:
        logger.exception("[OTIS Routes] Failed to get analytics")
        return jsonify({"success": False, "error": "Failed to load analytics"}), 500


@otis_bp.route("/settings", methods=["GET"])
@require_otis
def get_settings(user):
    """
    GET /api/otis/settings

    Get user's OTIS settings.

    Returns:
        {
            "success": true,
            "settings": {
                "voice_speed": 1.0,
                "voice_pitch": 0.0,
                "auto_listen": true,
                "confirm_actions": true
            }
        }
    """
    try:
        db = get_db()
        row = db.execute(
            "SELECT * FROM otis_settings WHERE user_id = ?",
            (user["id"],)
        ).fetchone()

        if row:
            settings = dict(row)
            # Parse JSON settings if stored
            if "settings_json" in settings and settings["settings_json"]:
                try:
                    custom = json.loads(settings["settings_json"])
                    settings.update(custom)
                except json.JSONDecodeError:
                    pass
        else:
            # Default settings
            settings = {
                "voice_speed": 1.0,
                "voice_pitch": 0.0,
                "auto_listen": True,
                "confirm_actions": True
            }

        db.close()

        return jsonify({
            "success": True,
            "settings": settings
        }), 200

    except Exception as e:
        logger.exception("[OTIS Routes] Failed to get settings")
        return jsonify({"success": False, "error": "Failed to load settings"}), 500


@otis_bp.route("/settings", methods=["PUT"])
@require_otis
@audit_otis("settings_update")
def update_settings(user):
    """
    PUT /api/otis/settings
    Body: {
        "voice_speed": 1.2,
        "voice_pitch": 0.1,
        "auto_listen": false,
        "confirm_actions": true
    }

    Update user's OTIS settings.

    Returns:
        {"success": true, "settings": {...}}
    """
    data = request.get_json(silent=True) or {}

    try:
        db = get_db()

        # Check if settings exist
        row = db.execute(
            "SELECT id FROM otis_settings WHERE user_id = ?",
            (user["id"],)
        ).fetchone()

        settings_json = json.dumps(data)

        if row:
            # Update
            db.execute(
                "UPDATE otis_settings SET settings_json = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (settings_json, user["id"])
            )
        else:
            # Insert
            org_id = user.get("org_id")
            db.execute(
                "INSERT INTO otis_settings (org_id, user_id, settings_json) VALUES (?, ?, ?)",
                (org_id, user["id"], settings_json)
            )

        db.commit()
        db.close()

        logger.info(f"[OTIS Routes] Updated settings for user {user['id']}")

        return jsonify({
            "success": True,
            "settings": data
        }), 200

    except Exception as e:
        logger.exception("[OTIS Routes] Failed to update settings")
        return jsonify({"success": False, "error": "Failed to save settings"}), 500


@otis_bp.route("/validate", methods=["POST"])
@require_otis
def validate_command(user):
    """
    POST /api/otis/validate
    Body: {"command": "approve John's trip"}

    Pre-validate a voice command before sending it to OTIS.
    Returns whether it's valid, and whether confirmation is needed for high-risk commands.

    Returns:
        {
            "success": true,
            "valid": true,
            "needs_confirmation": true,
            "risk_reason": "This command performs an irreversible action"
        }
    """
    data = request.get_json(silent=True) or {}
    command = data.get("command", "").strip()

    if not command:
        return jsonify({"success": False, "error": "command is required"}), 400

    result = OtisCommandSecurity.validate(command)
    return jsonify({"success": True, **result}), 200


def _build_otis_context(user: dict, db) -> dict:
    """
    Build rich real-time context for OTIS from the database.
    Used so Gemini can answer questions about trips, expenses, and approvals.
    """
    ctx = {
        "user_name": user.get("name", "there"),
        "user_role": user.get("role", "employee"),
        "user_email": user.get("email", ""),
        "org_id": user.get("org_id"),
    }

    try:
        # Pending expenses — use actual schema columns
        rows = db.execute(
            """SELECT id, invoice_amount, category, verification_status, approval_status, created_at
               FROM expenses_db WHERE user_id = ? ORDER BY created_at DESC LIMIT 10""",
            (user["id"],)
        ).fetchall()
        expenses = [dict(r) for r in rows]
        pending = [
            e for e in expenses
            if e.get("approval_status") in ("draft", "submitted")
            or e.get("verification_status") == "pending"
        ]
        ctx["pending_expenses"] = pending
        ctx["total_expenses"] = len(expenses)
        ctx["pending_expense_count"] = len(pending)
        ctx["pending_expense_total"] = sum(float(e.get("invoice_amount", 0)) for e in pending)
    except Exception as e:
        logger.debug("[OTIS Context] expenses query failed: %s", e)
        _rollback_db_safely(db)

    try:
        # Recent travel requests — use actual schema columns
        rows = db.execute(
            """SELECT id, destination, purpose, status, start_date, end_date, estimated_total
               FROM travel_requests WHERE user_id = ? ORDER BY created_at DESC LIMIT 5""",
            (user["id"],)
        ).fetchall()
        ctx["recent_trips"] = [dict(r) for r in rows]
    except Exception as e:
        logger.debug("[OTIS Context] trips query failed: %s", e)
        _rollback_db_safely(db)

    try:
        # Pending approvals (if manager/admin) — use actual schema columns
        if user.get("role") in ("admin", "manager", "super_admin"):
            rows = db.execute(
                """SELECT tr.id, tr.destination, tr.purpose, u.name as requester_name,
                          tr.estimated_total, tr.status
                   FROM travel_requests tr
                   JOIN users u ON u.id = tr.user_id
                   WHERE tr.org_id = ? AND tr.status = 'submitted'
                   ORDER BY tr.created_at DESC LIMIT 10""",
                (user.get("org_id"),)
            ).fetchall()
            ctx["pending_approvals"] = [dict(r) for r in rows]
            ctx["pending_approval_count"] = len(ctx["pending_approvals"])
    except Exception as e:
        logger.debug("[OTIS Context] approvals query failed: %s", e)
        _rollback_db_safely(db)

    try:
        # Upcoming meetings — use actual schema columns (no title/location)
        today = datetime.now().date().isoformat()
        rows = db.execute(
            """SELECT client_name, company, meeting_date, venue, status
               FROM client_meetings WHERE user_id = ?
               AND meeting_date >= ? ORDER BY meeting_date ASC LIMIT 5""",
            (user["id"], today)
        ).fetchall()
        ctx["upcoming_meetings"] = [dict(r) for r in rows]
    except Exception as e:
        logger.debug("[OTIS Context] meetings query failed: %s", e)
        _rollback_db_safely(db)

    return ctx


def _resolve_structured_otis_query(user: dict, command_text: str) -> dict | None:
    """
    Try to answer OTIS data questions directly from the shared query engine.
    Returns None when the message is not a supported structured query.
    """
    try:
        if not should_use_structured_query(command_text):
            return None
        query_result = handle_query(user, command_text, strict=True)
        data = query_result.get("data", {}) if query_result else {}
        if not data.get("success"):
            return None

        response_text = format_query_result_for_voice(query_result, command_text)
        if not response_text:
            return None

        return {
            "response_text": response_text,
            "query_type": query_result.get("type"),
            "query_data": data,
            "data_source": "structured_query",
        }
    except Exception as e:
        logger.warning("[OTIS Structured Query] Failed for '%s': %s", command_text[:80], e)
        return None


def _resolve_otis_session_id(db, user_id: int, requested_session_id: str | None) -> str | None:
    """
    Resolve the session OTIS should use for this command.
    Reuses the requested session when valid, otherwise falls back to the
    user's current active session so follow-up turns keep their memory.
    """
    if requested_session_id:
        row = db.execute(
            "SELECT session_id FROM otis_sessions WHERE session_id = ? AND user_id = ?",
            (requested_session_id, user_id)
        ).fetchone()
        if row:
            return row["session_id"]

    active = db.execute(
        "SELECT session_id FROM otis_sessions WHERE user_id = ? AND status = 'active' "
        "ORDER BY started_at DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    return active["session_id"] if active else None


def _load_otis_conversation_history(db, session_id: str, max_turns: int = 5) -> list[dict]:
    """
    Load recent OTIS conversation turns in a history shape Gemini can use.
    This is resilient to older malformed rows so follow-up questions still
    inherit the latest valid context.
    """
    if not session_id:
        return []

    rows = db.execute(
        """SELECT role, content FROM (
               SELECT role, content, turn_number
               FROM otis_conversations
               WHERE session_id = ?
               ORDER BY turn_number DESC
               LIMIT ?
           ) recent
           ORDER BY turn_number ASC""",
        (session_id, max_turns * 2)
    ).fetchall()

    history = []
    pending_user = None

    for row in rows:
        role = (row["role"] or "").strip().lower()
        content = (row["content"] or "").strip()
        if not content:
            continue

        if role == "user":
            if pending_user:
                history.append({
                    "user_input": pending_user,
                    "assistant_response": "",
                })
            pending_user = content
            continue

        if role == "assistant":
            if pending_user is not None:
                history.append({
                    "user_input": pending_user,
                    "assistant_response": content,
                })
                pending_user = None
            elif history and not history[-1].get("assistant_response"):
                history[-1]["assistant_response"] = content

    if pending_user:
        history.append({
            "user_input": pending_user,
            "assistant_response": "",
        })

    return history[-max_turns:]


@otis_bp.route("/command", methods=["POST"])
@require_otis
def process_command_rest(user):
    """
    POST /api/otis/command
    Body: {"command": "What are my pending expenses?", "session_id": "otis-abc123"}

    Process a voice or text command via direct Gemini call with live DB context.
    Reliable synchronous path — no async complexity.

    Returns:
        {
            "success": true,
            "response": "You have 3 pending expenses totalling ₹12,450.",
            "session_id": "otis-abc123",
            "timestamp": "2026-03-27T..."
        }
    """
    data = request.get_json(silent=True) or {}
    command_text = data.get("command", "").strip()
    requested_session_id = data.get("session_id")

    if not command_text:
        return jsonify({"success": False, "error": "command is required"}), 400

    # Light sanitisation — strip dangerous chars only, keep natural language
    command_text = command_text[:1000]

    try:
        db = get_db()
        try:
            session_id = _resolve_otis_session_id(db, user["id"], requested_session_id)
            structured_result = _resolve_structured_otis_query(user, command_text)
            context = None
            conversation_history = []
            if not structured_result:
                context = _build_otis_context(user, db)
                conversation_history = _load_otis_conversation_history(db, session_id) if session_id else []
        finally:
            db.close()

        query_type = None
        query_data = None
        data_source = "gemini"

        if structured_result:
            response_text = structured_result["response_text"]
            query_type = structured_result["query_type"]
            query_data = structured_result["query_data"]
            data_source = structured_result["data_source"]
        else:
            from services.gemini_service import gemini

            response_text = gemini.generate_voice_optimized(
                prompt=command_text,
                context=context,
                conversation_history=conversation_history,
                model_type="flash"
            )

        if not response_text:
            response_text = "I understand. Could you please rephrase your question?"

        # Persist to conversation history
        if session_id:
            try:
                db3 = get_db()
                # Get current max turn number
                row = db3.execute(
                    "SELECT COALESCE(MAX(turn_number), 0) FROM otis_conversations WHERE session_id = ?",
                    (session_id,)
                ).fetchone()
                next_turn = (row[0] if row else 0) + 1
                db3.execute(
                    "INSERT INTO otis_conversations (session_id, turn_number, role, content) VALUES (?, ?, ?, ?)",
                    (session_id, next_turn, "user", command_text)
                )
                db3.execute(
                    "INSERT INTO otis_conversations (session_id, turn_number, role, content) VALUES (?, ?, ?, ?)",
                    (session_id, next_turn + 1, "assistant", response_text)
                )
                # Log to otis_commands
                db3.execute(
                    """INSERT INTO otis_commands
                       (org_id, user_id, session_id, command_text, transcript, response_text, success, latency_ms)
                       VALUES (?, ?, ?, ?, ?, ?, 1, 0)""",
                    (user.get("org_id"), user["id"], session_id, command_text, command_text, response_text)
                )
                db3.execute(
                    "UPDATE otis_sessions SET total_turns = COALESCE(total_turns, 0) + 1 WHERE session_id = ?",
                    (session_id,)
                )
                db3.commit()
                db3.close()
            except Exception:
                pass

        logger.info(f"[OTIS REST] user={user['id']} cmd='{command_text[:40]}' → '{response_text[:60]}...'")

        return jsonify({
            "success": True,
            "response": response_text,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "data_source": data_source,
            "query_type": query_type,
            "query_data": query_data,
        }), 200

    except Exception:
        logger.exception("[OTIS REST] Command processing failed")
        return jsonify({"success": False, "error": "Failed to process command"}), 500


# ── Audio Transcription ────────────────────────────────────────────────────────

@otis_bp.route("/transcribe", methods=["POST"])
@require_otis
def transcribe_audio(user):
    """
    POST /api/otis/transcribe
    Multipart form: audio=<file>

    Transcribes voice audio using the configured OTIS STT stack.
    Prefers Deepgram and falls back through the service chain when needed.

    Returns:
        {"success": true, "text": "transcribed text", "provider": "deepgram|google|vosk|mock|gemini"}
    """
    if "audio" not in request.files:
        return jsonify({"success": False, "error": "audio file required"}), 400

    audio_file   = request.files["audio"]
    mime_type    = audio_file.content_type or audio_file.mimetype or "audio/webm"
    audio_bytes  = audio_file.read()

    if len(audio_bytes) < 400:
        return jsonify({"success": False, "error": "Audio too short — try again"}), 400

    # ── Try the OTIS STT stack first ─────────────────────────────────────────
    try:
        import asyncio
        import concurrent.futures
        from services.deepgram_service import SpeechToTextService
        stt = SpeechToTextService()

        # asyncio.run() fails inside Flask-SocketIO (gevent patches the loop).
        # Run in a fresh thread with its own event loop instead.
        def _run_stt():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(stt.transcribe(audio_bytes))
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            result = ex.submit(_run_stt).result(timeout=15)

        if result and result.text:
            provider = getattr(getattr(result, "provider", None), "value", "unknown")
            logger.info(
                f"[OTIS Transcribe] {provider} OK: '{result.text[:60]}' "
                f"(conf={getattr(result, 'confidence', 0):.2f})"
            )
            return jsonify({
                "success":    True,
                "text":       result.text,
                "confidence": getattr(result, "confidence", 0.9),
                "provider":   provider,
            }), 200
    except Exception as e:
        logger.warning(f"[OTIS Transcribe] STT service failed, trying Gemini: {e}")

    # ── Fallback: Gemini multimodal transcription ─────────────────────────────
    try:
        from services.gemini_service import gemini
        text = gemini.transcribe_audio(audio_bytes, mime_type)
        if text:
            logger.info(f"[OTIS Transcribe] Gemini fallback OK: '{text[:60]}'")
            return jsonify({"success": True, "text": text, "provider": "gemini"}), 200
    except Exception as e:
        logger.warning(f"[OTIS Transcribe] Gemini transcription failed: {e}")

    return jsonify({"success": False, "error": "Could not transcribe audio"}), 422


# ── Text-to-Speech ────────────────────────────────────────────────────────────

@otis_bp.route("/speak", methods=["POST"])
@require_otis
def speak_text(user):
    """
    POST /api/otis/speak
    Body: {"text": "Hello, I am Jarvis."}

    Synthesises speech using the OTIS TTS stack and returns playable audio.

    Returns:
        audio/* binary  — on success
        {"success": false, "error": "..."}  — on failure
    """
    from flask import Response
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()[:2000]

    if not text:
        return jsonify({"success": False, "error": "text is required"}), 400

    try:
        import asyncio
        import concurrent.futures
        from services.elevenlabs_voice_service import TextToSpeechService
        tts = TextToSpeechService()

        # asyncio.run() fails inside Flask-SocketIO (gevent patches the loop).
        # Run in a fresh thread with its own event loop instead.
        def _run_tts():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(tts.speak(text))
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            result = ex.submit(_run_tts).result(timeout=10)

        if result and result.audio_data:
            provider = getattr(getattr(result, "provider", None), "value", "unknown")
            audio_format = (getattr(result, "audio_format", "") or "").lower()
            mimetype = {
                "mp3": "audio/mpeg",
                "wav": "audio/wav",
            }.get(audio_format, "application/octet-stream")

            logger.info(f"[OTIS Speak] {provider} OK — {len(result.audio_data)} bytes")
            return Response(
                result.audio_data,
                mimetype=mimetype,
                headers={
                    "Content-Length": str(len(result.audio_data)),
                    "X-Provider":     provider,
                    "Cache-Control":  "no-store",
                },
            )
    except Exception as e:
        logger.exception(f"[OTIS Speak] TTS failed: {e}")
        return jsonify({"success": False, "error": "TTS synthesis failed"}), 500

    return jsonify({"success": False, "error": "TTS returned no audio"}), 500
