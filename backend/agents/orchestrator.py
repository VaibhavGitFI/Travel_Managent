"""
TravelSync Pro — Master Orchestrator (A2A Architecture)
Coordinates all agents in parallel, assembles comprehensive trip plan.
Implements Google's Agent-to-Agent communication protocol.
"""
import sys
import os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from concurrent.futures import ThreadPoolExecutor, as_completed
from services.gemini_service import gemini

logger = logging.getLogger(__name__)


def get_gemini_model():
    """Backward-compatible model getter."""
    return gemini.get_model("flash")


def plan_trip(trip_input: dict) -> dict:
    """
    Main A2A orchestrator entry point.
    Runs all agents in parallel for maximum performance.
    """
    # Normalize input
    destination = trip_input.get("destination", "Mumbai")
    origin = trip_input.get("origin", "")
    num_travelers = int(trip_input.get("num_travelers", 1))
    duration_days = int(trip_input.get("duration_days", 3))
    purpose = trip_input.get("purpose", "client meeting")
    travel_dates = trip_input.get("travel_dates", "")
    meeting_time = trip_input.get("meeting_time", "10:00 AM")
    budget = trip_input.get("budget", "moderate")
    client_address = trip_input.get("client_address", "")
    is_rural = trip_input.get("is_rural", False)
    require_veg = trip_input.get("require_veg", False)
    user_id = trip_input.get("user_id", 1)

    # Build travelers list
    travelers = []
    traveler_names = trip_input.get("traveler_names", [])
    traveler_origins = trip_input.get("traveler_origins", [])
    if traveler_origins:
        for i, orig in enumerate(traveler_origins):
            if orig.strip():
                travelers.append({
                    "name": traveler_names[i] if i < len(traveler_names) else f"Traveler {i+1}",
                    "origin": orig.strip()
                })
    if not travelers and origin:
        travelers = [{"name": "Traveler 1", "origin": origin}]
    if not travelers:
        travelers = [{"name": f"Traveler {i+1}", "origin": "Mumbai"} for i in range(num_travelers)]

    trip_details = {
        "destination": destination,
        "origin": travelers[0]["origin"] if travelers else origin,
        "travelers": travelers,
        "num_travelers": len(travelers),
        "duration_days": duration_days,
        "purpose": purpose,
        "travel_dates": travel_dates,
        "meeting_time": meeting_time,
        "budget": budget,
        "client_address": client_address,
        "is_rural": is_rural,
        "require_veg": require_veg,
        "start_date": travel_dates.split(" to ")[0].strip() if travel_dates else "",
    }

    # Run all agents in parallel
    results = _run_agents_parallel(trip_details, user_id)

    # Build comprehensive response
    return {
        "success": True,
        "ai_powered": gemini.is_available,
        "trip_summary": _build_summary(trip_details),
        "hotels": results.get("hotels", {}),
        "travel": results.get("travel", {}),
        "weather": results.get("weather", {}),
        "checklist": results.get("checklist", {}),
        "guide": results.get("guide", {}),
        "meetings": results.get("meetings", {}),
        "metadata": {
            "destination": destination,
            "duration_days": duration_days,
            "num_travelers": len(travelers),
            "travelers": travelers,
            "purpose": purpose,
            "travel_dates": travel_dates,
            "is_rural": is_rural,
            "data_sources": _get_data_sources(results),
        },
    }


def _run_agents_parallel(trip_details: dict, user_id: int) -> dict:
    """Execute all agents concurrently using ThreadPoolExecutor."""
    destination = trip_details["destination"]
    duration_days = trip_details["duration_days"]
    travel_dates = trip_details.get("travel_dates", "")

    # Parse dates for weather
    dates = travel_dates.split(" to ") if travel_dates else []
    start_date = dates[0].strip() if dates else ""
    end_date = dates[-1].strip() if dates else ""

    def run_hotels():
        from agents.hotel_agent import search_hotels
        return "hotels", search_hotels(trip_details)

    def run_travel():
        from agents.travel_mode_agent import recommend_travel_mode
        return "travel", recommend_travel_mode(trip_details)

    def run_weather():
        from agents.weather_agent import get_travel_weather
        return "weather", get_travel_weather(destination, start_date, end_date)

    def run_checklist():
        from agents.checklist_agent import generate_checklist
        return "checklist", generate_checklist(trip_details)

    def run_guide():
        from agents.guide_agent import get_destination_guide
        return "guide", get_destination_guide(destination, duration_days)

    def run_meetings():
        from agents.meeting_agent import get_meetings_for_destination
        return "meetings", get_meetings_for_destination(destination, user_id, travel_dates)

    results = {}
    tasks = [run_hotels, run_travel, run_weather, run_checklist, run_guide, run_meetings]

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(task): task.__name__ for task in tasks}
        for future in as_completed(futures, timeout=30):
            try:
                key, value = future.result(timeout=25)
                results[key] = value
            except Exception as e:
                task_name = futures[future]
                logger.warning("[Orchestrator] Agent %s failed: %s", task_name, e)
                results[task_name.replace("run_", "")] = {"error": str(e)}

    return results


def _build_summary(trip_details: dict) -> dict:
    destination = trip_details["destination"]
    duration_days = trip_details["duration_days"]
    purpose = trip_details["purpose"]
    travelers = trip_details.get("travelers", [])
    travel_dates = trip_details.get("travel_dates", "Not specified")
    is_rural = trip_details.get("is_rural", False)

    major_metros = ["mumbai", "delhi", "bangalore", "bengaluru", "hyderabad",
                    "chennai", "pune", "kolkata", "ahmedabad", "jaipur"]
    trip_type = ("Rural / Outstation Visit"
                  if is_rural or not any(m in destination.lower() for m in major_metros)
                  else "Metro City Business Visit")

    origins = list(set(t.get("origin", "") for t in travelers))
    is_multi_origin = len(origins) > 1

    return {
        "destination": destination,
        "origin_cities": ", ".join(origins),
        "duration": f"{duration_days} day{'s' if duration_days > 1 else ''}",
        "purpose": purpose.title(),
        "trip_type": trip_type,
        "travelers": travelers,
        "num_travelers": len(travelers),
        "travel_dates": travel_dates,
        "is_multi_origin": is_multi_origin,
        "requires_team_sync": is_multi_origin,
        "is_rural": is_rural,
        "status": "Planned ✅",
        "long_stay": duration_days >= 5,
        "pg_recommended": duration_days >= 5,
    }


def _get_data_sources(results: dict) -> dict:
    """Summarize which data sources were used (live vs fallback)."""
    sources = {}
    for agent, result in results.items():
        if isinstance(result, dict):
            sources[agent] = result.get("data_source") or result.get("source") or "unknown"
    return sources
