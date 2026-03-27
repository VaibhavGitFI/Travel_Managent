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

logger = logging.getLogger(__name__)


class TTSProvider(Enum):
    """Available TTS providers."""
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
            # Get voice ID from config (Indian English female by default)
            voice_id = Config.OTIS_VOICE_ID or "EXAVITQu4vr4xnSDxMaL"

            # Generate speech
            response = self._client.text_to_speech.convert(
                voice_id=voice_id,
                optimize_streaming_latency=4,  # Max optimization
                output_format="mp3_22050_32",  # 22.05kHz, 32kbps MP3
                text=text,
                model_id="eleven_turbo_v2_5",  # Fastest model
                voice_settings={
                    "stability": Config.OTIS_VOICE_STABILITY or 0.5,
                    "similarity_boost": Config.OTIS_VOICE_SIMILARITY or 0.75,
                    "style": 0.3,  # Professional style
                    "use_speaker_boost": True
                }
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
                    "model": "eleven_turbo_v2_5",
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


# ── Google TTS Provider ───────────────────────────────────────────────────────

class GoogleTTSProvider(TTSProviderBase):
    """Google Text-to-Speech provider (fallback 1)."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self._client = None
        if self.is_configured:
            self._initialize_google()

    def _check_configuration(self) -> bool:
        """Check if Google credentials are configured."""
        return bool(Config.GOOGLE_VISION_API_KEY)

    def _initialize_google(self):
        """Initialize Google TTS client."""
        try:
            from google.cloud import texttospeech

            os.environ["GOOGLE_API_KEY"] = Config.GOOGLE_VISION_API_KEY

            self._client = texttospeech.TextToSpeechClient()
            self._texttospeech = texttospeech

            logger.info("[TTS Google] ✅ Google Text-to-Speech initialized")
        except ImportError:
            logger.warning(
                "[TTS Google] google-cloud-texttospeech not installed. "
                "Install with: pip install google-cloud-texttospeech"
            )
            self.is_configured = False
        except Exception as e:
            logger.error(f"[TTS Google] Initialization failed: {e}")
            self.is_configured = False

    def get_provider_name(self) -> TTSProvider:
        return TTSProvider.GOOGLE

    async def synthesize(self, text: str) -> SpeechResult:
        """Synthesize speech using Google TTS."""
        if not self.is_configured:
            raise RuntimeError("Google TTS is not configured")

        start_time = time.time()

        try:
            # Set input text
            synthesis_input = self._texttospeech.SynthesisInput(text=text)

            # Configure voice (Indian English female)
            voice = self._texttospeech.VoiceSelectionParams(
                language_code="en-IN",
                name="en-IN-Wavenet-D",  # Indian English female
                ssml_gender=self._texttospeech.SsmlVoiceGender.FEMALE
            )

            # Configure audio
            audio_config = self._texttospeech.AudioConfig(
                audio_encoding=self._texttospeech.AudioEncoding.MP3,
                speaking_rate=Config.OTIS_VOICE_SPEED or 1.0,
                pitch=Config.OTIS_VOICE_PITCH or 0.0
            )

            # Synthesize
            response = self._client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )

            audio_data = response.audio_content

            latency_ms = (time.time() - start_time) * 1000

            # Estimate duration
            duration_seconds = len(audio_data) / (32000 / 8)

            logger.debug(
                f"[TTS Google] Synthesized {len(text)} chars "
                f"(latency: {latency_ms:.0f}ms)"
            )

            result = SpeechResult(
                audio_data=audio_data,
                text=text,
                provider=TTSProvider.GOOGLE,
                latency_ms=latency_ms,
                audio_format="mp3",
                sample_rate=24000,
                duration_seconds=duration_seconds,
                metadata={"voice": "en-IN-Wavenet-D"}
            )

            self.update_stats(result, success=True)
            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"[TTS Google] Synthesis failed: {e}")

            result = SpeechResult(
                audio_data=b"",
                text=text,
                provider=TTSProvider.GOOGLE,
                latency_ms=latency_ms,
                metadata={"error": str(e)}
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
                if 'indian' in voice.name.lower() or 'india' in voice.name.lower():
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
            import struct
            import math

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

            # Convert to WAV bytes (simplified WAV header)
            audio_data = struct.pack(f"{len(samples)}h", *samples)

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
                audio_format="raw_pcm",
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

    This service tries providers in order until one succeeds:
        1. ElevenLabs (best quality, human-like, Indian accent)
        2. Google TTS (good quality, Indian accent)
        3. pyttsx3 (offline, robotic but works)
        4. Beep (audio feedback, always works)

    Features:
        - Automatic provider selection
        - Graceful degradation
        - Works offline
        - Indian English accent
        - Always provides audio feedback

    Usage:
        >>> service = TextToSpeechService()
        >>> result = await service.speak("Hello from Otis!")
        >>> # Play result.audio_data
    """

    def __init__(self):
        """Initialize TTS service with all available providers."""
        self._providers: List[TTSProviderBase] = []
        self._active_provider: Optional[TTSProviderBase] = None

        logger.info("[TTS Service] Initializing text-to-speech providers...")

        # Initialize all providers
        config = {}

        # Try ElevenLabs first (best quality)
        elevenlabs = ElevenLabsProvider(config)
        if elevenlabs.is_configured:
            self._providers.append(elevenlabs)
            logger.info("[TTS Service]   ✅ ElevenLabs (primary)")
        else:
            logger.info("[TTS Service]   ⏭️  ElevenLabs (not configured)")

        # Try Google TTS
        google = GoogleTTSProvider(config)
        if google.is_configured:
            self._providers.append(google)
            logger.info("[TTS Service]   ✅ Google TTS (fallback 1)")
        else:
            logger.info("[TTS Service]   ⏭️  Google TTS (not configured)")

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

        # Reorder providers if preferred specified
        providers = self._providers.copy()
        if preferred_provider:
            providers.sort(
                key=lambda p: 0 if p.get_provider_name() == preferred_provider else 1
            )

        last_error = None

        # Try each provider
        for provider in providers:
            if not provider.is_configured:
                continue

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
                    logger.warning(
                        f"[TTS Service] {provider.get_provider_name().value} failed "
                        f"(attempt {attempt + 1}/{max_retries}): {e}"
                    )

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
