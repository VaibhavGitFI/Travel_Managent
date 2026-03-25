"""
TravelSync Pro — Expense Approval Routes
Adds approval workflow on top of existing expense CRUD (which stays untouched).
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from auth import get_current_user
from database import get_db

logger = logging.getLogger(__name__)

expense_approvals_bp = Blueprint("expense_approvals", __name__, url_prefix="/api/expenses")

_APPROVER_ROLES = ("manager", "admin", "super_admin")


def _find_approver(db, user):
    """Find the appropriate approver for an employee's expense."""
    # 1. Use the employee's assigned manager_id if set
    manager_id = user.get("manager_id")
    if manager_id:
        mgr = db.execute("SELECT id, role FROM users WHERE id = ?", (manager_id,)).fetchone()
        if mgr:
            return mgr["id"]

    # 2. Find first manager/admin in the same department
    dept = user.get("department")
    if dept:
        mgr = db.execute(
            "SELECT id FROM users WHERE role IN ('manager', 'admin', 'super_admin') AND department = ? AND id != ? LIMIT 1",
            (dept, user["id"]),
        ).fetchone()
        if mgr:
            return mgr["id"]

    # 3. Fallback: first manager/admin in the system
    mgr = db.execute(
        "SELECT id FROM users WHERE role IN ('manager', 'admin', 'super_admin') AND id != ? LIMIT 1",
        (user["id"],),
    ).fetchone()
    return mgr["id"] if mgr else None


@expense_approvals_bp.route("/<int:expense_id>/submit", methods=["POST"])
def submit_expense(expense_id):
    """POST /api/expenses/:id/submit — submit an expense for approval."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        db = get_db()
        expense = db.execute("SELECT * FROM expenses_db WHERE id = ?", (expense_id,)).fetchone()
        if not expense:
            db.close()
            return jsonify({"success": False, "error": "Expense not found"}), 404

        exp = dict(expense)
        if exp["user_id"] != user["id"] and user["role"] not in _APPROVER_ROLES:
            db.close()
            return jsonify({"success": False, "error": "Not authorized"}), 403

        status = exp.get("approval_status", "draft")
        if status not in ("draft", "rejected", None, ""):
            db.close()
            return jsonify({"success": False, "error": f"Cannot submit expense with status '{status}'"}), 400

        approver_id = _find_approver(db, user)
        if not approver_id:
            db.close()
            return jsonify({"success": False, "error": "No approver available. Contact your admin."}), 400

        now = datetime.utcnow().isoformat()
        db.execute(
            "UPDATE expenses_db SET approval_status = 'submitted', approver_id = ?, submitted_at = ?, approval_comments = NULL WHERE id = ?",
            (approver_id, now, expense_id),
        )
        db.commit()
        db.close()

        # Notify the approver
        try:
            from services.notification_service import notify
            amt = exp.get("verified_amount") or exp.get("invoice_amount") or exp.get("payment_amount") or 0
            notify(
                user_id=approver_id,
                title="New Expense for Approval",
                message=f"{user.get('full_name') or user.get('name', 'An employee')} submitted an expense of ₹{int(amt):,} for your approval.",
                notification_type="expense_submitted",
                action_url="/approvals",
                details={"Category": exp.get("category", ""), "Amount": f"₹{int(amt):,}", "Description": exp.get("description", "")},
            )
        except Exception:
            pass

        return jsonify({"success": True, "message": "Expense submitted for approval", "approver_id": approver_id}), 200
    except Exception:
        logger.exception("[ExpenseApproval] submit failed")
        return jsonify({"success": False, "error": "Failed to submit expense"}), 500


@expense_approvals_bp.route("/<int:expense_id>/approve", methods=["POST"])
def approve_expense(expense_id):
    """POST /api/expenses/:id/approve — approve an expense."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    if user["role"] not in _APPROVER_ROLES:
        return jsonify({"success": False, "error": "Manager or admin access required"}), 403

    try:
        db = get_db()
        expense = db.execute("SELECT * FROM expenses_db WHERE id = ?", (expense_id,)).fetchone()
        if not expense:
            db.close()
            return jsonify({"success": False, "error": "Expense not found"}), 404

        exp = dict(expense)
        if exp.get("approval_status") != "submitted":
            db.close()
            return jsonify({"success": False, "error": "Expense is not pending approval"}), 400

        # Only assigned approver or super_admin can approve
        if exp.get("approver_id") != user["id"] and user["role"] != "super_admin":
            db.close()
            return jsonify({"success": False, "error": "Not assigned as approver"}), 403

        data = request.get_json(silent=True) or {}
        now = datetime.utcnow().isoformat()
        db.execute(
            "UPDATE expenses_db SET approval_status = 'approved', approved_at = ?, approval_comments = ? WHERE id = ?",
            (now, data.get("comments", ""), expense_id),
        )
        db.commit()

        # Notify the expense owner
        try:
            from services.notification_service import notify
            amt = exp.get("verified_amount") or exp.get("invoice_amount") or exp.get("payment_amount") or 0
            notify(
                user_id=exp["user_id"],
                title="Expense Approved ✅",
                message=f"Your expense of ₹{int(amt):,} ({exp.get('category', '')}) has been approved.",
                notification_type="expense_approved",
                action_url="/expenses",
            )
            from extensions import socketio
            socketio.emit("data_changed", {"entity": "expenses"}, namespace="/")
        except Exception:
            pass

        db.close()
        return jsonify({"success": True, "message": "Expense approved"}), 200
    except Exception:
        logger.exception("[ExpenseApproval] approve failed")
        return jsonify({"success": False, "error": "Failed to approve expense"}), 500


@expense_approvals_bp.route("/<int:expense_id>/reject", methods=["POST"])
def reject_expense(expense_id):
    """POST /api/expenses/:id/reject — reject an expense with reason."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    if user["role"] not in _APPROVER_ROLES:
        return jsonify({"success": False, "error": "Manager or admin access required"}), 403

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        return jsonify({"success": False, "error": "Rejection reason is required"}), 400

    try:
        db = get_db()
        expense = db.execute("SELECT * FROM expenses_db WHERE id = ?", (expense_id,)).fetchone()
        if not expense:
            db.close()
            return jsonify({"success": False, "error": "Expense not found"}), 404

        exp = dict(expense)
        if exp.get("approval_status") != "submitted":
            db.close()
            return jsonify({"success": False, "error": "Expense is not pending approval"}), 400

        if exp.get("approver_id") != user["id"] and user["role"] != "super_admin":
            db.close()
            return jsonify({"success": False, "error": "Not assigned as approver"}), 403

        now = datetime.utcnow().isoformat()
        db.execute(
            "UPDATE expenses_db SET approval_status = 'rejected', approved_at = ?, approval_comments = ? WHERE id = ?",
            (now, reason, expense_id),
        )
        db.commit()

        # Notify the expense owner
        try:
            from services.notification_service import notify
            amt = exp.get("verified_amount") or exp.get("invoice_amount") or exp.get("payment_amount") or 0
            notify(
                user_id=exp["user_id"],
                title="Expense Rejected ❌",
                message=f"Your expense of ₹{int(amt):,} ({exp.get('category', '')}) was rejected. Reason: {reason}",
                notification_type="expense_rejected",
                action_url="/expenses",
            )
            from extensions import socketio
            socketio.emit("data_changed", {"entity": "expenses"}, namespace="/")
        except Exception:
            pass

        db.close()
        return jsonify({"success": True, "message": "Expense rejected"}), 200
    except Exception:
        logger.exception("[ExpenseApproval] reject failed")
        return jsonify({"success": False, "error": "Failed to reject expense"}), 500


@expense_approvals_bp.route("/pending-approvals", methods=["GET"])
def pending_expense_approvals():
    """GET /api/expenses/pending-approvals — list expenses awaiting this user's approval."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    if user["role"] not in _APPROVER_ROLES:
        return jsonify({"success": False, "error": "Manager or admin access required"}), 403

    try:
        db = get_db()
        if user["role"] == "super_admin":
            rows = db.execute(
                """SELECT e.*, u.name as employee_name, u.department as employee_dept
                   FROM expenses_db e JOIN users u ON e.user_id = u.id
                   WHERE e.approval_status = 'submitted'
                   ORDER BY e.submitted_at DESC""",
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT e.*, u.name as employee_name, u.department as employee_dept
                   FROM expenses_db e JOIN users u ON e.user_id = u.id
                   WHERE e.approval_status = 'submitted' AND e.approver_id = ?
                   ORDER BY e.submitted_at DESC""",
                (user["id"],),
            ).fetchall()
        db.close()

        expenses = []
        for r in rows:
            exp = dict(r)
            exp["amount"] = exp.get("verified_amount") or exp.get("invoice_amount") or exp.get("payment_amount") or 0
            expenses.append(exp)

        return jsonify({"success": True, "expenses": expenses, "total": len(expenses)}), 200
    except Exception:
        logger.exception("[ExpenseApproval] pending list failed")
        return jsonify({"success": True, "expenses": [], "total": 0}), 200
