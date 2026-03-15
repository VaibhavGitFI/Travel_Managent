"""
Request Agent - Travel request CRUD + approval workflow
Status flow: draft -> submitted -> pending_approval -> approved -> booked -> in_progress -> completed
"""
import json
import logging
from datetime import datetime, date
from database import get_db
from agents.policy_agent import validate_request

logger = logging.getLogger(__name__)

# Valid manual transitions per role
# Format: { current_status: [allowed_next_statuses] }
_ALLOWED_TRANSITIONS = {
    "employee": {
        "approved":    ["booked"],
        "booked":      ["in_progress"],
        "in_progress": ["completed"],
    },
    "manager": {
        "approved":    ["booked"],
        "booked":      ["in_progress"],
        "in_progress": ["completed"],
    },
    "admin": {
        "draft":         ["submitted"],
        "submitted":     ["pending_approval", "approved"],
        "pending_approval": ["approved", "rejected"],
        "approved":      ["booked", "rejected"],
        "booked":        ["in_progress"],
        "in_progress":   ["completed"],
        "completed":     [],
        "rejected":      [],
    },
}


def create_request(data, user_id):
    """Create a new travel request."""
    db = get_db()
    now = datetime.now()
    request_id = f"TR-{now.strftime('%Y')}-{now.strftime('%m%d%H%M%S')}"

    estimated_total = float(data.get("estimated_total", 0))
    if estimated_total == 0:
        duration = int(data.get("duration_days", 1))
        hotel = float(data.get("hotel_budget_per_night", 5000))
        travelers = int(data.get("num_travelers", 1))
        estimated_total = (hotel * duration) + (2000 * duration * travelers) + (5000 * travelers)

    import json
    travelers_json = json.dumps(data.get("travelers", []))

    compliance = validate_request({**data, "estimated_total": estimated_total})

    db.execute("""
        INSERT INTO travel_requests
        (request_id, user_id, destination, origin, purpose, trip_type, travel_dates,
         start_date, end_date, duration_days, num_travelers, travelers_json,
         flight_class, hotel_budget_per_night, estimated_total, status, policy_compliance_json, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        request_id, user_id,
        data.get("destination", ""),
        data.get("origin", ""),
        data.get("purpose", ""),
        data.get("trip_type", "domestic"),
        data.get("travel_dates", ""),
        data.get("start_date", ""),
        data.get("end_date", ""),
        int(data.get("duration_days", 1)),
        int(data.get("num_travelers", 1)),
        travelers_json,
        data.get("flight_class", "economy"),
        float(data.get("hotel_budget_per_night", 5000)),
        estimated_total,
        "draft",
        json.dumps(compliance),
        data.get("notes", ""),
    ))
    db.commit()
    db.close()

    return {
        "success": True,
        "request_id": request_id,
        "status": "draft",
        "compliance": compliance,
        "estimated_total": estimated_total,
    }


def get_requests(user_id=None, status=None):
    """List travel requests, optionally filtered."""
    db = get_db()
    query = """
        SELECT tr.*, u.full_name as requester_name, u.department, u.avatar_initials
        FROM travel_requests tr
        LEFT JOIN users u ON tr.user_id = u.id
        WHERE 1=1
    """
    params = []
    if user_id:
        query += " AND tr.user_id = ?"
        params.append(user_id)
    if status:
        query += " AND tr.status = ?"
        params.append(status)
    query += " ORDER BY tr.created_at DESC"

    rows = db.execute(query, params).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_request_detail(request_id):
    """Get full detail for a single request."""
    db = get_db()
    req = db.execute("""
        SELECT tr.*, u.full_name as requester_name, u.department, u.avatar_initials, u.email
        FROM travel_requests tr
        LEFT JOIN users u ON tr.user_id = u.id
        WHERE tr.request_id = ?
    """, (request_id,)).fetchone()

    if not req:
        db.close()
        return None

    approvals = db.execute("""
        SELECT a.*, u.full_name as approver_name
        FROM approvals a
        LEFT JOIN users u ON a.approver_id = u.id
        WHERE a.request_id = ?
        ORDER BY a.created_at DESC
    """, (request_id,)).fetchall()

    expenses = db.execute("""
        SELECT * FROM expenses_db WHERE request_id = ? ORDER BY created_at DESC
    """, (request_id,)).fetchall()

    db.close()

    return {
        "request": dict(req),
        "approvals": [dict(a) for a in approvals],
        "expenses": [dict(e) for e in expenses],
    }


def update_request(request_id, data, user_id):
    """Update a draft travel request."""
    db = get_db()
    req = db.execute("SELECT * FROM travel_requests WHERE request_id = ? AND user_id = ?",
                     (request_id, user_id)).fetchone()
    if not req:
        db.close()
        return {"success": False, "error": "Request not found"}
    if req["status"] not in ("draft",):
        db.close()
        return {"success": False, "error": "Only draft requests can be edited"}

    import json
    estimated_total = float(data.get("estimated_total", req["estimated_total"]))
    compliance = validate_request({**data, "estimated_total": estimated_total})

    db.execute("""
        UPDATE travel_requests SET
            destination=?, origin=?, purpose=?, trip_type=?, travel_dates=?,
            start_date=?, end_date=?, duration_days=?, num_travelers=?,
            flight_class=?, hotel_budget_per_night=?, estimated_total=?,
            policy_compliance_json=?, notes=?, updated_at=?
        WHERE request_id=?
    """, (
        data.get("destination", req["destination"]),
        data.get("origin", req["origin"]),
        data.get("purpose", req["purpose"]),
        data.get("trip_type", req["trip_type"]),
        data.get("travel_dates", req["travel_dates"]),
        data.get("start_date", req["start_date"]),
        data.get("end_date", req["end_date"]),
        int(data.get("duration_days", req["duration_days"])),
        int(data.get("num_travelers", req["num_travelers"])),
        data.get("flight_class", req["flight_class"]),
        float(data.get("hotel_budget_per_night", req["hotel_budget_per_night"])),
        estimated_total,
        json.dumps(compliance),
        data.get("notes", req["notes"]),
        datetime.now().isoformat(),
        request_id,
    ))
    db.commit()
    db.close()
    return {"success": True, "request_id": request_id, "compliance": compliance}


def submit_request(request_id, user_id):
    """Submit a draft request for approval."""
    db = get_db()
    req = db.execute("SELECT * FROM travel_requests WHERE request_id = ? AND user_id = ?",
                     (request_id, user_id)).fetchone()
    if not req:
        db.close()
        return {"success": False, "error": "Request not found"}
    if req["status"] != "draft":
        db.close()
        return {"success": False, "error": "Only draft requests can be submitted"}

    import json
    compliance = validate_request(dict(req))

    # Auto-approve if eligible
    if compliance.get("can_auto_approve"):
        db.execute("UPDATE travel_requests SET status='approved', updated_at=? WHERE request_id=?",
                   (datetime.now().isoformat(), request_id))
        db.execute("""
            INSERT INTO approvals (request_id, approver_id, status, comments, decided_at)
            VALUES (?, NULL, 'approved', 'Auto-approved: within policy and below threshold', ?)
        """, (request_id, datetime.now().isoformat()))
        db.commit()
        db.close()
        return {"success": True, "status": "approved", "message": "Auto-approved (within policy)"}

    # Otherwise, set to pending approval
    db.execute("UPDATE travel_requests SET status='pending_approval', policy_compliance_json=?, updated_at=? WHERE request_id=?",
               (json.dumps(compliance), datetime.now().isoformat(), request_id))

    # Find a manager to assign
    manager = db.execute("SELECT id FROM users WHERE role IN ('manager','admin') LIMIT 1").fetchone()
    approver_id = manager["id"] if manager else 1

    db.execute("INSERT INTO approvals (request_id, approver_id, status) VALUES (?,?,?)",
               (request_id, approver_id, "pending"))

    db.commit()
    db.close()
    return {"success": True, "status": "pending_approval", "message": "Submitted for manager approval"}


def process_approval(request_id, approver_id, action, comments=""):
    """Approve or reject a travel request."""
    db = get_db()
    approval = db.execute(
        "SELECT * FROM approvals WHERE request_id = ? AND approver_id = ? AND status = 'pending'",
        (request_id, approver_id)
    ).fetchone()

    if not approval:
        db.close()
        return {"success": False, "error": "No pending approval found"}

    new_status = "approved" if action == "approve" else "rejected"
    now = datetime.now().isoformat()

    db.execute("UPDATE approvals SET status=?, comments=?, decided_at=? WHERE id=?",
               (new_status, comments, now, approval["id"]))
    db.execute("UPDATE travel_requests SET status=?, updated_at=? WHERE request_id=?",
               (new_status, now, request_id))
    db.commit()
    db.close()

    return {
        "success": True,
        "request_id": request_id,
        "status": new_status,
        "message": f"Request {new_status}",
    }


def get_pending_approvals(approver_id=None):
    """Get pending approval queue."""
    db = get_db()
    query = """
        SELECT a.*, tr.destination, tr.origin, tr.purpose, tr.duration_days,
               tr.estimated_total, tr.start_date, tr.end_date, tr.policy_compliance_json,
               tr.num_travelers, tr.flight_class,
               u.full_name as requester_name, u.department, u.avatar_initials
        FROM approvals a
        JOIN travel_requests tr ON a.request_id = tr.request_id
        JOIN users u ON tr.user_id = u.id
        WHERE a.status = 'pending'
    """
    params = []
    if approver_id:
        query += " AND a.approver_id = ?"
        params.append(approver_id)
    query += " ORDER BY a.created_at ASC"

    rows = db.execute(query, params).fetchall()
    db.close()
    return [dict(r) for r in rows]


def update_request_status(request_id: str, new_status: str, actor_user_id: int,
                           actor_role: str = "employee") -> dict:
    """
    Transition a request to a new status.
    Validates allowed transitions based on current status and actor role.
    """
    db = get_db()
    req = db.execute(
        "SELECT * FROM travel_requests WHERE request_id = ?", (request_id,)
    ).fetchone()

    if not req:
        db.close()
        return {"success": False, "error": "Request not found"}

    req = dict(req)
    current = req.get("status", "")

    # Ownership check — non-admins can only change their own requests
    if actor_role not in ("admin", "manager") and req.get("user_id") != actor_user_id:
        db.close()
        return {"success": False, "error": "You can only update your own requests"}

    role_key = actor_role if actor_role in _ALLOWED_TRANSITIONS else "employee"
    allowed = _ALLOWED_TRANSITIONS.get(role_key, {}).get(current, [])

    if new_status not in allowed:
        db.close()
        return {
            "success": False,
            "error": f"Cannot transition from '{current}' to '{new_status}'",
            "current_status": current,
            "allowed_transitions": allowed,
        }

    now = datetime.now().isoformat()
    db.execute(
        "UPDATE travel_requests SET status=?, updated_at=? WHERE request_id=?",
        (new_status, now, request_id)
    )
    db.commit()
    db.close()

    return {
        "success": True,
        "request_id": request_id,
        "previous_status": current,
        "status": new_status,
        "message": f"Status updated to {new_status}",
    }


def check_and_auto_transition() -> list:
    """
    Auto-transition requests based on travel dates.
    Call periodically or on list requests to keep statuses current.
    - approved/booked + start_date <= today → in_progress
    - in_progress + end_date < today → completed
    Returns list of transitioned request_ids.
    """
    db = get_db()
    today = date.today().isoformat()
    transitioned = []

    try:
        # approved/booked → in_progress when start_date arrives
        rows = db.execute("""
            SELECT request_id, status, start_date, user_id, destination
            FROM travel_requests
            WHERE status IN ('approved', 'booked')
              AND start_date IS NOT NULL AND start_date != ''
              AND start_date <= ?
        """, (today,)).fetchall()

        for row in rows:
            row = dict(row)
            db.execute(
                "UPDATE travel_requests SET status='in_progress', updated_at=? WHERE request_id=?",
                (datetime.now().isoformat(), row["request_id"])
            )
            transitioned.append({"request_id": row["request_id"], "from": row["status"], "to": "in_progress"})
            logger.info("[AutoTransition] %s: %s → in_progress", row["request_id"], row["status"])

        # in_progress → completed when end_date has passed
        rows = db.execute("""
            SELECT request_id, user_id, destination
            FROM travel_requests
            WHERE status = 'in_progress'
              AND end_date IS NOT NULL AND end_date != ''
              AND end_date < ?
        """, (today,)).fetchall()

        for row in rows:
            row = dict(row)
            db.execute(
                "UPDATE travel_requests SET status='completed', updated_at=? WHERE request_id=?",
                (datetime.now().isoformat(), row["request_id"])
            )
            transitioned.append({"request_id": row["request_id"], "from": "in_progress", "to": "completed"})
            logger.info("[AutoTransition] %s: in_progress → completed", row["request_id"])

        db.commit()
    except Exception as e:
        logger.warning("[AutoTransition] Error: %s", e)
    finally:
        db.close()

    return transitioned


def generate_trip_report(request_id: str) -> dict:
    """
    Generate a post-trip summary report using Gemini AI.
    Pulls expenses, meetings, compliance data from DB.
    """
    db = get_db()
    try:
        req = db.execute("""
            SELECT tr.*, u.full_name as requester_name, u.department
            FROM travel_requests tr
            LEFT JOIN users u ON tr.user_id = u.id
            WHERE tr.request_id = ?
        """, (request_id,)).fetchone()

        if not req:
            return {"success": False, "error": "Request not found"}

        req = dict(req)

        expenses = db.execute(
            "SELECT * FROM expenses_db WHERE request_id = ? OR trip_id = ?",
            (request_id, request_id)
        ).fetchall()
        expenses = [dict(e) for e in expenses]
        total_spent = sum(float(e.get("amount") or e.get("invoice_amount") or 0) for e in expenses)

        meetings = db.execute(
            "SELECT * FROM client_meetings WHERE user_id = ? AND LOWER(destination) LIKE ?",
            (req.get("user_id"), f"%{(req.get('destination') or '').lower()}%")
        ).fetchall()
        meetings = [dict(m) for m in meetings]

    finally:
        db.close()

    budget = float(req.get("estimated_total") or 0)

    try:
        from services.gemini_service import gemini
        if gemini.is_available:
            compliance_raw = req.get("policy_compliance_json") or "{}"
            try:
                compliance = json.loads(compliance_raw) if isinstance(compliance_raw, str) else compliance_raw
            except Exception:
                compliance = {}

            expense_lines = "\n".join([
                f"  - {e.get('category','misc')}: ₹{e.get('amount') or e.get('invoice_amount', 0)}"
                for e in expenses[:10]
            ]) or "  No expenses recorded"

            meeting_lines = "\n".join([
                f"  - {m.get('client_name')} ({m.get('company','')}) on {m.get('meeting_date','')} at {m.get('venue','')}"
                for m in meetings[:10]
            ]) or "  No meetings recorded"

            prompt = f"""Generate a concise post-trip business report (3-5 paragraphs) for:

Trip: {req.get('origin','N/A')} → {req.get('destination','N/A')}
Employee: {req.get('requester_name','N/A')} ({req.get('department','N/A')})
Dates: {req.get('start_date','N/A')} to {req.get('end_date','N/A')} ({req.get('duration_days',0)} days)
Purpose: {req.get('purpose','N/A')}

Budget: ₹{budget:,.0f} | Actual: ₹{total_spent:,.0f} | Variance: ₹{total_spent - budget:+,.0f}
Policy Compliant: {compliance.get('is_compliant', 'N/A')}

Expenses:
{expense_lines}

Client Meetings:
{meeting_lines}

Write a professional executive summary: key outcomes, budget performance, meetings conducted,
and recommendations for future trips. Be specific and business-focused.
"""
            narrative = gemini.generate(prompt)
            if narrative:
                return {
                    "success": True,
                    "request_id": request_id,
                    "report": {
                        "narrative": narrative,
                        "destination": req.get("destination"),
                        "dates": f"{req.get('start_date')} to {req.get('end_date')}",
                        "duration_days": req.get("duration_days"),
                        "budget": budget,
                        "actual_spend": total_spent,
                        "variance": total_spent - budget,
                        "expense_count": len(expenses),
                        "meeting_count": len(meetings),
                        "ai_generated": True,
                    },
                }
    except Exception as e:
        logger.warning("[TripReport] Gemini error: %s", e)

    return {
        "success": True,
        "request_id": request_id,
        "report": {
            "narrative": (
                f"Trip from {req.get('origin','N/A')} to {req.get('destination','N/A')} completed. "
                f"Duration: {req.get('duration_days', 0)} days. "
                f"Budget: ₹{budget:,.0f} | Spent: ₹{total_spent:,.0f}. "
                f"Meetings conducted: {len(meetings)}. Expenses: {len(expenses)}. "
                "Set GEMINI_API_KEY for an AI-generated executive summary."
            ),
            "destination": req.get("destination"),
            "dates": f"{req.get('start_date')} to {req.get('end_date')}",
            "duration_days": req.get("duration_days"),
            "budget": budget,
            "actual_spend": total_spent,
            "variance": total_spent - budget,
            "expense_count": len(expenses),
            "meeting_count": len(meetings),
            "ai_generated": False,
        },
    }
