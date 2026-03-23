"""
TravelSync Pro — WhatsApp Bot Routes
Interactive AI-powered WhatsApp bot via Twilio webhook.
Maintains per-user conversation history for contextual responses.
Supports receipt image scanning via OCR.
"""
import logging
import time
import os
import tempfile
from collections import defaultdict
from base64 import b64encode
from flask import Blueprint, request, Response
import requests as http_requests
from database import get_db
from services.whatsapp_service import whatsapp_service

logger = logging.getLogger(__name__)

# ── Conversation memory (per phone number) ───────────────────────────────────
# Stores last N messages per user for context. Expires after 30 min of inactivity.

_MAX_HISTORY = 20          # max messages to keep per user
_SESSION_TIMEOUT = 1800    # 30 minutes

_conversations: dict[str, dict] = defaultdict(lambda: {"messages": [], "last_active": 0})

# Pending expenses waiting for category confirmation
_pending_expenses: dict[str, dict] = {}  # phone -> {amount, vendor, date, description, gst, payment_method, user_id}


def _get_history(phone: str) -> list[dict]:
    """Get conversation history for a phone number. Clears if expired."""
    session = _conversations[phone]
    if time.time() - session["last_active"] > _SESSION_TIMEOUT:
        session["messages"] = []
    return session["messages"]


def _add_to_history(phone: str, role: str, content: str):
    """Add a message to conversation history."""
    session = _conversations[phone]
    session["messages"].append({"role": role, "content": content})
    session["last_active"] = time.time()
    # Trim old messages
    if len(session["messages"]) > _MAX_HISTORY:
        session["messages"] = session["messages"][-_MAX_HISTORY:]


def _clear_history(phone: str):
    """Clear conversation history for a user."""
    _conversations[phone] = {"messages": [], "last_active": 0}

whatsapp_bp = Blueprint("whatsapp", __name__, url_prefix="/api/whatsapp")

# ── Menus ────────────────────────────────────────────────────────────────────

HELP_TEXT = (
    "*TravelSync Pro*\n"
    "Corporate Travel Assistant\n\n"
    "*Available Commands:*\n"
    "1 - My Trips\n"
    "2 - Trip Status\n"
    "3 - Approvals\n"
    "4 - Expenses\n"
    "5 - Meetings\n"
    "6 - Weather (e.g. weather Mumbai)\n"
    "7 - SOS / Emergency\n\n"
    "*Expense Tracking:*\n"
    "- Send a receipt photo to auto-scan and save\n"
    "- Type: expense 500 Uber cab to airport\n"
    "- UPI screenshots are auto-categorized\n\n"
    "You can also type any travel-related question and I will assist you."
)

WELCOME_TEXT = (
    "*Welcome to TravelSync Pro*\n\n"
    "I can help you manage trips, review approvals, "
    "track expenses, and answer travel questions.\n\n"
    "Type *help* to see available commands."
)


# ── User lookup ──────────────────────────────────────────────────────────────

def _find_user_by_phone(phone: str) -> dict | None:
    try:
        db = get_db()
        clean = phone.replace("whatsapp:", "").strip()
        user = db.execute("SELECT * FROM users WHERE phone = ?", (clean,)).fetchone()
        if not user and clean.startswith("+91"):
            alt = clean[3:]
            user = db.execute("SELECT * FROM users WHERE phone LIKE ?", (f"%{alt}",)).fetchone()
        db.close()
        return dict(user) if user else None
    except Exception:
        return None


# ── Data handlers ────────────────────────────────────────────────────────────

def _get_user_trips(user_id: int, limit: int = 5) -> str:
    try:
        db = get_db()
        rows = db.execute(
            "SELECT request_id, destination, origin, start_date, end_date, status, estimated_total "
            "FROM travel_requests WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        db.close()

        if not rows:
            return "You don't have any trips yet. Create one on TravelSync Pro."

        lines = ["*Your Recent Trips*\n"]
        for r in rows:
            row = dict(r)
            budget = f"Rs. {int(row.get('estimated_total') or 0):,}" if row.get("estimated_total") else "TBD"
            lines.append(
                f"*{row.get('origin', '?')} > {row['destination']}*\n"
                f"  Dates: {row.get('start_date', '?')} to {row.get('end_date', '?')}\n"
                f"  Budget: {budget}\n"
                f"  Status: {row.get('status', 'draft')}\n"
                f"  ID: {row.get('request_id', '?')}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.warning("[WA Bot] get_user_trips failed: %s", e)
        return "Unable to load trips at the moment. Please try again."


def _get_pending_approvals(user_id: int, role: str) -> str:
    try:
        if role not in ("admin", "manager"):
            return "Only managers and admins can view approvals."

        db = get_db()
        if role == "admin":
            rows = db.execute(
                "SELECT a.request_id, t.destination, t.origin, t.start_date, "
                "t.estimated_total, u.full_name "
                "FROM approvals a "
                "JOIN travel_requests t ON a.request_id = t.request_id "
                "JOIN users u ON t.user_id = u.id "
                "WHERE a.status = 'pending' ORDER BY a.created_at DESC LIMIT 5"
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT a.request_id, t.destination, t.origin, t.start_date, "
                "t.estimated_total, u.full_name "
                "FROM approvals a "
                "JOIN travel_requests t ON a.request_id = t.request_id "
                "JOIN users u ON t.user_id = u.id "
                "WHERE a.status = 'pending' AND a.approver_id = ? "
                "ORDER BY a.created_at DESC LIMIT 5",
                (user_id,),
            ).fetchall()
        db.close()

        if not rows:
            return "No pending approvals. You're all caught up."

        lines = [f"*Pending Approvals ({len(rows)})*\n"]
        for i, r in enumerate(rows, 1):
            row = dict(r)
            budget = f"Rs. {int(row.get('estimated_total') or 0):,}" if row.get("estimated_total") else "TBD"
            lines.append(
                f"*{i}. {row.get('full_name', '?')}* > {row['destination']}\n"
                f"  Date: {row.get('start_date', '?')} | Budget: {budget}\n"
                f"  ID: {row.get('request_id', '?')}\n"
                f"  To approve: approve {row.get('request_id', '')}\n"
                f"  To reject: reject {row.get('request_id', '')}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.warning("[WA Bot] get_pending_approvals failed: %s", e)
        return "Unable to load approvals. Please try again."


def _get_expense_summary(user_id: int) -> str:
    try:
        db = get_db()
        rows = db.execute(
            "SELECT category, SUM(invoice_amount) as total, COUNT(*) as cnt "
            "FROM expenses_db WHERE user_id = ? GROUP BY category ORDER BY total DESC",
            (user_id,),
        ).fetchall()
        total_row = db.execute(
            "SELECT SUM(invoice_amount) as grand_total, COUNT(*) as cnt FROM expenses_db WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        db.close()

        if not rows:
            return "No expenses recorded yet."

        total_row = dict(total_row)
        lines = ["*Expense Summary*\n"]
        for r in rows:
            row = dict(r)
            lines.append(f"  {(row.get('category') or 'other').title()}: Rs. {int(row['total'] or 0):,} ({row['cnt']} items)")

        grand = int(total_row.get("grand_total") or 0)
        lines.append(f"\n*Total: Rs. {grand:,}* across {total_row.get('cnt', 0)} expenses")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("[WA Bot] get_expense_summary failed: %s", e)
        return "Unable to load expenses. Please try again."


def _get_upcoming_meetings(user_id: int) -> str:
    try:
        db = get_db()
        rows = db.execute(
            "SELECT client_name, company, destination, meeting_date, meeting_time, venue, agenda "
            "FROM client_meetings WHERE user_id = ? AND status = 'scheduled' "
            "ORDER BY meeting_date ASC LIMIT 5",
            (user_id,),
        ).fetchall()
        db.close()

        if not rows:
            return "No upcoming meetings scheduled."

        lines = ["*Upcoming Meetings*\n"]
        for i, r in enumerate(rows, 1):
            row = dict(r)
            lines.append(
                f"*{i}. {row.get('client_name', '?')}* ({row.get('company', '')})\n"
                f"  Location: {row.get('venue', row.get('destination', '?'))}\n"
                f"  Date: {row.get('meeting_date', '?')} at {row.get('meeting_time', '?')}\n"
                f"  Agenda: {row.get('agenda', 'No agenda')}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.warning("[WA Bot] get_upcoming_meetings failed: %s", e)
        return "Unable to load meetings. Please try again."


def _handle_approve_reject(user: dict, command: str, request_id: str) -> str:
    try:
        if user.get("role") not in ("admin", "manager"):
            return "Only managers and admins can approve or reject requests."

        from agents.request_agent import process_approval
        action = "approve" if command == "approve" else "reject"
        result = process_approval(
            request_id, approver_id=user["id"], action=action,
            comments=f"Via WhatsApp by {user.get('full_name', user['username'])}"
        )

        if result.get("success"):
            return f"Request *{request_id}* has been *{action}d* successfully."
        return f"Could not {action} request: {result.get('error', 'Unknown error')}"
    except Exception as e:
        logger.warning("[WA Bot] approve/reject failed: %s", e)
        return "Failed to process the request. Please try on the web app."


def _get_weather(city: str) -> str:
    try:
        from services.weather_service import weather
        data = weather.get_current(city)
        if not data:
            return f"Weather data is not available for {city} at the moment."

        return (
            f"*Weather in {city}*\n\n"
            f"Temperature: {data.get('temperature', '?')}°C\n"
            f"Wind: {data.get('wind_speed', '?')} km/h\n"
            f"Humidity: {data.get('humidity', '?')}%\n"
            f"Condition: {data.get('description', '?')}"
        )
    except Exception:
        return f"Weather service is currently unavailable for {city}."


# ── AI Chat ──────────────────────────────────────────────────────────────────

def _ai_chat(user: dict, message: str, phone: str) -> str:
    system_prompt = (
        "You are TravelSync Pro, a corporate travel assistant available on WhatsApp. "
        "You help with travel planning, hotel recommendations, flight options, expense policies, and travel tips. "
        f"The user is {user.get('full_name', 'an employee')} ({user.get('role', 'employee')}) "
        f"from the {user.get('department', 'General')} department.\n\n"
        "Rules:\n"
        "- Respond concisely in under 150 words\n"
        "- Use *bold* only for section headings\n"
        "- Do not use italic, strikethrough, or emoji-heavy formatting\n"
        "- Use numbered lists (1. 2. 3.) for recommendations and steps\n"
        "- Use bullet points (- or •) for details under each item\n"
        "- Add a blank line between sections for readability\n"
        "- Never reveal or mention your AI model, engine, or provider name\n"
        "- You are TravelSync Pro. Refer to yourself only as TravelSync Pro if needed\n"
        "- Be professional, clear, and well-structured like a premium assistant\n"
        "- End with a brief actionable suggestion when appropriate\n"
        "- If asked something unrelated to travel or business, politely redirect\n"
        "- You have access to the conversation history. Use it to maintain context and give relevant follow-up answers."
    )

    # Build conversation history for the AI
    history = _get_history(phone)

    # Try Claude first (better at multi-turn conversations)
    try:
        from services.anthropic_service import claude
        if claude.is_available:
            response = claude.generate(message, system=system_prompt, history=history)
            if response:
                return response.strip()
    except Exception:
        pass

    # Fallback to Gemini
    try:
        from services.gemini_service import gemini
        gemini_ok = gemini.configured and not (
            hasattr(gemini, '_cooldown_until') and time.time() < gemini._cooldown_until
        )
        if gemini_ok:
            # Build context string from history for Gemini
            context_lines = []
            for msg in history[-10:]:
                role_label = "User" if msg["role"] == "user" else "Assistant"
                context_lines.append(f"{role_label}: {msg['content']}")
            context = "\n".join(context_lines)
            full_prompt = f"{system_prompt}\n\nConversation so far:\n{context}\n\nUser: {message}" if context else f"{system_prompt}\n\nUser: {message}"
            response = gemini.generate(full_prompt, model_type="flash")
            if response:
                return response.strip()
    except Exception:
        pass

    return _ai_fallback(message)


def _ai_fallback(message: str) -> str:
    msg = message.lower()
    if any(w in msg for w in ("hotel", "stay", "accommodation")):
        return (
            "I'm unable to search hotels at the moment. "
            "Please use the Trip Planner on the TravelSync Pro web app, "
            "or try again in a minute."
        )
    if any(w in msg for w in ("flight", "fly", "book")):
        return (
            "Flight search is temporarily unavailable. "
            "Please use the Trip Planner on the TravelSync Pro web app, "
            "or try again in a minute."
        )
    if any(w in msg for w in ("weather", "rain", "temperature")):
        city = message.strip().split()[-1]
        return _get_weather(city) if len(city) > 2 else "Please specify a city. Example: weather Mumbai"

    return (
        "I'm temporarily unable to process this request. "
        "Please try again in a minute.\n\n"
        "Available commands:\n"
        "1 - My Trips\n"
        "3 - Approvals\n"
        "4 - Expenses\n"
        "5 - Meetings\n"
        "help - Full menu"
    )


# ── Receipt OCR via WhatsApp image ────────────────────────────────────────────

def _process_receipt_image(media_url: str, user: dict, caption: str = "") -> str:
    """Download image from Twilio, run OCR, auto-categorize, and save expense."""
    try:
        # Download image from Twilio
        sid = os.getenv("TWILIO_ACCOUNT_SID")
        token = os.getenv("TWILIO_AUTH_TOKEN")
        auth = b64encode(f"{sid}:{token}".encode()).decode()

        resp = http_requests.get(media_url, headers={"Authorization": f"Basic {auth}"}, timeout=15)
        if resp.status_code != 200:
            return "Could not download the image. Please try again."

        image_bytes = resp.content

        # Step 1: Run Google Vision OCR to get actual text from the image
        ocr_data = None
        raw_text = ""
        try:
            from services.vision_service import vision
            if vision.configured:
                ocr_data = vision.extract_from_bytes(image_bytes)
                raw_text = ocr_data.get("raw_text", "")
                logger.info("[WA Bot] OCR extracted %d chars, source=%s", len(raw_text), ocr_data.get("source"))
        except Exception as exc:
            logger.warning("[WA Bot] Vision OCR failed: %s", exc)

        # Step 2: If OCR got text, use parsed data + AI to categorize
        # If OCR failed, tell user we can't process
        if not raw_text and not (ocr_data and ocr_data.get("extracted")):
            return (
                "*Receipt Processing*\n\n"
                "Could not read text from this image. Please ensure:\n"
                "- The receipt is clearly visible\n"
                "- The image is not blurry\n"
                "- Text is readable\n\n"
                "Or type: expense 500 description"
            )

        # Use OCR-parsed fields first
        extracted = ocr_data.get("extracted", {}) if ocr_data else {}
        amount = extracted.get("amount")
        vendor = extracted.get("vendor")
        date = extracted.get("date")
        gst = extracted.get("cgst", 0) + extracted.get("sgst", 0) + extracted.get("igst", 0)
        if gst == 0:
            gst = None
        payment_method = extracted.get("payment_method", "")

        # Step 3: AI categorization using the REAL OCR text
        ai_result = _ai_categorize_receipt(raw_text, caption, extracted)
        category = ai_result.get("category", "other")
        description = ai_result.get("description") or caption or f"Receipt from {vendor or 'unknown'}"

        # Override with AI if OCR missed fields
        if not amount and ai_result.get("amount"):
            amount = ai_result["amount"]
        if not vendor and ai_result.get("vendor"):
            vendor = ai_result["vendor"]
        if not date and ai_result.get("date"):
            date = ai_result["date"]

        cat_labels = {
            "flight": "Flight", "hotel": "Hotel", "food": "Food & Meals",
            "transport": "Local Transport", "visa": "Visa / Docs",
            "communication": "Communication", "other": "Other",
        }
        confident_categories = {"flight", "hotel", "food", "transport", "visa", "communication"}
        phone = user.get("phone", "").replace("whatsapp:", "").strip()

        # Build extracted details summary
        lines = ["*Receipt Scanned*\n"]
        if amount:
            lines.append(f"*Amount:* Rs. {float(amount):,.2f}")
        if vendor:
            lines.append(f"*Vendor:* {vendor}")
        if date:
            lines.append(f"*Date:* {date}")
        if gst:
            lines.append(f"*GST:* Rs. {float(gst):,.2f}")
        if payment_method:
            lines.append(f"*Payment:* {payment_method}")
        if description and description != caption:
            lines.append(f"*Description:* {description}")

        # Decide: auto-save or ask for category
        if category in confident_categories:
            # Auto-save with detected category
            lines.append(f"\n*Category:* {cat_labels.get(category, category.title())} (auto-detected)")
            saved = _save_expense(user["id"], category, description, amount, vendor, date)
            lines.append("")
            if saved:
                lines.append("Expense saved to your account.")
            else:
                lines.append("Could not save automatically. Please submit on the app.")
        else:
            # Category not confident — ask the user
            pending = {
                "amount": amount, "vendor": vendor, "date": date,
                "description": description, "gst": gst,
                "payment_method": payment_method, "user_id": user["id"],
            }
            _pending_expenses[phone] = pending

            lines.append("\nI could not auto-detect the category. Please reply with a number:\n")
            lines.append("1 - Flight")
            lines.append("2 - Hotel")
            lines.append("3 - Food & Meals")
            lines.append("4 - Local Transport")
            lines.append("5 - Visa / Docs")
            lines.append("6 - Communication")
            lines.append("7 - Other")

        return "\n".join(lines)

    except Exception as exc:
        logger.exception("[WA Bot] Receipt processing failed: %s", exc)
        return "An error occurred while processing the receipt. Please try again."


def _ai_categorize_receipt(ocr_text: str, caption: str, ocr_extracted: dict) -> dict:
    """Use AI to categorize receipt based on REAL OCR text — no hallucination."""
    prompt = (
        "You are an expense categorization AI. You have the EXACT text from a receipt below.\n"
        "Based ONLY on this text, extract and categorize:\n\n"
        f"--- RECEIPT TEXT ---\n{ocr_text[:1500]}\n--- END ---\n\n"
    )
    if ocr_extracted:
        prompt += f"OCR already extracted: amount={ocr_extracted.get('amount')}, vendor={ocr_extracted.get('vendor')}, date={ocr_extracted.get('date')}\n\n"
    if caption:
        prompt += f"User note: {caption}\n\n"

    prompt += (
        "Based STRICTLY on the receipt text above, provide:\n"
        "1. category (MUST be one of: flight, hotel, food, transport, visa, communication, other)\n"
        "2. description (brief 5-10 word summary of what was purchased)\n"
        "3. vendor (merchant/company name from the receipt)\n"
        "4. amount (total amount in INR, number only — only if OCR missed it)\n"
        "5. date (YYYY-MM-DD — only if OCR missed it)\n\n"
        "IMPORTANT: Only use information from the receipt text. Do NOT guess or make up data.\n\n"
        "Respond in this exact format (one per line):\n"
        "category: <category>\ndescription: <text>\nvendor: <name>\namount: <number or empty>\ndate: <date or empty>"
    )

    # Try Claude
    try:
        from services.anthropic_service import claude
        if claude.is_available:
            resp = claude.generate(prompt, system="You are a receipt categorizer. Only use data from the receipt text provided. Never hallucinate.")
            if resp:
                return _parse_extraction(resp)
    except Exception:
        pass

    # Fallback to Gemini
    try:
        from services.gemini_service import gemini
        if gemini.configured and not (hasattr(gemini, '_cooldown_until') and time.time() < gemini._cooldown_until):
            resp = gemini.generate(prompt, model_type="flash")
            if resp:
                return _parse_extraction(resp)
    except Exception:
        pass

    # Fallback: keyword categorization from OCR text
    return {"category": _categorize_text(ocr_text + " " + (caption or "")), "description": caption or ""}


def _handle_quick_expense(user: dict, body: str, phone: str) -> str:
    """Handle quick expense command: expense 500 uber cab to airport"""
    text = body.strip()
    # Remove prefix
    for prefix in ("expense ", "exp "):
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
            break

    if not text:
        return "Usage: expense 500 Uber cab to airport\n\nOr send a receipt photo to auto-scan."

    # Try to extract amount from the start
    parts = text.split(None, 1)
    amount_str = parts[0].replace(",", "").replace("₹", "").replace("rs", "").replace("Rs", "")
    try:
        amount = float(amount_str)
    except ValueError:
        return "Could not read the amount. Usage: expense 500 Uber cab to airport"

    description = parts[1] if len(parts) > 1 else "Quick expense"
    today = time.strftime("%Y-%m-%d")

    # AI categorize the description
    category = _categorize_text(description)

    if category and category != "other":
        cat_labels = {"flight": "Flight", "hotel": "Hotel", "food": "Food & Meals", "transport": "Local Transport", "visa": "Visa / Docs", "communication": "Communication", "other": "Other"}
        saved = _save_expense(user["id"], category, description, amount, "", today)
        if saved:
            return (
                f"*Expense Saved*\n\n"
                f"*Amount:* Rs. {amount:,.2f}\n"
                f"*Category:* {cat_labels.get(category, category)} (auto-detected)\n"
                f"*Description:* {description}\n"
                f"*Date:* {today}\n\n"
                f"Saved to your TravelSync account."
            )
        return "Could not save. Please try on the app."
    else:
        _pending_expenses[phone] = {
            "amount": amount, "vendor": "", "date": today,
            "description": description, "gst": None,
            "payment_method": "", "user_id": user["id"],
        }
        return (
            f"*Quick Expense*\n\n"
            f"*Amount:* Rs. {amount:,.2f}\n"
            f"*Description:* {description}\n\n"
            "Please select a category:\n\n"
            "1 - Flight\n"
            "2 - Hotel\n"
            "3 - Food & Meals\n"
            "4 - Local Transport\n"
            "5 - Visa / Docs\n"
            "6 - Communication\n"
            "7 - Other"
        )


def _categorize_text(description: str) -> str:
    """Auto-categorize expense from description text."""
    d = description.lower()
    # Check transport FIRST (cab to airport should be transport, not flight)
    if any(w in d for w in ("cab", "uber", "ola", "taxi", "auto", "metro", "bus", "petrol", "fuel", "parking", "toll", "rickshaw")):
        return "transport"
    if any(w in d for w in ("flight", "airline", "air india", "indigo", "vistara", "spicejet", "boarding pass", "airfare")):
        return "flight"
    if any(w in d for w in ("hotel", "marriott", "oyo", "taj", "resort", "stay", "room", "lodge", "airbnb", "check-in")):
        return "hotel"
    if any(w in d for w in ("food", "lunch", "dinner", "breakfast", "meal", "restaurant", "cafe", "zomato", "swiggy", "coffee", "tea", "snack")):
        return "food"
    if any(w in d for w in ("train", "railway", "irctc")):
        return "transport"
    if any(w in d for w in ("visa", "passport", "document", "stamp", "embassy")):
        return "visa"
    if any(w in d for w in ("phone", "sim", "recharge", "internet", "wifi", "data", "call")):
        return "communication"
    return "other"


def _save_expense(user_id: int, category: str, description: str, amount, vendor: str, date: str) -> bool:
    """Save an expense to the database. Returns True on success."""
    try:
        desc = description or (f"Receipt from {vendor}" if vendor else "Expense")
        if vendor and vendor not in desc:
            desc = f"{vendor} - {desc}"
        db = get_db()
        db.execute(
            """INSERT INTO expenses_db
               (user_id, category, description, invoice_amount, date, verification_status, stage, currency_code)
               VALUES (?, ?, ?, ?, ?, 'pending', 1, 'INR')""",
            (user_id, category, desc, float(amount or 0), date or ""),
        )
        db.commit()
        db.close()
        return True
    except Exception as exc:
        logger.warning("[WA Bot] Failed to save expense: %s", exc)
        return False


def _parse_extraction(text: str) -> dict:
    """Parse the structured AI response into a dict."""
    result = {}
    for line in text.strip().split("\n"):
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower().replace(" ", "_")
        val = val.strip()
        if key in ("amount", "gst"):
            # Extract number
            cleaned = "".join(c for c in val if c.isdigit() or c == ".")
            if cleaned:
                try:
                    result[key] = float(cleaned)
                except ValueError:
                    pass
        elif key in ("vendor", "date", "category", "description", "payment_method"):
            if val and val.lower() not in ("none", "empty", "n/a", ""):
                result[key] = val
    return result


# ── Message router ───────────────────────────────────────────────────────────

def _process_message(from_number: str, body: str) -> str:
    text = body.strip().lower()
    phone = from_number.replace("whatsapp:", "").strip()
    user = _find_user_by_phone(from_number)

    logger.info("[WA Bot] Processing: text='%s', user=%s", text, user.get("username") if user else "unknown")

    # Sandbox join
    if text.startswith("join "):
        _clear_history(phone)
        if user:
            return f"Hello {user.get('full_name', 'there')}. You are now connected.\n\nType *help* to see available commands."
        return WELCOME_TEXT

    # Greetings — reset conversation
    greetings = ("hi", "hello", "hey", "start", "hii", "hiii", "yo", "sup")
    if text in greetings or text.startswith("hi ") or text.startswith("hello ") or text.startswith("hey "):
        _clear_history(phone)
        if user:
            return f"Hello {user.get('full_name', 'there')}.\n\n" + HELP_TEXT
        return WELCOME_TEXT + "\n\nNote: Your phone number is not linked to a TravelSync account. Please contact your admin."

    if text in ("help", "menu", "?"):
        return HELP_TEXT

    # Clear command
    if text in ("clear", "reset", "new", "new chat"):
        _clear_history(phone)
        return "Conversation cleared. How can I help you?"

    if not user:
        return (
            "*Account Not Linked*\n\n"
            "Your phone number is not connected to a TravelSync Pro account. "
            "Please ask your admin to add your phone number, "
            "or sign in to TravelSync Pro and update your profile."
        )

    # Check if user has a pending expense waiting for category
    if phone in _pending_expenses:
        cat_map = {"1": "flight", "2": "hotel", "3": "food", "4": "transport", "5": "visa", "6": "communication", "7": "other"}
        if text in cat_map:
            pending = _pending_expenses.pop(phone)
            category = cat_map[text]
            cat_labels = {"flight": "Flight", "hotel": "Hotel", "food": "Food & Meals", "transport": "Local Transport", "visa": "Visa / Docs", "communication": "Communication", "other": "Other"}
            saved = _save_expense(
                pending["user_id"], category, pending.get("description", ""),
                pending.get("amount"), pending.get("vendor", ""), pending.get("date", ""),
            )
            if saved:
                return (
                    f"*Expense Saved*\n\n"
                    f"*Amount:* Rs. {float(pending.get('amount', 0)):,.2f}\n"
                    f"*Category:* {cat_labels.get(category, category)}\n"
                    f"*Vendor:* {pending.get('vendor', '—')}\n\n"
                    f"Expense has been added to your TravelSync account."
                )
            return "Could not save the expense. Please try again or submit on the app."
        elif text in ("cancel", "skip", "no"):
            _pending_expenses.pop(phone)
            return "Expense cancelled. Send another receipt anytime."
        # If they typed something else, remind them
        # Don't consume the message — fall through to normal processing
        # But first remind about pending
        # Actually let's just remind and continue
        pass

    # Commands (these don't need conversation context)
    if text in ("1", "trips", "my trips"):
        return _get_user_trips(user["id"])

    if text in ("2", "status", "trip status"):
        return _get_user_trips(user["id"], limit=3) + "\n\nReply with a trip ID for details."

    if text in ("3", "approvals", "pending"):
        return _get_pending_approvals(user["id"], user.get("role", "employee"))

    if text in ("4", "expenses", "expense"):
        return _get_expense_summary(user["id"])

    if text in ("5", "meetings", "meeting"):
        return _get_upcoming_meetings(user["id"])

    if text.startswith("6") or text.startswith("weather"):
        city = text.replace("6", "").replace("weather", "").strip()
        if not city:
            return "Please specify a city. Example: weather Mumbai"
        return _get_weather(city)

    if text in ("7", "sos", "emergency"):
        return (
            "*Emergency Contacts*\n\n"
            "112 - General Emergency\n"
            "108 - Ambulance\n"
            "100 - Police\n"
            "101 - Fire\n\n"
            "To send an SOS alert to your manager, please use the TravelSync Pro app."
        )

    # Quick expense: "expense 500 uber cab to airport"
    if text.startswith("expense ") or text.startswith("exp "):
        return _handle_quick_expense(user, body, phone)

    # Approve / reject
    if text.startswith("approve ") or text.startswith("reject "):
        parts = text.split(maxsplit=1)
        cmd = parts[0]
        rid = parts[1].strip().upper() if len(parts) > 1 else ""
        if not rid:
            return f"Usage: {cmd} TR-2026-XXXXXXX"
        return _handle_approve_reject(user, cmd, rid)

    # AI chat — with conversation memory
    _add_to_history(phone, "user", body)
    reply = _ai_chat(user, body, phone)
    _add_to_history(phone, "assistant", reply)
    return reply


# ── Webhook ──────────────────────────────────────────────────────────────────

@whatsapp_bp.route("/webhook", methods=["POST"])
def webhook():
    from_number = request.form.get("From", "")
    body = request.form.get("Body", "").strip()
    num_media = int(request.form.get("NumMedia", "0"))

    logger.info("[WA Bot] Message from %s: '%s', media=%d", from_number, body[:100], num_media)

    # Handle image/media messages (receipt scanning)
    if num_media > 0:
        media_url = request.form.get("MediaUrl0", "")
        media_type = request.form.get("MediaContentType0", "")
        logger.info("[WA Bot] Media received: type=%s, url=%s", media_type, media_url[:80])

        if media_type and ("image" in media_type or "pdf" in media_type):
            user = _find_user_by_phone(from_number)
            if not user:
                reply = "Your phone is not linked to a TravelSync account. Please contact your admin to scan receipts."
            else:
                reply = _process_receipt_image(media_url, user, caption=body)
        else:
            reply = "I can only process images and PDFs. Please send a photo of your receipt."

        clean_from = from_number.replace("whatsapp:", "")
        whatsapp_service.send(clean_from, "", reply, "info", ai_tips=False, raw_body=True)
        return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                        content_type="text/xml", status=200)

    # Handle text messages
    if not body:
        return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                        content_type="text/xml", status=200)

    reply = _process_message(from_number, body)

    clean_from = from_number.replace("whatsapp:", "")
    whatsapp_service.send(clean_from, "", reply, "info", ai_tips=False, raw_body=True)

    return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                    content_type="text/xml", status=200)


@whatsapp_bp.route("/webhook", methods=["GET"])
def webhook_verify():
    return {"status": "ok", "service": "TravelSync WhatsApp Bot"}, 200
