"""
TravelSync Pro — Budget Forecasting Agent
Predicts trip cost ranges using historical expense data + Amadeus price metrics + Gemini insights.
"""
import logging
from datetime import datetime, date

from database import get_db
from services.amadeus_service import amadeus
from services.gemini_service import gemini

logger = logging.getLogger(__name__)

# Per-diem tier rates (INR/day) — mirrors requests.py _PER_DIEM_TIERS
_TIER_RATES = {
    "tier1": {
        "hotel": 6000, "meals": 1200, "local_transport": 800, "incidentals": 500,
        "cities": ["mumbai", "delhi", "bangalore", "bengaluru", "hyderabad",
                   "chennai", "kolkata", "pune", "gurgaon", "noida"],
    },
    "tier2": {
        "hotel": 3500, "meals": 800, "local_transport": 500, "incidentals": 300,
        "cities": ["ahmedabad", "jaipur", "surat", "lucknow", "kochi", "nagpur",
                   "bhopal", "indore", "chandigarh", "goa", "vadodara"],
    },
    "international": {
        "hotel": 15000, "meals": 3000, "local_transport": 2000, "incidentals": 1000,
        "cities": ["new york", "london", "singapore", "dubai", "tokyo", "paris",
                   "berlin", "sydney", "toronto", "san francisco"],
    },
    "tier3": {
        "hotel": 2000, "meals": 500, "local_transport": 300, "incidentals": 200,
        "cities": [],
    },
}

# Base flight cost estimates (INR, round-trip per person) when no Amadeus data
_FLIGHT_ESTIMATES = {
    "domestic": {"min": 4000, "mid": 7000, "max": 14000},
    "international": {"min": 35000, "mid": 60000, "max": 120000},
}


def _get_tier(destination: str) -> tuple[str, dict]:
    dest_lower = destination.lower().strip()
    for tier_name, info in _TIER_RATES.items():
        if any(c in dest_lower for c in info.get("cities", [])):
            return tier_name, info
    return "tier3", _TIER_RATES["tier3"]


def _date_diff(start: str, end: str) -> int:
    """Return duration in days between two YYYY-MM-DD strings."""
    try:
        d1 = datetime.strptime(start, "%Y-%m-%d").date()
        d2 = datetime.strptime(end, "%Y-%m-%d").date()
        return max(1, (d2 - d1).days + 1)
    except (ValueError, TypeError):
        return 1


def _pull_historical(destination: str) -> list[dict]:
    """Fetch completed/in_progress trips to this destination with their actual spend."""
    dest_lower = destination.lower().strip()
    try:
        db = get_db()
        rows = db.execute(
            """SELECT tr.request_id, tr.destination, tr.origin, tr.start_date, tr.end_date,
                      tr.duration_days, tr.estimated_total, tr.budget_inr, tr.trip_type,
                      tr.num_travelers,
                      COALESCE(SUM(e.invoice_amount), 0) AS actual_spend
               FROM travel_requests tr
               LEFT JOIN expenses_db e ON e.request_id = tr.request_id
               WHERE LOWER(tr.destination) LIKE ? AND tr.status IN ('completed', 'in_progress')
               GROUP BY tr.request_id
               LIMIT 20""",
            (f"%{dest_lower}%",)
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("[BudgetForecast] Historical query failed: %s", exc)
        return []


def forecast_budget(
    origin: str,
    destination: str,
    start_date: str,
    end_date: str,
    trip_type: str = "domestic",
    num_travelers: int = 1,
) -> dict:
    """
    Generate a budget forecast for a trip.

    Returns:
        {
          success: bool,
          forecast: {min, mid, max},
          breakdown: {flight, hotel, per_diem, misc},
          historical_trips: int,
          historical_avg: float | None,
          confidence: "high" | "medium" | "low",
          ai_insight: str | None,
          source: str,
        }
    """
    duration = _date_diff(start_date, end_date)
    n = max(1, int(num_travelers or 1))
    tier_name, tier_rates = _get_tier(destination)

    # 1. Historical data
    history = _pull_historical(destination)
    historical_avg = None
    if history:
        spend_values = []
        for h in history:
            val = h.get("actual_spend") or h.get("estimated_total") or h.get("budget_inr") or 0
            if val and float(val) > 0:
                spend_values.append(float(val))
        if spend_values:
            historical_avg = sum(spend_values) / len(spend_values)

    # 2. Amadeus flight price analysis
    amadeus_price = None
    if amadeus.configured and start_date:
        try:
            origin_code = amadeus.get_airport_code(origin) if origin else None
            dest_code = amadeus.get_airport_code(destination)
            if origin_code and dest_code:
                price_data = amadeus.get_price_analysis(origin_code, dest_code, start_date)
                if price_data.get("source") == "amadeus_live":
                    amadeus_price = price_data.get("level")
        except Exception as exc:
            logger.debug("[BudgetForecast] Amadeus price skip: %s", exc)

    # 3. Build cost breakdown
    # Flight (round-trip per traveler)
    is_intl = trip_type == "international" or tier_name == "international"
    base_flight = _FLIGHT_ESTIMATES["international" if is_intl else "domestic"]

    # Scale flight by traveler count
    flight_min = base_flight["min"] * n
    flight_mid = base_flight["mid"] * n
    flight_max = base_flight["max"] * n

    if amadeus_price and str(amadeus_price).replace(".", "").isdigit():
        # Use Amadeus reference price as mid
        ref = float(amadeus_price) * n
        flight_min = int(ref * 0.8)
        flight_mid = int(ref)
        flight_max = int(ref * 1.4)

    # Hotel
    hotel_daily = tier_rates.get("hotel", 3000)
    hotel_total = hotel_daily * duration * n

    # Per diem (meals + transport + incidentals) — company pays one set per traveler
    daily_allowance = (
        tier_rates.get("meals", 600)
        + tier_rates.get("local_transport", 400)
        + tier_rates.get("incidentals", 300)
    )
    per_diem_total = daily_allowance * duration * n

    # Misc buffer (visas, tips, extras)
    subtotal_mid = flight_mid + hotel_total + per_diem_total
    misc = int(subtotal_mid * 0.08)

    # Final ranges
    forecast_min = int(flight_min + hotel_total * 0.85 + per_diem_total + misc * 0.5)
    forecast_mid = int(flight_mid + hotel_total + per_diem_total + misc)
    forecast_max = int(flight_max + hotel_total * 1.2 + per_diem_total * 1.1 + misc * 1.5)

    # If historical average exists, blend it in (weight 40% history, 60% formula)
    if historical_avg:
        forecast_min = int(forecast_min * 0.6 + historical_avg * 0.6 * 0.4)
        forecast_mid = int(forecast_mid * 0.6 + historical_avg * 0.4)
        forecast_max = int(forecast_max * 0.6 + historical_avg * 1.3 * 0.4)

    # 4. Confidence level
    if len(history) >= 3:
        confidence = "high"
    elif len(history) >= 1 or amadeus_price:
        confidence = "medium"
    else:
        confidence = "low"

    # 5. AI narrative insight
    ai_insight = None
    if gemini.is_available:
        insight_prompt = (
            f"Give a short 2-sentence budget insight for a {duration}-day {trip_type} "
            f"business trip from {origin or 'origin'} to {destination} for {n} traveler(s). "
            f"Estimated range: ₹{forecast_min:,} – ₹{forecast_max:,} INR. "
            f"Historical trips to this destination: {len(history)}. "
            f"Focus on cost-saving tips and key expense drivers. Be concise and practical."
        )
        ai_insight = gemini.generate(insight_prompt)

    return {
        "success": True,
        "destination": destination,
        "origin": origin,
        "duration_days": duration,
        "num_travelers": n,
        "trip_type": trip_type,
        "tier": tier_name,
        "forecast": {
            "min": forecast_min,
            "mid": forecast_mid,
            "max": forecast_max,
            "currency": "INR",
        },
        "breakdown": {
            "flight": {"min": flight_min, "mid": flight_mid, "max": flight_max},
            "hotel": hotel_total,
            "per_diem": per_diem_total,
            "misc_buffer": misc,
        },
        "historical_trips": len(history),
        "historical_avg": round(historical_avg, 0) if historical_avg else None,
        "amadeus_price_data": bool(amadeus_price),
        "confidence": confidence,
        "ai_insight": ai_insight,
        "source": "budget_forecast_agent",
    }
