"""
TravelSync Pro — Unified Query Engine
Context-aware data query system for WhatsApp, Cliq, and in-app chatbots.
Respects role-based access control (employee/manager/admin hierarchy).
"""
import re
import logging
from datetime import datetime, timedelta
from database import get_db, table_columns
from auth import get_user_org

logger = logging.getLogger(__name__)


def _get_effective_org_id(user: dict) -> int | None:
    """Resolve org_id from the user payload or org membership when available."""
    org_id = user.get("org_id")
    if org_id:
        return org_id
    try:
        membership = get_user_org(user.get("id"))
        return membership.get("org_id") if membership else None
    except Exception:
        return None


def _normalize_query_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _platform_scope_requested(query_text: str) -> bool:
    query_lower = _normalize_query_text(query_text)
    markers = (
        "platform",
        "platform-wide",
        "entire platform",
        "whole platform",
        "all orgs",
        "all organizations",
        "across organizations",
        "across all organizations",
        "company wide",
    )
    return any(marker in query_lower for marker in markers)


def _resolve_org_from_query(query_text: str, fallback_org_id: int | None = None) -> dict | None:
    query_lower = _normalize_query_text(query_text)
    if not query_lower:
        return None

    current_org_markers = (
        "my org",
        "my organization",
        "our org",
        "our organization",
        "this org",
        "this organization",
    )
    wants_org_context = " org" in query_lower or "organization" in query_lower
    if fallback_org_id and any(marker in query_lower for marker in current_org_markers):
        return {"org_id": fallback_org_id}

    if not wants_org_context:
        return None

    try:
        db = get_db()
        rows = db.execute(
            "SELECT id, name, slug FROM organizations ORDER BY LENGTH(name) DESC, id ASC"
        ).fetchall()
        db.close()
    except Exception:
        return {"org_id": fallback_org_id} if fallback_org_id else None

    for row in rows:
        org = dict(row)
        candidates = [
            _normalize_query_text(org.get("name")),
            _normalize_query_text(org.get("slug")),
        ]
        for candidate in candidates:
            if candidate and candidate in query_lower:
                return {
                    "org_id": org["id"],
                    "org_name": org.get("name"),
                    "org_slug": org.get("slug"),
                }

    if fallback_org_id:
        for row in rows:
            org = dict(row)
            if org.get("id") == fallback_org_id:
                return {
                    "org_id": org["id"],
                    "org_name": org.get("name"),
                    "org_slug": org.get("slug"),
                }
        return {"org_id": fallback_org_id}

    return None


def _humanize_role(role: str) -> str:
    return (role or "user").replace("_", " ")


def _pluralize(word: str, count: int) -> str:
    return word if count == 1 else f"{word}s"


def detect_query_type(query_text: str) -> str | None:
    """Classify a natural-language data question into a structured query type."""
    query_lower = (query_text or "").lower()

    if any(w in query_lower for w in ["user", "users", "employee", "employees", "staff", "team member", "team members"]):
        return "users"
    if any(w in query_lower for w in ["trip", "travel", "journey", "request"]) and "approval" not in query_lower:
        return "trips"
    if any(w in query_lower for w in ["expense", "receipt", "bill", "spending", "spent", "cost", "reimbursement"]):
        return "expenses"
    if any(w in query_lower for w in ["approval", "approve", "pending", "review"]):
        return "approvals"
    if any(w in query_lower for w in ["meeting", "client", "appointment", "visit"]):
        return "meetings"
    if any(w in query_lower for w in ["analytics", "stats", "summary", "dashboard", "report", "breakdown"]):
        return "analytics"

    return None


def should_use_structured_query(query_text: str) -> bool:
    """
    Decide whether a message should be answered by the structured DB query layer
    or left to the planning / action / conversational flows.
    """
    query_lower = _normalize_query_text(query_text)
    query_type = detect_query_type(query_text)

    if not query_type:
        return False

    if query_type == "trips":
        record_markers = (
            "show my trips",
            "show trips",
            "my trips",
            "my trip requests",
            "trip requests",
            "travel requests",
            "travel request",
            "recent trips",
            "pending trips",
            "approved trips",
            "rejected trips",
            "trip status",
            "travel status",
        )
        planning_markers = (
            "help me plan",
            "plan trip",
            "plan a trip",
            "book trip",
            "arrange trip",
            "itinerary",
            "recommend",
            "suggest",
        )
        route_pattern = re.search(r"(?:from\s+)?[a-z][a-z\s]+?\s+to\s+[a-z][a-z\s]+", query_lower)
        time_markers = ("next week", "tomorrow", "next month", "this weekend", "next weekend")
        data_markers = ("show", "list", "display", "status", "pending", "approved", "rejected", "recent", "overview", "summary")

        if any(marker in query_lower for marker in record_markers):
            return True
        if any(marker in query_lower for marker in planning_markers):
            return False
        if route_pattern and any(marker in query_lower for marker in ("plan", "book", "arrange", "visit", "go to", *time_markers)):
            return False
        if any(marker in query_lower for marker in data_markers) and any(noun in query_lower for noun in ("trip", "trips", "travel request", "travel requests", "request", "requests")):
            return True
        return False

    if query_type == "approvals":
        if any(marker in query_lower for marker in ("approve ", "reject ", "approve the", "reject the")):
            return False
        return True

    if query_type == "meetings":
        if any(marker in query_lower for marker in ("schedule meeting", "arrange meeting", "book meeting", "create meeting")):
            return False
        return True

    if query_type == "expenses":
        if any(marker in query_lower for marker in ("add expense", "submit expense", "file expense", "create expense", "upload receipt")):
            return False
        return True

    if query_type in ("users", "analytics"):
        return True

    return False


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


def _get_scope_filter(user: dict, entity: str, query_text: str = "") -> dict:
    """
    Returns query filter based on user role and entity type.
    - employee: sees only their own data
    - manager: sees their team's data (users with manager_id = their id)
    - admin: sees all org data
    """
    role = user.get("role", "employee").lower()
    user_id = user.get("id")
    org_id = _get_effective_org_id(user)

    if role == "super_admin":
        requested_org = _resolve_org_from_query(query_text, fallback_org_id=org_id)
        if requested_org:
            return {
                "scope": "org",
                "org_id": requested_org.get("org_id"),
                "org_name": requested_org.get("org_name"),
                "org_slug": requested_org.get("org_slug"),
            }
        if _platform_scope_requested(query_text):
            return {"scope": "all"}
        if org_id:
            return {"scope": "org", "org_id": org_id}
        return {"scope": "all"}
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
        scope = _get_scope_filter(user, "trips", query_text)
        date_range = _parse_date_query(query_text)

        # Base query
        if scope["scope"] == "all":
            base_query = "SELECT * FROM travel_requests WHERE 1=1"
            params = []
        elif scope["scope"] == "org":
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
        scope = _get_scope_filter(user, "expenses", query_text)
        date_range = _parse_date_query(query_text)

        # Base query
        if scope["scope"] == "all":
            base_query = "SELECT * FROM expenses_db WHERE 1=1"
            params = []
        elif scope["scope"] == "org":
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

        if role not in ("manager", "admin", "super_admin"):
            return {
                "success": False,
                "error": "Only managers and admins can view approvals",
                "approvals": [],
            }

        # Managers see approvals assigned to them, admins see all
        if role in ("admin", "super_admin"):
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
        scope = _get_scope_filter(user, "meetings", query_text)
        date_range = _parse_date_query(query_text)

        # Base query
        if scope["scope"] == "all":
            base_query = "SELECT * FROM client_meetings WHERE 1=1"
            params = []
        elif scope["scope"] == "org":
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
        scope = _get_scope_filter(user, "analytics", query_text)
        date_range = _parse_date_query(query_text)

        # Build scope filter
        if scope["scope"] == "all":
            expense_filter = "1=1"
            trip_filter = "1=1"
            params_exp = []
            params_trip = []
        elif scope["scope"] == "org":
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


def query_users(user: dict, query_text: str = "") -> dict:
    """Query platform, organization, team, or self user data based on role."""
    try:
        db = get_db()
        cols = table_columns(db, "users")
        scope = _get_scope_filter(user, "users", query_text)
        query_lower = (query_text or "").lower()

        select_cols = [
            "u.id",
            "u.username",
            "u.name",
            "u.full_name",
            "u.email",
            "u.role",
            "u.department",
            "u.created_at",
        ]
        if "email_verified" in cols:
            select_cols.append("u.email_verified")

        if scope["scope"] == "all":
            from_sql = "FROM users u"
            where_clauses = ["1=1"]
            params = []
        elif scope["scope"] == "org":
            from_sql = "FROM users u JOIN org_members om ON om.user_id = u.id"
            where_clauses = ["om.org_id = ?"]
            params = [scope["org_id"]]
        elif scope["scope"] == "team":
            from_sql = "FROM users u"
            where_clauses = ["(u.id = ? OR u.manager_id = ?)"]
            params = [scope["user_id"], scope["manager_id"]]
        else:
            from_sql = "FROM users u"
            where_clauses = ["u.id = ?"]
            params = [scope["user_id"]]

        role_map = {
            "super admin": "super_admin",
            "superadmin": "super_admin",
            "admin": "admin",
            "manager": "manager",
            "employee": "employee",
        }
        for label, role_value in role_map.items():
            if label in query_lower:
                where_clauses.append("u.role = ?")
                params.append(role_value)
                break

        if "verified" in query_lower and "email_verified" in cols:
            where_clauses.append("u.email_verified = 1")
        elif "unverified" in query_lower and "email_verified" in cols:
            where_clauses.append("COALESCE(u.email_verified, 0) = 0")

        where_sql = " AND ".join(where_clauses)
        base_sql = f"{from_sql} WHERE {where_sql}"

        rows = db.execute(
            f"SELECT {', '.join(select_cols)} {base_sql} ORDER BY u.created_at DESC LIMIT 50",
            tuple(params),
        ).fetchall()
        users = [dict(row) for row in rows]

        count_row = db.execute(
            f"SELECT COUNT(*) as count {base_sql}",
            tuple(params),
        ).fetchone()
        exact_count = dict(count_row).get("count", 0) if count_row else 0

        role_breakdown_query = (
            f"SELECT scoped_users.role, COUNT(*) as count "
            f"FROM (SELECT u.id, u.role {base_sql}) scoped_users "
            "GROUP BY scoped_users.role ORDER BY count DESC, scoped_users.role ASC"
        )
        role_breakdown = [dict(r) for r in db.execute(role_breakdown_query, tuple(params)).fetchall()]

        verified_count = None
        if "email_verified" in cols:
            verified_row = db.execute(
                f"SELECT COUNT(*) as count FROM (SELECT COALESCE(u.email_verified, 0) as email_verified {base_sql}) scoped_users "
                "WHERE scoped_users.email_verified = 1",
                tuple(params)
            ).fetchone()
            verified_count = dict(verified_row).get("count", 0) if verified_row else 0

        db.close()

        return {
            "success": True,
            "count": exact_count,
            "users": users,
            "scope": scope["scope"],
            "org_name": scope.get("org_name"),
            "role_breakdown": role_breakdown,
            "verified_count": verified_count,
        }

    except Exception as e:
        logger.exception("[QueryEngine] query_users failed")
        return {"success": False, "error": str(e), "users": []}


def handle_query(user: dict, query_text: str, strict: bool = False) -> dict:
    """
    Main query handler - detects intent and routes to appropriate query function.
    Returns structured data that can be formatted by each channel (WhatsApp/Cliq/Web).
    """
    query_type = detect_query_type(query_text)

    if query_type == "trips":
        return {"type": "trips", "data": query_trips(user, query_text)}
    elif query_type == "expenses":
        return {"type": "expenses", "data": query_expenses(user, query_text)}
    elif query_type == "approvals":
        return {"type": "approvals", "data": query_approvals(user, query_text)}
    elif query_type == "meetings":
        return {"type": "meetings", "data": query_meetings(user, query_text)}
    elif query_type == "analytics":
        return {"type": "analytics", "data": query_analytics(user, query_text)}
    elif query_type == "users":
        return {"type": "users", "data": query_users(user, query_text)}
    elif strict:
        return {"type": "general", "data": {"success": False, "error": "No structured query detected"}}
    else:
        # Default to expense query if ambiguous
        return {"type": "expenses", "data": query_expenses(user, query_text)}


def format_query_result_for_voice(query_result: dict, query_text: str = "") -> str | None:
    """Format a structured query result as a concise OTIS/Jarvis voice response."""
    if not query_result or not query_result.get("data", {}).get("success"):
        return None

    query_type = query_result.get("type")
    data = query_result.get("data", {})
    query_lower = (query_text or "").lower()

    if query_type == "users":
        count = int(data.get("count", 0) or 0)
        scope = data.get("scope", "self")
        org_name = data.get("org_name")
        scope_text = {
            "all": "the platform",
            "org": org_name or "your organisation",
            "team": "your team",
            "self": "your account",
        }.get(scope, "your scope")

        if scope == "self":
            user_row = (data.get("users") or [{}])[0]
            name = user_row.get("full_name") or user_row.get("name") or user_row.get("username") or "you"
            role = _humanize_role(user_row.get("role", "user"))
            return f"I found your user record. You are logged in as {name}, with the role of {role}."

        first_sentence = f"There are {count} users in {scope_text} right now."

        role_parts = []
        for row in data.get("role_breakdown", [])[:3]:
            role_count = int(row.get("count", 0) or 0)
            role_name = _humanize_role(row.get("role", "user"))
            role_parts.append(f"{role_count} {_pluralize(role_name, role_count)}")

        second_sentence = None
        if role_parts:
            second_sentence = "That includes " + ", ".join(role_parts[:-1]) + (f", and {role_parts[-1]}." if len(role_parts) > 1 else f"{role_parts[0]}.")

        if len(role_parts) == 2:
            second_sentence = f"That includes {role_parts[0]} and {role_parts[1]}."

        third_sentence = None
        verified_count = data.get("verified_count")
        if verified_count is not None and any(word in query_lower for word in ["overview", "summary", "verified", "verification"]):
            third_sentence = f"{int(verified_count)} {_pluralize('account', int(verified_count))} have verified email."

        preview_names = []
        if any(word in query_lower for word in ["list", "show", "who", "which", "name"]):
            for user_row in (data.get("users") or [])[:3]:
                preview_names.append(
                    user_row.get("full_name") or user_row.get("name") or user_row.get("username") or "Unknown user"
                )
        if preview_names:
            third_sentence = f"The first few are {', '.join(preview_names[:-1]) + f', and {preview_names[-1]}' if len(preview_names) > 1 else preview_names[0]}."

        return " ".join(part for part in [first_sentence, second_sentence, third_sentence] if part)

    if query_type == "approvals":
        count = int(data.get("count", 0) or 0)
        approvals = data.get("approvals", []) or []
        if count == 0:
            return "You have no approvals waiting right now."
        names = []
        for approval in approvals[:3]:
            destination = approval.get("destination") or "an unnamed trip"
            requester = approval.get("requester_name")
            if requester:
                names.append(f"{destination} for {requester}")
            else:
                names.append(destination)
        detail = f" The latest are {', '.join(names[:-1]) + f', and {names[-1]}' if len(names) > 1 else names[0]}." if names else ""
        return f"You have {count} pending {_pluralize('approval', count)}.{detail}"

    if query_type == "trips":
        count = int(data.get("count", 0) or 0)
        scope = data.get("scope", "self")
        scope_text = {
            "all": "the platform",
            "org": "your organisation",
            "team": "your team",
            "self": "your account",
        }.get(scope, "your scope")
        trips = data.get("trips", []) or []
        if count == 0:
            return f"I could not find any travel requests in {scope_text}."
        status_counts = {}
        for trip in trips:
            status = (trip.get("status") or "unknown").lower()
            status_counts[status] = status_counts.get(status, 0) + 1
        status_sentence = None
        if status_counts:
            parts = [f"{value} {status}" for status, value in status_counts.items()]
            status_sentence = "In the latest results, " + ", ".join(parts[:-1]) + (f", and {parts[-1]}." if len(parts) > 1 else f"{parts[0]}.")
            if len(parts) == 2:
                status_sentence = f"In the latest results, {parts[0]} and {parts[1]}."
        return " ".join(part for part in [f"I found {count} travel {_pluralize('request', count)} in {scope_text}.", status_sentence] if part)

    if query_type == "expenses":
        count = int(data.get("count", 0) or 0)
        total_amount = float(data.get("total_amount", 0) or 0)
        if count == 0:
            return "I could not find any matching expenses."
        return f"I found {count} {_pluralize('expense', count)} totalling {total_amount:,.0f} rupees."

    if query_type == "meetings":
        count = int(data.get("count", 0) or 0)
        meetings = data.get("meetings", []) or []
        if count == 0:
            return "You have no matching meetings right now."
        next_meeting = meetings[0]
        client_name = next_meeting.get("client_name") or next_meeting.get("company")
        meeting_date = next_meeting.get("meeting_date")
        if client_name and meeting_date:
            return f"You have {count} upcoming {_pluralize('meeting', count)}. The next one is with {client_name} on {meeting_date}."
        return f"You have {count} upcoming {_pluralize('meeting', count)}."

    if query_type == "analytics":
        expense_count = int(data.get("expenses", {}).get("count", 0) or 0)
        expense_total = float(data.get("expenses", {}).get("total_amount", 0) or 0)
        trip_count = int(data.get("trips", {}).get("count", 0) or 0)
        trip_total = float(data.get("trips", {}).get("total_budget", 0) or 0)
        return (
            f"Your analytics show {trip_count} {_pluralize('trip', trip_count)} worth {trip_total:,.0f} rupees, "
            f"and {expense_count} {_pluralize('expense', expense_count)} totalling {expense_total:,.0f} rupees."
        )

    return None
