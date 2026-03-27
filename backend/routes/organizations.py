"""
TravelSync Pro — Organization Routes
Create orgs, manage members, org settings, invite flow.
"""
import re
import logging
from flask import Blueprint, request, jsonify
from auth import (get_current_user, get_current_org, org_required,
                  org_admin_required, get_user_org, invalidate_org_cache,
                  generate_tokens, generate_csrf_token)
from database import get_db
from extensions import limiter
from validators import ValidationError, validate_string, validate_email

logger = logging.getLogger(__name__)

orgs_bp = Blueprint("organizations", __name__, url_prefix="/api/orgs")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$")
_ORG_ROLES = {"org_owner", "org_admin", "org_manager", "member"}


def _slugify(name: str) -> str:
    """Generate a URL-safe slug from an org name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50]
    return slug or "org"


# ── Org CRUD ──────────────────────────────────────────────────────────────────

@orgs_bp.route("", methods=["POST"])
@limiter.limit("5 per minute")
def create_org():
    """POST /api/orgs — create a new organization. Creator becomes org_owner."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    try:
        name = validate_string(data, "name", min_len=2, max_len=100)
    except ValidationError as e:
        return jsonify({"success": False, "error": e.message}), 400

    slug = data.get("slug") or _slugify(name)
    if not _SLUG_RE.match(slug):
        return jsonify({"success": False, "error": "Slug must be 3-50 lowercase alphanumeric characters with hyphens"}), 400

    db = get_db()
    try:
        # Check slug uniqueness
        existing = db.execute("SELECT id FROM organizations WHERE slug = ?", (slug,)).fetchone()
        if existing:
            return jsonify({"success": False, "error": f"Organization slug '{slug}' is already taken"}), 409

        # Check if user already owns an org
        existing_membership = get_user_org(user["id"])
        if existing_membership and existing_membership.get("org_role") == "org_owner":
            db.close()
            return jsonify({"success": False, "error": "You already own an organization"}), 409

        # Create org
        db.execute(
            """INSERT INTO organizations (name, slug, billing_email, plan)
               VALUES (?, ?, ?, 'free')""",
            (name, slug, user.get("email", "")),
        )
        db.commit()
        org = db.execute("SELECT * FROM organizations WHERE slug = ?", (slug,)).fetchone()

        if not org:
            db.close()
            return jsonify({"success": False, "error": "Failed to create organization"}), 500

        org_id = org["id"]

        # Add creator as org_owner
        db.execute(
            """INSERT INTO org_members (org_id, user_id, org_role, department)
               VALUES (?, ?, 'org_owner', ?)""",
            (org_id, user["id"], user.get("department", "General")),
        )

        # Create default travel policy for the org
        db.execute(
            """INSERT INTO travel_policies
               (org_id, name, flight_class, hotel_budget_per_night, max_trip_duration_days,
                advance_booking_days, per_diem_inr, monthly_budget_inr, auto_approve_threshold)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (org_id, f"{name} Travel Policy", "economy", 8000, 30, 3, 2500, 500000, 15000),
        )
        db.commit()
        db.close()

        # Bust caches
        invalidate_org_cache(user["id"])
        from auth import _user_cache
        _user_cache.pop(user["id"], None)

        return jsonify({
            "success": True,
            "organization": {
                "id": org_id,
                "name": name,
                "slug": slug,
                "plan": "free",
            },
            "message": f"Organization '{name}' created. You are the owner.",
        }), 201

    except Exception as e:
        logger.exception("[Orgs] create_org failed")
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to create organization"}), 500


@orgs_bp.route("/me", methods=["GET"])
def get_my_org():
    """GET /api/orgs/me — get current user's organization."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    membership = get_user_org(user["id"])
    if not membership:
        return jsonify({"success": True, "organization": None, "message": "Not a member of any organization"}), 200

    db = get_db()
    try:
        org = db.execute("SELECT * FROM organizations WHERE id = ?", (membership["org_id"],)).fetchone()
        member_count = db.execute(
            "SELECT COUNT(*) as cnt FROM org_members WHERE org_id = ?",
            (membership["org_id"],)
        ).fetchone()
        db.close()

        if not org:
            return jsonify({"success": True, "organization": None}), 200

        org_data = dict(org)
        org_data["member_count"] = member_count["cnt"] if isinstance(member_count, dict) else member_count[0]
        org_data["my_role"] = membership.get("org_role", "member")

        return jsonify({"success": True, "organization": org_data}), 200
    except Exception as e:
        logger.exception("[Orgs] get_my_org failed")
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to load organization"}), 500


@orgs_bp.route("/settings", methods=["PUT"])
@limiter.limit("10 per minute")
def update_org_settings():
    """PUT /api/orgs/settings — update org name, billing email, settings."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    org = get_current_org()
    if not org:
        return jsonify({"success": False, "error": "Organization membership required"}), 403
    if org.get("org_role") not in ("org_owner", "org_admin"):
        return jsonify({"success": False, "error": "Organization admin access required"}), 403

    data = request.get_json(silent=True) or {}
    allowed = {"name", "billing_email", "settings_json", "logo_url"}
    updates = {k: v for k, v in data.items() if k in allowed and v is not None}

    if not updates:
        return jsonify({"success": False, "error": "No valid fields to update"}), 400

    db = get_db()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [org["org_id"]]
        db.execute(f"UPDATE organizations SET {set_clause} WHERE id = ?", values)
        db.commit()
        db.close()
        return jsonify({"success": True, "message": "Organization settings updated"}), 200
    except Exception as e:
        logger.exception("[Orgs] update_org_settings failed")
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to update settings"}), 500


# ── Members ───────────────────────────────────────────────────────────────────

@orgs_bp.route("/members", methods=["GET"])
def list_members():
    """GET /api/orgs/members — list organization members."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    org = get_current_org()
    if not org:
        return jsonify({"success": False, "error": "Organization membership required"}), 403

    db = get_db()
    try:
        rows = db.execute("""
            SELECT om.id as membership_id, om.org_role, om.department, om.joined_at,
                   u.id as user_id, u.username, u.full_name, u.email,
                   u.avatar_initials, u.profile_picture, u.phone
            FROM org_members om
            JOIN users u ON om.user_id = u.id
            WHERE om.org_id = ?
            ORDER BY om.joined_at ASC
        """, (org["org_id"],)).fetchall()
        db.close()
        return jsonify({"success": True, "members": [dict(r) for r in rows]}), 200
    except Exception as e:
        logger.exception("[Orgs] list_members failed")
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to load members"}), 500


@orgs_bp.route("/invite", methods=["POST"])
@limiter.limit("10 per minute")
def invite_member():
    """POST /api/orgs/invite — invite a user to the org by email."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    org = get_current_org()
    if not org:
        return jsonify({"success": False, "error": "Organization membership required"}), 403
    if org.get("org_role") not in ("org_owner", "org_admin"):
        return jsonify({"success": False, "error": "Only org admins can invite members"}), 403

    data = request.get_json(silent=True) or {}
    try:
        email = validate_email(data)
    except ValidationError as e:
        return jsonify({"success": False, "error": e.message}), 400

    role = data.get("role", "member")
    if role not in _ORG_ROLES:
        return jsonify({"success": False, "error": f"Invalid role. Must be one of: {', '.join(sorted(_ORG_ROLES))}"}), 400

    # Can't invite as org_owner
    if role == "org_owner":
        return jsonify({"success": False, "error": "Cannot invite as org_owner. Transfer ownership instead."}), 400

    db = get_db()
    try:
        # Find user by email
        target = db.execute("SELECT id, full_name FROM users WHERE email = ?", (email,)).fetchone()
        if not target:
            db.close()
            return jsonify({"success": False, "error": "No user found with that email. They must register first."}), 404

        # Check if already a member
        existing = db.execute(
            "SELECT id FROM org_members WHERE org_id = ? AND user_id = ?",
            (org["org_id"], target["id"])
        ).fetchone()
        if existing:
            db.close()
            return jsonify({"success": False, "error": "User is already a member of this organization"}), 409

        # Check member limit
        org_row = db.execute("SELECT max_members FROM organizations WHERE id = ?", (org["org_id"],)).fetchone()
        count = db.execute("SELECT COUNT(*) as cnt FROM org_members WHERE org_id = ?", (org["org_id"],)).fetchone()
        current_count = count["cnt"] if isinstance(count, dict) else count[0]
        max_members = (org_row["max_members"] if isinstance(org_row, dict) else org_row[0]) if org_row else 50
        if current_count >= max_members:
            db.close()
            return jsonify({"success": False, "error": f"Organization has reached the member limit ({max_members})"}), 403

        # Add member
        department = data.get("department") or target.get("department", "General") if isinstance(target, dict) else "General"
        db.execute(
            """INSERT INTO org_members (org_id, user_id, org_role, department, invited_by)
               VALUES (?, ?, ?, ?, ?)""",
            (org["org_id"], target["id"], role, department, user["id"]),
        )
        db.commit()
        db.close()

        invalidate_org_cache(target["id"])

        # Send notification
        try:
            from services.notification_service import notify
            membership = get_user_org(user["id"])
            org_name = membership.get("org_name", "an organization") if membership else "an organization"
            notify(
                user_id=target["id"],
                title="Organization Invite",
                message=f"You've been added to {org_name} as {role.replace('_', ' ')}.",
                notification_type="org_invite",
                action_url="/profile",
            )
        except Exception:
            pass

        return jsonify({
            "success": True,
            "message": f"Invited {target.get('full_name', email)} as {role.replace('_', ' ')}",
        }), 201

    except Exception as e:
        logger.exception("[Orgs] invite_member failed")
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to invite member"}), 500


@orgs_bp.route("/members/<int:member_user_id>/role", methods=["PUT"])
@limiter.limit("10 per minute")
def update_member_role(member_user_id):
    """PUT /api/orgs/members/:id/role — change a member's org role."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    org = get_current_org()
    if not org:
        return jsonify({"success": False, "error": "Organization membership required"}), 403
    if org.get("org_role") not in ("org_owner", "org_admin"):
        return jsonify({"success": False, "error": "Only org admins can change roles"}), 403

    data = request.get_json(silent=True) or {}
    new_role = data.get("role", "")
    if new_role not in _ORG_ROLES or new_role == "org_owner":
        return jsonify({"success": False, "error": "Invalid role"}), 400

    # Can't change own role
    if member_user_id == user["id"]:
        return jsonify({"success": False, "error": "Cannot change your own role"}), 400

    db = get_db()
    try:
        db.execute(
            "UPDATE org_members SET org_role = ? WHERE org_id = ? AND user_id = ?",
            (new_role, org["org_id"], member_user_id),
        )
        db.commit()
        db.close()
        invalidate_org_cache(member_user_id)
        return jsonify({"success": True, "message": f"Role updated to {new_role.replace('_', ' ')}"}), 200
    except Exception as e:
        logger.exception("[Orgs] update_member_role failed")
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to update role"}), 500


@orgs_bp.route("/members/<int:member_user_id>", methods=["DELETE"])
@limiter.limit("10 per minute")
def remove_member(member_user_id):
    """DELETE /api/orgs/members/:id — remove a member from the org."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    org = get_current_org()
    if not org:
        return jsonify({"success": False, "error": "Organization membership required"}), 403

    # Only org_owner/org_admin can remove others; any member can remove self
    if member_user_id != user["id"] and org.get("org_role") not in ("org_owner", "org_admin"):
        return jsonify({"success": False, "error": "Only org admins can remove members"}), 403

    # Can't remove the org_owner
    if member_user_id != user["id"]:
        db = get_db()
        target_membership = db.execute(
            "SELECT org_role FROM org_members WHERE org_id = ? AND user_id = ?",
            (org["org_id"], member_user_id)
        ).fetchone()
        if target_membership and dict(target_membership).get("org_role") == "org_owner":
            db.close()
            return jsonify({"success": False, "error": "Cannot remove the organization owner"}), 403
        db.close()

    db = get_db()
    try:
        db.execute(
            "DELETE FROM org_members WHERE org_id = ? AND user_id = ?",
            (org["org_id"], member_user_id),
        )
        db.commit()
        db.close()
        invalidate_org_cache(member_user_id)
        return jsonify({"success": True, "message": "Member removed"}), 200
    except Exception as e:
        logger.exception("[Orgs] remove_member failed")
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to remove member"}), 500
