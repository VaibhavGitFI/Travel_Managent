"""
TravelSync Pro — Anthropic Claude AI Service
Uses claude-opus-4-6 for intelligent, context-aware travel assistant responses.
Falls back gracefully when ANTHROPIC_API_KEY is not set.
"""
import os
import logging
from typing import Generator

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8192


class AnthropicService:
    def __init__(self):
        self._client = None
        self._initialized = False

    def _ensure_init(self):
        """Lazy init — loads API key and creates client on first use."""
        if self._initialized:
            return
        self._initialized = True
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.configured = bool(self.api_key)
        if self.configured:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
                logger.info("[Anthropic] Claude %s ready", MODEL)
            except ImportError:
                logger.warning("[Anthropic] anthropic package not installed")
                self.configured = False
            except Exception as e:
                logger.warning("[Anthropic] Init failed: %s", e)
                self.configured = False
        else:
            self.configured = False

    @property
    def is_available(self) -> bool:
        self._ensure_init()
        return self.configured and self._client is not None

    def generate(self, message: str, system: str = "", history: list = None) -> str | None:
        """
        Send a single message (with optional history) and return the full reply.
        """
        self._ensure_init()
        if not self.is_available:
            return None
        try:
            messages = _build_messages(message, history)
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system or "",
                messages=messages,
            )
            for block in response.content:
                if block.type == "text":
                    return block.text
        except Exception as e:
            logger.warning("[Anthropic] generate error: %s", e)
        return None

    def stream(self, message: str, system: str = "", history: list = None) -> Generator[str, None, None]:
        """Stream response tokens one chunk at a time."""
        self._ensure_init()
        if not self.is_available:
            return
        try:
            messages = _build_messages(message, history)
            with self._client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system or "",
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            logger.warning("[Anthropic] stream error: %s", e)


def _build_messages(message: str, history: list = None) -> list:
    """
    Build the messages array for the Anthropic API.
    history items: {"role": "user"|"assistant", "content": str}
    The current message is appended as the last user turn.
    """
    messages = []

    if history:
        for item in history:
            role = item.get("role", "user")
            # Normalise Gemini-style role names
            if role == "model":
                role = "assistant"
            content = item.get("content") or (
                item.get("parts", [""])[0] if isinstance(item.get("parts"), list) else ""
            )
            if role in ("user", "assistant") and content:
                # Avoid consecutive same-role messages
                if messages and messages[-1]["role"] == role:
                    messages[-1]["content"] += "\n" + content
                else:
                    messages.append({"role": role, "content": content})

    # Append current user message
    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"] += "\n" + message
    else:
        messages.append({"role": "user", "content": message})

    return messages


# Singleton
claude = AnthropicService()
