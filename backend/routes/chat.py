"""
TravelSync Pro — AI Chat Routes
Production-grade chat with session management, streaming, and multi-turn context.
"""
import json
import os
import uuid
import logging
from datetime import date, datetime
from flask import Blueprint, request, jsonify, Response, stream_with_context
from werkzeug.utils import secure_filename
from auth import get_current_user
from extensions import limiter
from agents.chat_agent import (
    process_message,
    build_system_prompt,
    format_structured_chat_response,
    _detect_intent,
    _extract_entities,
    _build_action_cards,
    _enrich_reply,
    _pattern_reply,
    _get_recent_history,
)
from agents.query_engine import handle_query, should_use_structured_query
from services.anthropic_service import claude
from services.gemini_service import gemini
from database import get_db, table_columns
from config import Config
from services.vision_service import vision

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")
logger = logging.getLogger(__name__)


def _gen_session_id():
    return f"cs-{uuid.uuid4().hex[:12]}"


def _auto_title(message: str) -> str:
    """Generate a short title from the first user message."""
    # Try AI-generated title (non-blocking, fallback to truncation)
    try:
        if gemini.configured:
            title = gemini.generate(
                f"Generate a 3-6 word title for this chat message. Return ONLY the title, no quotes:\n\n{message[:200]}",
                model_type="flash",
            )
            if title and len(title.strip()) < 60:
                return title.strip().strip('"\'')
    except Exception:
        pass
    # Fallback: first 50 chars
    clean = message.strip().replace("\n", " ")
    return clean[:50] + ("..." if len(clean) > 50 else "")


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
        session_id = request.form.get("session_id")
        return message, context, upload, session_id

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    session_id = data.get("session_id")
    return message, context, None, session_id


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


def _insert_chat_message(db, user_id: int, role: str, content: str, intent: str = None, action_cards=None, session_id: str = None):
    cols = table_columns(db, "chat_messages")
    values = {"user_id": user_id, "role": role, "content": content}
    if "intent" in cols and intent is not None:
        values["intent"] = intent
    if "action_card_json" in cols and action_cards is not None:
        values["action_card_json"] = json.dumps(action_cards)
    if "session_id" in cols and session_id is not None:
        values["session_id"] = session_id

    keys = list(values.keys())
    placeholders = ",".join("?" for _ in keys)
    db.execute(
        f"INSERT INTO chat_messages ({','.join(keys)}) VALUES ({placeholders})",
        tuple(values[k] for k in keys),
    )


def _persist_chat_exchange(user_id: int, session_id: str, message: str, reply: str, intent: str, action_cards=None):
    db = None
    try:
        db = get_db()
        _insert_chat_message(db, user_id, "user", message, intent, session_id=session_id)
        _insert_chat_message(db, user_id, "assistant", reply, intent, action_cards, session_id=session_id)
        msg_count = db.execute("SELECT COUNT(*) as cnt FROM chat_messages WHERE session_id = ?", (session_id,)).fetchone()
        cnt = msg_count["cnt"] if isinstance(msg_count, dict) else msg_count[0]
        if cnt <= 2:
            title = _auto_title(message)
            db.execute("UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (title, session_id))
        else:
            db.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
        db.commit()
    finally:
        if db:
            db.close()


def _json_safe(value):
    """Recursively convert stream payloads into JSON-safe values."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


@chat_bp.route("", methods=["POST"])
@limiter.limit("30 per minute")
def chat():
    """POST /api/chat — send a message to the AI travel assistant."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    message, context, upload, session_id = _request_payload()
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

        # Auto-create session if not provided
        if not session_id:
            session_id = _gen_session_id()
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO chat_sessions (id, user_id, title) VALUES (?, ?, ?)",
                    (session_id, user["id"], "New Chat"),
                )
                db.commit()
                db.close()
            except Exception:
                pass

        result = process_message(message, user=user, context=context, session_id=session_id)
        reply = result.get("reply", "")
        result["message"] = reply
        result["response"] = reply
        result["session_id"] = session_id

        # Persist message + reply
        try:
            user_content = original_message or "Sent an attachment"
            _persist_chat_exchange(
                user["id"],
                session_id,
                user_content,
                reply,
                result.get("intent", "general"),
                result.get("action_cards"),
            )
        except Exception as persist_err:
            logger.warning("[Chat] Failed to persist chat messages: %s", persist_err)

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
    session_id = data.get("session_id")

    if not message:
        return jsonify({"success": False, "error": "message is required"}), 400

    # Auto-create session if not provided
    if not session_id:
        session_id = _gen_session_id()
        try:
            db = get_db()
            db.execute("INSERT INTO chat_sessions (id, user_id, title) VALUES (?, ?, ?)", (session_id, user["id"], "New Chat"))
            db.commit()
            db.close()
        except Exception:
            pass

    intent = _detect_intent(message)
    entities = _extract_entities(message, context=context)
    action_cards = _build_action_cards(intent, entities)

    try:
        if should_use_structured_query(message):
            query_result = handle_query(user, message, strict=True)
            structured_result = format_structured_chat_response(query_result, entities)
        else:
            structured_result = None
    except Exception as e:
        logger.warning("[Chat Stream] Query engine failed: %s", e)
        structured_result = None

    if structured_result:
        reply = structured_result.get("reply", "")
        stream_intent = structured_result.get("intent", intent)
        stream_action_cards = structured_result.get("action_cards", action_cards)

        def generate_structured():
            yield f"data: {json.dumps({'token': reply})}\n\n"
            try:
                _persist_chat_exchange(
                    user["id"],
                    session_id,
                    message,
                    reply,
                    stream_intent,
                    stream_action_cards,
                )
            except Exception as persist_err:
                logger.warning("[Chat Stream] Persist error: %s", persist_err)

            done_event = {
                "done": True,
                "action_cards": stream_action_cards,
                "intent": stream_intent,
                "ai_powered": True,
                "model": structured_result.get("model", "structured_query"),
                "data_source": structured_result.get("data_source", "structured_query"),
                "session_id": session_id,
                "query_data": structured_result.get("query_data"),
            }
            yield f"data: {json.dumps(_json_safe(done_event))}\n\n"

        return Response(
            stream_with_context(generate_structured()),
            content_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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

    # Build multi-turn history scoped to session
    history = _get_recent_history(user["id"], limit=20, session_id=session_id) if user.get("id") else []

    # Enrich message with web search results (same as process_message)
    enriched_message = message
    try:
        from services.search_service import search
        if search.configured and intent in ("plan_trip", "search_flight", "search_hotel", "weather", "general"):
            destination = entities.get("destination", "")
            if intent == "search_flight" and destination:
                results = search.search_flights(entities.get("origin") or "India", destination, entities.get("date") or "")
            elif intent == "search_hotel" and destination:
                results = search.search_hotels(destination)
            else:
                results = search.search_travel(message[:120])
            ctx = search.format_for_prompt(results)
            if ctx:
                enriched_message = f"{message}\n\n{ctx}"
    except Exception as e:
        logger.warning("[Chat Stream] Search enrichment failed: %s", e)

    accumulated = []

    def generate():
        ai_powered = False
        model_used = None

        # ── 1. Stream via Claude (Anthropic) ──────────────────────
        if claude.is_available:
            for chunk in claude.stream(enriched_message, system=full_system_prompt, history=history):
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
            gemini_history.append({"role": "user", "parts": [enriched_message]})
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
        try:
            _persist_chat_exchange(user["id"], session_id, message, enriched, intent, action_cards)
        except Exception as persist_err:
            logger.warning("[Chat Stream] Persist error: %s", persist_err)

        done_event = {'done': True, 'action_cards': action_cards, 'intent': intent, 'ai_powered': ai_powered, 'model': model_used, 'session_id': session_id}
        if trip_results:
            done_event['trip_results'] = trip_results
        yield f"data: {json.dumps(_json_safe(done_event))}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@chat_bp.route("/transcribe", methods=["POST"])
@limiter.limit("20 per minute")
def transcribe_audio():
    """POST /api/chat/transcribe — transcribe an audio file using Gemini."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    upload = request.files.get("audio")
    if not upload or not upload.filename:
        return jsonify({"success": False, "error": "Audio file is required"}), 400

    ext = os.path.splitext(upload.filename)[1].lower().lstrip(".")
    allowed_audio = {"ogg", "mp3", "wav", "m4a", "webm", "aac", "opus", "amr"}
    if ext not in allowed_audio:
        return jsonify({"success": False, "error": f"Audio type .{ext} not supported"}), 400

    try:
        audio_bytes = upload.read()
        if len(audio_bytes) < 500:
            return jsonify({"success": False, "error": "Audio too short"}), 400

        mime_map = {
            "ogg": "audio/ogg", "mp3": "audio/mpeg", "wav": "audio/wav",
            "m4a": "audio/mp4", "aac": "audio/aac", "opus": "audio/opus",
            "webm": "audio/webm", "amr": "audio/amr",
        }
        mime = mime_map.get(ext, "audio/ogg")

        if not gemini.configured:
            return jsonify({"success": False, "error": "Voice transcription requires Gemini API key"}), 503

        text = gemini.transcribe_audio(audio_bytes, mime)
        if not text:
            return jsonify({"success": False, "error": "Could not transcribe audio. Try speaking more clearly."}), 422

        return jsonify({"success": True, "text": text}), 200
    except Exception as e:
        logger.exception("[Chat] Transcribe failed")
        return jsonify({"success": False, "error": "Transcription failed"}), 500


@chat_bp.route("/history", methods=["GET"])
def history():
    """GET /api/chat/history?session_id=X — messages for a session (or all if omitted)."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    session_id = request.args.get("session_id")
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except (ValueError, TypeError):
        limit = 50

    try:
        db = get_db()
        cols = table_columns(db, "chat_messages")
        select_cols = ["id", "role", "content", "created_at"]
        if "intent" in cols:
            select_cols.append("intent")
        if "action_card_json" in cols:
            select_cols.append("action_card_json")
        if "session_id" in cols:
            select_cols.append("session_id")

        if session_id:
            rows = db.execute(
                f"SELECT {', '.join(select_cols)} FROM chat_messages WHERE user_id = ? AND session_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                (user["id"], session_id, limit),
            ).fetchall()
        else:
            rows = db.execute(
                f"SELECT {', '.join(select_cols)} FROM chat_messages WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
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
    except Exception:
        logger.exception("[Chat] history endpoint failed")
        return jsonify({"success": False, "error": "Failed to load chat history"}), 500


# ── Session CRUD ───────────────────────────────────────────────────────────────

@chat_bp.route("/sessions", methods=["GET"])
def list_sessions():
    """GET /api/chat/sessions — list all chat sessions for the current user."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    try:
        db = get_db()
        rows = db.execute(
            "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT 50",
            (user["id"],),
        ).fetchall()
        db.close()
        sessions = [dict(r) for r in rows]
        return jsonify({"success": True, "sessions": sessions}), 200
    except Exception:
        logger.exception("[Chat] list sessions failed")
        return jsonify({"success": True, "sessions": []}), 200


@chat_bp.route("/sessions", methods=["POST"])
def create_session():
    """POST /api/chat/sessions — create a new chat session."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    data = request.get_json(silent=True) or {}
    title = data.get("title", "New Chat")
    sid = _gen_session_id()
    try:
        db = get_db()
        db.execute(
            "INSERT INTO chat_sessions (id, user_id, title) VALUES (?, ?, ?)",
            (sid, user["id"], title),
        )
        db.commit()
        session = {"id": sid, "title": title, "created_at": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat()}
        db.close()
        return jsonify({"success": True, "session": session}), 201
    except Exception:
        logger.exception("[Chat] create session failed")
        return jsonify({"success": False, "error": "Failed to create session"}), 500


@chat_bp.route("/sessions/<session_id>", methods=["PATCH"])
def rename_session(session_id):
    """PATCH /api/chat/sessions/:id — rename a session."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"success": False, "error": "Title is required"}), 400
    try:
        db = get_db()
        db.execute("UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?", (title, session_id, user["id"]))
        db.commit()
        db.close()
        return jsonify({"success": True}), 200
    except Exception:
        logger.exception("[Chat] rename session failed")
        return jsonify({"success": False, "error": "Failed to rename session"}), 500


@chat_bp.route("/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    """DELETE /api/chat/sessions/:id — delete a session and its messages."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    try:
        db = get_db()
        db.execute("DELETE FROM chat_messages WHERE session_id = ? AND user_id = ?", (session_id, user["id"]))
        db.execute("DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user["id"]))
        db.commit()
        db.close()
        return jsonify({"success": True}), 200
    except Exception:
        logger.exception("[Chat] delete session failed")
        return jsonify({"success": False, "error": "Failed to delete session"}), 500
