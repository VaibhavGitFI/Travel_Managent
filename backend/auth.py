"""
TravelSync Pro - Session-based Authentication
Provides login_required/admin_required decorators and auth API endpoints
"""
from functools import wraps
from flask import session, jsonify, request
from werkzeug.security import check_password_hash
from database import get_db


def get_current_user():
    """Get the currently logged-in user from session."""
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
            return {
                "success": True,
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
