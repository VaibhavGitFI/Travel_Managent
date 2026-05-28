"""
TravelSync Pro — Google Maps Platform Service
Distance Matrix, Geocoding, Places API, Directions.
Configure GOOGLE_MAPS_API_KEY to enable real data.
"""
import os
import re
import math
import logging
from cachetools import TTLCache
from services.http_client import http as requests

logger = logging.getLogger(__name__)


class MapsService:
    GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    DISTANCE_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
    PLACES_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
    PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
    AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        self.configured = bool(self.api_key)
        self._cache = TTLCache(maxsize=200, ttl=3600)
        self._pg_cache = TTLCache(maxsize=50, ttl=1800)  # PG results cached 30 min
        self._hotel_cache = TTLCache(maxsize=50, ttl=900)  # Hotel results cached 15 min

    def geocode(self, address: str, components: str = None) -> dict:
        """Convert address/city to lat/lng coordinates.

        components — optional Geocoding API component filter string, e.g.
            "locality:Dhule|administrative_area:Maharashtra|country:IN"
        When provided, Google restricts results to that component scope,
        giving precise results for colonies/areas within a specific city.
        """
        cache_key = f"geo_{address.lower()}_{(components or '').lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self.configured:
            try:
                params = {"address": address, "key": self.api_key}
                if components:
                    params["components"] = components
                resp = requests.get(self.GEOCODE_URL, params=params, timeout=10)
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

    def geocode_by_place_id(self, place_id: str) -> dict:
        """
        Resolve a Google place_id to exact lat/lng via Geocoding API.
        More precise than text geocoding — uses the confirmed Google place pin.
        """
        if not self.configured or not place_id:
            return {"source": "fallback"}

        cache_key = f"geo_pid_{place_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            resp = requests.get(
                self.GEOCODE_URL,
                params={"place_id": place_id, "key": self.api_key},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("results"):
                    loc = data["results"][0]["geometry"]["location"]
                    result = {
                        "lat": loc["lat"],
                        "lng": loc["lng"],
                        "formatted": data["results"][0].get("formatted_address", ""),
                        "source": "google_maps",
                    }
                    self._cache[cache_key] = result
                    return result
        except Exception as e:
            logger.warning("[Maps] Geocode by place_id error: %s", e)

        return {"source": "fallback"}

    def reverse_geocode(self, lat: float, lng: float) -> dict:
        """Convert lat/lng coordinates to address, city, and country."""
        cache_key = f"revgeo_{lat:.4f}_{lng:.4f}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self.configured:
            try:
                resp = requests.get(
                    self.GEOCODE_URL,
                    params={"latlng": f"{lat},{lng}", "key": self.api_key},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("results"):
                        top = data["results"][0]
                        components = {c["types"][0]: c["long_name"] for c in top.get("address_components", []) if c.get("types")}
                        result = {
                            "formatted_address": top.get("formatted_address", ""),
                            "city": components.get("locality") or components.get("administrative_area_level_2") or "",
                            "state": components.get("administrative_area_level_1", ""),
                            "country": components.get("country", ""),
                            "postal_code": components.get("postal_code", ""),
                            "lat": lat,
                            "lng": lng,
                            "source": "google_maps",
                        }
                        self._cache[cache_key] = result
                        return result
            except Exception as e:
                logger.warning("[Maps] Reverse geocode error: %s", e)

        return {"formatted_address": "", "city": "", "state": "", "country": "", "lat": lat, "lng": lng, "source": "fallback"}

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

    # Matches Google Plus Codes like "WQ3F+P14" — indicates no real street address
    _PLUS_CODE_RE = re.compile(r'^[A-Z0-9]{4,8}\+[A-Z0-9]{2,4}\b')

    # Names that indicate administrative areas / non-hotel entities
    _NON_HOTEL_TERMS = frozenset({
        'village', 'tehsil', 'taluka', 'taluk', 'district', 'ward',
        'nagar panchayat', 'gram panchayat', 'municipal corporation',
        'block', 'mandal', 'sub-district',
    })

    def _is_quality_hotel(self, p: dict) -> bool:
        """Return True only if the Places result looks like a real, bookable hotel."""
        name     = p.get("name", "")
        vicinity = p.get("vicinity", "")
        rating   = p.get("rating")
        reviews  = p.get("user_ratings_total", 0)

        # Must have at least a few real reviews
        if not rating or reviews < 5:
            return False

        # Reject very poor quality
        if rating < 2.8:
            return False

        # Reject Plus Code addresses — unregistered local places with no real address
        if self._PLUS_CODE_RE.match(vicinity) or self._PLUS_CODE_RE.match(name):
            return False

        # Reject if name looks like an administrative division, not a hotel
        name_lower = name.lower()
        if any(term in name_lower for term in self._NON_HOTEL_TERMS):
            return False

        return True

    def search_hotels(self, city: str, budget_max: int = None, limit: int = 8,
                      coords: dict = None) -> list:
        """
        Search real hotels using Google Places Nearby Search.

        coords — optional pre-resolved {lat, lng} to anchor the search.
                 When provided (e.g. meeting location pin), hotels are searched
                 around that point rather than the city center, so results are
                 actually near the meeting spot.  Falls back to city geocoding
                 when not provided.
        """
        if not self.configured:
            return []

        anchor = coords if (coords and coords.get("lat") and coords.get("lng")) else None
        anchor_key = f"{anchor['lat']:.4f},{anchor['lng']:.4f}" if anchor else ""
        cache_key = f"hotel_{city.lower()}_{budget_max}_{limit}_{anchor_key}"
        if cache_key in self._hotel_cache:
            return self._hotel_cache[cache_key]

        # Resolve search anchor — meeting location pin takes precedence over city center
        if anchor:
            search_coords = anchor
        else:
            # 1. Geocode city → lat/lng
            search_coords = self.geocode(city)
            if search_coords.get("source") == "fallback" or not search_coords.get("lat"):
                return []

        # 2. Nearby search for lodging — keyword=hotel ensures only real hotels surface
        try:
            params = {
                "location": f"{search_coords['lat']},{search_coords['lng']}",
                "radius": 5000,
                "type": "lodging",
                "keyword": "hotel",
                "key": self.api_key,
            }
            resp = requests.get(self.PLACES_URL, params=params, timeout=15)
            if resp.status_code != 200:
                return []

            PRICE_MAP = {0: (800, 2000), 1: (1500, 4000), 2: (3500, 8000),
                         3: (7000, 18000), 4: (15000, 40000)}

            # Fetch all API results then apply quality filter, so we always
            # have enough after filtering even in smaller cities
            all_results = resp.json().get("results", [])
            hotels = []
            for p in all_results:
                # Skip low-quality, unaddressed, and non-hotel results
                if not self._is_quality_hotel(p):
                    continue

                price_level = p.get("price_level", 2)
                lo, hi = PRICE_MAP.get(price_level, (3000, 10000))
                import random
                price = random.randint(lo, hi)
                if budget_max and price > budget_max:
                    continue

                # Build proxy photo URLs — route through our backend so the
                # API key stays server-side and browser referrer restrictions
                # on the Google Places Photo API don't block images.
                # Store up to 3 references so the frontend can try the next
                # one automatically if a reference expires or fails.
                photo_url = None
                photo_urls = []
                for ph in p.get("photos", [])[:3]:
                    ref = ph.get("photo_reference", "")
                    if ref:
                        proxy = f"/api/accommodation/photo?ref={ref}&max=600"
                        photo_urls.append(proxy)
                if photo_urls:
                    photo_url = photo_urls[0]

                # Stars from price_level
                stars = min(max(price_level + 1, 1), 5) if price_level is not None else 3
                hotel_name = p.get("name", "Hotel")

                place_id = p.get("place_id", "")
                lat = p.get("geometry", {}).get("location", {}).get("lat")
                lng = p.get("geometry", {}).get("location", {}).get("lng")
                vicinity = p.get("vicinity", city)

                # Google Maps — exact place via place_id
                maps_url = f"https://www.google.com/maps/search/?api=1&query={hotel_name.replace(' ', '+')}&query_place_id={place_id}" if place_id else f"https://www.google.com/maps/search/{hotel_name.replace(' ', '+')}+{city.replace(' ', '+')}"

                # Google search for booking — always reliable fallback
                search_query = f"{hotel_name} {city} book hotel".replace(' ', '+')
                google_search_url = f"https://www.google.com/search?q={search_query}"

                # Smart booking platform links based on hotel name
                booking_platforms = self._get_booking_platforms(hotel_name, city, p.get("types", []))

                hotels.append({
                    "name": hotel_name,
                    "rating": p.get("rating", 3.5),
                    "stars": stars,
                    "user_ratings_total": p.get("user_ratings_total", 0),
                    "location": vicinity,
                    "area": vicinity,
                    "price_per_night": price,
                    "price": price,
                    "currency": "INR",
                    "photo_url": photo_url,
                    "photo_urls": photo_urls,
                    "amenities": self._guess_amenities(p, price_level),
                    "place_id": place_id,
                    "latitude": lat,
                    "longitude": lng,
                    "maps_url": maps_url,
                    "google_search_url": google_search_url,
                    "booking_platforms": booking_platforms,
                    "source": "google_places",
                })
                if len(hotels) >= limit:
                    break

            # AI-powered price estimation for accuracy
            hotels = self._ai_estimate_prices(hotels, city)
            self._hotel_cache[cache_key] = hotels
            return hotels
        except Exception as e:
            logger.warning("[Maps] Hotel search error: %s", e)
        return []

    def _ai_estimate_prices(self, hotels: list, city: str) -> list:
        """Use AI to estimate realistic prices based on hotel name, city, and rating."""
        if not hotels:
            return hotels
        try:
            hotel_list = "\n".join(
                f"- {h['name']} (rating {h.get('rating', '?')}, stars {h.get('stars', '?')})"
                for h in hotels[:10]
            )
            prompt = (
                f"Estimate realistic per-night prices in INR for these hotels in {city}, India.\n"
                f"Use current 2026 market rates. Be specific and accurate.\n\n"
                f"{hotel_list}\n\n"
                f"Respond with ONLY hotel name and price, one per line, format:\n"
                f"Hotel Name: 5500\n"
                f"No currency symbols, no ranges, just the best estimate number."
            )

            response = None
            try:
                from services.anthropic_service import claude
                if claude.is_available:
                    response = claude.generate(prompt, system="You are an Indian hotel pricing expert. Give accurate single-number INR per-night estimates.")
            except Exception:
                pass
            if not response:
                try:
                    from services.gemini_service import gemini
                    import time
                    if gemini.configured and not (hasattr(gemini, '_cooldown_until') and time.time() < gemini._cooldown_until):
                        response = gemini.generate(prompt, model_type="flash")
                except Exception:
                    pass

            if response:
                price_map = {}
                for line in response.strip().split("\n"):
                    if ":" not in line:
                        continue
                    name_part, _, price_part = line.rpartition(":")
                    name_part = name_part.strip()
                    cleaned = "".join(c for c in price_part.strip() if c.isdigit())
                    if cleaned:
                        try:
                            price_map[name_part.lower()] = int(cleaned)
                        except ValueError:
                            pass

                for h in hotels:
                    ai_price = price_map.get(h["name"].lower())
                    if ai_price and 500 <= ai_price <= 100000:
                        h["price_per_night"] = ai_price
                        h["price"] = ai_price
                        h["price_source"] = "ai_estimated"

        except Exception as e:
            logger.debug("[Maps] AI price estimation skipped: %s", e)
        return hotels

    @staticmethod
    def _get_booking_platforms(hotel_name: str, city: str, place_types: list) -> list:
        """Build verified booking platform links for this hotel.
        Only includes platforms known to work with these URL formats."""
        name_lower = hotel_name.lower()
        city_slug = city.lower().replace(' ', '-')
        # For Google search — always works
        search_q = f"{hotel_name} {city}".replace(' ', '+')

        platforms = []

        # 1. Chain direct sites — only if we can build a working URL
        CHAINS = {
            "marriott":    ("Marriott",    f"https://www.marriott.com/search/default.mi?keyword={search_q}"),
            "jw marriott": ("Marriott",    f"https://www.marriott.com/search/default.mi?keyword={search_q}"),
            "sheraton":    ("Marriott",    f"https://www.marriott.com/search/default.mi?keyword={search_q}"),
            "hyatt":       ("Hyatt",       f"https://www.hyatt.com/en-US/search?q={search_q}"),
            "taj":         ("Taj Hotels",  f"https://www.tajhotels.com/en-in/search/?query={search_q}"),
            "ihcl":        ("Taj Hotels",  f"https://www.tajhotels.com/en-in/search/?query={search_q}"),
            "oberoi":      ("Oberoi",      f"https://www.oberoihotels.com"),
            "hilton":      ("Hilton",      f"https://www.hilton.com/en/search/?query={search_q}"),
            "radisson":    ("Radisson",    f"https://www.radissonhotels.com/en-us/search?searchTerm={search_q}"),
            "lemon tree":  ("Lemon Tree",  f"https://www.lemontreehotels.com/hotels-in-{city_slug}"),
            "novotel":     ("Accor",       f"https://all.accor.com/hotel/search.html?destination={search_q}"),
            "ibis":        ("Accor",       f"https://all.accor.com/hotel/search.html?destination={search_q}"),
            "oyo":         ("OYO",         f"https://www.oyorooms.com/hotels-in-{city_slug}/"),
            "treebo":      ("Treebo",      f"https://www.treebo.com/hotels-in-{city_slug}/"),
            "fabhotel":    ("FabHotels",   f"https://www.fabhotels.com/hotels-in-{city_slug}"),
        }
        for keyword, (label, url) in CHAINS.items():
            if keyword in name_lower:
                platforms.append({"name": label, "url": url, "type": "direct"})
                break

        # 2. Booking.com — verified working format: ?ss=hotel+name+city
        platforms.append({
            "name": "Booking.com",
            "url": f"https://www.booking.com/searchresults.html?ss={search_q}",
            "type": "ota",
        })

        # 3. Google Hotels — always works, aggregates all OTA prices
        platforms.append({
            "name": "Google Hotels",
            "url": f"https://www.google.com/search?q={search_q}+booking+price",
            "type": "ota",
        })

        return platforms[:3]  # Max 3 — keep it clean

    @staticmethod
    def _guess_amenities(place: dict, price_level: int | None) -> list:
        """Guess amenities from price level and place types."""
        base = ["WiFi", "AC"]
        types = set(place.get("types", []))
        if price_level is not None and price_level >= 2:
            base.extend(["Restaurant", "Room Service"])
        if price_level is not None and price_level >= 3:
            base.extend(["Pool", "Gym", "Spa"])
        if "spa" in types:
            if "Spa" not in base:
                base.append("Spa")
        if "restaurant" in types or "food" in types:
            if "Restaurant" not in base:
                base.append("Restaurant")
        return base

    # ── City Tier Classification for PG availability ────────────
    TIER1_CITIES = {
        "mumbai", "delhi", "new delhi", "bangalore", "bengaluru", "hyderabad",
        "chennai", "pune", "kolkata", "gurgaon", "gurugram", "noida",
        "ghaziabad", "navi mumbai", "thane",
    }
    TIER2_CITIES = {
        "ahmedabad", "jaipur", "lucknow", "kochi", "cochin", "chandigarh",
        "indore", "bhopal", "nagpur", "coimbatore", "vizag", "visakhapatnam",
        "mysore", "mysuru", "mangalore", "trivandrum", "thiruvananthapuram",
        "bhubaneswar", "dehradun", "surat", "vadodara", "goa", "panaji",
    }

    PG_SEARCH_KEYWORDS = {
        "tier1": [
            ("paying guest", "Managed PG"),
            ("coliving space", "Coliving"),
            ("serviced apartment", "Serviced Apartment"),
            ("hostel accommodation", "Hostel"),
        ],
        "tier2": [
            ("paying guest", "Managed PG"),
            ("serviced apartment", "Serviced Apartment"),
        ],
    }

    PG_BOOKING_PLATFORMS = {
        "stanza":   ("Stanza Living", "https://www.stanzaliving.com"),
        "nestaway": ("NestAway", "https://www.nestaway.com"),
        "zolo":     ("Zolo Stays", "https://www.zolostays.com"),
        "colive":   ("Colive", "https://www.colive.com"),
        "oyo life": ("OYO Life", "https://www.oyorooms.com/long-term-stays"),
        "coho":     ("CoHo", "https://www.coho.in"),
        "zostel":   ("Zostel", "https://www.zostel.com"),
    }

    # Google Places API (New) — Text Search endpoint
    PLACES_NEW_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"

    # Fields to fetch — field masking keeps payload lean and reduces cost
    _PG_FIELD_MASK = (
        "places.id,places.displayName,places.formattedAddress,"
        "places.location,places.rating,places.userRatingCount,"
        "places.priceLevel,places.photos,places.regularOpeningHours,"
        "places.internationalPhoneNumber,places.websiteUri,places.types"
    )

    # Price level → multiplier applied on top of city-tier base rent
    _PRICE_LEVEL_MULTIPLIER = {
        "PRICE_LEVEL_FREE":           0.40,
        "PRICE_LEVEL_INEXPENSIVE":    0.70,
        "PRICE_LEVEL_MODERATE":       1.00,
        "PRICE_LEVEL_EXPENSIVE":      1.55,
        "PRICE_LEVEL_VERY_EXPENSIVE": 2.40,
    }

    # Base monthly rent (INR) by city tier × PG type
    _PG_BASE_RENT = {
        "tier1": {"Managed PG": 12000, "Coliving": 18000, "Hostel": 7000, "Serviced Apartment": 25000},
        "tier2": {"Managed PG": 8000,  "Coliving": 13000, "Hostel": 5000, "Serviced Apartment": 18000},
        "tier3": {"Managed PG": 5000,  "Coliving": 9000,  "Hostel": 3500, "Serviced Apartment": 12000},
    }

    # Keywords that indicate the result is NOT a PG/long-stay option
    _NON_PG_KEYWORDS = frozenset({
        "resort", "hotel", "inn", "lodge", "motel", "heritage hotel",
        "government", "collector", "municipality", "municipal corporation",
        "school", "college", "university", "institute", "polytechnic",
        "hospital", "clinic", "orphanage", "ashram", "dharamshala",
        "dharmshala", "mandir", "temple", "church",
    })

    # Regex matching a Plus Code prefix like "WQ9M+V6X" at the start of an address part
    _PLUS_CODE_RE = re.compile(r'^[A-Z0-9]{4,8}\+[A-Z0-9]{2,4}(\s|$)', re.IGNORECASE)

    def search_pg_options(self, city: str, budget_monthly: int = None, limit: int = 8,
                          coords: dict = None) -> list:
        """
        Search real PG / coliving / long-stay options using Google Places API (New).

        coords — optional pre-resolved {lat, lng} (e.g. meeting location pin).
                 When provided, the search is anchored to that point so results
                 are near the actual meeting area, not just the city centre.
        Uses Text Search (POST) with locationBias circle, X-Goog-FieldMask,
        multiple query terms, and place_id deduplication.
        Falls back to AI generation only when Google returns < 3 real results.
        """
        if not self.configured:
            return []

        city_lower = city.lower().strip()

        # Include anchor in cache key so a Kalewadi search doesn't return city-center results
        anchor = coords if (coords and coords.get("lat") and coords.get("lng")) else None
        anchor_key = f"{anchor['lat']:.4f},{anchor['lng']:.4f}" if anchor else ""
        pg_cache_key = f"pg_v2_{city_lower}_{budget_monthly}_{limit}_{anchor_key}"
        if pg_cache_key in self._pg_cache:
            return self._pg_cache[pg_cache_key]

        if anchor:
            # Meeting location provided — search around that pin
            center = {"latitude": anchor["lat"], "longitude": anchor["lng"]}
        else:
            # Geocode city with component filter for a precise center pin
            resolved = self.geocode(city, components=f"locality:{city}")
            if not resolved.get("lat") or resolved.get("source") == "fallback":
                resolved = self.geocode(city)
            if not resolved.get("lat") or resolved.get("source") == "fallback":
                return []
            center = {"latitude": resolved["lat"], "longitude": resolved["lng"]}

        # Search terms → type label. Run in order; stop when limit met.
        search_queries = [
            (f"PG accommodation in {city}",            "Managed PG"),
            (f"paying guest accommodation in {city}",  "Managed PG"),
            (f"coliving space in {city}",              "Coliving"),
            (f"hostel in {city}",                      "Hostel"),
            (f"serviced apartment in {city}",          "Serviced Apartment"),
            (f"furnished apartment for rent in {city}","Serviced Apartment"),
        ]

        seen_ids = set()
        all_results = []

        for text_query, pg_type in search_queries:
            if len(all_results) >= limit * 2:
                break
            try:
                places = self._places_text_search(
                    text_query,
                    center=center,
                    radius=10000,   # 10 km city-wide, strict boundary
                    max_results=5,
                )
            except Exception as e:
                logger.warning("[Maps] PG text search error for %r: %s", text_query, e)
                continue

            for p in places:
                pid = p.get("id", "")
                if not pid or pid in seen_ids:
                    continue

                display_name = (p.get("displayName") or {}).get("text", "").strip()
                if not display_name:
                    continue

                # ── Non-PG filter ─────────────────────────────────────────────
                # Skip obvious hotels, resorts, government buildings, schools etc.
                name_lower = display_name.lower()
                if any(kw in name_lower for kw in self._NON_PG_KEYWORDS):
                    continue
                # Also check Google place types returned by the API
                place_types = p.get("types") or []
                bad_types = {"hotel", "resort_hotel", "motel", "extended_stay_hotel"}
                pg_type_hints = {"hostel", "lodging"}
                if bad_types.intersection(place_types) and not pg_type_hints.intersection(place_types):
                    continue
                # ─────────────────────────────────────────────────────────────

                seen_ids.add(pid)

                formatted_addr = p.get("formattedAddress", city)
                location = p.get("location", {})
                rating = p.get("rating")
                rating_count = p.get("userRatingCount", 0)
                price_level = p.get("priceLevel") or ""

                # ── Dynamic rent: city-tier + PG type + rating nudge ──────────
                city_tier = (
                    "tier1" if city_lower in self.TIER1_CITIES else
                    "tier2" if city_lower in self.TIER2_CITIES else
                    "tier3"
                )
                base_rent = self._PG_BASE_RENT[city_tier].get(pg_type, self._PG_BASE_RENT[city_tier]["Managed PG"])
                if price_level in self._PRICE_LEVEL_MULTIPLIER:
                    monthly_rent = int(base_rent * self._PRICE_LEVEL_MULTIPLIER[price_level])
                else:
                    # No price level from Google → nudge by rating
                    if rating and rating >= 4.5:
                        monthly_rent = int(base_rent * 1.20)
                    elif rating and rating < 3.5:
                        monthly_rent = int(base_rent * 0.85)
                    else:
                        monthly_rent = base_rent
                # Round to nearest 500
                monthly_rent = round(monthly_rent / 500) * 500
                # ─────────────────────────────────────────────────────────────

                if budget_monthly and monthly_rent > budget_monthly:
                    continue

                # ── Plus Code-aware area extraction ───────────────────────────
                addr_parts = [pt.strip() for pt in formatted_addr.split(",")]
                area = next(
                    (pt for pt in addr_parts if pt and not self._PLUS_CODE_RE.match(pt)),
                    addr_parts[-1] if addr_parts else city,
                )
                # ─────────────────────────────────────────────────────────────

                # Build photo proxy URLs from new API photo resource names.
                # Resource name format: "places/PLACE_ID/photos/PHOTO_ID"
                import urllib.parse
                photo_urls = []
                for ph in (p.get("photos") or [])[:3]:
                    ph_name = ph.get("name", "")
                    if ph_name:
                        photo_urls.append(
                            f"/api/accommodation/photo?name={urllib.parse.quote(ph_name, safe='')}&max=600"
                        )
                # Brand logo fallback when no Google photo available
                photo_url = photo_urls[0] if photo_urls else self._get_pg_brand_image(display_name)
                photo_urls_final = photo_urls if photo_urls else ([photo_url] if photo_url else [])

                booking_platforms = self._get_pg_platforms(display_name, city)
                maps_url = f"https://www.google.com/maps/place/?q=place_id:{pid}"
                phone = p.get("internationalPhoneNumber", "")
                website = p.get("websiteUri", "")

                # Derive amenities from type label
                base_amenities = {
                    "Managed PG":         ["WiFi", "AC", "Security", "Meals"],
                    "Coliving":           ["WiFi", "AC", "Security", "Meals", "Community"],
                    "Hostel":             ["WiFi", "Security", "Common Area"],
                    "Serviced Apartment": ["WiFi", "AC", "Kitchen", "Laundry", "Security"],
                }.get(pg_type, ["WiFi", "AC", "Security"])

                pg_lat = location.get("latitude")
                pg_lng = location.get("longitude")

                # Distance from meeting pin — shown on the card so travellers
                # know exactly how far each PG is from their meeting location.
                dist_label = None
                dist_km_val = None
                if anchor and pg_lat and pg_lng:
                    d = self._haversine_coords_km(anchor["lat"], anchor["lng"], pg_lat, pg_lng)
                    dist_km_val = round(d, 1)
                    dist_label = f"{dist_km_val} km from meeting location"

                all_results.append({
                    "name":                    display_name,
                    "type":                    pg_type,
                    "location":                formatted_addr,
                    "area":                    area,
                    "monthly_rent":            monthly_rent,
                    "rating":                  rating,
                    "user_ratings_total":      rating_count,
                    "place_id":                pid,
                    "latitude":                pg_lat,
                    "longitude":               pg_lng,
                    "photo_url":               photo_url,
                    "photo_urls":              photo_urls_final,
                    "maps_url":                maps_url,
                    "phone":                   phone,
                    "website":                 website,
                    "booking_platforms":       booking_platforms,
                    "amenities":               base_amenities,
                    "distance_from_meeting_km": dist_km_val,
                    "distance_from_meeting":   dist_label,
                    "source":                  "google_places_new",
                })

        # When meeting location provided → sort by distance first, then rating.
        # Without meeting location → sort purely by rating.
        if anchor:
            all_results.sort(key=lambda x: (
                x.get("distance_from_meeting_km") if x.get("distance_from_meeting_km") is not None else 999,
                -(x.get("rating") or 0),
            ))
        else:
            all_results.sort(
                key=lambda x: (x.get("rating") or 0, x.get("user_ratings_total") or 0),
                reverse=True,
            )
        results = all_results[:limit]

        # AI fallback only when real results are sparse
        if len(results) < 3:
            tier = "tier1" if city_lower in self.TIER1_CITIES else "tier2"
            ai_results = self._ai_generate_pg_options(city, tier, limit - len(results))
            results.extend(ai_results)
            logger.info("[Maps] PG: %d real + %d AI results for %s", len(results) - len(ai_results), len(ai_results), city)
        else:
            logger.info("[Maps] PG: %d real results for %s from Google Places", len(results), city)

        if results:
            self._pg_cache[pg_cache_key] = results
        return results

    def _places_text_search(self, text_query: str, center: dict,
                            radius: float, max_results: int = 5) -> list:
        """
        Google Places API (New) Text Search.
        POST https://places.googleapis.com/v1/places:searchText

        Uses locationBias circle so results are strongly ranked toward the city
        area without hard-clipping (searchText does not support locationRestriction
        with circle — only locationBias does).
        """
        headers = {
            "Content-Type":     "application/json",
            "X-Goog-Api-Key":   self.api_key,
            "X-Goog-FieldMask": self._PG_FIELD_MASK,
        }
        body = {
            "textQuery":      text_query,
            "maxResultCount": max_results,
            "locationBias": {
                "circle": {
                    "center": center,
                    "radius": float(radius),
                }
            },
        }
        resp = requests.post(self.PLACES_NEW_TEXT_URL, json=body, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("places", [])
        logger.warning("[Maps] Places Text Search %d for %r: %s",
                       resp.status_code, text_query, resp.text[:300])
        return []

    def _ai_generate_pg_options(self, city: str, tier: str, limit: int) -> list:
        """Use AI to generate genuine PG/coliving options that actually exist in this city."""
        city_slug = city.lower().replace(' ', '-')

        prompt = (
            f"List {limit} REAL paying guest (PG), coliving, or hostel options in {city}, India.\n"
            f"Only include operators that ACTUALLY operate in {city} as of 2026.\n\n"
            f"Known PG operators in India: Stanza Living, Zolo Stays, NestAway, Colive, "
            f"CoHo, OYO Life, Zostel (hostels), Backpacker Panda, goSTOPS, The Hosteller.\n\n"
            f"For each, provide on ONE line in this EXACT format:\n"
            f"Name | Type | Area | Monthly_Rent | Amenities\n\n"
            f"Example:\n"
            f"Zolo Crest | Coliving | Koramangala | 12000 | WiFi, AC, Meals, Laundry\n"
            f"Stanza Living Park View | Managed PG | Hinjewadi | 9500 | WiFi, AC, Security, Meals\n\n"
            f"Rules:\n"
            f"- Only include options that genuinely exist in {city}\n"
            f"- Use real area names within {city}\n"
            f"- Monthly rent must be realistic for {city} (2026 rates)\n"
            f"- Include a mix of budget and premium options\n"
            f"- Include both men's and women's options if applicable"
        )

        response = None
        # Use Gemini (free) first to avoid Anthropic costs
        try:
            from services.gemini_service import gemini
            import time as _time
            if gemini.configured and not (hasattr(gemini, '_cooldown_until') and _time.time() < gemini._cooldown_until):
                response = gemini.generate(prompt, model_type="flash")
        except Exception:
            pass
        # Only fallback to Claude if Gemini fails
        if not response:
            try:
                from config import Config
                from services.anthropic_service import claude
                if claude.is_available:
                    response = claude.generate(prompt, system=f"You are an expert on PG accommodations in Indian cities. Only list REAL operators that exist in {city}.")
            except Exception:
                pass

        if not response:
            return []

        import re
        results = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("---") or line.startswith("Example") or line.startswith("Name |"):
                continue

            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                # Try comma-separated as fallback
                parts = [p.strip() for p in line.split(",", 4)]
            if len(parts) < 3:
                continue

            name = re.sub(r'^\d+[\.\)\-]\s*', '', parts[0]).strip("- *").replace('**', '').replace('*', '').strip()
            if not name or len(name) < 3 or name.lower().startswith("name") or name.lower().startswith("example"):
                continue
            pg_type = parts[1].strip().replace('**', '') if len(parts) > 1 else "Managed PG"
            area = parts[2].strip().replace('**', '') if len(parts) > 2 else city
            rent_str = "".join(c for c in (parts[3] if len(parts) > 3 else "")) if len(parts) > 3 else ""
            amenities_str = parts[4].strip() if len(parts) > 4 else "WiFi, AC, Meals, Security"

            try:
                rent = int(rent_str) if rent_str else 10000
            except ValueError:
                rent = 10000

            if rent < 3000 or rent > 80000:
                rent = 10000

            amenities = [a.strip().replace('**', '') for a in amenities_str.split(",")]
            booking_platforms = self._get_pg_platforms(name, city)
            search_q = f"{name} {area} {city}".replace(' ', '+')

            # Real Maps URL — search by name + area for accurate pin
            maps_url = f"https://www.google.com/maps/search/{search_q}"

            # Get logo/photo from the PG brand
            photo_url = self._get_pg_brand_image(name)

            results.append({
                "name": name,
                "type": pg_type,
                "location": f"{area}, {city}",
                "area": area,
                "monthly_rent": rent,
                "rating": None,
                "user_ratings_total": 0,
                "place_id": None,
                "photo_url": photo_url,
                "maps_url": maps_url,
                "booking_platforms": booking_platforms,
                "amenities": amenities[:6],
                "price_source": "ai_estimated",
                "source": "ai_generated",
            })

        return results[:limit]

    def _city_has_pg(self, city: str) -> bool:
        """Check if city has PG/coliving — use Gemini (free) first."""
        prompt = (
            f"Does '{city}' in India have PG operators like Stanza Living, Zolo, NestAway? "
            f"Only 'yes' if working professionals use PGs there. Answer ONLY yes or no."
        )
        try:
            from services.gemini_service import gemini
            import time
            if gemini.configured and not (hasattr(gemini, '_cooldown_until') and time.time() < gemini._cooldown_until):
                resp = gemini.generate(prompt, model_type="flash")
                if resp and resp.strip().lower().startswith("yes"):
                    return True
                return False
        except Exception:
            pass
        # Default: no PG for unknown cities
        return False

    def _ai_validate_pg(self, pgs: list, city: str) -> list:
        """AI validates PG results — removes false positives and estimates realistic prices."""
        try:
            pg_list = "\n".join(
                f"- {p['name']} ({p['type']}, area: {p.get('location', '?')}, rating: {p.get('rating', '?')})"
                for p in pgs[:12]
            )
            prompt = (
                f"Here are PG/coliving search results in {city}, India:\n\n{pg_list}\n\n"
                f"For each one:\n"
                f"1. Is it genuinely a PG, coliving space, hostel, or serviced apartment? (yes/no)\n"
                f"2. Estimated monthly rent in INR (realistic 2026 rates for {city})\n\n"
                f"Respond ONLY in this format, one per line:\n"
                f"Name: yes/no, 15000\n"
                f"(name, then colon, then yes or no, then comma, then price number)"
            )

            response = None
            try:
                from services.anthropic_service import claude
                if claude.is_available:
                    response = claude.generate(prompt, system="You are an Indian PG accommodation expert. Validate and price PGs accurately.")
            except Exception:
                pass

            if not response:
                try:
                    from services.gemini_service import gemini
                    import time
                    if gemini.configured and not (hasattr(gemini, '_cooldown_until') and time.time() < gemini._cooldown_until):
                        response = gemini.generate(prompt, model_type="flash")
                except Exception:
                    pass

            if response:
                validation = {}
                for line in response.strip().split("\n"):
                    if ":" not in line:
                        continue
                    name_part, _, rest = line.rpartition(":")
                    name_part = name_part.strip().lower()
                    parts = rest.strip().split(",")
                    is_valid = "yes" in parts[0].lower() if parts else False
                    price = 0
                    if len(parts) >= 2:
                        cleaned = "".join(c for c in parts[1].strip() if c.isdigit())
                        if cleaned:
                            try:
                                price = int(cleaned)
                            except ValueError:
                                pass
                    validation[name_part] = {"valid": is_valid, "price": price}

                # Apply validation
                validated = []
                for pg in pgs:
                    key = pg["name"].lower().strip()
                    info = validation.get(key, {})
                    if info.get("valid", True):  # Default to keeping if AI didn't mention it
                        if info.get("price") and 3000 <= info["price"] <= 100000:
                            pg["monthly_rent"] = info["price"]
                            pg["price_source"] = "ai_estimated"
                        elif pg["monthly_rent"] == 0:
                            pg["monthly_rent"] = 12000  # Reasonable default
                        validated.append(pg)
                return validated

        except Exception as e:
            logger.debug("[Maps] PG AI validation skipped: %s", e)

        # Fallback — set default prices
        for pg in pgs:
            if pg["monthly_rent"] == 0:
                pg["monthly_rent"] = 12000
        return pgs

    @staticmethod
    def _get_pg_brand_image(name: str) -> str | None:
        """Return a brand logo/image URL for known PG operators."""
        name_lower = name.lower()
        # Use favicon/logo URLs that are publicly accessible
        BRAND_LOGOS = {
            "zolo":     "https://images.zolostays.com/zolostays/assets/images/zolo_og.png",
            "stanza":   "https://res.cloudinary.com/stanza-living/image/upload/v1/web-cms/stanza-living-og.jpg",
            "nestaway": "https://www.nestaway.com/images/nestaway-logo-og.png",
            "colive":   "https://www.colive.com/assets/images/colive-og-image.png",
            "zostel":   "https://www.zostel.com/wp-content/uploads/2022/05/zostel-og.jpg",
            "oyo":      "https://assets.oyoroomscdn.com/cmsMedia/c63a72dc-9f3e-40f0-b8e8-4a8b6b0c07a4.png",
            "coho":     "https://www.coho.in/assets/images/coho_logo.png",
            "hosteller": "https://www.thehosteller.com/images/logo-og.png",
            "gostops":  "https://www.gostops.com/images/logo-og.png",
            "backpacker": "https://www.backpackerpanda.com/images/logo-og.png",
        }
        for keyword, url in BRAND_LOGOS.items():
            if keyword in name_lower:
                return url
        return None

    @staticmethod
    def _get_pg_platforms(name: str, city: str) -> list:
        """Get booking platforms for a PG based on brand detection."""
        name_lower = name.lower()
        city_slug = city.lower().replace(' ', '-')
        search_q = f"{name} {city}".replace(' ', '+')
        platforms = []

        PG_BRANDS = {
            "stanza":    ("Stanza Living", f"https://www.stanzaliving.com/{city_slug}"),
            "nestaway":  ("NestAway",      f"https://www.nestaway.com/house-for-rent-in-{city_slug}"),
            "zolo":      ("Zolo Stays",    f"https://www.zolostays.com/pg-in-{city_slug}"),
            "colive":    ("Colive",        f"https://www.colive.com/coliving-pg-in-{city_slug}"),
            "oyo":       ("OYO Life",      f"https://www.oyolife.com/{city_slug}"),
            "coho":      ("CoHo Living",   f"https://www.coho.in/{city_slug}"),
            "zostel":    ("Zostel",        f"https://www.zostel.com/zostel/{city_slug}/"),
            "hosteller": ("The Hosteller", f"https://www.thehosteller.com/{city_slug}/"),
            "gostops":   ("goSTOPS",       f"https://www.gostops.com/hostels/{city_slug}"),
        }

        for keyword, (label, url) in PG_BRANDS.items():
            if keyword in name_lower:
                platforms.append({"name": label, "url": url, "type": "direct"})
                break

        # Google search — always works as fallback
        platforms.append({
            "name": "Check Availability",
            "url": f"https://www.google.com/search?q={search_q}+rent+booking+price",
            "type": "ota",
        })

        return platforms[:2]

    @staticmethod
    def _guess_pg_amenities(name: str, pg_type: str) -> list:
        """Smart amenity guessing based on PG name and type."""
        base = ["WiFi", "AC"]
        name_lower = name.lower()
        if pg_type == "Coliving":
            base.extend(["Community", "Meals", "Laundry", "Security"])
        elif pg_type == "Serviced Apartment":
            base.extend(["Kitchen", "Housekeeping", "Security"])
        elif pg_type == "Hostel":
            base.extend(["Common Area", "Lockers", "Laundry"])
        else:  # Managed PG
            base.extend(["Meals", "Security", "Laundry"])
        if any(w in name_lower for w in ("premium", "luxury", "grand", "ultra")):
            base.append("Gym")
        if any(w in name_lower for w in ("women", "ladies", "girls")):
            base.append("Women Only")
        if any(w in name_lower for w in ("men", "boys", "gents")):
            base.append("Men Only")
        return list(dict.fromkeys(base))  # Dedupe while preserving order

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

    def autocomplete_cities(self, query: str, limit: int = 6,
                            restrict_city: str = None, place_search: bool = False) -> list:
        """
        Return city/area/place autocomplete suggestions.

        place_search=True  → geocode type (streets, colonies, landmarks, any specific place)
        place_search=False → (regions) type (cities + neighbourhoods)
        restrict_city      → adds Google location bias + strictbounds to pin results inside that city
        """
        query = (query or "").strip()
        if len(query) < 2:
            return []

        cache_key = f"ac_{query.lower()}_{(restrict_city or '').lower()}_{place_search}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        suggestions = []

        if self.configured:
            try:
                params = {
                    "input": query,
                    "key": self.api_key,
                    "language": "en",
                }

                if place_search:
                    # Full place search — captures roads, colonies, landmarks, buildings
                    # exactly like Google Maps search bar.
                    # We use geocode|establishment to cover both addressable locations
                    # (colonies, streets) and named businesses/landmarks.
                    # NOTE: No strictbounds — strict clipping hides valid colonies in
                    # smaller cities (e.g. GTP Colony, Dhule). Soft bias via
                    # location+radius ranks nearby results first without hiding them.
                    params["types"] = "geocode"
                    if restrict_city:
                        # Use component-filtered geocoding to get the precise city center.
                        # e.g. "Dhule" → exact Dhule, Maharashtra — not any other Dhule.
                        coords = self.geocode(
                            restrict_city,
                            components=f"locality:{restrict_city}",
                        )
                        if coords.get("lat") and coords.get("source") != "fallback":
                            params["location"] = f"{coords['lat']},{coords['lng']}"
                            params["radius"]   = 30000   # soft bias — ranks nearby first, doesn't hide results
                else:
                    # City / neighbourhood picker — strictbounds is fine here since
                    # we want results clearly within the region, not cross-city suggestions.
                    params["types"] = "(regions)"
                    if restrict_city:
                        coords = self.geocode(
                            restrict_city,
                            components=f"locality:{restrict_city}",
                        )
                        if coords.get("lat") and coords.get("source") != "fallback":
                            params["location"]     = f"{coords['lat']},{coords['lng']}"
                            params["radius"]       = 40000
                            params["strictbounds"] = "true"

                resp = requests.get(self.AUTOCOMPLETE_URL, params=params, timeout=5)
                if resp.status_code == 200:
                    city_check = (restrict_city or "").lower() if place_search else None
                    for p in resp.json().get("predictions", [])[:limit]:
                        sf = p.get("structured_formatting", {})
                        secondary = sf.get("secondary_text", "")
                        description = p.get("description", "")
                        # When restricting to a city in place_search mode, skip results
                        # that don't mention the restrict_city in their address — these are
                        # location-bias misses (e.g. same-named colony in a different state).
                        if city_check:
                            in_secondary = city_check in secondary.lower()
                            in_desc = city_check in description.lower()
                            if not in_secondary and not in_desc:
                                continue
                        suggestions.append({
                            "label": description,
                            "city": sf.get("main_text", description),
                            "secondary": secondary,
                            "place_id": p.get("place_id", ""),
                            "source": "google",
                        })

                # --- Geocoding fallback for place_search ---
                # When autocomplete has no results for a colony/area (e.g. "GTP Colony, Dhule"),
                # the Geocoding API with component filter often succeeds where autocomplete fails.
                # We use: address=QUERY&components=locality:CITY to pin it to the right city.
                if not suggestions and place_search and restrict_city:
                    try:
                        geo_params = {
                            "address": query,
                            "components": f"locality:{restrict_city}",
                            "key": self.api_key,
                        }
                        geo_resp = requests.get(self.GEOCODE_URL, params=geo_params, timeout=5)
                        if geo_resp.status_code == 200:
                            for r in geo_resp.json().get("results", [])[:limit]:
                                formatted = r.get("formatted_address", query)
                                loc = r.get("geometry", {}).get("location", {})
                                place_id = r.get("place_id", "")
                                # Split address parts; first component might be a Plus Code
                                parts = [p.strip() for p in formatted.split(",")]
                                # Skip leading Plus Code (e.g. "WQJH+54G") — not human-readable
                                if parts and self._PLUS_CODE_RE.match(parts[0]):
                                    parts = parts[1:]
                                # Use the query text itself as the display name so the user
                                # sees what they typed (e.g. "GTP Colony") rather than a
                                # formatted address fragment
                                short_name = query.title()
                                secondary = ", ".join(parts).strip()
                                suggestions.append({
                                    "label": f"{short_name}, {secondary}",
                                    "city": short_name,
                                    "secondary": secondary,
                                    "place_id": place_id,
                                    "lat": loc.get("lat"),
                                    "lng": loc.get("lng"),
                                    "source": "google_geocode",
                                })
                    except Exception as geo_err:
                        logger.warning("[Maps] Geocode fallback for autocomplete error: %s", geo_err)

            except Exception as e:
                logger.warning("[Maps] Autocomplete error: %s", e)

        # Fallback: area + city list when API unavailable
        if not suggestions:
            q_lower = query.lower()
            # Format: (display_name, secondary_text)
            # Specific areas are listed before their parent city so area matches surface first
            FALLBACK = [
                # ── Mumbai ────────────────────────────────────────────────────────
                ("Bandra", "Mumbai, Maharashtra, India"),
                ("Bandra Kurla Complex", "Mumbai, Maharashtra, India"),
                ("BKC", "Mumbai, Maharashtra, India"),
                ("Andheri", "Mumbai, Maharashtra, India"),
                ("Andheri East", "Mumbai, Maharashtra, India"),
                ("Andheri West", "Mumbai, Maharashtra, India"),
                ("Juhu", "Mumbai, Maharashtra, India"),
                ("Powai", "Mumbai, Maharashtra, India"),
                ("Colaba", "Mumbai, Maharashtra, India"),
                ("Lower Parel", "Mumbai, Maharashtra, India"),
                ("Worli", "Mumbai, Maharashtra, India"),
                ("Dadar", "Mumbai, Maharashtra, India"),
                ("Goregaon", "Mumbai, Maharashtra, India"),
                ("Malad", "Mumbai, Maharashtra, India"),
                ("Borivali", "Mumbai, Maharashtra, India"),
                ("Kurla", "Mumbai, Maharashtra, India"),
                ("Chembur", "Mumbai, Maharashtra, India"),
                ("Vikhroli", "Mumbai, Maharashtra, India"),
                ("Mulund", "Mumbai, Maharashtra, India"),
                ("Thane", "Mumbai Metropolitan Region, Maharashtra, India"),
                ("Navi Mumbai", "Maharashtra, India"),
                ("Mumbai", "Maharashtra, India"),
                # ── Delhi / NCR ────────────────────────────────────────────────────
                ("Connaught Place", "New Delhi, Delhi, India"),
                ("Karol Bagh", "New Delhi, Delhi, India"),
                ("Lajpat Nagar", "New Delhi, Delhi, India"),
                ("Saket", "New Delhi, Delhi, India"),
                ("Nehru Place", "New Delhi, Delhi, India"),
                ("Vasant Kunj", "New Delhi, Delhi, India"),
                ("South Delhi", "Delhi, India"),
                ("Dwarka", "Delhi, India"),
                ("Rohini", "Delhi, India"),
                ("Pitampura", "Delhi, India"),
                ("Janakpuri", "Delhi, India"),
                ("Paschim Vihar", "Delhi, India"),
                ("Rajouri Garden", "Delhi, India"),
                ("New Delhi", "Delhi, India"),
                ("Delhi", "India"),
                # ── Gurgaon / Gurugram ────────────────────────────────────────────
                ("Cyber City", "Gurugram, Haryana, India"),
                ("DLF Phase 1", "Gurugram, Haryana, India"),
                ("DLF Phase 2", "Gurugram, Haryana, India"),
                ("DLF Phase 3", "Gurugram, Haryana, India"),
                ("Golf Course Road", "Gurugram, Haryana, India"),
                ("Sohna Road", "Gurugram, Haryana, India"),
                ("MG Road", "Gurugram, Haryana, India"),
                ("Sector 29", "Gurugram, Haryana, India"),
                ("Sector 44", "Gurugram, Haryana, India"),
                ("Gurgaon", "Haryana, India"),
                ("Gurugram", "Haryana, India"),
                # ── Noida ─────────────────────────────────────────────────────────
                ("Sector 18", "Noida, Uttar Pradesh, India"),
                ("Sector 62", "Noida, Uttar Pradesh, India"),
                ("Sector 63", "Noida, Uttar Pradesh, India"),
                ("Sector 125", "Noida, Uttar Pradesh, India"),
                ("Greater Noida", "Uttar Pradesh, India"),
                ("Noida", "Uttar Pradesh, India"),
                # ── Bengaluru ─────────────────────────────────────────────────────
                ("Koramangala", "Bengaluru, Karnataka, India"),
                ("Indiranagar", "Bengaluru, Karnataka, India"),
                ("Whitefield", "Bengaluru, Karnataka, India"),
                ("Electronic City", "Bengaluru, Karnataka, India"),
                ("HSR Layout", "Bengaluru, Karnataka, India"),
                ("MG Road", "Bengaluru, Karnataka, India"),
                ("Jayanagar", "Bengaluru, Karnataka, India"),
                ("JP Nagar", "Bengaluru, Karnataka, India"),
                ("Marathahalli", "Bengaluru, Karnataka, India"),
                ("Hebbal", "Bengaluru, Karnataka, India"),
                ("Yelahanka", "Bengaluru, Karnataka, India"),
                ("Sarjapur Road", "Bengaluru, Karnataka, India"),
                ("Bannerghatta Road", "Bengaluru, Karnataka, India"),
                ("Rajajinagar", "Bengaluru, Karnataka, India"),
                ("Malleswaram", "Bengaluru, Karnataka, India"),
                ("Bangalore", "Karnataka, India"),
                ("Bengaluru", "Karnataka, India"),
                # ── Hyderabad ─────────────────────────────────────────────────────
                ("Hitech City", "Hyderabad, Telangana, India"),
                ("Gachibowli", "Hyderabad, Telangana, India"),
                ("Banjara Hills", "Hyderabad, Telangana, India"),
                ("Jubilee Hills", "Hyderabad, Telangana, India"),
                ("Madhapur", "Hyderabad, Telangana, India"),
                ("Secunderabad", "Telangana, India"),
                ("Kukatpally", "Hyderabad, Telangana, India"),
                ("Kondapur", "Hyderabad, Telangana, India"),
                ("Miyapur", "Hyderabad, Telangana, India"),
                ("Uppal", "Hyderabad, Telangana, India"),
                ("Hyderabad", "Telangana, India"),
                # ── Chennai ───────────────────────────────────────────────────────
                ("Anna Nagar", "Chennai, Tamil Nadu, India"),
                ("T. Nagar", "Chennai, Tamil Nadu, India"),
                ("Velachery", "Chennai, Tamil Nadu, India"),
                ("OMR", "Chennai, Tamil Nadu, India"),
                ("Old Mahabalipuram Road", "Chennai, Tamil Nadu, India"),
                ("Adyar", "Chennai, Tamil Nadu, India"),
                ("Nungambakkam", "Chennai, Tamil Nadu, India"),
                ("Guindy", "Chennai, Tamil Nadu, India"),
                ("Perambur", "Chennai, Tamil Nadu, India"),
                ("Porur", "Chennai, Tamil Nadu, India"),
                ("Sholinganallur", "Chennai, Tamil Nadu, India"),
                ("Thoraipakkam", "Chennai, Tamil Nadu, India"),
                ("Chennai", "Tamil Nadu, India"),
                # ── Pune ──────────────────────────────────────────────────────────
                ("Hinjewadi", "Pune, Maharashtra, India"),
                ("Kothrud", "Pune, Maharashtra, India"),
                ("Koregaon Park", "Pune, Maharashtra, India"),
                ("Wakad", "Pune, Maharashtra, India"),
                ("Baner", "Pune, Maharashtra, India"),
                ("Viman Nagar", "Pune, Maharashtra, India"),
                ("Hadapsar", "Pune, Maharashtra, India"),
                ("Aundh", "Pune, Maharashtra, India"),
                ("Kharadi", "Pune, Maharashtra, India"),
                ("Shivajinagar", "Pune, Maharashtra, India"),
                ("Pimpri", "Pune, Maharashtra, India"),
                ("Pune", "Maharashtra, India"),
                # ── Kolkata ───────────────────────────────────────────────────────
                ("Salt Lake", "Kolkata, West Bengal, India"),
                ("Park Street", "Kolkata, West Bengal, India"),
                ("Rajarhat", "Kolkata, West Bengal, India"),
                ("Howrah", "West Bengal, India"),
                ("New Town", "Kolkata, West Bengal, India"),
                ("Esplanade", "Kolkata, West Bengal, India"),
                ("Kolkata", "West Bengal, India"),
                # ── Ahmedabad ─────────────────────────────────────────────────────
                ("SG Highway", "Ahmedabad, Gujarat, India"),
                ("Bodakdev", "Ahmedabad, Gujarat, India"),
                ("Vastrapur", "Ahmedabad, Gujarat, India"),
                ("Navrangpura", "Ahmedabad, Gujarat, India"),
                ("Prahlad Nagar", "Ahmedabad, Gujarat, India"),
                ("Ahmedabad", "Gujarat, India"),
                # ── Other major cities ────────────────────────────────────────────
                ("Jaipur", "Rajasthan, India"),
                ("Surat", "Gujarat, India"),
                ("Lucknow", "Uttar Pradesh, India"),
                ("Kanpur", "Uttar Pradesh, India"),
                ("Nagpur", "Maharashtra, India"),
                ("Indore", "Madhya Pradesh, India"),
                ("Bhopal", "Madhya Pradesh, India"),
                ("Visakhapatnam", "Andhra Pradesh, India"),
                ("Vizag", "Andhra Pradesh, India"),
                ("Patna", "Bihar, India"),
                ("Vadodara", "Gujarat, India"),
                ("Ludhiana", "Punjab, India"),
                ("Agra", "Uttar Pradesh, India"),
                ("Nashik", "Maharashtra, India"),
                ("Faridabad", "Haryana, India"),
                ("Rajkot", "Gujarat, India"),
                ("Varanasi", "Uttar Pradesh, India"),
                ("Amritsar", "Punjab, India"),
                ("Prayagraj", "Uttar Pradesh, India"),
                ("Ranchi", "Jharkhand, India"),
                ("Coimbatore", "Tamil Nadu, India"),
                ("Jodhpur", "Rajasthan, India"),
                ("Madurai", "Tamil Nadu, India"),
                ("Raipur", "Chhattisgarh, India"),
                ("Kochi", "Kerala, India"),
                ("Chandigarh", "India"),
                ("Guwahati", "Assam, India"),
                ("Thiruvananthapuram", "Kerala, India"),
                ("Goa", "India"),
                ("Panaji", "Goa, India"),
                ("Udaipur", "Rajasthan, India"),
                ("Shimla", "Himachal Pradesh, India"),
                ("Manali", "Himachal Pradesh, India"),
                ("Mysuru", "Karnataka, India"),
                ("Mysore", "Karnataka, India"),
                ("Pondicherry", "India"),
                ("Dehradun", "Uttarakhand, India"),
                ("Mangalore", "Karnataka, India"),
                ("Hubli", "Karnataka, India"),
                # ── International ─────────────────────────────────────────────────
                ("Dubai", "UAE"),
                ("Dubai Marina", "Dubai, UAE"),
                ("Downtown Dubai", "Dubai, UAE"),
                ("Singapore", "Singapore"),
                ("London", "United Kingdom"),
                ("New York", "United States"),
                ("Manhattan", "New York, United States"),
                ("Bangkok", "Thailand"),
                ("Kuala Lumpur", "Malaysia"),
            ]
            for display_name, secondary in FALLBACK:
                if q_lower in display_name.lower() or display_name.lower().startswith(q_lower):
                    suggestions.append({
                        "label": f"{display_name}, {secondary}",
                        "city": display_name,
                        "secondary": secondary,
                        "place_id": "",
                        "source": "fallback",
                    })
                    if len(suggestions) >= limit:
                        break

        self._cache[cache_key] = suggestions
        return suggestions

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

    def _haversine_coords_km(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Haversine distance between two explicit lat/lng coordinates (km)."""
        r1 = math.radians(lat1); r2 = math.radians(lat2)
        dr = math.radians(lat2 - lat1); dl = math.radians(lng2 - lng1)
        a = math.sin(dr / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dl / 2) ** 2
        return 6371 * 2 * math.asin(math.sqrt(a))

    def verify_area_in_city(self, place_id: str, destination: str) -> dict:
        """
        Check whether a Google place (identified by place_id) lies within the
        destination city — using geocoded coordinates, NOT string matching.

        Returns:
          {
            "valid": bool,           True when the area is plausibly in/near the city
            "distance_km": float,    straight-line km from city centre
            "area_name": str,        human-readable formatted address of the area
            "city_name": str,        resolved destination city name
          }
        Always returns valid=True when coordinates cannot be resolved (fail-open).
        """
        if not self.configured or not place_id or not destination:
            return {"valid": True, "distance_km": 0.0, "area_name": "", "city_name": destination}

        # ── Resolve meeting area coordinates ─────────────────────────
        area_coords = self.geocode_by_place_id(place_id)
        if area_coords.get("source") == "fallback" or not area_coords.get("lat"):
            return {"valid": True, "distance_km": 0.0, "area_name": "", "city_name": destination}

        # ── Resolve destination city center coordinates ───────────────
        city_coords = self.geocode(destination, components=f"locality:{destination}")
        if city_coords.get("source") == "fallback" or not city_coords.get("lat"):
            city_coords = self.geocode(destination)
        if city_coords.get("source") == "fallback" or not city_coords.get("lat"):
            return {"valid": True, "distance_km": 0.0,
                    "area_name": area_coords.get("formatted", ""), "city_name": destination}

        distance_km = self._haversine_coords_km(
            area_coords["lat"], area_coords["lng"],
            city_coords["lat"], city_coords["lng"],
        )

        # Threshold: tier-1 metros have large footprints; use 60 km for safety.
        # A 60 km radius captures Hinjewadi→Pune CBD (25 km), Whitefield→Bangalore (20 km), etc.
        # Anything beyond 60 km is genuinely a different city.
        valid = distance_km <= 60.0

        return {
            "valid": valid,
            "distance_km": round(distance_km, 1),
            "area_name": area_coords.get("formatted", ""),
            "city_name": city_coords.get("formatted", destination),
        }


maps = MapsService()
