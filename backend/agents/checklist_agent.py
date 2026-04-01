"""
TravelSync Pro — Checklist & Medical Guide Agent
Dynamic Gemini-powered packing lists and travel preparation.
"""
import sys
import os
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

from services.gemini_service import gemini
from services.weather_service import weather
from services.maps_service import maps

EMERGENCY_INFO = {
    "mumbai": {"hospital": "KEM Hospital: 022-24107000", "police": "Mumbai Police: 100", "fire": "101"},
    "delhi": {"hospital": "AIIMS: 011-26588500", "police": "Delhi Police: 100", "fire": "101"},
    "bangalore": {"hospital": "Victoria Hospital: 080-22971440", "police": "Bangalore Police: 100", "fire": "101"},
    "bengaluru": {"hospital": "Victoria Hospital: 080-22971440", "police": "Bangalore Police: 100", "fire": "101"},
    "hyderabad": {"hospital": "Osmania Hospital: 040-24600124", "police": "Hyderabad Police: 100", "fire": "101"},
    "chennai": {"hospital": "Government General: 044-25305000", "police": "Chennai Police: 100", "fire": "101"},
    "kolkata": {"hospital": "SSKM: 033-22044440", "police": "Kolkata Police: 100", "fire": "101"},
    "pune": {"hospital": "Sassoon Hospital: 020-26128000", "police": "Pune Police: 100", "fire": "101"},
    "default": {"hospital": "Nearest hospital — call 108", "police": "100", "fire": "101"},
}


def generate_checklist(trip_details: dict, model=None) -> dict:
    """Generate a dynamic, context-aware packing + preparation checklist."""
    destination = trip_details.get("destination", "")
    duration_days = int(trip_details.get("duration_days", 3))
    purpose = trip_details.get("purpose", "business")
    is_rural = trip_details.get("is_rural", False)
    budget = trip_details.get("budget", "moderate")
    travel_dates = trip_details.get("travel_dates", "")

    # Get weather context
    weather_data = {}
    try:
        weather_data = weather.get_current(destination)
    except Exception as exc:
        logger.warning("[Checklist] Weather lookup failed for %s: %s", destination, exc)

    weather_context = ""
    if weather_data.get("temp"):
        weather_context = (f"Current weather: {weather_data['temp']}°C, "
                            f"{weather_data.get('description', '')}. "
                            f"Humidity: {weather_data.get('humidity', '')}%.")

    if gemini.is_available:
        prompt = f"""
Generate a practical packing checklist for a corporate trip.
Destination: {destination}
Duration: {duration_days} days
Purpose: {purpose}
Rural/Remote: {'Yes' if is_rural else 'No'}
{weather_context}

Return JSON:
{{
  "documents": ["item1", "item2"],
  "clothing": ["item1 (weather-specific)"],
  "electronics": ["item1"],
  "toiletries": ["item1"],
  "medical": ["item1"],
  "business_items": ["item1"],
  "rural_extras": ["item1"],
  "tips": ["tip1", "tip2"]
}}
Only include rural_extras if rural=Yes. Be specific to {destination}'s climate and culture.
"""
        result = gemini.generate_json(prompt)
        if result:
            result["destination"] = destination
            result["duration"] = duration_days
            result["weather"] = weather_data
            result["ai_powered"] = True
            result["emergency_contacts"] = EMERGENCY_INFO.get(
                destination.lower(), EMERGENCY_INFO["default"])
            return result

    # Fallback checklist
    return _fallback_checklist(destination, duration_days, is_rural, weather_data)


def get_medical_guidance(symptoms: str, destination: str, model=None) -> dict:
    """
    AI-powered medical guidance for travel ailments.
    NOT a substitute for professional medical advice.
    """
    # Get nearby hospitals via Google Maps
    hospitals = []
    if maps.configured:
        coords = maps.geocode(destination)
        loc = {"lat": coords["lat"], "lng": coords["lng"]}
        hospital_places = maps.nearby_places(loc, "hospital", radius=3000)
        hospitals = [
            {"name": p.get("name"), "vicinity": p.get("vicinity"),
             "rating": p.get("rating"), "maps_url": f"https://www.google.com/maps/place/?q=place_id:{p.get('place_id')}"}
            for p in hospital_places[:3]
        ]

    guidance = {}
    if gemini.is_available and symptoms:
        prompt = f"""
A business traveler in {destination} reports: {symptoms}

Provide basic first-aid guidance. This is NOT medical diagnosis.
Return JSON:
{{
  "disclaimer": "This is general guidance only. Seek professional medical care for serious symptoms.",
  "immediate_steps": ["step1", "step2"],
  "when_to_see_doctor": "description",
  "common_medications": ["OTC med name - use case"],
  "hydration_advice": "tip",
  "rest_recommendation": "tip",
  "emergency_threshold": "symptoms that need 108 immediately"
}}
"""
        guidance = gemini.generate_json(prompt) or {}

    return {
        "success": True,
        "destination": destination,
        "symptoms": symptoms,
        "guidance": guidance,
        "nearby_hospitals": hospitals,
        "emergency_contacts": EMERGENCY_INFO.get(destination.lower(), EMERGENCY_INFO["default"]),
        "universal_emergency": {"ambulance": "108", "police": "100", "fire": "101"},
        "disclaimer": "This is general information only. Consult a qualified doctor for medical advice.",
    }


def _fallback_checklist(destination: str, duration: int, is_rural: bool,
                         weather_data: dict) -> dict:
    temp = weather_data.get("temp", 28) if weather_data else 28
    is_hot = temp > 30
    is_cold = temp < 18

    clothing = ["Formal shirts/blouses (3-4)", "Business trousers/skirts (2-3)",
                "Comfortable formal shoes", "Casual change of clothes"]
    if is_cold:
        clothing += ["Warm jacket/sweater", "Thermal innerwear"]
    elif is_hot:
        clothing += ["Light cotton fabrics", "Sunscreen SPF 50"]

    return {
        "documents": [
            "Company ID card", "Aadhar card / Passport",
            "Travel authorization letter", "Hotel booking confirmation",
            "Flight/train tickets", "Business cards", "Expense forms",
        ],
        "clothing": clothing,
        "electronics": [
            "Laptop + charger", "Mobile phone + charger",
            "Power bank (20000mAh)", "Universal adapter",
            "Earphones/headset for calls",
        ],
        "toiletries": ["Toothbrush & paste", "Deodorant", "Hand sanitizer", "Face wash"],
        "medical": ["Pain reliever (Crocin/Dolo 650)", "Antacids", "ORS sachets",
                    "Any prescription medicines (extra supply)"],
        "business_items": ["Notebook + pen", "Business presentation folder",
                            "Portable WiFi/SIM card"],
        "rural_extras": ["Insect repellent", "Water purification tablets",
                          "Extra cash (rural ATMs limited)"] if is_rural else [],
        "tips": [
            f"Book flexible tickets for {destination} — unexpected delays common",
            "Carry physical copies of all important documents",
            "Download Google Maps offline for {destination}",
        ],
        "destination": destination,
        "duration": duration,
        "weather": weather_data,
        "ai_powered": False,
        "emergency_contacts": EMERGENCY_INFO.get(destination.lower(), EMERGENCY_INFO["default"]),
    }
