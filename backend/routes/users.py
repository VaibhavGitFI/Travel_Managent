"""
TravelSync Pro — User Management Routes
Super admin only: list users, change roles, view user details.
"""
import logging
from flask import Blueprint, request, jsonify
from auth import get_current_user, super_admin_required, _user_cache
from database import get_db
from extensions import limiter

logger = logging.getLogger(__name__)

users_bp = Blueprint("users", __name__, url_prefix="/api/users")

VALID_ROLES = {"employee", "manager", "admin", "super_admin"}


@users_bp.route("", methods=["GET"])
@super_admin_required
def list_users():
    """GET /api/users — list all users (super_admin only)."""
    role_filter = request.args.get("role")
    search = request.args.get("search", "").strip()

    try:
        db = get_db()
        query = "SELECT id, username, name, full_name, email, role, department, sub_role, phone, profile_picture, email_verified, created_at FROM users"
        params = []
        conditions = []

        if role_filter and role_filter in VALID_ROLES:
            conditions.append("role = ?")
            params.append(role_filter)

        if search:
            conditions.append("(name LIKE ? OR email LIKE ? OR username LIKE ?)")
            params.extend([f"%{search}%"] * 3)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC"
        rows = db.execute(query, params).fetchall()
        db.close()

        users = [dict(r) for r in rows]
        return jsonify({"success": True, "users": users, "total": len(users)}), 200
    except Exception:
        logger.exception("[Users] list failed")
        return jsonify({"success": False, "error": "Failed to list users"}), 500


@users_bp.route("/<int:user_id>", methods=["GET"])
@super_admin_required
def get_user(user_id):
    """GET /api/users/:id — get single user detail."""
    try:
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        db.close()
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404
        safe = {k: v for k, v in dict(user).items() if k != "password_hash"}
        return jsonify({"success": True, "user": safe}), 200
    except Exception:
        logger.exception("[Users] get user failed")
        return jsonify({"success": False, "error": "Failed to get user"}), 500


@users_bp.route("/<int:user_id>/role", methods=["PUT"])
@limiter.limit("10 per minute")
@super_admin_required
def update_role(user_id):
    """PUT /api/users/:id/role — change a user's role (super_admin only)."""
    current_user = get_current_user()
    if current_user["id"] == user_id:
        return jsonify({"success": False, "error": "Cannot change your own role"}), 400

    data = request.get_json(silent=True) or {}
    new_role = data.get("role", "").strip()

    if new_role not in VALID_ROLES:
        return jsonify({"success": False, "error": f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}"}), 400

    try:
        db = get_db()
        user = db.execute("SELECT id, name, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            db.close()
            return jsonify({"success": False, "error": "User not found"}), 404

        old_role = dict(user)["role"]
        db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        db.commit()
        db.close()

        # Bust cache
        _user_cache.pop(user_id, None)

        return jsonify({
            "success": True,
            "message": f"Role updated: {old_role} → {new_role}",
            "user_id": user_id,
            "old_role": old_role,
            "new_role": new_role,
        }), 200
    except Exception:
        logger.exception("[Users] role update failed")
        return jsonify({"success": False, "error": "Failed to update role"}), 500


@users_bp.route("/<int:user_id>/verify", methods=["POST"])
@limiter.limit("10 per minute")
@super_admin_required
def verify_user(user_id):
    """POST /api/users/:id/verify — manually verify a user's email (super_admin only)."""
    try:
        db = get_db()
        user = db.execute("SELECT id, email, email_verified FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            db.close()
            return jsonify({"success": False, "error": "User not found"}), 404

        db.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))
        db.commit()
        db.close()
        _user_cache.pop(user_id, None)
        return jsonify({"success": True, "message": "User email verified"}), 200
    except Exception:
        logger.exception("[Users] verify user failed")
        return jsonify({"success": False, "error": "Failed to verify user"}), 500
