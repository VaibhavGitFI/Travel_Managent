"""
TravelSync Pro — Expense Routes
3-stage verification: invoice upload -> payment proof -> amount match.
Supports Vision OCR for automatic receipt extraction.
"""
import logging
import os
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from auth import get_current_user, get_current_org
from config import Config
from agents.expense_agent import (
    add_expense,
    get_expenses,
    upload_and_extract,
)
from agents.anomaly_agent import detect_anomalies
from extensions import limiter
from validators import ValidationError, validate_string, validate_float, validate_currency, validate_enum

logger = logging.getLogger(__name__)

expenses_bp = Blueprint("expenses", __name__, url_prefix="/api")


@expenses_bp.route("/expenses", methods=["GET"])
def list_expenses():
    """GET /api/expenses?trip_id=X&page=1&per_page=20&search=X — list expenses with pagination and search."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    trip_id = request.args.get("trip_id", "").strip()

    try:
        org = get_current_org()
        oid = org["org_id"] if org else None
        result = get_expenses(trip_id or None, user_id=user["id"], org_id=oid)
        expenses = result.get("expenses", []) if isinstance(result, dict) else result

        # Search filter
        search = (request.args.get("search") or "").strip().lower()
        if search:
            expenses = [
                e for e in expenses
                if search in (e.get("description") or "").lower()
                or search in (e.get("vendor") or "").lower()
                or search in (e.get("category") or "").lower()
            ]

        total = len(expenses)

        # Pagination
        try:
            page = max(1, int(request.args.get("page", 1)))
            per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        except (ValueError, TypeError):
            page, per_page = 1, 20

        total_pages = max(1, -(-total // per_page))
        start = (page - 1) * per_page
        items = expenses[start:start + per_page]

        out = result if isinstance(result, dict) else {"success": True}
        out.update({
            "expenses": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        })
        return jsonify(out), 200
    except Exception as e:
        logger.exception("Failed to list expenses")
        return jsonify({"success": False, "error": "Failed to load expenses"}), 500


@expenses_bp.route("/expenses", methods=["POST"])
@limiter.limit("30 per minute")
def submit_expense():
    """POST /api/expenses — submit a new expense or advance an existing one through stages."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    data["user_id"] = user["id"]
    org = get_current_org()
    if org:
        data["org_id"] = org["org_id"]

    # Validate expense fields (skip for stage-advancement which has expense_id)
    if not data.get("expense_id"):
        try:
            validate_string(data, "category", max_len=50, required=False)
            validate_string(data, "description", max_len=500, required=False)
            validate_float(data, "invoice_amount", min_val=0, max_val=50000000, required=False, default=0)
            validate_currency(data, "currency_code", required=False)
        except ValidationError as e:
            return jsonify({"success": False, "error": e.message}), 400

    try:
        result = add_expense(data)
        status = 201 if result.get("success") and not data.get("expense_id") else 200
        if not result.get("success"):
            status = 400
        if result.get("success"):
            try:
                from extensions import socketio
                socketio.emit("data_changed", {"entity": "expenses"}, namespace="/")
                socketio.emit("data_changed", {"entity": "analytics"}, namespace="/")
            except Exception:
                pass
        return jsonify(result), status
    except Exception as e:
        logger.exception("Failed to submit expense")
        return jsonify({"success": False, "error": "Failed to submit expense"}), 500


@expenses_bp.route("/expenses/summary", methods=["GET"])
def expense_summary():
    """GET /api/expenses/summary?trip_id=X — totals and category breakdown for a trip."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    trip_id = request.args.get("trip_id", "").strip()
    if not trip_id:
        return jsonify({"success": False, "error": "trip_id query parameter is required"}), 400

    try:
        result = get_expenses(trip_id, user_id=user["id"])
        if not result.get("success"):
            return jsonify(result), 400
        # Return only the summary portion
        return jsonify({
            "success": True,
            "trip_id": trip_id,
            "summary": result.get("summary", {}),
        }), 200
    except Exception as e:
        logger.exception("Failed to load expense summary")
        return jsonify({"success": False, "error": "Failed to load expense summary"}), 500


@expenses_bp.route("/expense/upload-and-extract", methods=["POST"])
@expenses_bp.route("/expenses/upload-and-extract", methods=["POST"])
@limiter.limit("10 per minute")
def upload_and_extract_route():
    """POST /api/expense/upload-and-extract — multipart upload + instant OCR extraction."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    uploaded_file = request.files.get("file") or request.files.get("receipt")
    if not uploaded_file:
        return jsonify({"success": False, "error": "No file uploaded (field name: 'file' or 'receipt')"}), 400
    if not uploaded_file.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    if not Config.allowed_file(uploaded_file.filename):
        return jsonify({
            "success": False,
            "error": f"File type not allowed. Allowed: {', '.join(Config.ALLOWED_EXTENSIONS)}",
        }), 400

    try:
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        filename = secure_filename(uploaded_file.filename)
        file_path = os.path.join(Config.UPLOAD_FOLDER, filename)
        uploaded_file.save(file_path)

        # Run OCR extraction
        result = upload_and_extract(file_path)
        result["filename"] = filename
        result["url"] = f"/api/uploads/{filename}"
        result["size"] = os.path.getsize(file_path)
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Failed to upload and extract receipt")
        return jsonify({"success": False, "error": "Failed to process uploaded receipt"}), 500


@expenses_bp.route("/expenses/anomalies", methods=["GET"])
def expense_anomalies():
    """GET /api/expenses/anomalies — AI-powered anomaly detection on user's expenses."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    try:
        result = detect_anomalies(user["id"])
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Failed to detect expense anomalies")
        return jsonify({"success": False, "error": "Anomaly detection failed", "anomalies": []}), 500
