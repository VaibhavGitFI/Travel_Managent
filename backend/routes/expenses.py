"""
TravelSync Pro — Expense Routes
3-stage verification: invoice upload -> payment proof -> amount match.
Supports Vision OCR for automatic receipt extraction.
"""
import os
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from auth import get_current_user
from config import Config
from agents.expense_agent import (
    add_expense,
    get_expenses,
    upload_and_extract,
)

expenses_bp = Blueprint("expenses", __name__, url_prefix="/api")


@expenses_bp.route("/expenses", methods=["GET"])
def list_expenses():
    """GET /api/expenses?trip_id=X — list expenses for current user (optionally by trip)."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    trip_id = request.args.get("trip_id", "").strip()

    try:
        result = get_expenses(trip_id or None, user_id=user["id"])
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@expenses_bp.route("/expenses", methods=["POST"])
def submit_expense():
    """POST /api/expenses — submit a new expense or advance an existing one through stages."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    data["user_id"] = user["id"]

    try:
        result = add_expense(data)
        status = 201 if result.get("success") and not data.get("expense_id") else 200
        if not result.get("success"):
            status = 400
        return jsonify(result), status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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
        return jsonify({"success": False, "error": str(e)}), 500


@expenses_bp.route("/expense/upload-and-extract", methods=["POST"])
@expenses_bp.route("/expenses/upload-and-extract", methods=["POST"])
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
        return jsonify({"success": False, "error": str(e)}), 500
