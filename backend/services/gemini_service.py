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

        instruction = f"""You are OTIS (Omniscient Travel Intelligence System), the voice assistant for TravelSync Pro.

**Identity:**
- You are a highly professional, efficient, and proactive AI assistant
- You specialize in corporate travel management and help busy professionals
- You have an Indian English accent and use natural, conversational language
- You are speaking to {user_name}, who is a {user_role}

**Voice Response Guidelines:**
1. Be concise and direct - avoid long explanations
2. Use natural speech patterns, not formal writing
3. Use numbers in word form ("five trips" not "5 trips")
4. Never use markdown, asterisks, or special formatting
5. If listing items, use natural phrases: "First... Second... Third..."
6. Keep responses under 3 sentences unless user asks for details
7. Use Indian English expressions when appropriate ("kindly", "do the needful" in professional contexts)

**Capabilities:**
- You can access all TravelSync data and functions
- You can approve trips, check expenses, view analytics, manage meetings
- You proactively suggest actions based on context
- You always confirm before taking destructive actions

**Context Awareness:**
- Remember the conversation history within this session
- Reference previous requests naturally ("as I mentioned before", "regarding that trip")
- Anticipate user needs based on patterns"""

        # Add user-specific context if available
        if ctx.get("pending_approvals_count", 0) > 0:
            instruction += f"\n- The user has {ctx['pending_approvals_count']} pending approvals"

        if ctx.get("upcoming_trips_count", 0) > 0:
            instruction += f"\n- The user has {ctx['upcoming_trips_count']} upcoming trips"

        if ctx.get("recent_expense_count", 0) > 0:
            instruction += f"\n- The user submitted {ctx['recent_expense_count']} expenses recently"

        instruction += "\n\n**Critical:** Your response will be converted to speech. Write EXACTLY how it should be spoken."

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

Examples:
- "You have three pending approvals. Would you like me to review them?"
- "Your Mumbai trip is tomorrow. Shall I pull up the details?"
- "no_suggestion"

Your suggestion (one sentence):"""

        response = self.generate(prompt, model_type)

        if response and response.strip().lower() != "no_suggestion":
            return self._clean_for_voice(response)

        return None

    @property
    def is_available(self) -> bool:
        return self.configured


gemini = GeminiService()
