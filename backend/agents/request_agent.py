"""
Request Agent - Travel request CRUD + approval workflow
Status flow: draft -> submitted -> pending_approval -> approved -> booked -> in_progress -> completed
"""
from datetime import datetime
from database import get_db
from agents.policy_agent import validate_request


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
