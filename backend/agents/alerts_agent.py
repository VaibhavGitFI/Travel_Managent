"""
TravelSync Pro — Smart Alerts Agent
Generates proactive alerts for the dashboard: upcoming trips, pending approvals,
expiring requests, and budget warnings.
"""
import logging
from datetime import datetime, timedelta
from database import get_db, table_columns

logger = logging.getLogger(__name__)


def get_user_alerts(user: dict) -> list:
    """
    Generate smart alerts for a user based on their DB data.
    Returns a list of alert dicts: {type, severity, title, message, action}
    """
    if not user or not user.get("id"):
        return []

    alerts = []
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    three_days = (now + timedelta(days=3)).strftime("%Y-%m-%d")

    try:
        db = get_db()

        # 1. Upcoming trips (within 3 days, approved/booked)
        try:
            cols = table_columns(db, "travel_requests")
            if "start_date" in cols and "status" in cols:
                upcoming = db.execute(
                    """SELECT request_id, destination, start_date, status
                       FROM travel_requests
                       WHERE user_id = ? AND start_date >= ? AND start_date <= ?
                             AND status IN ('approved', 'booked')
                       ORDER BY start_date LIMIT 5""",
                    (user["id"], today, three_days),
                ).fetchall()
                for trip in upcoming:
                    td = dict(trip)
                    days_until = (datetime.strptime(td["start_date"], "%Y-%m-%d") - now).days
                    alerts.append({
                        "type": "upcoming_trip",
                        "severity": "info" if days_until > 1 else "warning",
                        "title": f"Trip to {td['destination']} in {days_until} day{'s' if days_until != 1 else ''}",
                        "message": f"Your {td['status']} trip starts on {td['start_date']}. Make sure everything is ready.",
                        "action": {"type": "navigate", "target": "/requests"},
                    })
        except Exception as e:
            logger.debug("[Alerts] Upcoming trips query error: %s", e)

        # 2. Pending approvals (managers only)
        if user.get("role") in ("manager", "admin"):
            try:
                pending = db.execute(
                    "SELECT COUNT(*) as cnt FROM approvals WHERE approver_id = ? AND status = 'pending'",
                    (user["id"],),
                ).fetchone()
                cnt = dict(pending).get("cnt", 0)
                if cnt > 0:
                    alerts.append({
                        "type": "pending_approvals",
                        "severity": "warning" if cnt >= 3 else "info",
                        "title": f"{cnt} pending approval{'s' if cnt != 1 else ''}",
                        "message": f"You have {cnt} travel request{'s' if cnt != 1 else ''} awaiting your review.",
                        "action": {"type": "navigate", "target": "/approvals"},
                    })
            except Exception as e:
                logger.debug("[Alerts] Pending approvals query error: %s", e)

        # 3. Expiring requests (travel date approaching, still pending)
        try:
            cols = table_columns(db, "travel_requests")
            if "start_date" in cols:
                seven_days = (now + timedelta(days=7)).strftime("%Y-%m-%d")
                expiring = db.execute(
                    """SELECT request_id, destination, start_date
                       FROM travel_requests
                       WHERE user_id = ? AND start_date >= ? AND start_date <= ?
                             AND status IN ('submitted', 'pending_approval', 'draft')
                       ORDER BY start_date LIMIT 3""",
                    (user["id"], today, seven_days),
                ).fetchall()
                for req in expiring:
                    rd = dict(req)
                    alerts.append({
                        "type": "expiring_request",
                        "severity": "critical",
                        "title": f"Request to {rd['destination']} needs approval soon",
                        "message": f"Travel date {rd['start_date']} is approaching but this request hasn't been approved yet.",
                        "action": {"type": "navigate", "target": "/requests"},
                    })
        except Exception as e:
            logger.debug("[Alerts] Expiring requests query error: %s", e)

        # 4. Budget warnings (monthly expenses > 80% of policy limit)
        try:
            policy = db.execute("SELECT monthly_budget_inr FROM travel_policies LIMIT 1").fetchone()
            if policy:
                budget = dict(policy).get("monthly_budget_inr", 0)
                if budget and budget > 0:
                    month_start = now.replace(day=1).strftime("%Y-%m-%d")
                    spent_row = db.execute(
                        """SELECT COALESCE(SUM(COALESCE(verified_amount, invoice_amount, payment_amount, 0)), 0) as total
                           FROM expenses_db WHERE user_id = ? AND created_at >= ?""",
                        (user["id"], month_start),
                    ).fetchone()
                    spent = float(dict(spent_row).get("total", 0)) if spent_row else 0
                    pct = round((spent / budget) * 100)
                    if pct >= 80:
                        alerts.append({
                            "type": "budget_warning",
                            "severity": "critical" if pct >= 100 else "warning",
                            "title": f"Monthly budget {pct}% used",
                            "message": f"You've spent ₹{spent:,.0f} of your ₹{budget:,.0f} monthly limit.",
                            "action": {"type": "navigate", "target": "/expenses"},
                        })
        except Exception as e:
            logger.debug("[Alerts] Budget warning query error: %s", e)

        db.close()
    except Exception as e:
        logger.warning("[Alerts] Failed to generate alerts: %s", e)

    return alerts
