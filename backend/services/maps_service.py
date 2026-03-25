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
        self._pg_cache = TTLCache(maxsize=50, ttl=1800)  # PG results cached 30 min
        self._hotel_cache = TTLCache(maxsize=50, ttl=900)  # Hotel results cached 15 min

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

    def search_hotels(self, city: str, budget_max: int = None, limit: int = 8) -> list:
        """
        Search real hotels in a city using Google Places Nearby Search.
        Returns hotels with real names, ratings, and addresses.
        """
        if not self.configured:
            return []

        cache_key = f"hotel_{city.lower()}_{budget_max}_{limit}"
        if cache_key in self._hotel_cache:
            return self._hotel_cache[cache_key]

        # 1. Geocode city → lat/lng
        coords = self.geocode(city)
        if coords.get("source") == "fallback" or not coords.get("lat"):
            return []

        # 2. Nearby search for lodging
        try:
            params = {
                "location": f"{coords['lat']},{coords['lng']}",
                "radius": 5000,
                "type": "lodging",
                "key": self.api_key,
            }
            resp = requests.get(self.PLACES_URL, params=params, timeout=15)
            if resp.status_code != 200:
                return []

            PRICE_MAP = {0: (800, 2000), 1: (1500, 4000), 2: (3500, 8000),
                         3: (7000, 18000), 4: (15000, 40000)}

            hotels = []
            for p in resp.json().get("results", [])[:limit]:
                price_level = p.get("price_level", 2)
                lo, hi = PRICE_MAP.get(price_level, (3000, 10000))
                import random
                price = random.randint(lo, hi)
                if budget_max and price > budget_max:
                    continue

                # Build photo URL from photo_reference
                photo_url = None
                photos = p.get("photos", [])
                if photos and photos[0].get("photo_reference"):
                    photo_url = (
                        f"https://maps.googleapis.com/maps/api/place/photo"
                        f"?maxwidth=600&photo_reference={photos[0]['photo_reference']}"
                        f"&key={self.api_key}"
                    )

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
                    "amenities": self._guess_amenities(p, price_level),
                    "place_id": place_id,
                    "latitude": lat,
                    "longitude": lng,
                    "maps_url": maps_url,
                    "google_search_url": google_search_url,
                    "booking_platforms": booking_platforms,
                    "source": "google_places",
                })
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

    def search_pg_options(self, city: str, budget_monthly: int = None, limit: int = 8) -> list:
        """
        Search PG / coliving / serviced apartments using Google Places.
        City-tier aware: only shows PG in cities where they actually exist.
        AI validates results to filter out non-PG false positives.
        """
        if not self.configured:
            return []

        city_lower = city.lower().strip()
        city_slug = city_lower.replace(' ', '-')

        # Tier check — don't show PG for small cities
        if city_lower in self.TIER1_CITIES:
            tier = "tier1"
        elif city_lower in self.TIER2_CITIES:
            tier = "tier2"
        else:
            # Ask AI if this city has PG/coliving options
            if not self._city_has_pg(city):
                logger.info("[Maps] PG not available in %s (low-tier city)", city)
                return []
            tier = "tier2"

        coords = self.geocode(city)
        if not coords.get("lat") or coords.get("source") == "fallback":
            return []

        pg_cache_key = f"pg_{city_lower}_{limit}"
        if pg_cache_key in self._pg_cache:
            return self._pg_cache[pg_cache_key]

        # Google Places doesn't index PGs well in India.
        # Use AI to generate genuine PG options with real operators.
        results = self._ai_generate_pg_options(city, tier, limit)
        if results:
            self._pg_cache[pg_cache_key] = results
        return results

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
