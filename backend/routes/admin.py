"""
TravelSync Pro — Super Admin Platform Management Routes
Platform-wide oversight: all orgs, plans, status, usage stats.
Only accessible to super_admin role.
"""
import json
import logging
from flask import Blueprint, request, jsonify
from auth import get_current_user, super_admin_required
from database import get_db
from extensions import limiter
from services.audit_service import log_action

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

VALID_PLANS = {"free", "starter", "pro", "enterprise"}
VALID_STATUSES = {"active", "inactive", "suspended", "trial"}

# Features available per plan
PLAN_FEATURES = {
    "free": {
        "max_members": 5, "max_requests_month": 20,
        "ai_chat": True, "ocr": False, "webhooks": False, "api_access": False,
        "priority_support": False, "custom_policies": False,
    },
    "starter": {
        "max_members": 25, "max_requests_month": 100,
        "ai_chat": True, "ocr": True, "webhooks": False, "api_access": False,
        "priority_support": False, "custom_policies": True,
    },
    "pro": {
        "max_members": 100, "max_requests_month": 500,
        "ai_chat": True, "ocr": True, "webhooks": True, "api_access": True,
        "priority_support": True, "custom_policies": True,
    },
    "enterprise": {
        "max_members": 9999, "max_requests_month": 99999,
        "ai_chat": True, "ocr": True, "webhooks": True, "api_access": True,
        "priority_support": True, "custom_policies": True,
    },
}


# ── Platform Stats ────────────────────────────────────────────────────────────

@admin_bp.route("/stats", methods=["GET"])
@limiter.limit("30 per minute")
@super_admin_required
def platform_stats():
    """GET /api/admin/stats — platform-wide KPIs for super admin dashboard."""
    db = get_db()
    try:
        stats = {}

        # Org counts
        row = db.execute("SELECT COUNT(*) as cnt FROM organizations").fetchone()
        stats["total_orgs"] = _val(row, "cnt")

        row = db.execute("SELECT COUNT(*) as cnt FROM organizations WHERE status = 'active'").fetchone()
        stats["active_orgs"] = _val(row, "cnt")

        # Plan distribution
        rows = db.execute(
            "SELECT plan, COUNT(*) as cnt FROM organizations GROUP BY plan ORDER BY cnt DESC"
        ).fetchall()
        stats["orgs_by_plan"] = {_val(r, "plan") or "free": _val(r, "cnt") for r in rows}

        # User counts
        row = db.execute("SELECT COUNT(*) as cnt FROM users").fetchone()
        stats["total_users"] = _val(row, "cnt")

        row = db.execute("SELECT COUNT(*) as cnt FROM users WHERE email_verified = 1").fetchone()
        stats["verified_users"] = _val(row, "cnt")

        # Role distribution
        rows = db.execute(
            "SELECT role, COUNT(*) as cnt FROM users GROUP BY role ORDER BY cnt DESC"
        ).fetchall()
        stats["users_by_role"] = {_val(r, "role") or "employee": _val(r, "cnt") for r in rows}

        # Travel requests
        row = db.execute("SELECT COUNT(*) as cnt FROM travel_requests").fetchone()
        stats["total_requests"] = _val(row, "cnt")

        rows = db.execute(
            "SELECT status, COUNT(*) as cnt FROM travel_requests GROUP BY status ORDER BY cnt DESC"
        ).fetchall()
        stats["requests_by_status"] = {_val(r, "status") or "draft": _val(r, "cnt") for r in rows}

        # Expenses
        row = db.execute("SELECT COUNT(*) as cnt FROM expenses_db").fetchone()
        stats["total_expenses"] = _val(row, "cnt")

        row = db.execute("SELECT COALESCE(SUM(invoice_amount), 0) as total FROM expenses_db").fetchone()
        stats["total_expense_amount"] = round(float(_val(row, "total")), 2)

        # Meetings
        row = db.execute("SELECT COUNT(*) as cnt FROM client_meetings").fetchone()
        stats["total_meetings"] = _val(row, "cnt")

        # SOS events
        row = db.execute("SELECT COUNT(*) as cnt FROM sos_events").fetchone()
        stats["total_sos_events"] = _val(row, "cnt")

        # Available plans
        stats["available_plans"] = list(PLAN_FEATURES.keys())

        db.close()
        return jsonify({"success": True, "stats": stats}), 200

    except Exception as e:
        logger.exception("[Admin] platform_stats failed")
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to load platform stats"}), 500


# ── Organization Management ───────────────────────────────────────────────────

@admin_bp.route("/orgs", methods=["GET"])
@limiter.limit("30 per minute")
@super_admin_required
def list_all_orgs():
    """GET /api/admin/orgs — list all organizations with member counts and usage."""
    db = get_db()
    try:
        search = (request.args.get("search") or "").strip().lower()
        status_filter = request.args.get("status", "").strip()
        plan_filter = request.args.get("plan", "").strip()

        orgs = db.execute("""
            SELECT o.*,
                   (SELECT COUNT(*) FROM org_members om WHERE om.org_id = o.id) as member_count,
                   (SELECT COUNT(*) FROM travel_requests tr WHERE tr.org_id = o.id) as request_count,
                   (SELECT COUNT(*) FROM expenses_db e WHERE e.org_id = o.id) as expense_count
            FROM organizations o
            ORDER BY o.created_at DESC
        """).fetchall()

        result = []
        for org in orgs:
            o = dict(org)
            # Apply filters
            if status_filter and o.get("status") != status_filter:
                continue
            if plan_filter and o.get("plan") != plan_filter:
                continue
            if search and search not in (o.get("name") or "").lower() and search not in (o.get("slug") or "").lower():
                continue

            # Get the org owner
            owner = db.execute("""
                SELECT u.id, u.full_name, u.email FROM org_members om
                JOIN users u ON om.user_id = u.id
                WHERE om.org_id = ? AND om.org_role = 'org_owner' LIMIT 1
            """, (o["id"],)).fetchone()
            o["owner"] = dict(owner) if owner else None
            o["plan_features"] = PLAN_FEATURES.get(o.get("plan", "free"), PLAN_FEATURES["free"])

            result.append(o)

        db.close()
        return jsonify({
            "success": True,
            "organizations": result,
            "total": len(result),
            "available_plans": list(PLAN_FEATURES.keys()),
            "available_statuses": list(VALID_STATUSES),
        }), 200

    except Exception as e:
        logger.exception("[Admin] list_all_orgs failed")
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to load organizations"}), 500


@admin_bp.route("/orgs/<int:org_id>", methods=["GET"])
@limiter.limit("30 per minute")
@super_admin_required
def get_org_detail(org_id):
    """GET /api/admin/orgs/:id — full detail for a single organization."""
    db = get_db()
    try:
        org = db.execute("SELECT * FROM organizations WHERE id = ?", (org_id,)).fetchone()
        if not org:
            db.close()
            return jsonify({"success": False, "error": "Organization not found"}), 404

        o = dict(org)

        # Members
        members = db.execute("""
            SELECT om.org_role, om.joined_at,
                   u.id as user_id, u.full_name, u.email, u.role, u.department, u.avatar_initials
            FROM org_members om
            JOIN users u ON om.user_id = u.id
            WHERE om.org_id = ?
            ORDER BY om.joined_at ASC
        """, (org_id,)).fetchall()
        o["members"] = [dict(m) for m in members]
        o["member_count"] = len(o["members"])

        # Usage stats
        row = db.execute("SELECT COUNT(*) as cnt FROM travel_requests WHERE org_id = ?", (org_id,)).fetchone()
        o["request_count"] = _val(row, "cnt")

        row = db.execute("SELECT COUNT(*) as cnt FROM expenses_db WHERE org_id = ?", (org_id,)).fetchone()
        o["expense_count"] = _val(row, "cnt")

        row = db.execute("SELECT COALESCE(SUM(invoice_amount), 0) as total FROM expenses_db WHERE org_id = ?", (org_id,)).fetchone()
        o["total_spend"] = round(float(_val(row, "total")), 2)

        row = db.execute("SELECT COUNT(*) as cnt FROM client_meetings WHERE org_id = ?", (org_id,)).fetchone()
        o["meeting_count"] = _val(row, "cnt")

        # Plan features
        o["plan_features"] = PLAN_FEATURES.get(o.get("plan", "free"), PLAN_FEATURES["free"])

        # Policies
        policies = db.execute("SELECT * FROM travel_policies WHERE org_id = ?", (org_id,)).fetchall()
        o["policies"] = [dict(p) for p in policies]

        db.close()
        return jsonify({"success": True, "organization": o}), 200

    except Exception as e:
        logger.exception("[Admin] get_org_detail failed for %s", org_id)
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to load organization"}), 500


@admin_bp.route("/orgs/<int:org_id>", methods=["PUT"])
@limiter.limit("10 per minute")
@super_admin_required
def update_org(org_id):
    """PUT /api/admin/orgs/:id — update org plan, status, limits, notes."""
    user = get_current_user()
    data = request.get_json(silent=True) or {}

    db = get_db()
    try:
        org = db.execute("SELECT * FROM organizations WHERE id = ?", (org_id,)).fetchone()
        if not org:
            db.close()
            return jsonify({"success": False, "error": "Organization not found"}), 404

        before = dict(org)
        updates = {}
        allowed_fields = {"name", "plan", "status", "max_members", "billing_email", "notes", "features_json"}

        for field in allowed_fields:
            if field in data and data[field] is not None:
                updates[field] = data[field]

        # Validate plan
        if "plan" in updates and updates["plan"] not in VALID_PLANS:
            db.close()
            return jsonify({"success": False, "error": f"Invalid plan. Must be: {', '.join(sorted(VALID_PLANS))}"}), 400

        # Validate status
        if "status" in updates and updates["status"] not in VALID_STATUSES:
            db.close()
            return jsonify({"success": False, "error": f"Invalid status. Must be: {', '.join(sorted(VALID_STATUSES))}"}), 400

        # Apply plan defaults for max_members if plan changed
        if "plan" in updates and "max_members" not in updates:
            plan_config = PLAN_FEATURES.get(updates["plan"], {})
            if plan_config.get("max_members"):
                updates["max_members"] = plan_config["max_members"]

        if not updates:
            db.close()
            return jsonify({"success": False, "error": "No valid fields to update"}), 400

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [org_id]
        db.execute(f"UPDATE organizations SET {set_clause} WHERE id = ?", values)
        db.commit()

        # Fetch updated
        updated = db.execute("SELECT * FROM organizations WHERE id = ?", (org_id,)).fetchone()
        db.close()

        # Audit log
        log_action(
            action="update_org",
            entity="organizations",
            entity_id=str(org_id),
            actor_id=user["id"] if user else None,
            before=before,
            after=dict(updated) if updated else updates,
        )

        return jsonify({
            "success": True,
            "organization": dict(updated) if updated else {},
            "message": f"Organization updated: {', '.join(updates.keys())}",
        }), 200

    except Exception as e:
        logger.exception("[Admin] update_org failed for %s", org_id)
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to update organization"}), 500


@admin_bp.route("/orgs/<int:org_id>/activate", methods=["POST"])
@limiter.limit("10 per minute")
@super_admin_required
def activate_org(org_id):
    """POST /api/admin/orgs/:id/activate — set org status to active."""
    return _set_org_status(org_id, "active")


@admin_bp.route("/orgs/<int:org_id>/deactivate", methods=["POST"])
@limiter.limit("10 per minute")
@super_admin_required
def deactivate_org(org_id):
    """POST /api/admin/orgs/:id/deactivate — set org status to inactive."""
    return _set_org_status(org_id, "inactive")


@admin_bp.route("/orgs/<int:org_id>/suspend", methods=["POST"])
@limiter.limit("10 per minute")
@super_admin_required
def suspend_org(org_id):
    """POST /api/admin/orgs/:id/suspend — suspend org (blocks all member access)."""
    return _set_org_status(org_id, "suspended")


def _set_org_status(org_id: int, new_status: str):
    """Shared logic for status changes."""
    user = get_current_user()
    db = get_db()
    try:
        org = db.execute("SELECT id, name, status FROM organizations WHERE id = ?", (org_id,)).fetchone()
        if not org:
            db.close()
            return jsonify({"success": False, "error": "Organization not found"}), 404

        old_status = dict(org).get("status", "unknown")
        db.execute("UPDATE organizations SET status = ? WHERE id = ?", (new_status, org_id))
        db.commit()
        db.close()

        log_action(
            action=f"org_{new_status}",
            entity="organizations",
            entity_id=str(org_id),
            actor_id=user["id"] if user else None,
            details={"old_status": old_status, "new_status": new_status},
        )

        return jsonify({
            "success": True,
            "message": f"Organization '{dict(org)['name']}' is now {new_status}",
            "status": new_status,
        }), 200

    except Exception as e:
        logger.exception("[Admin] _set_org_status failed for %s", org_id)
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": "Failed to update status"}), 500


@admin_bp.route("/plans", methods=["GET"])
@super_admin_required
def list_plans():
    """GET /api/admin/plans — list all available plans with features."""
    return jsonify({
        "success": True,
        "plans": {name: {**features, "name": name} for name, features in PLAN_FEATURES.items()},
    }), 200


# ── Helpers ───────────────────────────────────────────────────────────────────

def _val(row, key):
    """Safely extract a value from a sqlite3.Row or dict."""
    if row is None:
        return 0
    if isinstance(row, dict):
        return row.get(key, 0)
    try:
        return row[key]
    except (KeyError, IndexError):
        try:
            return row[0]
        except Exception:
            return 0
