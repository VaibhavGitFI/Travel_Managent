"""
TravelSync Pro — Zoho Cliq Bot Handler
Handles incoming messages from the TravelSync Pro bot in Zoho Cliq.
Reuses the same logic as the WhatsApp bot for consistency.
"""
import hmac
import logging
from flask import Blueprint, request, jsonify
from database import get_db

logger = logging.getLogger(__name__)

cliq_bot_bp = Blueprint("cliq_bot", __name__, url_prefix="/api/cliq")


def _verify_cliq_webhook() -> bool:
    """Verify Cliq webhook request via shared secret token.
    Fail-closed: if CLIQ_WEBHOOK_TOKEN is not configured, reject all requests."""
    from config import Config
    expected_token = Config.CLIQ_WEBHOOK_TOKEN
    if not expected_token:
        logger.warning("[Cliq Bot] CLIQ_WEBHOOK_TOKEN not configured — rejecting webhook")
        return False

    # Zoho Cliq can send the token in Authorization header or a custom header.
    incoming = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not incoming:
        incoming = request.headers.get("X-Cliq-Token", "").strip()
    if not incoming:
        return False

    return hmac.compare_digest(incoming, expected_token)


# Guided expense flow state per user
from services.state_store import StateNamespace
_expense_flow = StateNamespace("cliq:expense_flow", ttl_seconds=1800)

CATEGORY_BUTTONS = [
    {"text": "Flight"}, {"text": "Hotel"}, {"text": "Food & Meals"},
    {"text": "Local Transport"}, {"text": "Visa / Docs"}, {"text": "Communication"}, {"text": "Other"},
]

CATEGORY_MAP = {
    "flight": "flight", "hotel": "hotel", "food & meals": "food", "food": "food",
    "local transport": "transport", "transport": "transport", "visa / docs": "visa", "visa": "visa",
    "communication": "communication", "other": "other",
}


def _process_receipt(file_url: str, user: dict, caption: str = "") -> str:
    """Download image from Cliq, run OCR, categorize, and save expense. Same as WhatsApp flow."""
    try:
        from services.http_client import http as http_requests
        from routes.whatsapp import (
            _ai_categorize_receipt, _save_expense, _categorize_text,
            _pending_expenses,
        )

        # Download image
        resp = http_requests.get(file_url, timeout=15)
        if resp.status_code != 200:
            return "Could not download the image. Please try again."

        image_bytes = resp.content

        # Run Google Vision OCR
        raw_text = ""
        ocr_data = None
        try:
            from services.vision_service import vision
            if vision.configured:
                ocr_data = vision.extract_from_bytes(image_bytes)
                raw_text = ocr_data.get("raw_text", "")
                logger.info("[Cliq Bot] OCR extracted %d chars", len(raw_text))
        except Exception as exc:
            logger.warning("[Cliq Bot] Vision OCR failed: %s", exc)

        if not raw_text and not (ocr_data and ocr_data.get("extracted")):
            return (
                "*Receipt Processing*\n\n"
                "Could not read text from this image. Please ensure:\n"
                "- The receipt is clearly visible\n"
                "- The image is not blurry\n\n"
                "Or type: expense 500 description"
            )

        # Use OCR-parsed fields
        extracted = ocr_data.get("extracted", {}) if ocr_data else {}
        amount = extracted.get("amount")
        vendor = extracted.get("vendor")
        date = extracted.get("date")
        gst = (extracted.get("cgst", 0) or 0) + (extracted.get("sgst", 0) or 0) + (extracted.get("igst", 0) or 0)
        if gst == 0:
            gst = None
        payment_method = extracted.get("payment_method", "")

        # AI categorization using real OCR text
        ai_result = _ai_categorize_receipt(raw_text, caption, extracted)
        category = ai_result.get("category", "other")
        description = ai_result.get("description") or caption or f"Receipt from {vendor or 'unknown'}"

        if not amount and ai_result.get("amount"):
            amount = ai_result["amount"]
        if not vendor and ai_result.get("vendor"):
            vendor = ai_result["vendor"]

        cat_labels = {
            "flight": "Flight", "hotel": "Hotel", "food": "Food & Meals",
            "transport": "Local Transport", "visa": "Visa / Docs",
            "communication": "Communication", "other": "Other",
        }
        confident_categories = {"flight", "hotel", "food", "transport", "visa", "communication"}

        # Build response
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
        if description:
            lines.append(f"*Description:* {description}")

        # Auto-save if confident
        phone_key = f"cliq_{user.get('email', '')}"
        if category in confident_categories and amount:
            lines.append(f"\n*Category:* {cat_labels.get(category, category)} (auto-detected)")
            logger.info("[Cliq Bot] Saving expense: user_id=%s, category=%s, amount=%s, vendor=%s, date=%s, source=cliq",
                       user["id"], category, amount, vendor or "", date or "")
            saved = _save_expense(user["id"], category, description, amount, vendor or "", date or "", source="cliq")
            logger.info("[Cliq Bot] Expense save result: %s", saved)
            lines.append("")
            if saved:
                lines.append("Expense saved to your account.")
                logger.info("[Cliq Bot] Expense successfully saved for user %s", user["id"])
            else:
                lines.append("Could not save. Please submit on the app.")
                logger.warning("[Cliq Bot] Expense save failed for user %s", user["id"])
        elif amount:
            # Ask for category
            _pending_expenses[phone_key] = {
                "amount": amount, "vendor": vendor or "", "date": date or "",
                "description": description, "user_id": user["id"],
            }
            lines.append("\nSelect the category:")
            lines.append("\n1 - Flight\n2 - Hotel\n3 - Food & Meals\n4 - Local Transport\n5 - Visa / Docs\n6 - Communication\n7 - Other")
        else:
            lines.append("\nCould not extract amount. Type: expense 500 description")

        return "\n".join(lines)

    except Exception as exc:
        logger.exception("[Cliq Bot] Receipt processing failed: %s", exc)
        return "Error processing receipt. Please try again."


def _process_voice_note(file_url: str, file_type: str, user: dict, phone_key: str) -> str:
    """Download voice note from Cliq, transcribe via Gemini, process as text command."""
    try:
        from services.http_client import http as http_requests

        # Download audio
        resp = http_requests.get(file_url, timeout=15)
        if resp.status_code != 200:
            return "Could not download the voice note. Please try again."

        audio_bytes = resp.content
        if len(audio_bytes) < 500:
            return "Voice note too short. Please record a longer message."

        # Determine MIME type
        mime_map = {
            "ogg": "audio/ogg", "mp3": "audio/mpeg", "wav": "audio/wav",
            "m4a": "audio/mp4", "aac": "audio/aac", "opus": "audio/opus",
            "webm": "audio/webm", "amr": "audio/amr",
        }
        mime = "audio/ogg"
        if file_type and "/" in file_type:
            mime = file_type
        else:
            ext = file_url.rsplit(".", 1)[-1].lower().split("?")[0] if "." in file_url else ""
            mime = mime_map.get(ext, "audio/ogg")

        # Transcribe using Gemini
        from services.gemini_service import gemini
        if not gemini.configured:
            return (
                "Voice notes require GEMINI_API_KEY to be configured.\n"
                "Please type your message instead."
            )

        transcribed = gemini.transcribe_audio(audio_bytes, mime)
        if not transcribed:
            return (
                "Could not understand the voice note. Please try:\n"
                "- Speaking clearly and closer to the mic\n"
                "- Reducing background noise\n"
                "- Or type your message instead"
            )

        logger.info("[Cliq Bot] Voice transcribed: '%s'", transcribed[:100])

        # Process transcribed text as a regular message
        reply = _process_cliq_message(transcribed, user, phone_key)
        return f"*Voice:* _{transcribed}_\n\n{reply}"

    except Exception as exc:
        logger.exception("[Cliq Bot] Voice processing failed: %s", exc)
        return "Error processing voice note. Please type your message instead."


def _find_user_by_email(email: str) -> dict | None:
    """Look up user by email address with intelligent fallback."""
    if not email:
        logger.warning("[Cliq Bot] _find_user_by_email called with empty email")
        return None

    try:
        db = get_db()
        email_clean = email.lower().strip()

        # Try exact lowercase match first
        user = db.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email_clean,)).fetchone()

        if user:
            logger.info("[Cliq Bot] User found by email: %s (ID: %s)", email, user["id"])
            db.close()
            return dict(user)

        # Try partial match as fallback
        user = db.execute("SELECT * FROM users WHERE LOWER(email) LIKE ?", (f"%{email_clean}%",)).fetchone()

        if user:
            logger.info("[Cliq Bot] User found by partial email match: %s -> %s (ID: %s)", email, user["email"], user["id"])
            db.close()
            return dict(user)

        # Log all emails for debugging
        all_emails = db.execute("SELECT id, email FROM users WHERE email IS NOT NULL LIMIT 5").fetchall()
        logger.warning("[Cliq Bot] User NOT found for email: %s. Sample emails in DB: %s",
                      email, [dict(e)["email"] for e in all_emails])
        db.close()
        return None

    except Exception as e:
        logger.exception("[Cliq Bot] _find_user_by_email failed for %s: %s", email, e)
        return None


def _find_user_by_name(name: str) -> dict | None:
    """Look up user by full name (fallback)."""
    if not name:
        return None
    try:
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE full_name = ? OR name = ?", (name, name)).fetchone()
        db.close()
        return dict(user) if user else None
    except Exception:
        return None


@cliq_bot_bp.route("/bot", methods=["POST"])
def bot_handler():
    """POST /api/cliq/bot — handle messages from Zoho Cliq bot."""
    if not _verify_cliq_webhook():
        return jsonify({"success": False, "error": "Forbidden"}), 403

    # Cliq sends data as form-encoded OR JSON depending on invokeurl config
    data = request.get_json(silent=True)
    if not data:
        data = request.form.to_dict()
    if not data:
        # Try raw body
        try:
            import json
            data = json.loads(request.data.decode('utf-8'))
        except Exception:
            data = {}

    message = (data.get("message") or "").strip()
    user_name = data.get("user_name", "")
    user_email = data.get("user_email", "")
    chat_id = data.get("chat_id", "")
    file_url = data.get("file_url", "")
    file_name = data.get("file_name", "")
    file_type = data.get("file_type", "")

    logger.info("[Cliq Bot] Raw data: %s", dict(data))
    logger.info("[Cliq Bot] Message from %s (%s): '%s', file=%s", user_name, user_email, message[:80], bool(file_url))

    # Handle voice/audio attachments (transcribe → process as text)
    audio_exts = ('.ogg', '.mp3', '.wav', '.m4a', '.aac', '.opus', '.webm', '.amr')
    if file_url and ("audio" in file_type.lower() or file_name.lower().endswith(audio_exts)):
        user = _find_user_by_email(user_email) or _find_user_by_name(user_name)
        if not user:
            return jsonify({"text": "Your account is not linked. Please contact your admin."})
        reply = _process_voice_note(file_url, file_type, user, f"cliq_{user_email or user_name}")
        buttons = _get_context_buttons(reply, user)
        return jsonify({"text": reply, "suggestions": buttons})

    # Image/file attachments — direct user to web app for receipt scanning
    if file_url and ("image" in file_type.lower() or file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.pdf'))):
        return jsonify({
            "text": "*Receipt Upload*\n\nReceipt scanning via Cliq is not supported. Please use the TravelSync web app to upload receipts:\n\nGo to Expenses → Upload Receipt\n\nOr type *start expense* here to log an expense manually.",
            "suggestions": [{"text": "Start Expense"}, {"text": "Expenses"}, {"text": "Help"}],
        })

    if not message:
        return jsonify({
            "text": "Send me a message or type *help* to see what I can do.",
            "suggestions": [
                {"text": "My Trips"}, {"text": "Approvals"}, {"text": "Expenses"},
                {"text": "Meetings"}, {"text": "Help"}
            ]
        })

    # Find user in our DB
    user = _find_user_by_email(user_email) or _find_user_by_name(user_name)

    # If user not found and not asking for help, provide intelligent diagnostic
    if not user and message.lower() not in ("hi", "hello", "hey", "help", "start", "hii"):
        # Log detailed diagnostic
        logger.error(
            "[Cliq Bot] User lookup failed - Email: %s | Name: %s | Chat ID: %s",
            user_email, user_name, chat_id
        )

        return jsonify({
            "text": (
                "*Account Lookup Failed*\n\n"
                f"Could not find account for:\n"
                f"Email: {user_email}\n"
                f"Name: {user_name or 'Not provided'}\n\n"
                "*Possible reasons:*\n"
                "1. Email mismatch - Check your TravelSync account email\n"
                "2. Account not yet created in the system\n\n"
                "*Next steps:*\n"
                "Verify your email in TravelSync web app or contact your admin."
            ),
            "suggestions": [{"text": "Help"}, {"text": "Contact Admin"}]
        })

    try:
        phone_key = f"cliq_{user_email or user_name}"
        reply = _process_cliq_message(message, user, phone_key)

        # Build response with contextual buttons
        response = {"text": reply}
        buttons = _get_context_buttons(message, user)
        if buttons:
            response["suggestions"] = buttons

        return jsonify(response)

    except Exception as e:
        logger.exception("[Cliq Bot] Error processing message")
        return jsonify({"text": "Something went wrong. Please try again."})


def _get_context_buttons(message: str, user: dict | None) -> list:
    """Return contextual quick-reply buttons based on the message."""
    text = message.strip().lower()

    # Greetings / help → show main menu
    if text in ("hi", "hello", "hey", "help", "menu", "start", "hii", "?"):
        buttons = [
            {"text": "My Trips"}, {"text": "Approvals"}, {"text": "Expenses"},
            {"text": "Meetings"}, {"text": "Weather Mumbai"}, {"text": "Help"},
        ]
        if user and user.get("role") in ("admin", "manager"):
            buttons.insert(1, {"text": "Pending Approvals"})
        return buttons

    # After trips → offer related actions
    if text in ("1", "trips", "my trips", "2", "status", "trip status"):
        return [
            {"text": "Plan New Trip"}, {"text": "Approvals"}, {"text": "Expenses"}, {"text": "Help"},
        ]

    # After approvals
    if text in ("3", "approvals", "pending", "pending approvals"):
        return [
            {"text": "My Trips"}, {"text": "Expenses"}, {"text": "Meetings"}, {"text": "Help"},
        ]

    # After expenses
    if text in ("4", "expenses", "expense"):
        return [
            {"text": "Start Expense"}, {"text": "My Trips"}, {"text": "Help"},
        ]

    # After add expense prompt
    if "add" in text and "expense" in text or "submit" in text and "expense" in text or text in ("submit expense", "add expense"):
        return [
            {"text": "Start Expense"}, {"text": "My Trips"}, {"text": "Help"},
        ]

    # After meetings
    if text in ("5", "meetings", "meeting"):
        return [
            {"text": "My Trips"}, {"text": "Expenses"}, {"text": "Weather Mumbai"}, {"text": "Help"},
        ]

    # After weather
    if text.startswith("weather") or text.startswith("6"):
        return [
            {"text": "Weather Delhi"}, {"text": "Weather Bangalore"}, {"text": "My Trips"}, {"text": "Help"},
        ]

    # Expense category selection
    if text in ("upload receipt",):
        return [
            {"text": "Expense 500 Uber cab"}, {"text": "Expense 1200 Hotel stay"}, {"text": "Expense 350 Lunch"}, {"text": "Help"},
        ]

    # After plan trip
    if "plan" in text and "trip" in text:
        return [
            {"text": "My Trips"}, {"text": "Expenses"}, {"text": "Meetings"}, {"text": "Help"},
        ]

    # Expense flow — show category buttons or confirm buttons
    phone_key = f"cliq_{user.get('email', '') if user else ''}"
    if phone_key in _expense_flow:
        step = _expense_flow.get(phone_key, {}).get("step")
        if step == "category":
            return CATEGORY_BUTTONS
        if step == "confirm":
            return [{"text": "Yes"}, {"text": "No"}, {"text": "Cancel"}]
        if step == "amount":
            return [{"text": "Cancel"}]
        if step == "description":
            return [{"text": "Cancel"}]

    # Default — always show basic navigation
    return [
        {"text": "My Trips"}, {"text": "Expenses"}, {"text": "Submit Expense"}, {"text": "Help"},
    ]


def _process_cliq_message(body: str, user: dict | None, phone_key: str) -> str:
    """Process a Cliq bot message — similar to WhatsApp but adapted for Cliq."""
    from routes.whatsapp import (
        HELP_TEXT, WELCOME_TEXT,
        _get_user_trips, _get_pending_approvals, _get_expense_summary,
        _get_upcoming_meetings, _get_weather, _handle_approve_reject,
        _ai_chat, _handle_quick_expense,
        _add_to_history, _get_history, _clear_history,
        _pending_expenses, _categorize_text, _save_expense,
    )

    text = body.strip().lower()

    # Greetings
    greetings = ("hi", "hello", "hey", "start", "hii", "hiii", "yo", "sup")
    if text in greetings or text.startswith("hi ") or text.startswith("hello "):
        _clear_history(phone_key)
        if user:
            return f"Hello {user.get('full_name', 'there')}.\n\n" + HELP_TEXT
        return WELCOME_TEXT + "\n\nNote: Your account is not linked. Please contact your admin."

    if text in ("help", "menu", "?"):
        return HELP_TEXT

    if text in ("clear", "reset", "new", "new chat"):
        _clear_history(phone_key)
        _expense_flow.pop(phone_key, None)
        return "Conversation cleared. How can I help you?"

    # Cancel expense flow
    if text == "cancel" and phone_key in _expense_flow:
        _expense_flow.pop(phone_key)
        return "Expense submission cancelled."

    if not user:
        return (
            "*Account Not Linked*\n\n"
            "Your Cliq account is not connected to TravelSync Pro. "
            "Please ask your admin to add your email in the system."
        )

    # Check pending expense category
    if phone_key in _pending_expenses:
        cat_map = {"1": "flight", "2": "hotel", "3": "food", "4": "transport", "5": "visa", "6": "communication", "7": "other"}
        if text in cat_map:
            pending = _pending_expenses.pop(phone_key)
            category = cat_map[text]
            cat_labels = {"flight": "Flight", "hotel": "Hotel", "food": "Food & Meals", "transport": "Local Transport", "visa": "Visa / Docs", "communication": "Communication", "other": "Other"}
            logger.info("[Cliq Bot] Saving pending expense: user_id=%s, category=%s, amount=%s, vendor=%s, date=%s, source=cliq",
                       pending["user_id"], category, pending.get("amount"), pending.get("vendor", ""), pending.get("date", ""))
            saved = _save_expense(pending["user_id"], category, pending.get("description", ""), pending.get("amount"), pending.get("vendor", ""), pending.get("date", ""), source="cliq")
            logger.info("[Cliq Bot] Pending expense save result: %s", saved)
            if saved:
                logger.info("[Cliq Bot] Pending expense successfully saved for user %s", pending["user_id"])
                return f"*Expense Saved*\n\n*Amount:* Rs. {float(pending.get('amount', 0)):,.2f}\n*Category:* {cat_labels.get(category, category)}\n\nExpense added to your TravelSync account."
            logger.warning("[Cliq Bot] Pending expense save failed for user %s", pending["user_id"])
            return "Could not save. Please try on the web app."
        elif text in ("cancel", "skip"):
            _pending_expenses.pop(phone_key)
            return "Expense cancelled."

    # Guided expense submission flow
    if phone_key in _expense_flow:
        return _handle_expense_flow(phone_key, text, body, user)

    # Start guided expense flow — catch all expense-related intents
    expense_triggers = (
        "submit expense", "add expense", "new expense", "upload receipt",
        "log expense", "i want to add expense", "add an expense",
        "submit receipt", "scan receipt", "expense entry", "record expense",
    )
    if text in expense_triggers or (("expense" in text or "receipt" in text) and ("add" in text or "submit" in text or "log" in text or "upload" in text or "scan" in text or "want" in text)):
        if not user:
            return "*Account Not Linked*\n\nYour Cliq account is not connected to TravelSync.\n\nPlease contact your admin to link your account first."
        return (
            "*Add New Expense*\n\n"
            "Choose how you'd like to add:\n\n"
            "1. Type directly: expense 500 Uber cab to airport\n\n"
            "2. Guided step-by-step — tap *Start Expense* or type *start expense*\n\n"
            "To upload a receipt, use the TravelSync web app."
        )

    # Start step-by-step guided flow (from button, direct text, or "option 3")
    if text in ("start expense", "option 3", "guided", "step by step"):
        if not user:
            return "*Account Not Linked*\n\nYour Cliq account is not connected to TravelSync.\n\nPlease contact your admin to link your account."
        _expense_flow[phone_key] = {"step": "amount", "user_id": user["id"]}
        return "*Enter Expense Amount*\n\nEnter the amount in Rupees:\n\nExample: 500"

    # "Option 1" or "1" from add-expense menu — quick type entry
    if text in ("option 1",):
        return "*Quick Expense Entry*\n\nType: expense <amount> <description>\n\nExamples:\n  expense 500 Uber cab to airport\n  expense 1200 Hotel stay in Mumbai\n  expense 350 Lunch at client office"

    # "Option 2" — direct text entry info
    if text in ("option 2",):
        return "*Quick Expense Entry*\n\nType: expense <amount> <description>\n\nExamples:\n  expense 500 Uber cab to airport\n  expense 1200 Hotel stay in Mumbai\n  expense 350 Lunch at client office"

    # Commands
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
            "To send an SOS alert, use the TravelSync Pro app."
        )

    # Quick expense
    if text.startswith("expense ") or text.startswith("exp "):
        return _handle_quick_expense(user, body, phone_key)

    # Approve / reject travel requests
    if text.startswith("approve ") or text.startswith("reject "):
        parts = text.split(maxsplit=1)
        cmd = parts[0]
        rid = parts[1].strip().upper() if len(parts) > 1 else ""
        if not rid:
            return f"Usage: {cmd} TR-2026-XXXXXXX"
        return _handle_approve_reject(user, cmd, rid)

    # Approve / reject expenses
    from routes.whatsapp import _handle_expense_approve_reject, _get_pending_expense_approvals
    if text.startswith("approve-expense ") or text.startswith("reject-expense "):
        parts = text.split(maxsplit=1)
        cmd = parts[0]
        eid = parts[1].strip() if len(parts) > 1 else ""
        if not eid:
            return f"Usage: {cmd} <expense_id>"
        return _handle_expense_approve_reject(user, cmd, eid)

    # Pending expense approvals (for managers)
    if text in ("expense approvals", "pending expenses", "expense pending"):
        return _get_pending_expense_approvals(user["id"], user.get("role", "employee"))

    # Smart intent detection — word-level matching for natural language
    words = set(text.split())
    has = lambda *kws: all(any(kw in w for w in words) for kw in kws)

    # Expense queries
    if (has("expense") and any(w in text for w in ("pending", "approved", "rejected", "status", "show", "list", "detail", "how much", "how many", "total"))) \
       or ("expense" in text and ("my" in text or "all" in text)):
        summary = _get_expense_summary(user["id"])
        _add_to_history(phone_key, "user", body)
        _add_to_history(phone_key, "assistant", summary)
        return summary

    # Approval queries
    if (has("approval") and any(w in text for w in ("pending", "status", "how many", "how much", "show", "list", "my"))) \
       or ("pending" in text and "approval" in text) \
       or ("pending" in text and "approve" in text):
        if "expense" in text and user.get("role") in ("admin", "manager", "super_admin"):
            result = _get_pending_expense_approvals(user["id"], user.get("role", "employee"))
        else:
            result = _get_pending_approvals(user["id"], user.get("role", "employee"))
        _add_to_history(phone_key, "user", body)
        _add_to_history(phone_key, "assistant", result)
        return result

    # Trip queries
    if has("trip") or has("travel") and any(w in text for w in ("my", "status", "show", "list", "upcoming")):
        if any(w in text for w in ("my", "status", "show", "list", "upcoming", "recent")):
            result = _get_user_trips(user["id"])
            _add_to_history(phone_key, "user", body)
            _add_to_history(phone_key, "assistant", result)
            return result

    # Meeting queries
    if any(w in text for w in ("meeting", "meetings")) and any(w in text for w in ("my", "upcoming", "next", "client", "show", "list", "schedule")):
        result = _get_upcoming_meetings(user["id"])
        _add_to_history(phone_key, "user", body)
        _add_to_history(phone_key, "assistant", result)
        return result

    # Advanced query engine — handles complex natural language queries with date ranges
    if any(keyword in text for keyword in ("show", "list", "from", "in", "this", "last", "pending", "approved", "rejected")):
        try:
            from agents.query_engine import handle_query

            query_result = handle_query(user, body)

            if query_result and query_result.get("data", {}).get("success"):
                data = query_result["data"]
                query_type = query_result["type"]

                # Format response for Cliq
                if query_type == "expenses" and data.get("expenses"):
                    expenses = data["expenses"][:10]
                    lines = [f"*Your Expenses* ({data['scope']} scope)\n"]
                    lines.append(f"Total: {data['count']} items, ₹{data.get('total_amount', 0):,.0f}\n")
                    for exp in expenses:
                        cat = exp.get("category", "other")
                        amt = exp.get("invoice_amount") or exp.get("verified_amount") or exp.get("payment_amount") or 0
                        desc = exp.get("description", "")[:50]
                        date = exp.get("date", "")
                        source_icon = {"whatsapp": "💬", "cliq": "💼", "web": "🌐"}.get(exp.get("source"), "📝")
                        lines.append(f"{source_icon} Rs. {float(amt):,.0f} - {cat}")
                        if desc:
                            lines.append(f"  {desc}")
                        if date:
                            lines.append(f"  📅 {date}")
                        lines.append("")
                    _add_to_history(phone_key, "user", body)
                    _add_to_history(phone_key, "assistant", "\n".join(lines))
                    return "\n".join(lines)

                elif query_type == "trips" and data.get("trips"):
                    trips = data["trips"][:10]
                    lines = [f"*Your Trips* ({data['scope']} scope)\n"]
                    lines.append(f"Total: {data['count']} trips\n")
                    for trip in trips:
                        dest = trip.get("destination", "?")
                        origin = trip.get("origin", "?")
                        status = trip.get("status", "pending")
                        dates = f"{trip.get('start_date', '')} to {trip.get('end_date', '')}" if trip.get("start_date") else ""
                        lines.append(f"📍 {origin} → {dest}")
                        lines.append(f"  Status: {status}")
                        if dates:
                            lines.append(f"  📅 {dates}")
                        if trip.get("estimated_total"):
                            lines.append(f"  💰 Rs. {trip['estimated_total']:,.0f}")
                        lines.append("")
                    _add_to_history(phone_key, "user", body)
                    _add_to_history(phone_key, "assistant", "\n".join(lines))
                    return "\n".join(lines)

                elif query_type == "approvals" and data.get("approvals"):
                    approvals = data["approvals"][:10]
                    lines = [f"*Pending Approvals* ({data['role']} view)\n"]
                    lines.append(f"Total: {data['count']} approvals\n")
                    for appr in approvals:
                        requester = appr.get("requester_name", "Unknown")
                        dest = appr.get("destination", "?")
                        status = appr.get("status", "pending")
                        lines.append(f"👤 {requester} → {dest}")
                        lines.append(f"  Status: {status}")
                        if appr.get("start_date"):
                            lines.append(f"  📅 {appr['start_date']}")
                        if appr.get("estimated_total"):
                            lines.append(f"  💰 Rs. {appr['estimated_total']:,.0f}")
                        lines.append(f"  ID: {appr.get('request_id', '?')}")
                        lines.append("")
                    _add_to_history(phone_key, "user", body)
                    _add_to_history(phone_key, "assistant", "\n".join(lines))
                    return "\n".join(lines)

        except Exception as e:
            logger.warning("[Cliq Bot] Query engine failed: %s", e)
            # Continue to AI chat fallback

    # AI chat with memory and full DB context
    _add_to_history(phone_key, "user", body)
    reply = _ai_chat(user, body, phone_key)
    _add_to_history(phone_key, "assistant", reply)
    return reply


def _handle_expense_flow(phone_key: str, text: str, raw: str, user: dict) -> str:
    """Handle the step-by-step expense submission flow."""
    import time
    from routes.whatsapp import _save_expense, _categorize_text

    CAT_LABELS = {
        "flight": "Flight", "hotel": "Hotel", "food": "Food & Meals",
        "transport": "Local Transport", "visa": "Visa / Docs",
        "communication": "Communication", "other": "Other",
    }

    flow = _expense_flow.get(phone_key, {})
    step = flow.get("step")

    if text == "cancel":
        _expense_flow.pop(phone_key, None)
        return "Expense submission cancelled."

    # Step 1: Amount
    if step == "amount":
        cleaned = "".join(c for c in raw.strip() if c.isdigit() or c == ".")
        try:
            amount = float(cleaned)
            if amount <= 0 or amount > 1000000:
                return "Please enter a valid amount between 1 and 10,00,000.\n\nExample: 500"
            flow["amount"] = amount
            flow["step"] = "description"
            _expense_flow.set(phone_key, flow)
            return f"*Amount Set*\n\nRs. {amount:,.2f}\n\nNow describe the expense:\n\nExample: Uber cab to airport"
        except (ValueError, TypeError):
            return "Invalid amount. Please enter a number.\n\nExample: 500"

    # Step 2: Description
    if step == "description":
        if len(raw.strip()) < 2:
            return "Please enter a brief description.\n\nExample: Uber cab to airport"
        flow["description"] = raw.strip()
        auto_cat = _categorize_text(raw.strip())
        if auto_cat and auto_cat != "other":
            flow["category"] = auto_cat
            flow["step"] = "confirm"
            _expense_flow.set(phone_key, flow)
            return (
                f"*Expense Summary*\n\n"
                f"Amount: Rs. {flow['amount']:,.2f}\n"
                f"Description: {flow['description']}\n"
                f"Category: {CAT_LABELS.get(auto_cat, auto_cat)} (auto-detected)\n"
                f"Date: {time.strftime('%Y-%m-%d')}\n\n"
                f"Confirm and save?"
            )
        else:
            flow["step"] = "category"
            _expense_flow.set(phone_key, flow)
            return (
                f"Amount: Rs. {flow['amount']:,.2f}\n"
                f"Description: {flow['description']}\n\n"
                f"Select the category:"
            )

    # Step 3: Category (manual selection)
    if step == "category":
        cat = CATEGORY_MAP.get(text.lower())
        if not cat:
            return "Please select a valid category:\n\nFlight | Hotel | Food & Meals | Local Transport | Visa / Docs | Communication | Other"
        flow["category"] = cat
        flow["step"] = "confirm"
        _expense_flow.set(phone_key, flow)
        return (
            f"*Expense Summary*\n\n"
            f"Amount: Rs. {flow['amount']:,.2f}\n"
            f"Description: {flow['description']}\n"
            f"Category: {CAT_LABELS.get(cat, cat)}\n"
            f"Date: {time.strftime('%Y-%m-%d')}\n\n"
            f"Confirm and save? Reply *yes* to save or *no* to cancel"
        )

    # Step 4: Confirm
    if step == "confirm":
        if text in ("yes", "confirm", "save", "ok", "y", "submit"):
            logger.info("[Cliq Bot] Saving guided expense: user_id=%s, category=%s, amount=%s, description=%s, source=cliq",
                       flow["user_id"], flow["category"], flow["amount"], flow["description"])
            saved = _save_expense(
                flow["user_id"], flow["category"], flow["description"],
                flow["amount"], "", time.strftime("%Y-%m-%d"), source="cliq"
            )
            logger.info("[Cliq Bot] Guided expense save result: %s", saved)
            saved_amount = flow["amount"]
            saved_desc = flow["description"]
            saved_cat = CAT_LABELS.get(flow["category"], flow["category"])
            _expense_flow.pop(phone_key, None)
            if saved:
                logger.info("[Cliq Bot] Guided expense successfully saved for user %s", flow["user_id"])
                return (
                    f"*Expense Saved*\n\n"
                    f"Amount: Rs. {saved_amount:,.2f}\n"
                    f"Description: {saved_desc}\n"
                    f"Category: {saved_cat}\n\n"
                    f"Added to TravelSync Pro. Type *4* or *expenses* to view all."
                )
            logger.warning("[Cliq Bot] Guided expense save failed for user %s", flow.get("user_id"))
            return "*Save Failed*\n\nCouldn't save the expense. Please try on the web app or contact support."
        elif text in ("no", "cancel", "edit", "n"):
            _expense_flow.pop(phone_key, None)
            return "Expense cancelled. Type *start expense* to start again."
        else:
            return "Reply *yes* to save or *no* to cancel."

    # Unknown step — reset
    _expense_flow.pop(phone_key, None)
    return "Something went wrong. Type *start expense* to try again."
