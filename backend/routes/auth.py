"""
TravelSync Pro — Authentication Routes
Handles login, logout, and current-user endpoints.
"""
from flask import Blueprint, request, jsonify, session
from auth import login_user, logout_user, get_current_user, demo_login

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
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


@auth_bp.route("/me", methods=["GET"])
def me():
    """GET /api/auth/me — return current logged-in user from session."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    # Strip password_hash before returning
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}
    return jsonify({"success": True, "user": safe_user}), 200
