"""
TravelSync Pro — Gemini AI Service
Uses Gemini 2.5 Pro (complex/chat) and 2.5 Flash (fast/vision/streaming).
Enterprise-grade with higher rate limits.
Falls back gracefully when GEMINI_API_KEY not set.

"""
import os
import json
import re
import logging
import time
from typing import Dict, List, Optional, Any

from config import Config

logger = logging.getLogger(__name__)

GEMINI_MODELS = {
    "flash": "gemini-2.5-flash",
    "pro": "gemini-2.5-pro",
    "vision": "gemini-2.5-flash",
}


class GeminiService:
    def __init__(self):
        self.api_key = Config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        self.configured = bool(self.api_key)
        self._genai = None
        self._cooldown_until = 0.0
        self._last_quota_log_at = 0.0

        if self.configured:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._genai = genai
            except ImportError:
                logger.warning("google-generativeai not installed. Run: pip install google-generativeai")
                self.configured = False

    def _is_quota_error(self, message: str) -> bool:
        text = (message or "").lower()
        return "quota exceeded" in text or "429" in text

    def _enter_cooldown(self, message: str) -> None:
        retry_seconds = 60.0
        retry_match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", message, flags=re.IGNORECASE)
        if retry_match:
            retry_seconds = max(float(retry_match.group(1)), 15.0)
        else:
            seconds_match = re.search(r"retry_delay\s*\{\s*seconds:\s*([0-9]+)", message, flags=re.IGNORECASE)
            if seconds_match:
                retry_seconds = max(float(seconds_match.group(1)), 15.0)

        self._cooldown_until = time.time() + retry_seconds

        # Avoid spamming logs for every generation attempt while quota is exhausted.
        if time.time() - self._last_quota_log_at > 60:
            logger.warning("[Gemini] Quota exceeded. Cooling down API calls for %.0fs.", retry_seconds)
            self._last_quota_log_at = time.time()

    def get_model(self, model_type: str = "flash"):
        if not self.configured or not self._genai:
            return None
        try:
            return self._genai.GenerativeModel(GEMINI_MODELS.get(model_type, GEMINI_MODELS["flash"]))
        except Exception as e:
            logger.warning("[Gemini] Model init error: %s", e)
            return None

    def generate(self, prompt: str, model_type: str = "flash", system_instruction: str = None) -> str | None:
        """Generate text response from Gemini."""
        if not self.configured:
            return None
        if self._cooldown_until > time.time():
            return None
        try:
            model_name = GEMINI_MODELS.get(model_type, GEMINI_MODELS["flash"])
            if system_instruction:
                model = self._genai.GenerativeModel(model_name, system_instruction=system_instruction)
            else:
                model = self._genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_text = str(e)
            if self._is_quota_error(error_text):
                self._enter_cooldown(error_text)
                return None
            logger.warning("[Gemini] Generate error: %s", e)
            return None

    def generate_stream(self, prompt: str, system_instruction: str = None):
        """
        Stream text chunks from Gemini using the streaming API.
        Yields string chunks as they arrive.
        """
        if not self.configured or not self._genai:
            yield ""
            return
        if self._cooldown_until > time.time():
            yield ""
            return

        try:
            model_name = GEMINI_MODELS["flash"]
            if system_instruction:
                model = self._genai.GenerativeModel(model_name, system_instruction=system_instruction)
            else:
                model = self._genai.GenerativeModel(model_name)

            response = model.generate_content(prompt, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            error_text = str(e)
            if self._is_quota_error(error_text):
                self._enter_cooldown(error_text)
            logger.warning("[Gemini] Stream error: %s", e)
            return

    def generate_with_history(self, system_instruction: str, messages: list, model_type: str = "flash") -> str | None:
        """
        Generate a response using multi-turn chat history.
        messages: list of {"role": "user"|"model", "parts": [str]}
        """
        if not self.configured or not self._genai:
            return None
        if self._cooldown_until > time.time():
            return None
        try:
            model_name = GEMINI_MODELS.get(model_type, GEMINI_MODELS["flash"])
            model = self._genai.GenerativeModel(model_name, system_instruction=system_instruction)
            # Separate history from current message
            history = messages[:-1] if len(messages) > 1 else []
            current = messages[-1]["parts"][0] if messages else ""
            chat = model.start_chat(history=history)
            response = chat.send_message(current)
            return response.text
        except Exception as e:
            error_text = str(e)
            if self._is_quota_error(error_text):
                self._enter_cooldown(error_text)
                return None
            logger.warning("[Gemini] Chat history error: %s", e)
            return None

    def stream_with_history(self, system_instruction: str, messages: list):
        """
        Stream response using multi-turn chat history.
        Yields text chunks.
        """
        if not self.configured or not self._genai:
            yield ""
            return
        if self._cooldown_until > time.time():
            yield ""
            return
        try:
            model_name = GEMINI_MODELS["flash"]
            model = self._genai.GenerativeModel(model_name, system_instruction=system_instruction)
            history = messages[:-1] if len(messages) > 1 else []
            current = messages[-1]["parts"][0] if messages else ""
            chat = model.start_chat(history=history)
            response = chat.send_message(current, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            error_text = str(e)
            if self._is_quota_error(error_text):
                self._enter_cooldown(error_text)
            logger.warning("[Gemini] Stream history error: %s", e)
            return

    def generate_json(self, prompt: str, model_type: str = "flash") -> dict | None:
        """Generate and parse a JSON response."""
        full_prompt = prompt + "\n\nIMPORTANT: Respond with valid JSON only. No markdown, no explanation, just raw JSON."
        text = self.generate(full_prompt, model_type)
        if not text:
            return None
        try:
            # Strip markdown code fences if present
            clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
            return json.loads(clean)
        except (json.JSONDecodeError, ValueError):
            return None

    def analyze_image(self, image_path: str, prompt: str) -> str | None:
        """Analyze an image file using Gemini vision."""
        if not self.configured or not self._genai:
            return None
        if self._cooldown_until > time.time():
            return None
        try:
            import PIL.Image
            model = self._genai.GenerativeModel(GEMINI_MODELS["vision"])
            img = PIL.Image.open(image_path)
            response = model.generate_content([prompt, img])
            return response.text
        except Exception as e:
            error_text = str(e)
            if self._is_quota_error(error_text):
                self._enter_cooldown(error_text)
                return None
            logger.warning("[Gemini] Image analysis error: %s", e)
            return None

    def _format_otis_context_value(self, value: Any) -> str | None:
        """Convert context values into compact prompt-friendly text."""
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, list):
            if not value:
                return None
            items = []
            for item in value[:3]:
                formatted = self._format_otis_context_value(item)
                if formatted:
                    items.append(formatted)
            if not items:
                return None
            extra = len(value) - len(items)
            suffix = f" (+{extra} more)" if extra > 0 else ""
            return "; ".join(items) + suffix
        if isinstance(value, dict):
            compact = {
                k: v for k, v in value.items()
                if v not in (None, "", [], {})
            }
            if not compact:
                return None
            try:
                return json.dumps(compact, ensure_ascii=True, default=str, separators=(",", ":"))
            except TypeError:
                return str(compact)
        return str(value)

    def _build_otis_context_block(self, context: Dict[str, Any] | None) -> str:
        """Serialize OTIS context into a concise block for Gemini."""
        if not isinstance(context, dict) or not context:
            return ""

        preferred_order = [
            "user_name",
            "user_role",
            "user_email",
            "org_id",
            "pending_expense_count",
            "pending_expense_total",
            "total_expenses",
            "pending_approval_count",
            "recent_trips",
            "pending_approvals",
            "upcoming_meetings",
        ]
        keys = preferred_order + [k for k in context.keys() if k not in preferred_order]
        lines = []
        seen = set()

        for key in keys:
            if key in seen:
                continue
            seen.add(key)
            formatted = self._format_otis_context_value(context.get(key))
            if not formatted:
                continue
            label = key.replace("_", " ")
            lines.append(f"- {label}: {formatted}")

        return "\n".join(lines)

    def _normalize_otis_history(self, conversation_history: List[Dict[str, Any]] | None) -> List[Dict[str, str]]:
        """Normalize OTIS history into user/assistant pairs."""
        normalized = []
        for turn in conversation_history or []:
            if not isinstance(turn, dict):
                continue
            user_input = (
                turn.get("user_input")
                or turn.get("user")
                or turn.get("prompt")
                or ""
            ).strip()
            assistant_response = (
                turn.get("assistant_response")
                or turn.get("assistant")
                or turn.get("response")
                or ""
            ).strip()
            if not user_input and not assistant_response:
                continue
            normalized.append({
                "user_input": user_input,
                "assistant_response": assistant_response,
            })
        return normalized[-5:]

    def _build_otis_system_instruction(self, context: Dict[str, Any] | None = None) -> str:
        """System instruction for OTIS voice/text replies."""
        user_bits = []
        if isinstance(context, dict):
            user_name = (context.get("user_name") or "").strip()
            user_role = (context.get("user_role") or "").strip()
            if user_name:
                user_bits.append(f"You are speaking to {user_name}.")
            if user_role:
                user_bits.append(f"Their role is {user_role}.")

        user_context = " ".join(user_bits)
        return (
            "You are OTIS, a friendly, smart travel assistant who talks like a real person — "
            "warm, direct, and conversational, the way a knowledgeable colleague speaks, not a robot. "
            f"{user_context} "
            "Rules: plain text only — no markdown, bullets, headings, code blocks, or emojis. "
            "Use contractions (I've, you'll, it's, don't, let's). "
            "Keep voice replies compact and easy to listen to. "
            "When a request is broad, open-ended, or missing constraints, give a short helpful answer and then ask one short follow-up question instead of giving a long monologue. "
            "Only give a longer reply when the user clearly asks for depth or multiple examples. "
            "Sound natural: vary sentence length, start with the answer not a preamble, "
            "and never say 'Certainly!', 'Of course!', 'Sure thing!' or similar filler. "
            "You can answer any user question: TravelSync tasks, general knowledge, explanations, planning, writing help, "
            "productivity questions, and casual conversation. "
            "Use the TravelSync context whenever it is relevant to the question. "
            "If the question is outside TravelSync, answer it normally from general knowledge instead of refusing. "
            "Don't invent private TravelSync data that isn't in the context. "
            "Ask one short follow-up when something's unclear. "
            "TravelSync-specific strengths include hotel search, flights/trains/buses, weather, currency conversion, "
            "trip planning, travel requests, expenses, meetings, approvals, analytics, and SOS alerts."
        ).strip()

    def _build_otis_answer_instruction(self, prompt: str) -> str:
        """Match answer depth to the user's request without producing long spoken monologues."""
        prompt_lower = (prompt or "").strip().lower()

        broad_markers = (
            "what can you help me with", "what all can you do", "what can you do",
            "help me with", "best", "options", "ideas", "recommend", "suggest",
            "plan", "some jokes", "jokes options", "which is better", "what should i choose",
        )
        explicit_depth_markers = (
            "explain", "why", "how", "compare", "difference", "tell me more",
            "details", "walk me through", "what are", "what's the best",
            "pros and cons",
        )
        multi_example_markers = (
            "three jokes", "3 jokes", "five ideas", "5 ideas", "examples", "ways", "steps",
            "list", "compare", "pros and cons",
        )

        if any(marker in prompt_lower for marker in broad_markers):
            return (
                "Answer as OTIS in plain text suitable for speech. "
                "Give one short helpful answer, then ask exactly one short follow-up question to narrow the user's need. "
                "Keep the whole reply brief and avoid listing too many options at once."
            )

        if any(marker in prompt_lower for marker in explicit_depth_markers):
            if any(marker in prompt_lower for marker in multi_example_markers):
                return (
                    "Answer as OTIS in plain text suitable for speech. "
                    "Give a helpful answer with a few useful points or examples, but keep it easy to listen to."
                )
            return (
                "Answer as OTIS in plain text suitable for speech. "
                "Answer directly in two to four short sentences."
            )

        return (
            "Answer as OTIS in plain text suitable for speech. "
            "Keep it brief and natural."
        )

    def _clean_voice_response(self, text: str | None) -> str | None:
        """Remove markdown/noisy formatting while keeping text readable on screen."""
        if not text:
            return None

        cleaned = text.strip()
        cleaned = re.sub(r"```(?:[\w+-]+)?\s*", "", cleaned)
        cleaned = cleaned.replace("```", "")
        cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", cleaned)
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
        cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
        cleaned = re.sub(r"^\s*[-*•]+\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\n{2,}", ". ", cleaned)
        cleaned = re.sub(r"\n+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = re.sub(r"([.?!]){2,}", r"\1", cleaned)
        return cleaned.strip()

    def generate_voice_optimized(
        self,
        prompt: str,
        context: Dict[str, Any] | None = None,
        conversation_history: List[Dict[str, Any]] | None = None,
        model_type: str = "flash",
    ) -> str | None:
        """
        Generate a concise OTIS response suitable for both speech and UI display.
        Compatible with existing OTIS route and agent call sites.
        """
        if not prompt or not prompt.strip():
            return None
        if not self.configured or not self._genai:
            return None
        if self._cooldown_until > time.time():
            return None

        system_instruction = self._build_otis_system_instruction(context)
        context_block = self._build_otis_context_block(context)

        prompt_parts = []
        if context_block:
            prompt_parts.append("[TravelSync Context]\n" + context_block)
        prompt_parts.append("[User Request]\n" + prompt.strip())
        prompt_parts.append(self._build_otis_answer_instruction(prompt))
        current_message = "\n\n".join(prompt_parts)

        messages = []
        for turn in self._normalize_otis_history(conversation_history):
            if turn["user_input"]:
                messages.append({"role": "user", "parts": [turn["user_input"]]})
            if turn["assistant_response"]:
                messages.append({"role": "model", "parts": [turn["assistant_response"]]})
        messages.append({"role": "user", "parts": [current_message]})

        response_text = self.generate_with_history(
            system_instruction=system_instruction,
            messages=messages,
            model_type=model_type,
        )
        if not response_text:
            response_text = self.generate(
                current_message,
                model_type=model_type,
                system_instruction=system_instruction,
            )

        return self._clean_voice_response(response_text)

    def generate_travel_plan(self, destination: str, duration: int, purpose: str, preferences: dict) -> dict | None:
        """Generate a structured travel plan using Gemini Pro."""
        prompt = f"""
Create a detailed corporate travel plan for:
- Destination: {destination}
- Duration: {duration} days
- Purpose: {purpose}
- Budget: {preferences.get('budget', 'moderate')}
- Travelers: {preferences.get('num_travelers', 1)}

Return JSON with keys:
{{
  "day_plan": [{{"day": 1, "activities": [], "meals": [], "transport": ""}}],
  "key_tips": [],
  "local_etiquette": [],
  "safety_notes": [],
  "estimated_daily_budget_inr": 0
}}
"""
        return self.generate_json(prompt, "pro")

    def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str | None:
        """Transcribe audio bytes using Gemini multimodal. Returns transcribed text or None."""
        if not self.configured or not self._genai:
            return None
        if self._cooldown_until > time.time():
            return None
        import tempfile
        tmp_path = None
        uploaded_file = None
        try:
            # Gemini requires file upload for audio — write to temp file first
            ext_map = {
                "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/wav": ".wav",
                "audio/mp4": ".m4a", "audio/aac": ".aac", "audio/opus": ".opus",
                "audio/webm": ".webm", "audio/amr": ".amr",
            }
            suffix = ext_map.get(mime_type, ".ogg")
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp.flush()
                tmp_path = tmp.name

            uploaded_file = self._genai.upload_file(tmp_path, mime_type=mime_type)

            model = self._genai.GenerativeModel(GEMINI_MODELS["flash"])
            prompt = (
                "Transcribe this audio accurately. Return ONLY the spoken text, "
                "nothing else. If the audio is in Hindi or another Indian language, "
                "transliterate to English. If the audio is unclear or empty, return: [unclear]"
            )
            response = model.generate_content([prompt, uploaded_file])
            text = (response.text or "").strip()
            if not text or text == "[unclear]":
                return None
            return text
        except Exception as e:
            error_text = str(e)
            if self._is_quota_error(error_text):
                self._enter_cooldown(error_text)
                return None
            logger.warning("[Gemini] Audio transcription error: %s", e)
            return None
        finally:
            # Clean up temp file and uploaded file
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            if uploaded_file:
                try:
                    self._genai.delete_file(uploaded_file.name)
                except Exception:
                    pass

    def generate_with_functions(
        self,
        prompt: str,
        functions: List[Dict],
        system_instruction: str = None,
        model_type: str = "flash"
    ) -> Dict[str, Any]:
        """
        Generate response with function calling support.
        Returns dict with 'text' or 'function_call' fields.

        Args:
            prompt: User input
            functions: List of function definitions in Gemini format
            system_instruction: System prompt
            model_type: Model to use

        Returns:
            {
                "type": "text" | "function_call",
                "text": str (if type=text),
                "function_name": str (if type=function_call),
                "parameters": dict (if type=function_call)
            }
        """
        if not self.configured or not self._genai:
            return {"type": "text", "text": None}
        if self._cooldown_until > time.time():
            return {"type": "text", "text": None}

        try:
            model_name = GEMINI_MODELS.get(model_type, GEMINI_MODELS["flash"])

            # Build tools specification
            tools = []
            for func in functions:
                tool = {
                    "function_declarations": [{
                        "name": func["name"],
                        "description": func["description"],
                        "parameters": func.get("parameters", {})
                    }]
                }
                tools.append(tool)

            # Create model with tools
            if system_instruction:
                model = self._genai.GenerativeModel(
                    model_name,
                    system_instruction=system_instruction,
                    tools=tools
                )
            else:
                model = self._genai.GenerativeModel(model_name, tools=tools)

            response = model.generate_content(prompt)

            # Check if model wants to call a function
            if hasattr(response.candidates[0].content, 'parts'):
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call'):
                        fc = part.function_call
                        return {
                            "type": "function_call",
                            "function_name": fc.name,
                            "parameters": dict(fc.args) if fc.args else {}
                        }

            # Regular text response
            return {
                "type": "text",
                "text": response.text
            }

        except Exception as e:
            error_text = str(e)
            if self._is_quota_error(error_text):
                self._enter_cooldown(error_text)
                return {"type": "text", "text": None}
            logger.warning("[Gemini] Function calling error: %s", e)
            return {"type": "text", "text": None}

    @property
    def is_available(self) -> bool:
        return self.configured


gemini = GeminiService()
