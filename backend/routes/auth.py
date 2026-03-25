"""
TravelSync Pro — Authentication Routes
Handles login, logout, register, password reset, and current-user endpoints.
"""
import logging
import secrets
import time
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash
from auth import login_user, logout_user, get_current_user, verify_token, generate_tokens, _get_user_by_id
from database import get_db
from extensions import limiter

logger = logging.getLogger(__name__)

# In-memory token stores
_reset_tokens = {}   # {code: {"user_id": int, "expires": float}}
_verify_tokens = {}  # {code: {"user_id": int, "email": str, "expires": float}}

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    """POST /api/auth/login — authenticate user and start session."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400

    result = login_user(username, password)
    status = 200 if result.get("success") else 401
    return jsonify(result), status


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """POST /api/auth/logout — clear session."""
    result = logout_user()
    return jsonify(result), 200


@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    """POST /api/auth/refresh — exchange a refresh token for a new access token."""
    data = request.get_json(silent=True) or {}
    refresh_token = (data.get("refresh_token") or "").strip()
    if not refresh_token:
        return jsonify({"success": False, "error": "refresh_token is required"}), 400

    user_id = verify_token(refresh_token, "refresh")
    if not user_id:
        return jsonify({"success": False, "error": "Invalid or expired refresh token"}), 401

    user = _get_user_by_id(user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 401

    tokens = generate_tokens(user_id)
    return jsonify({"success": True, **tokens}), 200


@auth_bp.route("/me", methods=["GET"])
def me():
    """GET /api/auth/me — return current logged-in user from session."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    # Strip password_hash before returning
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}
    return jsonify({"success": True, "user": safe_user}), 200


@auth_bp.route("/register", methods=["POST"])
@limiter.limit("3 per minute")
def register():
    """POST /api/auth/register — create account and send verification email."""
    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")
    department = (data.get("department") or "General").strip()

    if not full_name or not email or not password:
        return jsonify({"success": False, "error": "Full name, email, and password are required"}), 400

    if "@" not in email or "." not in email:
        return jsonify({"success": False, "error": "Invalid email address"}), 400

    if len(password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400

    # Generate username from email (before the @)
    username = email.split("@")[0].lower().replace(".", "_").replace("-", "_")

    try:
        db = get_db()
        # Check if email already exists
        existing = db.execute("SELECT id, email_verified FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            ex = dict(existing)
            if ex.get("email_verified", 1):
                db.close()
                return jsonify({"success": False, "error": "An account with this email already exists"}), 409
            else:
                # Unverified account — resend code
                user_id = ex["id"]
                db.close()
                verify_code = f"{secrets.randbelow(1000000):06d}"
                _verify_tokens[verify_code] = {"user_id": user_id, "email": email, "expires": time.time() + 900}
                _send_verification_email(email, full_name, verify_code)
                return jsonify({
                    "success": True,
                    "needs_verification": True,
                    "message": "Verification code resent to your email.",
                }), 200

        # Check if username exists, append number if so
        base_username = username
        counter = 1
        while db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            username = f"{base_username}{counter}"
            counter += 1

        initials = "".join(w[0].upper() for w in full_name.split()[:2])
        password_hash = generate_password_hash(password)

        # Create user with email_verified = 0
        db.execute(
            """INSERT INTO users (username, password_hash, name, full_name, email, role, department, avatar_initials, email_verified)
               VALUES (?, ?, ?, ?, ?, 'employee', ?, ?, 0)""",
            (username, password_hash, full_name, full_name, email, department, initials),
        )
        db.commit()

        user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        db.close()

        if user:
            # Generate and send verification code
            verify_code = f"{secrets.randbelow(1000000):06d}"
            _verify_tokens[verify_code] = {"user_id": user["id"], "email": email, "expires": time.time() + 900}
            _send_verification_email(email, full_name, verify_code)

            return jsonify({
                "success": True,
                "needs_verification": True,
                "message": "Account created! Check your email for the verification code.",
            }), 201

        return jsonify({"success": False, "error": "Registration failed"}), 500
    except Exception as e:
        logger.exception("[Auth] register failed")
        return jsonify({"success": False, "error": "Registration failed. Please try again."}), 500


@auth_bp.route("/verify-email", methods=["POST"])
@limiter.limit("5 per minute")
def verify_email():
    """POST /api/auth/verify-email — verify email with 6-digit code."""
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()

    if not code:
        return jsonify({"success": False, "error": "Verification code is required"}), 400

    token_data = _verify_tokens.get(code)
    if not token_data:
        return jsonify({"success": False, "error": "Invalid verification code"}), 400

    if time.time() > token_data["expires"]:
        _verify_tokens.pop(code, None)
        return jsonify({"success": False, "error": "Code expired. Please register again."}), 400

    try:
        db = get_db()
        db.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (token_data["user_id"],))
        db.commit()

        user = db.execute("SELECT * FROM users WHERE id = ?", (token_data["user_id"],)).fetchone()
        db.close()

        _verify_tokens.pop(code, None)

        if user:
            u = dict(user)
            session["user_id"] = u["id"]
            tokens = generate_tokens(u["id"])
            name = u.get("full_name") or u.get("name") or u["username"]
            return jsonify({
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
                    "avatar_initials": u.get("avatar_initials", ""),
                },
            }), 200

        return jsonify({"success": False, "error": "Verification failed"}), 500
    except Exception as e:
        logger.exception("[Auth] verify_email failed")
        return jsonify({"success": False, "error": "Verification failed"}), 500


def _send_verification_email(email: str, name: str, code: str):
    """Send the 6-digit verification code via email."""
    try:
        from services.email_service import email_service
        email_service.send_notification(
            to_email=email,
            title="Verify Your Email",
            message=f"Hi {name},\n\nYour verification code is:\n\n{code}\n\nEnter this code to activate your TravelSync Pro account. It expires in 15 minutes.",
            notification_type="info",
        )
    except Exception as exc:
        logger.warning("[Auth] Failed to send verification email: %s", exc)


@auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("3 per minute")
def forgot_password():
    """POST /api/auth/forgot-password — send a password reset email."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"success": False, "error": "Email is required"}), 400

    try:
        db = get_db()
        user = db.execute("SELECT id, full_name, email FROM users WHERE email = ?", (email,)).fetchone()
        db.close()

        # Always return success to prevent email enumeration
        if not user:
            return jsonify({"success": True, "message": "If an account with that email exists, a reset link has been sent."}), 200

        # Generate reset token (6-digit code for simplicity)
        reset_code = f"{secrets.randbelow(1000000):06d}"
        _reset_tokens[reset_code] = {
            "user_id": user["id"],
            "expires": time.time() + 900,  # 15 minutes
        }

        # Send reset email
        try:
            from services.email_service import email_service
            name = dict(user).get("full_name") or "User"
            email_service.send_notification(
                to_email=email,
                title="Password Reset Code",
                message=f"Hi {name},\n\nYour password reset code is:\n\n{reset_code}\n\nThis code expires in 15 minutes. If you did not request this, please ignore this email.",
                notification_type="info",
            )
        except Exception as exc:
            logger.warning("[Auth] Failed to send reset email: %s", exc)

        return jsonify({"success": True, "message": "If an account with that email exists, a reset link has been sent."}), 200
    except Exception as e:
        logger.exception("[Auth] forgot_password failed")
        return jsonify({"success": False, "error": "Failed to process request"}), 500


@auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("5 per minute")
def reset_password():
    """POST /api/auth/reset-password — reset password using the code from email."""
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    new_password = data.get("new_password", "")

    if not code or not new_password:
        return jsonify({"success": False, "error": "Reset code and new password are required"}), 400

    if len(new_password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400

    # Validate token
    token_data = _reset_tokens.get(code)
    if not token_data:
        return jsonify({"success": False, "error": "Invalid or expired reset code"}), 400

    if time.time() > token_data["expires"]:
        _reset_tokens.pop(code, None)
        return jsonify({"success": False, "error": "Reset code has expired. Please request a new one."}), 400

    try:
        db = get_db()
        password_hash = generate_password_hash(new_password)
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, token_data["user_id"]))
        db.commit()
        db.close()

        # Invalidate the token
        _reset_tokens.pop(code, None)

        return jsonify({"success": True, "message": "Password has been reset. You can now log in."}), 200
    except Exception as e:
        logger.exception("[Auth] reset_password failed")
        return jsonify({"success": False, "error": "Failed to reset password"}), 500


# ── Profile Endpoints ──────────────────────────────────────────────────────────

@auth_bp.route("/profile", methods=["GET"])
def get_profile():
    """GET /api/auth/profile — return full user profile."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    safe = {k: v for k, v in dict(user).items() if k != "password_hash"}
    return jsonify({"success": True, "user": safe}), 200


@auth_bp.route("/profile", methods=["PUT"])
def update_profile():
    """PUT /api/auth/profile — update editable profile fields."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    allowed = {"full_name", "name", "phone", "department", "sub_role", "avatar_initials"}
    updates = {k: v for k, v in data.items() if k in allowed and v is not None}

    if not updates:
        return jsonify({"success": False, "error": "No valid fields to update"}), 400

    # Keep name and full_name in sync
    if "full_name" in updates:
        updates["name"] = updates["full_name"]
        updates["avatar_initials"] = "".join(w[0].upper() for w in updates["full_name"].split()[:2])

    try:
        db = get_db()
        # Schema-tolerant: only update columns that exist
        cols = {r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()}
        valid_updates = {k: v for k, v in updates.items() if k in cols}

        if valid_updates:
            set_clause = ", ".join(f"{k} = ?" for k in valid_updates)
            values = list(valid_updates.values()) + [user["id"]]
            db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
            db.commit()

        # Bust auth cache
        from auth import _user_cache
        _user_cache.pop(user["id"], None)

        # Return updated user
        updated = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        db.close()
        safe = {k: v for k, v in dict(updated).items() if k != "password_hash"}
        return jsonify({"success": True, "user": safe}), 200
    except Exception:
        logger.exception("[Auth] update_profile failed")
        return jsonify({"success": False, "error": "Failed to update profile"}), 500


@auth_bp.route("/profile/avatar", methods=["POST"])
def upload_avatar():
    """POST /api/auth/profile/avatar — upload a profile picture."""
    import os
    from werkzeug.utils import secure_filename
    from config import Config

    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    upload = request.files.get("avatar")
    if not upload or not upload.filename:
        return jsonify({"success": False, "error": "Avatar file is required"}), 400

    ext = os.path.splitext(upload.filename)[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return jsonify({"success": False, "error": "Only image files allowed (png, jpg, gif, webp)"}), 400

    try:
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        safe_name = secure_filename(upload.filename)
        filename = f"avatar_{user['id']}_{safe_name}"
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
        upload.save(filepath)

        db = get_db()
        db.execute("UPDATE users SET profile_picture = ? WHERE id = ?", (filename, user["id"]))
        db.commit()
        db.close()

        from auth import _user_cache
        _user_cache.pop(user["id"], None)

        return jsonify({"success": True, "url": f"/api/uploads/{filename}"}), 200
    except Exception:
        logger.exception("[Auth] upload_avatar failed")
        return jsonify({"success": False, "error": "Failed to upload avatar"}), 500
