"""
TravelSync Pro — Flight Search Service
Uses AviationStack API when configured; falls back to realistic curated flight data.
Get a free API key at: https://aviationstack.com (100 req/month free)

Optional env: AVIATIONSTACK_API_KEY
"""
import os
import random
import logging
from datetime import datetime, timedelta
from services.http_client import http as requests
from cachetools import TTLCache

logger = logging.getLogger(__name__)

AIRLINES_INDIA = [
    {"code": "6E", "name": "IndiGo",          "iata": "6E", "url": "https://www.goindigo.in"},
    {"code": "AI", "name": "Air India",        "iata": "AI", "url": "https://www.airindia.in"},
    {"code": "SG", "name": "SpiceJet",         "iata": "SG", "url": "https://www.spicejet.com"},
    {"code": "UK", "name": "Vistara",          "iata": "UK", "url": "https://www.airvistara.com"},
    {"code": "IX", "name": "Air Asia India",   "iata": "IX", "url": "https://www.airasia.com/in"},
    {"code": "QP", "name": "Akasa Air",        "iata": "QP", "url": "https://www.akasaair.com"},
]

AIRLINES_INTL = [
    {"code": "EK", "name": "Emirates",         "iata": "EK", "url": "https://www.emirates.com"},
    {"code": "QR", "name": "Qatar Airways",    "iata": "QR", "url": "https://www.qatarairways.com"},
    {"code": "SQ", "name": "Singapore Airlines","iata": "SQ", "url": "https://www.singaporeair.com"},
    {"code": "BA", "name": "British Airways",  "iata": "BA", "url": "https://www.britishairways.com"},
    {"code": "LH", "name": "Lufthansa",        "iata": "LH", "url": "https://www.lufthansa.com"},
    {"code": "AF", "name": "Air France",       "iata": "AF", "url": "https://www.airfrance.com"},
    {"code": "TG", "name": "Thai Airways",     "iata": "TG", "url": "https://www.thaiairways.com"},
    {"code": "AI", "name": "Air India",        "iata": "AI", "url": "https://www.airindia.in"},
]

# Typical departure windows (hour, minute)
_DEPARTURE_SLOTS = [
    (5, 30), (6, 0), (6, 45), (7, 15), (8, 0), (8, 30),
    (9, 15), (10, 0), (11, 30), (12, 45), (14, 0), (15, 30),
    (16, 45), (17, 30), (18, 0), (19, 15), (20, 0), (21, 30),
    (22, 0), (23, 15),
]

# Domestic India base fares (INR) by distance bucket
_DOMESTIC_FARES = {
    "short":  (2500,  6000),   # < 500 km
    "medium": (3500,  9000),   # 500-1200 km
    "long":   (5000, 14000),   # > 1200 km
}

# International fares (INR) rough buckets
_INTL_FARES = {
    "gulf":      (18000,  40000),
    "southeast": (22000,  55000),
    "europe":    (45000, 120000),
    "usa":       (60000, 160000),
    "other":     (30000,  90000),
}


CITY_AIRPORT_CODES = {
    "mumbai": "BOM", "delhi": "DEL", "new delhi": "DEL",
    "bangalore": "BLR", "bengaluru": "BLR", "hyderabad": "HYD",
    "chennai": "MAA", "madras": "MAA", "kolkata": "CCU", "calcutta": "CCU",
    "pune": "PNQ", "ahmedabad": "AMD", "kochi": "COK", "cochin": "COK",
    "goa": "GOI", "panaji": "GOI", "jaipur": "JAI", "lucknow": "LKO",
    "varanasi": "VNS", "amritsar": "ATQ", "chandigarh": "IXC",
    "nagpur": "NAG", "bhopal": "BHO", "indore": "IDR", "surat": "STV",
    "coimbatore": "CJB", "mangalore": "IXE", "trichy": "TRZ",
    "patna": "PAT", "ranchi": "IXR", "bhubaneswar": "BBI",
    "visakhapatnam": "VTZ", "vijayawada": "VGA", "tirupati": "TIR",
    "jodhpur": "JDH", "udaipur": "UDR", "aurangabad": "IXU",
    "srinagar": "SXR", "leh": "IXL", "bagdogra": "IXB",
    "guwahati": "GAU", "imphal": "IMF", "agartala": "IXA",
    # International
    "dubai": "DXB", "abu dhabi": "AUH", "doha": "DOH", "riyadh": "RUH",
    "london": "LHR", "paris": "CDG", "frankfurt": "FRA", "berlin": "BER",
    "amsterdam": "AMS", "madrid": "MAD", "barcelona": "BCN", "rome": "FCO",
    "zurich": "ZRH", "vienna": "VIE", "prague": "PRG", "istanbul": "IST",
    "new york": "JFK", "los angeles": "LAX", "san francisco": "SFO",
    "chicago": "ORD", "dallas": "DFW", "miami": "MIA", "seattle": "SEA",
    "toronto": "YYZ", "vancouver": "YVR", "mexico city": "MEX",
    "sao paulo": "GRU", "buenos aires": "EZE", "santiago": "SCL",
    "singapore": "SIN", "bangkok": "BKK", "kuala lumpur": "KUL",
    "jakarta": "CGK", "manila": "MNL", "hong kong": "HKG",
    "tokyo": "NRT", "osaka": "KIX", "seoul": "ICN", "beijing": "PEK",
    "shanghai": "PVG", "sydney": "SYD", "melbourne": "MEL",
    "auckland": "AKL", "cape town": "CPT", "johannesburg": "JNB",
    "cairo": "CAI", "nairobi": "NBO",
}


def get_airport_code(city_name: str) -> str:
    """Map city name to IATA airport code."""
    normalized = (city_name or "").strip().lower()
    if not normalized:
        return ""
    if normalized in CITY_AIRPORT_CODES:
        return CITY_AIRPORT_CODES[normalized]
    city_key = normalized.split(",")[0].strip()
    return CITY_AIRPORT_CODES.get(city_key, city_name[:3].upper())


NO_FLY_PAIRS = {
    frozenset({"pune", "mumbai"}), frozenset({"gurgaon", "delhi"}),
    frozenset({"noida", "delhi"}), frozenset({"navi mumbai", "mumbai"}),
    frozenset({"thane", "mumbai"}), frozenset({"ghaziabad", "delhi"}),
    frozenset({"gurugram", "delhi"}),
}


class FlightsService:
    AVIATIONSTACK_URL = "https://api.aviationstack.com/v1/flights"

    def __init__(self):
        self.api_key = os.getenv("AVIATIONSTACK_API_KEY")
        self.configured = bool(self.api_key)
        self._cache = TTLCache(maxsize=100, ttl=1800)

    def search_flights(self, origin: str, destination: str,
                       departure_date: str, adults: int = 1,
                       max_results: int = 6) -> dict:
        """
        Search one-way flights. Validates route first.
        Returns empty if no flights exist on this route.
        """
        cache_key = f"fl_{origin}_{destination}_{departure_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Validate: both must be recognized airport cities
        o_lower = self._resolve_city(origin).lower()
        d_lower = self._resolve_city(destination).lower()

        if not o_lower or not d_lower:
            return {"flights": [], "source": "none", "reason": "Unknown city"}

        # No flights for same city or very close cities
        if o_lower == d_lower:
            return {"flights": [], "source": "none", "reason": "Same city"}

        if frozenset({o_lower, d_lower}) in NO_FLY_PAIRS:
            return {"flights": [], "source": "none", "reason": "Cities too close for flights"}

        # Check if both cities have airports
        if o_lower not in CITY_AIRPORT_CODES and origin.upper() not in set(CITY_AIRPORT_CODES.values()):
            return {"flights": [], "source": "none", "reason": f"No airport in {origin}"}
        if d_lower not in CITY_AIRPORT_CODES and destination.upper() not in set(CITY_AIRPORT_CODES.values()):
            return {"flights": [], "source": "none", "reason": f"No airport in {destination}"}

        # Try AviationStack live data
        if self.configured:
            result = self._aviationstack_search(
                origin, destination, departure_date, adults, max_results)
            if result.get("flights"):
                self._cache[cache_key] = result
                return result

        # Fall back to AI-validated curated data
        result = self._curated_flights(
            origin, destination, departure_date, adults, max_results)
        self._cache[cache_key] = result
        return result

    def _resolve_city(self, code_or_name: str) -> str:
        """Resolve airport code back to city name, or return as-is."""
        code_upper = code_or_name.strip().upper()
        rev = {v: k for k, v in CITY_AIRPORT_CODES.items()}
        return rev.get(code_upper, code_or_name.strip().lower())

    # ── AviationStack ────────────────────────────────────────────────

    def _aviationstack_search(self, origin: str, destination: str,
                               departure_date: str, adults: int,
                               max_results: int) -> dict:
        try:
            params = {
                "access_key": self.api_key,
                "dep_iata": origin.upper(),
                "arr_iata": destination.upper(),
                "flight_date": departure_date,
                "limit": max_results,
            }
            resp = requests.get(self.AVIATIONSTACK_URL, params=params, timeout=10)
            if resp.status_code != 200:
                return {"flights": []}
            data = resp.json()
            raw = data.get("data", [])
            if not raw:
                return {"flights": []}

            flights = []
            for f in raw[:max_results]:
                dep = f.get("departure", {})
                arr = f.get("arrival", {})
                airline = f.get("airline", {})
                fl = f.get("flight", {})

                dep_time = dep.get("scheduled", "")
                arr_time = arr.get("scheduled", "")
                duration = _calc_duration(dep_time, arr_time)

                price = self._estimate_price(origin, destination)

                flights.append({
                    "airline": airline.get("name", ""),
                    "airline_code": airline.get("iata", ""),
                    "flight_number": fl.get("iata", fl.get("number", "")),
                    "departure_time": _fmt_time(dep_time),
                    "arrival_time": _fmt_time(arr_time),
                    "duration": duration,
                    "stops": 0,
                    "stop_label": "Non-stop",
                    "price": price,
                    "fare": price,
                    "currency": "INR",
                    "price_display": f"₹{price:,}",
                    "cabin": "Economy",
                    "booking_url": self._booking_url(
                        origin, destination, departure_date, adults,
                        airline.get("name", "")
                    ),
                    "source": "aviationstack",
                })

            return {
                "flights": flights,
                "source": "aviationstack",
                "origin_code": origin,
                "dest_code": destination,
            }
        except Exception as e:
            logger.warning("[Flights] AviationStack error: %s", e)
            return {"flights": []}

    # ── AI-enhanced curated data ─────────────────────────────────────

    def _curated_flights(self, origin: str, destination: str,
                          departure_date: str, adults: int,
                          max_results: int) -> dict:
        o_city = self._resolve_city(origin)
        d_city = self._resolve_city(destination)
        is_domestic = self._is_domestic_india(origin, destination)

        # Use AI for realistic flights on this specific route
        ai_flights = self._ai_generate_flights(o_city, d_city, departure_date, is_domestic, max_results)
        if ai_flights:
            for f in ai_flights:
                f["booking_url"] = self._booking_url(origin, destination, departure_date, adults, f.get("airline", ""))
            return {
                "flights": ai_flights[:max_results],
                "source": "ai_generated",
                "origin_code": origin,
                "dest_code": destination,
            }

        # Fallback: deterministic curated data
        airlines = AIRLINES_INDIA if is_domestic else AIRLINES_INTL
        fare_range = self._fare_range(origin, destination, is_domestic)

        random.seed(f"{origin}{destination}{departure_date}")
        slots = random.sample(_DEPARTURE_SLOTS, min(max_results, len(_DEPARTURE_SLOTS)))
        selected_airlines = [airlines[i % len(airlines)] for i in range(max_results)]

        flights = []
        for i, (hour, minute) in enumerate(slots[:max_results]):
            airline = selected_airlines[i]
            price_base = random.randint(*fare_range)
            price = price_base * adults if adults > 1 else price_base
            duration_hrs = self._estimate_duration(origin, destination)
            dep_dt = datetime.strptime(departure_date, "%Y-%m-%d").replace(hour=hour, minute=minute)
            arr_dt = dep_dt + timedelta(hours=duration_hrs)
            stops = 0 if duration_hrs < 3 or is_domestic else (1 if random.random() < 0.4 else 0)

            flights.append({
                "airline": airline["name"],
                "airline_code": airline["iata"],
                "flight_number": f"{airline['iata']}{random.randint(100, 999)}",
                "origin": origin, "destination": destination,
                "departure_time": dep_dt.strftime("%H:%M"),
                "arrival_time": arr_dt.strftime("%H:%M"),
                "duration": f"{int(duration_hrs)}h {int((duration_hrs % 1) * 60)}m",
                "stops": stops,
                "stop_label": "Non-stop" if stops == 0 else f"{stops} stop",
                "price": price, "fare": price, "currency": "INR",
                "price_display": f"₹{price:,}", "cabin": "Economy",
                "booking_url": self._booking_url(origin, destination, departure_date, adults, airline["name"]),
                "airline_url": airline["url"], "source": "curated",
            })

        flights.sort(key=lambda x: x["price"])
        return {"flights": flights, "source": "curated", "origin_code": origin, "dest_code": destination}

    def _ai_generate_flights(self, origin_city: str, dest_city: str,
                              date: str, is_domestic: bool, limit: int) -> list:
        """Use Gemini (free) to generate realistic flights for this specific route."""
        cache_key = f"ai_fl_{origin_city}_{dest_city}_{date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt = (
            f"List {limit} realistic flights from {origin_city} to {dest_city} on {date}.\n"
            f"Only include airlines that ACTUALLY fly this route.\n"
            f"Use real flight numbers if you know them, otherwise realistic ones.\n\n"
            f"Format per line (pipe-separated):\n"
            f"Airline | FlightNo | DepartTime | ArriveTime | Duration | Stops | Price_INR\n\n"
            f"Example:\n"
            f"IndiGo | 6E 302 | 06:15 | 08:30 | 2h 15m | 0 | 4500\n\n"
            f"Rules:\n"
            f"- Only airlines that fly {origin_city} to {dest_city}\n"
            f"- Realistic 2026 prices in INR\n"
            f"- Include departure/arrival times\n"
            f"- If NO airline flies this route directly, say NONE"
        )

        response = None
        try:
            from services.gemini_service import gemini
            import time
            if gemini.configured and not (hasattr(gemini, '_cooldown_until') and time.time() < gemini._cooldown_until):
                response = gemini.generate(prompt, model_type="flash")
        except Exception:
            pass

        if not response or "NONE" in response.upper()[:20]:
            return []

        import re
        flights = []
        for line in response.strip().split("\n"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 6:
                continue

            airline = re.sub(r'^\d+[\.\)\-]\s*', '', parts[0]).replace('**', '').strip()
            if not airline or airline.lower().startswith("airline") or airline.lower().startswith("example"):
                continue

            flight_no = parts[1].strip().replace('**', '') if len(parts) > 1 else ""
            dep_time = parts[2].strip() if len(parts) > 2 else ""
            arr_time = parts[3].strip() if len(parts) > 3 else ""
            duration = parts[4].strip() if len(parts) > 4 else ""
            stops_str = parts[5].strip() if len(parts) > 5 else "0"
            price_str = parts[6].strip() if len(parts) > 6 else ""

            try:
                stops = int(re.sub(r'[^\d]', '', stops_str) or "0")
            except ValueError:
                stops = 0

            price_cleaned = re.sub(r'[^\d]', '', price_str)
            try:
                price = int(price_cleaned) if price_cleaned else 0
            except ValueError:
                price = 0

            if price < 500 or price > 200000:
                price = 0

            # Find airline URL
            airline_url = ""
            for a in AIRLINES_INDIA + AIRLINES_INTL:
                if a["name"].lower() in airline.lower() or airline.lower() in a["name"].lower():
                    airline_url = a["url"]
                    break

            flights.append({
                "airline": airline,
                "airline_code": flight_no.split()[0] if flight_no else "",
                "flight_number": flight_no,
                "origin": origin_city, "destination": dest_city,
                "departure_time": dep_time, "arrival_time": arr_time,
                "duration": duration, "stops": stops,
                "stop_label": "Non-stop" if stops == 0 else f"{stops} stop",
                "price": price, "fare": price, "currency": "INR",
                "price_display": f"₹{price:,}" if price else "",
                "cabin": "Economy", "airline_url": airline_url,
                "source": "ai_generated",
            })

        if flights:
            self._cache[cache_key] = flights
        return flights

    # ── Helpers ──────────────────────────────────────────────────────

    def _is_domestic_india(self, origin: str, destination: str) -> bool:
        india_codes = set(CITY_AIRPORT_CODES.values())
        # Remove international codes
        intl_prefixes = {"LHR", "CDG", "FRA", "JFK", "LAX", "SIN", "BKK", "DXB",
                         "DOH", "NRT", "ICN", "SYD", "MEL", "AMS", "IST", "BER"}
        return (origin.upper() not in intl_prefixes and
                destination.upper() not in intl_prefixes and
                origin.upper() in india_codes and
                destination.upper() in india_codes)

    def _fare_range(self, origin: str, destination: str, is_domestic: bool) -> tuple:
        if is_domestic:
            dist = self._rough_distance(origin, destination)
            if dist < 500:
                return _DOMESTIC_FARES["short"]
            if dist < 1200:
                return _DOMESTIC_FARES["medium"]
            return _DOMESTIC_FARES["long"]

        # International
        gulf = {"DXB", "AUH", "DOH", "RUH", "KWI", "BAH"}
        se_asia = {"SIN", "BKK", "KUL", "CGK", "MNL", "HAN", "SGN"}
        europe = {"LHR", "CDG", "FRA", "AMS", "FCO", "MAD", "BER", "ZRH", "VIE"}
        usa = {"JFK", "LAX", "SFO", "ORD", "DFW", "MIA"}

        dest_u = destination.upper()
        if dest_u in gulf:
            return _INTL_FARES["gulf"]
        if dest_u in se_asia:
            return _INTL_FARES["southeast"]
        if dest_u in europe:
            return _INTL_FARES["europe"]
        if dest_u in usa:
            return _INTL_FARES["usa"]
        return _INTL_FARES["other"]

    def _estimate_duration(self, origin: str, destination: str) -> float:
        dist = self._rough_distance(origin, destination)
        # ~800 km/h cruise + 30-min overhead
        return max(0.75, dist / 800 + 0.5)

    def _rough_distance(self, origin: str, destination: str) -> float:
        """Very rough distance lookup by airport code."""
        from services.maps_service import maps

        rev = {v: k for k, v in CITY_AIRPORT_CODES.items()}
        o_city = rev.get(origin.upper(), origin)
        d_city = rev.get(destination.upper(), destination)
        try:
            return maps.get_distance_km(o_city, d_city)
        except Exception:
            return 1000  # safe default

    def _estimate_price(self, origin: str, destination: str) -> int:
        is_dom = self._is_domestic_india(origin, destination)
        lo, hi = self._fare_range(origin, destination, is_dom)
        return random.randint(lo, hi)

    def _booking_url(self, origin: str, destination: str, date: str,
                     adults: int, airline_name: str = "") -> str:
        """Generate reliable booking URL — Google Flights always works."""
        rev = {v: k for k, v in CITY_AIRPORT_CODES.items()}
        o_city = rev.get(origin.upper(), origin).replace(' ', '+')
        d_city = rev.get(destination.upper(), destination).replace(' ', '+')
        search_q = f"{airline_name} {o_city} to {d_city} {date} flight booking".replace(' ', '+')
        return f"https://www.google.com/search?q={search_q}"

    def _airline_url(self, airline_name: str) -> str:
        """Get direct airline website."""
        for a in AIRLINES_INDIA + AIRLINES_INTL:
            if a["name"].lower() == airline_name.lower():
                return a["url"]
        return ""


# ── Module-level helpers ─────────────────────────────────────────────

def _fmt_time(iso_str: str) -> str:
    if not iso_str:
        return ""
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
        try:
            return datetime.strptime(iso_str[:19], fmt[:len(fmt)]).\
                strftime("%H:%M")
        except ValueError:
            continue
    return iso_str[:5]


def _calc_duration(dep: str, arr: str) -> str:
    if not dep or not arr:
        return ""
    try:
        d = datetime.fromisoformat(dep[:19])
        a = datetime.fromisoformat(arr[:19])
        mins = int((a - d).total_seconds() / 60)
        if mins <= 0:
            return ""
        return f"{mins // 60}h {mins % 60}m"
    except Exception:
        return ""


flights = FlightsService()
