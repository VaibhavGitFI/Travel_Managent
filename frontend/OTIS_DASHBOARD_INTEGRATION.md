# OTIS Dashboard Integration Guide

**How to add the OTIS Dashboard page to TravelSync Pro**

---

## Quick Start

### 1. Add Route to App.jsx

Edit `/frontend/src/App.jsx`:

```javascript
// Add import at the top (around line 23)
const OtisDashboard = lazy(() => import('./pages/OtisDashboard'))

// Add route inside the protected Layout section (around line 145, after Analytics)
<Route
  path="/otis"
  element={
    <Suspense fallback={<PageLoader />}>
      <OtisDashboard />
    </Suspense>
  }
/>
```

---

### 2. Add Navigation Item to Sidebar

Edit `/frontend/src/components/layout/Sidebar.jsx`:

```javascript
// Add import at the top
import { Volume2 } from 'lucide-react'

// Add to navGroups (in the "Manage" section, around line 40)
const navGroups = [
  {
    label: 'Travel',
    items: [
      { to: '/dashboard',     icon: LayoutDashboard, label: 'Dashboard' },
      { to: '/planner',       icon: MapPin,          label: 'Trip Planner' },
      { to: '/accommodation', icon: Building2,       label: 'Accommodation' },
      { to: '/meetings',      icon: Users,           label: 'Meetings' },
      { to: '/chat',          icon: Sparkles,        label: 'AI Chat' },
    ],
  },
  {
    label: 'Manage',
    items: [
      { to: '/expenses',  icon: Receipt,     label: 'Expenses' },
      { to: '/requests',  icon: FileText,    label: 'Requests' },
      { to: '/approvals', icon: CheckSquare, label: 'Approvals' },
      { to: '/analytics', icon: BarChart3,   label: 'Analytics', roles: ELEVATED },
      { to: '/otis',      icon: Volume2,     label: 'OTIS', roles: ELEVATED }, // NEW
    ],
  },
  // ... rest
]
```

**That's it!** OTIS Dashboard will now be accessible at `/otis` for admins and managers.

---

## What You Get

### Overview Tab
- **KPI Cards:** Total sessions, commands, avg latency, success rate
- **Daily Activity Chart:** Bar chart showing commands per day
- **Recent Sessions:** Quick view of last 5 sessions
- **Service Status:** Status of all OTIS services (wake word, STT, TTS, LLM)

### Sessions Tab
- **Session List:** All voice sessions with metadata
- **Session Details:** Click to view full conversation
- **Conversation Viewer:** Chat-style replay of user/assistant messages
- **Commands Executed:** List of functions called with latency
- **Delete Sessions:** Remove old sessions

### Commands Tab
- **Command History:** All commands executed
- **Function Calls:** See which functions were called
- **Latency Metrics:** Response time for each command
- **Success/Failure Status:** Visual indicators

### Settings Tab
- **Voice Speed:** Adjust TTS speed (0.5x - 2.0x)
- **Voice Pitch:** Adjust TTS pitch (-1 to +1)
- **Auto Listen:** Toggle automatic listening after wake word
- **Confirm Actions:** Toggle action confirmation prompts
- **Edit Mode:** Enable/disable editing
- **Save/Cancel:** Persist changes to backend

---

## Features

### Dashboard Analytics
```javascript
// Loads from backend API
const analytics = await getOtisAnalytics('7d')

analytics.summary:
- total_sessions: 10
- total_commands: 45
- avg_session_duration: 180
- total_voice_time: 1800
- avg_latency_ms: 350
- success_rate: 0.95

analytics.daily: [
  { date: '2026-03-26', sessions: 3, commands: 15, avg_latency: 350 }
]
```

### Session Details
```javascript
const session = await getOtisSession(sessionId)

session.conversation: [
  { turn_number: 1, role: 'user', content: '...', created_at: '...' },
  { turn_number: 2, role: 'assistant', content: '...', created_at: '...' }
]

session.commands: [
  {
    command_text: 'What pending approvals do I have?',
    response_text: 'You have three pending approvals...',
    function_called: 'get_pending_approvals',
    success: true,
    latency_ms: 350,
    created_at: '...'
  }
]
```

### Settings Management
```javascript
const settings = await getOtisSettings()

settings:
- voice_speed: 1.0
- voice_pitch: 0.0
- auto_listen: true
- confirm_actions: true

// Update
await updateOtisSettings({
  voice_speed: 1.2,
  voice_pitch: 0.1,
  auto_listen: false,
  confirm_actions: true
})
```

---

## UI Components Used

### From TravelSync UI Library
- `StatCard` - KPI metrics display
- `Card` - Container cards
- `Badge` - Status badges
- `Button` - Action buttons
- `Spinner` - Loading states
- `Skeleton` - Loading placeholders

### Icons (Lucide React)
- `Volume2` - OTIS icon
- `MessageSquare` - Sessions
- `Zap` - Commands
- `Settings` - Settings
- `Activity` - Overview
- `BarChart3` - Analytics
- `CheckCircle/XCircle` - Success/failure
- `Clock` - Duration/latency
- `Trash2` - Delete
- `Eye` - View details

---

## Permissions

### Admin/Manager Only
```javascript
// Sidebar nav item includes role restriction
{ to: '/otis', icon: Volume2, label: 'OTIS', roles: ELEVATED }

// ELEVATED = ['manager', 'admin', 'super_admin']
```

Only users with manager, admin, or super_admin roles will see the menu item.

### Permission Checks in Dashboard
```javascript
// Dashboard checks OTIS availability on mount
const status = await getOtisStatus()

if (!status.available) {
  // Shows error UI with reason
  // "OTIS is currently available to admins only"
}
```

---

## Tabs Explained

### 1. Overview Tab (Default)

**Purpose:** Quick glance at OTIS usage

**Sections:**
- **KPI Cards** (4 metrics)
- **Daily Activity Chart** (last 7 days)
- **Recent Sessions** (last 5)
- **Service Status** (wake word, STT, TTS, LLM)

**Use Case:** "How is OTIS performing? Are services healthy?"

---

### 2. Sessions Tab

**Purpose:** View and manage session history

**Features:**
- List all sessions (20 most recent)
- Expandable session details
- Full conversation replay
- Delete sessions
- Session metadata (duration, turns, wake word)

**Use Case:** "I want to review what users asked OTIS"

---

### 3. Commands Tab

**Purpose:** Audit trail of all commands

**Features:**
- Chronological command list (50 most recent)
- Function call tracking
- Latency metrics
- Success/failure status
- Searchable/filterable (future)

**Use Case:** "Which functions are being used most? Any failures?"

---

### 4. Settings Tab

**Purpose:** User preference management

**Features:**
- Voice speed slider (0.5x - 2.0x)
- Voice pitch slider (-1 to +1)
- Auto listen toggle
- Confirm actions toggle
- Edit/Save workflow

**Use Case:** "I want OTIS to speak faster"

---

## State Management

### Tab State
```javascript
const [activeTab, setActiveTab] = useState('overview')
// overview | sessions | commands | settings
```

### Data Loading
```javascript
const loadData = useCallback(async () => {
  const [statusRes, analyticsRes, sessionsRes, commandsRes, settingsRes] =
    await Promise.allSettled([
      getOtisStatus(),
      getOtisAnalytics(period),
      listOtisSessions(20),
      getOtisCommands(50),
      getOtisSettings(),
    ])

  // Set state for each
}, [period])
```

All API calls run in parallel for fast loading.

---

## Period Filter

```javascript
const [period, setPeriod] = useState('7d')

<select value={period} onChange={(e) => setPeriod(e.target.value)}>
  <option value="7d">Last 7 days</option>
  <option value="30d">Last 30 days</option>
  <option value="90d">Last 90 days</option>
</select>
```

Changes analytics time range dynamically.

---

## Session Details Modal

```javascript
// Click "View" on a session
const handleViewSession = async (sessionId) => {
  const data = await getOtisSession(sessionId)
  setSessionDetails(data)
  setSelectedSession(sessionId)
}

// Renders inline in the session card
{selectedSession === session.session_id && sessionDetails && (
  <div className="mt-4 pt-4 border-t">
    {/* Conversation replay */}
    {/* Commands executed */}
  </div>
)}
```

Expands within the session card (no modal overlay).

---

## Customization

### Change Time Periods

```javascript
<select>
  <option value="1d">Last 24 hours</option>  {/* NEW */}
  <option value="7d">Last 7 days</option>
  <option value="30d">Last 30 days</option>
  <option value="90d">Last 90 days</option>
  <option value="all">All time</option>      {/* NEW */}
</select>
```

### Add Export Feature

```javascript
const handleExport = () => {
  const csv = sessions.map(s =>
    `${s.session_id},${s.started_at},${s.total_turns}`
  ).join('\n')

  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'otis-sessions.csv'
  a.click()
}

<Button onClick={handleExport} leftIcon={<Download />}>
  Export CSV
</Button>
```

### Add Search/Filter

```javascript
const [searchQuery, setSearchQuery] = useState('')

const filteredSessions = sessions.filter(s =>
  s.session_id.includes(searchQuery) ||
  formatDate(s.started_at).includes(searchQuery)
)
```

---

## Error Handling

### API Failures
```javascript
const [statusRes, analyticsRes] = await Promise.allSettled([...])

if (statusRes.status === 'fulfilled') {
  setStatus(statusRes.value)
} else {
  // API failed, but don't crash the dashboard
  console.error('Status check failed')
}
```

Uses `Promise.allSettled` to handle partial failures gracefully.

### OTIS Unavailable
```javascript
if (!status?.available) {
  return (
    <Card className="p-8 text-center">
      <XCircle className="text-red-500" />
      <h2>OTIS Unavailable</h2>
      <p>{status?.reason}</p>
    </Card>
  )
}
```

Shows user-friendly error when OTIS is disabled.

---

## Performance

### Loading States
```javascript
if (loading) return <LoadingSkeleton />

const LoadingSkeleton = () => (
  <div>
    <Skeleton className="h-20 w-full" />
    <div className="grid grid-cols-4 gap-3">
      {[1,2,3,4].map(i => <Skeleton key={i} className="h-24" />)}
    </div>
  </div>
)
```

### Data Refresh
```javascript
const loadData = useCallback(async () => {
  // Loads on mount and when period changes
}, [period])

<button onClick={loadData}>
  <RefreshCw size={13} />
  Refresh
</button>
```

---

## Accessibility

### Keyboard Navigation
- Tab through navigation tabs
- Tab through session cards
- Tab through buttons
- Enter to activate

### Screen Readers
- Semantic HTML (`<nav>`, `<main>`, `<button>`)
- Descriptive labels
- Status badges with text

### Visual
- Color-coded status indicators
- High contrast mode support
- Dark mode support (follows theme)

---

## Testing

### Manual Test Flow

**1. Navigate to Dashboard**
```
http://localhost:5173/otis
```

**2. Check Overview Tab**
- KPI cards should show data (or 0 if no usage)
- Daily activity chart should render
- Recent sessions should show (if any)
- Service status should show green/yellow/red dots

**3. Check Sessions Tab**
- Click "View" on a session
- Should expand to show conversation
- Commands should list with function calls
- Delete button should work (with confirmation)

**4. Check Commands Tab**
- Should list all commands chronologically
- Should show function names
- Should show success/failure icons
- Should show latency

**5. Check Settings Tab**
- Click "Edit Settings"
- Adjust sliders
- Toggle switches
- Click "Save Changes"
- Should persist and toast success

**6. Test Period Filter**
- Change from "7d" to "30d"
- Should reload analytics data
- Charts should update

---

## Troubleshooting

### Dashboard shows "OTIS Unavailable"

**Check:**
1. Backend running? `http://localhost:3399/api/otis/status`
2. `OTIS_ENABLED=True` in `backend/.env`?
3. User has admin/manager role?

### No sessions showing

**Cause:** User hasn't used OTIS yet

**Solution:** Use OTIS voice widget to create sessions

### Analytics shows 0

**Cause:** No data in selected period

**Solution:** Change period to "90d" or use OTIS more

### Settings not saving

**Check:**
1. Network tab - is PUT request succeeding?
2. Backend logs - any errors?
3. Check `otis_settings` table in database

---

## Future Enhancements

### Planned
- ⏳ Search/filter sessions
- ⏳ Export sessions to CSV/JSON
- ⏳ Delete multiple sessions
- ⏳ Charts with Chart.js/Recharts
- ⏳ Real-time updates (WebSocket)
- ⏳ Voice playback (audio recordings)
- ⏳ Transcript search
- ⏳ Favorite commands
- ⏳ Command shortcuts

### Under Consideration
- Usage by user (admin view)
- Cost tracking
- Performance benchmarks
- A/B testing different prompts
- Voice quality ratings

---

## Support

For issues:
1. Check browser console for errors
2. Check backend logs: `/backend/logs/app.log`
3. Test API directly: `curl http://localhost:3399/api/otis/sessions`
4. Verify database has data: `SELECT * FROM otis_sessions LIMIT 10`

---

**Status:** Production Ready ✅
**Last Updated:** 2026-03-26
