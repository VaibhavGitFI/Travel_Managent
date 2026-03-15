"""
TravelSync Pro — Authentication Routes
Handles login, logout, and current-user endpoints.
"""
from flask import Blueprint, request, jsonify, session
from auth import login_user, logout_user, get_current_user, demo_login, verify_token, generate_tokens, _get_user_by_id
from extensions import limiter

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    """POST /api/auth/login — authenticate user and start session."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username and not password:
        # Demo mode: auto-login as admin
        result = demo_login()
        return jsonify(result), 200 if result.get("success") else 401

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
