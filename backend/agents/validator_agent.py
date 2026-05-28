"""
TravelSync Pro — Multi-Agent Validation Layer
Cross-validates trip plan outputs for budget coherence, date coherence, and compliance.
Runs after all agents complete; returns validation_flags[] with severity levels.
"""
import logging
import re
from datetime import datetime, date

from services.gemini_service import gemini

logger = logging.getLogger(__name__)

SEVERITY_ERROR   = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO    = "info"


def validate_trip_plan(trip_details: dict, agent_results: dict) -> dict:
    """
    Validate trip plan outputs from all agents.

    Args:
        trip_details: the normalized trip input dict
        agent_results: the dict returned by _run_agents_parallel (hotels, travel, weather, etc.)

    Returns:
        {
          "validation_flags": [{"code": str, "severity": str, "message": str, "field": str}],
          "overall": "pass" | "warn" | "fail",
          "ai_review": str | None,
        }
    """
    flags = []

    flags.extend(_check_dates(trip_details))
    flags.extend(_check_budget_coherence(trip_details))
    flags.extend(_check_compliance(trip_details))
    flags.extend(_check_agent_data(trip_details, agent_results))

    # Derive overall status
    severities = {f["severity"] for f in flags}
    if SEVERITY_ERROR in severities:
        overall = "fail"
    elif SEVERITY_WARNING in severities:
        overall = "warn"
    else:
        overall = "pass"

    # AI narrative review (only when there are flags worth explaining)
    ai_review = None
    if gemini.is_available and flags:
        flag_text = "\n".join(f"- [{f['severity'].upper()}] {f['message']}" for f in flags)
        prompt = (
            f"A travel request for {trip_details.get('destination')} "
            f"({trip_details.get('duration_days')} days) has these validation issues:\n{flag_text}\n\n"
            "In 2 sentences, explain the most important issue and suggest the best corrective action. Be concise."
        )
        ai_review = gemini.generate(prompt)

    return {
        "validation_flags": flags,
        "overall": overall,
        "ai_review": ai_review,
        "flag_count": len(flags),
    }


# ── Individual Validators ─────────────────────────────────────────────────────

def _check_dates(trip: dict) -> list[dict]:
    flags = []
    today = date.today()

    start_raw = trip.get("start_date") or trip.get("travel_dates", "").split(" to ")[0].strip()
    end_raw = trip.get("end_date") or (trip.get("travel_dates", "").split(" to ")[-1].strip())
    duration = int(trip.get("duration_days") or 1)

    start = _parse_date(start_raw)
    end = _parse_date(end_raw)

    if not start:
        flags.append({
            "code": "MISSING_START_DATE",
            "severity": SEVERITY_WARNING,
            "message": "Travel start date is not specified.",
            "field": "start_date",
        })
    else:
        if start < today:
            flags.append({
                "code": "START_DATE_PAST",
                "severity": SEVERITY_ERROR,
                "message": f"Travel start date {start_raw} is in the past.",
                "field": "start_date",
            })
        # Advance booking check
        delta_days = (start - today).days if start >= today else 0
        if 0 < delta_days < 3:
            flags.append({
                "code": "SHORT_ADVANCE_BOOKING",
                "severity": SEVERITY_WARNING,
                "message": f"Trip starts in {delta_days} day(s). Policy requires 3+ days advance booking.",
                "field": "start_date",
            })

    if start and end:
        if end < start:
            flags.append({
                "code": "END_BEFORE_START",
                "severity": SEVERITY_ERROR,
                "message": f"Return date {end_raw} is before departure date {start_raw}.",
                "field": "end_date",
            })
        else:
            actual_duration = (end - start).days + 1
            if duration > 0 and abs(actual_duration - duration) > 1:
                flags.append({
                    "code": "DURATION_MISMATCH",
                    "severity": SEVERITY_INFO,
                    "message": (
                        f"Declared duration ({duration} days) does not match dates "
                        f"({actual_duration} days). Using date-derived value."
                    ),
                    "field": "duration_days",
                })

    return flags


def _check_budget_coherence(trip: dict) -> list[dict]:
    flags = []
    destination = trip.get("destination", "")
    duration = max(1, int(trip.get("duration_days") or 1))
    trip_type = trip.get("trip_type") or ("international" if _is_international(destination) else "domestic")
    budget_raw = trip.get("budget_inr") or trip.get("estimated_total") or 0

    try:
        budget = float(budget_raw)
    except (ValueError, TypeError):
        budget = 0.0

    if budget <= 0:
        return flags  # No budget to validate

    # Minimum reasonable budgets (INR) per day based on trip type
    min_daily = 3000 if trip_type == "domestic" else 15000
    min_total = min_daily * duration

    if budget < min_total * 0.5:
        flags.append({
            "code": "BUDGET_TOO_LOW",
            "severity": SEVERITY_WARNING,
            "message": (
                f"Budget ₹{budget:,.0f} may be insufficient for a {duration}-day {trip_type} trip "
                f"to {destination}. Estimated minimum: ₹{min_total:,.0f}."
            ),
            "field": "estimated_budget",
        })

    # Check for suspiciously round or zero amounts
    if budget > 0 and budget % 100000 == 0 and budget > 100000:
        flags.append({
            "code": "ROUND_BUDGET_PLACEHOLDER",
            "severity": SEVERITY_INFO,
            "message": f"Budget ₹{budget:,.0f} appears to be a placeholder. Consider refining with the budget forecast.",
            "field": "estimated_budget",
        })

    return flags


def _check_compliance(trip: dict) -> list[dict]:
    flags = []
    flight_class = (trip.get("flight_class") or "economy").lower()
    duration = max(1, int(trip.get("duration_days") or 1))
    num_travelers = max(1, int(trip.get("num_travelers") or 1))
    trip_type = trip.get("trip_type") or "domestic"

    # Flight class policy
    if flight_class in ("business", "first") and trip_type == "domestic":
        flags.append({
            "code": "FLIGHT_CLASS_UPGRADE",
            "severity": SEVERITY_WARNING,
            "message": f"{flight_class.title()} class selected for a domestic trip. Policy default is economy.",
            "field": "flight_class",
        })

    # Long duration without PG check
    if duration >= 5 and not trip.get("accommodation_notes"):
        flags.append({
            "code": "LONG_STAY_PG_SUGGESTED",
            "severity": SEVERITY_INFO,
            "message": f"Trip is {duration} days. Consider PG or serviced apartment for extended stays (cost saving).",
            "field": "duration_days",
        })

    # Too many travelers
    if num_travelers > 6:
        flags.append({
            "code": "LARGE_GROUP",
            "severity": SEVERITY_INFO,
            "message": f"{num_travelers} travelers. Confirm group booking limits with travel desk.",
            "field": "num_travelers",
        })

    return flags


def _check_agent_data(trip: dict, results: dict) -> list[dict]:
    """Check consistency of agent results against trip parameters."""
    flags = []
    destination = trip.get("destination", "")

    # Weather agent: check for extreme conditions
    weather = results.get("weather", {})
    if isinstance(weather, dict):
        alerts = weather.get("alerts") or []
        for alert in alerts[:2]:
            flags.append({
                "code": "WEATHER_ALERT",
                "severity": SEVERITY_WARNING,
                "message": f"Weather alert for {destination}: {alert}",
                "field": "destination",
            })
        # Check for monsoon/storm season warning in notes
        note = weather.get("note") or weather.get("forecast_note") or ""
        if any(w in note.lower() for w in ("monsoon", "cyclone", "storm", "hurricane", "typhoon", "flood")):
            flags.append({
                "code": "ADVERSE_WEATHER_SEASON",
                "severity": SEVERITY_WARNING,
                "message": f"Adverse weather season detected for {destination}: {note[:120]}",
                "field": "destination",
            })

    # Hotels agent: no hotels found
    hotels = results.get("hotels", {})
    if isinstance(hotels, dict):
        hotel_list = hotels.get("hotels") or hotels.get("options") or []
        if trip.get("duration_days", 1) > 0 and len(hotel_list) == 0 and hotels.get("source") != "error":
            flags.append({
                "code": "NO_HOTELS_FOUND",
                "severity": SEVERITY_INFO,
                "message": f"No hotels found for {destination}. Try adjusting budget or dates.",
                "field": "destination",
            })

    # Travel agent: flight not available
    travel = results.get("travel", {})
    if isinstance(travel, dict):
        modes = travel.get("modes", {})
        if trip.get("trip_type") == "international" and "flight" not in modes:
            flags.append({
                "code": "NO_FLIGHT_OPTIONS",
                "severity": SEVERITY_WARNING,
                "message": f"No flight options found for international trip to {destination}. Verify route.",
                "field": "destination",
            })

    return flags


def _parse_date(date_str: str) -> date | None:
    if not date_str or str(date_str).strip().lower() in ("", "null", "none"):
        return None
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _is_international(destination: str) -> bool:
    intl_countries = [
        "usa", "uk", "london", "paris", "berlin", "dubai", "singapore", "tokyo",
        "sydney", "toronto", "new york", "hong kong", "bangkok", "seoul",
    ]
    d = destination.lower()
    return any(c in d for c in intl_countries)
