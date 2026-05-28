"""
OTIS Voice Dispatcher
Detects action intents in voice commands and routes to TravelSync agents.

Returns a result dict on match, or None when no intent matches
so the caller falls through to Gemini for conversational replies.

Supported intents:
    hotel_search      — hotel_agent.search_hotels()
    transport_search  — travel_mode_agent.recommend_travel_mode()
    weather           — weather_agent.get_travel_weather()
    currency          — currency_service.currency.convert()
    plan_trip         — quick voice acknowledgement + directs to Planner tab
    sos               — log DB + notify managers
"""
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Known Indian and international cities for fast matching ───────────────────
_CITIES = {
    "mumbai", "delhi", "new delhi", "bangalore", "bengaluru", "hyderabad",
    "chennai", "kolkata", "pune", "ahmedabad", "jaipur", "lucknow", "surat",
    "kanpur", "nagpur", "indore", "thane", "bhopal", "visakhapatnam", "vizag",
    "patna", "vadodara", "ghaziabad", "ludhiana", "agra", "nashik", "faridabad",
    "meerut", "rajkot", "varanasi", "srinagar", "chandigarh", "guwahati",
    "noida", "coimbatore", "ranchi", "kochi", "cochin", "trivandrum",
    "thiruvananthapuram", "madurai", "amritsar", "navi mumbai", "goa", "panaji",
    "manali", "shimla", "dehradun", "haridwar", "rishikesh", "mysore", "mysuru",
    "ooty", "kodaikanal", "gulmarg", "leh", "ladakh", "darjeeling",
    # International
    "dubai", "abu dhabi", "singapore", "london", "new york", "bangkok",
    "kuala lumpur", "tokyo", "hong kong", "sydney", "paris", "berlin",
    "toronto", "los angeles", "chicago", "san francisco", "seattle", "boston",
    "amsterdam", "rome", "barcelona", "milan", "zurich", "vienna", "brussels",
    "bali", "jakarta", "manila", "riyadh", "doha", "kuwait city", "muscat",
    "colombo", "kathmandu", "dhaka", "karachi", "islamabad",
}

_STOP_WORDS = {
    "the", "a", "an", "my", "your", "our", "this", "that", "please", "now",
    "today", "tomorrow", "next", "last", "some", "any", "what", "where",
    "when", "how", "which", "who", "me", "us", "you", "it", "is", "are",
}


def _extract_cities_in_order(text: str) -> list[tuple[int, str]]:
    """Return unique city matches ordered by their first appearance in the text."""
    text_lower = text.lower()
    matches = []
    seen = set()

    for city in sorted(_CITIES, key=len, reverse=True):
        idx = text_lower.find(city)
        if idx == -1:
            continue
        normalized = city.title()
        if normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        matches.append((idx, normalized))

    matches.sort(key=lambda item: item[0])
    return matches

# ── Parameter extraction ──────────────────────────────────────────────────────

def _extract_city(text: str) -> str:
    """Extract the most specific city name from command text."""
    text_lower = text.lower()

    # Exact match against known cities (longest match wins)
    matched = sorted(
        [c for c in _CITIES if c in text_lower],
        key=len, reverse=True
    )
    if matched:
        return matched[0].title()

    # Regex fallback: capitalised words after location prepositions
    for kw in ("in ", "to ", "at ", "near ", "for "):
        m = re.search(
            rf'\b{re.escape(kw)}([A-Za-z][a-z]+(?:(?:\s+|-)[A-Za-z][a-z]+){{0,2}})',
            text, re.IGNORECASE,
        )
        if m:
            city = m.group(1).strip()
            if city.lower() not in _STOP_WORDS and len(city) > 2:
                return city.title()
    return ""


def _extract_origin_dest(text: str) -> tuple:
    """Extract (origin, destination) from 'from X to Y' patterns."""
    m = re.search(
        r'\bfrom\s+([A-Za-z][a-z]+(?:\s+[A-Za-z][a-z]+){0,2})'
        r'\s+to\s+([A-Za-z][a-z]+(?:\s+[A-Za-z][a-z]+){0,2})',
        text, re.IGNORECASE,
    )
    if m:
        origin = _extract_city(m.group(1)) or m.group(1).title()
        dest = _extract_city(m.group(2)) or m.group(2).title()
        return origin, dest

    ordered_cities = _extract_cities_in_order(text)
    if len(ordered_cities) >= 2:
        return ordered_cities[0][1], ordered_cities[1][1]
    if ordered_cities:
        return "", ordered_cities[0][1]
    return "", _extract_city(text)


def _extract_duration(text: str, default: int = 3) -> int:
    m = re.search(r'(\d+)\s*(?:night|nights|day|days)', text, re.IGNORECASE)
    return int(m.group(1)) if m else default


def _detect_budget(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("budget", "cheap", "affordable", "economy", "low cost")):
        return "budget"
    if any(w in t for w in ("luxury", "premium", "five star", "5 star", "high end", "expensive")):
        return "luxury"
    return "moderate"


# ── Intent detection patterns ─────────────────────────────────────────────────

_HOTEL_KEYWORDS = (
    r'\b(find|search|show|get|look for|need|want|book)\b.{0,30}'
    r'\b(hotel|hotels|accommodation|stay|room|rooms|lodge|lodging|resort|property|pg|hostel)\b',
    r'\b(hotel|accommodation|resort|lodge|hostel)\b.{0,30}\b(in|at|near|for)\b',
    r'\bwhere\b.{0,20}\b(stay|sleep|lodge)\b',
    r'\b(pg|paying guest|serviced apartment|coliving|co-living)\b.{0,30}\b(in|at|near)\b',
)

_TRANSPORT_KEYWORDS = (
    r'\b(find|search|show|book|get|check)\b.{0,30}'
    r'\b(flight|flights|train|trains|bus|buses|ticket|tickets)\b',
    r'\b(flight|flights|train|trains|bus|buses)\b.{0,30}\b(from|to)\b',
    r'\bhow\b.{0,30}\b(travel|get|reach|go)\b.{0,30}\b(to|from)\b',
    r'\b(travel mode|travel options|transport options|airfare|air fare|plane ticket)\b',
    r'\b(irctc|redbus|indigo|spicejet|air india|vistara)\b',
)

_WEATHER_KEYWORDS = (
    r'\b(weather|forecast|temperature|climate|rain|rainfall|humidity|sunny|cloudy)\b',
    r'\b(what.s|how.s|is it|will it)\b.{0,20}'
    r'\b(weather|raining|hot|cold|sunny|warm|humid|snowing)\b',
    r'\b(pack|packing|bring|carry)\b.{0,30}\b(weather|rain|umbrella|jacket|clothes)\b',
)

_CURRENCY_KEYWORDS = (
    r'\b(convert|conversion|exchange|how much|calculate)\b.{0,50}'
    r'\b(usd|inr|eur|gbp|aed|sar|jpy|cny|sgd|thb|myr|cad|aud|chf)\b',
    r'\b\d[\d,]*\.?\d*\s*(usd|inr|eur|gbp|aed|sar|jpy|cny|sgd)\b.{0,30}\b(to|in|into)\b',
    r'\b(currency|forex|exchange rate)\b',
    r'\b(rupee|dollar|euro|pound|dirham|riyal|yen|yuan|ringgit)\b.{0,30}\b(rate|conversion|convert|exchange)\b',
)

_PLAN_KEYWORDS = (
    r'\b(plan|planning|arrange|organise|organize|set up|help me plan)\b.{0,30}'
    r'\b(trip|travel|journey|visit|tour|itinerary)\b',
    r'\b(create|make|build|draft)\b.{0,20}\b(itinerary|travel plan|trip plan)\b',
    r'\bi\s+(need to|want to|have to|am going to|am|will be)\b.{0,30}'
    r'\b(travel|go|visit|fly)\b.{0,15}\bto\b',
)

_SOS_KEYWORDS = (
    r'\b(sos|mayday)\b',
    r'\b(emergency|urgent help|help me now|i need help immediately|in danger|send alert)\b',
    r'\b(send|trigger|raise)\b.{0,20}\b(sos|emergency|alert|distress)\b',
)


def _any_match(text: str, patterns: tuple) -> bool:
    t = text.lower()
    return any(re.search(p, t, re.IGNORECASE) for p in patterns)


def detect_intent(command: str) -> str | None:
    """Classify a voice command into an action intent, or None for chat/DB queries."""
    if _any_match(command, _SOS_KEYWORDS):
        return "sos"
    if _any_match(command, _HOTEL_KEYWORDS):
        return "hotel_search"
    if _any_match(command, _TRANSPORT_KEYWORDS):
        return "transport_search"
    if _any_match(command, _WEATHER_KEYWORDS):
        return "weather"
    if _any_match(command, _CURRENCY_KEYWORDS):
        return "currency"
    if _any_match(command, _PLAN_KEYWORDS):
        return "plan_trip"
    return None


# ── Voice response formatters ─────────────────────────────────────────────────

def _fmt_hotels(result: dict, destination: str) -> str:
    hotels = result.get("hotels", [])
    if not hotels:
        return (
            f"I couldn't find hotels in {destination or 'that location'} right now. "
            "Check the Accommodation tab in the app for full options."
        )
    top = hotels[:3]
    parts = [f"Found {len(hotels)} hotel{'s' if len(hotels) != 1 else ''} in {destination}."]
    for h in top:
        name = h.get("name", "")
        price = h.get("price_per_night") or h.get("price_range", "")
        rating = h.get("rating", "")
        detail = name
        if rating:
            detail += f", rated {rating}"
        if price:
            detail += (
                f", ₹{int(price):,} per night"
                if isinstance(price, (int, float))
                else f", ₹{price} per night"
            )
        parts.append(detail)
    if len(hotels) > 3:
        parts.append(f"Plus {len(hotels) - 3} more in the app.")
    return ". ".join(parts) + "."


def _fmt_transport(result: dict, origin: str, dest: str) -> str:
    mode = result.get("recommended_mode", "")
    modes = result.get("modes", {})
    parts = []

    if mode:
        parts.append(f"Recommended: {mode}.")

    flights = modes.get("flight", {}).get("options", [])
    if flights:
        f = flights[0]
        carrier = f.get("airline") or f.get("carrier", "")
        price = f.get("price") or f.get("price_inr", "")
        dep = f.get("departure_time", "")
        bits = []
        if carrier:
            bits.append(carrier)
        if dep:
            bits.append(f"departs {dep}")
        if price:
            bits.append(
                f"₹{int(price):,}"
                if isinstance(price, (int, float))
                else f"₹{price}"
            )
        if bits:
            parts.append(f"Top flight: {', '.join(bits)}.")
        if len(flights) > 1:
            parts.append(f"{len(flights) - 1} more flight option{'s' if len(flights) > 2 else ''} in the app.")
    elif mode == "flight":
        parts.append("Flight is the fastest option. Check Google Flights for live fares.")

    train = modes.get("train", {})
    if train.get("available"):
        train_line = "Train option available."
        if train.get("popular_trains"):
            train_line += f" Top train: {train['popular_trains'][0]}."
        if train.get("estimated_duration"):
            train_line += f" Estimated duration {train['estimated_duration']}."
        if train.get("platforms"):
            train_line += f" Check {train['platforms'][0].get('name', 'IRCTC')} for live seats."
        parts.append(train_line)

    bus = modes.get("bus", {})
    if bus.get("available"):
        bus_line = "Bus option available."
        if bus.get("estimated_duration"):
            bus_line += f" Estimated duration {bus['estimated_duration']}."
        if bus.get("platforms"):
            primary_platform = bus["platforms"][0].get("name", "RedBus")
            bus_line += f" Check {primary_platform} for live tickets."
        parts.append(bus_line)

    cab = modes.get("cab", {})
    if cab.get("available"):
        cab_line = "Cab option available."
        if cab.get("estimated_duration"):
            cab_line += f" Estimated duration {cab['estimated_duration']}."
        if cab.get("estimated_fare"):
            cab_line += f" Estimated fare {cab['estimated_fare']}."
        if cab.get("platforms"):
            cab_line += f" Book on {cab['platforms'][0].get('name', 'Uber')}."
        parts.append(cab_line)

    if not parts:
        route = f"from {origin} to {dest}" if origin and dest else dest or "that route"
        return f"I found travel options {route}. Open the Planner tab for full details."

    return " ".join(parts)


def _fmt_weather(result: dict, city: str) -> str:
    city_label = city or result.get("city", "that city")
    current = result.get("current") or {}
    temp = current.get("temp") or current.get("temperature")
    desc = current.get("description") or current.get("condition", "")
    rain_prob = current.get("rain_probability", 0)

    if not temp and not desc:
        # Try first forecast entry
        forecasts = result.get("forecast", [])
        if forecasts:
            f = forecasts[0]
            temp = f.get("temp_max") or f.get("temp")
            desc = f.get("description", "")

    if not temp and not desc:
        return f"I couldn't get weather data for {city_label} right now."

    parts = [f"Weather in {city_label}:"]
    if temp is not None:
        parts.append(f"{temp}°C")
    if desc:
        parts.append(desc)
    if rain_prob and int(rain_prob) > 50:
        parts.append(f"Rain likely ({rain_prob}% chance) — carry an umbrella.")

    return " ".join(parts) + "."


def _fmt_currency(result: dict) -> str:
    if "error" in result:
        return "I couldn't complete that conversion. Please check the currency codes."
    amount = result.get("amount", 0)
    from_cur = result.get("from", "")
    to_cur = result.get("to", "")
    converted = result.get("converted")
    rate = result.get("rate")
    if converted is None:
        return "Currency conversion is unavailable right now."
    return (
        f"{amount:,.2f} {from_cur} equals {converted:,.2f} {to_cur}. "
        f"Rate: 1 {from_cur} = {rate} {to_cur}."
    )


# ── Intent handlers ───────────────────────────────────────────────────────────

def _handle_hotel_search(user: dict, command: str) -> dict:
    try:
        from agents.hotel_agent import search_hotels

        city = _extract_city(command)
        if not city:
            return _ask("Which city are you looking for hotels in?", "hotel_search")

        result = search_hotels({
            "destination": city,
            "duration_days": _extract_duration(command),
            "budget": _detect_budget(command),
            "num_travelers": 1,
        })
        return {
            "response_text": _fmt_hotels(result, city),
            "query_type": "hotel_search",
            "query_data": {"destination": city, "hotels": result.get("hotels", [])[:5]},
            "data_source": result.get("source", "hotel_agent"),
        }
    except Exception as e:
        logger.warning("[OTIS Dispatcher] Hotel search error: %s", e)
        return _error("I had trouble searching hotels. Try the Accommodation tab.", "hotel_search")


def _handle_transport_search(user: dict, command: str) -> dict:
    try:
        from agents.travel_mode_agent import recommend_travel_mode

        origin, dest = _extract_origin_dest(command)
        if not dest:
            return _ask(
                "Which route? Say something like 'flights from Mumbai to Delhi'.",
                "transport_search",
            )

        cmd_lower = command.lower()
        preferred = ""
        if any(w in cmd_lower for w in ("flight", "fly", "plane", "air")):
            preferred = "flight"
        elif "train" in cmd_lower:
            preferred = "train"
        elif "bus" in cmd_lower:
            preferred = "bus"
        elif any(w in cmd_lower for w in ("cab", "taxi", "car", "uber", "ola")):
            preferred = "cab"

        result = recommend_travel_mode({
            "destination": dest,
            "origin": origin or "",
            "num_travelers": 1,
            "purpose": "business",
            "preferred_mode": preferred,
            "travel_dates": "",
            "travelers": [{"origin": origin or ""}],
        },
            include_live_flights=(preferred == "flight"),
            include_ai_tip=False,
        )
        return {
            "response_text": _fmt_transport(result, origin, dest),
            "query_type": "transport_search",
            "query_data": {
                "origin": origin,
                "destination": dest,
                "recommended_mode": result.get("recommended_mode"),
            },
            "data_source": result.get("data_source", "travel_mode_agent"),
        }
    except Exception as e:
        logger.warning("[OTIS Dispatcher] Transport search error: %s", e)
        return _error("I had trouble finding transport options. Try the Planner tab.", "transport_search")


def _handle_weather(user: dict, command: str) -> dict:
    try:
        from agents.weather_agent import get_travel_weather

        city = _extract_city(command)
        if not city:
            return _ask("Which city's weather would you like?", "weather")

        result = get_travel_weather(city)
        return {
            "response_text": _fmt_weather(result, city),
            "query_type": "weather",
            "query_data": {"city": city, "temp": result.get("current", {}).get("temp")},
            "data_source": result.get("source", "weather_agent"),
        }
    except Exception as e:
        logger.warning("[OTIS Dispatcher] Weather error: %s", e)
        return _error("Weather information is unavailable right now.", "weather")


def _handle_currency(user: dict, command: str) -> dict:
    try:
        from services.currency_service import currency

        # Currency code patterns (ISO 4217)
        _CODE = r'(?:usd|inr|eur|gbp|aed|sar|jpy|cny|sgd|thb|myr|cad|aud|chf|nzd|krw|hkd)'

        m = re.search(
            rf'(\d[\d,]*\.?\d*)\s*({_CODE})\s+(?:to|in|into)\s+({_CODE})',
            command, re.IGNORECASE,
        )

        if not m:
            # Replace natural-language currency words with ISO codes
            word_map = {
                r'\brupee[s]?\b': "INR", r'\bdollar[s]?\b': "USD",
                r'\beuro[s]?\b': "EUR", r'\bpound[s]?\b': "GBP",
                r'\bdirham[s]?\b': "AED", r'\briyal[s]?\b': "SAR",
                r'\byen\b': "JPY", r'\byuan\b': "CNY", r'\bringgit\b': "MYR",
                r'\bsing(?:apore)?\s*dollar[s]?\b': "SGD",
                r'\bbaht\b': "THB",
            }
            normalized = command
            for pattern, code in word_map.items():
                normalized = re.sub(pattern, code, normalized, flags=re.IGNORECASE)

            m = re.search(
                rf'(\d[\d,]*\.?\d*)\s*({_CODE})\s+(?:to|in|into)\s+({_CODE})',
                normalized, re.IGNORECASE,
            )

        if not m:
            # Destination-based: "currency for Dubai trip"
            dest = _extract_city(command)
            if dest:
                travel_data = currency.get_travel_currencies(dest)
                local = travel_data.get("local_currency", {})
                rate_info = travel_data.get("rate_from_inr", {})
                if local:
                    code = local.get("code", "")
                    rate = rate_info.get("rate", "")
                    text = f"{dest} uses {local.get('name', code)} ({code})."
                    if rate:
                        text += f" 1 INR = {rate} {code}."
                    return {
                        "response_text": text,
                        "query_type": "currency",
                        "query_data": travel_data,
                        "data_source": travel_data.get("source", "currency_service"),
                    }
            return _ask(
                "How much and between which currencies? Say something like '1000 USD to INR'.",
                "currency",
            )

        amount = float(m.group(1).replace(",", ""))
        from_cur = m.group(2).upper()
        to_cur = m.group(3).upper()
        result = currency.convert(amount, from_cur, to_cur)
        return {
            "response_text": _fmt_currency(result),
            "query_type": "currency",
            "query_data": result,
            "data_source": result.get("source", "currency_service"),
        }
    except Exception as e:
        logger.warning("[OTIS Dispatcher] Currency error: %s", e)
        return _error("Currency conversion is unavailable right now.", "currency")


def _handle_plan_trip(user: dict, command: str) -> dict:
    """
    Full orchestrator takes 10-20 s — too slow for voice.
    Acknowledge the request and direct the user to the Planner tab.
    """
    dest = _extract_city(command)
    duration = _extract_duration(command)

    if not dest:
        return _ask("Sure! Which city are you planning to travel to?", "plan_trip")

    return {
        "response_text": (
            f"I'll help you plan a {duration}-day trip to {dest}. "
            f"Head to the Planner tab, enter {dest}, and the AI will generate "
            "hotels, flights, weather, and a full itinerary in under 30 seconds."
        ),
        "query_type": "plan_trip",
        "query_data": {"destination": dest, "duration": duration},
        "data_source": "otis_dispatcher",
    }


def _handle_sos(user: dict, command: str) -> dict:
    """Log an SOS event and notify managers."""
    try:
        from database import get_db

        city = _extract_city(command) or "Unknown"

        cmd_lower = command.lower()
        emergency_type = "general"
        if any(w in cmd_lower for w in ("medical", "sick", "injured", "hospital", "accident", "heart")):
            emergency_type = "medical"
        elif any(w in cmd_lower for w in ("fire", "burning", "smoke")):
            emergency_type = "fire"
        elif any(w in cmd_lower for w in ("theft", "robbed", "stolen", "robbery", "mugging")):
            emergency_type = "theft"
        elif any(w in cmd_lower for w in ("security", "threat", "danger", "attack")):
            emergency_type = "security"

        message = re.sub(
            r'\b(sos|mayday|emergency|send alert|send sos|help)\b', '',
            command, flags=re.IGNORECASE,
        ).strip() or "SOS via OTIS voice assistant"

        db = get_db()
        db.execute(
            """INSERT INTO sos_events
               (user_id, destination, location, emergency_type, message, resolved, created_at)
               VALUES (?, ?, ?, ?, ?, 0, ?)""",
            (user["id"], city, city, emergency_type, message, datetime.now()),
        )
        db.commit()
        db.close()

        # Notify managers silently on failure
        try:
            from services.notification_service import notify
            notify(
                user_id=None,
                title=f"SOS Alert — {user.get('name', 'Team member')}",
                message=f"Location: {city}. {message}",
                notification_type="sos_alert",
                broadcast_to_role="manager",
                extra={"user_id": user["id"], "city": city, "emergency_type": emergency_type},
            )
        except Exception:
            pass

        return {
            "response_text": (
                f"SOS alert sent. Your managers have been notified. "
                f"If this is a life-threatening emergency, call 112 immediately."
            ),
            "query_type": "sos",
            "query_data": {"city": city, "emergency_type": emergency_type},
            "data_source": "sos_agent",
        }
    except Exception as e:
        logger.error("[OTIS Dispatcher] SOS error: %s", e)
        return {
            "response_text": "SOS logged. Please also call emergency services on 112 immediately.",
            "query_type": "sos",
            "query_data": {},
            "data_source": "error",
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ask(text: str, query_type: str) -> dict:
    return {"response_text": text, "query_type": query_type, "query_data": {}, "data_source": "otis_dispatcher"}


def _error(text: str, query_type: str) -> dict:
    return {"response_text": text, "query_type": query_type, "query_data": {}, "data_source": "error"}


# ── Main entry point ──────────────────────────────────────────────────────────

_HANDLERS = {
    "hotel_search":     _handle_hotel_search,
    "transport_search": _handle_transport_search,
    "weather":          _handle_weather,
    "currency":         _handle_currency,
    "plan_trip":        _handle_plan_trip,
    "sos":              _handle_sos,
}


def dispatch(user: dict, command: str) -> dict | None:
    """
    Detect action intent and route to the appropriate TravelSync agent.

    Returns a result dict with keys:
        response_text  — voice-ready reply (1-3 short sentences)
        query_type     — intent name
        query_data     — structured data for the frontend
        data_source    — which agent answered

    Returns None when no action intent is detected (caller should use
    the structured-query engine or Gemini for conversational answers).
    """
    intent = detect_intent(command)
    if not intent:
        return None

    logger.info(
        "[OTIS Dispatcher] intent=%s | cmd='%s'",
        intent, command[:70],
    )

    handler = _HANDLERS.get(intent)
    if not handler:
        return None

    return handler(user, command)
