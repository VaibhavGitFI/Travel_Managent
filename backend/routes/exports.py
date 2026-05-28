"""
TravelSync Pro — PDF Export Routes
Generate and download PDF reports for trips and expenses.
"""
import logging
from flask import Blueprint, jsonify, make_response
from auth import get_current_user, get_current_org
from extensions import limiter

logger = logging.getLogger(__name__)

exports_bp = Blueprint("exports", __name__, url_prefix="/api/export")


@exports_bp.route("/trip/<string:request_id>/pdf", methods=["GET"])
@limiter.limit("10 per minute")
def export_trip_pdf(request_id):
    """GET /api/export/trip/:id/pdf — download trip report as PDF."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        from agents.request_agent import get_request_detail
        detail = get_request_detail(request_id)
        if not detail:
            return jsonify({"success": False, "error": "Request not found"}), 404

        req = detail.get("request", {})
        # Verify access: own request or admin
        if req.get("user_id") != user["id"] and user.get("role") not in ("admin", "manager", "super_admin"):
            return jsonify({"success": False, "error": "Access denied"}), 403

        from services.pdf_service import generate_trip_report_pdf
        pdf_bytes = generate_trip_report_pdf(
            request_data=req,
            expenses=detail.get("expenses", []),
            approvals=detail.get("approvals", []),
        )

        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'attachment; filename="trip-report-{request_id}.pdf"'
        return response

    except Exception as e:
        logger.exception("[Export] Trip PDF failed for %s", request_id)
        return jsonify({"success": False, "error": "Failed to generate PDF"}), 500


@exports_bp.route("/expenses/pdf", methods=["GET"])
@limiter.limit("10 per minute")
def export_expenses_pdf():
    """GET /api/export/expenses/pdf?trip_id=X — download expense summary as PDF."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        from flask import request
        trip_id = request.args.get("trip_id", "").strip()

        from agents.expense_agent import get_expenses
        org = get_current_org()
        oid = org["org_id"] if org else None
        result = get_expenses(trip_id=trip_id or None, user_id=user["id"], org_id=oid)
        expenses = result.get("expenses", []) if isinstance(result, dict) else result

        if not expenses:
            return jsonify({"success": False, "error": "No expenses found"}), 404

        user_name = user.get("full_name") or user.get("name") or user.get("username", "")

        from services.pdf_service import generate_expense_summary_pdf
        pdf_bytes = generate_expense_summary_pdf(
            expenses=expenses,
            user_name=user_name,
            trip_id=trip_id,
        )

        filename = f"expenses-{trip_id or 'all'}-{user['id']}.pdf"
        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        logger.exception("[Export] Expense PDF failed")
        return jsonify({"success": False, "error": "Failed to generate PDF"}), 500
