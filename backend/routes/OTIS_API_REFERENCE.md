# OTIS Voice Assistant - API Reference

**Version:** 1.0.0
**Base URL:** `/api/otis`
**WebSocket URL:** `/socket.io`

---

## Overview

OTIS (Omniscient Travel Intelligence System) provides a voice-activated AI assistant for TravelSync Pro. This API enables:

- Voice session management
- Real-time voice command processing via WebSocket
- Conversation history tracking
- Voice usage analytics
- User settings customization

---

## Authentication

All endpoints require authentication. Use session cookies or JWT tokens.

```http
Cookie: ts_session=...
# OR
Authorization: Bearer <token>
```

---

## REST API Endpoints

### 1. Get OTIS Status

Check if OTIS is available and get service status.

```http
GET /api/otis/status
```

**Response:**
```json
{
  "success": true,
  "enabled": true,
  "available": true,
  "reason": null,
  "permissions": {
    "can_use": true,
    "can_approve_trips": true,
    "can_view_analytics": true,
    "can_execute_functions": true
  },
  "services": {
    "wake_word": "available",
    "stt": "deepgram",
    "tts": "elevenlabs",
    "llm": "gemini"
  },
  "session": {
    "active": false,
    "session_id": null,
    "started_at": null
  },
  "config": {
    "max_session_duration": 600,
    "idle_timeout": 30,
    "wake_word": "Hey Otis"
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Not authenticated

---

### 2. Start Voice Session

Create a new OTIS voice session.

```http
POST /api/otis/start
```

**Rate Limit:** 10 requests per hour

**Response:**
```json
{
  "success": true,
  "session_id": "otis-abc123def456",
  "started_at": "2026-03-26T10:30:00.000Z",
  "message": "OTIS session started. Say 'Hey Otis' to begin."
}
```

**Status Codes:**
- `201 Created` - Session created
- `401 Unauthorized` - Not authenticated
- `403 Forbidden` - No permission (admin-only mode)
- `429 Too Many Requests` - Rate limit exceeded

---

### 3. Stop Voice Session

End an active voice session.

```http
POST /api/otis/stop
Content-Type: application/json

{
  "session_id": "otis-abc123def456"  // Optional, uses active session if omitted
}
```

**Response:**
```json
{
  "success": true,
  "session_id": "otis-abc123def456",
  "duration_seconds": 180,
  "total_turns": 5
}
```

**Status Codes:**
- `200 OK` - Session stopped
- `404 Not Found` - No active session
- `401 Unauthorized` - Not authenticated

---

### 4. List Voice Sessions

Get user's voice session history.

```http
GET /api/otis/sessions?limit=20
```

**Query Parameters:**
- `limit` (optional, default=20, max=100) - Number of sessions to return

**Response:**
```json
{
  "success": true,
  "sessions": [
    {
      "session_id": "otis-abc123",
      "started_at": "2026-03-26T10:30:00Z",
      "ended_at": "2026-03-26T10:35:00Z",
      "duration_seconds": 300,
      "total_turns": 5,
      "status": "ended",
      "wake_word_detected": 1
    }
  ],
  "total": 1
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Not authenticated

---

### 5. Get Session Details

Get detailed information about a specific session.

```http
GET /api/otis/sessions/:id
```

**Response:**
```json
{
  "success": true,
  "session": {
    "session_id": "otis-abc123",
    "started_at": "2026-03-26T10:30:00Z",
    "ended_at": "2026-03-26T10:35:00Z",
    "duration_seconds": 300,
    "total_turns": 5,
    "status": "ended"
  },
  "conversation": [
    {
      "turn_number": 1,
      "role": "user",
      "content": "What pending approvals do I have?",
      "created_at": "2026-03-26T10:30:15Z"
    },
    {
      "turn_number": 2,
      "role": "assistant",
      "content": "You have three pending approvals...",
      "created_at": "2026-03-26T10:30:16Z"
    }
  ],
  "commands": [
    {
      "command_text": "What pending approvals do I have?",
      "response_text": "You have three pending approvals...",
      "function_called": "get_pending_approvals",
      "success": true,
      "latency_ms": 350,
      "created_at": "2026-03-26T10:30:15Z"
    }
  ]
}
```

**Status Codes:**
- `200 OK` - Success
- `404 Not Found` - Session not found
- `401 Unauthorized` - Not authenticated

---

### 6. Delete Session

Delete a voice session and all related data.

```http
DELETE /api/otis/sessions/:id
```

**Response:**
```json
{
  "success": true
}
```

**Status Codes:**
- `200 OK` - Deleted
- `404 Not Found` - Session not found
- `401 Unauthorized` - Not authenticated

---

### 7. Get Command History

List recent voice commands executed by the user.

```http
GET /api/otis/commands?limit=50
```

**Query Parameters:**
- `limit` (optional, default=50, max=200)

**Response:**
```json
{
  "success": true,
  "commands": [
    {
      "command_text": "What pending approvals do I have?",
      "response_text": "You have three pending approvals...",
      "function_called": "get_pending_approvals",
      "success": true,
      "latency_ms": 350,
      "created_at": "2026-03-26T10:30:15Z",
      "session_id": "otis-abc123"
    }
  ],
  "total": 1
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Not authenticated

---

### 8. Get Voice Analytics

Get usage statistics and analytics.

```http
GET /api/otis/analytics?period=7d
```

**Query Parameters:**
- `period` (optional, default=7d, max=90d) - Time period (e.g., "7d", "30d")

**Response:**
```json
{
  "success": true,
  "period": "7d",
  "summary": {
    "total_sessions": 10,
    "total_commands": 45,
    "avg_session_duration": 180,
    "total_voice_time": 1800,
    "avg_latency_ms": 350,
    "success_rate": 0.95
  },
  "daily": [
    {
      "date": "2026-03-26",
      "sessions": 3,
      "commands": 15,
      "avg_latency": 350
    }
  ]
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Not authenticated

---

### 9. Get User Settings

Get OTIS settings for current user.

```http
GET /api/otis/settings
```

**Response:**
```json
{
  "success": true,
  "settings": {
    "voice_speed": 1.0,
    "voice_pitch": 0.0,
    "auto_listen": true,
    "confirm_actions": true
  }
}
```

**Status Codes:**
- `200 OK` - Success
- `401 Unauthorized` - Not authenticated

---

### 10. Update User Settings

Update OTIS settings.

```http
PUT /api/otis/settings
Content-Type: application/json

{
  "voice_speed": 1.2,
  "voice_pitch": 0.1,
  "auto_listen": false,
  "confirm_actions": true
}
```

**Response:**
```json
{
  "success": true,
  "settings": {
    "voice_speed": 1.2,
    "voice_pitch": 0.1,
    "auto_listen": false,
    "confirm_actions": true
  }
}
```

**Status Codes:**
- `200 OK` - Updated
- `401 Unauthorized` - Not authenticated

---

## WebSocket Events

Connect to: `ws://localhost:3399/socket.io`

### Client → Server Events

#### 1. Start Session

```javascript
socket.emit('otis:start_session', {
  session_id: 'otis-abc123'
});
```

**Server Response:**
```javascript
socket.on('otis:session_started', (data) => {
  // data = { session_id: 'otis-abc123', status: 'ready' }
});
```

---

#### 2. Send Audio Chunk

```javascript
socket.emit('otis:audio_chunk', {
  session_id: 'otis-abc123',
  audio: '<base64-encoded-audio>',
  is_final: false
});
```

**Server Response:**
```javascript
socket.on('otis:audio_received', (data) => {
  // data = { session_id: '...', chunk_size: 1024, is_final: false }
});

// When is_final=true:
socket.on('otis:transcribing', (data) => {
  // data = { session_id: '...' }
});

socket.on('otis:transcript', (data) => {
  // data = { text: 'What pending approvals do I have?', session_id: '...' }
});
```

---

#### 3. Process Voice Command

```javascript
socket.emit('otis:process_command', {
  session_id: 'otis-abc123',
  command: 'What pending approvals do I have?'
});
```

**Server Responses:**
```javascript
// 1. Processing started
socket.on('otis:processing', (data) => {
  // data = { session_id: '...', command: '...' }
});

// 2. Response ready
socket.on('otis:response', (data) => {
  // data = {
  //   session_id: '...',
  //   command: 'What pending approvals do I have?',
  //   response: 'You have three pending approvals...',
  //   timestamp: '2026-03-26T10:30:16Z'
  // }
});
```

---

#### 4. Request TTS Audio

```javascript
socket.emit('otis:request_audio', {
  session_id: 'otis-abc123',
  text: 'You have three pending approvals'
});
```

**Server Response:**
```javascript
socket.on('otis:audio_ready', (data) => {
  // data = {
  //   session_id: '...',
  //   text: '...',
  //   audio_url: '<base64-audio-data>',
  //   duration_ms: 2500
  // }
});
```

---

#### 5. Stop Session

```javascript
socket.emit('otis:stop_session', {
  session_id: 'otis-abc123'
});
```

**Server Response:**
```javascript
socket.on('otis:session_stopped', (data) => {
  // data = { session_id: 'otis-abc123' }
});
```

---

### Server → Client Events

#### Error Event

```javascript
socket.on('otis:error', (data) => {
  // data = { error: 'Authentication required' }
  console.error('OTIS error:', data.error);
});
```

---

## Usage Examples

### Example 1: Start Session and Process Command

```javascript
// 1. Check status
const status = await fetch('/api/otis/status').then(r => r.json());
if (!status.available) {
  alert('OTIS is not available');
  return;
}

// 2. Start session
const session = await fetch('/api/otis/start', { method: 'POST' })
  .then(r => r.json());

// 3. Connect WebSocket
const socket = io('http://localhost:3399');

socket.emit('otis:start_session', {
  session_id: session.session_id
});

socket.on('otis:session_started', () => {
  console.log('OTIS ready!');
});

// 4. Process command
socket.emit('otis:process_command', {
  session_id: session.session_id,
  command: 'What pending approvals do I have?'
});

socket.on('otis:response', (data) => {
  console.log('OTIS:', data.response);
  // Display response in UI
});

// 5. Stop session when done
await fetch('/api/otis/stop', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ session_id: session.session_id })
});
```

---

### Example 2: View Session History

```javascript
// Get recent sessions
const sessions = await fetch('/api/otis/sessions?limit=10')
  .then(r => r.json());

// Get details of a specific session
const details = await fetch(`/api/otis/sessions/${sessions.sessions[0].session_id}`)
  .then(r => r.json());

console.log('Conversation:', details.conversation);
console.log('Commands:', details.commands);
```

---

### Example 3: Voice Analytics Dashboard

```javascript
// Get 30-day analytics
const analytics = await fetch('/api/otis/analytics?period=30d')
  .then(r => r.json());

console.log('Total sessions:', analytics.summary.total_sessions);
console.log('Success rate:', analytics.summary.success_rate);
console.log('Avg latency:', analytics.summary.avg_latency_ms + 'ms');

// Chart daily usage
analytics.daily.forEach(day => {
  console.log(`${day.date}: ${day.commands} commands`);
});
```

---

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 401 | Authentication required | User not logged in |
| 403 | Access denied | OTIS admin-only mode or no permission |
| 404 | Not found | Session or resource not found |
| 429 | Too many requests | Rate limit exceeded |
| 500 | Internal server error | Server-side error |

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `POST /api/otis/start` | 10 per hour |
| All other endpoints | No limit (subject to global app limits) |

---

## Permissions

### Admin-Only Mode

When `OTIS_ADMIN_ONLY=True`:
- Only users with role `admin` or `manager` can use OTIS
- Other users get 403 Forbidden

### Function Permissions

Certain OTIS functions require admin role:
- `approve_trip()` - Admin/Manager only
- `reject_trip()` - Admin/Manager only
- `get_travel_stats()` - Admin/Manager only
- `get_spend_report()` - Admin/Manager only

---

## Session Lifecycle

```
1. User clicks "Start OTIS"
   ↓
2. Frontend: POST /api/otis/start
   ↓
3. Backend: Creates session in database, returns session_id
   ↓
4. Frontend: Connect WebSocket, emit otis:start_session
   ↓
5. User speaks: "Hey Otis, what pending approvals do I have?"
   ↓
6. Frontend: Capture audio, emit otis:audio_chunk (or emit otis:process_command if already transcribed)
   ↓
7. Backend: STT → LLM → Function Call → TTS
   ↓
8. Backend: Emit otis:response with text
   ↓
9. Frontend: Display + play audio
   ↓
10. User clicks "Stop" or idle timeout
    ↓
11. Frontend: POST /api/otis/stop
    ↓
12. Backend: Updates session as ended, calculates duration
```

---

## Best Practices

### 1. Always Check Status First

```javascript
const status = await fetch('/api/otis/status').then(r => r.json());
if (!status.available) {
  // Show error message
  return;
}
```

### 2. Handle WebSocket Errors

```javascript
socket.on('otis:error', (data) => {
  console.error('OTIS error:', data.error);
  // Show user-friendly error message
});

socket.on('connect_error', (err) => {
  console.error('Connection failed:', err);
  // Retry or show offline message
});
```

### 3. Stop Sessions Properly

```javascript
// Always stop session when user leaves
window.addEventListener('beforeunload', () => {
  fetch('/api/otis/stop', { method: 'POST', keepalive: true });
});
```

### 4. Respect Rate Limits

```javascript
// Don't start too many sessions
// Limit: 10 per hour
const canStart = checkRateLimit();
if (!canStart) {
  alert('Too many sessions started. Please wait.');
}
```

---

## Support

For issues or questions:
1. Check backend logs: `/backend/logs/app.log`
2. Review OTIS architecture: `/backend/agents/OTIS_ARCHITECTURE.md`
3. Check Gemini guide: `/backend/services/GEMINI_OTIS_GUIDE.md`

---

**Status:** Production Ready ✅
**Version:** 1.0.0
**Last Updated:** 2026-03-26
