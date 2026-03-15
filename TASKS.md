
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
*Next: Build Feature #1 — AI Chat Grounded Responses*
