"""
TravelSync Pro — File Upload Routes
Generic multipart file upload and static file serving for uploaded content.
Includes document parsing (flight tickets, hotel vouchers, visa, train tickets).
"""
import os
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from auth import get_current_user
from config import Config
from agents.document_agent import parse_document
from extensions import limiter

uploads_bp = Blueprint("uploads", __name__, url_prefix="/api/uploads")
logger = logging.getLogger(__name__)


@uploads_bp.route("", methods=["POST"])
@limiter.limit("15 per minute")
def upload_file():
    """POST /api/uploads — upload a file; returns filename, url, and size."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file field in request (expected 'file')"}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    if not Config.allowed_file(uploaded_file.filename):
        return jsonify({
            "success": False,
            "error": f"File type not allowed. Allowed: {', '.join(sorted(Config.ALLOWED_EXTENSIONS))}",
        }), 400

    try:
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        raw_name = secure_filename(uploaded_file.filename)
        # Avoid collisions: prefix with timestamp if file already exists
        base_path = os.path.join(Config.UPLOAD_FOLDER, raw_name)
        if os.path.exists(base_path):
            ts = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
            name_part, ext_part = os.path.splitext(raw_name)
            filename = f"{name_part}_{ts}{ext_part}"
        else:
            filename = raw_name
        file_path = os.path.join(Config.UPLOAD_FOLDER, filename)
        uploaded_file.save(file_path)
        size = os.path.getsize(file_path)
        return jsonify({
            "success": True,
            "filename": filename,
            "url": f"/api/uploads/{filename}",
            "size": size,
        }), 201
    except Exception as e:
        logger.exception("Failed to upload file")
        return jsonify({"success": False, "error": "Failed to upload file"}), 500


@uploads_bp.route("/parse-document", methods=["POST"])
@limiter.limit("10 per minute")
def parse_document_endpoint():
    """
    POST /api/uploads/parse-document — multipart upload + instant document parsing.

    Form fields:
      file        — the document image (JPG/PNG/PDF)
      doc_type    — optional: flight_ticket | hotel_voucher | visa | train_ticket | receipt | auto
      trip_start  — optional: YYYY-MM-DD trip start date (for visa overlap check)
      trip_end    — optional: YYYY-MM-DD trip end date
    """
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file field in request"}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    # Allow common document formats including PDF
    doc_allowed = Config.ALLOWED_EXTENSIONS | {"pdf"}
    ext = uploaded_file.filename.rsplit(".", 1)[-1].lower() if "." in uploaded_file.filename else ""
    if ext not in doc_allowed:
        return jsonify({
            "success": False,
            "error": f"File type .{ext} not allowed. Use JPG, PNG, or PDF.",
        }), 400

    doc_type = (request.form.get("doc_type") or "auto").strip().lower()
    trip_start = (request.form.get("trip_start") or "").strip()
    trip_end = (request.form.get("trip_end") or "").strip()

    try:
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        safe_name = secure_filename(uploaded_file.filename)
        stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
        file_path = os.path.join(Config.UPLOAD_FOLDER, stored_name)
        uploaded_file.save(file_path)

        result = parse_document(
            file_path=file_path,
            doc_type=doc_type,
            trip_start=trip_start or None,
            trip_end=trip_end or None,
        )
        result["url"] = f"/api/uploads/{stored_name}"
        return jsonify(result), 200 if result.get("success") else 422

    except Exception as exc:
        logger.exception("[DocumentParse] Unexpected error")
        return jsonify({"success": False, "error": "Failed to parse document"}), 500


@uploads_bp.route("/<path:filename>", methods=["GET"])
def serve_file(filename):
    """GET /api/uploads/<filename> — serve an uploaded file."""
    # Prevent path traversal
    safe = os.path.basename(filename)
    if safe != filename:
        return jsonify({"success": False, "error": "Invalid filename"}), 400

    file_path = os.path.join(Config.UPLOAD_FOLDER, safe)
    if not os.path.isfile(file_path):
        return jsonify({"success": False, "error": "File not found"}), 404

    try:
        response = send_from_directory(Config.UPLOAD_FOLDER, safe)
        # Cache avatars for 1 hour to avoid repeated loads
        if safe.startswith("avatar_"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    except Exception as e:
        logger.exception("Failed to serve file %s", filename)
        return jsonify({"success": False, "error": "File not found"}), 404
