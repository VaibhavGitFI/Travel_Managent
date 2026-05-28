"""
TravelSync Pro — Input Validation Helpers
Lightweight validation without external dependencies (no marshmallow/pydantic required).
"""
import re
from functools import wraps
from datetime import datetime as _dt
from typing import Any
from flask import request as flask_request, jsonify

# Reusable regex patterns
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CITY_RE = re.compile(r"^[A-Za-z\s\-.,''()]{2,100}$")
_PHONE_RE = re.compile(r"^[\+\d\s\-()]{6,20}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,128}$")


class ValidationError(Exception):
    """Raised when input validation fails."""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def validate_required(data: dict, fields: list[str]) -> None:
    """Ensure all listed fields are present and non-empty."""
    for field in fields:
        val = data.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            raise ValidationError(field, f"{field} is required")


def validate_string(data: dict, field: str, min_len: int = 1, max_len: int = 500,
                    pattern: re.Pattern | None = None, required: bool = True) -> str | None:
    """Validate and return a trimmed string field."""
    val = data.get(field)
    if val is None or (isinstance(val, str) and not val.strip()):
        if required:
            raise ValidationError(field, f"{field} is required")
        return None
    val = str(val).strip()
    if len(val) < min_len:
        raise ValidationError(field, f"{field} must be at least {min_len} characters")
    if len(val) > max_len:
        raise ValidationError(field, f"{field} must not exceed {max_len} characters")
    if pattern and not pattern.match(val):
        raise ValidationError(field, f"{field} has invalid format")
    return val


def validate_email(data: dict, field: str = "email", required: bool = True) -> str | None:
    """Validate an email field."""
    val = data.get(field)
    if val is None or (isinstance(val, str) and not val.strip()):
        if required:
            raise ValidationError(field, "Email is required")
        return None
    val = str(val).strip().lower()
    if len(val) > 254:
        raise ValidationError(field, "Email too long")
    if not _EMAIL_RE.match(val):
        raise ValidationError(field, "Invalid email address")
    return val


def validate_password(password: str) -> str:
    """Validate password strength. Returns the password if valid."""
    if not password or len(password) < 8:
        raise ValidationError("password", "Password must be at least 8 characters")
    if len(password) > 128:
        raise ValidationError("password", "Password must not exceed 128 characters")
    if not _PASSWORD_RE.match(password):
        raise ValidationError("password", "Password must contain at least one uppercase letter, one lowercase letter, and one number")
    return password


def validate_int(data: dict, field: str, min_val: int | None = None,
                 max_val: int | None = None, required: bool = True, default: int = 0) -> int:
    """Validate and return an integer field."""
    val = data.get(field)
    if val is None:
        if required:
            raise ValidationError(field, f"{field} is required")
        return default
    try:
        val = int(val)
    except (ValueError, TypeError):
        raise ValidationError(field, f"{field} must be a number")
    if min_val is not None and val < min_val:
        raise ValidationError(field, f"{field} must be at least {min_val}")
    if max_val is not None and val > max_val:
        raise ValidationError(field, f"{field} must not exceed {max_val}")
    return val


def validate_float(data: dict, field: str, min_val: float | None = None,
                   max_val: float | None = None, required: bool = True, default: float = 0.0) -> float:
    """Validate and return a float field."""
    val = data.get(field)
    if val is None:
        if required:
            raise ValidationError(field, f"{field} is required")
        return default
    try:
        val = float(val)
    except (ValueError, TypeError):
        raise ValidationError(field, f"{field} must be a number")
    if min_val is not None and val < min_val:
        raise ValidationError(field, f"{field} must be at least {min_val}")
    if max_val is not None and val > max_val:
        raise ValidationError(field, f"{field} must not exceed {max_val}")
    return val


def validate_date(data: dict, field: str, required: bool = True) -> str | None:
    """Validate a date string in YYYY-MM-DD format."""
    val = data.get(field)
    if val is None or (isinstance(val, str) and not val.strip()):
        if required:
            raise ValidationError(field, f"{field} is required")
        return None
    val = str(val).strip()
    if not _DATE_RE.match(val):
        raise ValidationError(field, f"{field} must be in YYYY-MM-DD format")
    try:
        _dt.strptime(val, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(field, f"{field} is not a valid date")
    return val


def validate_city(data: dict, field: str, required: bool = True) -> str | None:
    """Validate a city/location name."""
    return validate_string(data, field, min_len=2, max_len=100, pattern=_CITY_RE, required=required)


def validate_enum(data: dict, field: str, allowed: set[str], required: bool = True, default: str = "") -> str:
    """Validate a field against a set of allowed values."""
    val = data.get(field)
    if val is None or (isinstance(val, str) and not val.strip()):
        if required:
            raise ValidationError(field, f"{field} is required")
        return default
    val = str(val).strip()
    if val not in allowed:
        raise ValidationError(field, f"{field} must be one of: {', '.join(sorted(allowed))}")
    return val


def validate_currency(data: dict, field: str = "currency_code", required: bool = False) -> str:
    """Validate ISO 4217 currency code."""
    val = data.get(field)
    if val is None or (isinstance(val, str) and not val.strip()):
        if required:
            raise ValidationError(field, "Currency code is required")
        return "INR"
    val = str(val).strip().upper()
    if not _CURRENCY_RE.match(val):
        raise ValidationError(field, "Currency code must be a 3-letter ISO 4217 code")
    return val


# ── Decorator-style validators for route handlers ────────────────────────────

def require_json(*required_fields):
    """Decorator: validates required fields exist in JSON body."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            data = flask_request.get_json(silent=True)
            if data is None:
                return jsonify({"success": False, "error": "Request body must be JSON"}), 400
            missing = [fld for fld in required_fields if fld not in data or data[fld] is None]
            if missing:
                return jsonify({"success": False, "error": f"Missing required fields: {', '.join(missing)}"}), 400
            return f(*args, **kwargs)
        return wrapper
    return decorator


def require_id(param_name):
    """Decorator: validates a URL parameter is a positive integer."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            val = kwargs.get(param_name)
            if val is not None:
                try:
                    val = int(val)
                    if val <= 0:
                        raise ValueError
                    kwargs[param_name] = val
                except (ValueError, TypeError):
                    return jsonify({"success": False, "error": f"Invalid {param_name}"}), 400
            return f(*args, **kwargs)
        return wrapper
    return decorator


def sanitize_string(value, max_length=500):
    """Strip, truncate, and remove null bytes from string input."""
    if not isinstance(value, str):
        return value
    return value.strip().replace("\x00", "")[:max_length]
