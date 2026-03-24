"""
TravelSync Pro — Gemini AI Service
Uses Google Gemini 2.0 Flash (fast, cheap) and 1.5 Pro (complex analysis)
Falls back gracefully when GEMINI_API_KEY not set.
"""
import os
import json
import re
import logging
import time

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
        try:
            model = self._genai.GenerativeModel(GEMINI_MODELS["flash"])
            audio_part = {"mime_type": mime_type, "data": audio_bytes}
            prompt = (
                "Transcribe this audio accurately. Return ONLY the spoken text, "
                "nothing else. If the audio is in Hindi or another Indian language, "
                "transliterate to English. If the audio is unclear or empty, return: [unclear]"
            )
            response = model.generate_content([prompt, audio_part])
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

    @property
    def is_available(self) -> bool:
        return self.configured


gemini = GeminiService()
