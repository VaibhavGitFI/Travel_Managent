"""
TravelSync Pro — Unified Query Engine
Context-aware data query system for WhatsApp, Cliq, and in-app chatbots.
Respects role-based access control (employee/manager/admin hierarchy).
"""
import re
import logging
from datetime import datetime, timedelta
from database import get_db, table_columns

logger = logging.getLogger(__name__)


def _parse_date_query(text: str) -> dict:
    """Extract date range from natural language query."""
    text_lower = text.lower()
    today = datetime.now()

    # Relative dates
    if "today" in text_lower:
        return {"start": today.strftime("%Y-%m-%d"), "end": today.strftime("%Y-%m-%d")}
    if "yesterday" in text_lower:
        yesterday = today - timedelta(days=1)
        return {"start": yesterday.strftime("%Y-%m-%d"), "end": yesterday.strftime("%Y-%m-%d")}
    if "this week" in text_lower or "current week" in text_lower:
        start = today - timedelta(days=today.weekday())
        return {"start": start.strftime("%Y-%m-%d"), "end": today.strftime("%Y-%m-%d")}
    if "last week" in text_lower:
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
        return {"start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")}
    if "this month" in text_lower or "current month" in text_lower:
        start = today.replace(day=1)
        return {"start": start.strftime("%Y-%m-%d"), "end": today.strftime("%Y-%m-%d")}
    if "last month" in text_lower:
        first_this_month = today.replace(day=1)
        last_month = first_this_month - timedelta(days=1)
        start = last_month.replace(day=1)
        return {"start": start.strftime("%Y-%m-%d"), "end": last_month.strftime("%Y-%m-%d")}
    if "last 7 days" in text_lower or "past week" in text_lower:
        start = today - timedelta(days=7)
        return {"start": start.strftime("%Y-%m-%d"), "end": today.strftime("%Y-%m-%d")}
    if "last 30 days" in text_lower or "past month" in text_lower:
        start = today - timedelta(days=30)
        return {"start": start.strftime("%Y-%m-%d"), "end": today.strftime("%Y-%m-%d")}

    # Specific month patterns: "in january", "january 2026", "jan", etc.
    month_match = re.search(r'\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b', text_lower)
    if month_match:
        month_map = {
            "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
            "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
            "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9,
            "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
        }
        month = month_map.get(month_match.group(1))
        year_match = re.search(r'\b(20\d{2})\b', text)
        year = int(year_match.group(1)) if year_match else today.year
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = datetime(year, month + 1, 1) - timedelta(days=1)
        return {"start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")}

    return {}


def _get_scope_filter(user: dict, entity: str) -> dict:
    """
    Returns query filter based on user role and entity type.
    - employee: sees only their own data
    - manager: sees their team's data (users with manager_id = their id)
    - admin: sees all org data
    """
    role = user.get("role", "employee").lower()
    user_id = user.get("id")
    org_id = user.get("org_id")

    if role == "admin":
        return {"scope": "org", "org_id": org_id}
    elif role == "manager":
        return {"scope": "team", "manager_id": user_id, "user_id": user_id}
    else:
        return {"scope": "self", "user_id": user_id}


def query_trips(user: dict, query_text: str = "") -> dict:
    """Query travel requests based on user role and query text."""
    try:
        db = get_db()
        cols = table_columns(db, "travel_requests")
        scope = _get_scope_filter(user, "trips")
        date_range = _parse_date_query(query_text)

        # Base query
        if scope["scope"] == "org":
            base_query = "SELECT * FROM travel_requests WHERE org_id = ?"
            params = [scope["org_id"]]
        elif scope["scope"] == "team":
            # Manager sees their own + their team's trips
            base_query = """
                SELECT t.* FROM travel_requests t
                LEFT JOIN users u ON t.user_id = u.id
                WHERE (t.user_id = ? OR u.manager_id = ?)
            """
            params = [scope["user_id"], scope["manager_id"]]
        else:
            base_query = "SELECT * FROM travel_requests WHERE user_id = ?"
            params = [scope["user_id"]]

        # Add date filter if specified
        if date_range and "start_date" in cols:
            base_query += " AND start_date >= ? AND start_date <= ?"
            params.extend([date_range["start"], date_range["end"]])

        # Add status filter from query text
        query_lower = query_text.lower()
        if "pending" in query_lower and "status" in cols:
            base_query += " AND status = 'pending'"
        elif "approved" in query_lower and "status" in cols:
            base_query += " AND status = 'approved'"
        elif "rejected" in query_lower and "status" in cols:
            base_query += " AND status = 'rejected'"

        base_query += " ORDER BY created_at DESC LIMIT 20"

        rows = db.execute(base_query, tuple(params)).fetchall()
        db.close()

        trips = [dict(row) for row in rows]

        return {
            "success": True,
            "count": len(trips),
            "trips": trips,
            "scope": scope["scope"],
        }

    except Exception as e:
        logger.exception("[QueryEngine] query_trips failed")
        return {"success": False, "error": str(e), "trips": []}


def query_expenses(user: dict, query_text: str = "") -> dict:
    """Query expenses based on user role and query text."""
    try:
        db = get_db()
        cols = table_columns(db, "expenses_db")
        scope = _get_scope_filter(user, "expenses")
        date_range = _parse_date_query(query_text)

        # Base query
        if scope["scope"] == "org":
            base_query = "SELECT * FROM expenses_db WHERE org_id = ?"
            params = [scope["org_id"]]
        elif scope["scope"] == "team":
            base_query = """
                SELECT e.* FROM expenses_db e
                LEFT JOIN users u ON e.user_id = u.id
                WHERE (e.user_id = ? OR u.manager_id = ?)
            """
            params = [scope["user_id"], scope["manager_id"]]
        else:
            base_query = "SELECT * FROM expenses_db WHERE user_id = ?"
            params = [scope["user_id"]]

        # Date filter
        if date_range and "date" in cols:
            base_query += " AND date >= ? AND date <= ?"
            params.extend([date_range["start"], date_range["end"]])

        # Category filter
        query_lower = query_text.lower()
        if "flight" in query_lower and "category" in cols:
            base_query += " AND category = 'flight'"
        elif "hotel" in query_lower and "category" in cols:
            base_query += " AND category = 'hotel'"
        elif "food" in query_lower or "meal" in query_lower and "category" in cols:
            base_query += " AND category IN ('food', 'meals')"
        elif ("transport" in query_lower or "cab" in query_lower or "taxi" in query_lower) and "category" in cols:
            base_query += " AND category IN ('transport', 'cab')"

        # Approval status filter
        if "approval_status" in cols:
            if "pending" in query_lower:
                base_query += " AND approval_status = 'pending'"
            elif "approved" in query_lower:
                base_query += " AND approval_status = 'approved'"
            elif "rejected" in query_lower:
                base_query += " AND approval_status = 'rejected'"
            elif "draft" in query_lower:
                base_query += " AND approval_status = 'draft'"

        # Source filter
        if "source" in cols:
            if "whatsapp" in query_lower:
                base_query += " AND source = 'whatsapp'"
            elif "cliq" in query_lower:
                base_query += " AND source = 'cliq'"

        base_query += " ORDER BY created_at DESC LIMIT 50"

        rows = db.execute(base_query, tuple(params)).fetchall()

        # Calculate summary
        amt_expr = "COALESCE(verified_amount, invoice_amount, payment_amount, 0)" if "verified_amount" in cols else "COALESCE(invoice_amount, 0)"
        summary_query = base_query.replace("SELECT * FROM", f"SELECT COUNT(*) as count, SUM({amt_expr}) as total FROM").replace("ORDER BY created_at DESC LIMIT 50", "")
        summary = db.execute(summary_query, tuple(params)).fetchone()
        db.close()

        expenses = [dict(row) for row in rows]
        summary_dict = dict(summary) if summary else {}

        return {
            "success": True,
            "count": summary_dict.get("count", len(expenses)),
            "total_amount": summary_dict.get("total", 0),
            "expenses": expenses,
            "scope": scope["scope"],
        }

    except Exception as e:
        logger.exception("[QueryEngine] query_expenses failed")
        return {"success": False, "error": str(e), "expenses": []}


def query_approvals(user: dict, query_text: str = "") -> dict:
    """Query approvals based on user role."""
    try:
        db = get_db()
        role = user.get("role", "employee").lower()
        user_id = user.get("id")

        if role not in ("manager", "admin"):
            return {
                "success": False,
                "error": "Only managers and admins can view approvals",
                "approvals": [],
            }

        # Managers see approvals assigned to them, admins see all
        if role == "admin":
            base_query = """
                SELECT a.*, t.destination, t.origin, t.start_date, t.estimated_total, u.full_name as requester_name
                FROM approvals a
                JOIN travel_requests t ON a.request_id = t.request_id
                JOIN users u ON t.user_id = u.id
                WHERE 1=1
            """
            params = []
        else:
            base_query = """
                SELECT a.*, t.destination, t.origin, t.start_date, t.estimated_total, u.full_name as requester_name
                FROM approvals a
                JOIN travel_requests t ON a.request_id = t.request_id
                JOIN users u ON t.user_id = u.id
                WHERE a.approver_id = ?
            """
            params = [user_id]

        # Status filter
        query_lower = query_text.lower()
        if "pending" in query_lower:
            base_query += " AND a.status = 'pending'"
        elif "approved" in query_lower:
            base_query += " AND a.status = 'approved'"
        elif "rejected" in query_lower:
            base_query += " AND a.status = 'rejected'"

        base_query += " ORDER BY a.created_at DESC LIMIT 20"

        rows = db.execute(base_query, tuple(params)).fetchall()
        db.close()

        approvals = [dict(row) for row in rows]

        return {
            "success": True,
            "count": len(approvals),
            "approvals": approvals,
            "role": role,
        }

    except Exception as e:
        logger.exception("[QueryEngine] query_approvals failed")
        return {"success": False, "error": str(e), "approvals": []}


def query_meetings(user: dict, query_text: str = "") -> dict:
    """Query client meetings based on user role and query text."""
    try:
        db = get_db()
        scope = _get_scope_filter(user, "meetings")
        date_range = _parse_date_query(query_text)

        # Base query
        if scope["scope"] == "org":
            base_query = "SELECT * FROM client_meetings WHERE org_id = ?"
            params = [scope["org_id"]]
        elif scope["scope"] == "team":
            base_query = """
                SELECT m.* FROM client_meetings m
                LEFT JOIN users u ON m.user_id = u.id
                WHERE (m.user_id = ? OR u.manager_id = ?)
            """
            params = [scope["user_id"], scope["manager_id"]]
        else:
            base_query = "SELECT * FROM client_meetings WHERE user_id = ?"
            params = [scope["user_id"]]

        # Date filter
        if date_range:
            base_query += " AND meeting_date >= ? AND meeting_date <= ?"
            params.extend([date_range["start"], date_range["end"]])
        else:
            # Default to upcoming meetings
            today = datetime.now().strftime("%Y-%m-%d")
            base_query += " AND meeting_date >= ?"
            params.append(today)

        base_query += " ORDER BY meeting_date ASC, meeting_time ASC LIMIT 20"

        rows = db.execute(base_query, tuple(params)).fetchall()
        db.close()

        meetings = [dict(row) for row in rows]

        return {
            "success": True,
            "count": len(meetings),
            "meetings": meetings,
            "scope": scope["scope"],
        }

    except Exception as e:
        logger.exception("[QueryEngine] query_meetings failed")
        return {"success": False, "error": str(e), "meetings": []}


def query_analytics(user: dict, query_text: str = "") -> dict:
    """Generate analytics summary based on user scope."""
    try:
        db = get_db()
        cols_exp = table_columns(db, "expenses_db")
        scope = _get_scope_filter(user, "analytics")
        date_range = _parse_date_query(query_text)

        # Build scope filter
        if scope["scope"] == "org":
            expense_filter = "org_id = ?"
            trip_filter = "org_id = ?"
            params_exp = [scope["org_id"]]
            params_trip = [scope["org_id"]]
        elif scope["scope"] == "team":
            expense_filter = """user_id IN (
                SELECT id FROM users WHERE id = ? OR manager_id = ?
            )"""
            trip_filter = """user_id IN (
                SELECT id FROM users WHERE id = ? OR manager_id = ?
            )"""
            params_exp = [scope["user_id"], scope["manager_id"]]
            params_trip = [scope["user_id"], scope["manager_id"]]
        else:
            expense_filter = "user_id = ?"
            trip_filter = "user_id = ?"
            params_exp = [scope["user_id"]]
            params_trip = [scope["user_id"]]

        # Date filter
        date_clause_exp = ""
        date_clause_trip = ""
        if date_range and "date" in cols_exp:
            date_clause_exp = " AND date >= ? AND date <= ?"
            params_exp.extend([date_range["start"], date_range["end"]])
        if date_range:
            date_clause_trip = " AND start_date >= ? AND start_date <= ?"
            params_trip.extend([date_range["start"], date_range["end"]])

        # Expense analytics
        amt_expr = "COALESCE(verified_amount, invoice_amount, payment_amount, 0)" if "verified_amount" in cols_exp else "COALESCE(invoice_amount, 0)"

        expense_summary = db.execute(
            f"SELECT COUNT(*) as count, SUM({amt_expr}) as total FROM expenses_db WHERE {expense_filter}{date_clause_exp}",
            tuple(params_exp)
        ).fetchone()

        # By category
        category_breakdown = db.execute(
            f"SELECT category, COUNT(*) as count, SUM({amt_expr}) as total FROM expenses_db WHERE {expense_filter}{date_clause_exp} GROUP BY category ORDER BY total DESC LIMIT 10",
            tuple(params_exp)
        ).fetchall()

        # By source
        source_breakdown = []
        if "source" in cols_exp:
            source_breakdown = db.execute(
                f"SELECT source, COUNT(*) as count, SUM({amt_expr}) as total FROM expenses_db WHERE {expense_filter}{date_clause_exp} GROUP BY source ORDER BY total DESC",
                tuple(params_exp)
            ).fetchall()

        # Trip statistics
        trip_summary = db.execute(
            f"SELECT COUNT(*) as count, SUM(COALESCE(estimated_total, 0)) as total FROM travel_requests WHERE {trip_filter}{date_clause_trip}",
            tuple(params_trip)
        ).fetchone()

        db.close()

        return {
            "success": True,
            "scope": scope["scope"],
            "expenses": {
                "count": dict(expense_summary).get("count", 0),
                "total_amount": dict(expense_summary).get("total", 0),
                "by_category": [dict(r) for r in category_breakdown],
                "by_source": [dict(r) for r in source_breakdown],
            },
            "trips": {
                "count": dict(trip_summary).get("count", 0),
                "total_budget": dict(trip_summary).get("total", 0),
            },
        }

    except Exception as e:
        logger.exception("[QueryEngine] query_analytics failed")
        return {"success": False, "error": str(e)}


def handle_query(user: dict, query_text: str) -> dict:
    """
    Main query handler - detects intent and routes to appropriate query function.
    Returns structured data that can be formatted by each channel (WhatsApp/Cliq/Web).
    """
    query_lower = query_text.lower()

    # Detect intent
    if any(w in query_lower for w in ["trip", "travel", "visit", "journey", "request"]):
        return {"type": "trips", "data": query_trips(user, query_text)}
    elif any(w in query_lower for w in ["expense", "receipt", "bill", "spending", "spent", "cost"]):
        return {"type": "expenses", "data": query_expenses(user, query_text)}
    elif any(w in query_lower for w in ["approval", "approve", "pending", "review"]):
        return {"type": "approvals", "data": query_approvals(user, query_text)}
    elif any(w in query_lower for w in ["meeting", "client", "appointment", "visit"]):
        return {"type": "meetings", "data": query_meetings(user, query_text)}
    elif any(w in query_lower for w in ["analytics", "stats", "summary", "dashboard", "report", "breakdown"]):
        return {"type": "analytics", "data": query_analytics(user, query_text)}
    else:
        # Default to expense query if ambiguous
        return {"type": "expenses", "data": query_expenses(user, query_text)}
