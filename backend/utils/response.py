"""
TravelSync Pro — Standardized API Response Helpers

All API responses should use these helpers for consistent shape:
    Success: {"success": True, "data": ..., "message": ...}
    Error:   {"success": False, "error": "...", "errors": [...]}
"""
from flask import jsonify


def success_response(data=None, message=None, status=200):
    """Build a standardized success response."""
    body = {"success": True}
    if data is not None:
        body["data"] = data
    if message:
        body["message"] = message
    return jsonify(body), status


def error_response(message, status=400, errors=None):
    """Build a standardized error response."""
    body = {"success": False, "error": message}
    if errors:
        body["errors"] = errors
    return jsonify(body), status
