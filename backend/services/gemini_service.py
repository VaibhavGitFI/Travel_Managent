"""
TravelSync Pro — Gemini AI Service
Uses Gemini 2.5 Pro (complex/chat) and 2.5 Flash (fast/vision/streaming).
Enterprise-grade with higher rate limits.
Falls back gracefully when GEMINI_API_KEY not set.

Enhanced with OTIS voice intelligence:
- Function calling for TravelSync actions
- Voice-optimized response formatting
- Proactive suggestions and context awareness
"""
import os
import json
import re
import logging
import time
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

GEMINI_MODELS = {
    "flash": "gemini-2.5-flash",
    "pro": "gemini-2.5-pro",
    "vision": "gemini-2.5-flash",
}


class GeminiService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
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
        Generate response with function calling support for OTIS.
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

    def generate_voice_optimized(
        self,
        prompt: str,
        context: Dict[str, Any] = None,
        conversation_history: List[Dict] = None,
        model_type: str = "flash"
    ) -> Optional[str]:
        """
        Generate a voice-optimized response for OTIS.
        Returns concise, natural speech without markdown.

        Args:
            prompt: User's voice command
            context: User context (name, role, recent trips, etc.)
            conversation_history: Previous turns in this session
            model_type: Model to use

        Returns:
            Natural speech response or None
        """
        if not self.configured:
            return None

        # Build voice-optimized system instruction
        system_instruction = self._build_otis_system_instruction(context)

        # Build messages with history
        messages = []
        if conversation_history:
            for turn in conversation_history[-5:]:  # Last 5 turns for context
                messages.append({
                    "role": "user",
                    "parts": [turn.get("user_input", "")]
                })
                messages.append({
                    "role": "model",
                    "parts": [turn.get("assistant_response", "")]
                })

        # Add current prompt
        messages.append({"role": "user", "parts": [prompt]})

        # Generate with history
        response = self.generate_with_history(
            system_instruction=system_instruction,
            messages=messages,
            model_type=model_type
        )

        if response:
            # Clean for voice output
            response = self._clean_for_voice(response)

        return response

    def _build_otis_system_instruction(self, context: Dict[str, Any] = None) -> str:
        """Build OTIS-specific system instruction."""
        ctx = context or {}
        user_name = ctx.get("user_name", "there")
        user_role = ctx.get("user_role", "user")

        # ── Live context summary ──────────────────────────────────────────────
        live_context = []
        if ctx.get("pending_expense_count", 0) > 0:
            live_context.append(
                f"{ctx['pending_expense_count']} pending expense(s) totalling "
                f"₹{ctx.get('pending_expense_total', 0):,.0f}"
            )
        if ctx.get("pending_approval_count", 0) > 0:
            live_context.append(f"{ctx['pending_approval_count']} trip request(s) awaiting your approval")
        if ctx.get("upcoming_meetings"):
            m = ctx["upcoming_meetings"][0]
            live_context.append(
                f"next meeting: {m.get('title','')} with {m.get('client_name','')} on {m.get('meeting_date','')}"
            )
        if ctx.get("recent_trips"):
            t = ctx["recent_trips"][0]
            live_context.append(
                f"latest trip request: {t.get('destination','')} — status {t.get('status','')}"
            )
        live_ctx_str = "\n".join(f"  • {l}" for l in live_context) if live_context else "  • No urgent items right now."

        instruction = f"""You are JARVIS, the intelligent voice assistant embedded inside TravelSync Pro — a corporate travel management platform used by Indian businesses.

## YOUR IDENTITY
- Name: Jarvis (Just A Rather Very Intelligent System)
- Personality: Professional, warm, efficient — like a trusted EA who knows the entire business
- Accent & tone: Clear Indian English — natural, confident, never robotic
- You are speaking to {user_name}, who is a {user_role} in their organisation

## TRAVELSYNC PRO — COMPLETE APP KNOWLEDGE
You have expert knowledge of every feature in TravelSync Pro:

**TRIP PLANNER** (/planner)
- AI-powered trip planning: flights, hotels, weather, packing lists, travel policy check
- Output: full itinerary with Amadeus flights, hotel options, weather forecast, checklist

**EXPENSE MANAGEMENT** (/expenses)
- Submit expenses with OCR receipt scanning (Google Vision API)
- Track status: draft → submitted → approved/rejected
- Categories: flights, hotels, meals, transport, client entertainment

**TRAVEL REQUESTS & APPROVALS** (/requests, /approvals)
- Employees raise travel requests; managers/admins approve or reject
- Workflow: draft → submitted → approved/rejected → completed

**CLIENT MEETINGS** (/meetings)
- Schedule and track client meetings linked to travel
- Source types: manual, email, WhatsApp, phone, calendar, LinkedIn

**ACCOMMODATION** (/accommodation)
- Search hotels via Amadeus Hotels API
- For stays 5+ days: suggests PG options (Stanza, NestAway, OYO Life, CoHo, Colive)

**ANALYTICS & REPORTS** (/analytics)
- KPI dashboard: total spend, trips, policy compliance score
- Spend breakdown by category, month, department

**CHAT AI** (/chat)
- Persistent chat with Gemini AI for any travel or business question
- Multi-session, markdown responses, voice input supported

**SOS EMERGENCY**
- One-tap SOS alert sent to manager with GPS location

**TRAVEL POLICY** (policy_agent)
- Auto-checks if trip budget/class/hotel tier is within company policy
- Flags violations before submission

**CURRENCY & WEATHER**
- Real-time currency conversion (Open Exchange Rates)
- City weather forecasts for travel dates (OpenWeatherMap)

## LIVE USER CONTEXT RIGHT NOW
{live_ctx_str}

## INTENT DETECTION — READ THIS CAREFULLY
Understand what the user really wants, even if phrased casually, indirectly, or in Indian English.
Map the request to the closest real TravelSync capability without inventing user intent.

## VOICE RESPONSE RULES — NON-NEGOTIABLE
1. **No markdown ever** — no asterisks, no hyphens, no hash symbols, no backticks
2. **Rupee amounts** — say "rupees" or "₹" followed by number: "twelve thousand rupees"
3. **Numbers** — spell small numbers: "three" not "3"; use digits for large: "12,450"
4. **Max 3 sentences** — unless user explicitly asks for a detailed report
5. **Always confirm actions** — "Done, I have approved John's Mumbai trip"
6. **Use Indian business English naturally** — "kindly", "as of now", "on priority"
7. **End with a helpful follow-up** — "Would you like me to do anything else?"
8. **If you cannot take an action** — explain clearly in one sentence and suggest the right page
9. **For live counts or summaries** — answer directly from the live TravelSync data you were given; do not tell the user to open a dashboard when the answer is already available

## CRITICAL
Your response goes directly to ElevenLabs text-to-speech. Write EXACTLY how it should sound when spoken aloud by a professional Indian voice assistant. No formatting. No lists. Natural sentences only."""

        return instruction

    def _clean_for_voice(self, text: str) -> str:
        """
        Clean text for natural voice output.
        Removes markdown, formats numbers, etc.
        """
        if not text:
            return text

        # Remove markdown formatting
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)      # Italic
        text = re.sub(r'`(.+?)`', r'\1', text)         # Code
        text = re.sub(r'#+\s*', '', text)              # Headers
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)  # Links

        # Remove bullet points and list markers
        text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

        # Convert common abbreviations to full words for speech
        text = re.sub(r'\bINR\b', 'rupees', text)
        text = re.sub(r'\bUSD\b', 'dollars', text)
        text = re.sub(r'\bkm\b', 'kilometers', text)
        text = re.sub(r'\bhr\b', 'hour', text)
        text = re.sub(r'\bhrs\b', 'hours', text)
        text = re.sub(r'\bmin\b', 'minutes', text)

        # Clean up extra whitespace
        text = re.sub(r'\n\n+', '\n', text)
        text = re.sub(r'  +', ' ', text)
        text = text.strip()

        return text

    def generate_proactive_suggestion(
        self,
        context: Dict[str, Any],
        model_type: str = "flash"
    ) -> Optional[str]:
        """
        Generate a proactive suggestion for the user based on context.
        Used when OTIS detects an opportunity to be helpful.

        Args:
            context: User context including pending tasks, trips, etc.
            model_type: Model to use

        Returns:
            Natural speech suggestion or None
        """
        if not self.configured:
            return None

        # Build prompt for proactive suggestion
        prompt = f"""Based on this user's current situation, suggest ONE helpful action OTIS can take:

User Context:
- Pending approvals: {context.get('pending_approvals_count', 0)}
- Upcoming trips in next 7 days: {context.get('upcoming_trips_count', 0)}
- Recent expenses awaiting approval: {context.get('pending_expenses_count', 0)}
- Unread notifications: {context.get('unread_notifications', 0)}

If there's an actionable suggestion, phrase it as a natural voice prompt.
If nothing urgent, return: "no_suggestion"

Your suggestion (one sentence):"""

        response = self.generate(prompt, model_type)

        if response and response.strip().lower() != "no_suggestion":
            return self._clean_for_voice(response)

        return None

    @property
    def is_available(self) -> bool:
        return self.configured


gemini = GeminiService()
