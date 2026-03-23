
# TravelSync Pro — Build Checklist
**Demo: 21 March 2026 | Today: 15 March 2026 | 6 days**

Track every change here. One feature at a time. No partial merges.

---

## LEGEND
- `[ ]` Not started
- `[~]` In progress
- `[x]` Done & tested
- `[!]` Blocked / needs input

---

## SPRINT 1 — Core AI & Real-Time (Days 1–2: Mar 15–16)

### 1. AI Chat — Grounded Responses  `[x]`
Fix Gemini chat so it gives real, contextual answers grounded in live data.
- [x] Inject user profile + active trips into system prompt
- [x] Inject live weather when city is detected
- [x] Inject live currency rates when currency intent detected
- [x] Remove hallucination risk — explicit instructions to not invent flight numbers/prices
- [x] Add travel knowledge base context to system prompt
- **File:** `backend/agents/chat_agent.py`, `backend/routes/chat.py`

### 2. Real-Time WebSocket Notifications `[x]`
Wire up SocketIO so events fire when things happen.
- [x] Emit `notification` on approval decision (approved/rejected) → notify requester
- [x] Emit `notification` on request submit → notify assigned manager
- [x] Emit `trip_update` when orchestrator finishes plan
- [x] Frontend: `socket.on('notification')` → Zustand + rich toast
- [x] User room auto-join on connect via session cookie
- [x] `backend/extensions.py` (SocketIO singleton, no circular imports)
- [x] `frontend/src/lib/socket.js` (singleton, autoConnect: false)
- **Files:** `backend/extensions.py`, `backend/app.py`, `backend/routes/approvals.py`, `backend/routes/requests.py`, `backend/routes/trips.py`, `frontend/src/lib/socket.js`, `frontend/src/components/layout/Layout.jsx`

### 3. Action Cards in Chat `[x]`
Wire up AI action cards so chat can navigate the app.
- [x] Frontend Chat.jsx renders action card buttons below AI reply
- [x] `openTab` action → `navigate(target)` via ROUTE_MAP
- [x] `openSOS` action → emergency numbers toast (SOS page wired in Feature #5)
- [x] `tel` action → `window.location.href = 'tel:...'`
- [x] `action_cards` captured from API response + chat history
- [x] Color-coded buttons: SOS=red, tel=green, navigation=accent
- **File:** `frontend/src/pages/Chat.jsx`

### 4. AI Meeting Parser (Email/WhatsApp → Auto-fill) `[x]`
Paste raw text, Gemini extracts meeting details.
- [x] `POST /api/meetings/parse-text` endpoint
- [x] Gemini prompt with structured JSON extraction → returns `extracted` fields
- [x] Regex fallback when Gemini unavailable (date, time, email, phone)
- [x] Date/time normalizer: multi-format → YYYY-MM-DD / HH:MM
- [x] Frontend: "Parse Email/WA" button on Meetings page
- [x] Parse modal: email/whatsapp toggle, paste area, extracted preview, "Use These Details" → pre-fills form
- [x] `parseMeetingText` API function in `meetings.js`
- **Files:** `backend/routes/meetings.py`, `backend/agents/meeting_agent.py`, `frontend/src/api/meetings.js`, `frontend/src/pages/Meetings.jsx`

### 5. SOS Emergency System `[x]`
Log SOS events, surface emergency contacts.
- [x] `POST /api/sos` — log event to notifications table, broadcast to all managers via SocketIO
- [x] `GET /api/sos/contacts?city=X` — return local emergency numbers + nearby hospitals
- [x] `sos_agent.py` — 40+ cities (India + international), Google Maps hospital search
- [x] `frontend/src/api/sos.js` — API functions
- [x] Floating SOS button (fixed bottom-right, visible when logged in)
- [x] SOS modal: quick call buttons (108/100/112), city-specific numbers, alert manager
- [x] `openSOS` action card now triggers this modal
- **Files:** `backend/routes/sos.py`, `backend/agents/sos_agent.py`, `frontend/src/api/sos.js`, `frontend/src/components/layout/Layout.jsx`

---

## SPRINT 2 — Trip Lifecycle & Intelligence (Days 3–4: Mar 17–18)

### 6. Trip Status Lifecycle Complete `[x]`
Close the loop: approved → booked → in_progress → completed.
- [x] `PUT /api/requests/:id/status` endpoint with role-based transition rules
- [x] `check_and_auto_transition()` — runs on every `GET /api/requests`, no cron needed
- [x] `update_request_status()` with `_ALLOWED_TRANSITIONS` map per role
- [x] Frontend: status transition buttons on each RequestRow (Mark Booked/Started/Completed)
- [x] SocketIO notification when status updated by manager/admin
- **Files:** `backend/routes/requests.py`, `backend/agents/request_agent.py`, `frontend/src/api/requests.js`, `frontend/src/pages/Requests.jsx`

### 7. AI Trip Summary Report `[x]`
Gemini generates post-trip report on completion.
- [x] `GET /api/requests/:id/report` endpoint
- [x] Gemini prompt: destination, meetings, expenses vs budget, compliance
- [x] Regex/structured fallback when Gemini unavailable
- [x] Frontend: "View Report" button on completed trips + report modal
- **Files:** `backend/routes/requests.py`, `backend/agents/request_agent.py`, `frontend/src/api/requests.js`, `frontend/src/pages/Requests.jsx`

### 8. Per Diem Calculator `[x]`
City-tier based daily allowance calculator.
- [x] 4-tier rate map: Tier 1 metros, Tier 2 majors, Tier 3 others, International
- [x] `GET /api/requests/per-diem?city=X&days=N` endpoint
- [x] Live estimate shown in Request form when city + dates are filled (auto-fetch)
- [x] Displays daily rates breakdown (hotel/meals/transport/incidentals)
- **Files:** `backend/routes/requests.py`, `frontend/src/api/requests.js`, `frontend/src/pages/Requests.jsx`

### 9. Streaming AI Chat `[x]`
Progressive token streaming via Server-Sent Events.
- [x] `gemini_service.generate_stream()` using Gemini streaming API
- [x] Flask: `Response(stream_with_context(...), content_type='text/event-stream')`
- [x] Frontend: `fetch` with ReadableStream, append tokens in-place
- [x] Streaming cursor (blinking `|`) during generation; fallback TypingBubble for file uploads
- [x] File attachments continue using non-streaming path
- **Files:** `backend/services/gemini_service.py`, `backend/routes/chat.py`, `frontend/src/api/chat.js`, `frontend/src/pages/Chat.jsx`

---

## SPRINT 3 — Advanced AI (Days 4–5: Mar 18–19)

### 10. Budget Forecasting Agent `[x]`
Intelligent budget prediction using history + Amadeus price metrics.
- [x] `budget_forecast_agent.py` — pull historical expenses for route, Amadeus price metrics
- [x] `POST /api/requests/budget-forecast`
- [x] Show forecast range on Request creation form (min/mid/max + breakdown + AI insight)
- [x] "Use as Budget" button pre-fills estimated budget field
- **Files:** `backend/agents/budget_forecast_agent.py`, `backend/routes/requests.py`, `frontend/src/api/requests.js`, `frontend/src/pages/Requests.jsx`

### 11. Document Processing Pipeline `[x]`
Multi-doc OCR: flight tickets, hotel vouchers, visa, train tickets.
- [x] `document_agent.py` — Gemini Vision with type-specific prompts + Vision API + regex fallback
- [x] `POST /api/uploads/parse-document`
- [x] Auto-populate travel_requests fields from parsed docs via `prefill_fields`
- [x] Flag visa expiry overlapping with trip (`warnings[]`)
- **Files:** `backend/agents/document_agent.py`, `backend/routes/uploads.py`

### 12. Carbon Footprint Tracker `[x]`
CO₂ calculation per trip and greener alternatives.
- [x] CO₂ formula per mode (flight/train/cab/bus) — DEFRA/ICAO 2023 factors
- [x] `calculate_carbon(distance_km, mode, travelers)` in `travel_mode_agent.py`
- [x] `get_carbon_analytics()` in `analytics_agent.py` — monthly trend + dept comparison
- [x] `GET /api/analytics/carbon` + `GET /api/analytics/carbon/estimate`
- [x] Greener alternative suggestions + trees-to-offset metric
- **Files:** `backend/agents/travel_mode_agent.py`, `backend/agents/analytics_agent.py`, `backend/routes/analytics.py`

### 13. Multi-Agent Validation Layer `[x]`
Cross-validate agent outputs for coherence.
- [x] `validator_agent.py` — budget coherence, date coherence, compliance pre-check, agent data cross-check
- [x] Returns `validation_flags[]` with severity (error/warning/info) + overall (pass/warn/fail)
- [x] Integrated into orchestrator — runs after all 6 agents; result in `validation` key
- [x] Gemini AI review of flags when issues detected
- **Files:** `backend/agents/validator_agent.py`, `backend/agents/orchestrator.py`

---

## SPRINT 4 — GCP Deployment (Days 5–6: Mar 19–21)

### 14. GCP API Setup `[x]`
Enable and configure all required APIs.
- [x] All API keys documented in CLAUDE.md — obtain from respective portals
- [x] Stored in GCP Secret Manager via cloudbuild.yaml `--set-secrets`
- [x] All services have fallback mode when keys not set

### 15. GCP Secret Manager Integration `[x]`
Pull secrets from Secret Manager instead of .env in production.
- [x] `config.py` — `_is_gcp()` detects Cloud Run/App Engine via `K_SERVICE` env var
- [x] `_get_env_or_secret()` checks env first, then Secret Manager on GCP
- [x] `cloudbuild.yaml` updated with all secret names including `JWT_SECRET_KEY`, `DATABASE_URL`
- **Files:** `backend/config.py`, `cloudbuild.yaml`

### 16. Cloud SQL Setup `[x]`
PostgreSQL on Cloud SQL for production DB.
- [x] `database.py` — `get_db()` uses psycopg2 when `DATABASE_URL` is set
- [x] `_PGAdapter` wraps psycopg2 to provide sqlite3-compatible interface (`?` placeholders, dict rows)
- [x] `psycopg2-binary` added to `requirements.txt`
- [x] Zero code changes needed in routes — adapter is transparent
- **Files:** `backend/database.py`, `requirements.txt`

### 17. Cloud Run Deployment `[x]`
Final deployment to Cloud Run.
- [x] `Dockerfile` — multi-stage: Node 20 builds React, Python 3.11-slim runs backend
- [x] `cloudbuild.yaml` — builds + pushes image, deploys to Cloud Run asia-south1
- [x] Tagged with `$COMMIT_SHA` + `latest` for rollback capability
- [x] All secrets via `--set-secrets`; `GCP_PROJECT_ID` via `--set-env-vars`
- **Files:** `Dockerfile`, `cloudbuild.yaml`

### 18. JWT Authentication `[x]`
Stateless auth for Cloud Run horizontal scaling.
- [x] `auth.py` — `generate_tokens()`, `verify_token()` using PyJWT HS256
- [x] `get_current_user()` checks Bearer header first, then session cookie (backward-compatible)
- [x] `POST /api/auth/login` returns `{access_token, refresh_token}` alongside existing session
- [x] `POST /api/auth/refresh` — exchange refresh token for new access token
- [x] `frontend/src/api/auth.js` — `setAccessToken()`, stores refresh in sessionStorage
- [x] `PyJWT` added to `requirements.txt`
- **Files:** `backend/auth.py`, `backend/routes/auth.py`, `frontend/src/api/auth.js`, `requirements.txt`

### 19. Rate Limiting `[x]`
Protect all endpoints from abuse.
- [x] `flask-limiter` added to `extensions.py` (singleton, no circular imports)
- [x] Plan-trip: 10/min, Chat + ChatStream: 30/min, Login: 5/min per IP
- [x] 429 handled in `frontend/src/api/client.js` → toast with retry-after info
- [x] `flask-limiter` added to `requirements.txt`
- **Files:** `backend/extensions.py`, `backend/app.py`, `backend/routes/trips.py`, `backend/routes/chat.py`, `backend/routes/auth.py`, `frontend/src/api/client.js`

---

## ONGOING — Code Quality & Security

- [ ] All endpoints return consistent `{success, data/error}` envelope
- [ ] No secrets in code (only env vars / Secret Manager)
- [ ] All file uploads: type check + size check + path traversal prevention
- [ ] All SQL: parameterized queries only (no f-string SQL)
- [ ] Logging: structured JSON logs for Cloud Run (no print() statements)

---

## COMPLETED

*(Move items here when done)*

- [x] React + Flask architecture setup
- [x] All 12 Flask blueprint routes working
- [x] Database schema with auto-migration
- [x] Login auth fix (sqlite3.Row → dict)
- [x] Uploads auth security fix
- [x] Single-command startup (npm start)
- [x] .gitignore rebuilt
- [x] README fully documented

---

*Last updated: 2026-03-15*

---

## Frontend Refactor & AI System Improvements

### Design System Foundation
- [x] Added semantic design tokens to `tailwind.config.js`: `brand.*` (dark, mid, light, muted, cyan) and `surface.*` (DEFAULT, raised, sunken, border, border-strong)
- [x] Created `cn()` utility at `frontend/src/lib/cn.js` wrapping clsx for conditional classes
- [x] Updated CSS custom properties in `index.css` to match new token system
- [x] Added comprehensive chat markdown prose styles (`.chat-prose`) for rich AI response rendering
- [x] Installed `react-markdown` + `remark-gfm` for proper markdown rendering in AI chat

### Layout Shell Refactor
- [x] **Sidebar** — Split navigation into "Travel" and "Manage" groups with section headings, added user profile footer (name/role/logout), removed CitySkylineSVG, added collapse/expand toggles, replaced all hardcoded hex with brand tokens, active indicator bar
- [x] **Topbar** — Added Cmd+K shortcut trigger (navigates to AI Chat), shows user full name on desktop, removed dead breadcrumb code, cleaner health indicator, uses surface tokens
- [x] **Layout** — Main content area now provides padding (`px-4 py-5 sm:px-6 sm:py-6`), pages no longer need their own rounded-3xl wrappers, background uses `bg-surface` token

### AI Chat System Enhancement
- [x] **Rich DB Context Injection** (`chat_agent.py`) — `_build_user_context()` queries real DB data: recent travel requests (last 5 with status/dates/budget), pending approvals (for managers), upcoming meetings (next 7 days), expense totals, travel policy summary. Injected as structured system prompt context.
- [x] **Multi-turn Conversation** (`gemini_service.py`) — Added `generate_with_history()` and `stream_with_history()` using Gemini `model.start_chat(history=...)` for proper multi-turn context. Chat remembers last 6 messages.
- [x] **History-Aware Streaming** (`routes/chat.py`) — Stream endpoint now uses `build_system_prompt()` with user DB context + `stream_with_history()` with conversation history
- [x] **Markdown Rendering** (`Chat.jsx`) — Replaced naive `renderMessageContent()` with `react-markdown` + `remark-gfm`. Proper headings, bold, lists, tables, code blocks with syntax highlighting. `.chat-prose` CSS class for consistent styling.
- [x] **Streaming Resilience** (`api/chat.js`) — Added 60s timeout via AbortController, JWT Bearer token in stream request headers
- [x] **Grounding Instructions** — System prompt explicitly forbids inventing booking refs, flight numbers, or prices. Instructs model to cite actual context data.

### Page-by-Page Token Cleanup
- [x] **Dashboard** — Removed rounded-3xl wrapper, replaced 20+ hardcoded hex values with brand/surface tokens, cleaner stat cards and quick actions
- [x] **Login** — Updated gradient to use brand-dark/navy tokens, cleaned submit button and placeholder colors
- [x] **Requests** — Full token replacement, consistent surface borders and backgrounds
- [x] **Meetings** — Full token replacement with cn() utility
- [x] **Expenses** — Token replacement (kept chart SVG hex colors as-is)
- [x] **Analytics** — Full token replacement
- [x] **Approvals** — Full token replacement
- [x] **TripPlanner** — Full token replacement
- [x] **Accommodation** — Full token replacement
- [x] **StatCard component** — Updated corporate accent to use surface/brand tokens

### Real-Time Improvements
- [x] **Stale Data Store** — Added `staleData` slice to Zustand store with `markStale(key)` and `clearStale(key)` actions for requests/meetings/expenses/approvals/analytics
- [x] **WebSocket Data Changed Events** — Layout.jsx listens for `data_changed` socket events and marks corresponding data as stale
- [x] **Backend Emissions** — Approval approve/reject routes now emit `data_changed` for both `approvals` and `requests` entities via SocketIO

### New Libraries Added
- `react-markdown` — Markdown rendering for AI chat responses
- `remark-gfm` — GitHub Flavored Markdown support (tables, strikethrough, task lists)

### Architecture Decisions
- **No component library** — Kept existing custom Tailwind components (Button, Input, Modal, Badge, etc.) rather than adding shadcn/ui. Existing components work well and avoid a multi-day migration.
- **No dark mode** — Deferred to avoid doubling design surface area before demo
- **SSE kept for chat streaming** — No migration to WebSocket; SSE works correctly for unidirectional AI responses
- **Multi-turn via Gemini chat sessions** — Uses `model.start_chat(history=...)` rather than concatenating all messages into a single prompt

---

## Tier 1: Advanced Real-Time + AI Features

### 1. Skeleton Loading Screens `[x]`
Content-shaped shimmer placeholders instead of centered spinners.
- [x] `Skeleton.jsx` — composable primitives: `Skeleton`, `SkeletonText`, `SkeletonCard`, `SkeletonRow`, `SkeletonTable`
- [x] Uses existing `.skeleton` CSS class (shimmer animation in `index.css`)
- [x] Dashboard → 5x SkeletonRow in trips list
- [x] Requests → SkeletonRow list
- [x] Approvals → SkeletonRow list
- [x] Expenses → SkeletonTable (desktop) + SkeletonRow (mobile)
- [x] Meetings → 6x SkeletonCard in 3-col grid
- [x] Analytics → stat card skeletons + chart area rectangles
- [x] Chat → alternating message bubble skeletons
- **Files:** `frontend/src/components/ui/Skeleton.jsx`, 7 page components

### 2. Real-time Auto-Refresh `[x]`
Pages auto-refresh when socket `data_changed` events fire.
- [x] `useAutoRefresh.js` hook — watches `staleData[key]`, calls `fetchFn`, clears stale
- [x] Wired into: Requests, Approvals, Expenses, Meetings, Analytics, Dashboard
- [x] Backend emits `data_changed` from: requests (create/submit/status), expenses (submit), meetings (create/update/delete)
- **Files:** `frontend/src/hooks/useAutoRefresh.js`, 6 page components, `backend/routes/requests.py`, `backend/routes/expenses.py`, `backend/routes/meetings.py`

### 3. Pagination + Search `[x]`
Server-side pagination and search for large lists.
- [x] Backend: `?page=1&per_page=20&search=X` on GET /api/requests, /api/expenses, /api/meetings
- [x] Response: `{success, items, total, page, per_page, total_pages}` + backward-compat keys
- [x] `usePagination.js` hook — page/search/loading/fetch with 400ms debounced search
- [x] `Pagination.jsx` — prev/next controls + page indicator
- [x] Requests page: search input + pagination controls
- [x] Expenses page: search input + pagination controls
- [x] Meetings page: search input + pagination controls
- **Files:** `frontend/src/hooks/usePagination.js`, `frontend/src/components/ui/Pagination.jsx`, 3 page components, 3 backend routes, 3 API modules

### 4. Proactive AI Notifications `[x]`
Smart alerts on Dashboard — upcoming trips, pending approvals, budget warnings.
- [x] `alerts_agent.py` — `get_user_alerts(user)` queries DB for upcoming trips (3 days), pending approvals (managers), expiring requests, budget warnings (80%+ monthly limit)
- [x] `GET /api/alerts` endpoint via `alerts_bp`
- [x] `getAlerts()` in `analytics.js`
- [x] Dashboard: dismissible AlertCard components above KPI stats (severity colors: info=blue, warning=amber, critical=red)
- **Files:** `backend/agents/alerts_agent.py`, `backend/routes/alerts.py`, `backend/app.py`, `frontend/src/api/analytics.js`, `frontend/src/pages/Dashboard.jsx`

### 5. Chat → Action Execution (Trip Planning Inline) `[x]`
"Plan a trip to Mumbai" in chat runs the orchestrator and shows results inline.
- [x] `chat_agent.py`: when intent=`plan_trip` + destination exists, calls `orchestrator.plan_trip()`
- [x] `_summarize_trip_results()` extracts top 3 flights, top 3 hotels, weather summary
- [x] Streaming endpoint: orchestrator runs before stream starts, `trip_results` included in `done` SSE event
- [x] Non-streaming endpoint: `trip_results` in response dict
- [x] `TripResultsCard` component: destination header, top flights/hotels with prices, weather summary, "View Full Plan" link
- **Files:** `backend/agents/chat_agent.py`, `backend/routes/chat.py`, `frontend/src/pages/Chat.jsx`

---

## Tier 2: Differentiating Features

### 6. AI Expense Anomaly Detection `[x]`
Flag suspicious expenses with 5 detection rules.
- [x] `anomaly_agent.py` — 5 detectors: duplicate amounts, weekend submissions, category outliers (2x avg), round amounts (>₹5000), rapid-fire submissions (<5min)
- [x] `GET /api/expenses/anomalies` endpoint
- [x] `getExpenseAnomalies()` API function
- [x] Expenses page: "AI Anomaly Scan" panel with Scan button, color-coded anomaly cards (warning=amber, info=blue)
- **Files:** `backend/agents/anomaly_agent.py`, `backend/routes/expenses.py`, `frontend/src/api/expenses.js`, `frontend/src/pages/Expenses.jsx`

### 7. Smart Trip Recommendations `[x]`
AI suggests optimal combos based on past trips + travel policy.
- [x] `recommendation_agent.py` — queries past trips, historical expenses, travel policy; generates hotel/flight tips + budget insight
- [x] Gemini AI insight: 3 actionable tips specific to the destination
- [x] `POST /api/trips/recommendations` endpoint
- [x] `getTripRecommendations()` API function
- [x] TripPlanner: "AI Tips" button fetches recommendations, displays hotel/flight policy tips, budget info, AI insights
- **Files:** `backend/agents/recommendation_agent.py`, `backend/routes/trips.py`, `frontend/src/api/trips.js`, `frontend/src/pages/TripPlanner.jsx`

### 8. Redis Cache Layer `[x]`
Unified cache with optional Redis + automatic TTLCache fallback.
- [x] `cache_service.py` — `CacheStore` class: Redis primary (when `REDIS_URL` set), TTLCache fallback (zero config)
- [x] Pre-configured instances: `weather_cache` (30min), `currency_cache` (1hr), `amadeus_cache` (5min), `session_cache` (24hr)
- [x] `get_cache_status()` exposed in `/api/health`
- [x] JSON serialization, namespace isolation, TTL per-key overrides
- **Files:** `backend/services/cache_service.py`, `backend/routes/health.py`

### 9. Background Task Queue `[x]`
Thread-pool async task runner with SocketIO progress events.
- [x] `task_queue.py` — `TaskQueue` class: ThreadPoolExecutor (4 workers), TTLCache task store (1hr), progress tracking
- [x] `task_queue.submit()` returns task_id, emits `task_progress` socket events (pending→running→completed/failed)
- [x] `POST /api/trips/plan-async` — async trip planning, returns 202 with task_id
- [x] `GET /api/tasks/<id>` — task status; `GET /api/tasks/<id>/result` — task result; `GET /api/tasks` — list user tasks
- **Files:** `backend/services/task_queue.py`, `backend/routes/trips.py`

### 10. Nearby Venue Search UI `[x]`
Wire existing backend venue search into Meetings page.
- [x] "Find Venues" button in Meetings toolbar opens venue search modal
- [x] Location input + search → shows hotels with conference, coworking spaces, cafes with ratings
- [x] Uses existing `getNearbyVenues` API + `suggest_nearby_venues` backend
- **Files:** `frontend/src/pages/Meetings.jsx`
