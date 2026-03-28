"""
OTIS Voice Agent - Wake Word Detection Service
Dual-backend: Porcupine (Picovoice) or OpenWakeWord, selected automatically.

Selection logic:
    • PORCUPINE_ACCESS_KEY is set  → use Picovoice Porcupine (high accuracy, paid)
    • No key                       → use OpenWakeWord (open-source, free, no key needed)

Switching backends requires only adding / removing PORCUPINE_ACCESS_KEY from backend/.env.
No code changes needed.

Custom "Hey Otis" wake word:
    Porcupine  → train at https://console.picovoice.ai/, set OTIS_WAKE_WORD_MODEL to .ppn path
    OpenWakeWord → train at https://github.com/dscripka/openWakeWord, set OTIS_WAKE_WORD_MODEL to .onnx path
    Default fallback for both backends: built-in "jarvis" / "hey_jarvis" keyword
"""

import sys
import os
import logging
import threading
import time
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# OpenWakeWord standard chunk = 80 ms at 16 kHz
OWW_FRAME_LENGTH = 1280
# Porcupine standard chunk = 512 samples at 16 kHz
PORCUPINE_FRAME_LENGTH = 512
SAMPLE_RATE = 16000


# ── Status enum (shared) ───────────────────────────────────────────────────────

class WakeWordStatus(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    DETECTED = "detected"
    ERROR = "error"
    STOPPED = "stopped"


# ── Config dataclass ───────────────────────────────────────────────────────────

@dataclass
class WakeWordConfig:
    """Unified configuration for either backend."""
    access_key: str = ""          # Porcupine access key (empty → use OpenWakeWord)
    model_path: str = ""          # Custom .ppn (Porcupine) or .onnx (OpenWakeWord) file
    keyword: str = "Hey Otis"     # Human-readable label
    threshold: float = 0.5        # Sensitivity / detection threshold (0.0–1.0)
    sample_rate: int = SAMPLE_RATE
    frame_length: int = OWW_FRAME_LENGTH  # Updated after backend init

    def __post_init__(self):
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"threshold must be 0.0–1.0, got {self.threshold}")

    @property
    def backend(self) -> str:
        return "porcupine" if self.access_key else "openwakeword"


# ── Main service ───────────────────────────────────────────────────────────────

class WakeWordService:
    """
    Wake word detection service with automatic backend selection.

    With Porcupine (requires PORCUPINE_ACCESS_KEY):
        - <100 ms latency, <0.01 % false-positive rate
        - Needs free key from https://console.picovoice.ai/

    With OpenWakeWord (no key required):
        - Fully offline, open-source
        - Slightly lower accuracy; good enough for most use cases

    Usage:
        >>> service = WakeWordService()
        >>> service.start_listening(on_wake_word_detected=lambda: print("Otis!"))
        >>> # feed 1280-byte audio frames via process_audio_frame()
        >>> service.cleanup()
    """

    def __init__(self, config: Optional[WakeWordConfig] = None):
        if config is None:
            config = self._load_config_from_env()
        self.config = config

        self._engine = None        # Porcupine engine OR OpenWakeWord Model
        self._status = WakeWordStatus.IDLE
        self._callbacks = []
        self._lock = threading.Lock()
        self._detection_count = 0
        self._false_positive_count = 0
        self._last_detection_time = None

        if self.config.backend == "porcupine":
            self._init_porcupine()
        else:
            self._init_openwakeword()

        logger.info(
            f"[OTIS Wake Word] Initialized with backend='{self.config.backend}', "
            f"keyword='{self.config.keyword}', threshold={self.config.threshold}, "
            f"frame_length={self.config.frame_length}"
        )

    # ── Config loading ─────────────────────────────────────────────────────────

    @staticmethod
    def _load_config_from_env() -> WakeWordConfig:
        return WakeWordConfig(
            access_key=Config.PORCUPINE_ACCESS_KEY or "",
            model_path=os.getenv("OTIS_WAKE_WORD_MODEL", ""),
            keyword=Config.OTIS_WAKE_WORD or "Hey Otis",
            threshold=float(os.getenv("OTIS_WAKE_WORD_SENSITIVITY", "0.5")),
        )

    # ── Backend: Porcupine ─────────────────────────────────────────────────────

    def _init_porcupine(self):
        try:
            import pvporcupine as pv
        except ImportError:
            raise ImportError(
                "pvporcupine is not installed. "
                "Run: pip install pvporcupine  OR  remove PORCUPINE_ACCESS_KEY to use OpenWakeWord."
            )

        try:
            custom = self.config.model_path and os.path.isfile(self.config.model_path)
            if custom:
                logger.info(f"[OTIS Wake Word] Porcupine: loading custom model {self.config.model_path}")
                self._engine = pv.create(
                    access_key=self.config.access_key,
                    keyword_paths=[self.config.model_path],
                    sensitivities=[self.config.threshold],
                )
            else:
                # Fall back to built-in keyword until custom 'Hey Otis' model is trained
                logger.info(
                    "[OTIS Wake Word] Porcupine: no custom model — using built-in 'jarvis'. "
                    "Train a custom model at https://console.picovoice.ai/ and set OTIS_WAKE_WORD_MODEL."
                )
                self._engine = pv.create(
                    access_key=self.config.access_key,
                    keywords=["jarvis"],
                    sensitivities=[self.config.threshold],
                )

            self.config.sample_rate = self._engine.sample_rate
            self.config.frame_length = self._engine.frame_length
            self._status = WakeWordStatus.IDLE

        except Exception as e:
            self._status = WakeWordStatus.ERROR
            raise RuntimeError(f"Porcupine init failed: {e}") from e

    # ── Backend: OpenWakeWord ──────────────────────────────────────────────────

    def _init_openwakeword(self):
        try:
            from openwakeword.model import Model as OWWModel
        except ImportError:
            raise ImportError(
                "openwakeword is not installed. "
                "Run: pip install openwakeword"
            )

        try:
            custom = self.config.model_path and os.path.isfile(self.config.model_path)
            if custom:
                models = [self.config.model_path]
                logger.info(f"[OTIS Wake Word] OpenWakeWord: loading custom model {self.config.model_path}")
            else:
                models = ["hey_jarvis"]
                logger.info(
                    "[OTIS Wake Word] OpenWakeWord: no custom model — using built-in 'hey_jarvis'. "
                    "Say 'Hey Jarvis' to activate OTIS for now. "
                    "Train a custom model and set OTIS_WAKE_WORD_MODEL=/path/to/hey_otis.onnx."
                )

            self._engine = OWWModel(wakeword_models=models, inference_framework="onnx")
            self.config.frame_length = OWW_FRAME_LENGTH
            self._status = WakeWordStatus.IDLE

        except Exception as e:
            self._status = WakeWordStatus.ERROR
            raise RuntimeError(f"OpenWakeWord init failed: {e}") from e

    # ── Core detection ─────────────────────────────────────────────────────────

    def process_audio_frame(self, audio_frame: bytes) -> bool:
        """
        Feed one audio chunk; returns True if the wake word is detected.

        Args:
            audio_frame: Raw 16-bit PCM bytes.
                         Must be exactly frame_length * 2 bytes.
        """
        with self._lock:
            if self._status != WakeWordStatus.LISTENING:
                return False

            expected = self.config.frame_length * 2
            if len(audio_frame) != expected:
                raise ValueError(
                    f"Wrong frame size: expected {expected} bytes "
                    f"({self.config.frame_length} samples), got {len(audio_frame)}"
                )

            try:
                detected = (
                    self._process_porcupine(audio_frame)
                    if self.config.backend == "porcupine"
                    else self._process_oww(audio_frame)
                )
                if detected:
                    self._on_wake_word_detected()
                return detected

            except Exception as e:
                logger.error(f"[OTIS Wake Word] Frame processing error: {e}")
                self._status = WakeWordStatus.ERROR
                raise RuntimeError(f"Audio processing failed: {e}") from e

    def _process_porcupine(self, audio_frame: bytes) -> bool:
        import struct
        pcm = struct.unpack(f"{self.config.frame_length}h", audio_frame)
        return self._engine.process(pcm) >= 0

    def _process_oww(self, audio_frame: bytes) -> bool:
        import numpy as np
        pcm = np.frombuffer(audio_frame, dtype=np.int16)
        predictions = self._engine.predict(pcm)
        return any(score >= self.config.threshold for score in predictions.values())

    # ── Wake word callback ─────────────────────────────────────────────────────

    def _on_wake_word_detected(self):
        now = time.time()
        if self._last_detection_time and (now - self._last_detection_time) < 1.0:
            self._false_positive_count += 1
            return

        self._detection_count += 1
        self._last_detection_time = now
        self._status = WakeWordStatus.DETECTED

        logger.info(f"[OTIS Wake Word] Wake word detected! (#{self._detection_count})")

        for cb in self._callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"[OTIS Wake Word] Callback error: {e}", exc_info=True)

        self._status = WakeWordStatus.LISTENING

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def register_callback(self, callback: Callable[[], None]):
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[], None]):
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def start_listening(self, on_wake_word_detected: Optional[Callable[[], None]] = None):
        with self._lock:
            if self._status == WakeWordStatus.ERROR:
                raise RuntimeError("Service is in error state.")
            if on_wake_word_detected:
                self.register_callback(on_wake_word_detected)
            self._status = WakeWordStatus.LISTENING
            logger.info(f"[OTIS Wake Word] Listening ({self.config.backend})...")

    def stop_listening(self):
        with self._lock:
            self._status = WakeWordStatus.IDLE
            logger.info("[OTIS Wake Word] Stopped listening")

    def cleanup(self):
        with self._lock:
            self._status = WakeWordStatus.STOPPED
            self._callbacks.clear()
            if self._engine is not None:
                if self.config.backend == "porcupine":
                    try:
                        self._engine.delete()
                    except Exception:
                        pass
                self._engine = None
            logger.info("[OTIS Wake Word] Cleanup complete")

    # ── Introspection ──────────────────────────────────────────────────────────

    def get_statistics(self) -> dict:
        with self._lock:
            return {
                "status": self._status.value,
                "backend": self.config.backend,
                "total_detections": self._detection_count,
                "false_positives": self._false_positive_count,
                "last_detection_time": self._last_detection_time,
                "configured_keyword": self.config.keyword,
                "threshold": self.config.threshold,
                "sample_rate": self.config.sample_rate,
                "frame_length": self.config.frame_length,
            }

    def reset_statistics(self):
        with self._lock:
            self._detection_count = 0
            self._false_positive_count = 0
            self._last_detection_time = None

    def is_listening(self) -> bool:
        return self._status == WakeWordStatus.LISTENING

    def get_status(self) -> WakeWordStatus:
        return self._status

    # ── Context manager ────────────────────────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()

    def __del__(self):
        try:
            if getattr(self, "_engine", None) is not None:
                self.cleanup()
        except Exception:
            pass
