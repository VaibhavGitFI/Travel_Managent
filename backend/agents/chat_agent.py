"""
TravelSync Pro — AI Chat Agent
Gemini 2.0 Flash powered travel assistant with rich DB context.
Falls back to pattern matching when Gemini unavailable.
"""
import sys
import os
import re
import json
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.anthropic_service import claude
from services.gemini_service import gemini
from services.weather_service import weather
from services.currency_service import currency
from services.search_service import search
from database import get_db

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are TravelSync Pro, an intelligent corporate travel assistant powered by real-time data.

You help with:
- Flight and hotel search with live pricing from Google Places and flight APIs
- Trip planning for business visits across India and internationally
- Expense tracking and receipt verification via OCR
- Travel policy compliance checking
- Client meeting scheduling and coordination
- Live weather forecasts via OpenWeatherMap
- Currency conversion via real-time exchange rates
- Team coordination for multi-city and multi-timezone travel

Rules:
- Be concise, professional, and practical.
- Do NOT use emojis anywhere in your response. Plain text only.
- Use markdown formatting: **bold** for emphasis, bullet lists, tables, and headings where helpful.
- Prefer factual and actionable responses. Cite actual values when they appear in context.
- When real-time web search results are provided in context, use them to give accurate, current answers.
- If data is unavailable, say so clearly and suggest the right tab/action to get it.
- NEVER fabricate booking references, flight numbers, or specific prices that aren't in the context.
- If the user asks something outside travel, politely redirect.
"""


def _build_user_context(user: dict) -> str:
    """Build rich context from the user's actual DB data."""
    if not user or not user.get("id"):
        return ""

    context_parts = []
    now = datetime.now()
    context_parts.append(f"Current date/time: {now.strftime('%A, %B %d, %Y at %I:%M %p')}")
    context_parts.append(f"User: {user.get('name', '')} (role: {user.get('role', 'employee')}, department: {user.get('department', 'N/A')})")

    try:
        db = get_db()

        # Recent travel requests (last 5)
        try:
            cols_info = db.execute("PRAGMA table_info(travel_requests)").fetchall()
            cols = {r[1] for r in cols_info}
            select = ["request_id", "destination", "status"]
            if "origin" in cols:
                select.append("origin")
            if "start_date" in cols:
                select.append("start_date")
            if "end_date" in cols:
                select.append("end_date")
            if "duration_days" in cols:
                select.append("duration_days")
            if "estimated_total" in cols:
                select.append("estimated_total")
            if "purpose" in cols:
                select.append("purpose")

            requests = db.execute(
                f"SELECT {', '.join(select)} FROM travel_requests WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
                (user["id"],),
            ).fetchall()

            if requests:
                req_lines = []
                for r in requests:
                    rd = dict(r)
                    line = f"  - {rd.get('request_id', 'N/A')}: {rd.get('origin', '?')} → {rd.get('destination', '?')} | Status: {rd.get('status', '?')}"
                    if rd.get("start_date"):
                        line += f" | Dates: {rd['start_date']}"
                        if rd.get("end_date"):
                            line += f" to {rd['end_date']}"
                    if rd.get("estimated_total"):
                        line += f" | Budget: ₹{rd['estimated_total']:,.0f}"
                    if rd.get("purpose"):
                        line += f" | Purpose: {rd['purpose']}"
                    req_lines.append(line)
                context_parts.append("Recent travel requests:\n" + "\n".join(req_lines))
            else:
                context_parts.append("Recent travel requests: None")
        except Exception as e:
            logger.debug("[Chat Context] Requests query error: %s", e)

        # Pending approvals (for managers)
        if user.get("role") in ("manager", "admin"):
            try:
                pending = db.execute(
                    "SELECT COUNT(*) as cnt FROM approvals WHERE approver_id = ? AND status = 'pending'",
                    (user["id"],),
                ).fetchone()
                cnt = dict(pending).get("cnt", 0)
                context_parts.append(f"Pending approvals for you: {cnt}")
            except Exception:
                pass

        # Upcoming meetings (next 7 days)
        try:
            week_from_now = (now + timedelta(days=7)).strftime("%Y-%m-%d")
            today_str = now.strftime("%Y-%m-%d")
            meetings = db.execute(
                "SELECT client_name, company, destination, meeting_date, meeting_time, venue, status FROM client_meetings WHERE user_id = ? AND meeting_date >= ? AND meeting_date <= ? ORDER BY meeting_date LIMIT 5",
                (user["id"], today_str, week_from_now),
            ).fetchall()
            if meetings:
                mtg_lines = []
                for m in meetings:
                    md = dict(m)
                    line = f"  - {md.get('client_name', '?')} ({md.get('company', '')})"
                    line += f" | {md.get('meeting_date', '?')} {md.get('meeting_time', '')}"
                    line += f" | {md.get('destination', '')} - {md.get('venue', '')}"
                    line += f" | Status: {md.get('status', 'scheduled')}"
                    mtg_lines.append(line)
                context_parts.append("Upcoming meetings (next 7 days):\n" + "\n".join(mtg_lines))
            else:
                context_parts.append("Upcoming meetings: None in next 7 days")
        except Exception as e:
            logger.debug("[Chat Context] Meetings query error: %s", e)

        # Recent expenses summary
        try:
            expenses = db.execute(
                "SELECT COUNT(*) as cnt, SUM(COALESCE(verified_amount, invoice_amount, payment_amount, 0)) as total FROM expenses_db WHERE user_id = ?",
                (user["id"],),
            ).fetchone()
            ed = dict(expenses)
            if ed.get("cnt", 0) > 0:
                context_parts.append(f"Total expenses: {ed['cnt']} items, ₹{ed.get('total', 0):,.0f}")
            else:
                context_parts.append("Total expenses: None recorded")
        except Exception as e:
            logger.debug("[Chat Context] Expenses query error: %s", e)

        # Travel policy summary
        try:
            policy = db.execute("SELECT * FROM travel_policies LIMIT 1").fetchone()
            if policy:
                pd = dict(policy)
                context_parts.append(
                    f"Company policy: Flight class={pd.get('flight_class', 'economy')}, "
                    f"Hotel budget/night=₹{pd.get('hotel_budget_per_night', 'N/A')}, "
                    f"Monthly budget=₹{pd.get('monthly_budget_inr', 'N/A')}, "
                    f"Auto-approve threshold=₹{pd.get('auto_approve_threshold', 'N/A')}"
                )
        except Exception:
            pass

        db.close()
    except Exception as e:
        logger.warning("[Chat Context] DB context build failed: %s", e)

    return "\n".join(context_parts)


def _get_recent_history(user_id: int, limit: int = 6) -> list:
    """
    Get recent chat messages for multi-turn context.
    Returns Anthropic-compatible format: [{"role": "user"|"assistant", "content": str}]
    """
    try:
        db = get_db()
        rows = db.execute(
            "SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        db.close()

        messages = []
        for r in reversed(rows):
            rd = dict(r)
            role = rd["role"]  # already "user" or "assistant"
            messages.append({"role": role, "content": rd["content"]})
        return messages
    except Exception as e:
        logger.debug("[Chat History] Failed to load: %s", e)
        return []


def _history_for_gemini(history: list) -> list:
    """Convert Anthropic-style history to Gemini format."""
    return [
        {"role": "model" if h["role"] == "assistant" else "user",
         "parts": [h["content"]]}
        for h in history
    ]


def build_system_prompt(user: dict = None) -> str:
    """Build the full system prompt with user context."""
    user_context = _build_user_context(user)
    if user_context:
        return f"{SYSTEM_PROMPT}\n\n--- USER CONTEXT ---\n{user_context}\n--- END CONTEXT ---"
    return SYSTEM_PROMPT


def _summarize_trip_results(results: dict) -> dict:
    """Extract top flights, hotels, and weather from orchestrator results for inline display."""
    summary = {}
    try:
        # Destination
        trip_summary = results.get("trip_summary", {})
        summary["destination"] = trip_summary.get("destination", "")
        summary["duration"] = trip_summary.get("duration", "")
        summary["travel_dates"] = trip_summary.get("travel_dates", "")

        # Top flights
        travel = results.get("travel", {})
        flights = travel.get("flights", travel.get("options", []))
        if isinstance(flights, list):
            summary["flights"] = flights[:3]
        elif isinstance(flights, dict):
            all_flights = flights.get("outbound", flights.get("results", []))
            summary["flights"] = (all_flights[:3] if isinstance(all_flights, list) else [])

        # Top hotels
        hotels = results.get("hotels", {})
        hotel_list = hotels.get("hotels", hotels.get("results", []))
        if isinstance(hotel_list, list):
            summary["hotels"] = hotel_list[:3]

        # Weather
        weather_data = results.get("weather", {})
        summary["weather"] = {
            "summary": weather_data.get("summary", ""),
            "forecast": (weather_data.get("forecast", []))[:3],
        }
    except Exception as e:
        logger.debug("[Chat] Trip summary extraction error: %s", e)

    return summary


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

    # If plan_trip intent with a destination, run the orchestrator
    trip_results = None
    if intent == "plan_trip" and entities.get("destination"):
        try:
            from agents.orchestrator import plan_trip
            trip_input = {
                "destination": entities["destination"],
                "origin": entities.get("origin") or "",
                "duration_days": 3,
                "purpose": "business",
                "user_id": user.get("id", 1) if user else 1,
            }
            raw = plan_trip(trip_input)
            if raw.get("success"):
                trip_results = _summarize_trip_results(raw)
        except Exception as e:
            logger.warning("[Chat] Orchestrator call failed: %s", e)

    full_system_prompt = build_system_prompt(user)
    user_id = user.get("id") if user else None
    history = _get_recent_history(user_id, limit=6) if user_id else []

    # Append attachment context to the message if present
    enriched_message = message
    if context.get("attachment", {}).get("summary"):
        enriched_message += f"\n\nAttachment context: {context['attachment']['summary']}"

    # Real-time web search enrichment for travel queries
    if search.configured and intent in ("plan_trip", "search_flight", "search_hotel",
                                         "weather", "general"):
        try:
            destination = entities.get("destination", "")
            if intent == "search_flight" and destination:
                results = search.search_flights(
                    entities.get("origin") or "India", destination,
                    entities.get("date") or "")
            elif intent == "search_hotel" and destination:
                results = search.search_hotels(destination)
            else:
                results = search.search_travel(message[:120])
            ctx = search.format_for_prompt(results)
            if ctx:
                enriched_message = f"{enriched_message}\n\n{ctx}"
        except Exception as e:
            logger.warning("[Chat] Search enrichment failed: %s", e)

    reply = None
    model_used = None

    # ── 1. Try Claude (Anthropic) ─────────────────────────────────
    if claude.is_available:
        reply = claude.generate(enriched_message, system=full_system_prompt, history=history)
        if reply:
            model_used = "claude-opus-4-6"

    # ── 2. Try Gemini as fallback ─────────────────────────────────
    if not reply and gemini.is_available:
        gemini_history = _history_for_gemini(history)
        gemini_history.append({"role": "user", "parts": [enriched_message]})
        reply = gemini.generate_with_history(full_system_prompt, gemini_history)
        if reply:
            model_used = "gemini-2.0-flash"

    if reply:
        reply = _enrich_reply(reply, intent, entities)
        action_cards = _build_action_cards(intent, entities)
        result = {
            "reply": reply,
            "intent": intent,
            "entities": entities,
            "action_cards": action_cards,
            "ai_powered": True,
            "model": model_used,
        }
        if trip_results:
            result["trip_results"] = trip_results
        return result

    # ── 3. Pattern-based fallback ─────────────────────────────────
    reply = _pattern_reply(message, intent, entities)
    action_cards = _build_action_cards(intent, entities)
    result = {
        "reply": reply,
        "intent": intent,
        "entities": entities,
        "action_cards": action_cards,
        "ai_powered": False,
        "note": "Set ANTHROPIC_API_KEY for Claude-powered responses",
    }
    if trip_results:
        result["trip_results"] = trip_results
    return result


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
        "mumbai", "delhi", "bangalore", "bengaluru", "hyderabad", "chennai", "kolkata", "pune",
        "ahmedabad", "jaipur", "surat", "lucknow", "kochi", "goa", "varanasi", "amritsar",
        "london", "paris", "berlin", "frankfurt", "amsterdam", "zurich", "madrid", "barcelona",
        "new york", "los angeles", "san francisco", "chicago", "toronto", "vancouver",
        "dubai", "abu dhabi", "doha", "riyadh", "singapore", "bangkok", "tokyo", "osaka",
        "seoul", "beijing", "shanghai", "sydney", "melbourne", "auckland",
    ]
    known_cities = context.get("known_cities", default_cities)
    msg_lower = message.lower()
    found_cities = [c.title() for c in known_cities if c in msg_lower]

    amount_match = re.search(r"(?:₹|rs\.?\s*|inr\s*|\$|€|£|aed\s*|usd\s*|eur\s*)([0-9,]+(?:\.[0-9]{1,2})?)", msg_lower, re.IGNORECASE)
    amount = float(amount_match.group(1).replace(",", "")) if amount_match else None

    date_match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b", message)
    date = date_match.group(1) if date_match else None

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
            weather_snippet = (f"\n\n**Live Weather in {destination}**: "
                               f"{w.get('temp')}°C, {w.get('description')}, "
                               f"Humidity: {w.get('humidity')}%")
            reply += weather_snippet
        except Exception as e:
            logger.warning("[Chat] Weather enrich failed: %s", e)

    if intent == "currency":
        try:
            rates = currency.get_rates()
            if rates.get("source") == "openexchangerates":
                reply += "\n\n*Live exchange rates from OpenExchangeRates*"
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
        "search_flight": (f"I can search live flights to {destination}. "
                           "Go to **Trip Planner** → select flight mode to see real-time fares."),
        "weather": (f"I can check the live weather for {destination}. "
                    "Ask me again in a moment or visit the Trip Planner for the full forecast."),
        "expense": ("Add your expense in the **Expenses** tab. "
                    "Upload your receipt image and I'll auto-extract the amount via OCR."),
        "meeting": ("Add client meetings in the **Meetings** tab. "
                    "You can add meetings from any source: email, WhatsApp, phone, or manual."),
        "emergency": ("For immediate help, call your local emergency services number "
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
            {"label": "SOS", "action": "openSOS"},
            {"label": "Call Ambulance", "action": "tel", "target": "108"},
        ],
        "status": [
            {"label": "My Requests", "action": "openTab", "target": "requests"},
        ],
        "policy": [
            {"label": "View Requests", "action": "openTab", "target": "requests"},
        ],
    }
    return cards.get(intent, [])
