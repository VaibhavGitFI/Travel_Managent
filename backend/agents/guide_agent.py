"""
TravelSync Pro — Destination Guide Agent
Real places via Google Maps Places API + Gemini AI local knowledge.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.maps_service import maps
from services.gemini_service import gemini
from services.weather_service import weather


def get_destination_guide(destination: str, duration_days: int = 3, model=None) -> dict:
    """
    Comprehensive destination guide using Google Maps + Gemini.
    """
    coord = maps.geocode(destination)
    location = {"lat": coord["lat"], "lng": coord["lng"]}

    # Fetch from Google Maps Places API
    tourist_spots = maps.nearby_places(location, "tourist_attraction", radius=5000)
    restaurants = maps.nearby_places(location, "restaurant", radius=2000,
                                      keyword="top rated")
    hospitals = maps.nearby_places(location, "hospital", radius=3000)
    atms = maps.nearby_places(location, "atm", radius=1000)

    # Current weather
    current_weather = weather.get_current(destination)

    # Gemini-powered rich content
    ai_guide = _generate_ai_guide(destination, duration_days)

    # Build day-wise plan
    day_plan = _build_day_plan(destination, duration_days, tourist_spots, ai_guide)

    return {
        "success": True,
        "destination": destination,
        "coordinates": {"lat": coord["lat"], "lng": coord["lng"]},
        "tourist_spots": _format_places(tourist_spots, "tourist_attraction"),
        "restaurants": _format_places(restaurants, "restaurant"),
        "hospitals": _format_places(hospitals, "hospital"),
        "atms": _format_places(atms, "atm"),
        "day_plan": day_plan,
        "ai_insights": ai_guide,
        "current_weather": current_weather,
        "static_map_url": maps.get_static_map_url(coord["lat"], coord["lng"]),
        "google_maps_url": f"https://www.google.com/maps/search/{destination.replace(' ', '+')}",
        "data_source": "google_maps" if maps.configured else "gemini_fallback",
    }


# Backward-compat alias used by orchestrator
def get_tourist_spots(destination: str, duration_days: int = 3, model=None) -> dict:
    return get_destination_guide(destination, duration_days, model)


def _generate_ai_guide(destination: str, duration: int) -> dict:
    """Use Gemini to generate rich local knowledge."""
    if not gemini.is_available:
        return {}

    prompt = f"""
You are a local expert guide for {destination}, India.
Create a practical travel guide for a {duration}-day corporate trip.

Return JSON:
{{
  "city_brief": "2-sentence overview",
  "best_areas_to_stay": ["area1", "area2"],
  "must_try_food": [
    {{"dish": "name", "where": "restaurant/area", "price_range": "₹X-Y"}}
  ],
  "local_transport": {{
    "metro": "yes/no + key lines",
    "auto_rickshaw": "availability + approx fare",
    "cab": "Ola/Uber availability",
    "best_option": "recommendation"
  }},
  "cultural_notes": ["tip1", "tip2"],
  "business_districts": ["area1", "area2"],
  "safety_tips": ["tip1", "tip2"],
  "useful_apps": ["app1 - use case"],
  "emergency_numbers": {{
    "police": "100",
    "ambulance": "108",
    "fire": "101",
    "local_hospital": "name and number if known"
  }}
}}
"""
    return gemini.generate_json(prompt) or {}


def _build_day_plan(destination: str, duration: int, spots: list, ai_guide: dict) -> list:
    """Build a day-wise itinerary."""
    if gemini.is_available:
        spot_names = [p.get("name") for p in spots[:8] if p.get("name")]
        prompt = f"""
Day-wise itinerary for {duration} days in {destination} (corporate trip).
Available spots: {', '.join(spot_names) if spot_names else 'major attractions'}.
Keep evenings free for client dinners.

Return JSON array:
[
  {{
    "day": 1,
    "theme": "Day theme",
    "morning": "activity",
    "afternoon": "activity",
    "evening": "dinner suggestion",
    "travel_tip": "quick tip"
  }}
]
"""
        result = gemini.generate_json(prompt)
        if result and isinstance(result, list):
            return result

    # Minimal fallback
    return [
        {"day": i + 1, "theme": f"Day {i + 1} in {destination}",
         "morning": "Business meetings / Work",
         "afternoon": "Explore local area",
         "evening": "Team dinner at local restaurant"}
        for i in range(duration)
    ]


def _format_places(places: list, place_type: str) -> list:
    """Format Google Places API results."""
    if not places:
        return []
    return [
        {
            "name": p.get("name"),
            "rating": p.get("rating"),
            "ratings_count": p.get("user_ratings_total"),
            "vicinity": p.get("vicinity"),
            "open_now": p.get("open_now"),
            "maps_url": f"https://www.google.com/maps/place/?q=place_id:{p.get('place_id')}" if p.get("place_id") else "",
            "type": place_type,
            "source": p.get("source", "google_maps"),
        }
        for p in places
    ]
