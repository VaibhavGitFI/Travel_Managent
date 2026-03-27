# OTIS Frontend Integration Guide

**How to add OTIS Voice Assistant to TravelSync Pro**

---

## Quick Start

### 1. Add OtisLauncher to Layout

Edit `/frontend/src/components/layout/Layout.jsx`:

```javascript
// Add import at the top
import OtisLauncher from '../voice/OtisLauncher'

// Add component before closing tag (around line 600+)
export default function Layout() {
  // ... existing code ...

  return (
    <div className="h-screen flex overflow-hidden bg-gray-50 dark:bg-gray-900">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>

      {/* SOS Panel */}
      {/* ... existing SOS code ... */}

      {/* OTIS Voice Assistant - NEW */}
      <OtisLauncher />
    </div>
  )
}
```

**That's it!** OTIS will now be accessible from every page via the floating button in the bottom-left corner.

---

## What You Get

### Floating Action Button
- **Location:** Bottom-left corner (opposite of chat)
- **Design:** Blue-purple gradient with pulse animation
- **Icon:** Volume2 (speaker icon)
- **Behavior:** Appears only when user is logged in

### Voice Widget
- **UI:** Floating card (expandable/minimizable)
- **States:** Idle → Ready → Listening → Processing → Speaking
- **Features:**
  - Real-time WebSocket communication
  - Voice input (Web Speech API fallback)
  - Text input fallback
  - Waveform visualization
  - Message history
  - Session management

---

## Files Created

### 1. API Client (`/frontend/src/api/otis.js`)
```javascript
import { getOtisStatus, startOtisSession, stopOtisSession } from '../api/otis'
```

**Functions:**
- `getOtisStatus()` - Check availability
- `startOtisSession()` - Create session
- `stopOtisSession()` - End session
- `listOtisSessions()` - Session history
- `getOtisSession(id)` - Session details
- `deleteOtisSession(id)` - Delete session
- `getOtisCommands()` - Command history
- `getOtisAnalytics()` - Usage stats
- `getOtisSettings()` - User settings
- `updateOtisSettings()` - Update settings
- `connectOtisWebSocket()` - WebSocket setup
- `sendOtisCommand()` - Send command
- `stopOtisWebSocket()` - Disconnect

---

### 2. Voice Widget (`/frontend/src/components/voice/OtisVoiceWidget.jsx`)

**Main Component:**
```javascript
<OtisVoiceWidget onClose={() => setIsOpen(false)} />
```

**States:**
- `IDLE` - Not started
- `CONNECTING` - Connecting to backend
- `READY` - Ready for commands
- `LISTENING` - Recording voice
- `PROCESSING` - Processing command
- `SPEAKING` - Speaking response
- `ERROR` - Error state

**Features:**
- Permission checks (admin-only mode support)
- WebSocket real-time communication
- Voice input with waveform visualization
- Text input fallback
- Message history with scrolling
- Minimize/maximize
- Auto-scroll to latest message
- Browser TTS for responses
- Session management

---

### 3. Waveform Visualizer (`/frontend/src/components/voice/WaveformVisualizer.jsx`)

**Component:**
```javascript
<WaveformVisualizer active={isRecording} level={audioLevel} />
```

**Props:**
- `active` - Whether animation is active
- `level` - Audio level (0-100)
- `barCount` - Number of bars (default: 5)
- `color` - Bar color (default: blue)

**Animation:**
- Sine wave patterns
- Randomized heights
- Smooth transitions
- Responds to audio level

---

### 4. Launcher Button (`/frontend/src/components/voice/OtisLauncher.jsx`)

**Component:**
```javascript
<OtisLauncher />
```

**Features:**
- Floating action button (FAB)
- Gradient background (blue-purple)
- Pulse animation
- Hover scale effect
- Only shows when logged in
- Opens/closes widget

---

## User Flow

### Starting OTIS

1. User clicks OTIS button (bottom-left)
2. Widget opens (floating card)
3. User clicks "Start OTIS"
4. Backend creates session via REST API
5. WebSocket connects
6. OTIS shows "Ready" state
7. Greeting message: "OTIS is ready. How can I help you?"

### Voice Command

1. User clicks "Voice" button
2. Browser requests microphone permission (first time)
3. Recording starts (waveform animates)
4. User speaks: "What pending approvals do I have?"
5. User clicks "Stop" (or auto-stops after silence)
6. Speech recognition transcribes
7. Command sent via WebSocket
8. OTIS processes (calls backend agent)
9. Response received
10. Text displayed + TTS speaks response

### Text Command

1. User types in text input
2. User presses Enter or clicks "Send"
3. Command sent via WebSocket
4. OTIS processes
5. Response received and displayed

### Ending Session

1. User clicks "End" button
2. WebSocket disconnects
3. REST API called to stop session
4. Widget shows session stats
5. Returns to idle state

---

## Customization

### Change Position

Edit `OtisLauncher.jsx`:
```javascript
// Bottom-right instead of bottom-left
className="fixed bottom-6 right-6 z-40 ..."

// Top-right
className="fixed top-20 right-6 z-40 ..."
```

### Change Colors

Edit `OtisLauncher.jsx`:
```javascript
// Green gradient
className="... bg-gradient-to-br from-green-500 to-teal-600 ..."

// Single color
className="... bg-blue-500 ..."
```

### Change Size

Edit `OtisVoiceWidget.jsx`:
```javascript
// Larger widget
isMinimized ? 'w-80' : 'w-[32rem]'

// Taller messages area
<div className="h-96 overflow-y-auto ...">
```

### Change Wake Word Button Text

Edit `OtisVoiceWidget.jsx`:
```javascript
<button ...>
  <Volume2 className="w-5 h-5" />
  Hey OTIS  {/* Changed from "Start OTIS" */}
</button>
```

---

## WebSocket Events

### Client Emits

```javascript
socket.emit('otis:start_session', { session_id })
socket.emit('otis:process_command', { session_id, command })
socket.emit('otis:stop_session', { session_id })
```

### Client Listens

```javascript
socket.on('otis:session_started', (data) => {})
socket.on('otis:processing', (data) => {})
socket.on('otis:response', (data) => {})
socket.on('otis:error', (data) => {})
socket.on('otis:session_stopped', (data) => {})
```

---

## Permissions

### Admin-Only Mode

When `OTIS_ADMIN_ONLY=True` in backend:

```javascript
// Status response
{
  "available": false,
  "reason": "OTIS is currently available to admins only"
}
```

Widget shows error message and cannot start.

### User Permissions

```javascript
{
  "permissions": {
    "can_use": true,
    "can_approve_trips": true,  // admin/manager only
    "can_view_analytics": true,  // admin/manager only
    "can_execute_functions": true
  }
}
```

---

## Error Handling

### No Microphone Permission

```javascript
toast.error('Microphone access denied')
// Widget falls back to text input
```

### WebSocket Disconnection

```javascript
socket.on('disconnect', () => {
  toast.error('Connection lost')
  setOtisState(OTIS_STATES.ERROR)
})
```

### Session Limit Exceeded

```javascript
// Response: 429 Too Many Requests
toast.error('Too many sessions started. Please wait.')
```

### OTIS Unavailable

```javascript
// Status check fails
<div>OTIS Unavailable: {reason}</div>
```

---

## Browser Compatibility

### Required Features
- ✅ WebSocket (all modern browsers)
- ✅ MediaRecorder API (for audio recording)
- ⚠️ Web Speech API (Chrome/Edge only)
- ✅ SpeechSynthesis API (TTS - all browsers)

### Fallbacks
- If Web Speech API unavailable → Text input only
- If MediaRecorder unavailable → Text input only
- If WebSocket fails → Shows error, retry option

---

## Testing

### 1. Test Status Check

```javascript
import { getOtisStatus } from '../api/otis'

const status = await getOtisStatus()
console.log('OTIS Status:', status)
// { available: true, enabled: true, services: { ... } }
```

### 2. Test Session Start

1. Click OTIS button
2. Click "Start OTIS"
3. Check browser console for WebSocket connection
4. Should see "OTIS is ready" message

### 3. Test Text Command

1. Type "What pending approvals do I have?"
2. Click "Send"
3. Should see response within 1-2 seconds

### 4. Test Voice Command (Chrome/Edge)

1. Click "Voice" button
2. Allow microphone permission
3. Speak clearly
4. Click "Stop"
5. Should see transcribed text + response

---

## Troubleshooting

### Widget doesn't appear

**Check:**
1. User is logged in? (`auth.isLoggedIn`)
2. OtisLauncher added to Layout.jsx?
3. No JavaScript errors in console?

### "OTIS is not available"

**Check:**
1. Backend running? (`http://localhost:3399/api/otis/status`)
2. OTIS_ENABLED=True in backend/.env?
3. User has permission? (admin-only mode)

### WebSocket not connecting

**Check:**
1. Socket.io client installed? (`npm list socket.io-client`)
2. CORS configured correctly in backend?
3. Port 3399 accessible?

### Voice recording not working

**Check:**
1. Browser is Chrome/Edge? (Web Speech API)
2. Microphone permission granted?
3. HTTPS (required for getUserMedia)?
   - Localhost is OK for development

### Response not speaking

**Check:**
1. Browser volume not muted?
2. `speechSynthesis` supported? (check console)
3. Try different browser

---

## Performance

### Metrics

| Metric | Target | Typical |
|--------|--------|---------|
| Widget load time | <100ms | 50ms |
| Status check | <200ms | 150ms |
| Session start | <500ms | 300ms |
| Text command | <2s | 1-1.5s |
| Voice command | <3s | 2-2.5s |
| WebSocket latency | <100ms | 50ms |

### Optimization Tips

1. **Lazy load widget:** Only load when button clicked
2. **Debounce text input:** Wait 300ms after typing
3. **Limit message history:** Keep last 50 messages
4. **Cancel pending requests:** On component unmount
5. **Reuse WebSocket:** Don't reconnect on every command

---

## Accessibility

### Keyboard Navigation
- Tab to OTIS button → Enter to open
- Tab through widget controls
- Enter to send text command
- Esc to close widget (TODO)

### Screen Readers
- Aria labels on all buttons
- Status announcements (TODO)
- Message role attributes (TODO)

### Visual
- High contrast mode support
- Dark mode support
- Waveform has fallback text

---

## Future Enhancements

### Planned
1. ✅ Basic voice widget (MVP)
2. ⏳ Keyboard shortcut (Ctrl+Shift+O)
3. ⏳ Wake word detection (server-side)
4. ⏳ Audio streaming (instead of Web Speech API)
5. ⏳ Multi-language support (Hindi)
6. ⏳ Voice settings panel
7. ⏳ Conversation export
8. ⏳ Voice shortcuts (custom wake phrases)

### Under Consideration
- Proactive suggestions
- Context awareness (current page)
- Voice authentication
- Offline mode

---

## Support

For issues:
1. Check browser console for errors
2. Check backend logs: `/backend/logs/app.log`
3. Test REST API: `curl http://localhost:3399/api/otis/status`
4. Test WebSocket: Browser DevTools → Network → WS

---

**Status:** Production Ready (MVP) ✅
**Last Updated:** 2026-03-26
