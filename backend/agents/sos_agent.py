"""
TravelSync Pro — SOS Emergency Agent
Provides local emergency numbers by city/country and nearby hospital search.
"""
import logging
from services.maps_service import maps

logger = logging.getLogger(__name__)

# ── Local emergency numbers by city / country ──────────────────────────────
EMERGENCY_NUMBERS = {
    # India — universal
    "default_india": {
        "ambulance": "108",
        "police": "100",
        "fire": "101",
        "women_helpline": "1091",
        "tourist_helpline": "1800111363",
        "general": "112",
    },
    # India — city overrides
    "mumbai": {
        "ambulance": "108", "police": "100", "fire": "101",
        "traffic": "1095", "general": "112",
        "hospitals": ["KEM Hospital: +91-22-24136051", "Nair Hospital: +91-22-23027444"],
    },
    "delhi": {
        "ambulance": "102", "police": "100", "fire": "101",
        "traffic": "1095", "general": "112",
        "hospitals": ["AIIMS: +91-11-26588500", "Safdarjung: +91-11-26730000"],
    },
    "bangalore": {
        "ambulance": "108", "police": "100", "fire": "101", "general": "112",
        "hospitals": ["NIMHANS: +91-80-46110007", "Victoria Hospital: +91-80-26704097"],
    },
    "hyderabad": {
        "ambulance": "108", "police": "100", "fire": "101", "general": "112",
    },
    "chennai": {
        "ambulance": "108", "police": "100", "fire": "101", "general": "112",
    },
    "kolkata": {
        "ambulance": "1800-345-5644", "police": "100", "fire": "101", "general": "112",
    },
    "pune": {
        "ambulance": "108", "police": "100", "fire": "101", "general": "112",
    },
    # International
    "usa": {"ambulance": "911", "police": "911", "fire": "911", "general": "911"},
    "uk": {"ambulance": "999", "police": "999", "fire": "999", "general": "999"},
    "uae": {"ambulance": "998", "police": "999", "fire": "997", "general": "999"},
    "dubai": {"ambulance": "998", "police": "999", "fire": "997", "general": "999"},
    "singapore": {"ambulance": "995", "police": "999", "fire": "995", "general": "999"},
    "australia": {"ambulance": "000", "police": "000", "fire": "000", "general": "000"},
    "germany": {"ambulance": "112", "police": "110", "fire": "112", "general": "112"},
    "france": {"ambulance": "15", "police": "17", "fire": "18", "general": "112"},
    "japan": {"ambulance": "119", "police": "110", "fire": "119", "general": "119"},
    "default": {
        "ambulance": "112",
        "police": "112",
        "fire": "112",
        "general": "112",
        "note": "112 is the international emergency number recognized in 100+ countries",
    },
}


def get_emergency_contacts(city: str = "") -> dict:
    """Return emergency contact numbers for a given city or country."""
    city_lower = (city or "").lower().strip()

    # Direct city match
    if city_lower in EMERGENCY_NUMBERS:
        numbers = dict(EMERGENCY_NUMBERS[city_lower])
        numbers.setdefault("general", "112")
        return {
            "success": True,
            "city": city,
            "numbers": numbers,
            "source": "database",
        }

    # Country detection from city string
    country_keywords = {
        "usa": ["new york", "los angeles", "chicago", "san francisco", "houston"],
        "uk": ["london", "manchester", "birmingham", "edinburgh"],
        "uae": ["abu dhabi"],
        "singapore": ["singapore"],
        "australia": ["sydney", "melbourne", "brisbane", "perth"],
        "germany": ["berlin", "frankfurt", "munich", "hamburg"],
        "france": ["paris", "lyon", "marseille"],
        "japan": ["tokyo", "osaka", "kyoto", "nagoya"],
    }
    for country, cities in country_keywords.items():
        if any(c in city_lower for c in cities):
            numbers = dict(EMERGENCY_NUMBERS.get(country, EMERGENCY_NUMBERS["default"]))
            numbers.setdefault("general", "112")
            return {
                "success": True,
                "city": city,
                "country": country,
                "numbers": numbers,
                "source": "database",
            }

    # Check if city is in India (default Indian numbers)
    indian_cities = [
        "ahmedabad", "surat", "jaipur", "lucknow", "kochi", "nagpur", "bhopal",
        "indore", "chandigarh", "goa", "varanasi", "amritsar", "agra", "patna",
    ]
    if any(c in city_lower for c in indian_cities) or city_lower.endswith("india"):
        numbers = dict(EMERGENCY_NUMBERS["default_india"])
        return {
            "success": True,
            "city": city,
            "country": "India",
            "numbers": numbers,
            "source": "database",
        }

    # Default fallback
    return {
        "success": True,
        "city": city or "Unknown",
        "numbers": dict(EMERGENCY_NUMBERS["default"]),
        "source": "default",
    }


def find_nearby_hospitals(city: str, limit: int = 5) -> list:
    """Search for hospitals near the given city using Google Maps."""
    if not maps.configured:
        return [{
            "name": "Google Maps not configured",
            "note": "Set GOOGLE_MAPS_API_KEY to find nearby hospitals in real-time",
            "source": "fallback",
        }]

    try:
        coord = maps.geocode(city)
        if not coord:
            return []

        location = {"lat": coord["lat"], "lng": coord["lng"]}
        places = maps.nearby_places(location, "hospital", radius=5000)
        hospitals = []
        for p in (places or [])[:limit]:
            hospitals.append({
                "name": p.get("name", ""),
                "vicinity": p.get("vicinity", ""),
                "rating": p.get("rating"),
                "open_now": p.get("opening_hours", {}).get("open_now"),
                "place_id": p.get("place_id", ""),
                "source": "google_maps",
            })
        return hospitals
    except Exception as e:
        logger.warning("[SOS] Hospital search failed: %s", e)
        return []
