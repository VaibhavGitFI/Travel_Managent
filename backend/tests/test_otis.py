import io
import uuid
from datetime import datetime

from config import Config
from agents.chat_agent import _enrich_reply, process_message
from agents.query_engine import query_users, should_use_structured_query
from routes.chat import _json_safe
from routes.otis import _build_otis_context, _load_otis_conversation_history
from services.deepgram_service import DeepgramProvider, STTProvider, TranscriptionResult


def _enable_otis(monkeypatch):
    monkeypatch.setattr(Config, "OTIS_ENABLED", True, raising=False)
    monkeypatch.setattr(Config, "OTIS_ADMIN_ONLY", True, raising=False)


def test_super_admin_otis_status_permissions(super_admin_client, monkeypatch):
    _enable_otis(monkeypatch)

    resp = super_admin_client.get("/api/otis/status")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["available"] is True
    assert data["permissions"]["can_use"] is True
    assert data["permissions"]["can_approve_trips"] is True
    assert data["permissions"]["can_view_analytics"] is True
    assert data["permissions"]["can_execute_functions"] is True


def test_otis_command_updates_session_turns(super_admin_client, monkeypatch):
    _enable_otis(monkeypatch)

    from services.gemini_service import gemini

    monkeypatch.setattr(
        gemini,
        "generate_voice_optimized",
        lambda **kwargs: "Test OTIS response",
    )

    start = super_admin_client.post("/api/otis/start", json={})
    assert start.status_code == 201
    session_id = start.get_json()["session_id"]

    command = super_admin_client.post(
        "/api/otis/command",
        json={"command": "Show me pending approvals", "session_id": session_id},
    )
    assert command.status_code == 200

    details = super_admin_client.get(f"/api/otis/sessions/{session_id}")
    assert details.status_code == 200
    details_json = details.get_json()

    assert details_json["session"]["total_turns"] == 1
    assert len(details_json["conversation"]) == 2
    assert len(details_json["commands"]) == 1


def test_otis_follow_up_uses_prior_session_history(super_admin_client, monkeypatch):
    _enable_otis(monkeypatch)

    from services.gemini_service import gemini

    calls = []

    def fake_generate_voice_optimized(**kwargs):
        calls.append(kwargs)
        if kwargs["prompt"] == "Show me pending approvals":
            return "You have two pending approvals."
        return "They are both Mumbai requests."

    monkeypatch.setattr(gemini, "generate_voice_optimized", fake_generate_voice_optimized)

    start = super_admin_client.post("/api/otis/start", json={})
    assert start.status_code == 201
    session_id = start.get_json()["session_id"]

    first = super_admin_client.post(
        "/api/otis/command",
        json={"command": "Show me pending approvals", "session_id": session_id},
    )
    assert first.status_code == 200
    first_response = first.get_json()["response"]

    second = super_admin_client.post(
        "/api/otis/command",
        json={"command": "What are they?", "session_id": session_id},
    )
    assert second.status_code == 200

    assert calls[-1]["conversation_history"] == [
        {
            "user_input": "Show me pending approvals",
            "assistant_response": first_response,
        }
    ]


def test_otis_command_uses_active_session_when_session_id_missing(super_admin_client, monkeypatch):
    _enable_otis(monkeypatch)

    from services.gemini_service import gemini

    monkeypatch.setattr(
        gemini,
        "generate_voice_optimized",
        lambda **kwargs: "Using the active OTIS session.",
    )

    start = super_admin_client.post("/api/otis/start", json={})
    assert start.status_code == 201
    session_id = start.get_json()["session_id"]

    command = super_admin_client.post(
        "/api/otis/command",
        json={"command": "Continue our conversation"},
    )
    assert command.status_code == 200
    assert command.get_json()["session_id"] == session_id

    details = super_admin_client.get(f"/api/otis/sessions/{session_id}")
    assert details.status_code == 200
    details_json = details.get_json()

    assert details_json["session"]["total_turns"] == 1
    assert len(details_json["conversation"]) == 2


def test_deepgram_provider_initializes_with_current_sdk(monkeypatch):
    monkeypatch.setattr(Config, "DEEPGRAM_API_KEY", "test-key", raising=False)

    provider = DeepgramProvider({})

    assert provider.is_configured is True
    assert provider.get_provider_name() == STTProvider.DEEPGRAM


def test_otis_transcribe_reports_actual_provider(super_admin_client, monkeypatch):
    _enable_otis(monkeypatch)

    import services.deepgram_service as deepgram_service

    class FakeSTTService:
        def __init__(self):
            pass

        async def transcribe(self, audio_data):
            return TranscriptionResult(
                text="mock transcript",
                confidence=0.91,
                is_final=True,
                provider=STTProvider.MOCK,
                latency_ms=12,
            )

        def get_active_provider(self):
            return STTProvider.MOCK

    monkeypatch.setattr(deepgram_service, "SpeechToTextService", FakeSTTService)

    resp = super_admin_client.post(
        "/api/otis/transcribe",
        data={"audio": (io.BytesIO(b"x" * 600), "voice.webm")},
        content_type="multipart/form-data",
    )
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["success"] is True
    assert data["text"] == "mock transcript"
    assert data["provider"] == "mock"


def test_otis_speak_falls_back_to_playable_audio(super_admin_client, monkeypatch):
    _enable_otis(monkeypatch)
    monkeypatch.setattr(Config, "ELEVENLABS_API_KEY", "", raising=False)

    resp = super_admin_client.post("/api/otis/speak", json={"text": "Fallback audio please"})

    assert resp.status_code == 200
    assert resp.headers["X-Provider"] == "beep"
    assert resp.headers["Content-Type"].startswith("audio/wav")
    assert len(resp.data) > 44


def test_otis_context_rolls_back_after_handled_query_error():
    class FakeCursor:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class FakeDb:
        def __init__(self):
            self.aborted = False
            self.rollback_calls = 0

        def execute(self, sql, params=()):
            if self.aborted:
                raise RuntimeError("current transaction is aborted")

            if "FROM client_meetings" in sql:
                self.aborted = True
                raise RuntimeError("invalid SQL for current adapter")

            return FakeCursor([])

        def rollback(self):
            self.aborted = False
            self.rollback_calls += 1

    db = FakeDb()
    user = {"id": 1, "role": "super_admin", "name": "Test User", "email": "test@example.com"}

    context = _build_otis_context(user, db)
    history = _load_otis_conversation_history(db, "otis-test")

    assert context["user_name"] == "Test User"
    assert history == []
    assert db.rollback_calls == 1


def test_auth_me_includes_org_context(auth_client, db):
    slug = f"acme-travel-{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO organizations (name, slug, plan, status) VALUES (?, ?, ?, ?)",
        ("Acme Travel", slug, "starter", "active"),
    )
    org_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    db.execute(
        "INSERT INTO org_members (org_id, user_id, org_role, department) VALUES (?, ?, ?, ?)",
        (org_id, auth_client.user["id"], "org_owner", "Engineering"),
    )
    db.commit()

    resp = auth_client.get("/api/auth/me")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["user"]["org_id"] == org_id
    assert data["user"]["org_role"] == "org_owner"


def test_query_users_returns_exact_count_beyond_preview_limit(db):
    from werkzeug.security import generate_password_hash

    prefix = f"bulk_user_{uuid.uuid4().hex[:8]}"
    for idx in range(60):
        db.execute(
            """INSERT INTO users
               (username, password_hash, name, full_name, email, role, department, email_verified)
               VALUES (?, ?, ?, ?, ?, 'employee', 'Operations', 1)""",
            (
                f"{prefix}_{idx}",
                generate_password_hash("TestPass1"),
                f"Bulk User {idx}",
                f"Bulk User {idx}",
                f"{prefix}_{idx}@example.com",
            ),
        )
    db.commit()
    expected_total = db.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]

    result = query_users({"id": 999999, "role": "super_admin"}, "how many users are there")

    assert result["success"] is True
    assert result["count"] == expected_total
    assert len(result["users"]) == 50


def test_query_users_scopes_super_admin_to_named_org(db):
    from werkzeug.security import generate_password_hash

    slug = f"fristine-{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO organizations (name, slug, plan, status) VALUES (?, ?, ?, ?)",
        ("Fristine", slug, "pro", "active"),
    )
    org_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    created_user_ids = []
    for idx in range(2):
        username = f"fristine_member_{uuid.uuid4().hex[:8]}"
        email = f"{username}@example.com"
        db.execute(
            """INSERT INTO users
               (username, password_hash, name, full_name, email, role, department, email_verified)
               VALUES (?, ?, ?, ?, ?, 'employee', 'Operations', 1)""",
            (
                username,
                generate_password_hash("TestPass1"),
                f"Fristine Member {idx}",
                f"Fristine Member {idx}",
                email,
            ),
        )
        user_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        created_user_ids.append(user_id)
        db.execute(
            "INSERT INTO org_members (org_id, user_id, org_role, department) VALUES (?, ?, ?, ?)",
            (org_id, user_id, "member", "Operations"),
        )
    db.commit()

    result = query_users(
        {"id": 999999, "role": "super_admin"},
        "How many users are there in Fristine org?",
    )

    assert result["success"] is True
    assert result["scope"] == "org"
    assert result["org_name"] == "Fristine"
    assert result["count"] == len(created_user_ids)


def test_structured_query_gate_understands_query_vs_planning():
    assert should_use_structured_query("How many users are there in my org?") is True
    assert should_use_structured_query("Show my trip requests") is True
    assert should_use_structured_query("Help me plan trip next week from Delhi to Indore") is False
    assert should_use_structured_query("Approve the Mumbai trip for John") is False


def test_otis_command_uses_structured_users_query_before_gemini(super_admin_client, monkeypatch, db):
    _enable_otis(monkeypatch)

    from services.gemini_service import gemini

    def fail_if_called(**kwargs):
        raise AssertionError("Gemini should not be called for structured user-count queries")

    monkeypatch.setattr(gemini, "generate_voice_optimized", fail_if_called)

    start = super_admin_client.post("/api/otis/start", json={})
    assert start.status_code == 201
    session_id = start.get_json()["session_id"]

    expected_total = db.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]

    resp = super_admin_client.post(
        "/api/otis/command",
        json={"command": "How many users are there? Give me an overview.", "session_id": session_id},
    )
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["data_source"] == "structured_query"
    assert data["query_type"] == "users"
    assert data["query_data"]["count"] == expected_total
    assert str(expected_total) in data["response"]


def test_chat_stream_uses_structured_org_users_query(super_admin_client, monkeypatch, db):
    from services.anthropic_service import claude
    from services.gemini_service import gemini
    from werkzeug.security import generate_password_hash

    slug = f"fristine-{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO organizations (name, slug, plan, status) VALUES (?, ?, ?, ?)",
        ("Fristine", slug, "pro", "active"),
    )
    org_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    db.execute(
        "INSERT INTO org_members (org_id, user_id, org_role, department) VALUES (?, ?, ?, ?)",
        (org_id, super_admin_client.user["id"], "org_owner", "Management"),
    )

    username = f"fristine_stream_{uuid.uuid4().hex[:8]}"
    db.execute(
        """INSERT INTO users
           (username, password_hash, name, full_name, email, role, department, email_verified)
           VALUES (?, ?, 'Fristine Stream User', 'Fristine Stream User', ?, 'employee', 'Operations', 1)""",
        (username, generate_password_hash("TestPass1"), f"{username}@example.com"),
    )
    member_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    db.execute(
        "INSERT INTO org_members (org_id, user_id, org_role, department) VALUES (?, ?, ?, ?)",
        (org_id, member_id, "member", "Operations"),
    )
    db.commit()

    monkeypatch.setattr(gemini, "generate", lambda *args, **kwargs: None)
    monkeypatch.setattr(claude, "stream", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Claude should not stream for structured org user queries")))
    monkeypatch.setattr(gemini, "stream_with_history", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Gemini should not stream for structured org user queries")))

    resp = super_admin_client.post(
        "/api/chat/stream",
        json={"message": "How many users are there in Fristine org?"},
    )

    body = resp.data.decode("utf-8")

    assert resp.status_code == 200
    assert "Fristine" in body
    assert "**Total:** 2 users" in body
    assert '"data_source": "structured_query"' in body


def test_chat_stream_json_safe_serializes_datetimes():
    payload = {
        "created_at": datetime(2026, 3, 28, 23, 52, 34),
        "items": [{"updated_at": datetime(2026, 3, 28, 23, 52, 35)}],
    }

    result = _json_safe(payload)

    assert result["created_at"] == "2026-03-28T23:52:34"
    assert result["items"][0]["updated_at"] == "2026-03-28T23:52:35"


def test_process_message_keeps_trip_planning_dynamic(monkeypatch):
    import agents.orchestrator as orchestrator
    import agents.query_engine as query_engine
    from services.anthropic_service import claude
    from services.gemini_service import gemini

    monkeypatch.setattr(
        query_engine,
        "handle_query",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Structured query path should not handle trip-planning prompts")),
    )
    monkeypatch.setattr(
        orchestrator,
        "plan_trip",
        lambda trip_input: {
            "success": True,
            "trip_summary": {"destination": trip_input["destination"], "duration": "3 days", "travel_dates": ""},
            "travel": {"flights": [{"airline": "Test Air", "price": 4200}]},
            "hotels": {"hotels": [{"name": "Indore Suites", "price_per_night": 3500}]},
            "weather": {"summary": "Warm and clear", "forecast": []},
        },
    )
    monkeypatch.setattr(claude, "generate", lambda *args, **kwargs: None)
    monkeypatch.setattr(gemini, "generate_with_history", lambda *args, **kwargs: None)

    result = process_message(
        "Help me plan trip next week from Delhi to Indore",
        user={"id": 1, "name": "Test User", "role": "super_admin", "org_id": 1},
    )

    assert result["intent"] == "plan_trip"
    assert result["trip_results"]["destination"] == "Indore"
    assert result["trip_results"]["flights"]
    assert result["trip_results"]["hotels"]


def test_weather_enrich_does_not_duplicate_live_block(monkeypatch):
    from services.weather_service import weather

    monkeypatch.setattr(
        weather,
        "get_current",
        lambda city: (_ for _ in ()).throw(AssertionError("Weather enrichment should not re-fetch when reply already contains a live weather block")),
    )

    reply = "**Live Weather in Bangalore**: 25°C, Clear Sky, Humidity: 58%"

    assert _enrich_reply(reply, "weather", {"destination": "Bangalore"}) == reply
