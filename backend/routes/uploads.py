"""
TravelSync Pro — File Upload Routes
Generic multipart file upload and static file serving for uploaded content.
"""
import os
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from auth import get_current_user
from config import Config

uploads_bp = Blueprint("uploads", __name__, url_prefix="/api/uploads")


@uploads_bp.route("", methods=["POST"])
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
        filename = secure_filename(uploaded_file.filename)
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
        return jsonify({"success": False, "error": str(e)}), 500


@uploads_bp.route("/<path:filename>", methods=["GET"])
def serve_file(filename):
    """GET /api/uploads/<filename> — serve an uploaded file (auth required)."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    # Prevent path traversal
    safe = os.path.basename(filename)
    if safe != filename:
        return jsonify({"success": False, "error": "Invalid filename"}), 400
    try:
        return send_from_directory(Config.UPLOAD_FOLDER, safe)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 404
