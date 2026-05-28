"""
OTIS Voice Agent - Main Orchestrator
Omniscient Travel Intelligence System

This is the brain that connects all voice components:
    Wake Word → Speech-to-Text → AI Processing → Text-to-Speech

Architecture:
    1. WakeWordService detects "Hey Otis"
    2. STT transcribes user speech
    3. Gemini processes command & calls functions
    4. TTS speaks response back
    5. Session stored in database

Aligned with TravelSync patterns:
    - Uses existing gemini service
    - Uses existing database patterns
    - Follows TravelSync code style
    - Integrates with TravelSync functions

Author: TravelSync Pro Team
Date: 2026-03-26
"""

import sys
import os
import asyncio
import logging
import json
import uuid
from datetime import datetime
from typing import Any, Optional, Dict, List, Callable
from dataclasses import dataclass
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, table_columns
from agents.query_engine import handle_query, format_query_result_for_voice, should_use_structured_query
from auth import get_user_org
from services.gemini_service import gemini
from services.wake_word_service import WakeWordService
from services.deepgram_service import SpeechToTextService
from services.elevenlabs_voice_service import TextToSpeechService
from config import Config

# Import OTIS function registry
try:
    from agents.otis_functions import OtisFunctionRegistry
except ImportError:
    logger.warning("[OTIS Agent] otis_functions.py not found - function calling disabled")
    OtisFunctionRegistry = None

logger = logging.getLogger(__name__)


class OtisState(Enum):
    """OTIS agent states."""
    IDLE = "idle"
    LISTENING_FOR_WAKE = "listening_for_wake"
    LISTENING_FOR_COMMAND = "listening_for_command"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class OtisSession:
    """Voice conversation session."""
    session_id: str
    user_id: int
    org_id: Optional[int]
    status: str
    started_at: datetime
    turns: int = 0
    conversation_history: List[Dict] = None

    def __post_init__(self):
        if self.conversation_history is None:
            self.conversation_history = []


class OtisAgent:
    """
    OTIS Voice Agent - Main orchestrator for voice interactions.

    This agent manages the complete voice interaction pipeline:
    1. Wake word detection ("Hey Otis")
    2. Speech-to-text transcription
    3. AI-powered command processing
    4. Function calling for TravelSync actions
    5. Text-to-speech responses
    6. Session & conversation management

    Features:
        - Multi-turn conversations with context
        - Admin-level TravelSync access
        - Proactive suggestions
        - Graceful error handling
        - Complete audit trail

    Usage:
        >>> agent = OtisAgent(user_id=1, org_id=1)
        >>> await agent.start()
        >>> # Processes voice commands automatically
        >>> await agent.stop()
    """

    def __init__(self, user_id: int, org_id: Optional[int] = None):
        """
        Initialize OTIS agent for a user.

        Args:
            user_id: TravelSync user ID
            org_id: Organization ID (optional)
        """
        self.user_id = user_id
        self.org_id = org_id
        self.user = None
        self._load_user_data()

        # Initialize state
        self._state = OtisState.IDLE
        self._current_session: Optional[OtisSession] = None

        # Initialize voice services
        self._wake_word: Optional[WakeWordService] = None
        self._stt: Optional[SpeechToTextService] = None
        self._tts: Optional[TextToSpeechService] = None
        self._initialize_services()

        # Initialize function registry for TravelSync actions
        self._function_registry: Optional[OtisFunctionRegistry] = None
        if OtisFunctionRegistry:
            try:
                self._function_registry = OtisFunctionRegistry()
                logger.info(
                    f"[OTIS Agent] ✅ Function registry initialized "
                    f"({len(self._function_registry.list_functions())} functions available)"
                )
            except Exception as e:
                logger.warning(f"[OTIS Agent] Function registry init failed: {e}")

        # Callbacks
        self._on_wake_callbacks: List[Callable] = []
        self._on_command_callbacks: List[Callable] = []
        self._on_response_callbacks: List[Callable] = []

        logger.info(
            f"[OTIS Agent] Initialized for user {user_id} "
            f"({self.user.get('name', 'Unknown')})"
        )

    def _load_user_data(self):
        """Load user data from database."""
        try:
            db = get_db()
            user_row = db.execute(
                "SELECT * FROM users WHERE id = ?",
                (self.user_id,)
            ).fetchone()

            if not user_row:
                logger.error(f"[OTIS Agent] User {self.user_id} not found")
                raise ValueError(f"User {self.user_id} not found")

            self.user = dict(user_row)
            membership = get_user_org(self.user_id)
            if membership:
                if not self.user.get("org_id"):
                    self.user["org_id"] = membership.get("org_id")
                if membership.get("org_role"):
                    self.user["org_role"] = membership.get("org_role")
                if membership.get("org_name"):
                    self.user["org_name"] = membership.get("org_name")
                if membership.get("org_slug"):
                    self.user["org_slug"] = membership.get("org_slug")
            if self.org_id and not self.user.get("org_id"):
                self.user["org_id"] = self.org_id

            # Check if user is admin (OTIS admin-only mode)
            if Config.OTIS_ADMIN_ONLY and self.user.get("role") not in ("admin", "manager", "super_admin"):
                logger.warning(
                    f"[OTIS Agent] User {self.user_id} ({self.user.get('role')}) "
                    f"attempted to use OTIS (admin-only mode)"
                )
                raise PermissionError("OTIS is currently available to admins only")

            db.close()

            logger.debug(
                f"[OTIS Agent] Loaded user: {self.user.get('name')} "
                f"(role: {self.user.get('role')})"
            )

        except Exception as e:
            logger.error(f"[OTIS Agent] Failed to load user data: {e}")
            raise

    def _initialize_services(self):
        """Initialize voice services (wake word, STT, TTS)."""
        try:
            # Initialize wake word service
            # Auto-selects Porcupine (if PORCUPINE_ACCESS_KEY is set) or OpenWakeWord (free fallback)
            try:
                self._wake_word = WakeWordService()
                logger.info(
                    f"[OTIS Agent] ✅ Wake word service initialized "
                    f"(backend: {self._wake_word.config.backend})"
                )
            except Exception as e:
                logger.warning(f"[OTIS Agent] Wake word init failed: {e}")

            # Initialize STT service
            self._stt = SpeechToTextService()
            logger.info(
                f"[OTIS Agent] ✅ STT service initialized "
                f"(provider: {self._stt.get_active_provider().value})"
            )

            # Initialize TTS service
            self._tts = TextToSpeechService()
            logger.info(
                f"[OTIS Agent] ✅ TTS service initialized "
                f"(provider: {self._tts.get_active_provider().value})"
            )

        except Exception as e:
            logger.error(f"[OTIS Agent] Service initialization failed: {e}")
            raise

    async def start(self):
        """
        Start OTIS agent and begin listening for wake word.

        This starts the voice interaction loop:
        1. Listen for "Hey Otis"
        2. On detection, listen for command
        3. Process command and respond
        4. Return to wake word listening
        """
        if self._state != OtisState.IDLE:
            logger.warning(f"[OTIS Agent] Already running (state: {self._state.value})")
            return

        logger.info("[OTIS Agent] Starting OTIS agent...")

        # Create session
        self._current_session = self._create_session()

        # Start listening for wake word
        if self._wake_word:
            self._wake_word.register_callback(self._on_wake_word_detected)
            self._wake_word.start_listening()
            self._state = OtisState.LISTENING_FOR_WAKE
            logger.info("[OTIS Agent] 👂 Listening for wake word...")
        else:
            logger.warning("[OTIS Agent] Wake word service not available, entering direct mode")
            self._state = OtisState.LISTENING_FOR_COMMAND

        # Trigger start callbacks
        for callback in self._on_wake_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"[OTIS Agent] Start callback error: {e}")

    async def stop(self):
        """Stop OTIS agent and clean up resources."""
        logger.info("[OTIS Agent] Stopping OTIS agent...")

        # Stop wake word listening
        if self._wake_word:
            self._wake_word.stop_listening()

        # End current session
        if self._current_session:
            self._end_session()

        self._state = OtisState.STOPPED
        logger.info("[OTIS Agent] ⏹️  OTIS agent stopped")

    def _create_session(self) -> OtisSession:
        """Create a new OTIS voice session."""
        session_id = str(uuid.uuid4())
        started_at = datetime.now()

        # Save to database
        try:
            db = get_db()
            db.execute(
                """INSERT INTO otis_sessions
                   (session_id, org_id, user_id, status, wake_word_detected, started_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, self.org_id, self.user_id, "active", 1, started_at)
            )
            db.commit()
            db.close()

            logger.info(f"[OTIS Agent] Created session: {session_id}")

        except Exception as e:
            logger.error(f"[OTIS Agent] Failed to create session in DB: {e}")

        # Create session object
        session = OtisSession(
            session_id=session_id,
            user_id=self.user_id,
            org_id=self.org_id,
            status="active",
            started_at=started_at
        )

        return session

    def _end_session(self):
        """End the current OTIS session."""
        if not self._current_session:
            return

        ended_at = datetime.now()
        duration_seconds = int((ended_at - self._current_session.started_at).total_seconds())

        # Update database
        try:
            db = get_db()
            db.execute(
                """UPDATE otis_sessions SET
                   status = ?, ended_at = ?, duration_seconds = ?, total_turns = ?
                   WHERE session_id = ?""",
                ("completed", ended_at, duration_seconds,
                 self._current_session.turns, self._current_session.session_id)
            )
            db.commit()
            db.close()

            logger.info(
                f"[OTIS Agent] Ended session {self._current_session.session_id} "
                f"(duration: {duration_seconds}s, turns: {self._current_session.turns})"
            )

        except Exception as e:
            logger.error(f"[OTIS Agent] Failed to end session in DB: {e}")

        self._current_session = None

    def _on_wake_word_detected(self):
        """Callback when wake word is detected."""
        logger.info("[OTIS Agent] 🎙️  Wake word detected!")

        # Change state
        self._state = OtisState.LISTENING_FOR_COMMAND

        # Play acknowledgment (optional beep or say "Yes?")
        # asyncio.create_task(self._play_acknowledgment())

        # Trigger wake callbacks
        for callback in self._on_wake_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback())
                else:
                    callback()
            except Exception as e:
                logger.error(f"[OTIS Agent] Wake callback error: {e}")

    async def process_audio_frame(self, audio_frame: bytes) -> Optional[str]:
        """
        Process an audio frame through the voice pipeline.

        This is the main entry point for audio processing. Depending on
        the current state, audio is routed to wake word detection or STT.

        Args:
            audio_frame: Raw audio data (16kHz, mono, 16-bit PCM)

        Returns:
            Response text if command was processed, None otherwise
        """
        if self._state == OtisState.LISTENING_FOR_WAKE:
            # Check for wake word
            if self._wake_word:
                try:
                    detected = self._wake_word.process_audio_frame(audio_frame)
                    if detected:
                        self._on_wake_word_detected()
                except Exception as e:
                    logger.error(f"[OTIS Agent] Wake word processing error: {e}")

            return None

        elif self._state == OtisState.LISTENING_FOR_COMMAND:
            # Transcribe speech
            # Note: This simplified version processes frame-by-frame
            # In production, you'd buffer audio until silence detected
            try:
                result = await self._stt.transcribe(audio_frame)

                if result.text:
                    logger.info(f"[OTIS Agent] 📝 Transcribed: '{result.text}'")

                    # Process command
                    response = await self.process_command(result.text)

                    # Return to wake word listening
                    self._state = OtisState.LISTENING_FOR_WAKE

                    return response

            except Exception as e:
                logger.error(f"[OTIS Agent] STT processing error: {e}")
                self._state = OtisState.LISTENING_FOR_WAKE

            return None

        return None

    async def process_command(self, command_text: str) -> str:
        """
        Process a voice command using Gemini AI.

        This is where the magic happens:
        1. Build context from user data
        2. Send command to Gemini
        3. Extract function calls (if any)
        4. Execute functions
        5. Generate response
        6. Speak response via TTS

        Args:
            command_text: Transcribed command from user

        Returns:
            Response text that was spoken
        """
        if not self._current_session:
            logger.error("[OTIS Agent] No active session")
            return "Session error. Please restart."

        self._state = OtisState.PROCESSING
        command_start_time = datetime.now()
        function_called = None
        function_result = None
        _stage_times: Dict = {}

        try:
            # Build rich context (cached — won't re-query DB on every command)
            context = self._build_context_dict_cached()

            # Build conversation history for Gemini
            conversation_history = self._get_conversation_history()

            response_text = None
            use_functions = False
            structured_query = None
            structured_response = None
            if should_use_structured_query(command_text):
                structured_query = handle_query(self.user, command_text, strict=True)
                structured_response = format_query_result_for_voice(structured_query, command_text)

            if structured_response:
                function_called = f"structured_query:{structured_query.get('type')}"
                function_result = structured_query.get("data")
                response_text = structured_response

            else:
                # Decide if we should use function calling or simple chat
                use_functions = self._function_registry is not None and self._should_use_functions(command_text)

            if use_functions:
                # Function calling workflow
                logger.debug("[OTIS Agent] Using function calling workflow")

                # Get function definitions
                functions = self._function_registry.get_functions_for_gemini()

                # System instruction for function calling
                system_instruction = self._get_function_calling_system_instruction()

                # Process with Gemini function calling
                _gemini_start = datetime.now()
                result = gemini.generate_with_functions(
                    prompt=command_text,
                    functions=functions,
                    system_instruction=system_instruction,
                    model_type="flash"
                )
                _stage_times["gemini_ms"] = int(
                    (datetime.now() - _gemini_start).total_seconds() * 1000
                )

                if result["type"] == "function_call":
                    # Gemini wants to call a function
                    function_name = result["function_name"]
                    parameters = result["parameters"]
                    function_called = function_name

                    logger.info(
                        f"[OTIS Agent] Function call requested: {function_name} "
                        f"with params: {parameters}"
                    )

                    # Execute the function
                    function_context = {
                        "user_id": self.user_id,
                        "org_id": self.org_id,
                        "user_role": self.user.get("role"),
                        "user_name": self.user.get("name")
                    }

                    _fn_start = datetime.now()
                    function_result = await self._function_registry.execute_function(
                        function_name=function_name,
                        parameters=parameters,
                        user_id=self.user_id,
                        user_role=self.user.get("role")
                    )
                    _stage_times["function_ms"] = int(
                        (datetime.now() - _fn_start).total_seconds() * 1000
                    )

                    # Get voice response from function result
                    if function_result.get("success"):
                        response_text = function_result.get("voice_response", "Done.")
                    else:
                        response_text = function_result.get(
                            "voice_response",
                            "I couldn't complete that action. Please try again."
                        )

                elif result["type"] == "text":
                    # Gemini responded with text (no function needed)
                    response_text = result["text"]

            elif not response_text:
                # Simple conversation (no functions)
                logger.debug("[OTIS Agent] Using simple conversation mode")

                _gemini_start = datetime.now()
                response_text = gemini.generate_voice_optimized(
                    prompt=command_text,
                    context=context,
                    conversation_history=conversation_history,
                    model_type="flash"
                )
                _stage_times["gemini_ms"] = int(
                    (datetime.now() - _gemini_start).total_seconds() * 1000
                )

            if not response_text:
                logger.warning("[OTIS Agent] Gemini returned empty response")
                response_text = "I'm having trouble processing that. Could you try again?"

            # Response is already cleaned by gemini.generate_voice_optimized or function result
            # But clean again just in case
            response_text = self._clean_response_for_voice(response_text)

            total_ms = int((datetime.now() - command_start_time).total_seconds() * 1000)
            logger.info(
                "[OTIS Agent] Command complete in %dms (gemini=%dms, fn=%dms)",
                total_ms,
                _stage_times.get("gemini_ms", 0),
                _stage_times.get("function_ms", 0),
            )

            # Save command to database
            self._save_command(
                command_text,
                response_text,
                command_start_time,
                function_called=function_called,
                function_result=function_result
            )

            # Update conversation history
            self._update_conversation(command_text, response_text)

            # Speak response
            await self._speak(response_text)

            # Trigger response callbacks
            for callback in self._on_response_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(response_text)
                    else:
                        callback(response_text)
                except Exception as e:
                    logger.error(f"[OTIS Agent] Response callback error: {e}")

            return response_text

        except Exception as e:
            logger.error(f"[OTIS Agent] Command processing error: {e}")
            error_response = "I encountered an error. Please try again."
            await self._speak(error_response)
            return error_response

        finally:
            self._state = OtisState.LISTENING_FOR_WAKE

    def _build_context_dict(self) -> Dict[str, Any]:
        """
        Build rich context as a dictionary for voice-optimized generation.
        Used by gemini.generate_voice_optimized().
        """
        context = {
            "user_name": self.user.get("name", "there"),
            "user_role": self.user.get("role", "user"),
            "user_department": self.user.get("department"),
            "org_id": self.user.get("org_id"),
            "org_name": self.user.get("org_name"),
            "org_role": self.user.get("org_role"),
            "pending_approvals_count": 0,
            "org_member_count": 0,
            "upcoming_trips_count": 0,
            "recent_expense_count": 0,
            "pending_expenses_count": 0,
            "unread_notifications": 0
        }

        try:
            db = get_db()

            # Count pending approvals (for admins/managers)
            if self.user.get("role") in ("manager", "admin", "super_admin"):
                try:
                    if self.user.get("role") == "super_admin" and self.user.get("org_id"):
                        result = db.execute(
                            "SELECT COUNT(*) as cnt FROM travel_requests "
                            "WHERE org_id = ? AND status = 'submitted'",
                            (self.user.get("org_id"),)
                        ).fetchone()
                    else:
                        result = db.execute(
                            "SELECT COUNT(*) as cnt FROM approvals "
                            "WHERE approver_id = ? AND status = 'pending'",
                            (self.user_id,)
                        ).fetchone()
                    context["pending_approvals_count"] = dict(result).get("cnt", 0)
                except Exception as e:
                    logger.debug(f"[OTIS Agent] Context approvals error: {e}")

            if self.user.get("org_id") and self.user.get("role") in ("admin", "super_admin"):
                try:
                    result = db.execute(
                        "SELECT COUNT(*) as cnt FROM org_members WHERE org_id = ?",
                        (self.user.get("org_id"),)
                    ).fetchone()
                    context["org_member_count"] = dict(result).get("cnt", 0)
                except Exception as e:
                    logger.debug(f"[OTIS Agent] Context org member count error: {e}")

            # Count upcoming trips (next 30 days)
            try:
                cols = table_columns(db, "travel_requests")
                if "start_date" in cols:
                    from datetime import timedelta
                    future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                    result = db.execute(
                        f"SELECT COUNT(*) as cnt FROM travel_requests "
                        f"WHERE user_id = ? AND start_date <= ? AND status IN ('approved', 'pending')",
                        (self.user_id, future_date)
                    ).fetchone()
                    context["upcoming_trips_count"] = dict(result).get("cnt", 0)
            except Exception as e:
                logger.debug(f"[OTIS Agent] Context trips error: {e}")

            # Count recent expenses (last 7 days)
            try:
                cols = table_columns(db, "expenses_db")
                if "expense_date" in cols:
                    from datetime import timedelta
                    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                    result = db.execute(
                        f"SELECT COUNT(*) as cnt FROM expenses_db "
                        f"WHERE user_id = ? AND expense_date >= ?",
                        (self.user_id, week_ago)
                    ).fetchone()
                    context["recent_expense_count"] = dict(result).get("cnt", 0)

                # Count pending expenses
                if "status" in cols:
                    result = db.execute(
                        "SELECT COUNT(*) as cnt FROM expenses_db "
                        "WHERE user_id = ? AND status = 'pending'",
                        (self.user_id,)
                    ).fetchone()
                    context["pending_expenses_count"] = dict(result).get("cnt", 0)
            except Exception as e:
                logger.debug(f"[OTIS Agent] Context expenses error: {e}")

            db.close()

        except Exception as e:
            logger.error(f"[OTIS Agent] Failed to build context dict: {e}")

        return context

    def _get_conversation_history(self) -> List[Dict]:
        """
        Get conversation history for current session.
        Returns list of dicts with 'user_input' and 'assistant_response' keys.
        """
        if not self._current_session:
            return []

        history = []
        for turn in self._current_session.conversation_history:
            if turn.get("role") == "user":
                history.append({"user_input": turn.get("content", "")})
            elif turn.get("role") == "assistant" and history:
                history[-1]["assistant_response"] = turn.get("content", "")

        return history

    def _should_use_functions(self, command_text: str) -> bool:
        """
        Heuristic to determine if we should use function calling for this command.

        Function calling is used for:
        - Action requests: approve, reject, create, update, delete
        - Data queries: get, show, list, check, find
        - Analytics: report, stats, analysis

        Simple conversation doesn't need functions:
        - Greetings: hi, hello, thanks
        - General questions: what, why, how (about system)
        """
        command_lower = command_text.lower()

        # Action keywords
        action_keywords = [
            "approve", "reject", "create", "add", "update", "edit", "delete", "remove",
            "submit", "cancel", "book", "reserve", "confirm"
        ]

        # Query keywords
        query_keywords = [
            "get", "show", "list", "check", "find", "search", "what's", "what are",
            "tell me", "give me", "display", "pending", "upcoming", "recent"
        ]

        # Analytics keywords
        analytics_keywords = [
            "report", "stats", "statistics", "analysis", "analytics", "spend", "budget",
            "total", "summary", "overview", "dashboard"
        ]

        # Check if any action/query/analytics keyword is present
        all_keywords = action_keywords + query_keywords + analytics_keywords
        for keyword in all_keywords:
            if keyword in command_lower:
                return True

        # Default: use simple conversation
        return False

    def _get_function_calling_system_instruction(self) -> str:
        """Get system instruction for function calling mode."""
        return f"""You are OTIS (Omniscient Travel Intelligence System), a voice assistant for TravelSync Pro.

You are speaking to {self.user.get('name')}, who is a {self.user.get('role')}.

**Function Calling Guidelines:**
1. When the user asks you to DO something (approve, check, get, etc.), call the appropriate function
2. Use the provided functions whenever possible - don't just describe what to do
3. Extract parameters carefully from the user's speech
4. If a required parameter is missing, ask the user for it
5. After calling a function, the voice_response will be provided - use it directly

**Voice Response Rules:**
- Be concise and natural
- No markdown or formatting
- Numbers as words: "three" not "3"
- Keep responses under 3 sentences
- Always confirm what you did

**Available Functions:**
- Approvals: get_pending_approvals, approve_trip, reject_trip
- Trips: get_my_trips, get_trip_details
- Expenses: get_my_expenses
- Meetings: get_upcoming_meetings
- Analytics: get_travel_stats, get_spend_report
- Policy: get_travel_policy
- Quick: get_my_schedule_today
"""

    def _build_context(self) -> str:
        """
        Build rich context from user's TravelSync data.

        Following chat_agent.py pattern for consistency.
        """
        context_parts = []
        now = datetime.now()

        context_parts.append(f"Current time: {now.strftime('%A, %B %d, %Y at %I:%M %p')}")
        context_parts.append(
            f"User: {self.user.get('name')} "
            f"(role: {self.user.get('role')}, "
            f"department: {self.user.get('department', 'N/A')})"
        )
        if self.user.get("org_id"):
            org_name = self.user.get("org_name") or f"Organization {self.user.get('org_id')}"
            org_role = self.user.get("org_role", "member")
            context_parts.append(f"Active organization: {org_name} (org role: {org_role})")

        try:
            db = get_db()

            # Recent travel requests (last 3)
            try:
                cols = table_columns(db, "travel_requests")
                select = ["request_id", "destination", "status"]
                if "start_date" in cols:
                    select.append("start_date")
                if "estimated_total" in cols:
                    select.append("estimated_total")

                requests = db.execute(
                    f"SELECT {', '.join(select)} FROM travel_requests "
                    f"WHERE user_id = ? ORDER BY created_at DESC LIMIT 3",
                    (self.user_id,)
                ).fetchall()

                if requests:
                    req_lines = []
                    for r in requests:
                        rd = dict(r)
                        line = f"  {rd.get('request_id')}: {rd.get('destination')} ({rd.get('status')})"
                        req_lines.append(line)
                    context_parts.append("Recent trips:\n" + "\n".join(req_lines))
            except Exception as e:
                logger.debug(f"[OTIS Agent] Context trips error: {e}")

            # Pending approvals (for admins/managers)
            if self.user.get("role") in ("manager", "admin", "super_admin"):
                try:
                    if self.user.get("role") == "super_admin" and self.user.get("org_id"):
                        pending = db.execute(
                            "SELECT COUNT(*) as cnt FROM travel_requests "
                            "WHERE org_id = ? AND status = 'submitted'",
                            (self.user.get("org_id"),)
                        ).fetchone()
                    else:
                        pending = db.execute(
                            "SELECT COUNT(*) as cnt FROM approvals "
                            "WHERE approver_id = ? AND status = 'pending'",
                            (self.user_id,)
                        ).fetchone()
                    cnt = dict(pending).get("cnt", 0)
                    context_parts.append(f"Pending approvals: {cnt}")
                except Exception as e:
                    logger.debug(f"[OTIS Agent] Context approvals error: {e}")

            if self.user.get("org_id") and self.user.get("role") in ("admin", "super_admin"):
                try:
                    members = db.execute(
                        "SELECT COUNT(*) as cnt FROM org_members WHERE org_id = ?",
                        (self.user.get("org_id"),)
                    ).fetchone()
                    context_parts.append(f"Organization members: {dict(members).get('cnt', 0)}")
                except Exception as e:
                    logger.debug(f"[OTIS Agent] Context org members error: {e}")

            db.close()

        except Exception as e:
            logger.error(f"[OTIS Agent] Failed to build context: {e}")

        return "\n".join(context_parts)

    def _get_system_instruction(self) -> str:
        """Get OTIS system instruction for Gemini."""
        return """You are OTIS (Omniscient Travel Intelligence System), a voice assistant for TravelSync Pro.

## Your Capabilities
- Check travel requests, approvals, expenses
- Approve or reject trip requests (admin only)
- Get travel analytics and spending reports
- Schedule meetings, check calendars
- Answer travel policy questions

## Response Rules for VOICE
- Be extremely concise - you are SPEAKING, not writing
- 2-3 sentences maximum per response
- NO markdown, NO bullet points, NO tables
- Use natural spoken language: "You have three pending approvals" not "Pending approvals: 3"
- Numbers: say "three" not "3", "five thousand rupees" not "₹5000"
- Always confirm actions: "I've approved the Mumbai trip for John"
- If uncertain, ask ONE follow-up question

## Important
- Keep responses SHORT - this is a voice conversation
- Be conversational and natural
- Always end with what happens next or offer to do more
"""

    def _build_conversation_history(self, current_message: str) -> List[Dict]:
        """
        Build Gemini conversation history.

        Format for Gemini chat:
        [
            {"role": "user", "parts": ["first message"]},
            {"role": "model", "parts": ["first response"]},
            {"role": "user", "parts": ["second message"]},
            ...
        ]
        """
        messages = []

        # Add context as system message (include in first user message)
        context = self._build_context()

        # Add previous turns from session
        if self._current_session and self._current_session.conversation_history:
            for turn in self._current_session.conversation_history:
                role = "user" if turn["role"] == "user" else "model"
                messages.append({
                    "role": role,
                    "parts": [turn["content"]]
                })

        # Add current message with context (if first message)
        if not messages:
            # First message - include context
            full_message = f"[System Context]\n{context}\n\n[User Command]\n{current_message}"
            messages.append({"role": "user", "parts": [full_message]})
        else:
            # Subsequent message
            messages.append({"role": "user", "parts": [current_message]})

        return messages

    def _clean_response_for_voice(self, text: str) -> str:
        """
        Clean AI response to be voice-friendly.

        Remove markdown, convert to natural speech.
        """
        import re

        # Remove markdown bold
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)

        # Remove markdown headers
        text = re.sub(r'###?\s+', '', text)

        # Remove bullet points
        text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)

        # Remove extra whitespace
        text = re.sub(r'\n\n+', '. ', text)
        text = re.sub(r'\n', '. ', text)

        # Remove multiple periods
        text = re.sub(r'\.\.+', '.', text)

        # Trim
        text = text.strip()

        return text

    def _update_conversation(self, user_message: str, assistant_message: str):
        """Update conversation history in session."""
        if not self._current_session:
            return

        # Add user message
        self._current_session.conversation_history.append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now().isoformat()
        })

        # Add assistant message
        self._current_session.conversation_history.append({
            "role": "assistant",
            "content": assistant_message,
            "timestamp": datetime.now().isoformat()
        })

        # Increment turn count
        self._current_session.turns += 1

        # Save conversation to database
        try:
            db = get_db()

            # Save user turn
            db.execute(
                """INSERT INTO otis_conversations
                   (session_id, turn_number, role, content)
                   VALUES (?, ?, ?, ?)""",
                (self._current_session.session_id,
                 self._current_session.turns * 2 - 1,
                 "user",
                 user_message)
            )

            # Save assistant turn
            db.execute(
                """INSERT INTO otis_conversations
                   (session_id, turn_number, role, content)
                   VALUES (?, ?, ?, ?)""",
                (self._current_session.session_id,
                 self._current_session.turns * 2,
                 "assistant",
                 assistant_message)
            )

            db.commit()
            db.close()

        except Exception as e:
            logger.error(f"[OTIS Agent] Failed to save conversation: {e}")

    def _save_command(
        self,
        command_text: str,
        response_text: str,
        started_at: datetime,
        function_called: Optional[str] = None,
        function_result: Optional[Dict] = None
    ):
        """Save command execution to database."""
        if not self._current_session:
            return

        latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)
        success = 1 if not function_result or function_result.get("success", True) else 0

        try:
            db = get_db()

            # Check if function_called column exists
            cols = table_columns(db, "otis_commands")

            if "function_called" in cols:
                # New schema with function tracking
                db.execute(
                    """INSERT INTO otis_commands
                       (org_id, user_id, session_id, command_text, transcript,
                        response_text, success, latency_ms, function_called, function_result)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (self.org_id, self.user_id, self._current_session.session_id,
                     command_text, command_text, response_text, success, latency_ms,
                     function_called, json.dumps(function_result) if function_result else None)
                )
            else:
                # Old schema (backwards compatible)
                db.execute(
                    """INSERT INTO otis_commands
                       (org_id, user_id, session_id, command_text, transcript,
                        response_text, success, latency_ms)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (self.org_id, self.user_id, self._current_session.session_id,
                     command_text, command_text, response_text, success, latency_ms)
                )

            db.commit()
            db.close()

            log_msg = f"[OTIS Agent] Saved command (latency: {latency_ms}ms)"
            if function_called:
                log_msg += f", function: {function_called}"
            logger.debug(log_msg)

        except Exception as e:
            logger.error(f"[OTIS Agent] Failed to save command: {e}")

    async def _speak(self, text: str):
        """Speak text using TTS service."""
        self._state = OtisState.SPEAKING

        try:
            result = await self._tts.speak(text)
            logger.info(
                f"[OTIS Agent] 🗣️  Speaking: '{text[:50]}...' "
                f"({result.provider.value}, {len(result.audio_data)} bytes)"
            )

            # In production, you'd send audio_data to the client for playback
            # For now, just log that we generated it
            return result.audio_data

        except Exception as e:
            logger.error(f"[OTIS Agent] TTS error: {e}")
            return None

    # ── Callback Registration ─────────────────────────────────────────────────

    def on_wake(self, callback: Callable):
        """Register callback for wake word detection."""
        self._on_wake_callbacks.append(callback)

    def on_command(self, callback: Callable):
        """Register callback for command received."""
        self._on_command_callbacks.append(callback)

    def on_response(self, callback: Callable):
        """Register callback for response generated."""
        self._on_response_callbacks.append(callback)

    # ── Status & Statistics ───────────────────────────────────────────────────

    def get_state(self) -> OtisState:
        """Get current agent state."""
        return self._state

    def get_session(self) -> Optional[OtisSession]:
        """Get current session."""
        return self._current_session

    def get_statistics(self) -> Dict:
        """Get comprehensive statistics."""
        stats = {
            "state": self._state.value,
            "user": {
                "id": self.user_id,
                "name": self.user.get("name"),
                "role": self.user.get("role")
            },
            "services": {
                "wake_word": self._wake_word.get_statistics() if self._wake_word else None,
                "stt": self._stt.get_statistics() if self._stt else None,
                "tts": self._tts.get_statistics() if self._tts else None
            }
        }

        if self._current_session:
            stats["session"] = {
                "session_id": self._current_session.session_id,
                "turns": self._current_session.turns,
                "started_at": self._current_session.started_at.isoformat()
            }

        return stats

    # ── Context Caching ───────────────────────────────────────────────────────

    _context_cache: Dict = {}
    _context_cache_time: Optional[datetime] = None
    _CONTEXT_TTL_SECONDS = 60  # Refresh context every 60 seconds

    def _build_context_dict_cached(self) -> Dict:
        """
        Cached version of _build_context_dict.
        DB context (pending counts etc.) is refreshed at most every 60 seconds
        to avoid hitting the database on every command.
        """
        now = datetime.now()
        if (
            self._context_cache
            and self._context_cache_time
            and (now - self._context_cache_time).total_seconds() < self._CONTEXT_TTL_SECONDS
        ):
            return self._context_cache
        self._context_cache = self._build_context_dict()
        self._context_cache_time = now
        return self._context_cache


# ── Agent Pool ─────────────────────────────────────────────────────────────────
# Cache OtisAgent instances per session so services are not re-initialized on
# every WebSocket command. Agents are evicted when the session ends.

class OtisAgentPool:
    """
    Thread-safe pool of OtisAgent instances keyed by (user_id, session_id).

    Usage:
        pool = OtisAgentPool.instance()
        agent = pool.get_or_create(user_id, org_id, session_id)
        pool.release(session_id)
    """

    _instance: Optional["OtisAgentPool"] = None
    _lock = None  # Created lazily to avoid import-time threading

    def __init__(self):
        import threading
        self._pool: Dict[str, "OtisAgent"] = {}  # key: session_id
        self._pool_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "OtisAgentPool":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_or_create(self, user_id: int, org_id: Optional[int], session_id: str) -> "OtisAgent":
        """Return cached agent for this session, or create a new one."""
        with self._pool_lock:
            if session_id not in self._pool:
                logger.info(
                    "[OTIS Pool] Creating new agent for session %s (user %s)",
                    session_id, user_id
                )
                agent = OtisAgent(user_id=user_id, org_id=org_id)
                # Set up a lightweight "web session" — no actual DB session, just
                # the session_id so process_command can persist commands.
                agent._current_session = OtisSession(
                    session_id=session_id,
                    user_id=user_id,
                    org_id=org_id,
                    status="active",
                    started_at=datetime.now()
                )
                self._pool[session_id] = agent
            else:
                logger.debug("[OTIS Pool] Reusing cached agent for session %s", session_id)
            return self._pool[session_id]

    def release(self, session_id: str) -> None:
        """Remove agent from pool when session ends."""
        with self._pool_lock:
            if session_id in self._pool:
                logger.info("[OTIS Pool] Released agent for session %s", session_id)
                del self._pool[session_id]

    def size(self) -> int:
        with self._pool_lock:
            return len(self._pool)


# ── Utility Functions ─────────────────────────────────────────────────────────

async def test_otis_agent():
    """Test OTIS agent with simulated commands."""
    print("=" * 70)
    print("OTIS Voice Agent - Interactive Test")
    print("=" * 70)

    # Check if Gemini is configured
    if not gemini.configured:
        print("\n❌ ERROR: GEMINI_API_KEY not set!")
        print("Add to backend/.env: GEMINI_API_KEY=your_key")
        return

    print("\n🔧 Initializing OTIS agent...")

    # Get a test user (create one if needed)
    try:
        db = get_db()

        # Check if any admin user exists
        admin = db.execute(
            "SELECT * FROM users WHERE role IN ('admin', 'manager') LIMIT 1"
        ).fetchone()

        if not admin:
            print("\n❌ No admin user found in database")
            print("Please create an admin user first or run database init")
            db.close()
            return

        user = dict(admin)
        db.close()

        print(f"✅ Using test user: {user['name']} (role: {user['role']})")

    except Exception as e:
        print(f"\n❌ Database error: {e}")
        return

    # Initialize agent
    try:
        agent = OtisAgent(user_id=user['id'])
        print("✅ OTIS agent initialized")
    except Exception as e:
        print(f"\n❌ Agent initialization failed: {e}")
        return

    # Start agent
    print("\n🚀 Starting OTIS agent...")
    await agent.start()

    # Test commands
    test_commands = [
        "What pending approvals do I have?",
        "Show me my recent trips",
        "How much have we spent on travel this month?"
    ]

    print("\n" + "=" * 70)
    print("Testing voice commands...")
    print("=" * 70)

    for i, command in enumerate(test_commands, 1):
        print(f"\n🎤 Test {i}/{len(test_commands)}: '{command}'")

        try:
            response = await agent.process_command(command)
            print(f"   ✅ Response: '{response}'")

        except Exception as e:
            print(f"   ❌ Command failed: {e}")

        # Small delay between commands
        await asyncio.sleep(1)

    # Show statistics
    print("\n📊 Final Statistics:")
    stats = agent.get_statistics()
    print(f"   State: {stats['state']}")
    print(f"   Session turns: {stats.get('session', {}).get('turns', 0)}")

    if stats['services']['stt']:
        stt_stats = stats['services']['stt']
        print(f"\n   STT Provider: {stt_stats.get('active_provider')}")
        for provider, pstats in stt_stats.get('providers', {}).items():
            if pstats['total_requests'] > 0:
                print(f"      {provider}: {pstats['success_rate']:.1%} success rate")

    if stats['services']['tts']:
        tts_stats = stats['services']['tts']
        print(f"\n   TTS Provider: {tts_stats.get('active_provider')}")
        for provider, pstats in tts_stats.get('providers', {}).items():
            if pstats['total_requests'] > 0:
                print(f"      {provider}: {pstats['success_rate']:.1%} success rate")

    # Stop agent
    print("\n⏹️  Stopping OTIS agent...")
    await agent.stop()

    print("\n✅ Test complete!")
    print("=" * 70)


if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(test_otis_agent())
