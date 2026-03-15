"""
Policy Agent - Travel policy validation engine
Returns compliance status with green/amber/red indicators per category
"""
from database import get_db


def get_active_policy():
    """Get the active travel policy."""
    try:
        db = get_db()
        policy = db.execute("SELECT * FROM travel_policies WHERE active = 1 LIMIT 1").fetchone()
        db.close()
        if policy:
            return dict(policy)
    except Exception:
        pass
    # Default policy fallback
    return {
        "max_flight_class": "economy",
        "max_hotel_per_night": 10000,
        "max_daily_perdiem": 2000,
        "max_trip_duration_days": 14,
        "min_advance_booking_days": 3,
        "max_total_budget": 100000,
        "auto_approve_below": 15000,
    }


def validate_request(request_data):
    """
    Validate a travel request against company policy.

    Returns:
        dict with overall_status (compliant/warning/violation),
        indicators per category (green/amber/red),
        and list of issues.
    """
    policy = get_active_policy()
    checks = []
    issues = []

    # Flight class check
    flight_class = request_data.get("flight_class", "economy")
    allowed_classes = {"economy": 1, "premium_economy": 2, "business": 3, "first": 4}
    max_class = policy.get("max_flight_class", "economy")
    if allowed_classes.get(flight_class, 1) > allowed_classes.get(max_class, 1):
        checks.append({"category": "Flight Class", "status": "red", "message": f"{flight_class} exceeds policy max ({max_class})"})
        issues.append(f"Flight class '{flight_class}' exceeds max allowed '{max_class}'")
    else:
        checks.append({"category": "Flight Class", "status": "green", "message": f"{flight_class} within policy"})

    # Hotel budget check
    hotel_budget = float(request_data.get("hotel_budget_per_night", 5000))
    max_hotel = policy.get("max_hotel_per_night", 10000)
    if hotel_budget > max_hotel:
        checks.append({"category": "Hotel Budget", "status": "red", "message": f"Rs.{hotel_budget:,.0f}/night exceeds cap Rs.{max_hotel:,.0f}"})
        issues.append(f"Hotel budget Rs.{hotel_budget:,.0f} exceeds cap Rs.{max_hotel:,.0f}")
    elif hotel_budget > max_hotel * 0.8:
        checks.append({"category": "Hotel Budget", "status": "amber", "message": f"Rs.{hotel_budget:,.0f}/night approaching cap"})
    else:
        checks.append({"category": "Hotel Budget", "status": "green", "message": f"Rs.{hotel_budget:,.0f}/night within policy"})

    # Duration check
    duration = int(request_data.get("duration_days", 1))
    max_dur = policy.get("max_trip_duration_days", 14)
    if duration > max_dur:
        checks.append({"category": "Duration", "status": "red", "message": f"{duration} days exceeds max {max_dur}"})
        issues.append(f"Trip duration {duration} days exceeds max {max_dur}")
    elif duration > max_dur * 0.7:
        checks.append({"category": "Duration", "status": "amber", "message": f"{duration} days approaching limit"})
    else:
        checks.append({"category": "Duration", "status": "green", "message": f"{duration} days within policy"})

    # Total budget check
    estimated_total = float(request_data.get("estimated_total", 0))
    max_budget = policy.get("max_total_budget", 100000)
    if estimated_total > max_budget:
        checks.append({"category": "Total Budget", "status": "red", "message": f"Rs.{estimated_total:,.0f} exceeds max Rs.{max_budget:,.0f}"})
        issues.append(f"Total Rs.{estimated_total:,.0f} exceeds budget Rs.{max_budget:,.0f}")
    elif estimated_total > max_budget * 0.8:
        checks.append({"category": "Total Budget", "status": "amber", "message": f"Rs.{estimated_total:,.0f} approaching limit"})
    else:
        checks.append({"category": "Total Budget", "status": "green", "message": f"Rs.{estimated_total:,.0f} within budget"})

    # Advance booking check
    from datetime import datetime, timedelta
    start_date = request_data.get("start_date", "")
    min_advance = policy.get("min_advance_booking_days", 3)
    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            days_ahead = (start - datetime.now()).days
            if days_ahead < min_advance:
                checks.append({"category": "Advance Booking", "status": "amber", "message": f"Only {days_ahead} days notice (min {min_advance})"})
                issues.append(f"Less than {min_advance} days advance booking")
            else:
                checks.append({"category": "Advance Booking", "status": "green", "message": f"{days_ahead} days advance notice"})
        except ValueError:
            checks.append({"category": "Advance Booking", "status": "green", "message": "Date not validated"})
    else:
        checks.append({"category": "Advance Booking", "status": "green", "message": "No date specified"})

    # Per diem check
    per_diem = float(request_data.get("daily_perdiem", 0))
    max_perdiem = policy.get("max_daily_perdiem", 2000)
    if per_diem > 0:
        if per_diem > max_perdiem:
            checks.append({"category": "Per Diem", "status": "red", "message": f"Rs.{per_diem:,.0f}/day exceeds Rs.{max_perdiem:,.0f}"})
            issues.append(f"Per diem Rs.{per_diem:,.0f} exceeds max Rs.{max_perdiem:,.0f}")
        else:
            checks.append({"category": "Per Diem", "status": "green", "message": f"Rs.{per_diem:,.0f}/day within policy"})

    # Determine overall status
    statuses = [c["status"] for c in checks]
    if "red" in statuses:
        overall = "violation"
    elif "amber" in statuses:
        overall = "warning"
    else:
        overall = "compliant"

    # Auto-approve eligibility
    auto_approve_limit = policy.get("auto_approve_below", 15000)
    can_auto_approve = overall == "compliant" and estimated_total < auto_approve_limit

    return {
        "overall_status": overall,
        "checks": checks,
        "issues": issues,
        "can_auto_approve": can_auto_approve,
        "auto_approve_limit": auto_approve_limit,
        "policy_name": policy.get("name", "Standard Corporate Policy"),
    }
