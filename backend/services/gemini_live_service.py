"""
TravelSync Pro — Gemini Live API Service
Real-time bidirectional voice: integrated STT + LLM + TTS in one streaming call.
Replaces the ElevenLabs (TTS) + Deepgram (STT) pipeline for OTIS.

Features:
  • < 500ms first-audio latency (single API call, no chaining)
  • Barge-in: user can interrupt OTIS mid-sentence
  • Indian English voice (Puck — clear, natural)
  • Input + output transcription for display
  • Graceful fallback to google-generativeai for one-shot transcription

Requires:  pip install google-genai
Models:
  Primary   — gemini-live-2.5-flash-preview-native-audio-dialog
  Fallback  — gemini-2.0-flash-live-001

WebSocket event contract (frontend unchanged):
  send:  otis:audio_chunk  {session_id, audio (b64), is_final}
  recv:  otis:transcript   {session_id, text}          ← what user said
         otis:response     {session_id, response}      ← OTIS text reply
         otis:audio_ready  {session_id, audio_b64, mime_type}
         otis:turn_complete{session_id}
         otis:barge_in     {session_id}
         otis:error        {error}
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import queue
import tempfile
import threading
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

# ── Model names ───────────────────────────────────────────────────────────────
_LIVE_MODEL_PRIMARY  = "gemini-live-2.5-flash-preview-native-audio-dialog"
_LIVE_MODEL_FALLBACK = "gemini-2.0-flash-live-001"

# ── Available Gemini Live voices ──────────────────────────────────────────────
# For Indian English: Puck (energetic/clear), Charon (calm), Kore (warm)
OTIS_VOICES = {
    "puck":   "Puck",
    "charon": "Charon",
    "kore":   "Kore",
    "fenrir": "Fenrir",
    "aoede":  "Aoede",
}
_DEFAULT_VOICE = "Puck"

# Audio: browser sends 16kHz mono PCM (standard MediaRecorder output)
_INPUT_MIME  = "audio/pcm;rate=16000"
_OUTPUT_MIME = "audio/pcm;rate=24000"   # Gemini Live output rate


# ─────────────────────────────────────────────────────────────────────────────
#  GeminiLiveSession — one voice conversation
# ─────────────────────────────────────────────────────────────────────────────

class GeminiLiveSession:
    """
    Wraps one Gemini Live API connection for an OTIS session.

    Thread model:
      SocketIO thread  → send_audio() → _audio_queue
      Live thread      → _thread_main() → asyncio event loop
                       → _receive_loop() → on_event() callback
                       → SocketIO emits via socketio.emit(room=...)
    """

    def __init__(
        self,
        session_id: str,
        api_key: str,
        system_prompt: str,
        voice_name: str = _DEFAULT_VOICE,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        self.session_id  = session_id
        self._api_key    = api_key
        self._prompt     = system_prompt
        self._voice      = voice_name
        self._on_event   = on_event

        self._audio_q: queue.Queue = queue.Queue(maxsize=300)
        self._running  = False
        self._thread: Optional[threading.Thread] = None
        self._text_buf: list[str] = []      # accumulates streamed text tokens

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._thread_main,
            name=f"otis-live-{self.session_id[:8]}",
            daemon=True,
        )
        self._thread.start()
        logger.info("[GeminiLive] Session %s started (voice=%s)", self.session_id[:12], self._voice)

    def stop(self) -> None:
        self._running = False
        # Unblock the send loop
        try:
            self._audio_q.put_nowait(None)
        except queue.Full:
            pass
        logger.info("[GeminiLive] Session %s stopping", self.session_id[:12])

    def send_audio(self, audio_bytes: bytes) -> None:
        """Queue raw PCM audio for streaming to Gemini. Non-blocking."""
        if not self._running:
            return
        try:
            self._audio_q.put_nowait(audio_bytes)
        except queue.Full:
            # Ring-buffer: drop oldest frame, keep newest
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._audio_q.put_nowait(audio_bytes)
            except queue.Full:
                pass

    def is_alive(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    # ── Thread / async machinery ──────────────────────────────────────────────

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_main())
        except Exception as exc:
            logger.error("[GeminiLive] %s thread crashed: %s", self.session_id[:12], exc)
            self._notify("error", {"message": str(exc)})
        finally:
            self._running = False
            try:
                loop.close()
            except Exception:
                pass

    async def _async_main(self) -> None:
        try:
            from google import genai          # google-genai package
            from google.genai import types
        except ImportError:
            logger.error("[GeminiLive] google-genai not installed. Run: pip install google-genai")
            self._notify("error", {"message": "google-genai package not installed. Run: pip install google-genai"})
            return

        client = genai.Client(api_key=self._api_key)

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO", "TEXT"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self._voice
                    )
                )
            ),
            system_instruction=self._prompt,
        )

        # Try primary model; fall back to older one on failure
        for model in (_LIVE_MODEL_PRIMARY, _LIVE_MODEL_FALLBACK):
            try:
                async with client.aio.live.connect(model=model, config=config) as sess:
                    logger.info("[GeminiLive] Connected: model=%s voice=%s", model, self._voice)
                    self._notify("connected", {"model": model, "voice": self._voice})
                    await asyncio.gather(
                        self._send_loop(sess),
                        self._receive_loop(sess),
                    )
                return  # clean exit
            except Exception as exc:
                logger.warning("[GeminiLive] Model %s failed: %s", model, exc)
                if model == _LIVE_MODEL_FALLBACK:
                    self._notify("error", {"message": f"Gemini Live unavailable: {exc}"})

    async def _send_loop(self, session) -> None:
        """Pull audio chunks from queue, send to Gemini Live."""
        from google.genai import types
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                chunk = await loop.run_in_executor(
                    None,
                    lambda: self._audio_q.get(timeout=0.05),
                )
                if chunk is None:          # stop sentinel
                    break
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type=_INPUT_MIME)
                )
            except queue.Empty:
                continue
            except Exception as exc:
                if self._running:
                    logger.debug("[GeminiLive] Send error: %s", exc)
                break

    async def _receive_loop(self, session) -> None:
        """Receive and dispatch Gemini Live responses."""
        try:
            async for response in session.receive():
                if not self._running:
                    break
                self._handle_response(response)
        except Exception as exc:
            if self._running:
                logger.error("[GeminiLive] Receive error: %s", exc)
                self._notify("error", {"message": str(exc)})

    def _handle_response(self, response) -> None:
        """Parse one Gemini Live response object and fire callbacks."""

        # ── Input transcription (what the user said) ──────────────────────
        it = getattr(response, "input_transcription", None)
        if it:
            text = getattr(it, "text", None) or ""
            if text:
                self._notify("transcript", {"text": text})

        # ── Server content ─────────────────────────────────────────────────
        sc = getattr(response, "server_content", None)
        if sc:
            # Barge-in: model was interrupted by user
            if getattr(sc, "interrupted", False):
                self._text_buf.clear()
                self._notify("barge_in", {})

            # Model turn parts (text tokens + audio chunks)
            mt = getattr(sc, "model_turn", None)
            if mt:
                for part in getattr(mt, "parts", []):
                    token = getattr(part, "text", None)
                    if token:
                        self._text_buf.append(token)
                        self._notify("text_token", {"token": token})

                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        audio_b64 = base64.b64encode(inline.data).decode()
                        mime = getattr(inline, "mime_type", _OUTPUT_MIME)
                        self._notify("audio_chunk", {
                            "audio_b64": audio_b64,
                            "mime_type": mime,
                        })

            # Turn complete — flush buffered text as the full response
            if getattr(sc, "turn_complete", False):
                if self._text_buf:
                    full = "".join(self._text_buf).strip()
                    if full:
                        self._notify("response", {"text": full})
                    self._text_buf.clear()
                self._notify("turn_complete", {})

        # ── Output transcription (what OTIS said, if TTS) ─────────────────
        ot = getattr(response, "output_transcription", None)
        if ot:
            text = getattr(ot, "text", None) or ""
            if text:
                self._notify("output_transcript", {"text": text})

        # ── Raw data (older SDK versions expose audio here) ────────────────
        raw = getattr(response, "data", None)
        if raw:
            audio_b64 = base64.b64encode(raw).decode()
            self._notify("audio_chunk", {"audio_b64": audio_b64, "mime_type": _OUTPUT_MIME})

        # ── Text (older SDK versions) ──────────────────────────────────────
        txt = getattr(response, "text", None)
        if txt and txt not in ("", None):
            self._notify("response", {"text": txt})

    def _notify(self, event_type: str, data: dict) -> None:
        if self._on_event:
            try:
                self._on_event(event_type, data)
            except Exception as exc:
                logger.error("[GeminiLive] Callback error (%s): %s", event_type, exc)


# ─────────────────────────────────────────────────────────────────────────────
#  GeminiLiveService — singleton, manages all sessions
# ─────────────────────────────────────────────────────────────────────────────

class GeminiLiveService:
    """
    Manages all active GeminiLiveSession objects (one per OTIS WebSocket session).
    Also provides one-shot transcription and TTS for REST endpoints.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.configured = bool(self.api_key)
        self._sdk_available = self._probe_sdk()
        self._sessions: Dict[str, GeminiLiveSession] = {}

        status = "ready" if self.live_available else (
            "no SDK (pip install google-genai)" if self.configured else "no GEMINI_API_KEY"
        )
        logger.info("[GeminiLive] Service initialised — %s", status)

    # ── SDK probe ─────────────────────────────────────────────────────────────

    @staticmethod
    def _probe_sdk() -> bool:
        try:
            from google import genai  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def live_available(self) -> bool:
        """True only when both API key and google-genai SDK are present."""
        return self.configured and self._sdk_available

    # ── Session management ────────────────────────────────────────────────────

    def create_session(
        self,
        session_id: str,
        system_prompt: str,
        on_event: Callable[[str, dict], None],
        voice_name: str = _DEFAULT_VOICE,
    ) -> Optional[GeminiLiveSession]:
        """Create (or replace) a Live API session."""
        if not self.live_available:
            return None

        self.stop_session(session_id)  # clean up any existing session

        sess = GeminiLiveSession(
            session_id=session_id,
            api_key=self.api_key,
            system_prompt=system_prompt,
            voice_name=voice_name,
            on_event=on_event,
        )
        sess.start()
        self._sessions[session_id] = sess
        return sess

    def send_audio(self, session_id: str, audio_bytes: bytes) -> bool:
        """Forward audio bytes to a running session. Returns True if sent."""
        sess = self._sessions.get(session_id)
        if sess and sess.is_alive():
            sess.send_audio(audio_bytes)
            return True
        return False

    def stop_session(self, session_id: str) -> None:
        sess = self._sessions.pop(session_id, None)
        if sess:
            sess.stop()

    def get_session(self, session_id: str) -> Optional[GeminiLiveSession]:
        return self._sessions.get(session_id)

    def session_alive(self, session_id: str) -> bool:
        sess = self._sessions.get(session_id)
        return sess is not None and sess.is_alive()

    # ── One-shot transcription (REST endpoint) ─────────────────────────────────

    def transcribe_audio_inline(self, audio_bytes: bytes, mime_type: str = "audio/webm;codecs=opus") -> dict:
        """
        Transcribe audio using Gemini inline data (NO file upload).
        Passes audio directly in the request body — ~1-2s vs 5-8s for file upload.
        """
        if not self.configured:
            return {"transcript": "", "success": False, "error": "GEMINI_API_KEY not set"}
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            audio_b64 = base64.b64encode(audio_bytes).decode()
            response = model.generate_content([
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": audio_b64
                    }
                },
                "Transcribe this audio exactly as spoken. Detect the language automatically. Return ONLY the spoken words — no labels, no explanations. If you cannot hear anything, return empty string."
            ])
            text = (response.text or "").strip()
            return {"transcript": text, "model": "gemini-2.0-flash-inline", "success": bool(text)}
        except Exception as exc:
            logger.warning("[GeminiLive] Inline transcription error: %s", exc)
            return {"transcript": "", "success": False, "error": str(exc)}

    def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> dict:
        """Transcribe audio — tries inline first (fast), falls back to file upload."""
        result = self.transcribe_audio_inline(audio_bytes, mime_type)
        if result.get("success"):
            return result

        # Fallback: file-upload API (slower but more robust for unusual formats)
        if not self.configured:
            return {"transcript": "", "model": "none", "success": False,
                    "error": "GEMINI_API_KEY not set"}
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")

            # Pick extension from mime type
            ext_map = {"wav": "wav", "ogg": "ogg", "mp4": "m4a", "m4a": "m4a", "webm": "webm"}
            ext = "webm"
            for k, v in ext_map.items():
                if k in mime_type:
                    ext = v
                    break

            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
                f.write(audio_bytes)
                tmp = f.name

            uploaded = None
            try:
                uploaded = genai.upload_file(tmp, mime_type=mime_type)
                resp = model.generate_content([
                    "Transcribe the audio exactly as spoken. Output ONLY the spoken words, no labels.",
                    uploaded,
                ])
                text = (resp.text or "").strip()
                return {"transcript": text, "model": "gemini-2.0-flash", "success": True}
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
                if uploaded:
                    try:
                        genai.delete_file(uploaded.name)
                    except Exception:
                        pass

        except Exception as exc:
            logger.warning("[GeminiLive] Transcription error: %s", exc)
            return {"transcript": "", "model": "error", "success": False, "error": str(exc)}

    # ── One-shot TTS (REST endpoint) ────────────────────────────────────────────

    def synthesize_speech(self, text: str, language_code: str = "en-IN") -> Optional[bytes]:
        """
        TTS with automatic fallback chain:
          1. Google Cloud TTS (best quality, needs Cloud TTS API enabled)
          2. Gemini TTS via google-genai SDK (works with just GEMINI_API_KEY)
        """
        # Try Google Cloud TTS first
        audio = self._tts_google_cloud(text, language_code)
        if audio:
            return audio

        # Fallback: Gemini TTS (works with just GEMINI_API_KEY)
        audio = self._tts_gemini(text)
        if audio:
            return audio

        logger.warning("[GeminiLive] All TTS methods failed for: '%s'", text[:40])
        return None

    def _tts_google_cloud(self, text: str, language_code: str = "en-IN") -> Optional[bytes]:
        """TTS via Google Cloud TTS API. Returns MP3 bytes or None."""
        api_key = (
            os.getenv("GOOGLE_TTS_API_KEY")
            or os.getenv("GOOGLE_VISION_API_KEY")
            or os.getenv("GOOGLE_MAPS_API_KEY")
        )
        if not api_key:
            return None

        voice_map = {
            "en-IN": ("en-IN-Neural2-B", "MALE"),
            "hi-IN": ("hi-IN-Neural2-B", "MALE"),
            "ta-IN": ("ta-IN-Neural2-A", "FEMALE"),
            "te-IN": ("te-IN-Standard-A", "FEMALE"),
            "kn-IN": ("kn-IN-Standard-A", "FEMALE"),
            "ml-IN": ("ml-IN-Standard-A", "FEMALE"),
            "gu-IN": ("gu-IN-Standard-A", "FEMALE"),
            "bn-IN": ("bn-IN-Standard-A", "FEMALE"),
        }
        voice_name, gender = voice_map.get(language_code, ("en-IN-Neural2-B", "MALE"))

        try:
            from services.http_client import http as _req
            payload = {
                "input": {"text": text[:4500]},
                "voice": {
                    "languageCode": language_code,
                    "name": voice_name,
                    "ssmlGender": gender,
                },
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": 1.05,
                    "pitch": 0.0,
                    "effectsProfileId": ["telephony-class-application"],
                },
            }
            resp = _req.post(
                f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}",
                json=payload, timeout=10
            )
            if resp.status_code == 200:
                content = resp.json().get("audioContent", "")
                if content:
                    return base64.b64decode(content)
            else:
                logger.debug("[GeminiLive] Google Cloud TTS %s HTTP %s (will try Gemini TTS)", language_code, resp.status_code)
        except Exception as exc:
            logger.debug("[GeminiLive] Google Cloud TTS error: %s", exc)
        return None

    def _tts_gemini(self, text: str) -> Optional[bytes]:
        """
        TTS via Gemini 2.5 Flash Preview TTS model.
        Works with just GEMINI_API_KEY — no separate Cloud TTS API needed.
        Returns WAV bytes (browser-playable) or None.
        """
        if not self.configured:
            return None
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=text[:2000],
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Kore"
                            )
                        )
                    ),
                ),
            )

            # Extract audio from response
            if response.candidates:
                for part in response.candidates[0].content.parts:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        pcm_data = inline.data
                        mime = getattr(inline, "mime_type", "")
                        # Parse sample rate from mime (e.g. "audio/L16;codec=pcm;rate=24000")
                        rate = 24000
                        if "rate=" in mime:
                            try:
                                rate = int(mime.split("rate=")[1].split(";")[0])
                            except (ValueError, IndexError):
                                pass
                        # Wrap raw PCM in WAV header for browser playback
                        wav = self._pcm_to_wav(pcm_data, sample_rate=rate, channels=1, sample_width=2)
                        logger.info("[GeminiLive] Gemini TTS OK — %d bytes WAV (rate=%d)", len(wav), rate)
                        return wav

            logger.debug("[GeminiLive] Gemini TTS returned no audio")
        except Exception as exc:
            logger.warning("[GeminiLive] Gemini TTS error: %s", exc)
        return None

    @staticmethod
    def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
        """Wrap raw PCM bytes in a WAV header so browsers can play it."""
        import struct, io
        data_size = len(pcm_data)
        buf = io.BytesIO()
        # RIFF header
        buf.write(b"RIFF")
        buf.write(struct.pack("<I", 36 + data_size))
        buf.write(b"WAVE")
        # fmt chunk
        buf.write(b"fmt ")
        buf.write(struct.pack("<I", 16))                          # chunk size
        buf.write(struct.pack("<H", 1))                           # PCM format
        buf.write(struct.pack("<H", channels))
        buf.write(struct.pack("<I", sample_rate))
        buf.write(struct.pack("<I", sample_rate * channels * sample_width))  # byte rate
        buf.write(struct.pack("<H", channels * sample_width))     # block align
        buf.write(struct.pack("<H", sample_width * 8))            # bits per sample
        # data chunk
        buf.write(b"data")
        buf.write(struct.pack("<I", data_size))
        buf.write(pcm_data)
        return buf.getvalue()

    # ── Status ─────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "live_available": self.live_available,
            "sdk_installed": self._sdk_available,
            "configured": self.configured,
            "active_sessions": len(self._sessions),
            "primary_model": _LIVE_MODEL_PRIMARY,
            "fallback_model": _LIVE_MODEL_FALLBACK,
            "default_voice": _DEFAULT_VOICE,
        }


# ── Module-level singleton ────────────────────────────────────────────────────
gemini_live = GeminiLiveService()
