# OTIS Voice Assistant — User Guide

**Omniscient Travel Intelligence System**
**TravelSync Pro v3.0**

---

## What is OTIS?

OTIS is a Siri/Alexa-level voice assistant built into TravelSync Pro. Say "Hey Otis" and speak naturally to manage corporate travel: approve trips, check expenses, view analytics — all hands-free in under one second.

**Who can use it:** Admins and Managers (configurable in `OTIS_ADMIN_ONLY`)

---

## Quick Start

### 1. Open TravelSync
Navigate to `http://localhost:5173` (dev) or your production URL.

### 2. Find the OTIS Button
A blue-purple floating button appears in the bottom-left corner of every page.

### 3. Click to Open
The OTIS Voice Widget opens. Click **Start Session** or say "Hey Otis".

### 4. Speak Your Command
```
"What pending approvals do I have?"
"Approve John's Mumbai trip"
"Show me last month's travel spend"
"When is my next trip?"
```

---

## Voice Commands

### Approvals
| Say | Action |
|-----|--------|
| "What pending approvals do I have?" | Lists all pending trip requests |
| "Approve John's trip to Mumbai" | Approves the specified trip |
| "Reject the Delhi trip — over budget" | Rejects with reason |

### Travel
| Say | Action |
|-----|--------|
| "Show me my upcoming trips" | Lists your approved trips |
| "What's the status of my Mumbai request?" | Gets request details |
| "Get me trip details for request 42" | Specific trip details |

### Expenses
| Say | Action |
|-----|--------|
| "Show me my recent expenses" | Last 7 days of expenses |
| "What expenses are pending approval?" | Pending expense list |

### Meetings
| Say | Action |
|-----|--------|
| "What meetings do I have today?" | Today's client meetings |
| "Show upcoming meetings" | Next 7 days of meetings |

### Analytics
| Say | Action |
|-----|--------|
| "What's our travel spend this month?" | Spend summary |
| "Show me travel statistics" | Dashboard KPIs |
| "Give me a compliance report" | Policy compliance score |

### General
| Say | Action |
|-----|--------|
| "What can you do?" | Lists OTIS capabilities |
| "Help" | Usage help |
| "Stop" / "Goodbye" | Ends the session |

---

## Confirmation for High-Risk Actions

For actions that are irreversible (approving or rejecting trips), OTIS will ask you to confirm:

```
You: "Approve John's Mumbai trip"
OTIS: "Just to confirm — approve the Mumbai trip for John departing March 28th?"
You: "Yes, approve it"
OTIS: "Done. John's Mumbai trip is approved. He'll be notified."
```

To skip confirmations, set `OTIS_REQUIRE_CONFIRMATION=False` in `backend/.env`.

---

## OTIS Dashboard

Navigate to **OTIS Voice** in the sidebar (admin/manager only).

### Overview Tab
- Total sessions, commands, average latency, success rate
- Daily activity bar chart
- Recent sessions list
- Service health status (wake word, STT, TTS, AI)

### Sessions Tab
- Full conversation history for every session
- Click **View** to replay the conversation
- Commands executed with latency and function names
- **Delete** sessions you no longer need

### Commands Tab
- Chronological list of all voice commands
- Which TravelSync function was called
- Response time in milliseconds
- Success / failure status

### Settings Tab
- **Voice Speed**: 0.5x (slow) to 2.0x (fast)
- **Voice Pitch**: -1 (low) to +1 (high)
- **Auto Listen**: Start listening immediately after wake word
- **Confirm Actions**: Require confirmation for high-risk commands

---

## OTIS Voice Widget

The floating widget (bottom-left) provides a full voice + text interface:

| State | Indicator | Meaning |
|-------|-----------|---------|
| Idle | Grey circle | Ready, waiting for command |
| Listening | Animated blue wave | Recording your voice |
| Processing | Spinning circle | AI is thinking |
| Speaking | Pulsing circle | Playing response |

### Text Fallback
If microphone isn't available, type commands in the text box at the bottom of the widget.

### Minimize
Click the **—** button to minimize OTIS to a small FAB. Your session stays active.

---

## Browser Requirements

| Feature | Requirement |
|---------|-------------|
| Voice input | Chrome/Edge (Web Speech API) |
| Text input | Any modern browser |
| Microphone | Required for voice commands |
| HTTPS | Required in production for mic access |

Firefox and Safari do not support Web Speech API. Use text mode on those browsers.

---

## Performance Targets

| Stage | Target | Description |
|-------|--------|-------------|
| Wake word detection | < 100ms | Porcupine offline, no network |
| Speech-to-text | 100–150ms | Deepgram Nova-3 streaming |
| AI processing | 300–500ms | Gemini 2.0 Flash |
| Text-to-speech | 75–150ms | ElevenLabs streaming |
| **Total end-to-end** | **< 800ms** | Feels instant (Siri-level) |

---

## Troubleshooting

### "OTIS Unavailable"
- Check backend is running: `http://localhost:3399/api/otis/status`
- Check `OTIS_ENABLED=True` in `backend/.env`
- Verify you have admin or manager role

### No microphone / voice not working
- Allow microphone permission in browser (click the camera/mic icon in address bar)
- Use Chrome or Edge for full voice support
- Fall back to text input in the widget

### OTIS doesn't understand me
- Speak clearly and naturally
- Use the text input fallback for complex commands
- Check STT service: `http://localhost:3399/api/otis/status` → `services.stt`

### Slow responses (> 2 seconds)
- Check Deepgram API key is set (`DEEPGRAM_API_KEY` in `.env`)
- Check ElevenLabs API key is set (`ELEVENLABS_API_KEY` in `.env`)
- Without keys, fallback providers are used (slower)
- Check backend logs: `tail -f backend/logs/app.log`

### Session limit reached
- Default: 10 sessions per hour per user
- Adjust with `OTIS_MAX_SESSIONS_PER_HOUR=20` in `.env`

---

## API Keys Required

| Service | Key | Purpose |
|---------|-----|---------|
| Porcupine | `PORCUPINE_ACCESS_KEY` | Wake word "Hey Otis" |
| Deepgram | `DEEPGRAM_API_KEY` | Speech-to-text (fast, Indian English) |
| ElevenLabs | `ELEVENLABS_API_KEY` | Natural TTS voice |
| Gemini | `GEMINI_API_KEY` | AI command understanding |

All services have fallbacks — OTIS works without any keys (with reduced quality).

---

## Environment Variables

```bash
# backend/.env

# Feature flags
OTIS_ENABLED=True
OTIS_ADMIN_ONLY=True          # Set False to allow all users
OTIS_DEBUG=False

# API Keys (fill in for production quality)
PORCUPINE_ACCESS_KEY=         # picovoice.ai
DEEPGRAM_API_KEY=             # console.deepgram.com
ELEVENLABS_API_KEY=           # elevenlabs.io/app/settings/api-keys

# Voice
OTIS_VOICE_ID=EXAVITQu4vr4xnSDxMaL   # Indian English female
OTIS_VOICE_SPEED=1.0
OTIS_WAKE_WORD=Hey Otis

# Behavior
OTIS_REQUIRE_CONFIRMATION=True        # Confirm high-risk actions
OTIS_AUTO_EXECUTE=False

# Limits
OTIS_MAX_SESSION_DURATION=600         # 10 minutes
OTIS_IDLE_TIMEOUT=30                  # 30 seconds idle
OTIS_MAX_SESSIONS_PER_HOUR=10
OTIS_MAX_COMMANDS_PER_SESSION=50
```

---

## Cost Estimate

### Development (free tier limits)
- Porcupine: Free (3 wake words)
- Deepgram: Free ($200 credit = ~200 hours)
- ElevenLabs: Free (10,000 chars/month)
- Gemini: Free tier available
- **Total: ₹0/month**

### Production (100 admin users, 2 sessions/day)
| Component | Cost per session | Monthly (6,000 sessions) |
|-----------|-----------------|--------------------------|
| Deepgram STT | ₹0.40 | ₹2,400 |
| Gemini Flash | ₹0.50 | ₹3,000 |
| ElevenLabs TTS | ₹4.00 | ₹24,000 |
| **Total** | **₹4.90** | **₹29,400 (~$350)** |

---

## Security

- **Admin-only by default** — `OTIS_ADMIN_ONLY=True`
- **Rate limited** — 10 sessions/hour, 50 commands/session
- **Command validation** — Injection attempts are blocked
- **Confirmation flow** — High-risk actions (approve/reject) require explicit confirmation
- **Full audit trail** — Every command logged to `otis_commands` table
- **Session isolation** — Each user only sees their own sessions and history

---

## For Developers

### Integration

```jsx
// In any page — OTIS Launcher is already in Layout.jsx
// No action needed — it's globally available
```

### API Endpoints
See `/backend/routes/OTIS_API_REFERENCE.md` for full REST API documentation.

### WebSocket Events
```javascript
// Listen for OTIS responses
socket.on('otis:response', ({ response, session_id }) => {
  // response: voice response text
})

// Listen for confirmation required (high-risk actions)
socket.on('otis:confirm_required', ({ command, risk_reason }) => {
  // Show confirmation dialog, then re-send with confirmed=true
})
```

### Architecture

```
Browser (voice widget)
  ├── Web Speech API (STT fallback)
  ├── Browser TTS (response playback)
  └── Socket.io WebSocket
        ↓
Flask Backend (app.py WebSocket handlers)
  ├── OtisCommandSecurity.validate()   ← injection check, quota
  └── OtisAgentPool.get_or_create()    ← cached agent instance
        ↓
OtisAgent.process_command()
  ├── _build_context_dict_cached()     ← DB queries, 60s TTL cache
  ├── gemini.generate_with_functions() ← Gemini 2.0 Flash
  ├── OtisFunctionRegistry.execute()   ← TravelSync actions
  └── _save_command()                  ← audit log
```

---

*OTIS — Omniscient Travel Intelligence System*
*TravelSync Pro v3.0 | Built 2026-03-27*
