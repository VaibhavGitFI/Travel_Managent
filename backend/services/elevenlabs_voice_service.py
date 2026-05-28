"""
OTIS Voice Agent - Text-to-Speech Service
Multi-tier TTS with automatic fallback and offline support

This service provides natural speech synthesis with intelligent fallbacks:
    1. ElevenLabs Turbo (primary, best quality, Indian accent)
    2. Google TTS (fallback 1, good quality)
    3. pyttsx3 Offline (fallback 2, always works)
    4. Beep/Tone (fallback 3, audio feedback)

Architecture:
    Text → Auto-detect Best TTS → Natural Speech Audio
              ↓ (if fails)
          Next Fallback → Speech Audio

Performance (ElevenLabs):
    - Latency: 75-150ms
    - Quality: Human-like, best in industry
    - Languages: 29+ languages including Hindi
    - Indian Accent: Native support

Author: TravelSync Pro Team
Date: 2026-03-26
"""

import sys
import os
import logging
import asyncio
import time
import io
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from services.http_client import http

logger = logging.getLogger(__name__)


class TTSProvider(Enum):
    """Available TTS providers."""
    GEMINI = "gemini"            # Cloud, natural conversational audio
    ELEVENLABS = "elevenlabs"    # Cloud, best quality
    GOOGLE = "google"            # Cloud, good quality
    PYTTSX3 = "pyttsx3"          # Offline, robotic
    BEEP = "beep"                # Fallback, just sound


@dataclass
class SpeechResult:
    """Result from text-to-speech synthesis."""
    audio_data: bytes                   # Audio bytes (WAV or MP3)
    text: str                           # Original text
    provider: TTSProvider               # Which provider was used
    latency_ms: float                   # Synthesis latency
    audio_format: str = "wav"          # Audio format
    sample_rate: int = 22050           # Sample rate (Hz)
    duration_seconds: float = 0.0      # Audio duration
    metadata: Dict = None               # Additional metadata

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# ── Abstract Base Provider ────────────────────────────────────────────────────

class TTSProviderBase(ABC):
    """Abstract base class for TTS providers."""

    def __init__(self, config: Dict):
        self.config = config
        self.is_configured = self._check_configuration()
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_latency_ms": 0.0,
            "total_characters": 0
        }

    @abstractmethod
    def _check_configuration(self) -> bool:
        """Check if provider is properly configured."""
        pass

    @abstractmethod
    async def synthesize(self, text: str) -> SpeechResult:
        """Synthesize text to speech."""
        pass

    @abstractmethod
    def get_provider_name(self) -> TTSProvider:
        """Get provider enum."""
        pass

    def update_stats(self, result: SpeechResult, success: bool):
        """Update provider statistics."""
        self._stats["total_requests"] += 1
        if success:
            self._stats["successful_requests"] += 1
            self._stats["total_latency_ms"] += result.latency_ms
            self._stats["total_characters"] += len(result.text)
        else:
            self._stats["failed_requests"] += 1

    def get_stats(self) -> Dict:
        """Get provider statistics."""
        success_rate = 0.0
        if self._stats["total_requests"] > 0:
            success_rate = self._stats["successful_requests"] / self._stats["total_requests"]

        avg_latency = 0.0
        if self._stats["successful_requests"] > 0:
            avg_latency = self._stats["total_latency_ms"] / self._stats["successful_requests"]

        return {
            **self._stats,
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency
        }


# ── ElevenLabs Provider ───────────────────────────────────────────────────────

class ElevenLabsProvider(TTSProviderBase):
    """ElevenLabs TTS provider (primary, best quality)."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self._client = None
        self._warned_missing_voice_id = False
        if self.is_configured:
            self._initialize_elevenlabs()

    def _check_configuration(self) -> bool:
        """Check if ElevenLabs API key is configured."""
        api_key = Config.ELEVENLABS_API_KEY
        if not api_key:
            logger.info("[TTS ElevenLabs] API key not configured. Skipping ElevenLabs provider.")
            return False
        return True

    def _initialize_elevenlabs(self):
        """Initialize ElevenLabs SDK."""
        try:
            from elevenlabs.client import ElevenLabs

            self._client = ElevenLabs(api_key=Config.ELEVENLABS_API_KEY)

            logger.info("[TTS ElevenLabs] ✅ ElevenLabs SDK initialized successfully")
        except ImportError:
            logger.warning(
                "[TTS ElevenLabs] elevenlabs not installed. "
                "Install with: pip install elevenlabs"
            )
            self.is_configured = False
        except Exception as e:
            logger.error(f"[TTS ElevenLabs] Initialization failed: {e}")
            self.is_configured = False

    def get_provider_name(self) -> TTSProvider:
        return TTSProvider.ELEVENLABS

    def _resolve_voice_id(self) -> str:
        """Resolve the configured ElevenLabs voice ID with a safe fallback."""
        voice_id = (Config.OTIS_VOICE_ID or "").strip()
        if voice_id:
            return voice_id

        fallback_voice_id = "pNInz6obpgDQGcFmaJgB"
        if not self._warned_missing_voice_id:
            logger.warning(
                "[TTS ElevenLabs] OTIS_VOICE_ID not set. Using fallback voice '%s'. "
                "Set OTIS_VOICE_ID to an Indian-English male voice from your ElevenLabs library for the best accent match.",
                fallback_voice_id,
            )
            self._warned_missing_voice_id = True
        return fallback_voice_id

    async def synthesize(self, text: str) -> SpeechResult:
        """
        Synthesize speech using ElevenLabs.

        Args:
            text: Text to convert to speech

        Returns:
            SpeechResult with audio data
        """
        if not self.is_configured:
            raise RuntimeError("ElevenLabs is not configured")

        start_time = time.time()

        try:
            voice_id = self._resolve_voice_id()
            model_id = Config.OTIS_VOICE_MODEL_ID or "eleven_turbo_v2_5"
            stability = Config.OTIS_VOICE_STABILITY
            similarity = Config.OTIS_VOICE_SIMILARITY
            style = Config.OTIS_VOICE_STYLE

            # Generate speech
            response = self._client.text_to_speech.convert(
                voice_id=voice_id,
                output_format="mp3_22050_32",  # 22.05kHz, 32kbps MP3
                text=text,
                model_id=model_id,
                voice_settings={
                    "stability": stability,
                    "similarity_boost": similarity,
                    "style": style,
                    "use_speaker_boost": Config.OTIS_VOICE_USE_SPEAKER_BOOST,
                },
            )

            # Collect audio chunks
            audio_chunks = []
            for chunk in response:
                if chunk:
                    audio_chunks.append(chunk)

            audio_data = b"".join(audio_chunks)

            latency_ms = (time.time() - start_time) * 1000

            # Estimate duration (rough: MP3 at 32kbps)
            duration_seconds = len(audio_data) / (32000 / 8)  # bytes / (bits_per_sec / 8)

            logger.debug(
                f"[TTS ElevenLabs] Synthesized {len(text)} chars "
                f"(latency: {latency_ms:.0f}ms, duration: {duration_seconds:.1f}s)"
            )

            result = SpeechResult(
                audio_data=audio_data,
                text=text,
                provider=TTSProvider.ELEVENLABS,
                latency_ms=latency_ms,
                audio_format="mp3",
                sample_rate=22050,
                duration_seconds=duration_seconds,
                metadata={
                    "voice_id": voice_id,
                    "voice_label": Config.OTIS_VOICE_LABEL,
                    "language": Config.OTIS_VOICE_LANGUAGE,
                    "gender": Config.OTIS_VOICE_GENDER,
                    "model": model_id,
                    "characters": len(text)
                }
            )

            self.update_stats(result, success=True)
            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"[TTS ElevenLabs] Synthesis failed: {e}")

            result = SpeechResult(
                audio_data=b"",
                text=text,
                provider=TTSProvider.ELEVENLABS,
                latency_ms=latency_ms,
                metadata={"error": str(e)}
            )
            self.update_stats(result, success=False)

            raise RuntimeError(f"ElevenLabs TTS failed: {e}") from e


# ── Gemini TTS Provider ───────────────────────────────────────────────────────

class GeminiTTSProvider(TTSProviderBase):
    """
    Gemini Developer API text-to-speech via REST.

    Uses the Gemini TTS preview model with a conversational voice and an
    Indian-English delivery prompt, then wraps the returned PCM in a WAV
    container for browser-safe playback.
    """

    _REST_URL = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash-preview-tts:generateContent"
    )
    _DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
    _DEFAULT_VOICE = "Charon"
    _SAMPLE_RATE = 24000

    def __init__(self, config: Dict):
        super().__init__(config)
        self._api_key = None
        self._model_name = self._DEFAULT_MODEL
        self._voice_name = self._DEFAULT_VOICE
        if self.is_configured:
            self._initialize_gemini()

    def _check_configuration(self) -> bool:
        return bool(Config.GEMINI_API_KEY)

    def _initialize_gemini(self):
        self._api_key = Config.GEMINI_API_KEY
        self._model_name = Config.GEMINI_TTS_MODEL or self._DEFAULT_MODEL
        self._voice_name = Config.GEMINI_TTS_VOICE or self._DEFAULT_VOICE
        logger.info(
            "[TTS Gemini] ✅ Gemini TTS REST initialized — model: %s | voice: %s",
            self._model_name,
            self._voice_name,
        )

    def get_provider_name(self) -> TTSProvider:
        return TTSProvider.GEMINI

    def _build_prompt(self, text: str) -> str:
        cleaned = " ".join((text or "").split()).strip()
        return (
            "Speak naturally in clear Indian English with a calm, helpful, "
            "conversational travel-assistant tone. Say exactly: "
            f"{cleaned}"
        )

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        import wave

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self._SAMPLE_RATE)
            wav_file.writeframes(pcm_data)
        return wav_buffer.getvalue()

    async def synthesize(self, text: str) -> SpeechResult:
        if not self.is_configured:
            raise RuntimeError("Gemini TTS is not configured")

        start_time = time.time()

        try:
            import base64
            import json as _json
            import urllib.error
            import urllib.request

            payload = _json.dumps({
                "contents": [{
                    "parts": [{
                        "text": self._build_prompt(text),
                    }]
                }],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": self._voice_name,
                            }
                        }
                    }
                },
                "model": self._model_name,
            }).encode("utf-8")

            req = urllib.request.Request(
                self._REST_URL,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self._api_key,
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                body = _json.loads(resp.read())

            candidate = ((body.get("candidates") or [{}])[0])
            content = candidate.get("content") or {}
            part = ((content.get("parts") or [{}])[0])
            inline_data = part.get("inlineData") or {}
            audio_b64 = inline_data.get("data", "")
            if not audio_b64:
                raise RuntimeError("Gemini TTS returned empty audio data")

            pcm_data = base64.b64decode(audio_b64)
            audio_data = self._pcm_to_wav(pcm_data)
            latency_ms = (time.time() - start_time) * 1000
            duration_seconds = len(pcm_data) / (self._SAMPLE_RATE * 2)

            result = SpeechResult(
                audio_data=audio_data,
                text=text,
                provider=TTSProvider.GEMINI,
                latency_ms=latency_ms,
                audio_format="wav",
                sample_rate=self._SAMPLE_RATE,
                duration_seconds=duration_seconds,
                metadata={
                    "model": self._model_name,
                    "voice": self._voice_name,
                    "mime_type": inline_data.get("mimeType", "audio/L16"),
                    "language": "en-IN",
                },
            )
            self.update_stats(result, success=True)
            return result

        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            latency_ms = (time.time() - start_time) * 1000
            logger.error("[TTS Gemini] HTTP %s — %s", exc.code, body_text[:300])
            result = SpeechResult(
                audio_data=b"",
                text=text,
                provider=TTSProvider.GEMINI,
                latency_ms=latency_ms,
                metadata={"error": body_text[:200]},
            )
            self.update_stats(result, success=False)
            raise RuntimeError(f"Gemini TTS HTTP {exc.code}: {body_text[:200]}") from exc
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error("[TTS Gemini] Synthesis failed: %s", e)
            result = SpeechResult(
                audio_data=b"",
                text=text,
                provider=TTSProvider.GEMINI,
                latency_ms=latency_ms,
                metadata={"error": str(e)},
            )
            self.update_stats(result, success=False)
            raise RuntimeError(f"Gemini TTS failed: {e}") from e


# ── Google TTS Provider ───────────────────────────────────────────────────────

class GoogleTTSProvider(TTSProviderBase):
    """
    Google Cloud Text-to-Speech via REST API — no Python package required.

    Uses the Neural2 en-IN voice by default (genuine Indian male accent).
    Reuses GOOGLE_VISION_API_KEY so no extra credentials are needed — just
    enable the "Cloud Text-to-Speech API" in your Google Cloud Console for
    the same project/key.

    Default voice: en-IN-Neural2-C (Indian male, Neural2 quality)
    Override:      set GOOGLE_TTS_VOICE=en-IN-Neural2-B  (alternative male)
                   or  GOOGLE_TTS_VOICE=en-IN-Neural2-D  (female)

    Latency: typically 200-400 ms (REST round-trip, no cold start).
    """

    _REST_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

    # Indian Neural2 voices — all genuinely Indian-accented
    # Neural2-C = clear male | Neural2-B = warmer male | Neural2-D = female
    _DEFAULT_VOICE = "en-IN-Neural2-C"

    def __init__(self, config: Dict):
        super().__init__(config)
        self._api_key = None
        self._voice_name = self._DEFAULT_VOICE
        if self.is_configured:
            self._initialize_google()

    def _check_configuration(self) -> bool:
        """Active when any Google API key is available (Vision key is reused)."""
        return bool(Config.GOOGLE_TTS_API_KEY or Config.GOOGLE_VISION_API_KEY)

    def _initialize_google(self):
        """Store credentials — no package import needed, just REST."""
        self._api_key = (
            Config.GOOGLE_TTS_API_KEY
            or Config.GOOGLE_VISION_API_KEY
        )
        self._voice_name = (
            os.getenv("GOOGLE_TTS_VOICE", "").strip()
            or self._DEFAULT_VOICE
        )
        logger.info(
            "[TTS Google] ✅ Google TTS REST initialized — voice: %s",
            self._voice_name,
        )

    def get_provider_name(self) -> TTSProvider:
        return TTSProvider.GOOGLE

    async def synthesize(self, text: str) -> SpeechResult:
        """Synthesize using Google TTS REST API — returns MP3 bytes."""
        if not self.is_configured:
            raise RuntimeError("Google TTS is not configured")

        start_time = time.time()

        try:
            import base64
            import json as _json

            payload = _json.dumps({
                "input": {"text": text},
                "voice": {
                    "languageCode": "en-IN",
                    "name": self._voice_name,
                    "ssmlGender": (
                        "FEMALE"
                        if "D" in self._voice_name or "A" in self._voice_name
                        else "MALE"
                    ),
                },
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": max(0.5, min(4.0, Config.OTIS_VOICE_SPEED or 1.0)),
                    "pitch": max(-20.0, min(20.0, Config.OTIS_VOICE_PITCH or 0.0)),
                },
            }).encode("utf-8")

            url = f"{self._REST_URL}?key={self._api_key}"
            resp = http.post(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                timeout=(3, 12),
            )
            body = resp.json()
            if resp.status_code >= 400:
                raise RuntimeError(f"Google TTS HTTP {resp.status_code}: {resp.text[:200]}")

            audio_b64 = body.get("audioContent", "")
            if not audio_b64:
                raise RuntimeError("Google TTS returned empty audioContent")

            audio_data = base64.b64decode(audio_b64)
            latency_ms = (time.time() - start_time) * 1000
            duration_seconds = len(audio_data) / (32000 / 8)

            logger.debug(
                "[TTS Google] Synthesized %d chars | voice=%s | %.0f ms",
                len(text), self._voice_name, latency_ms,
            )

            result = SpeechResult(
                audio_data=audio_data,
                text=text,
                provider=TTSProvider.GOOGLE,
                latency_ms=latency_ms,
                audio_format="mp3",
                sample_rate=24000,
                duration_seconds=duration_seconds,
                metadata={"voice": self._voice_name, "language": "en-IN"},
            )
            self.update_stats(result, success=True)
            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error("[TTS Google] Synthesis failed: %s", e)
            result = SpeechResult(
                audio_data=b"", text=text, provider=TTSProvider.GOOGLE,
                latency_ms=latency_ms, metadata={"error": str(e)},
            )
            self.update_stats(result, success=False)
            raise RuntimeError(f"Google TTS failed: {e}") from e


# ── pyttsx3 Offline Provider ──────────────────────────────────────────────────

class Pyttsx3Provider(TTSProviderBase):
    """pyttsx3 offline TTS provider (fallback 2, always works)."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self._engine = None
        if self.is_configured:
            self._initialize_pyttsx3()

    def _check_configuration(self) -> bool:
        """pyttsx3 works offline, always available."""
        return True

    def _initialize_pyttsx3(self):
        """Initialize pyttsx3 engine."""
        try:
            import pyttsx3

            self._engine = pyttsx3.init()

            # Configure voice
            self._engine.setProperty('rate', int((Config.OTIS_VOICE_SPEED or 1.0) * 150))
            self._engine.setProperty('volume', 0.9)

            # Try to find Indian English voice
            voices = self._engine.getProperty('voices')
            indian_voice = None
            for voice in voices:
                voice_name = (voice.name or "").lower()
                if (
                    'indian' in voice_name
                    or 'india' in voice_name
                    or (Config.OTIS_VOICE_LANGUAGE or "en-IN").lower() in voice_name
                ):
                    indian_voice = voice
                    break

            if indian_voice:
                self._engine.setProperty('voice', indian_voice.id)

            logger.info("[TTS pyttsx3] ✅ pyttsx3 initialized (offline mode)")

        except ImportError:
            logger.warning(
                "[TTS pyttsx3] pyttsx3 not installed. "
                "Install with: pip install pyttsx3"
            )
            self.is_configured = False
        except Exception as e:
            logger.error(f"[TTS pyttsx3] Initialization failed: {e}")
            self.is_configured = False

    def get_provider_name(self) -> TTSProvider:
        return TTSProvider.PYTTSX3

    async def synthesize(self, text: str) -> SpeechResult:
        """Synthesize speech using pyttsx3 (offline)."""
        if not self.is_configured:
            raise RuntimeError("pyttsx3 is not configured")

        start_time = time.time()

        try:
            import tempfile

            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_file = f.name

            # Save to file
            self._engine.save_to_file(text, temp_file)
            self._engine.runAndWait()

            # Read audio data
            with open(temp_file, 'rb') as f:
                audio_data = f.read()

            # Clean up
            os.unlink(temp_file)

            latency_ms = (time.time() - start_time) * 1000

            logger.debug(
                f"[TTS pyttsx3] Synthesized {len(text)} chars "
                f"(offline, latency: {latency_ms:.0f}ms)"
            )

            result = SpeechResult(
                audio_data=audio_data,
                text=text,
                provider=TTSProvider.PYTTSX3,
                latency_ms=latency_ms,
                audio_format="wav",
                sample_rate=22050,
                metadata={"offline": True}
            )

            self.update_stats(result, success=True)
            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"[TTS pyttsx3] Synthesis failed: {e}")

            result = SpeechResult(
                audio_data=b"",
                text=text,
                provider=TTSProvider.PYTTSX3,
                latency_ms=latency_ms,
                metadata={"error": str(e)}
            )
            self.update_stats(result, success=False)

            raise RuntimeError(f"pyttsx3 TTS failed: {e}") from e


# ── Beep Provider (Last Resort) ───────────────────────────────────────────────

class BeepProvider(TTSProviderBase):
    """Beep/tone provider for audio feedback (fallback 3, always works)."""

    def __init__(self, config: Dict):
        super().__init__(config)

    def _check_configuration(self) -> bool:
        """Beep provider is always available."""
        return True

    def get_provider_name(self) -> TTSProvider:
        return TTSProvider.BEEP

    async def synthesize(self, text: str) -> SpeechResult:
        """Generate a beep sound as audio feedback."""
        start_time = time.time()

        try:
            import math
            import struct
            import wave

            # Generate a pleasant beep (440Hz sine wave, 0.3 seconds)
            sample_rate = 22050
            duration = 0.3
            frequency = 440  # A4 note

            num_samples = int(sample_rate * duration)
            samples = []

            for i in range(num_samples):
                t = i / sample_rate
                # Sine wave with envelope (fade in/out)
                envelope = min(i / 1000, 1.0) * min((num_samples - i) / 1000, 1.0)
                sample = int(32767 * envelope * math.sin(2 * math.pi * frequency * t))
                samples.append(sample)

            pcm_data = struct.pack(f"{len(samples)}h", *samples)
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm_data)
            audio_data = wav_buffer.getvalue()

            latency_ms = (time.time() - start_time) * 1000

            logger.info(
                f"[TTS Beep] 🔔 Generated beep for '{text[:30]}...' "
                f"(fallback audio, latency: {latency_ms:.0f}ms)"
            )

            result = SpeechResult(
                audio_data=audio_data,
                text=text,
                provider=TTSProvider.BEEP,
                latency_ms=latency_ms,
                audio_format="wav",
                sample_rate=22050,
                duration_seconds=duration,
                metadata={"note": "Beep fallback - TTS not available"}
            )

            self.update_stats(result, success=True)
            return result

        except Exception as e:
            logger.error(f"[TTS Beep] Even beep failed: {e}")
            raise RuntimeError(f"Beep generation failed: {e}") from e


# ── Main TTS Service ──────────────────────────────────────────────────────────

class TextToSpeechService:
    """
    Multi-tier Text-to-Speech service with automatic fallback.

    Provider priority:
        1. Google TTS  — en-IN-Neural2-C primary
        2. ElevenLabs  — alternate premium fallback
        3. Gemini TTS  — conversational fallback
        4. pyttsx3     — offline fallback
        5. Beep        — last-resort audio feedback

    To override:
        Set OTIS_TTS_PROVIDER=gemini|google|elevenlabs in .env
    """

    def __init__(self):
        """Initialize TTS service with all available providers."""
        self._providers: List[TTSProviderBase] = []
        self._active_provider: Optional[TTSProviderBase] = None

        logger.info("[TTS Service] Initializing text-to-speech providers...")

        config = {}

        # Read preferred provider (default: google unless overridden in .env)
        preferred = os.getenv("OTIS_TTS_PROVIDER", "google").lower().strip()

        gemini = GeminiTTSProvider(config)
        google    = GoogleTTSProvider(config)
        elevenlabs = ElevenLabsProvider(config)

        if preferred == "elevenlabs":
            _ordered = [
                ("ElevenLabs", elevenlabs, "primary"),
                ("Google TTS", google, "fallback 1"),
                ("Gemini TTS", gemini, "fallback 2"),
            ]
        elif preferred == "gemini":
            _ordered = [
                ("Gemini TTS", gemini, "primary — natural conversational voice"),
                ("Google TTS", google, "fallback 1 — Indian accent"),
                ("ElevenLabs", elevenlabs, "fallback 2"),
            ]
        else:
            _ordered = [
                ("Google TTS", google, "primary — Indian accent (en-IN-Neural2-C)"),
                ("ElevenLabs", elevenlabs, "fallback 1"),
                ("Gemini TTS", gemini, "fallback 2"),
            ]

        for label, provider, role in _ordered:
            if provider.is_configured:
                self._providers.append(provider)
                logger.info("[TTS Service]   ✅ %s (%s)", label, role)
            else:
                logger.info("[TTS Service]   ⏭️  %s (not configured)", label)

        # Try pyttsx3 (offline)
        pyttsx3 = Pyttsx3Provider(config)
        if pyttsx3.is_configured:
            self._providers.append(pyttsx3)
            logger.info("[TTS Service]   ✅ pyttsx3 (offline fallback)")
        else:
            logger.info("[TTS Service]   ⏭️  pyttsx3 (not installed)")

        # Always add Beep provider (guaranteed to work)
        beep = BeepProvider(config)
        self._providers.append(beep)
        logger.info("[TTS Service]   ✅ Beep (audio feedback)")

        if not self._providers:
            raise RuntimeError("No TTS providers available!")

        # Set active provider to first available
        self._active_provider = self._providers[0]

        logger.info(
            f"[TTS Service] Initialized with {len(self._providers)} provider(s). "
            f"Active: {self._active_provider.get_provider_name().value}"
        )

        # Warm up the active cloud provider in the background so the first
        # real user request reuses a warm connection instead of paying the
        # initial handshake penalty.
        self._warmup_primary()

    def _ordered_providers(
        self,
        preferred_provider: Optional[TTSProvider] = None,
    ) -> List[TTSProviderBase]:
        """Return providers ordered by explicit preference, then active provider."""
        providers = [p for p in self._providers if p.is_configured]
        if not providers:
            return []

        if preferred_provider:
            providers.sort(
                key=lambda p: (
                    0 if p.get_provider_name() == preferred_provider else 1,
                    0 if p is self._active_provider else 1,
                )
            )
            return providers

        if self._active_provider and self._active_provider in providers:
            providers.sort(key=lambda p: 0 if p is self._active_provider else 1)

        return providers

    def _handle_provider_failure(self, provider: TTSProviderBase, error: Exception) -> None:
        """Demote permanently broken providers so OTIS doesn't retry them every turn."""
        message = str(error)
        provider_name = provider.get_provider_name()

        if provider_name == TTSProvider.GOOGLE and "HTTP 403" in message:
            provider.is_configured = False
            logger.warning(
                "[TTS Service] Disabling google for this process after permanent 403. "
                "Enable Google Cloud Text-to-Speech or use ElevenLabs as primary."
            )
            if self._active_provider is provider:
                self._active_provider = next(
                    (p for p in self._providers if p.is_configured and p is not provider),
                    None,
                )
            return

        if provider_name == TTSProvider.GEMINI and any(code in message for code in ("HTTP 400", "HTTP 403", "HTTP 404")):
            provider.is_configured = False
            logger.warning(
                "[TTS Service] Disabling gemini for this process after a permanent API error. "
                "OTIS will continue with Google or ElevenLabs."
            )
            if self._active_provider is provider:
                self._active_provider = next(
                    (p for p in self._providers if p.is_configured and p is not provider),
                    None,
                )

    def _warmup_primary(self):
        """Fire a background thread to warm up the primary cloud TTS provider."""
        import threading

        provider = self._active_provider
        if not provider or provider.get_provider_name() not in {
            TTSProvider.GOOGLE,
            TTSProvider.ELEVENLABS,
            TTSProvider.GEMINI,
        }:
            return

        def _run():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # A tiny phrase is enough to establish TLS and provider routing.
                loop.run_until_complete(provider.synthesize("Ready."))
                loop.close()
                logger.info(
                    "[TTS Service] %s connection warmed up",
                    provider.get_provider_name().value,
                )
            except Exception as e:
                logger.debug("[TTS Service] Warmup failed (non-critical): %s", e)

        threading.Thread(target=_run, daemon=True, name="tts-warmup").start()

    async def speak(
        self,
        text: str,
        max_retries: int = 2,
        preferred_provider: Optional[TTSProvider] = None
    ) -> SpeechResult:
        """
        Synthesize text to speech with automatic fallback.

        Args:
            text: Text to convert to speech
            max_retries: Maximum retries per provider (default: 2)
            preferred_provider: Try this provider first (optional)

        Returns:
            SpeechResult with audio data

        Raises:
            RuntimeError: If all providers fail (unlikely with beep fallback)
        """
        if not text or not text.strip():
            logger.warning("[TTS Service] Empty text provided")
            text = "Ready"  # Default text

        providers = self._ordered_providers(preferred_provider)

        last_error = None

        # Try each provider
        for provider in providers:
            logger.debug(
                f"[TTS Service] Attempting synthesis with: "
                f"{provider.get_provider_name().value}"
            )

            # Try with retries
            for attempt in range(max_retries):
                try:
                    result = await provider.synthesize(text)

                    if result.audio_data:  # Success!
                        self._active_provider = provider
                        logger.info(
                            f"[TTS Service] ✅ Synthesized successfully with "
                            f"{result.provider.value} "
                            f"({len(result.audio_data)} bytes, {result.latency_ms:.0f}ms)"
                        )
                        return result

                except Exception as e:
                    last_error = e
                    self._handle_provider_failure(provider, e)
                    logger.warning(
                        f"[TTS Service] {provider.get_provider_name().value} failed "
                        f"(attempt {attempt + 1}/{max_retries}): {e}"
                    )

                    if not provider.is_configured:
                        break

                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.1 * (2 ** attempt))
                        continue
                    break

            # This provider exhausted retries, try next
            logger.info(
                f"[TTS Service] ⏭️  Falling back from "
                f"{provider.get_provider_name().value} to next provider..."
            )

        # All providers failed (should never happen with beep fallback)
        error_msg = f"All TTS providers failed. Last error: {last_error}"
        logger.error(f"[TTS Service] ❌ {error_msg}")
        raise RuntimeError(error_msg)

    def get_active_provider(self) -> TTSProvider:
        """Get currently active TTS provider."""
        return self._active_provider.get_provider_name() if self._active_provider else None

    def get_available_providers(self) -> List[TTSProvider]:
        """Get list of available (configured) providers."""
        return [p.get_provider_name() for p in self._providers if p.is_configured]

    def get_statistics(self) -> Dict:
        """Get comprehensive statistics for all providers."""
        stats = {
            "active_provider": self.get_active_provider().value if self._active_provider else None,
            "providers": {}
        }

        for provider in self._providers:
            provider_stats = provider.get_stats()
            stats["providers"][provider.get_provider_name().value] = provider_stats

        return stats


# ── Utility Functions ─────────────────────────────────────────────────────────

async def test_tts_service():
    """Test TTS service with sample text."""
    print("=" * 70)
    print("OTIS Text-to-Speech - Interactive Test")
    print("=" * 70)

    # Initialize service
    print("\n🔧 Initializing TTS service...")
    service = TextToSpeechService()

    print(f"\n✅ Service initialized!")
    print(f"   Active provider: {service.get_active_provider().value}")
    print(f"   Available providers: {[p.value for p in service.get_available_providers()]}")

    # Test phrases
    test_phrases = [
        "Hello! I am Otis, your voice assistant.",
        "You have three pending approvals.",
        "Trip to Mumbai approved successfully!",
    ]

    print("\n" + "=" * 70)
    print("Testing speech synthesis...")
    print("=" * 70)

    for i, phrase in enumerate(test_phrases, 1):
        print(f"\n🗣️  Test {i}/{len(test_phrases)}: '{phrase}'")

        try:
            result = await service.speak(phrase)

            print(f"   ✅ Synthesis successful!")
            print(f"      Provider: {result.provider.value}")
            print(f"      Format: {result.audio_format}")
            print(f"      Size: {len(result.audio_data):,} bytes")
            print(f"      Latency: {result.latency_ms:.0f}ms")
            print(f"      Duration: {result.duration_seconds:.1f}s")

            # Save to file (optional)
            filename = f"test_tts_{i}.{result.audio_format}"
            with open(filename, 'wb') as f:
                f.write(result.audio_data)
            print(f"      Saved to: {filename}")

        except Exception as e:
            print(f"   ❌ Synthesis failed: {e}")

    # Final statistics
    print("\n📊 Final Statistics:")
    final_stats = service.get_statistics()
    for provider_name, provider_stats in final_stats["providers"].items():
        if provider_stats["total_requests"] > 0:
            print(f"\n   {provider_name}:")
            print(f"      Total requests: {provider_stats['total_requests']}")
            print(f"      Success rate: {provider_stats['success_rate']:.1%}")
            print(f"      Avg latency: {provider_stats['avg_latency_ms']:.0f}ms")
            print(f"      Total characters: {provider_stats['total_characters']}")

    print("\n✅ Test complete!")
    print("=" * 70)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(test_tts_service())
