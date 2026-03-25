"""
TravelSync Pro — SOS Emergency Agent
Provides local emergency numbers by city/country, nearby hospital/police search,
reverse-geocoding from GPS coordinates, and embassy contacts.
"""
import logging
import requests as http_requests
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
        "disaster_mgmt": "1078",
        "general": "112",
    },
    # India — city overrides with hospital hotlines
    "mumbai": {
        "ambulance": "108", "police": "100", "fire": "101",
        "traffic": "1095", "general": "112",
        "hospitals": ["KEM Hospital: +91-22-24136051", "Nair Hospital: +91-22-23027444", "Lilavati Hospital: +91-22-27571000"],
    },
    "delhi": {
        "ambulance": "102", "police": "100", "fire": "101",
        "traffic": "1095", "general": "112",
        "hospitals": ["AIIMS: +91-11-26588500", "Safdarjung: +91-11-26730000", "Max Saket: +91-11-26515050"],
    },
    "bangalore": {
        "ambulance": "108", "police": "100", "fire": "101", "general": "112",
        "hospitals": ["NIMHANS: +91-80-46110007", "Victoria Hospital: +91-80-26704097", "Manipal Hospital: +91-80-25023456"],
    },
    "bengaluru": {
        "ambulance": "108", "police": "100", "fire": "101", "general": "112",
        "hospitals": ["NIMHANS: +91-80-46110007", "Victoria Hospital: +91-80-26704097", "Manipal Hospital: +91-80-25023456"],
    },
    "hyderabad": {
        "ambulance": "108", "police": "100", "fire": "101", "general": "112",
        "hospitals": ["NIMS: +91-40-23390202", "Apollo Hospital: +91-40-23607777"],
    },
    "chennai": {
        "ambulance": "108", "police": "100", "fire": "101", "general": "112",
        "hospitals": ["Apollo Chennai: +91-44-28290200", "Govt General Hospital: +91-44-25305000"],
    },
    "kolkata": {
        "ambulance": "1800-345-5644", "police": "100", "fire": "101", "general": "112",
        "hospitals": ["SSKM Hospital: +91-33-22041101", "RN Tagore Hospital: +91-33-66259999"],
    },
    "pune": {
        "ambulance": "108", "police": "100", "fire": "101", "general": "112",
        "hospitals": ["Sassoon Hospital: +91-20-26128000", "Ruby Hall Clinic: +91-20-66455100"],
    },
    "ahmedabad": {
        "ambulance": "108", "police": "100", "fire": "101", "general": "112",
    },
    "jaipur": {
        "ambulance": "108", "police": "100", "fire": "101", "general": "112",
    },
    # International
    "usa": {"ambulance": "911", "police": "911", "fire": "911", "general": "911",
            "poison_control": "1-800-222-1222"},
    "uk": {"ambulance": "999", "police": "999", "fire": "999", "general": "999",
           "non_emergency": "111"},
    "uae": {"ambulance": "998", "police": "999", "fire": "997", "general": "999",
            "tourist_police": "800-4888"},
    "dubai": {"ambulance": "998", "police": "999", "fire": "997", "general": "999",
              "tourist_police": "800-4888"},
    "singapore": {"ambulance": "995", "police": "999", "fire": "995", "general": "999"},
    "australia": {"ambulance": "000", "police": "000", "fire": "000", "general": "000",
                  "police_non_emergency": "131-444"},
    "germany": {"ambulance": "112", "police": "110", "fire": "112", "general": "112"},
    "france": {"ambulance": "15", "police": "17", "fire": "18", "general": "112"},
    "japan": {"ambulance": "119", "police": "110", "fire": "119", "general": "119"},
    "canada": {"ambulance": "911", "police": "911", "fire": "911", "general": "911"},
    "thailand": {"ambulance": "1669", "police": "191", "fire": "199", "general": "1155",
                 "tourist_police": "1155"},
    "malaysia": {"ambulance": "999", "police": "999", "fire": "994", "general": "999"},
    "indonesia": {"ambulance": "118", "police": "110", "fire": "113", "general": "112"},
    "south korea": {"ambulance": "119", "police": "112", "fire": "119", "general": "112"},
    "italy": {"ambulance": "118", "police": "113", "fire": "115", "general": "112"},
    "spain": {"ambulance": "112", "police": "091", "fire": "080", "general": "112"},
    "netherlands": {"ambulance": "112", "police": "112", "fire": "112", "general": "112"},
    "switzerland": {"ambulance": "144", "police": "117", "fire": "118", "general": "112"},
    "china": {"ambulance": "120", "police": "110", "fire": "119", "general": "112"},
    "default": {
        "ambulance": "112",
        "police": "112",
        "fire": "112",
        "general": "112",
        "note": "112 is the international emergency number recognized in 100+ countries",
    },
}

# Country detection keywords
COUNTRY_KEYWORDS = {
    "usa": ["new york", "los angeles", "chicago", "san francisco", "houston", "miami",
            "seattle", "boston", "washington", "las vegas", "orlando", "atlanta", "dallas",
            "denver", "philadelphia", "united states", "america"],
    "uk": ["london", "manchester", "birmingham", "edinburgh", "glasgow", "liverpool",
           "bristol", "oxford", "cambridge", "united kingdom", "england", "scotland"],
    "uae": ["abu dhabi", "sharjah", "ajman"],
    "dubai": ["dubai"],
    "singapore": ["singapore"],
    "australia": ["sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra"],
    "germany": ["berlin", "frankfurt", "munich", "hamburg", "cologne", "stuttgart"],
    "france": ["paris", "lyon", "marseille", "nice", "toulouse", "bordeaux"],
    "japan": ["tokyo", "osaka", "kyoto", "nagoya", "yokohama", "sapporo"],
    "canada": ["toronto", "vancouver", "montreal", "calgary", "ottawa", "edmonton"],
    "thailand": ["bangkok", "phuket", "chiang mai", "pattaya"],
    "malaysia": ["kuala lumpur", "penang", "langkawi", "johor"],
    "indonesia": ["jakarta", "bali", "surabaya", "yogyakarta"],
    "south korea": ["seoul", "busan", "incheon", "jeju"],
    "italy": ["rome", "milan", "florence", "venice", "naples"],
    "spain": ["madrid", "barcelona", "seville", "valencia"],
    "netherlands": ["amsterdam", "rotterdam", "the hague", "utrecht"],
    "switzerland": ["zurich", "geneva", "bern", "basel"],
    "china": ["beijing", "shanghai", "guangzhou", "shenzhen", "hong kong"],
}

INDIAN_CITIES = [
    "ahmedabad", "surat", "jaipur", "lucknow", "kochi", "nagpur", "bhopal",
    "indore", "chandigarh", "goa", "varanasi", "amritsar", "agra", "patna",
    "thiruvananthapuram", "coimbatore", "visakhapatnam", "mysore", "mysuru",
    "guwahati", "ranchi", "bhubaneswar", "dehradun", "shimla", "srinagar",
    "jodhpur", "udaipur", "aurangabad", "nashik", "rajkot", "vadodara",
    "noida", "gurgaon", "gurugram", "faridabad", "greater noida",
]

# Indian embassy contacts for major countries
EMBASSY_CONTACTS = {
    "usa": {"embassy": "Indian Embassy Washington: +1-202-939-7000", "hotline": "+1-202-939-9806"},
    "uk": {"embassy": "Indian High Commission London: +44-20-7836-8484", "hotline": "+44-7766-534-052"},
    "uae": {"embassy": "Indian Embassy Abu Dhabi: +971-2-449-2700", "hotline": "+971-56-546-7218"},
    "dubai": {"embassy": "Indian Consulate Dubai: +971-4-397-1222", "hotline": "+971-56-546-7218"},
    "singapore": {"embassy": "Indian High Commission: +65-6737-6777", "hotline": "+65-8126-9174"},
    "australia": {"embassy": "Indian High Commission Canberra: +61-2-6273-3999", "hotline": "+61-4-1512-6607"},
    "germany": {"embassy": "Indian Embassy Berlin: +49-30-25795-0", "hotline": "+49-160-9490-4442"},
    "france": {"embassy": "Indian Embassy Paris: +33-1-40-50-70-70", "hotline": "+33-6-1527-1530"},
    "japan": {"embassy": "Indian Embassy Tokyo: +81-3-3262-2391", "hotline": "+81-80-5765-6789"},
    "canada": {"embassy": "Indian High Commission Ottawa: +1-613-744-3751", "hotline": "+1-613-882-4425"},
    "thailand": {"embassy": "Indian Embassy Bangkok: +66-2-258-0300", "hotline": "+66-81-007-6880"},
    "malaysia": {"embassy": "Indian High Commission KL: +60-3-2093-3510", "hotline": "+60-12-398-7575"},
    "china": {"embassy": "Indian Embassy Beijing: +86-10-6532-1908", "hotline": "+86-18-6120-6768"},
}


def _nominatim_reverse(lat: float, lng: float) -> dict:
    """Free fallback reverse geocoding via OpenStreetMap Nominatim (no API key needed)."""
    try:
        resp = http_requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "addressdetails": 1, "zoom": 16},
            headers={"User-Agent": "TravelSyncPro/1.0"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if "error" not in data:
                addr = data.get("address", {})
                city = (
                    addr.get("city")
                    or addr.get("town")
                    or addr.get("village")
                    or addr.get("suburb")
                    or addr.get("county")
                    or addr.get("state_district")
                    or ""
                )
                country = addr.get("country", "")
                state = addr.get("state", "")
                postal = addr.get("postcode", "")
                formatted = data.get("display_name", "")
                return {
                    "formatted_address": formatted,
                    "city": city,
                    "state": state,
                    "country": country,
                    "postal_code": postal,
                    "lat": lat,
                    "lng": lng,
                    "source": "openstreetmap",
                }
    except Exception as e:
        logger.warning("[SOS] Nominatim reverse geocode failed: %s", e)
    return None  # signal caller to try geo-estimation


# ── Coordinate-based region estimation (no API needed) ───────────────────────
# Bounding boxes: (lat_min, lat_max, lng_min, lng_max, country, nearest_city)
_GEO_REGIONS = [
    (8.0, 37.0, 68.0, 97.5, "India", "Mumbai"),
    (24.0, 26.5, 51.0, 56.5, "UAE", "Dubai"),
    (1.15, 1.48, 103.6, 104.1, "Singapore", "Singapore"),
    (24.5, 49.5, -125.0, -66.0, "USA", "New York"),
    (49.0, 61.0, -8.0, 2.0, "UK", "London"),
    (35.0, 46.0, 6.0, 18.5, "Italy", "Rome"),
    (36.0, 43.8, -9.5, 3.5, "Spain", "Madrid"),
    (47.0, 55.5, 5.5, 15.5, "Germany", "Berlin"),
    (41.0, 51.5, -5.5, 10.0, "France", "Paris"),
    (30.0, 46.0, 129.0, 146.0, "Japan", "Tokyo"),
    (41.0, 56.0, -141.0, -52.0, "Canada", "Toronto"),
    (-44.0, -10.0, 112.0, 154.0, "Australia", "Sydney"),
    (5.5, 20.5, 97.0, 106.0, "Thailand", "Bangkok"),
    (0.8, 7.5, 100.0, 119.5, "Malaysia", "Kuala Lumpur"),
    (-11.0, 6.0, 95.0, 141.0, "Indonesia", "Jakarta"),
    (33.0, 39.0, 124.0, 132.0, "South Korea", "Seoul"),
    (18.0, 53.5, 73.5, 135.0, "China", "Beijing"),
    (45.5, 48.0, 5.5, 10.5, "Switzerland", "Zurich"),
    (50.5, 53.8, 3.3, 7.3, "Netherlands", "Amsterdam"),
]


def _estimate_region_from_coords(lat: float, lng: float) -> dict:
    """Estimate country and nearest major city from raw GPS coordinates using bounding boxes."""
    for lat_min, lat_max, lng_min, lng_max, country, city in _GEO_REGIONS:
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            lat_dir = "N" if lat >= 0 else "S"
            lng_dir = "E" if lng >= 0 else "W"
            return {
                "formatted_address": f"Near {city}, {country} ({abs(lat):.4f}°{lat_dir}, {abs(lng):.4f}°{lng_dir})",
                "city": city,
                "state": "",
                "country": country,
                "postal_code": "",
                "lat": lat,
                "lng": lng,
                "source": "geo_estimate",
            }

    # Absolute fallback — show formatted coordinates
    lat_dir = "N" if lat >= 0 else "S"
    lng_dir = "E" if lng >= 0 else "W"
    return {
        "formatted_address": f"{abs(lat):.4f}°{lat_dir}, {abs(lng):.4f}°{lng_dir}",
        "city": "",
        "state": "",
        "country": "",
        "postal_code": "",
        "lat": lat,
        "lng": lng,
        "source": "coordinates",
    }


def reverse_geocode_location(lat: float, lng: float) -> dict:
    """Reverse-geocode GPS coordinates into city, country, and address.
    Uses Google Maps → Nominatim → coordinate-based estimation, in order."""
    if not lat or not lng:
        return {"city": "", "country": "", "formatted_address": "", "source": "none"}

    # Try Google Maps first
    if maps.configured:
        result = maps.reverse_geocode(lat, lng)
        if result.get("city") or result.get("formatted_address"):
            return result

    # Fallback to free Nominatim
    result = _nominatim_reverse(lat, lng)
    if result:
        return result

    # Final fallback — estimate from coordinate bounding boxes
    return _estimate_region_from_coords(lat, lng)


def get_emergency_contacts(city: str = "", country: str = "") -> dict:
    """Return emergency contact numbers for a given city or country."""
    city_lower = (city or "").lower().strip()
    country_lower = (country or "").lower().strip()

    # Direct city match
    if city_lower in EMERGENCY_NUMBERS:
        numbers = dict(EMERGENCY_NUMBERS[city_lower])
        numbers.setdefault("general", "112")
        return {
            "success": True,
            "city": city,
            "numbers": numbers,
            "embassy": EMBASSY_CONTACTS.get(city_lower),
            "source": "database",
        }

    # Direct country match
    if country_lower in EMERGENCY_NUMBERS:
        numbers = dict(EMERGENCY_NUMBERS[country_lower])
        numbers.setdefault("general", "112")
        return {
            "success": True,
            "city": city,
            "country": country,
            "numbers": numbers,
            "embassy": EMBASSY_CONTACTS.get(country_lower),
            "source": "database",
        }

    # Country detection from city string
    for ckey, cities in COUNTRY_KEYWORDS.items():
        if any(c in city_lower for c in cities) or any(c in country_lower for c in cities):
            numbers = dict(EMERGENCY_NUMBERS.get(ckey, EMERGENCY_NUMBERS["default"]))
            numbers.setdefault("general", "112")
            return {
                "success": True,
                "city": city,
                "country": ckey,
                "numbers": numbers,
                "embassy": EMBASSY_CONTACTS.get(ckey),
                "source": "database",
            }

    # Check if city is in India (default Indian numbers)
    if any(c in city_lower for c in INDIAN_CITIES) or city_lower.endswith("india") or country_lower == "india":
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


def find_nearby_hospitals(city: str = "", lat: float = None, lng: float = None, limit: int = 5) -> list:
    """Search for hospitals near the given location using Google Maps."""
    if not maps.configured:
        return [{
            "name": "Google Maps not configured",
            "note": "Set GOOGLE_MAPS_API_KEY to find nearby hospitals in real-time",
            "source": "fallback",
        }]

    try:
        if lat and lng:
            location = {"lat": lat, "lng": lng}
        elif city:
            coord = maps.geocode(city)
            if not coord:
                return []
            location = {"lat": coord["lat"], "lng": coord["lng"]}
        else:
            return []

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


def find_nearby_police(lat: float = None, lng: float = None, city: str = "", limit: int = 3) -> list:
    """Search for police stations near the given location."""
    if not maps.configured:
        return []
    try:
        if lat and lng:
            location = {"lat": lat, "lng": lng}
        elif city:
            coord = maps.geocode(city)
            if not coord:
                return []
            location = {"lat": coord["lat"], "lng": coord["lng"]}
        else:
            return []

        places = maps.nearby_places(location, "police", radius=5000)
        stations = []
        for p in (places or [])[:limit]:
            stations.append({
                "name": p.get("name", ""),
                "vicinity": p.get("vicinity", ""),
                "rating": p.get("rating"),
                "place_id": p.get("place_id", ""),
                "source": "google_maps",
            })
        return stations
    except Exception as e:
        logger.warning("[SOS] Police station search failed: %s", e)
        return []
