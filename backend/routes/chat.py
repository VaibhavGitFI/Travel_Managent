"""
TravelSync Pro — AI Chat Routes
Gemini 2.0 Flash powered travel assistant with intent detection and action cards.
"""
import json
import os
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, Response, stream_with_context
from werkzeug.utils import secure_filename
from auth import get_current_user
from extensions import limiter
from agents.chat_agent import (
    process_message,
    build_system_prompt,
    _detect_intent,
    _extract_entities,
    _build_action_cards,
    _enrich_reply,
    _pattern_reply,
    _get_recent_history,
)
from services.anthropic_service import claude
from services.gemini_service import gemini
from database import get_db
from config import Config
from services.vision_service import vision

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")
logger = logging.getLogger(__name__)


def _request_payload():
    is_multipart = request.content_type and "multipart/form-data" in request.content_type
    if is_multipart:
        message = request.form.get("message", "").strip()
        raw_context = request.form.get("context", "{}")
        try:
            context = json.loads(raw_context) if raw_context else {}
            if not isinstance(context, dict):
                context = {}
        except json.JSONDecodeError:
            context = {}
        upload = request.files.get("file")
        return message, context, upload

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    return message, context, None


def _extract_attachment(file_path: str, filename: str) -> dict:
    ext = os.path.splitext(filename)[1].lower()
    out = {"filename": filename, "kind": ext.lstrip(".") or "file"}

    if ext in {".png", ".jpg", ".jpeg", ".gif", ".pdf"}:
        ocr = vision.extract_receipt_data(file_path)
        extracted = ocr.get("extracted", {}) if isinstance(ocr, dict) else {}
        summary_bits = []
        if extracted.get("amount"):
            summary_bits.append(f"Amount: {extracted['amount']}")
        if extracted.get("vendor"):
            summary_bits.append(f"Vendor: {extracted['vendor']}")
        if extracted.get("date"):
            summary_bits.append(f"Date: {extracted['date']}")
        if extracted.get("invoice_number"):
            summary_bits.append(f"Invoice: {extracted['invoice_number']}")

        out["ocr"] = ocr
        out["summary"] = "; ".join(summary_bits) or ocr.get("note") or "Attachment processed"
        return out

    if ext in {".txt", ".md", ".csv", ".json"}:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read(4000)
        out["text_preview"] = text
        out["summary"] = f"Text attachment preview ({len(text)} chars): {text[:500]}"
        return out

    out["summary"] = "Attachment uploaded. File type not parsed for text extraction."
    return out


def _insert_chat_message(db, user_id: int, role: str, content: str, intent: str = None, action_cards=None):
    cols = {r[1] for r in db.execute("PRAGMA table_info(chat_messages)").fetchall()}
    values = {"user_id": user_id, "role": role, "content": content}
    if "intent" in cols and intent is not None:
        values["intent"] = intent
    if "action_card_json" in cols and action_cards is not None:
        values["action_card_json"] = json.dumps(action_cards)

    keys = list(values.keys())
    placeholders = ",".join("?" for _ in keys)
    db.execute(
        f"INSERT INTO chat_messages ({','.join(keys)}) VALUES ({placeholders})",
        tuple(values[k] for k in keys),
    )


@chat_bp.route("", methods=["POST"])
@limiter.limit("30 per minute")
def chat():
    """POST /api/chat — send a message to the AI travel assistant."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    message, context, upload = _request_payload()
    if not message and not upload:
        return jsonify({"success": False, "error": "message or attachment is required"}), 400

    try:
        original_message = message
        if upload:
            if not upload.filename:
                return jsonify({"success": False, "error": "Attachment filename is empty"}), 400
            if not Config.allowed_file(upload.filename):
                return jsonify({
                    "success": False,
                    "error": f"File type not allowed. Allowed: {', '.join(sorted(Config.ALLOWED_EXTENSIONS))}",
                }), 400

            os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
            safe_name = secure_filename(upload.filename)
            stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
            file_path = os.path.join(Config.UPLOAD_FOLDER, stored_name)
            upload.save(file_path)

            attachment = _extract_attachment(file_path, safe_name)
            attachment["url"] = f"/api/uploads/{stored_name}"
            context = {**context, "attachment": attachment}

            if not message:
                message = "Please analyze this attachment and help me with travel actions."
            if attachment.get("summary"):
                message = f"{message}\n\nAttachment context: {attachment['summary']}"

        result = process_message(message, user=user, context=context)
        reply = result.get("reply", "")
        result["message"] = reply
        result["response"] = reply

        # Persist message + reply to chat_messages table
        db = get_db()
        try:
            user_content = original_message or "Sent an attachment"
            _insert_chat_message(db, user["id"], "user", user_content, result.get("intent", "general"))
            _insert_chat_message(
                db,
                user["id"],
                "assistant",
                reply,
                result.get("intent", "general"),
                result.get("action_cards"),
            )
            db.commit()
        except Exception as persist_err:
            logger.warning("[Chat] Failed to persist chat messages: %s", persist_err)
        finally:
            db.close()

        return jsonify({"success": True, **result}), 200
    except Exception as e:
        logger.exception("[Chat] chat endpoint failed")
        return jsonify({"success": False, "error": "Failed to process message"}), 500


@chat_bp.route("/stream", methods=["POST"])
@limiter.limit("30 per minute")
def chat_stream():
    """POST /api/chat/stream — progressive SSE streaming of AI response."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    context = data.get("context") if isinstance(data.get("context"), dict) else {}

    if not message:
        return jsonify({"success": False, "error": "message is required"}), 400

    intent = _detect_intent(message)
    entities = _extract_entities(message, context=context)
    action_cards = _build_action_cards(intent, entities)

    # Run orchestrator for plan_trip intent with destination (before streaming)
    trip_results = None
    if intent == "plan_trip" and entities.get("destination"):
        try:
            from agents.orchestrator import plan_trip
            from agents.chat_agent import _summarize_trip_results
            trip_input = {
                "destination": entities["destination"],
                "origin": entities.get("origin") or "",
                "duration_days": 3,
                "purpose": "business",
                "user_id": user.get("id", 1),
            }
            raw = plan_trip(trip_input)
            if raw.get("success"):
                trip_results = _summarize_trip_results(raw)
        except Exception as e:
            logger.warning("[Chat Stream] Orchestrator call failed: %s", e)

    full_system_prompt = build_system_prompt(user)

    # Build multi-turn history (Anthropic format: role/content)
    history = _get_recent_history(user["id"], limit=6) if user.get("id") else []

    accumulated = []

    def generate():
        ai_powered = False
        model_used = None

        # ── 1. Stream via Claude (Anthropic) ──────────────────────
        if claude.is_available:
            from agents.chat_agent import _history_for_gemini  # noqa: reuse helper
            for chunk in claude.stream(message, system=full_system_prompt, history=history):
                accumulated.append(chunk)
                yield f"data: {json.dumps({'token': chunk})}\n\n"
            if accumulated:
                ai_powered = True
                model_used = "claude-opus-4-6"

        # ── 2. Fallback to Gemini ─────────────────────────────────
        if not accumulated and gemini.is_available:
            gemini_history = [
                {"role": "model" if h["role"] == "assistant" else "user",
                 "parts": [h["content"]]}
                for h in history
            ]
            gemini_history.append({"role": "user", "parts": [message]})
            for chunk in gemini.stream_with_history(full_system_prompt, gemini_history):
                accumulated.append(chunk)
                yield f"data: {json.dumps({'token': chunk})}\n\n"
            if accumulated:
                ai_powered = True
                model_used = "gemini-2.0-flash"

        full_reply = "".join(accumulated)

        if not full_reply:
            # Both unavailable — pattern fallback
            full_reply = _pattern_reply(message, intent, entities)
            yield f"data: {json.dumps({'token': full_reply})}\n\n"

        enriched = _enrich_reply(full_reply, intent, entities)
        extra = enriched[len(full_reply):]
        if extra:
            yield f"data: {json.dumps({'token': extra})}\n\n"

        # Persist user message + assistant reply
        db = None
        try:
            db = get_db()
            _insert_chat_message(db, user["id"], "user", message, intent)
            _insert_chat_message(db, user["id"], "assistant", enriched, intent, action_cards)
            db.commit()
        except Exception as persist_err:
            logger.warning("[Chat Stream] Persist error: %s", persist_err)
        finally:
            if db:
                db.close()

        done_event = {'done': True, 'action_cards': action_cards, 'intent': intent, 'ai_powered': ai_powered, 'model': model_used}
        if trip_results:
            done_event['trip_results'] = trip_results
        yield f"data: {json.dumps(done_event)}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@chat_bp.route("/history", methods=["GET"])
def history():
    """GET /api/chat/history — return recent chat messages for the current user."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    limit = min(int(request.args.get("limit", 50)), 200)

    try:
        db = get_db()
        cols = {r[1] for r in db.execute("PRAGMA table_info(chat_messages)").fetchall()}
        select_cols = ["id", "role", "content", "created_at"]
        if "intent" in cols:
            select_cols.append("intent")
        if "action_card_json" in cols:
            select_cols.append("action_card_json")

        rows = db.execute(
            f"""SELECT {', '.join(select_cols)}
                FROM chat_messages
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?""",
            (user["id"], limit),
        ).fetchall()

        messages = []
        for r in reversed(rows):
            item = dict(r)
            if "action_card_json" in item and item["action_card_json"]:
                try:
                    item["action_cards"] = json.loads(item["action_card_json"])
                except json.JSONDecodeError:
                    item["action_cards"] = []
            messages.append(item)

        db.close()
        return jsonify({"success": True, "messages": messages, "total": len(messages)}), 200
    except Exception as e:
        logger.exception("[Chat] history endpoint failed")
        return jsonify({"success": False, "error": "Failed to load chat history"}), 500


@chat_bp.route("/history", methods=["DELETE"])
def clear_history():
    """DELETE /api/chat/history — delete all chat messages for the current user."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    try:
        db = get_db()
        db.execute("DELETE FROM chat_messages WHERE user_id = ?", (user["id"],))
        db.commit()
        db.close()
        return jsonify({"success": True}), 200
    except Exception as e:
        logger.exception("[Chat] clear history failed")
        return jsonify({"success": False, "error": "Failed to clear history"}), 500
