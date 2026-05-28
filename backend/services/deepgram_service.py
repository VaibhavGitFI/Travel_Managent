"""
OTIS Voice Agent - Speech-to-Text Service
Multi-tier STT with automatic fallback and offline support

This service provides real-time speech-to-text with intelligent fallbacks:
    1. Deepgram Nova-3 (primary, if API key available)
    2. Google Speech-to-Text (fallback 1, if available)
    3. Vosk Offline (fallback 2, always works)
    4. Mock/Demo mode (fallback 3, for testing)

Architecture:
    Audio Stream → Auto-detect Best STT → Transcription
                       ↓ (if fails)
                   Next Fallback → Transcription

Performance (Deepgram):
    - Latency: 100-150ms
    - Accuracy: 95%+ (Indian English optimized)
    - Cost: $0.0043/minute

Author: TravelSync Pro Team
Date: 2026-03-26
"""

import sys
import os
import logging
import asyncio
import json
import time
from typing import Optional, Dict, List, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from services.http_client import http

logger = logging.getLogger(__name__)


class STTProvider(Enum):
    """Available STT providers."""
    DEEPGRAM = "deepgram"        # Cloud, best quality
    GOOGLE = "google"            # Cloud, good quality
    VOSK = "vosk"                # Offline, decent quality
    MOCK = "mock"                # Demo/testing mode


class STTStatus(Enum):
    """STT service status."""
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class TranscriptionResult:
    """Result from speech-to-text transcription."""
    text: str                           # Transcribed text
    confidence: float                   # Confidence score (0.0 to 1.0)
    is_final: bool                      # Is this the final transcription?
    provider: STTProvider               # Which provider was used
    latency_ms: float                   # Transcription latency
    language: str = "en-IN"            # Detected language
    alternatives: List[str] = None      # Alternative transcriptions
    metadata: Dict = None               # Additional metadata

    def __post_init__(self):
        if self.alternatives is None:
            self.alternatives = []
        if self.metadata is None:
            self.metadata = {}


# ── Abstract Base Provider ────────────────────────────────────────────────────

class STTProviderBase(ABC):
    """Abstract base class for STT providers."""

    def __init__(self, config: Dict):
        self.config = config
        self.is_configured = self._check_configuration()
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_latency_ms": 0.0,
            "avg_confidence": 0.0
        }

    @abstractmethod
    def _check_configuration(self) -> bool:
        """Check if provider is properly configured."""
        pass

    @abstractmethod
    async def transcribe(self, audio_data: bytes, mime_type: str = "audio/webm") -> TranscriptionResult:
        """Transcribe audio to text."""
        pass

    @abstractmethod
    def get_provider_name(self) -> STTProvider:
        """Get provider enum."""
        pass

    def update_stats(self, result: TranscriptionResult, success: bool):
        """Update provider statistics."""
        self._stats["total_requests"] += 1
        if success:
            self._stats["successful_requests"] += 1
            self._stats["total_latency_ms"] += result.latency_ms
            if result.confidence > 0:
                # Running average of confidence
                n = self._stats["successful_requests"]
                avg = self._stats["avg_confidence"]
                self._stats["avg_confidence"] = (avg * (n - 1) + result.confidence) / n
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


# ── Deepgram Provider ─────────────────────────────────────────────────────────

class DeepgramProvider(STTProviderBase):
    """Deepgram Nova-3 STT provider (primary, best quality)."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self._deepgram = None
        if self.is_configured:
            self._initialize_deepgram()

    def _check_configuration(self) -> bool:
        """Check if Deepgram API key is configured."""
        api_key = Config.DEEPGRAM_API_KEY
        if not api_key:
            logger.info("[STT Deepgram] API key not configured. Skipping Deepgram provider.")
            return False
        return True

    def _initialize_deepgram(self):
        """Initialize Deepgram SDK."""
        try:
            from deepgram import DeepgramClient

            # Deepgram SDK v6 exposes prerecorded transcription at
            # client.listen.v1.media.transcribe_file(...)
            self._deepgram = DeepgramClient(api_key=Config.DEEPGRAM_API_KEY)

            logger.info("[STT Deepgram] ✅ Deepgram SDK initialized successfully")
        except ImportError:
            logger.warning(
                "[STT Deepgram] deepgram-sdk not installed. "
                "Install with: pip install deepgram-sdk"
            )
            self.is_configured = False
        except Exception as e:
            logger.error(f"[STT Deepgram] Initialization failed: {e}")
            self.is_configured = False

    def get_provider_name(self) -> STTProvider:
        return STTProvider.DEEPGRAM

    async def transcribe(self, audio_data: bytes, mime_type: str = "audio/webm") -> TranscriptionResult:
        """
        Transcribe audio using Deepgram Nova-2.

        Args:
            audio_data: Raw audio bytes from the browser (WebM/Opus, WAV, MP3, etc.)
            mime_type: MIME type of the audio data (e.g. "audio/webm", "audio/wav")

        Returns:
            TranscriptionResult with transcribed text
        """
        if not self.is_configured:
            raise RuntimeError("Deepgram is not configured")

        start_time = time.time()

        try:
            # Deepgram SDK v6 — pass bytes directly; it auto-detects format.
            # Do NOT set encoding= for container formats (webm/mp4/ogg).
            response = self._deepgram.listen.v1.media.transcribe_file(
                request=audio_data,
                model="nova-2",
                language="en-IN",
                punctuate=True,
                smart_format=True,
            )

            # Deepgram SDK v6 returns typed response objects. Older versions
            # expose dict-like payloads, so we support both shapes.
            if hasattr(response, "results"):
                channels = getattr(response.results, "channels", []) or []
                raw_alternatives = getattr(channels[0], "alternatives", []) if channels else []
                metadata_duration = float(getattr(getattr(response, "metadata", None), "duration", 0) or 0)
                if not raw_alternatives:
                    return TranscriptionResult(
                        text="",
                        confidence=0.0,
                        is_final=True,
                        provider=STTProvider.DEEPGRAM,
                        latency_ms=(time.time() - start_time) * 1000
                    )

                alternative = raw_alternatives[0]
                transcript = (getattr(alternative, "transcript", "") or "").strip()
                confidence = float(getattr(alternative, "confidence", 0.0) or 0.0)
                other_alternatives = [
                    (getattr(alt, "transcript", "") or "").strip()
                    for alt in raw_alternatives[1:3]
                    if getattr(alt, "transcript", "")
                ]
            else:
                result = response.to_dict() if hasattr(response, "to_dict") else response
                if not isinstance(result, dict) or "results" not in result:
                    raise RuntimeError("Invalid response from Deepgram")
                channels = result["results"].get("channels", [])
                raw_alternatives = channels[0]["alternatives"] if channels else []
                metadata_duration = result.get("metadata", {}).get("duration", 0)
                if not raw_alternatives:
                    return TranscriptionResult(
                        text="",
                        confidence=0.0,
                        is_final=True,
                        provider=STTProvider.DEEPGRAM,
                        latency_ms=(time.time() - start_time) * 1000
                    )

                alternative = raw_alternatives[0]
                transcript = alternative.get("transcript", "").strip()
                confidence = alternative.get("confidence", 0.0)
                other_alternatives = [
                    alt.get("transcript", "")
                    for alt in raw_alternatives[1:3]
                    if alt.get("transcript")
                ]

            latency_ms = (time.time() - start_time) * 1000

            logger.debug(
                f"[STT Deepgram] Transcribed: '{transcript}' "
                f"(confidence: {confidence:.2f}, latency: {latency_ms:.0f}ms)"
            )

            result = TranscriptionResult(
                text=transcript,
                confidence=confidence,
                is_final=True,
                provider=STTProvider.DEEPGRAM,
                latency_ms=latency_ms,
                language="en-IN",
                alternatives=other_alternatives,
                metadata={
                    "model": "nova-2",
                    "duration": metadata_duration
                }
            )

            self.update_stats(result, success=True)
            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"[STT Deepgram] Transcription failed: {e}")

            result = TranscriptionResult(
                text="",
                confidence=0.0,
                is_final=True,
                provider=STTProvider.DEEPGRAM,
                latency_ms=latency_ms,
                metadata={"error": str(e)}
            )
            self.update_stats(result, success=False)

            raise RuntimeError(f"Deepgram transcription failed: {e}") from e


# ── Google Speech-to-Text Provider ────────────────────────────────────────────

class GoogleSTTProvider(STTProviderBase):
    """Google Speech-to-Text provider (fallback 1)."""

    _REST_URL = "https://speech.googleapis.com/v1/speech:recognize"
    _DEFAULT_SAMPLE_RATE = 16000
    _SPEECH_HINTS = [
        "TravelSync",
        "OTIS",
        "Jarvis",
        "Webex",
        "LinkedIn",
        "Zoho Cliq",
        "IRCTC",
        "ConfirmTkt",
        "RailYatri",
        "RedBus",
        "MakeMyTrip",
        "Air India",
        "IndiGo",
        "Vistara",
        "Bengaluru",
        "Mumbai",
        "Pune",
        "Delhi",
        "Hyderabad",
        "Chennai",
        "Toronto",
        "reimbursement",
        "approvals",
        "itinerary",
        "boarding pass",
        "expense report",
        "train tickets",
        "flight options",
        "hotel booking",
    ]

    def __init__(self, config: Dict):
        super().__init__(config)
        self._api_key = None
        if self.is_configured:
            self._initialize_google()

    def _check_configuration(self) -> bool:
        """Check if Google credentials are configured."""
        # Prefer a dedicated STT key, then fall back to TTS/Vision keys.
        return bool(
            Config.GOOGLE_STT_API_KEY
            or Config.GOOGLE_TTS_API_KEY
            or Config.GOOGLE_VISION_API_KEY
        )

    def _initialize_google(self):
        """Store Google REST credentials."""
        self._api_key = (
            Config.GOOGLE_STT_API_KEY
            or Config.GOOGLE_TTS_API_KEY
            or Config.GOOGLE_VISION_API_KEY
        )
        logger.info("[STT Google] ✅ Google Speech-to-Text REST initialized")

    def get_provider_name(self) -> STTProvider:
        return STTProvider.GOOGLE

    def _resolve_audio_config(self, audio_data: bytes, mime_type: str) -> Dict:
        import io
        import wave

        mime = ((mime_type or "").split(";")[0]).strip().lower()

        if mime == "audio/webm":
            return {"encoding": "WEBM_OPUS", "sampleRateHertz": 48000}
        if mime == "audio/ogg":
            return {"encoding": "OGG_OPUS", "sampleRateHertz": 48000}
        if mime in {"audio/mpeg", "audio/mp3"}:
            return {"encoding": "MP3", "sampleRateHertz": 24000}
        if mime in {"audio/wav", "audio/wave", "audio/x-wav"} or audio_data[:4] == b"RIFF":
            sample_rate = self._DEFAULT_SAMPLE_RATE
            try:
                with wave.open(io.BytesIO(audio_data), "rb") as wav_file:
                    sample_rate = wav_file.getframerate() or self._DEFAULT_SAMPLE_RATE
            except Exception:
                sample_rate = self._DEFAULT_SAMPLE_RATE
            return {"encoding": "LINEAR16", "sampleRateHertz": sample_rate}

        raise RuntimeError(f"Google STT unsupported mime type: {mime_type}")

    async def transcribe(self, audio_data: bytes, mime_type: str = "audio/webm") -> TranscriptionResult:
        """Transcribe audio using Google Speech-to-Text REST."""
        if not self.is_configured:
            raise RuntimeError("Google STT is not configured")

        start_time = time.time()

        try:
            import base64

            payload = {
                "config": {
                    **self._resolve_audio_config(audio_data, mime_type),
                    "languageCode": "en-IN",
                    "alternativeLanguageCodes": ["en-US"],
                    "enableAutomaticPunctuation": True,
                    "maxAlternatives": 3,
                    "model": "latest_short",
                    "speechContexts": [{
                        "phrases": self._SPEECH_HINTS,
                        "boost": 16.0,
                    }],
                },
                "audio": {
                    "content": base64.b64encode(audio_data).decode("ascii"),
                },
            }
            response = http.post(
                f"{self._REST_URL}?key={self._api_key}",
                json=payload,
                timeout=(3, 15),
            )
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code >= 400:
                raise RuntimeError(f"Google STT HTTP {response.status_code}: {response.text[:200]}")

            body = response.json()
            results = body.get("results", [])
            if not results:
                empty = TranscriptionResult(
                    text="",
                    confidence=0.0,
                    is_final=True,
                    provider=STTProvider.GOOGLE,
                    latency_ms=latency_ms,
                )
                self.update_stats(empty, success=True)
                return empty

            alternatives = (results[0].get("alternatives") or [])
            if not alternatives:
                empty = TranscriptionResult(
                    text="",
                    confidence=0.0,
                    is_final=True,
                    provider=STTProvider.GOOGLE,
                    latency_ms=latency_ms,
                )
                self.update_stats(empty, success=True)
                return empty

            primary = alternatives[0]
            transcript = (primary.get("transcript") or "").strip()
            confidence = float(primary.get("confidence", 0.0) or 0.0)
            other_alternatives = [
                (alt.get("transcript") or "").strip()
                for alt in alternatives[1:3]
                if (alt.get("transcript") or "").strip()
            ]

            result_obj = TranscriptionResult(
                text=transcript,
                confidence=confidence,
                is_final=True,
                provider=STTProvider.GOOGLE,
                latency_ms=latency_ms,
                language="en-IN",
                alternatives=other_alternatives,
            )
            self.update_stats(result_obj, success=True)
            return result_obj

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"[STT Google] Transcription failed: {e}")

            result = TranscriptionResult(
                text="",
                confidence=0.0,
                is_final=True,
                provider=STTProvider.GOOGLE,
                latency_ms=latency_ms,
                metadata={"error": str(e)}
            )
            self.update_stats(result, success=False)

            raise RuntimeError(f"Google STT failed: {e}") from e


# ── Vosk Offline Provider ─────────────────────────────────────────────────────

class VoskProvider(STTProviderBase):
    """Vosk offline STT provider (fallback 2, always works)."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self._model = None
        self._recognizer = None
        if self.is_configured:
            self._initialize_vosk()

    def _check_configuration(self) -> bool:
        """Vosk works offline, always available."""
        return True  # Always available (offline)

    def _initialize_vosk(self):
        """Initialize Vosk with offline model."""
        try:
            from vosk import Model, KaldiRecognizer
            import os

            # Try to find Vosk model
            model_paths = [
                "/Users/fristineinfotech/Development/Travel_Sync_12thMarch/backend/models/vosk-model-small-en-in-0.4",
                "./models/vosk-model-small-en-in-0.4",
                os.path.expanduser("~/.vosk/models/vosk-model-small-en-in-0.4"),
                "vosk-model-small-en-in-0.4"
            ]

            model_path = None
            for path in model_paths:
                if os.path.exists(path):
                    model_path = path
                    break

            if not model_path:
                logger.warning(
                    "[STT Vosk] Model not found. Download from: "
                    "https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip"
                )
                self.is_configured = False
                return

            self._model = Model(model_path)
            self._recognizer = KaldiRecognizer(self._model, 16000)

            logger.info(f"[STT Vosk] ✅ Vosk initialized with model: {model_path}")

        except ImportError:
            logger.warning(
                "[STT Vosk] vosk not installed. "
                "Install with: pip install vosk"
            )
            self.is_configured = False
        except Exception as e:
            logger.error(f"[STT Vosk] Initialization failed: {e}")
            self.is_configured = False

    def get_provider_name(self) -> STTProvider:
        return STTProvider.VOSK

    async def transcribe(self, audio_data: bytes, mime_type: str = "audio/webm") -> TranscriptionResult:
        """Transcribe audio using Vosk (offline)."""
        if not self.is_configured:
            raise RuntimeError("Vosk is not configured")

        start_time = time.time()

        try:
            # Process audio
            self._recognizer.AcceptWaveform(audio_data)

            # Get result
            result_json = self._recognizer.FinalResult()
            result = json.loads(result_json)

            transcript = result.get("text", "").strip()

            # Vosk doesn't provide confidence, estimate based on text length
            confidence = min(0.7, len(transcript.split()) * 0.1) if transcript else 0.0

            latency_ms = (time.time() - start_time) * 1000

            logger.debug(
                f"[STT Vosk] Transcribed: '{transcript}' "
                f"(offline, latency: {latency_ms:.0f}ms)"
            )

            result_obj = TranscriptionResult(
                text=transcript,
                confidence=confidence,
                is_final=True,
                provider=STTProvider.VOSK,
                latency_ms=latency_ms,
                language="en-IN",
                metadata={"offline": True}
            )

            self.update_stats(result_obj, success=True)
            return result_obj

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"[STT Vosk] Transcription failed: {e}")

            result = TranscriptionResult(
                text="",
                confidence=0.0,
                is_final=True,
                provider=STTProvider.VOSK,
                latency_ms=latency_ms,
                metadata={"error": str(e)}
            )
            self.update_stats(result, success=False)

            raise RuntimeError(f"Vosk transcription failed: {e}") from e


# ── Mock Provider (Demo Mode) ─────────────────────────────────────────────────

class MockSTTProvider(STTProviderBase):
    """Mock STT provider for testing (fallback 3, always works)."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self._mock_responses = [
            "Show me pending approvals",
            "What are my trips this month",
            "Approve John's Mumbai trip",
            "How much have we spent on travel",
            "Create a new trip to Delhi",
            "Cancel my Bangalore trip",
            "What's my schedule today",
            "Send SOS alert",
        ]
        self._response_index = 0

    def _check_configuration(self) -> bool:
        """Mock provider is always available."""
        return True

    def get_provider_name(self) -> STTProvider:
        return STTProvider.MOCK

    async def transcribe(self, audio_data: bytes, mime_type: str = "audio/webm") -> TranscriptionResult:
        """Return mock transcription for testing."""
        start_time = time.time()

        # Simulate processing time
        await asyncio.sleep(0.15)  # 150ms latency

        # Cycle through mock responses
        transcript = self._mock_responses[self._response_index]
        self._response_index = (self._response_index + 1) % len(self._mock_responses)

        latency_ms = (time.time() - start_time) * 1000

        logger.info(
            f"[STT Mock] 🎭 Mock transcription: '{transcript}' "
            f"(demo mode, latency: {latency_ms:.0f}ms)"
        )

        result = TranscriptionResult(
            text=transcript,
            confidence=0.95,  # High mock confidence
            is_final=True,
            provider=STTProvider.MOCK,
            latency_ms=latency_ms,
            language="en-IN",
            metadata={"mock": True, "note": "Demo mode - not real transcription"}
        )

        self.update_stats(result, success=True)
        return result


# ── Main Speech Service ───────────────────────────────────────────────────────

class SpeechToTextService:
    """
    Multi-tier Speech-to-Text service with automatic fallback.

    This service tries providers in order until one succeeds:
        1. Google STT or Deepgram (based on OTIS_STT_PROVIDER)
        2. Remaining cloud fallback
        3. Vosk (offline, decent quality)
        4. Mock (demo mode, always works)

    Features:
        - Automatic provider selection
        - Graceful degradation
        - Retry with exponential backoff
        - Comprehensive statistics
        - Works offline
        - Demo mode for testing

    Usage:
        >>> service = SpeechToTextService()
        >>> result = await service.transcribe(audio_data)
        >>> print(result.text, result.provider)
    """

    def __init__(self):
        """Initialize STT service with all available providers."""
        self._providers: List[STTProviderBase] = []
        self._active_provider: Optional[STTProviderBase] = None
        self._status = STTStatus.IDLE

        # Initialize all providers
        config = {}

        logger.info("[STT Service] Initializing speech-to-text providers...")

        preferred = (Config.OTIS_STT_PROVIDER or "deepgram").strip().lower()
        deepgram = DeepgramProvider(config)
        google = GoogleSTTProvider(config)

        if preferred == "google":
            ordered_cloud = [
                ("Google STT", google, "primary"),
                ("Deepgram", deepgram, "fallback 1"),
            ]
        else:
            ordered_cloud = [
                ("Deepgram", deepgram, "primary"),
                ("Google STT", google, "fallback 1"),
            ]

        for label, provider, role in ordered_cloud:
            if provider.is_configured:
                self._providers.append(provider)
                logger.info("[STT Service]   ✅ %s (%s)", label, role)
            else:
                logger.info("[STT Service]   ⏭️  %s (not configured)", label)

        # Try Vosk (offline)
        vosk = VoskProvider(config)
        if vosk.is_configured:
            self._providers.append(vosk)
            logger.info("[STT Service]   ✅ Vosk (offline fallback)")
        else:
            logger.info("[STT Service]   ⏭️  Vosk (model not found)")

        # Always add Mock provider (guaranteed to work)
        mock = MockSTTProvider(config)
        self._providers.append(mock)
        logger.info("[STT Service]   ✅ Mock (demo mode)")

        if not self._providers:
            raise RuntimeError("No STT providers available!")

        # Set active provider to first available
        self._active_provider = self._providers[0]

        logger.info(
            f"[STT Service] Initialized with {len(self._providers)} provider(s). "
            f"Active: {self._active_provider.get_provider_name().value}"
        )

        # Warm up the active cloud STT provider in the background so the first
        # real user request reuses an established connection.
        self._warmup_primary()

    def _warmup_primary(self):
        """Send a tiny silent clip to the active cloud provider to warm it up."""
        import threading
        import struct
        import wave
        import io

        provider = self._active_provider
        if not provider or provider.get_provider_name() not in {
            STTProvider.DEEPGRAM,
            STTProvider.GOOGLE,
        }:
            return

        def _run():
            try:
                # Build 200 ms of silence as a WAV. Both active cloud providers accept it.
                sample_rate = 16000
                num_samples = int(sample_rate * 0.2)
                pcm = struct.pack(f"{num_samples}h", *([0] * num_samples))
                buf = io.BytesIO()
                with wave.open(buf, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(sample_rate)
                    w.writeframes(pcm)
                audio_bytes = buf.getvalue()

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(provider.transcribe(audio_bytes, "audio/wav"))
                loop.close()
                logger.info(
                    "[STT Service] %s connection warmed up",
                    provider.get_provider_name().value,
                )
            except Exception as e:
                logger.debug("[STT Service] Warmup failed (non-critical): %s", e)

        threading.Thread(target=_run, daemon=True, name="stt-warmup").start()

    async def transcribe(
        self,
        audio_data: bytes,
        mime_type: str = "audio/webm",
        max_retries: int = 2,
        preferred_provider: Optional[STTProvider] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio to text with automatic fallback.

        Args:
            audio_data: Raw audio bytes from the browser
            mime_type: MIME type of the audio (e.g. "audio/webm", "audio/wav")
            max_retries: Maximum retries per provider (default: 2)
            preferred_provider: Try this provider first (optional)

        Returns:
            TranscriptionResult with transcribed text

        Raises:
            RuntimeError: If all providers fail
        """
        self._status = STTStatus.TRANSCRIBING

        # Reorder providers if preferred specified
        providers = self._providers.copy()
        if preferred_provider:
            providers.sort(
                key=lambda p: 0 if p.get_provider_name() == preferred_provider else 1
            )

        last_error = None
        # Track the first empty result from a real (non-mock) provider so we
        # can return it instead of falling through to fake mock responses.
        first_real_empty: Optional[TranscriptionResult] = None

        # Try each provider
        for provider in providers:
            if not provider.is_configured:
                continue

            is_mock = provider.get_provider_name() == STTProvider.MOCK

            logger.debug(
                f"[STT Service] Attempting transcription with: "
                f"{provider.get_provider_name().value}"
            )

            # Try with retries
            for attempt in range(max_retries):
                try:
                    result = await provider.transcribe(audio_data, mime_type)

                    if result.text:  # Got a real transcript
                        self._active_provider = provider
                        self._status = STTStatus.IDLE

                        logger.info(
                            f"[STT Service] ✅ Transcribed successfully with "
                            f"{result.provider.value} (attempt {attempt + 1}/{max_retries})"
                        )

                        return result

                    # Empty transcript — real providers return empty for silence;
                    # don't fall through to Mock (it returns fake canned text).
                    if not is_mock and first_real_empty is None:
                        first_real_empty = result

                    logger.info(
                        f"[STT Service] Empty transcription from "
                        f"{provider.get_provider_name().value} — audio may be silent"
                    )
                    break  # No point retrying an empty (not an error)

                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"[STT Service] {provider.get_provider_name().value} failed "
                        f"(attempt {attempt + 1}/{max_retries}): {e}"
                    )

                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.1 * (2 ** attempt))
                        continue
                    break

            # If a real provider already answered (even with empty), stop here —
            # do not hand off to Mock which would return fake canned text.
            if first_real_empty is not None:
                self._status = STTStatus.IDLE
                return first_real_empty

        # All providers failed with exceptions
        self._status = STTStatus.ERROR
        error_msg = f"All STT providers failed. Last error: {last_error}"
        logger.error(f"[STT Service] ❌ {error_msg}")
        raise RuntimeError(error_msg)

    def get_active_provider(self) -> STTProvider:
        """Get currently active STT provider."""
        return self._active_provider.get_provider_name() if self._active_provider else None

    def get_available_providers(self) -> List[STTProvider]:
        """Get list of available (configured) providers."""
        return [p.get_provider_name() for p in self._providers if p.is_configured]

    def get_statistics(self) -> Dict:
        """Get comprehensive statistics for all providers."""
        stats = {
            "active_provider": self.get_active_provider().value if self._active_provider else None,
            "status": self._status.value,
            "providers": {}
        }

        for provider in self._providers:
            provider_stats = provider.get_stats()
            stats["providers"][provider.get_provider_name().value] = provider_stats

        return stats

    def is_available(self) -> bool:
        """Check if any STT provider is available."""
        return len(self._providers) > 0

    def get_status(self) -> STTStatus:
        """Get current service status."""
        return self._status


# ── Utility Functions ─────────────────────────────────────────────────────────

async def test_stt_service():
    """Test STT service with sample audio or microphone."""
    print("=" * 70)
    print("OTIS Speech-to-Text - Interactive Test")
    print("=" * 70)

    # Initialize service
    print("\n🔧 Initializing STT service...")
    service = SpeechToTextService()

    print(f"\n✅ Service initialized!")
    print(f"   Active provider: {service.get_active_provider().value}")
    print(f"   Available providers: {[p.value for p in service.get_available_providers()]}")

    # Get statistics
    stats = service.get_statistics()
    print("\n📊 Provider Status:")
    for provider_name, provider_stats in stats["providers"].items():
        configured = "✅" if provider_stats["total_requests"] == 0 else "📊"
        print(f"   {configured} {provider_name}")

    print("\n" + "=" * 70)
    print("Testing with mock audio data...")
    print("=" * 70)

    # Create dummy audio data (silence)
    import struct
    sample_rate = 16000
    duration_seconds = 2
    num_samples = sample_rate * duration_seconds

    # Generate silence (16-bit PCM)
    audio_data = struct.pack(f"{num_samples}h", *[0] * num_samples)

    print(f"\n🎤 Transcribing {duration_seconds}s of audio...")

    try:
        result = await service.transcribe(audio_data)

        print(f"\n✅ Transcription successful!")
        print(f"   Provider: {result.provider.value}")
        print(f"   Text: '{result.text}'")
        print(f"   Confidence: {result.confidence:.2%}")
        print(f"   Latency: {result.latency_ms:.0f}ms")
        print(f"   Language: {result.language}")

        if result.alternatives:
            print(f"   Alternatives: {result.alternatives}")

    except Exception as e:
        print(f"\n❌ Transcription failed: {e}")

    # Final statistics
    print("\n📊 Final Statistics:")
    final_stats = service.get_statistics()
    for provider_name, provider_stats in final_stats["providers"].items():
        if provider_stats["total_requests"] > 0:
            print(f"\n   {provider_name}:")
            print(f"      Total requests: {provider_stats['total_requests']}")
            print(f"      Success rate: {provider_stats['success_rate']:.1%}")
            print(f"      Avg latency: {provider_stats['avg_latency_ms']:.0f}ms")
            print(f"      Avg confidence: {provider_stats['avg_confidence']:.2%}")

    print("\n✅ Test complete!")
    print("=" * 70)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(test_stt_service())
