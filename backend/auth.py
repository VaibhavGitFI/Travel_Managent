"""
TravelSync Pro - Authentication (Session + JWT)
Session cookies for browser SPA; JWT Bearer tokens for Cloud Run horizontal scaling.
Both auth methods are accepted by all protected endpoints.
"""
import time
import logging
from functools import wraps
from flask import session, jsonify, request
from werkzeug.security import check_password_hash
from database import get_db

logger = logging.getLogger(__name__)


# ── JWT helpers ────────────────────────────────────────────────────────────────

def _jwt_secret() -> str:
    from config import Config
    return Config.JWT_SECRET_KEY or Config.SECRET_KEY


def generate_tokens(user_id: int) -> dict:
    """Generate access + refresh JWT tokens for a user."""
    try:
        import jwt
        from config import Config
        now = int(time.time())
        access_payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + Config.JWT_ACCESS_TTL * 60,
            "type": "access",
        }
        refresh_payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + Config.JWT_REFRESH_TTL * 86400,
            "type": "refresh",
        }
        access_token = jwt.encode(access_payload, _jwt_secret(), algorithm="HS256")
        refresh_token = jwt.encode(refresh_payload, _jwt_secret(), algorithm="HS256")
        return {"access_token": access_token, "refresh_token": refresh_token}
    except Exception as exc:
        logger.warning("[Auth] JWT generation failed: %s", exc)
        return {}


def verify_token(token: str, token_type: str = "access") -> int | None:
    """Verify a JWT token; return user_id (int) or None."""
    try:
        import jwt
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
        if payload.get("type") != token_type:
            return None
        return int(payload["sub"])
    except Exception:
        return None


def _get_user_by_id(user_id: int) -> dict | None:
    try:
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        db.close()
        return dict(user) if user else None
    except Exception:
        return None


def get_current_user():
    """
    Get the currently authenticated user.
    Checks (in order): JWT Bearer header → Flask session cookie.
    """
    # 1. JWT Bearer token in Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        user_id = verify_token(token, "access")
        if user_id:
            return _get_user_by_id(user_id)

    # 2. Session cookie (existing browser SPA flow)
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        db.close()
        if user:
            return dict(user)
        return None
    except Exception:
        return None


def login_required(f):
    """Decorator: require user to be logged in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            # Demo mode fallback: auto-login as admin if no DB auth
            if session.get("demo_mode"):
                return f(*args, **kwargs)
            return jsonify({"success": False, "error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator: require admin or manager role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            if session.get("demo_mode"):
                return f(*args, **kwargs)
            return jsonify({"success": False, "error": "Authentication required"}), 401
        if user["role"] not in ("admin", "manager"):
            return jsonify({"success": False, "error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


def login_user(username, password):
    """Authenticate user and create session."""
    try:
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["demo_mode"] = False
            u = dict(user)
            name = u.get("name") or u.get("full_name") or u["username"]
            tokens = generate_tokens(u["id"])
            return {
                "success": True,
                **tokens,
                "user": {
                    "id": u["id"],
                    "username": u["username"],
                    "full_name": name,
                    "email": u.get("email", ""),
                    "role": u.get("role", "employee"),
                    "department": u.get("department", "General"),
                    "avatar_initials": "".join(w[0].upper() for w in name.split()[:2]),
                }
            }
        return {"success": False, "error": "Invalid username or password"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def demo_login():
    """Auto-login as admin for demo mode."""
    try:
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        db.close()

        if user:
            session["user_id"] = user["id"]
            session["demo_mode"] = True
            u = dict(user)
            name = u.get("name") or u.get("full_name") or u["username"]
            return {
                "success": True,
                "user": {
                    "id": u["id"],
                    "username": u["username"],
                    "full_name": name,
                    "email": u.get("email", ""),
                    "role": u.get("role", "admin"),
                    "department": u.get("department", "General"),
                    "avatar_initials": "".join(w[0].upper() for w in name.split()[:2]),
                }
            }
        # Fallback if no users exist
        session["user_id"] = 1
        session["demo_mode"] = True
        return {
            "success": True,
            "user": {
                "id": 1, "username": "admin", "full_name": "Demo Admin",
                "email": "admin@demo.com", "role": "admin",
                "department": "Management", "avatar_initials": "DA"
            }
        }
    except Exception:
        session["user_id"] = 1
        session["demo_mode"] = True
        return {
            "success": True,
            "user": {
                "id": 1, "username": "admin", "full_name": "Demo Admin",
                "email": "admin@demo.com", "role": "admin",
                "department": "Management", "avatar_initials": "DA"
            }
        }


def logout_user():
    """Clear session."""
    session.clear()
    return {"success": True, "message": "Logged out"}
