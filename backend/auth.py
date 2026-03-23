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
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# In-memory user cache — avoids DB round-trip on every request (60s TTL)
_user_cache = TTLCache(maxsize=100, ttl=60)


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
    # Check cache first
    cached = _user_cache.get(user_id)
    if cached is not None:
        return cached
    try:
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        db.close()
        if user:
            result = dict(user)
            _user_cache[user_id] = result
            return result
        return None
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
    return _get_user_by_id(user_id)


def login_required(f):
    """Decorator: require user to be logged in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            # Demo mode fallback: only allowed in non-GCP dev environments
            if session.get("demo_mode") and not _is_production():
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
            if session.get("demo_mode") and not _is_production():
                return f(*args, **kwargs)
            return jsonify({"success": False, "error": "Authentication required"}), 401
        if user["role"] not in ("admin", "manager"):
            return jsonify({"success": False, "error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


def _is_production() -> bool:
    """Check if running in production (GCP or explicit production flag)."""
    import os
    return bool(
        os.getenv("K_SERVICE")
        or os.getenv("GAE_APPLICATION")
        or os.getenv("PRODUCTION")
    )


def login_user(username, password):
    """Authenticate user and create session. Accepts username or email."""
    try:
        db = get_db()
        # Try username first, then email
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not user and "@" in username:
            user = db.execute("SELECT * FROM users WHERE email = ?", (username,)).fetchone()
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            # Block unverified accounts
            u = dict(user)
            if not u.get("email_verified", 1):
                return {"success": False, "error": "Email not verified. Please check your inbox for the verification code.", "needs_verification": True, "email": u.get("email", "")}
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
                    "name": name,
                    "full_name": name,
                    "email": u.get("email", ""),
                    "role": u.get("role", "employee"),
                    "department": u.get("department", "General"),
                    "avatar_initials": "".join(w[0].upper() for w in name.split()[:2]),
                }
            }
        return {"success": False, "error": "Invalid username or password"}
    except Exception as e:
        logger.exception("[Auth] login_user failed for %s", username)
        return {"success": False, "error": "Login failed. Please try again."}


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
                    "name": name,
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
                "id": 1, "username": "admin", "name": "Demo Admin",
                "full_name": "Demo Admin", "email": "admin@demo.com",
                "role": "admin", "department": "Management",
                "avatar_initials": "DA"
            }
        }
    except Exception:
        session["user_id"] = 1
        session["demo_mode"] = True
        return {
            "success": True,
            "user": {
                "id": 1, "username": "admin", "name": "Demo Admin",
                "full_name": "Demo Admin", "email": "admin@demo.com",
                "role": "admin", "department": "Management",
                "avatar_initials": "DA"
            }
        }


def logout_user():
    """Clear session."""
    session.clear()
    return {"success": True, "message": "Logged out"}
