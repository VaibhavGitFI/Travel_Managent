"""
TravelSync Pro — Amadeus Travel API Service
Real-time flights & hotels via Amadeus Self-Service API.
Falls back to curated mock data when not configured.
Get free API keys at: https://developers.amadeus.com/register
"""
import os
import random
import logging
import requests
from datetime import datetime, timedelta
from cachetools import TTLCache

logger = logging.getLogger(__name__)


# Major airport/city codes used as a fast local lookup before live API resolution.
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

AIRLINES = [
    {"code": "6E", "name": "IndiGo", "url": "https://www.goindigo.in"},
    {"code": "SG", "name": "SpiceJet", "url": "https://www.spicejet.com"},
    {"code": "AI", "name": "Air India", "url": "https://www.airindia.in"},
    {"code": "UK", "name": "Vistara (Air India)", "url": "https://www.airvistara.com"},
    {"code": "G8", "name": "Go First", "url": "https://www.gofirst.in"},
    {"code": "IX", "name": "Air Asia India", "url": "https://www.airasia.com/in"},
]

HOTEL_DATA = {
    "BOM": [
        {"name": "Taj Mahal Palace", "rating": 5.0, "area": "Colaba", "price_range": (12000, 35000)},
        {"name": "ITC Maratha", "rating": 5.0, "area": "Andheri", "price_range": (8000, 22000)},
        {"name": "JW Marriott Mumbai", "rating": 5.0, "area": "Juhu", "price_range": (9000, 25000)},
        {"name": "Novotel Mumbai", "rating": 4.0, "area": "Juhu", "price_range": (5000, 12000)},
        {"name": "Ibis Mumbai Airport", "rating": 3.5, "area": "Vile Parle", "price_range": (3000, 6000)},
        {"name": "Trident Nariman Point", "rating": 5.0, "area": "Nariman Point", "price_range": (10000, 28000)},
    ],
    "DEL": [
        {"name": "The Imperial New Delhi", "rating": 5.0, "area": "Janpath", "price_range": (15000, 40000)},
        {"name": "ITC Maurya", "rating": 5.0, "area": "Diplomatic Enclave", "price_range": (10000, 30000)},
        {"name": "Taj Palace Hotel", "rating": 5.0, "area": "Diplomatic Enclave", "price_range": (12000, 35000)},
        {"name": "Hyatt Regency Delhi", "rating": 4.5, "area": "Bhikaji Cama Place", "price_range": (7000, 18000)},
        {"name": "Lemon Tree Premier Delhi", "rating": 4.0, "area": "Aerocity", "price_range": (4500, 9000)},
        {"name": "Ibis New Delhi Aerocity", "rating": 3.5, "area": "Aerocity", "price_range": (3000, 6000)},
    ],
    "BLR": [
        {"name": "ITC Windsor", "rating": 5.0, "area": "Golf Course Rd", "price_range": (9000, 24000)},
        {"name": "The Oberoi Bengaluru", "rating": 5.0, "area": "MG Road", "price_range": (12000, 32000)},
        {"name": "Taj MG Road", "rating": 5.0, "area": "MG Road", "price_range": (8000, 22000)},
        {"name": "Courtyard Marriott Bengaluru", "rating": 4.0, "area": "Outer Ring Road", "price_range": (5000, 12000)},
        {"name": "Lemon Tree Whitefield", "rating": 4.0, "area": "Whitefield", "price_range": (4000, 8000)},
    ],
    "HYD": [
        {"name": "ITC Kohenur", "rating": 5.0, "area": "HITEC City", "price_range": (9000, 25000)},
        {"name": "Taj Falaknuma Palace", "rating": 5.0, "area": "Falaknuma", "price_range": (20000, 55000)},
        {"name": "Marriott Hyderabad", "rating": 5.0, "area": "HITEC City", "price_range": (7000, 18000)},
        {"name": "Novotel Hyderabad Airport", "rating": 4.0, "area": "Shamshabad", "price_range": (4500, 10000)},
        {"name": "Lemon Tree Premier HITEC", "rating": 4.0, "area": "HITEC City", "price_range": (4000, 9000)},
    ],
    "MAA": [
        {"name": "ITC Grand Chola", "rating": 5.0, "area": "Anna Salai", "price_range": (10000, 28000)},
        {"name": "The Leela Palace Chennai", "rating": 5.0, "area": "Old Mahabalipuram Rd", "price_range": (12000, 32000)},
        {"name": "Taj Coromandel", "rating": 5.0, "area": "Nungambakkam", "price_range": (9000, 24000)},
        {"name": "Hilton Chennai", "rating": 4.5, "area": "OMR", "price_range": (6000, 14000)},
    ],
    "GOI": [
        {"name": "Taj Exotica Resort Goa", "rating": 5.0, "area": "Benaulim", "price_range": (15000, 45000)},
        {"name": "The Leela Goa", "rating": 5.0, "area": "Mobor", "price_range": (12000, 38000)},
        {"name": "Novotel Goa Resort", "rating": 4.0, "area": "Candolim", "price_range": (6000, 15000)},
        {"name": "Aloft North Goa", "rating": 4.0, "area": "Candolim", "price_range": (5000, 12000)},
    ],
    "PNQ": [
        {"name": "JW Marriott Pune", "rating": 5.0, "area": "Senapati Bapat Road", "price_range": (8000, 22000)},
        {"name": "Hyatt Regency Pune", "rating": 5.0, "area": "Viman Nagar", "price_range": (7000, 18000)},
        {"name": "The Westin Pune", "rating": 5.0, "area": "Koregaon Park", "price_range": (8000, 20000)},
        {"name": "Novotel Pune Nagar Road", "rating": 4.0, "area": "Nagar Road", "price_range": (5000, 12000)},
        {"name": "Lemon Tree Hotel Pune", "rating": 4.0, "area": "Wakad", "price_range": (3500, 8000)},
        {"name": "Ibis Pune Hinjewadi", "rating": 3.5, "area": "Hinjewadi", "price_range": (2800, 5500)},
    ],
    "JAI": [
        {"name": "Rambagh Palace", "rating": 5.0, "area": "Bhawani Singh Road", "price_range": (20000, 60000)},
        {"name": "ITC Rajputana", "rating": 5.0, "area": "Palace Road", "price_range": (8000, 22000)},
        {"name": "Fairmont Jaipur", "rating": 5.0, "area": "Kukas", "price_range": (10000, 28000)},
        {"name": "Novotel Jaipur Convention Centre", "rating": 4.0, "area": "Kukas", "price_range": (5000, 12000)},
        {"name": "Lemon Tree Hotel Jaipur", "rating": 4.0, "area": "Malviya Nagar", "price_range": (3500, 8000)},
    ],
    "CCU": [
        {"name": "ITC Royal Bengal", "rating": 5.0, "area": "New Town", "price_range": (9000, 25000)},
        {"name": "The Oberoi Grand", "rating": 5.0, "area": "Jawaharlal Nehru Road", "price_range": (10000, 28000)},
        {"name": "Taj Bengal", "rating": 5.0, "area": "Alipore", "price_range": (8000, 22000)},
        {"name": "Novotel Kolkata Hotel & Residences", "rating": 4.0, "area": "New Town", "price_range": (5000, 12000)},
        {"name": "Ibis Kolkata Rajarhat", "rating": 3.5, "area": "Rajarhat", "price_range": (3000, 6000)},
    ],
    "COK": [
        {"name": "Taj Malabar Resort & Spa", "rating": 5.0, "area": "Willingdon Island", "price_range": (8000, 22000)},
        {"name": "Le Meridien Kochi", "rating": 5.0, "area": "Maradu", "price_range": (7000, 18000)},
        {"name": "Novotel Kochi Infopark", "rating": 4.0, "area": "Infopark", "price_range": (5000, 11000)},
        {"name": "Lemon Tree Hotel Kochi", "rating": 4.0, "area": "Edapally", "price_range": (3500, 7500)},
    ],
    "AMD": [
        {"name": "Hyatt Regency Ahmedabad", "rating": 5.0, "area": "Ashram Road", "price_range": (7000, 18000)},
        {"name": "Courtyard by Marriott Ahmedabad", "rating": 4.0, "area": "SG Highway", "price_range": (5000, 12000)},
        {"name": "Novotel Ahmedabad", "rating": 4.0, "area": "SG Highway", "price_range": (4500, 10000)},
        {"name": "Lemon Tree Hotel Ahmedabad", "rating": 4.0, "area": "Prahlad Nagar", "price_range": (3500, 7500)},
    ],
    "LKO": [
        {"name": "Renaissance Lucknow Hotel", "rating": 5.0, "area": "Gomti Nagar", "price_range": (6000, 16000)},
        {"name": "Taj Hotel & Convention Centre Lucknow", "rating": 5.0, "area": "Vipin Khand", "price_range": (7000, 18000)},
        {"name": "Lemon Tree Hotel Lucknow", "rating": 4.0, "area": "Sushant Golf City", "price_range": (3500, 7500)},
        {"name": "Ibis Lucknow", "rating": 3.5, "area": "Gomti Nagar", "price_range": (2800, 5500)},
    ],
}

PG_DATA = {
    "BOM": [
        {"name": "Stanza Living - Andheri West", "type": "Managed PG", "rent_monthly": 18000, "area": "Andheri West", "platform": "Stanza Living", "amenities": ["WiFi", "AC", "Meals", "Laundry"], "contact": "+91-1800-102-8282"},
        {"name": "NestAway Corporate Suite", "type": "Serviced Apartment", "rent_monthly": 35000, "area": "BKC", "platform": "NestAway", "amenities": ["WiFi", "AC", "Fully Furnished", "Housekeeping"], "contact": "+91-80-46110000"},
        {"name": "OYO Life - Powai", "type": "Managed PG", "rent_monthly": 15000, "area": "Powai", "platform": "OYO Life", "amenities": ["WiFi", "AC", "Meals"], "contact": "+91-9313931393"},
        {"name": "Colive Executive - Worli", "type": "Coliving", "rent_monthly": 25000, "area": "Worli", "platform": "Colive", "amenities": ["WiFi", "Gym", "Meals", "Events"], "contact": "+91-7338300300"},
    ],
    "DEL": [
        {"name": "Stanza Living - Connaught Place", "type": "Managed PG", "rent_monthly": 20000, "area": "Connaught Place", "platform": "Stanza Living", "amenities": ["WiFi", "AC", "Meals", "Laundry"], "contact": "+91-1800-102-8282"},
        {"name": "NestAway Serviced Flat", "type": "Serviced Apartment", "rent_monthly": 40000, "area": "Gurgaon", "platform": "NestAway", "amenities": ["WiFi", "AC", "Fully Furnished"], "contact": "+91-80-46110000"},
        {"name": "OYO Life - Cyber City", "type": "Managed PG", "rent_monthly": 18000, "area": "Sector 14 Gurugram", "platform": "OYO Life", "amenities": ["WiFi", "AC", "Meals"], "contact": "+91-9313931393"},
    ],
    "BLR": [
        {"name": "Stanza Living - Koramangala", "type": "Managed PG", "rent_monthly": 15000, "area": "Koramangala", "platform": "Stanza Living", "amenities": ["WiFi", "AC", "Meals"], "contact": "+91-1800-102-8282"},
        {"name": "CoHo Whitefield", "type": "Coliving", "rent_monthly": 18000, "area": "Whitefield", "platform": "CoHo", "amenities": ["WiFi", "Gym", "Community Kitchen"], "contact": "+91-7406000600"},
        {"name": "NestAway - Indiranagar", "type": "Serviced Apartment", "rent_monthly": 32000, "area": "Indiranagar", "platform": "NestAway", "amenities": ["WiFi", "Fully Furnished", "AC"], "contact": "+91-80-46110000"},
        {"name": "OYO Life - Electronic City", "type": "Managed PG", "rent_monthly": 12000, "area": "Electronic City", "platform": "OYO Life", "amenities": ["WiFi", "Meals"], "contact": "+91-9313931393"},
    ],
    "HYD": [
        {"name": "Stanza Living - HITEC City", "type": "Managed PG", "rent_monthly": 14000, "area": "HITEC City", "platform": "Stanza Living", "amenities": ["WiFi", "AC", "Meals"], "contact": "+91-1800-102-8282"},
        {"name": "NestAway Gachibowli", "type": "Serviced Apartment", "rent_monthly": 28000, "area": "Gachibowli", "platform": "NestAway", "amenities": ["WiFi", "Fully Furnished", "AC"], "contact": "+91-80-46110000"},
    ],
    "PNQ": [
        {"name": "Stanza Living - Hinjewadi", "type": "Managed PG", "rent_monthly": 13000, "area": "Hinjewadi Phase 1", "platform": "Stanza Living", "amenities": ["WiFi", "AC", "Meals", "Laundry"], "contact": "+91-1800-102-8282"},
        {"name": "NestAway Koregaon Park", "type": "Serviced Apartment", "rent_monthly": 30000, "area": "Koregaon Park", "platform": "NestAway", "amenities": ["WiFi", "AC", "Fully Furnished", "Housekeeping"], "contact": "+91-80-46110000"},
        {"name": "OYO Life - Baner", "type": "Managed PG", "rent_monthly": 11000, "area": "Baner", "platform": "OYO Life", "amenities": ["WiFi", "AC", "Meals"], "contact": "+91-9313931393"},
        {"name": "CoHo Wakad", "type": "Coliving", "rent_monthly": 16000, "area": "Wakad", "platform": "CoHo", "amenities": ["WiFi", "Gym", "Community Kitchen", "Events"], "contact": "+91-7406000600"},
    ],
    "JAI": [
        {"name": "Stanza Living - Malviya Nagar", "type": "Managed PG", "rent_monthly": 12000, "area": "Malviya Nagar", "platform": "Stanza Living", "amenities": ["WiFi", "AC", "Meals"], "contact": "+91-1800-102-8282"},
        {"name": "OYO Life - C-Scheme", "type": "Managed PG", "rent_monthly": 10000, "area": "C-Scheme", "platform": "OYO Life", "amenities": ["WiFi", "AC", "Meals"], "contact": "+91-9313931393"},
    ],
}


class AmadeusService:
    BASE_URL_TEST = "https://test.api.amadeus.com"
    BASE_URL_PROD = "https://api.amadeus.com"

    def __init__(self):
        self.client_id = os.getenv("AMADEUS_CLIENT_ID")
        self.client_secret = os.getenv("AMADEUS_CLIENT_SECRET")
        self.use_production = os.getenv("AMADEUS_ENV", "test") == "production"
        self.base_url = self.BASE_URL_PROD if self.use_production else self.BASE_URL_TEST
        self.configured = bool(self.client_id and self.client_secret)
        self._token = None
        self._token_expiry = 0
        self._cache = TTLCache(maxsize=50, ttl=300)
        self._city_code_cache = TTLCache(maxsize=300, ttl=86400)

    def _get_token(self) -> str | None:
        if self._token and datetime.now().timestamp() < self._token_expiry:
            return self._token
        try:
            resp = requests.post(
                f"{self.base_url}/v1/security/oauth2/token",
                data={"grant_type": "client_credentials",
                      "client_id": self.client_id,
                      "client_secret": self.client_secret},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._token_expiry = datetime.now().timestamp() + data.get("expires_in", 1799) - 60
            return self._token
        except Exception as e:
            logger.warning("[Amadeus] Token error: %s", e)
            return None

    def _headers(self) -> dict:
        token = self._get_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def get_airport_code(self, city_name: str) -> str:
        """Map city name to IATA code with local lookup + live Amadeus resolution."""
        normalized = (city_name or "").strip().lower()
        if not normalized:
            return ""

        cached = self._city_code_cache.get(normalized)
        if cached:
            return cached

        if normalized in CITY_AIRPORT_CODES:
            code = CITY_AIRPORT_CODES[normalized]
            self._city_code_cache[normalized] = code
            return code

        # Try comma-formatted city labels e.g. "Paris, France"
        city_key = normalized.split(",")[0].strip()
        if city_key in CITY_AIRPORT_CODES:
            code = CITY_AIRPORT_CODES[city_key]
            self._city_code_cache[normalized] = code
            return code

        code = self._resolve_city_code_live(city_key) if self.configured else None
        if code:
            self._city_code_cache[normalized] = code
            return code

        fallback = city_key.upper()[:3]
        self._city_code_cache[normalized] = fallback
        return fallback

    def _resolve_city_code_live(self, city_name: str) -> str | None:
        """Resolve a city/airport code from Amadeus locations endpoint."""
        headers = self._headers()
        if not headers:
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/v1/reference-data/locations",
                headers=headers,
                params={
                    "keyword": city_name,
                    "subType": "CITY,AIRPORT",
                    "view": "LIGHT",
                    "page[limit]": 5,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            for item in resp.json().get("data", []):
                iata = (
                    item.get("iataCode")
                    or item.get("address", {}).get("cityCode")
                    or item.get("address", {}).get("countryCode")
                )
                if iata and len(iata) == 3:
                    return iata.upper()
        except Exception as e:
            logger.warning("[Amadeus] City code resolve error for %s: %s", city_name, e)
        return None

    def search_flights(self, origin_code: str, dest_code: str, departure_date: str,
                       adults: int = 1, travel_class: str = "ECONOMY", max_results: int = 10) -> dict:
        """Search live flight offers."""
        cache_key = f"flights_{origin_code}_{dest_code}_{departure_date}_{adults}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self.configured:
            result = self._mock_flights(origin_code, dest_code, departure_date, adults)
            self._cache[cache_key] = result
            return result

        try:
            resp = requests.get(
                f"{self.base_url}/v2/shopping/flight-offers",
                headers=self._headers(),
                params={
                    "originLocationCode": origin_code,
                    "destinationLocationCode": dest_code,
                    "departureDate": departure_date,
                    "adults": adults,
                    "travelClass": travel_class,
                    "max": max_results,
                    "currencyCode": "INR",
                },
                timeout=15
            )
            if resp.status_code == 200:
                result = self._parse_flights(resp.json())
                self._cache[cache_key] = result
                return result
            logger.warning("[Amadeus] Flight search HTTP %s", resp.status_code)
        except Exception as e:
            logger.warning("[Amadeus] Flight search error: %s", e)

        return self._mock_flights(origin_code, dest_code, departure_date, adults)

    def search_hotels(self, city_code: str, check_in: str, check_out: str,
                      adults: int = 1, budget_max: int = None) -> list:
        """Search live hotel availability."""
        cache_key = f"hotels_{city_code}_{check_in}_{check_out}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self.configured:
            result = self._mock_hotels(city_code, budget_max)
            self._cache[cache_key] = result
            return result

        try:
            # Step 1: get hotel IDs by city
            r1 = requests.get(
                f"{self.base_url}/v1/reference-data/locations/hotels/by-city",
                headers=self._headers(),
                params={"cityCode": city_code, "radius": 5, "radiusUnit": "KM",
                        "ratings": "3,4,5", "hotelSource": "ALL"},
                timeout=15
            )
            if r1.status_code != 200:
                return self._mock_hotels(city_code, budget_max)

            hotel_ids = [h["hotelId"] for h in r1.json().get("data", [])[:20]]
            if not hotel_ids:
                return self._mock_hotels(city_code, budget_max)

            # Step 2: get pricing
            r2 = requests.get(
                f"{self.base_url}/v3/shopping/hotel-offers",
                headers=self._headers(),
                params={"hotelIds": ",".join(hotel_ids), "adults": adults,
                        "checkInDate": check_in, "checkOutDate": check_out,
                        "currency": "INR", "bestRateOnly": "true"},
                timeout=15
            )
            if r2.status_code == 200:
                result = self._parse_hotels(r2.json(), budget_max)
                self._cache[cache_key] = result
                return result
        except Exception as e:
            logger.warning("[Amadeus] Hotel search error: %s", e)

        return self._mock_hotels(city_code, budget_max)

    def search_pg_options(self, city_code: str, duration_days: int, budget_monthly: int = None) -> list:
        """Return PG / serviced apartment options for extended stays."""
        options = PG_DATA.get(city_code, [])
        result = []
        for pg in options:
            rent = pg["rent_monthly"]
            if budget_monthly and rent > budget_monthly:
                continue
            # Calculate weekly and daily equivalents
            pg_item = dict(pg)
            pg_item["rent_weekly"] = round(rent / 4)
            pg_item["rent_daily"] = round(rent / 30)
            pg_item["cost_for_stay"] = round((rent / 30) * duration_days)
            pg_item["source"] = "curated"
            result.append(pg_item)
        return result

    def get_price_analysis(self, origin: str, dest: str, date: str) -> dict:
        """Simple price level analysis for a route."""
        if not self.configured:
            return {"level": "normal", "insight": "Configure Amadeus API for price analysis"}
        try:
            resp = requests.get(
                f"{self.base_url}/v1/analytics/itinerary-price-metrics",
                headers=self._headers(),
                params={"originIataCode": origin, "destinationIataCode": dest,
                        "departureDate": date, "currencyCode": "INR"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [{}])[0]
                return {"level": data.get("priceMetrics", [{}])[0].get("amount", "N/A"),
                        "source": "amadeus_live"}
        except Exception as e:
            logger.warning("[Amadeus] Price analysis error: %s", e)
        return {"level": "normal", "source": "fallback"}

    # ── Parsers ────────────────────────────────────────────────────

    def _parse_flights(self, data: dict) -> dict:
        flights = []
        dictionaries = data.get("dictionaries", {})
        carriers = dictionaries.get("carriers", {})

        for offer in data.get("data", [])[:10]:
            itinerary = offer.get("itineraries", [{}])[0]
            segments = itinerary.get("segments", [{}])
            first_seg = segments[0] if segments else {}
            last_seg = segments[-1] if segments else {}
            price = offer.get("price", {})
            carrier_code = first_seg.get("carrierCode", "")
            carrier_name = carriers.get(carrier_code, carrier_code)

            # Find booking URL
            booking_url = next((a["url"] for a in AIRLINES if a["code"] == carrier_code),
                               "https://www.makemytrip.com/flights/")

            flights.append({
                "id": offer.get("id"),
                "airline": carrier_name,
                "airline_code": carrier_code,
                "flight_number": f"{carrier_code}{first_seg.get('number', '')}",
                "origin": first_seg.get("departure", {}).get("iataCode", ""),
                "destination": last_seg.get("arrival", {}).get("iataCode", ""),
                "departure": first_seg.get("departure", {}).get("at", ""),
                "arrival": last_seg.get("arrival", {}).get("at", ""),
                "duration": itinerary.get("duration", ""),
                "stops": len(segments) - 1,
                "price_inr": float(price.get("grandTotal", 0)),
                "price": float(price.get("grandTotal", 0)),
                "currency": price.get("currency", "INR"),
                "cabin": offer.get("travelerPricings", [{}])[0]
                              .get("fareDetailsBySegment", [{}])[0]
                              .get("cabin", "ECONOMY"),
                "booking_link": booking_url,
                "source": "amadeus_live",
            })
        return {"success": True, "flights": flights, "source": "amadeus_live",
                "count": len(flights)}

    def _parse_hotels(self, data: dict, budget_max: int = None) -> list:
        hotels = []
        for item in data.get("data", [])[:15]:
            hotel = item.get("hotel", {})
            offers = item.get("offers", [{}])
            offer = offers[0] if offers else {}
            price = offer.get("price", {})
            price_per_night = float(price.get("total", 0))

            if budget_max and price_per_night > budget_max:
                continue

            hotels.append({
                "id": hotel.get("hotelId"),
                "name": hotel.get("name", "Hotel"),
                "rating": float(hotel.get("rating", 3)),
                "latitude": hotel.get("latitude"),
                "longitude": hotel.get("longitude"),
                "address": ", ".join(hotel.get("address", {}).get("lines", [""])),
                "city": hotel.get("address", {}).get("cityName", ""),
                "area": hotel.get("address", {}).get("cityName", ""),
                "price_per_night": price_per_night,
                "price": price_per_night,
                "currency": price.get("currency", "INR"),
                "check_in": offer.get("checkInDate", ""),
                "check_out": offer.get("checkOutDate", ""),
                "room_type": offer.get("room", {}).get("typeEstimated", {}).get("category", "Standard"),
                "amenities": hotel.get("amenities", [])[:6],
                "booking_link": f"https://www.booking.com/searchresults.html?ss={hotel.get('name','')}",
                "source": "amadeus_live",
            })
        return hotels

    # ── Fallbacks ──────────────────────────────────────────────────

    def _mock_flights(self, origin: str, dest: str, date: str, adults: int) -> dict:
        """Curated mock flight data with real airline info."""
        flights = []
        for i, carrier in enumerate(AIRLINES[:4]):
            base = random.randint(3200, 11000)
            dep_hour = 6 + i * 3
            flights.append({
                "airline": carrier["name"],
                "airline_code": carrier["code"],
                "flight_number": f"{carrier['code']}{random.randint(101, 999)}",
                "origin": origin,
                "destination": dest,
                "departure": f"{date}T{dep_hour:02d}:00:00",
                "arrival": f"{date}T{dep_hour + 2:02d}:30:00",
                "duration": "PT2H30M",
                "stops": 0 if i < 3 else 1,
                "price_inr": base * adults,
                "price": base * adults,
                "currency": "INR",
                "cabin": "ECONOMY",
                "booking_link": carrier["url"],
                "source": "fallback",
            })
        return {"success": True, "flights": flights, "source": "fallback",
                "note": "Set AMADEUS_CLIENT_ID + AMADEUS_CLIENT_SECRET for live fares"}

    def _mock_hotels(self, city_code: str, budget_max: int = None) -> list:
        """Curated mock hotel data with real hotel names."""
        city_hotels = HOTEL_DATA.get(city_code, [
            {"name": f"Lemon Tree Hotel {city_code}", "rating": 4.0, "area": "City Centre", "price_range": (3500, 8000)},
            {"name": f"Ibis {city_code}", "rating": 3.5, "area": "Business District", "price_range": (2500, 5500)},
            {"name": f"Courtyard by Marriott {city_code}", "rating": 4.5, "area": "Commercial Zone", "price_range": (5000, 12000)},
            {"name": f"Novotel {city_code}", "rating": 4.0, "area": "City Centre", "price_range": (4500, 10000)},
        ])
        result = []
        for h in city_hotels:
            price = random.randint(h["price_range"][0], h["price_range"][1])
            if budget_max and price > budget_max:
                continue
            result.append({
                "name": h["name"],
                "rating": h["rating"],
                "area": h.get("area", ""),
                "price_per_night": price,
                "price": price,
                "currency": "INR",
                "amenities": ["WiFi", "Restaurant", "AC", "Room Service"],
                "source": "fallback",
            })
        return result


amadeus = AmadeusService()
