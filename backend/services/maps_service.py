"""
TravelSync Pro — Google Maps Platform Service
Distance Matrix, Geocoding, Places API, Directions.
Configure GOOGLE_MAPS_API_KEY to enable real data.
"""
import os
import math
import logging
import requests
from cachetools import TTLCache

logger = logging.getLogger(__name__)


class MapsService:
    GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    DISTANCE_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
    PLACES_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
    PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        self.configured = bool(self.api_key)
        self._cache = TTLCache(maxsize=200, ttl=3600)

    def geocode(self, address: str) -> dict:
        """Convert address/city to lat/lng coordinates."""
        cache_key = f"geo_{address.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self.configured:
            try:
                resp = requests.get(
                    self.GEOCODE_URL,
                    params={"address": address, "key": self.api_key},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("results"):
                        loc = data["results"][0]["geometry"]["location"]
                        result = {
                            "lat": loc["lat"],
                            "lng": loc["lng"],
                            "formatted": data["results"][0].get("formatted_address", address),
                            "source": "google_maps",
                        }
                        self._cache[cache_key] = result
                        return result
            except Exception as e:
                logger.warning("[Maps] Geocode error: %s", e)

        # Fallback: lookup from built-in city coords
        result = self._city_coords_fallback(address)
        self._cache[cache_key] = result
        return result

    def get_distance_km(self, origin: str, destination: str) -> float:
        """Get driving distance in km between two places."""
        if self.configured:
            try:
                resp = requests.get(
                    self.DISTANCE_URL,
                    params={
                        "origins": origin,
                        "destinations": destination,
                        "key": self.api_key,
                        "units": "metric",
                    },
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    element = data.get("rows", [{}])[0].get("elements", [{}])[0]
                    if element.get("status") == "OK":
                        return element["distance"]["value"] / 1000  # meters → km
            except Exception as e:
                logger.warning("[Maps] Distance error: %s", e)

        # Fallback: haversine calculation
        return self._haversine_km(origin, destination)

    def distance_matrix(self, origins: list, destinations: list, mode: str = "driving") -> dict:
        """Full distance matrix between multiple origins and destinations."""
        if self.configured:
            try:
                resp = requests.get(
                    self.DISTANCE_URL,
                    params={
                        "origins": "|".join(origins),
                        "destinations": "|".join(destinations),
                        "key": self.api_key,
                        "mode": mode,
                        "units": "metric",
                    },
                    timeout=15
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                logger.warning("[Maps] Distance matrix error: %s", e)
        return {"rows": [], "source": "fallback"}

    def nearby_places(self, location: dict, place_type: str, radius: int = 2000,
                      keyword: str = None) -> list:
        """Find nearby places using Google Places API."""
        if not self.configured:
            return []
        try:
            params = {
                "location": f"{location['lat']},{location['lng']}",
                "radius": radius,
                "type": place_type,
                "key": self.api_key,
            }
            if keyword:
                params["keyword"] = keyword

            resp = requests.get(self.PLACES_URL, params=params, timeout=15)
            if resp.status_code == 200:
                places = []
                for p in resp.json().get("results", [])[:10]:
                    places.append({
                        "name": p.get("name"),
                        "rating": p.get("rating"),
                        "user_ratings_total": p.get("user_ratings_total"),
                        "vicinity": p.get("vicinity"),
                        "place_id": p.get("place_id"),
                        "types": p.get("types", []),
                        "location": p.get("geometry", {}).get("location", {}),
                        "open_now": p.get("opening_hours", {}).get("open_now"),
                        "price_level": p.get("price_level"),
                        "source": "google_places",
                    })
                return places
        except Exception as e:
            logger.warning("[Maps] Nearby places error: %s", e)
        return []

    def directions(self, origin: str, destination: str, mode: str = "driving") -> dict:
        """Get route details between two locations."""
        if self.configured:
            try:
                resp = requests.get(
                    self.DIRECTIONS_URL,
                    params={"origin": origin, "destination": destination,
                            "mode": mode, "key": self.api_key},
                    timeout=10
                )
                if resp.status_code == 200 and resp.json().get("routes"):
                    leg = resp.json()["routes"][0]["legs"][0]
                    return {
                        "distance": leg["distance"]["text"],
                        "duration": leg["duration"]["text"],
                        "distance_value": leg["distance"]["value"],
                        "duration_value": leg["duration"]["value"],
                        "start_address": leg.get("start_address", origin),
                        "end_address": leg.get("end_address", destination),
                        "source": "google_maps",
                    }
            except Exception as e:
                logger.warning("[Maps] Directions error: %s", e)

        # Fallback estimate
        dist_km = self._haversine_km(origin, destination)
        speed_kmh = 60  # avg city/highway
        duration_min = int((dist_km / speed_kmh) * 60)
        return {
            "distance": f"{dist_km:.0f} km",
            "duration": f"{duration_min} mins",
            "distance_value": dist_km * 1000,
            "duration_value": duration_min * 60,
            "source": "estimated",
        }

    def get_place_details(self, place_id: str) -> dict:
        """Get detailed info about a place."""
        if not self.configured:
            return {}
        try:
            resp = requests.get(
                self.PLACE_DETAILS_URL,
                params={"place_id": place_id, "key": self.api_key,
                        "fields": "name,rating,formatted_address,opening_hours,website,formatted_phone_number"},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json().get("result", {})
        except Exception as e:
            logger.warning("[Maps] Place details error: %s", e)
        return {}

    def get_static_map_url(self, latitude: float, longitude: float, zoom: int = 14, size: str = "600x300") -> str:
        """Generate a static map image URL."""
        if not self.configured:
            return ""
        marker = f"{latitude},{longitude}"
        return (f"https://maps.googleapis.com/maps/api/staticmap"
                f"?center={marker}&zoom={zoom}&size={size}"
                f"&markers=color:red%7C{marker}&key={self.api_key}")

    # ── Internal helpers ────────────────────────────────────────────

    def _city_coords_fallback(self, address: str) -> dict:
        """Best-effort coordinate lookup from a curated city table."""
        CITY_COORDS = {
            # India
            "mumbai": (19.0760, 72.8777), "delhi": (28.6139, 77.2090),
            "new delhi": (28.6139, 77.2090), "bangalore": (12.9716, 77.5946),
            "bengaluru": (12.9716, 77.5946), "hyderabad": (17.3850, 78.4867),
            "chennai": (13.0827, 80.2707), "kolkata": (22.5726, 88.3639),
            "pune": (18.5204, 73.8567), "ahmedabad": (23.0225, 72.5714),
            "jaipur": (26.9124, 75.7873), "surat": (21.1702, 72.8311),
            "lucknow": (26.8467, 80.9462), "kanpur": (26.4499, 80.3319),
            "nagpur": (21.1458, 79.0882), "indore": (22.7196, 75.8577),
            "thane": (19.2183, 72.9781), "bhopal": (23.2599, 77.4126),
            "visakhapatnam": (17.6868, 83.2185), "patna": (25.5941, 85.1376),
            "vadodara": (22.3072, 73.1812), "ghaziabad": (28.6692, 77.4538),
            "ludhiana": (30.9010, 75.8573), "agra": (27.1767, 78.0081),
            "nashik": (19.9975, 73.7898), "faridabad": (28.4089, 77.3178),
            "meerut": (28.9845, 77.7064), "rajkot": (22.3039, 70.8022),
            "varanasi": (25.3176, 82.9739), "srinagar": (34.0837, 74.7973),
            "aurangabad": (19.8762, 75.3433), "amritsar": (31.6340, 74.8723),
            "navi mumbai": (19.0330, 73.0297), "allahabad": (25.4358, 81.8463),
            "prayagraj": (25.4358, 81.8463), "ranchi": (23.3441, 85.3096),
            "coimbatore": (11.0168, 76.9558), "jodhpur": (26.2389, 73.0243),
            "madurai": (9.9252, 78.1198), "raipur": (21.2514, 81.6296),
            "kochi": (9.9312, 76.2673), "chandigarh": (30.7333, 76.7794),
            "guwahati": (26.1445, 91.7362), "thiruvananthapuram": (8.5241, 76.9366),
            "goa": (15.2993, 74.1240), "panaji": (15.4989, 73.8278),
            "udaipur": (24.5854, 73.7125), "shimla": (31.1048, 77.1734),
            "manali": (32.2432, 77.1892), "darjeeling": (27.0360, 88.2627),
            "ooty": (11.4064, 76.6932), "mysore": (12.2958, 76.6394),
            "mysuru": (12.2958, 76.6394), "pondicherry": (11.9416, 79.8083),
            # International
            "dubai": (25.2048, 55.2708), "singapore": (1.3521, 103.8198),
            "london": (51.5074, -0.1278), "new york": (40.7128, -74.0060),
            "paris": (48.8566, 2.3522), "tokyo": (35.6762, 139.6503),
            "sydney": (-33.8688, 151.2093), "bangkok": (13.7563, 100.5018),
            "toronto": (43.6532, -79.3832), "hong kong": (22.3193, 114.1694),
        }
        city_key = address.lower().split(",")[0].strip()
        for key, coords in CITY_COORDS.items():
            if key in city_key or city_key in key:
                return {"lat": coords[0], "lng": coords[1],
                        "formatted": address, "source": "fallback"}
        # Default: geographic center of India
        return {"lat": 20.5937, "lng": 78.9629, "formatted": address, "source": "fallback"}

    def _haversine_km(self, origin: str, destination: str) -> float:
        """Calculate straight-line distance between two city names using haversine."""
        o = self._city_coords_fallback(origin)
        d = self._city_coords_fallback(destination)
        lat1, lon1 = math.radians(o["lat"]), math.radians(o["lng"])
        lat2, lon2 = math.radians(d["lat"]), math.radians(d["lng"])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        return 6371 * 2 * math.asin(math.sqrt(a))


maps = MapsService()
