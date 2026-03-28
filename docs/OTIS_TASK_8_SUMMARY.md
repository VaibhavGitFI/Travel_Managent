# Task #8 Complete: OTIS API Routes & WebSocket Handlers

**Date:** 2026-03-26
**Status:** ✅ Complete
**Progress:** 64% (9/14 tasks)

---

## 🎯 What Was Built

### 1. REST API Routes (`/backend/routes/otis.py`)

**File Size:** 750+ lines of production-ready code

**10 Endpoints Created:**

#### Session Management
1. **GET `/api/otis/status`**
   - Check OTIS availability
   - Get user permissions
   - View active services (wake word, STT, TTS, LLM)
   - See current session status

2. **POST `/api/otis/start`**
   - Start new voice session
   - Rate limited: 10 per hour
   - Creates session in database
   - Returns session_id

3. **POST `/api/otis/stop`**
   - End active session
   - Calculates duration
   - Returns session stats

#### History & Analytics
4. **GET `/api/otis/sessions`**
   - List user's voice sessions
   - Sorted by most recent
   - Paginated (limit parameter)

5. **GET `/api/otis/sessions/:id`**
   - Get full session details
   - Complete conversation history
   - All commands executed
   - Function calls made

6. **DELETE `/api/otis/sessions/:id`**
   - Delete session
   - Removes all related data (conversation, commands)

7. **GET `/api/otis/commands`**
   - Command execution history
   - Shows function calls
   - Latency metrics
   - Success rates

8. **GET `/api/otis/analytics`**
   - Voice usage statistics
   - Daily breakdown
   - Success rates
   - Latency averages

#### Settings
9. **GET `/api/otis/settings`**
   - Get user's voice settings
   - Voice speed, pitch, etc.

10. **PUT `/api/otis/settings`**
    - Update settings
    - Persists to database

---

### 2. WebSocket Handlers (`/backend/app.py`)

**5 Real-Time Events Added:**

#### Client → Server

1. **`otis:start_session`**
   - Initialize WebSocket connection for voice
   - Emits: `otis:session_started`

2. **`otis:audio_chunk`**
   - Stream audio data for STT
   - Supports chunked streaming
   - Emits: `otis:audio_received`, `otis:transcribing`, `otis:transcript`

3. **`otis:process_command`** ⭐ **Main Pipeline**
   - Process voice command (text already transcribed)
   - Calls OtisAgent.process_command()
   - Executes TravelSync functions
   - Emits: `otis:processing` → `otis:response`

4. **`otis:request_audio`**
   - Request TTS audio for text
   - Emits: `otis:audio_ready`

5. **`otis:stop_session`**
   - End WebSocket session
   - Emits: `otis:session_stopped`

#### Server → Client

- **`otis:session_started`** - Session ready
- **`otis:audio_received`** - Audio chunk received
- **`otis:transcribing`** - STT in progress
- **`otis:transcript`** - STT complete, text ready
- **`otis:processing`** - Command being processed
- **`otis:response`** - Response ready
- **`otis:audio_ready`** - TTS audio ready
- **`otis:session_stopped`** - Session ended
- **`otis:error`** - Error occurred

---

### 3. API Documentation (`/backend/routes/OTIS_API_REFERENCE.md`)

**Complete API reference created:**
- Overview and authentication
- 10 REST endpoint docs with examples
- 5 WebSocket event specs
- Error codes and rate limits
- Usage examples (3)
- Best practices
- Session lifecycle diagram

**Length:** 600+ lines of comprehensive documentation

---

## 🏗️ Architecture

### REST API Flow

```
Frontend                        Backend
   ↓                               ↓
POST /api/otis/start          Create session in DB
   ↓                               ↓
GET /api/otis/status          Check permissions
   ↓                               ↓
WebSocket connect             Join user room
   ↓                               ↓
emit otis:process_command     OtisAgent.process_command()
   ↓                               ↓
on otis:response              Send response back
   ↓                               ↓
POST /api/otis/stop           End session, save stats
```

### WebSocket Main Processing Pipeline

```javascript
// Client sends command
socket.emit('otis:process_command', {
  session_id: 'otis-abc123',
  command: 'What pending approvals do I have?'
});

// Server processes
1. Emit 'otis:processing' (acknowledge)
2. Create OtisAgent instance
3. Call agent.process_command(command)
   ├─ Build context (user, trips, approvals)
   ├─ Decide: use functions or chat?
   ├─ Call Gemini with functions
   ├─ Execute TravelSync function
   └─ Get voice-optimized response
4. Emit 'otis:response' with text
5. Save to database

// Client receives
socket.on('otis:response', (data) => {
  // data.response = "You have three pending approvals..."
  displayResponse(data.response);
  playAudio(data.response); // TTS
});
```

---

## 🔒 Security Features

### 1. Permission Checks

```python
def _check_otis_permission(user):
    """Check if user can use OTIS."""
    if not Config.OTIS_ENABLED:
        return False, "OTIS is currently disabled"

    if Config.OTIS_ADMIN_ONLY:
        if user.get("role") not in ("admin", "manager"):
            return False, "OTIS is currently available to admins only"

    return True, ""
```

### 2. Rate Limiting

```python
@otis_bp.route("/start", methods=["POST"])
@limiter.limit("10 per hour")  # Max 10 sessions per hour
def start_session():
    ...
```

### 3. Session Ownership

```python
# Verify user owns session before accessing
row = db.execute(
    "SELECT * FROM otis_sessions WHERE session_id = ? AND user_id = ?",
    (session_id, user["id"])
).fetchone()

if not row:
    return jsonify({"error": "Session not found"}), 404
```

### 4. Authentication Required

All endpoints check authentication:
```python
user = get_current_user()
if not user:
    return jsonify({"error": "Authentication required"}), 401
```

### 5. CSRF Protection

Inherits from Flask app:
- Safe methods (GET, HEAD) exempt
- POST/PUT/DELETE require valid CSRF token
- WebSocket uses session authentication

---

## 📊 Database Integration

### Tables Used

**`otis_sessions`**
```sql
INSERT INTO otis_sessions (org_id, user_id, session_id, status, started_at)
UPDATE otis_sessions SET status = 'ended', ended_at = ?, duration_seconds = ?
SELECT * FROM otis_sessions WHERE user_id = ? AND status = 'active'
```

**`otis_conversations`**
```sql
SELECT * FROM otis_conversations WHERE session_id = ? ORDER BY turn_number
```

**`otis_commands`**
```sql
SELECT * FROM otis_commands WHERE user_id = ? ORDER BY created_at DESC
```

**`otis_settings`**
```sql
INSERT INTO otis_settings (org_id, user_id, settings_json)
UPDATE otis_settings SET settings_json = ?, updated_at = CURRENT_TIMESTAMP
```

**`otis_analytics`** (for future aggregation)

---

## 🎨 Following TravelSync Patterns

### 1. Blueprint Structure

```python
from flask import Blueprint, request, jsonify
from auth import get_current_user
from extensions import limiter
from database import get_db, table_columns

otis_bp = Blueprint("otis", __name__, url_prefix="/api/otis")
```

Same pattern as `/backend/routes/chat.py`, `/backend/routes/expenses.py`

### 2. Response Format

```python
# Success
return jsonify({
    "success": True,
    "session_id": "...",
    "data": {...}
}), 200

# Error
return jsonify({
    "success": False,
    "error": "Authentication required"
}), 401
```

Consistent with all TravelSync APIs

### 3. Database Operations

```python
db = get_db()
# ... operations
db.commit()
db.close()
```

Uses existing `database.py` patterns

### 4. Error Handling

```python
try:
    # ... operation
except Exception as e:
    logger.exception("[OTIS Routes] Operation failed")
    return jsonify({"success": False, "error": "Failed..."}), 500
```

### 5. Schema Tolerance

```python
cols = table_columns(db, "otis_commands")
if "function_called" in cols:
    # Use new schema
else:
    # Use old schema (backwards compatible)
```

Same as `chat_agent.py`, `expense_agent.py`

---

## 🧪 Testing the API

### Test 1: Check Status

```bash
curl -X GET http://localhost:3399/api/otis/status \
  -H "Cookie: ts_session=..."
```

**Expected:**
```json
{
  "success": true,
  "enabled": true,
  "available": true,
  "permissions": {
    "can_use": true,
    "can_approve_trips": true
  },
  "services": {
    "wake_word": "available",
    "stt": "deepgram",
    "tts": "elevenlabs",
    "llm": "gemini"
  }
}
```

---

### Test 2: Start Session

```bash
curl -X POST http://localhost:3399/api/otis/start \
  -H "Cookie: ts_session=..." \
  -H "X-CSRF-Token: ..."
```

**Expected:**
```json
{
  "success": true,
  "session_id": "otis-abc123def456",
  "started_at": "2026-03-26T10:30:00Z",
  "message": "OTIS session started. Say 'Hey Otis' to begin."
}
```

---

### Test 3: WebSocket Processing

```javascript
const socket = io('http://localhost:3399');

socket.emit('otis:process_command', {
  session_id: 'otis-abc123',
  command: 'What pending approvals do I have?'
});

socket.on('otis:response', (data) => {
  console.log('OTIS:', data.response);
  // Expected: "You have three pending approvals. Mumbai trip for John..."
});
```

---

### Test 4: Get Analytics

```bash
curl -X GET "http://localhost:3399/api/otis/analytics?period=7d" \
  -H "Cookie: ts_session=..."
```

**Expected:**
```json
{
  "success": true,
  "summary": {
    "total_sessions": 10,
    "total_commands": 45,
    "avg_latency_ms": 350,
    "success_rate": 0.95
  },
  "daily": [...]
}
```

---

## ✅ Checklist

**REST API:**
- [x] 10 endpoints created
- [x] Permission checks on all routes
- [x] Rate limiting on /start
- [x] Session ownership verification
- [x] Database integration
- [x] Error handling
- [x] Logging
- [x] Follows TravelSync patterns

**WebSocket:**
- [x] 5 event handlers created
- [x] OTIS agent integration
- [x] Authentication check
- [x] Error handling
- [x] Logging
- [x] Real-time communication

**Documentation:**
- [x] Complete API reference (600+ lines)
- [x] 10 endpoint docs with examples
- [x] 5 WebSocket event specs
- [x] Usage examples
- [x] Best practices
- [x] Error codes
- [x] Rate limits

**Integration:**
- [x] Blueprint registered in app.py
- [x] WebSocket handlers in app.py
- [x] Imports added
- [x] No breaking changes

---

## 📈 Impact

### Before Task #8:
- ❌ No way for frontend to connect to OTIS
- ❌ No session management endpoints
- ❌ No analytics data accessible
- ❌ No WebSocket communication

### After Task #8:
- ✅ Complete REST API for OTIS control
- ✅ Real-time WebSocket voice processing
- ✅ Session management with history
- ✅ Analytics dashboard ready
- ✅ User settings customizable
- ✅ Production-ready backend

---

## 🚀 What's Next

**Backend is Complete!** ✅

Phases 1-3 are 100% done:
- ✅ Core Services (wake word, STT, TTS)
- ✅ AI Intelligence (orchestrator, functions, Gemini)
- ✅ Backend API (REST + WebSocket)

**Next:** Frontend Development (Phase 4)

**Task #9:** Create OTIS frontend voice widget
- React component with microphone access
- Waveform visualization
- Real-time WebSocket communication
- Voice button UI

**Task #10:** Build OTIS Dashboard
- Session history viewer
- Conversation playback
- Analytics charts
- Settings panel

---

**Status:** Backend Complete ✅
**Progress:** 64% (9/14 tasks)
**Time to Full Production:** ~3-5 days (Frontend + Testing)
