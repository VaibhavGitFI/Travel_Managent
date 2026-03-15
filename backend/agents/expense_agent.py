"""
TravelSync Pro — Expense Agent
Schema-tolerant expense CRUD + OCR extraction helper.
Works with both legacy and newer expenses_db column layouts.
"""
import os
from datetime import datetime
from database import get_db
from services.vision_service import vision
from services.currency_service import currency


EXPENSE_CATEGORIES = [
    "flight", "hotel", "pg_accommodation", "cab", "train", "bus",
    "meals", "conference", "stationery", "internet", "medical",
    "fuel", "parking", "visa", "insurance", "miscellaneous",
]


def _table_columns(db, table: str) -> set[str]:
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_amount(amount: float, currency_code: str) -> str:
    if currency_code == "INR":
        return currency.format_inr(amount)
    formatter = getattr(currency, "format_amount", None)
    if callable(formatter):
        return formatter(amount, currency_code)
    return f"{currency_code} {amount:,.2f}"


def add_expense(data: dict) -> dict:
    """Insert or update an expense in a schema-compatible manner."""
    db = get_db()
    try:
        cols = _table_columns(db, "expenses_db")
        expense_id = data.get("expense_id")
        user_id = data.get("user_id")
        amount = _safe_float(data.get("amount") or data.get("invoice_amount"), 0.0)
        currency_code = (data.get("currency_code") or data.get("currency") or "INR").upper()
        expense_date = data.get("expense_date") or data.get("date") or datetime.now().strftime("%Y-%m-%d")

        if expense_id:
            updates = {}
            if "category" in cols and data.get("category") is not None:
                updates["category"] = data.get("category")
            if "description" in cols and data.get("description") is not None:
                updates["description"] = data.get("description")
            if "amount" in cols and (data.get("amount") is not None or data.get("invoice_amount") is not None):
                updates["amount"] = amount
            if "invoice_amount" in cols and (data.get("invoice_amount") is not None or data.get("amount") is not None):
                updates["invoice_amount"] = amount
            if "currency" in cols:
                updates["currency"] = currency_code
            if "currency_code" in cols:
                updates["currency_code"] = currency_code
            if "expense_date" in cols:
                updates["expense_date"] = expense_date
            if "date" in cols:
                updates["date"] = expense_date
            if "status" in cols and data.get("status"):
                updates["status"] = data.get("status")

            if not updates:
                return {"success": False, "error": "No updatable fields provided"}

            set_clause = ", ".join(f"{k}=?" for k in updates)
            values = list(updates.values()) + [expense_id]
            db.execute(f"UPDATE expenses_db SET {set_clause} WHERE id = ?", values)
            db.commit()
            return {
                "success": True,
                "expense_id": expense_id,
                "amount": amount,
                "formatted_amount": _format_amount(amount, currency_code),
                "message": "Expense updated",
            }

        record = {}
        if "request_id" in cols:
            record["request_id"] = data.get("request_id") or data.get("trip_id") or "default"
        if "trip_id" in cols:
            record["trip_id"] = data.get("trip_id") or data.get("request_id") or "default"
        if "user_id" in cols:
            record["user_id"] = user_id
        if "category" in cols:
            record["category"] = data.get("category", "miscellaneous")
        if "description" in cols:
            record["description"] = data.get("description", "")
        if "amount" in cols:
            record["amount"] = amount
        if "invoice_amount" in cols:
            record["invoice_amount"] = amount
        if "currency" in cols:
            record["currency"] = currency_code
        if "currency_code" in cols:
            record["currency_code"] = currency_code
        if "expense_date" in cols:
            record["expense_date"] = expense_date
        if "date" in cols:
            record["date"] = expense_date
        if "invoice_number" in cols and data.get("invoice_number"):
            record["invoice_number"] = data.get("invoice_number")
        if "status" in cols:
            record["status"] = data.get("status", "pending")
        if "submitter" in cols:
            record["submitter"] = data.get("vendor") or data.get("submitter") or ""
        if "vendor" in cols:
            record["vendor"] = data.get("vendor", "")
        if "is_personal" in cols:
            record["is_personal"] = 1 if data.get("is_personal") else 0
        if "policy_compliant" in cols:
            record["policy_compliant"] = 1
        if "invoice_file" in cols and data.get("invoice_file"):
            record["invoice_file"] = data.get("invoice_file")
        if "payment_ref" in cols and data.get("payment_ref"):
            record["payment_ref"] = data.get("payment_ref")

        keys = list(record.keys())
        placeholders = ",".join("?" for _ in keys)
        db.execute(
            f"INSERT INTO expenses_db ({','.join(keys)}) VALUES ({placeholders})",
            tuple(record[k] for k in keys),
        )
        db.commit()
        new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        return {
            "success": True,
            "expense_id": new_id,
            "amount": amount,
            "formatted_amount": _format_amount(amount, currency_code),
            "message": "Expense submitted",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def get_expenses(trip_id: str = None, user_id: int = None) -> dict:
    """Fetch expenses, optionally filtered by trip/request id."""
    db = get_db()
    try:
        cols = _table_columns(db, "expenses_db")
        query = "SELECT * FROM expenses_db WHERE 1=1"
        params = []

        if user_id and "user_id" in cols:
            query += " AND user_id = ?"
            params.append(user_id)

        if trip_id:
            trip_filters = []
            if "trip_id" in cols:
                trip_filters.append("trip_id = ?")
                params.append(trip_id)
            if "request_id" in cols:
                trip_filters.append("request_id = ?")
                params.append(trip_id)
            if trip_filters:
                query += " AND (" + " OR ".join(trip_filters) + ")"

        order_col = "expense_date" if "expense_date" in cols else "date" if "date" in cols else "created_at"
        query += f" ORDER BY {order_col} DESC"
        rows = db.execute(query, tuple(params)).fetchall()

        expenses = []
        total = 0.0
        by_category = {}
        approved_count = 0
        pending_count = 0

        for row in rows:
            exp = dict(row)
            amount = _safe_float(
                exp.get("verified_amount")
                or exp.get("invoice_amount")
                or exp.get("amount")
                or exp.get("payment_amount"),
                0.0,
            )
            currency_code = (exp.get("currency_code") or exp.get("currency") or "INR").upper()
            status = (
                exp.get("status")
                or exp.get("verification_status")
                or ("approved" if str(exp.get("stage", "1")) == "3" else "pending")
            )
            expense_date = exp.get("expense_date") or exp.get("date") or (exp.get("created_at") or "")[:10]

            normalized = {
                **exp,
                "amount": amount,
                "currency_code": currency_code,
                "status": status,
                "expense_date": expense_date,
                "vendor": exp.get("vendor") or exp.get("submitter") or "",
                "display_amount": _format_amount(amount, currency_code),
                "ocr_confidence": exp.get("ocr_confidence"),
            }
            expenses.append(normalized)

            total += amount
            cat = normalized.get("category", "miscellaneous")
            by_category[cat] = by_category.get(cat, 0.0) + amount
            if status in ("approved", "verified", "reimbursed"):
                approved_count += 1
            else:
                pending_count += 1

        return {
            "success": True,
            "expenses": expenses,
            "summary": {
                "total": total,
                "total_formatted": _format_amount(total, "INR"),
                "count": len(expenses),
                "by_category_raw": by_category,
                "by_category": {k: _format_amount(v, "INR") for k, v in by_category.items()},
                "approved_count": approved_count,
                "pending_count": pending_count,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e), "expenses": []}
    finally:
        db.close()


def upload_and_extract(file_path: str) -> dict:
    """Run OCR extraction on uploaded receipt/invoice and flatten key fields."""
    if not os.path.exists(file_path):
        return {"success": False, "error": "File not found"}

    result = vision.extract_receipt_data(file_path)
    extracted = result.get("extracted", {}) if isinstance(result, dict) else {}
    gst = (
        _safe_float(extracted.get("cgst"), 0.0)
        + _safe_float(extracted.get("sgst"), 0.0)
        + _safe_float(extracted.get("igst"), 0.0)
    )

    return {
        "success": True,
        **result,
        "amount": extracted.get("amount"),
        "vendor": extracted.get("vendor"),
        "date": extracted.get("date"),
        "invoice_number": extracted.get("invoice_number"),
        "gst": gst if gst > 0 else None,
    }


def get_expense_categories() -> list:
    """Return all supported expense categories."""
    return EXPENSE_CATEGORIES
