"""
TravelSync Pro — AI Chat Agent
Gemini 2.0 Flash powered travel assistant.
Falls back to pattern matching when Gemini unavailable.
"""
import sys
import os
import re
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gemini_service import gemini
from services.weather_service import weather
from services.currency_service import currency

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are TravelSync Pro, an intelligent corporate travel assistant.
You help with:
- Flight and hotel bookings (Amadeus-powered real-time data)
- Trip planning for business visits across the world
- Expense tracking and receipt verification
- Travel policy compliance checking
- Client meeting scheduling
- Weather updates and packing suggestions
- Currency conversion for international travel
- Team coordination for multi-city and multi-timezone travel

Be concise, professional, and practical.
Prefer factual and actionable responses over generic statements.
If tools or live providers are unavailable, clearly state that and suggest alternatives.
"""


def process_message(message: str, user: dict = None, model=None, context: dict = None) -> dict:
    """
    Process a chat message and return AI response with intent and action cards.
    """
    context = context or {}
    if not message.strip():
        return {"reply": "How can I help you with your travel plans?",
                "intent": "general", "action_cards": []}

    intent = _detect_intent(message)
    entities = _extract_entities(message, context=context)

    # Try Gemini first
    if gemini.is_available:
        user_context = ""
        if user:
            user_context = f"User: {user.get('name', '')} ({user.get('role', 'employee')}). "

        attachment_context = ""
        if context.get("attachment"):
            attachment_context = f" Attachment: {context['attachment']}."

        prompt = f"{user_context}Query: {message}.{attachment_context}"
        reply = gemini.generate(prompt, system_instruction=SYSTEM_PROMPT)

        if reply:
            # Enrich with live data snippets
            reply = _enrich_reply(reply, intent, entities)
            action_cards = _build_action_cards(intent, entities)
            return {
                "reply": reply,
                "intent": intent,
                "entities": entities,
                "action_cards": action_cards,
                "ai_powered": True,
                "model": "gemini-2.0-flash",
            }

    # Pattern-based fallback
    reply = _pattern_reply(message, intent, entities)
    action_cards = _build_action_cards(intent, entities)

    return {
        "reply": reply,
        "intent": intent,
        "entities": entities,
        "action_cards": action_cards,
        "ai_powered": False,
        "note": "Set GEMINI_API_KEY for AI-powered responses",
    }


def _detect_intent(message: str) -> str:
    """Detect user intent from message."""
    msg = message.lower()
    patterns = {
        "plan_trip": r"\b(plan|book|arrange|schedule|trip|travel|visit|go to)\b",
        "search_hotel": r"\b(hotel|stay|accommodation|pg|room|lodge|hostel)\b",
        "search_flight": r"\b(flight|fly|plane|airline|airfare|ticket)\b",
        "weather": r"\b(weather|rain|temperature|forecast|climate)\b",
        "currency": r"\b(currency|convert|exchange|rate|usd|eur|dollar|euro|aed|pound)\b",
        "expense": r"\b(expense|receipt|invoice|bill|reimburse|payment|spent)\b",
        "meeting": r"\b(meeting|client|appointment|schedule|venue|office)\b",
        "emergency": r"\b(emergency|sos|help|accident|ambulance|hospital|police|danger)\b",
        "policy": r"\b(policy|compliance|limit|budget|allowed|permitted|violation)\b",
        "status": r"\b(status|pending|approved|rejected|request|approval)\b",
    }
    for intent, pattern in patterns.items():
        if re.search(pattern, msg):
            return intent
    return "general"


def _extract_entities(message: str, context: dict = None) -> dict:
    """Extract cities, dates, amounts from message."""
    context = context or {}
    default_cities = [
        # India
        "mumbai", "delhi", "bangalore", "bengaluru", "hyderabad", "chennai", "kolkata", "pune",
        "ahmedabad", "jaipur", "surat", "lucknow", "kochi", "goa", "varanasi", "amritsar",
        # Global
        "london", "paris", "berlin", "frankfurt", "amsterdam", "zurich", "madrid", "barcelona",
        "new york", "los angeles", "san francisco", "chicago", "toronto", "vancouver",
        "dubai", "abu dhabi", "doha", "riyadh", "singapore", "bangkok", "tokyo", "osaka",
        "seoul", "beijing", "shanghai", "sydney", "melbourne", "auckland",
    ]
    known_cities = context.get("known_cities", default_cities)
    msg_lower = message.lower()
    found_cities = [c.title() for c in known_cities if c in msg_lower]

    # Amounts
    amount_match = re.search(r"(?:₹|rs\.?\s*|inr\s*|\$|€|£|aed\s*|usd\s*|eur\s*)([0-9,]+(?:\.[0-9]{1,2})?)", msg_lower, re.IGNORECASE)
    amount = float(amount_match.group(1).replace(",", "")) if amount_match else None

    # Date mentions
    date_match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", message)
    date = date_match.group(1) if date_match else None

    # Currency mentions
    currency_codes = re.findall(r"\b(INR|USD|EUR|GBP|AED|SAR|JPY|CAD|AUD|SGD|CHF|CNY)\b", message.upper())
    countries = re.findall(
        r"\b(india|usa|united states|uk|united kingdom|france|germany|japan|uae|singapore|australia|canada)\b",
        msg_lower
    )

    return {
        "cities": found_cities,
        "origin": found_cities[0] if found_cities else None,
        "destination": found_cities[-1] if len(found_cities) > 1 else found_cities[0] if found_cities else None,
        "amount": amount,
        "date": date,
        "currencies": currency_codes,
        "countries": [c.title() for c in countries],
    }


def _enrich_reply(reply: str, intent: str, entities: dict) -> str:
    """Add live data snippets to Gemini reply."""
    destination = entities.get("destination")

    if intent == "weather" and destination:
        try:
            w = weather.get_current(destination)
            weather_snippet = (f"\n\n🌤 **Live Weather in {destination}**: "
                               f"{w.get('temp')}°C, {w.get('description')}, "
                               f"Humidity: {w.get('humidity')}%")
            reply += weather_snippet
        except Exception as e:
            logger.warning("[Chat] Weather enrich failed: %s", e)

    if intent == "currency":
        try:
            rates = currency.get_rates()
            if rates.get("source") == "openexchangerates":
                reply += "\n\n💱 *Live exchange rates from OpenExchangeRates*"
        except Exception as e:
            logger.warning("[Chat] Currency enrich failed: %s", e)

    return reply


def _pattern_reply(message: str, intent: str, entities: dict) -> str:
    """Fallback reply when Gemini is unavailable."""
    destination = entities.get("destination", "your destination")

    replies = {
        "plan_trip": (f"I can help plan your trip to {destination}! "
                       "Head to **Trip Planner** tab and fill in the details. "
                       "I'll search live flights, hotels, and build a complete itinerary."),
        "search_hotel": (f"Looking for accommodation in {destination}? "
                          "Use the **Hotels** tab. For stays over 5 days, "
                          "I'll also show PG and serviced apartment options."),
        "search_flight": (f"I can search live flights to {destination} via Amadeus API. "
                           "Go to **Trip Planner** → select flight mode to see real-time fares."),
        "weather": (f"Let me check the weather for {destination}. "
                    "Configure OPENWEATHER_API_KEY for live forecasts."),
        "expense": ("Add your expense in the **Expenses** tab. "
                    "Upload your receipt image and I'll auto-extract the amount via OCR."),
        "meeting": ("Add client meetings in the **Meetings** tab. "
                    "You can add meetings from any source: email, WhatsApp, phone, or manual."),
        "emergency": ("🚨 For immediate help, call your local emergency services number "
                       "(commonly 112 in many regions). Share your destination and I can provide local numbers."),
        "policy": ("Check your travel policy in the **Requests** tab. "
                   "The system auto-checks compliance when you submit a travel request."),
        "status": ("Check your request status in **Requests → My Requests** tab."),
    }
    return replies.get(intent,
                        ("I'm here to help with your corporate travel! "
                         "Try asking about flights, hotels, expenses, or trip planning."))


def _build_action_cards(intent: str, entities: dict) -> list:
    """Build quick-action cards for the UI."""
    dest = entities.get("destination", "")
    cards = {
        "plan_trip": [
            {"label": "Plan Trip", "action": "openTab", "target": "planner"},
            {"label": "Search Hotels", "action": "openTab", "target": "hotels"},
        ],
        "search_hotel": [
            {"label": "Search Hotels", "action": "openTab", "target": "hotels"},
        ],
        "search_flight": [
            {"label": "Plan Trip", "action": "openTab", "target": "planner"},
        ],
        "expense": [
            {"label": "Add Expense", "action": "openTab", "target": "expenses"},
        ],
        "meeting": [
            {"label": "Manage Meetings", "action": "openTab", "target": "meetings"},
        ],
        "emergency": [
            {"label": "🚨 SOS", "action": "openSOS"},
            {"label": "Call Ambulance", "action": "tel", "target": "108"},
        ],
        "status": [
            {"label": "My Requests", "action": "openTab", "target": "requests"},
        ],
    }
    return cards.get(intent, [
        {"label": "Trip Planner", "action": "openTab", "target": "planner"},
        {"label": "AI Chat", "action": "openTab", "target": "chat"},
    ])
