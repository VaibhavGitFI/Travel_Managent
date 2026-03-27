"""
TravelSync Pro — OTIS Security Module
Reusable decorators and validators for OTIS voice assistant routes.

Provides:
- require_otis  : Combined auth + OTIS permission decorator
- audit_otis    : Audit-logs every OTIS API call to the database
- OtisCommandSecurity : Validates commands, detects high-risk actions

Usage:
    from otis_security import require_otis, audit_otis, OtisCommandSecurity

    @otis_bp.route("/start", methods=["POST"])
    @require_otis
    def start_session(user):
        ...

    @otis_bp.route("/settings", methods=["PUT"])
    @require_otis
    @audit_otis("settings_update")
    def update_settings(user):
        ...
"""
import logging
import functools
import re
from datetime import datetime
from flask import jsonify, request, g
from auth import get_current_user
from config import Config

logger = logging.getLogger(__name__)

# ── Role constants ─────────────────────────────────────────────────────────────
ELEVATED_ROLES = ("admin", "manager", "super_admin")

# ── High-risk voice commands that require explicit confirmation ────────────────
# These patterns trigger a "needs_confirmation" flag in the response so the
# frontend can prompt the user before the action is executed.
_HIGH_RISK_PATTERNS = [
    # Financial approvals / rejections
    r"\b(approve|reject|deny)\b.*(trip|travel|request|expense)",
    # Bulk operations
    r"\b(delete|remove|cancel)\b.*(all|every|bulk)",
    # Budget / policy changes
    r"\b(change|update|set)\b.*(policy|budget|limit)",
]

_COMPILED_HIGH_RISK = [re.compile(p, re.IGNORECASE) for p in _HIGH_RISK_PATTERNS]


def _check_otis_permission(user: dict) -> tuple[bool, str]:
    """
    Single source of truth for OTIS permission logic.
    Returns (allowed: bool, reason: str).
    Called from both the require_otis decorator and the /status endpoint.
    """
    if not Config.OTIS_ENABLED:
        return False, "OTIS is currently disabled"
    if Config.OTIS_ADMIN_ONLY and user.get("role") not in ELEVATED_ROLES:
        return False, "OTIS is currently available to admins and managers only"
    return True, ""


# ── Decorators ─────────────────────────────────────────────────────────────────

def require_otis(fn):
    """
    Decorator: checks authentication + OTIS permission before the route runs.
    Injects `user` dict as the first positional argument to the route function.

    Usage:
        @otis_bp.route("/start", methods=["POST"])
        @require_otis
        def start_session(user):
            ...
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        allowed, reason = _check_otis_permission(user)
        if not allowed:
            logger.warning(
                "[OTIS Security] Access denied for user %s (role=%s): %s",
                user.get("id"), user.get("role"), reason
            )
            return jsonify({"success": False, "error": reason}), 403
        # Store on flask g so audit_otis can read it without a second DB call
        g.otis_user = user
        return fn(user, *args, **kwargs)
    return wrapper


def audit_otis(action: str):
    """
    Decorator factory: writes an audit record to otis_analytics after the route.
    Must be used AFTER @require_otis (so g.otis_user is set).

    Usage:
        @otis_bp.route("/settings", methods=["PUT"])
        @require_otis
        @audit_otis("settings_update")
        def update_settings(user):
            ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            # Non-blocking audit write — failures must never crash the route
            try:
                user = getattr(g, "otis_user", None)
                if user:
                    _write_audit_log(user, action)
            except Exception as e:
                logger.debug("[OTIS Audit] Non-blocking audit write failed: %s", e)
            return result
        return wrapper
    return decorator


def _write_audit_log(user: dict, action: str) -> None:
    """
    Write audit entry to access log. Also bumps the daily otis_analytics
    total_commands counter (schema-tolerant — silently skips if columns differ).
    """
    logger.info(
        "[OTIS Audit] user=%s role=%s action=%s ip=%s",
        user.get("id"), user.get("role"), action,
        _get_client_ip()
    )
    try:
        from database import get_db, table_columns
        today = datetime.now().date().isoformat()
        org_id = user.get("org_id")
        db = get_db()
        cols = table_columns(db, "otis_analytics")
        # Only write if the analytics table has the expected org/date columns
        if "org_id" in cols and "date" in cols and "total_commands" in cols:
            # Try to find existing row for today/org
            existing = db.execute(
                "SELECT id FROM otis_analytics WHERE org_id IS ? AND date = ? LIMIT 1",
                (org_id, today)
            ).fetchone()
            if existing:
                db.execute(
                    "UPDATE otis_analytics SET total_commands = COALESCE(total_commands, 0) + 1 "
                    "WHERE id = ?",
                    (existing["id"],)
                )
            else:
                db.execute(
                    "INSERT INTO otis_analytics (org_id, date, total_commands) VALUES (?, ?, 1)",
                    (org_id, today)
                )
            db.commit()
        db.close()
    except Exception:
        pass  # Audit must never raise


def _get_client_ip() -> str:
    """Get client IP from Flask request context (non-blocking)."""
    try:
        from flask import request as flask_request
        return (
            flask_request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or flask_request.remote_addr
            or "unknown"
        )
    except Exception:
        return "unknown"


# ── Command-Level Security ─────────────────────────────────────────────────────

class OtisCommandSecurity:
    """
    Validates voice commands before they are executed by the OTIS agent.

    Checks:
    1. Command is not empty / too long
    2. Command does not contain injection-style payloads
    3. High-risk commands are flagged so the frontend can confirm with the user
       (unless OTIS_REQUIRE_CONFIRMATION=False, which means auto-execute)
    """

    MAX_COMMAND_LENGTH = 512
    # Very basic check — OTIS doesn't run code but we want to catch prompt injection
    _INJECTION_PATTERNS = [
        r"ignore previous instructions",
        r"disregard.*instructions",
        r"system prompt",
        r"you are now",
        r"act as if",
        r"pretend you",
    ]
    _COMPILED_INJECTION = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

    @classmethod
    def validate(cls, command: str) -> dict:
        """
        Validate a voice command text.

        Returns:
            {
                "valid": True,
                "command": "<cleaned command>",
                "is_high_risk": False,
                "needs_confirmation": False,  # True when high-risk + REQUIRE_CONFIRMATION=True
                "risk_reason": None
            }
        Or:
            {
                "valid": False,
                "error": "<reason>"
            }
        """
        if not command or not command.strip():
            return {"valid": False, "error": "Command cannot be empty"}

        command = command.strip()

        if len(command) > cls.MAX_COMMAND_LENGTH:
            return {
                "valid": False,
                "error": f"Command too long (max {cls.MAX_COMMAND_LENGTH} characters)"
            }

        # Prompt-injection detection
        for pattern in cls._COMPILED_INJECTION:
            if pattern.search(command):
                logger.warning("[OTIS Security] Potential injection attempt: %r", command[:80])
                return {"valid": False, "error": "Command not allowed"}

        # High-risk action detection
        is_high_risk = False
        risk_reason = None
        for pattern in _COMPILED_HIGH_RISK:
            if pattern.search(command):
                is_high_risk = True
                risk_reason = "This command performs an irreversible action"
                break

        needs_confirmation = is_high_risk and Config.OTIS_REQUIRE_CONFIRMATION

        return {
            "valid": True,
            "command": command,
            "is_high_risk": is_high_risk,
            "needs_confirmation": needs_confirmation,
            "risk_reason": risk_reason,
        }

    @classmethod
    def check_command_quota(cls, user_id: int, session_id: str) -> tuple[bool, str]:
        """
        Check if user is within per-session command quota.
        Returns (allowed: bool, reason: str).
        """
        try:
            from database import get_db
            db = get_db()
            count_row = db.execute(
                "SELECT COUNT(*) AS cnt FROM otis_commands WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            db.close()
            count = count_row["cnt"] if count_row else 0
            if count >= Config.OTIS_MAX_COMMANDS_PER_SESSION:
                return False, (
                    f"Session command limit reached "
                    f"({Config.OTIS_MAX_COMMANDS_PER_SESSION} commands per session)"
                )
            return True, ""
        except Exception as e:
            logger.debug("[OTIS Security] Quota check failed: %s", e)
            return True, ""  # Fail open — don't block on quota errors


# ── Convenience re-export for routes ──────────────────────────────────────────
# Routes can import _check_otis_permission from here to keep /status lean
check_otis_permission = _check_otis_permission
