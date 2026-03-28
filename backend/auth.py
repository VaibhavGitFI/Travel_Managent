"""
TravelSync Pro - Authentication (Session + JWT)
Session cookies for browser SPA; JWT Bearer tokens for Cloud Run horizontal scaling.
Both auth methods are accepted by all protected endpoints.
"""
import time
import secrets
import logging
from functools import wraps
from flask import session, jsonify, request, make_response
from werkzeug.security import check_password_hash
from database import get_db
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# In-memory user cache — avoids DB round-trip on every request (60s TTL)
_user_cache = TTLCache(maxsize=100, ttl=60)

# ── JWT Token Blacklist ───────────────────────────────────────────────────────
# Revoked tokens stored with their expiry time; cleaned up periodically.
_token_blacklist: dict[str, float] = {}   # {jti_or_token_hash: expiry_timestamp}
_blacklist_last_cleanup = 0.0


# ── JWT helpers ────────────────────────────────────────────────────────────────

def _jwt_secret() -> str:
    from config import Config
    return Config.JWT_SECRET_KEY or Config.SECRET_KEY


def generate_tokens(user_id: int, org_id: int | None = None, org_role: str | None = None) -> dict:
    """Generate access + refresh JWT tokens for a user.  Includes org context if provided."""
    try:
        import jwt
        from config import Config
        now = int(time.time())
        base = {"sub": str(user_id), "iat": now}
        if org_id:
            base["org_id"] = org_id
        if org_role:
            base["org_role"] = org_role
        access_payload = {**base, "exp": now + Config.JWT_ACCESS_TTL * 60, "type": "access"}
        refresh_payload = {**base, "exp": now + Config.JWT_REFRESH_TTL * 86400, "type": "refresh"}
        access_token = jwt.encode(access_payload, _jwt_secret(), algorithm="HS256")
        refresh_token = jwt.encode(refresh_payload, _jwt_secret(), algorithm="HS256")
        return {"access_token": access_token, "refresh_token": refresh_token}
    except Exception as exc:
        logger.warning("[Auth] JWT generation failed: %s", exc)
        return {}


def verify_token(token: str, token_type: str = "access") -> int | None:
    """Verify a JWT token; return user_id (int) or None. Rejects blacklisted tokens."""
    try:
        import jwt, hashlib
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
        if payload.get("type") != token_type:
            return None
        # Check blacklist
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        if token_hash in _token_blacklist:
            return None
        return int(payload["sub"])
    except Exception:
        return None


def revoke_token(token: str) -> None:
    """Add a token to the blacklist. Auto-cleans expired entries."""
    import hashlib
    global _blacklist_last_cleanup
    try:
        import jwt
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"], options={"verify_exp": False})
        expiry = payload.get("exp", time.time() + 86400)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        _token_blacklist[token_hash] = expiry
        # Periodic cleanup (every 10 min)
        now = time.time()
        if now - _blacklist_last_cleanup > 600:
            _blacklist_last_cleanup = now
            expired = [k for k, exp in _token_blacklist.items() if exp < now]
            for k in expired:
                _token_blacklist.pop(k, None)
    except Exception:
        pass


def invalidate_user_cache(user_id: int) -> None:
    """Explicitly bust the auth cache for a user (call after role/permission changes)."""
    _user_cache.pop(user_id, None)


# ── CSRF Protection ──────────────────────────────────────────────────────────

def generate_csrf_token() -> str:
    """Generate a new CSRF token and store it in the session."""
    token = secrets.token_hex(32)
    session["_csrf_token"] = token
    return token


def validate_csrf(f):
    """Decorator: validate CSRF token on state-changing requests.
    Token must be sent as X-CSRF-Token header.
    Skips validation for JWT-authenticated requests (stateless, no CSRF risk).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # CSRF only applies to cookie/session auth, not Bearer token auth
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return f(*args, **kwargs)
        # Safe methods don't need CSRF
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return f(*args, **kwargs)
        # Validate token
        csrf_token = request.headers.get("X-CSRF-Token", "")
        session_token = session.get("_csrf_token", "")
        if not csrf_token or not session_token or csrf_token != session_token:
            return jsonify({"success": False, "error": "CSRF token missing or invalid"}), 403
        return f(*args, **kwargs)
    return decorated


# ── Multi-tenancy helpers ─────────────────────────────────────────────────────

# Cache for org membership lookups (user_id → {org_id, org_role})
_org_cache = TTLCache(maxsize=200, ttl=120)


def get_user_org(user_id: int) -> dict | None:
    """Return the user's active org membership: {org_id, org_role, org_name, org_slug}."""
    cached = _org_cache.get(user_id)
    if cached is not None:
        return cached
    try:
        db = get_db()
        row = db.execute("""
            SELECT om.org_id, om.org_role, o.name AS org_name, o.slug AS org_slug
            FROM org_members om
            JOIN organizations o ON o.id = om.org_id
            WHERE om.user_id = ?
            ORDER BY om.joined_at ASC
            LIMIT 1
        """, (user_id,)).fetchone()
        db.close()
        if row:
            result = dict(row)
            _org_cache[user_id] = result
            return result
        return None
    except Exception:
        return None


def _attach_org_context(user: dict | None) -> dict | None:
    """Return a copy of the user payload enriched with active org context."""
    if not user:
        return None

    enriched = dict(user)
    if enriched.get("org_id") and enriched.get("org_role"):
        return enriched

    org_id = None
    org_role = None
    org_name = None
    org_slug = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        try:
            import jwt
            payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
            if payload.get("org_id"):
                org_id = int(payload["org_id"])
                org_role = payload.get("org_role")
        except Exception:
            pass

    if not org_id:
        org_id = session.get("org_id")
        org_role = session.get("org_role", org_role)

    membership = get_user_org(enriched.get("id")) if enriched.get("id") else None
    if membership:
        if not org_id:
            org_id = membership.get("org_id")
        if not org_role:
            org_role = membership.get("org_role")
        org_name = membership.get("org_name")
        org_slug = membership.get("org_slug")

    if org_id:
        enriched["org_id"] = org_id
        if org_role:
            enriched["org_role"] = org_role
        if org_name:
            enriched["org_name"] = org_name
        if org_slug:
            enriched["org_slug"] = org_slug

    return enriched


def get_current_org() -> dict | None:
    """Return current user's org context. Checks JWT claims first, then DB."""
    # 1. JWT may carry org_id directly
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        try:
            import jwt
            payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
            if payload.get("org_id"):
                return {
                    "org_id": int(payload["org_id"]),
                    "org_role": payload.get("org_role", "member"),
                }
        except Exception:
            pass
    # 2. Session may carry org_id
    org_id = session.get("org_id")
    if org_id:
        return {"org_id": org_id, "org_role": session.get("org_role", "member")}
    # 3. Look up from DB
    user = get_current_user()
    if user:
        membership = get_user_org(user["id"])
        if membership:
            # Stash in session for future requests
            session["org_id"] = membership["org_id"]
            session["org_role"] = membership["org_role"]
            return membership
    return None


def org_required(f):
    """Decorator: require user to belong to an organization."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        org = get_current_org()
        if not org:
            return jsonify({"success": False, "error": "Organization membership required"}), 403
        return f(*args, **kwargs)
    return decorated


def org_admin_required(f):
    """Decorator: require org_owner or org_admin role within the org."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        org = get_current_org()
        if not org:
            return jsonify({"success": False, "error": "Organization membership required"}), 403
        if org.get("org_role") not in ("org_owner", "org_admin"):
            return jsonify({"success": False, "error": "Organization admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


def invalidate_org_cache(user_id: int) -> None:
    """Bust org cache for a user (call after membership changes)."""
    _org_cache.pop(user_id, None)


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
            return _attach_org_context(_get_user_by_id(user_id))

    # 2. Session cookie (existing browser SPA flow)
    user_id = session.get("user_id")
    if not user_id:
        return None
    return _attach_org_context(_get_user_by_id(user_id))


def login_required(f):
    """Decorator: require user to be logged in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator: require admin, manager, or super_admin role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        if user["role"] not in ("admin", "manager", "super_admin"):
            return jsonify({"success": False, "error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


def super_admin_required(f):
    """Decorator: require super_admin role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        if user["role"] != "super_admin":
            return jsonify({"success": False, "error": "Super admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


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
            u = dict(user)
            name = u.get("name") or u.get("full_name") or u["username"]

            # Resolve org membership for JWT + session
            membership = get_user_org(u["id"])
            org_id = membership["org_id"] if membership else None
            org_role = membership.get("org_role") if membership else None
            if org_id:
                session["org_id"] = org_id
                session["org_role"] = org_role

            tokens = generate_tokens(u["id"], org_id=org_id, org_role=org_role)
            csrf_token = generate_csrf_token()

            user_payload = {
                "id": u["id"],
                "username": u["username"],
                "name": name,
                "full_name": name,
                "email": u.get("email", ""),
                "role": u.get("role", "employee"),
                "department": u.get("department", "General"),
                "avatar_initials": "".join(w[0].upper() for w in name.split()[:2]),
                "profile_picture": u.get("profile_picture"),
                "sub_role": u.get("sub_role"),
                "phone": u.get("phone"),
            }
            if membership:
                user_payload["org_id"] = org_id
                user_payload["org_role"] = org_role
                user_payload["org_name"] = membership.get("org_name")
                user_payload["org_slug"] = membership.get("org_slug")

            return {
                "success": True,
                **tokens,
                "csrf_token": csrf_token,
                "user": user_payload,
            }
        return {"success": False, "error": "Invalid username or password"}
    except Exception as e:
        logger.exception("[Auth] login_user failed for %s", username)
        return {"success": False, "error": "Login failed. Please try again."}


def logout_user(access_token: str = None, refresh_token: str = None):
    """Clear session and revoke JWT tokens."""
    if access_token:
        revoke_token(access_token)
    if refresh_token:
        revoke_token(refresh_token)
    session.clear()
    return {"success": True, "message": "Logged out"}
