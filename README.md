# TravelSync Pro — v3.0
### AI-Powered Corporate Travel Management System

A full-stack corporate travel management platform built for Indian enterprises. Handles the complete travel lifecycle — trip planning, approval workflows, expense verification, client meetings, analytics, and multi-channel notifications — with an AI voice assistant, WhatsApp bot, and Zoho Cliq bot.

**Production URL:** https://travelsync-pro-127731572888.asia-south1.run.app

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Who Uses It](#who-uses-it)
3. [Feature Overview](#feature-overview)
4. [Architecture](#architecture)
5. [AI Agents](#ai-agents)
6. [Notification Channels](#notification-channels)
7. [OTIS Voice Assistant](#otis-voice-assistant)
8. [WhatsApp Bot](#whatsapp-bot)
9. [Zoho Cliq Bot](#zoho-cliq-bot)
10. [Tech Stack](#tech-stack)
11. [Project Structure](#project-structure)
12. [Local Setup](#local-setup)
13. [Environment Variables](#environment-variables)
14. [API Reference](#api-reference)
15. [GCP Deployment](#gcp-deployment)
16. [Troubleshooting](#troubleshooting)

---

## Problem Statement

Corporate travel in mid-to-large Indian enterprises is fragmented across email, WhatsApp, spreadsheets, and manual approvals. There is no single system connecting trip planning → approvals → bookings → expenses → compliance.

TravelSync Pro solves this end-to-end:

```
Employee plans trip  →  AI policy check  →  Manager approves
        ↓                                          ↓
  Expense submitted  ←   Trip completed   ←  Real-time data
        ↓
  3-stage OCR verification (Invoice + Payment proof + Amount match)
        ↓
  Finance approves  →  Analytics & compliance report
```

---

## Who Uses It

| Role | How They Use It |
|---|---|
| Employee / Traveler | Plan trips, submit requests, log expenses, get AI travel guidance via web, WhatsApp, or voice |
| Manager | Approve or reject requests with policy context and full audit trail |
| Finance / Admin | Review verified expenses, track departmental spend, generate compliance reports |
| HR / Operations | Monitor travel patterns, enforce travel policies, handle SOS alerts |

---

## Feature Overview

### AI Trip Planner
- Gemini 2.0 Flash generates a full trip plan in seconds — flights, hotels, weather, meetings, packing checklist, and local guide
- Amadeus Flights v2 for real flight data; Amadeus Hotels v3 for accommodation
- PG and long-stay options (Stanza Living, NestAway, OYO Life, CoHo, Colive) auto-suggested when stay is 5+ days
- Multi-traveler team sync — coordinates arrivals from different cities
- Travel modes: flights, trains (IRCTC/ixigo), buses (RedBus), cabs (Ola)

### Accommodation Search
- Hotel search via Amadeus Hotels v3
- Rural mode: filters hotels within 2km of client address using Google Maps Distance Matrix
- Budget tiers: Budget / Moderate / Premium
- Veg restaurant filter, proximity to metro/railway/airport

### Client Meetings Module
- Full meeting management — no external CRM needed
- Import from any source: manual, email, WhatsApp note, phone call, calendar, LinkedIn
- AI schedule optimization via Gemini
- Nearby venue suggestions via Google Maps Places

### 3-Stage Expense Verification
- Stage 1: Upload invoice → Google Vision OCR extracts amount, vendor, GST number, date
- Stage 2: Upload payment proof (bank statement or UPI receipt)
- Stage 3: System cross-checks all three amounts within ₹1 tolerance — mismatches flagged automatically
- Expense categories: Flight, Hotel, Food, Transport, Visa, Communication, Other
- Source tracking: web / WhatsApp / Cliq

### Approval Workflow
- Employees submit travel requests with destination, dates, budget, purpose
- Policy agent checks against configured rules (flight class, hotel cap, advance booking days)
- Auto-approval below configured threshold
- Manager receives pending approvals with full policy compliance report
- Audit trail: every action timestamped with comments

### Analytics Dashboard
- Monthly spend by category
- Department-wise budget utilization
- Top destinations by frequency and cost
- Policy compliance scorecard
- Pending approvals count and aging
- All data from live DB — nothing hardcoded

### AI Chat Assistant
- Powered by Gemini 2.0 Flash (Claude fallback if configured)
- Context-aware: knows your trips, expenses, meetings, and policies
- Conversation history persisted in DB

### Weather and Currency
- Live weather widget on dashboard (OpenWeatherMap)
- Travel weather forecast for destination dates
- Real-time currency conversion (Open Exchange Rates, USD pivot)

### Emergency SOS
- Floating SOS button on every screen
- Emergency contacts: Police (100), Ambulance (108), Fire (101), Women Helpline (1091)
- Location-aware emergency message dispatch

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   Experience Surfaces                             │
│                                                                   │
│  React Web App    WhatsApp Bot    Zoho Cliq Bot    OTIS Voice    │
│  (port 5173)      (Twilio)        (Deluge → API)   (WebSocket)   │
└──────────────────────────┬───────────────────────────────────────┘
                           │  REST + WebSocket (/api/*)
┌──────────────────────────▼───────────────────────────────────────┐
│                     Flask API  (port 3399)                        │
│                                                                   │
│  routes/auth          routes/trips         routes/expenses        │
│  routes/meetings      routes/approvals     routes/analytics       │
│  routes/weather       routes/currency      routes/chat            │
│  routes/whatsapp      routes/cliq_bot      routes/otis            │
│  routes/notifications routes/health                               │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│               A2A Orchestrator (ThreadPoolExecutor)               │
│         All agents run in parallel — failures are isolated        │
│                                                                   │
│  hotel_agent       travel_mode_agent    weather_agent             │
│  meeting_agent     guide_agent          checklist_agent           │
│  expense_agent     analytics_agent      chat_agent                │
│  policy_agent      request_agent        otis_agent                │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                      External Services                            │
│                                                                   │
│  Google Gemini 2.0 Flash   — AI planning, chat, OCR analysis     │
│  Amadeus Self-Service       — Flights v2, Hotels v3               │
│  Google Maps Platform       — Geocoding, Distance Matrix, Places  │
│  OpenWeatherMap             — Current weather + forecast          │
│  Open Exchange Rates        — Currency conversion                 │
│  Google Cloud Vision        — Receipt OCR                         │
│  Deepgram                   — Speech-to-text (OTIS)               │
│  Google TTS / ElevenLabs    — Text-to-speech (OTIS)               │
│  Twilio                     — WhatsApp bot                        │
│  Zoho Cliq API              — Cliq bot outgoing messages          │
│  SMTP                       — Email notifications                 │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                         Data Layer                                │
│                                                                   │
│  SQLite (development)  /  Cloud SQL PostgreSQL (production)       │
│  Redis (optional)      — session store, bot state, rate limits    │
│  GCS Bucket            — uploaded receipts and invoices           │
└──────────────────────────────────────────────────────────────────┘
```

### A2A Design Pattern

The orchestrator uses `ThreadPoolExecutor` to run all agents in parallel. A full trip plan — flights, hotels, weather, meetings, guide, packing checklist — is generated in a single parallel pass, typically in under 10 seconds.

Each agent:
- Has its own service dependency injected via a service class
- Returns a structured dict with `source: "live"` or `source: "fallback"`
- Never blocks another agent — failures return realistic demo data

### Service Fallback Pattern

Every external service checks `self.configured = bool(api_key)` at init. When unconfigured, it returns realistic demo data with `source: "fallback"` so the app is fully usable without any API keys in demo mode.

---

## AI Agents

| Agent | Responsibility |
|---|---|
| `orchestrator.py` | Parallel A2A coordinator — runs all agents, assembles results, never crashes on agent failure |
| `hotel_agent.py` | Amadeus Hotels v3 search, 2km radius rural filter, PG/long-stay suggestions |
| `travel_mode_agent.py` | Amadeus Flights v2, train/bus/cab links, cost comparison |
| `weather_agent.py` | OpenWeatherMap forecasts for travel dates and destination |
| `meeting_agent.py` | Client meeting CRUD, AI schedule optimization via Gemini, venue search |
| `guide_agent.py` | Google Maps Places + Gemini local guide (food, transport, cultural tips) |
| `checklist_agent.py` | AI packing checklists based on weather, duration, and trip purpose |
| `expense_agent.py` | 3-stage OCR expense verification (Google Vision), anomaly detection |
| `analytics_agent.py` | Live DB analytics — schema-tolerant queries using PRAGMA table_info |
| `chat_agent.py` | Gemini 2.0 Flash conversational assistant with full user context |
| `policy_agent.py` | Travel policy compliance checker — validates flight class, hotel cap, advance booking |
| `request_agent.py` | Travel request workflow — status transitions, approval routing |
| `otis_agent.py` | OTIS voice command processor — STT → intent → action → TTS response pipeline |
| `query_engine.py` | Natural language query handler for WhatsApp and Cliq bots — date-aware expense/trip/approval lookups |

---

## Notification Channels

TravelSync pushes notifications across five channels from a single notification service:

| Channel | Trigger | Config Required |
|---|---|---|
| In-app (Socket.IO) | Every event | None — always active |
| Email (SMTP) | Approvals, rejections, SOS alerts | `SMTP_*` vars |
| WhatsApp (Twilio) | Trip updates, approvals, expense confirmations | `TWILIO_*` vars |
| Zoho Cliq | All notification types with rich card formatting | `ZOHO_CLIQ_*` vars |
| Slack | Optional channel posting | `SLACK_WEBHOOK_URL` |

The notification service (`services/notification_service.py`) fans out to all configured channels simultaneously. Unconfigured channels are silently skipped — no errors thrown.

---

## OTIS Voice Assistant

OTIS (Operational Travel Intelligence System) is an in-browser voice agent embedded in the web app.

### What OTIS Can Do
- Answer questions about trips, expenses, approvals, meetings, and travel policies
- Execute commands: "Show my pending approvals", "What's my expense total this month"
- Real-time weather and currency queries
- Full conversation history stored per session
- Word-by-word animated response display as it speaks

### Voice Pipeline
```
User speaks  →  Deepgram STT (or Google STT fallback)
           →  Intent detection + DB context assembly
           →  Gemini 2.0 Flash generates response
           →  Google TTS (Indian English, Neural2-C voice)  →  Audio plays
           →  Word-by-word text animation in UI simultaneously
```

### UI Layout
Full-screen three-panel interface:
- Left panel: Conversation history with timestamps
- Center panel: Live response display with word-by-word animation + text input
- Right panel: Real-time waveform visualizer + mic control

### OTIS Configuration

```env
OTIS_ENABLED=true
OTIS_ADMIN_ONLY=false
OTIS_REQUIRE_CONFIRMATION=false
OTIS_WAKE_WORD=Hey Otis

# STT Provider
OTIS_STT_PROVIDER=google        # google | deepgram
DEEPGRAM_API_KEY=               # for deepgram STT

# TTS Provider
OTIS_TTS_PROVIDER=google        # google | elevenlabs
GOOGLE_TTS_VOICE=en-IN-Neural2-C   # Indian English male (recommended)

# ElevenLabs (alternative TTS)
ELEVENLABS_API_KEY=
OTIS_VOICE_ID=                  # ElevenLabs voice ID
OTIS_VOICE_MODEL_ID=eleven_multilingual_v2
OTIS_VOICE_STABILITY=0.58
OTIS_VOICE_SIMILARITY=0.82
```

---

## WhatsApp Bot

The WhatsApp bot gives employees full TravelSync access from any WhatsApp conversation.

### Setup
1. Sign up at twilio.com and activate the WhatsApp sandbox
2. Set the webhook URL in Twilio Console to: `https://your-domain/api/whatsapp`
3. Configure `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` in `.env`

### Commands

| Command | Response |
|---|---|
| `hi` / `hello` | Welcome message + menu |
| `1` or `my trips` | Your recent travel requests |
| `2` or `trip status` | Last 3 trips with status |
| `3` or `approvals` | Pending approvals (managers see full queue) |
| `4` or `expenses` | Expense summary: total, pending, approved |
| `5` or `meetings` | Upcoming client meetings |
| `weather Mumbai` | Live weather for any city |
| `expense 500 Uber cab` | Quick expense entry |
| `add expense` | Start guided step-by-step expense flow |
| `approve TR-2026-XXXX` | Approve a travel request (managers) |
| `reject TR-2026-XXXX` | Reject with reason (managers) |
| `plan trip` | Trip planning guidance + web app link |
| `help` | Full command list |

### Guided Expense Flow (WhatsApp)
```
User: add expense
Bot:  Enter the amount in Rupees:
User: 850
Bot:  Amount set: Rs. 850. Now describe the expense:
User: Lunch with client at Taj
Bot:  Category auto-detected: Food & Meals. Confirm? (yes/no)
User: yes
Bot:  Expense Saved — Rs. 850, Food & Meals
```

### Receipt Scanning
Send a photo of any receipt directly in WhatsApp. The bot extracts the amount and prompts for category. Full OCR via Google Vision — no manual typing needed.

---

## Zoho Cliq Bot

The Cliq bot brings TravelSync into your team's Zoho Cliq workspace.

### Setup
1. Create a bot in Zoho Cliq (Apps → Developer Tools → Bots)
2. Set the Message Handler to type **URL** pointing to: `https://your-domain/api/cliq/bot`
3. Add the Authorization header token in the handler
4. Configure env vars (see below)

**Message Handler Deluge code:**
```javascript
header = Map();
header.put("Content-Type", "application/json");
header.put("Authorization", "Bearer YOUR_CLIQ_WEBHOOK_TOKEN");

body = Map();
body.put("user_name", user.get("name"));
body.put("user_email", user.get("email"));
body.put("chat_id", chat.get("id"));
body.put("message", message);
body.put("file_url", "");
body.put("file_name", "");
body.put("file_type", "");

resp = invokeurl
[
    url :"https://travelsync-pro-127731572888.asia-south1.run.app/api/cliq/bot"
    type :POST
    parameters:body.toString()
    headers:header
    content-type:"application/json"
];

result = Map();
try {
    result.put("text", ifnull(resp.get("text"), "No response from TravelSync."));
    suggestions = resp.get("suggestions");
    if(suggestions != null) { result.put("suggestions", {"list": suggestions}); }
} catch (e) {
    result.put("text", "TravelSync server is offline. Please try again shortly.");
}
return result;
```

### Bot Configuration
- **API Endpoint:** `https://travelsync-pro-127731572888.asia-south1.run.app/api/cliq/bot`
- **Incoming Webhook:** `https://cliq.zoho.com/api/v2/bots/travelsyncpro/incoming`
- **Outgoing Message URL:** `https://cliq.zoho.com/api/v2/bots/travelsyncpro/message`
- **OAuth Scope:** `ZohoCliq.Channels.ALL,ZohoCliq.Bots.ALL`

### Commands

Same command set as WhatsApp — all features available including guided expense flow, trip planning, approvals, meetings, weather, and AI chat.

### Cliq Environment Variables

```env
ZOHO_CLIQ_API_ENDPOINT=https://cliq.zoho.com/api/v2/bots/travelsyncpro/message
ZOHO_CLIQ_CLIENT_ID=
ZOHO_CLIQ_CLIENT_SECRET=
ZOHO_CLIQ_REFRESH_TOKEN=
ZOHO_CLIQ_ACCESS_TOKEN=
CLIQ_WEBHOOK_TOKEN=         # shared secret — must match bot handler Authorization token
```

The service auto-detects the Zoho datacenter from the endpoint domain (`zoho.com` vs `zoho.in`) and refreshes the OAuth token automatically before expiry.

---

## Tech Stack

### Frontend
| Technology | Version | Purpose |
|---|---|---|
| React | 18.3 | UI framework |
| Vite | 5.4 | Build tool and dev proxy |
| Tailwind CSS | 3.4 | Utility-first styling |
| React Router | v6 | Client-side routing |
| Zustand | 5.0 | State management |
| Axios | 1.7 | HTTP client with interceptors |
| Socket.IO Client | 4.8 | Real-time WebSocket events |
| Lucide React | 0.462 | Icon library |

### Backend
| Technology | Version | Purpose |
|---|---|---|
| Flask | 3.x | REST API |
| Flask-SocketIO | 5.x | WebSocket (real-time notifications) |
| Flask-CORS | 4.x | Cross-origin support |
| Flask-Limiter | 3.x | Rate limiting |
| eventlet | — | Async WSGI server |
| psycopg2 | — | PostgreSQL driver |
| SQLite / Cloud SQL | — | Data persistence |

### AI and External APIs
| Service | Used For |
|---|---|
| Google Gemini 2.0 Flash | Trip planning, chat assistant, schedule optimization, checklist generation |
| Amadeus Self-Service | Flights v2 (real fares), Hotels v3 (live availability) |
| Google Maps Platform | Geocoding, Distance Matrix, Places API |
| OpenWeatherMap | Current weather widget, travel forecasts |
| Open Exchange Rates | Currency conversion (USD pivot, 160+ currencies) |
| Google Cloud Vision | Receipt OCR — extracts amount, vendor, GST, date |
| Deepgram | Speech-to-text for OTIS voice assistant |
| Google Cloud TTS | Indian English voice synthesis (OTIS primary) |
| ElevenLabs | Premium voice synthesis (OTIS secondary) |
| Twilio | WhatsApp bot webhook and messaging |
| Zoho Cliq API | Cliq bot messaging with OAuth2 token refresh |

### Deployment
| Platform | Purpose |
|---|---|
| GCP Cloud Run (`asia-south1`) | Serverless container hosting — auto-scales 1 to 10 instances |
| GCP Cloud Build | CI/CD — runs tests → lint → Docker build → deploy |
| GCP Secret Manager | All API keys and tokens in production |
| GCP Artifact Registry | Docker image storage |
| Cloud SQL (PostgreSQL) | Production database |
| GCS Bucket | Uploaded receipts and invoice storage |

---

## Project Structure

```
Travel_Sync_12thMarch/
├── run.py                           ← Start server from project root
├── requirements.txt
├── .env.example                     ← Template for all env vars
├── Dockerfile                       ← Container build (React build inside)
├── cloudbuild.yaml                  ← GCP CI/CD pipeline
│
├── backend/
│   ├── .env                         ← API keys — never commit
│   ├── app.py                       ← Flask factory + blueprint registration
│   ├── auth.py                      ← JWT auth helpers + @require_auth decorator
│   ├── config.py                    ← Centralized env config + Secret Manager fetch
│   ├── database.py                  ← Schema init, auto-migrations, connection pool
│   ├── otis_security.py             ← OTIS session auth and rate limiting
│   │
│   ├── agents/
│   │   ├── orchestrator.py          ← ThreadPoolExecutor parallel A2A runner
│   │   ├── hotel_agent.py           ← Amadeus Hotels v3 + PG suggestions
│   │   ├── travel_mode_agent.py     ← Amadeus Flights v2 + trains/buses/cabs
│   │   ├── weather_agent.py         ← OpenWeatherMap forecasts
│   │   ├── meeting_agent.py         ← Meeting CRUD + AI schedule optimization
│   │   ├── guide_agent.py           ← Google Maps Places + Gemini local guide
│   │   ├── checklist_agent.py       ← AI packing checklists
│   │   ├── expense_agent.py         ← 3-stage OCR expense verification
│   │   ├── analytics_agent.py       ← Live DB analytics (schema-tolerant)
│   │   ├── chat_agent.py            ← Gemini conversational assistant
│   │   ├── policy_agent.py          ← Travel policy compliance validator
│   │   ├── request_agent.py         ← Approval workflow engine
│   │   ├── otis_agent.py            ← OTIS voice command processor
│   │   ├── otis_functions.py        ← OTIS intent handlers (trip/expense/meeting lookups)
│   │   └── query_engine.py          ← Natural language DB query engine (for bots)
│   │
│   ├── routes/
│   │   ├── auth.py                  ← /api/auth/*
│   │   ├── trips.py                 ← /api/plan-trip
│   │   ├── expenses.py              ← /api/expenses + /api/expense/upload-and-extract
│   │   ├── meetings.py              ← /api/meetings CRUD
│   │   ├── requests.py              ← /api/requests CRUD
│   │   ├── approvals.py             ← /api/approvals
│   │   ├── analytics.py             ← /api/analytics/*
│   │   ├── weather.py               ← /api/weather
│   │   ├── currency.py              ← /api/currency/*
│   │   ├── chat.py                  ← /api/chat
│   │   ├── otis.py                  ← /api/otis/* (voice sessions, STT, TTS)
│   │   ├── whatsapp.py              ← /api/whatsapp (Twilio webhook + bot logic)
│   │   ├── cliq_bot.py              ← /api/cliq/bot (Cliq webhook + bot logic)
│   │   ├── notifications.py         ← /api/notifications
│   │   └── health.py                ← /api/health
│   │
│   └── services/
│       ├── gemini_service.py        ← Gemini 2.0 Flash client
│       ├── amadeus_service.py       ← Flights + Hotels + PG search
│       ├── maps_service.py          ← Google Maps (Geocoding, Distance, Places)
│       ├── weather_service.py       ← OpenWeatherMap
│       ├── currency_service.py      ← Open Exchange Rates
│       ├── vision_service.py        ← Google Vision OCR
│       ├── deepgram_service.py      ← Deepgram STT
│       ├── elevenlabs_voice_service.py ← ElevenLabs TTS
│       ├── wake_word_service.py     ← Wake word detection (Porcupine)
│       ├── email_service.py         ← SMTP email (verification, notifications)
│       ├── cliq_service.py          ← Zoho Cliq OAuth2 client + token refresh
│       ├── notification_service.py  ← Fan-out: in-app, email, WhatsApp, Cliq, Slack
│       ├── http_client.py           ← Shared requests session with retries
│       ├── input_sanitizer.py       ← AI prompt injection guard
│       └── state_store.py           ← TTL-based in-memory state (bot conversations)
│
└── frontend/
    ├── vite.config.js               ← Dev proxy: /api/* → localhost:3399
    ├── tailwind.config.js
    └── src/
        ├── App.jsx                  ← React Router v6 + auth guard
        ├── api/                     ← Axios modules (one per domain)
        │   ├── client.js            ← Axios instance with 401 redirect
        │   ├── auth.js
        │   ├── trips.js
        │   ├── expenses.js
        │   ├── meetings.js
        │   ├── analytics.js
        │   ├── chat.js
        │   └── otis.js              ← OTIS voice session API
        ├── store/
        │   └── useStore.js          ← Zustand: auth, sidebar, notifications
        ├── components/
        │   ├── layout/
        │   │   ├── Layout.jsx       ← Sidebar + Topbar wrapper
        │   │   ├── Sidebar.jsx      ← Navigation with all app sections
        │   │   └── Topbar.jsx       ← Health dot, notifications bell
        │   └── voice/
        │       ├── OtisLauncher.jsx      ← Floating mic button (bottom-right)
        │       ├── OtisVoiceWidget.jsx   ← Full-screen 3-panel voice agent UI
        │       └── WaveformVisualizer.jsx ← Real-time audio waveform animation
        └── pages/
            ├── Dashboard.jsx        ← KPIs, weather widget, recent activity
            ├── TripPlanner.jsx      ← AI trip planning + results
            ├── Accommodation.jsx    ← Hotel + PG search
            ├── Expenses.jsx         ← 3-stage OCR expense submission
            ├── Meetings.jsx         ← Client meeting management
            ├── Requests.jsx         ← Submit travel requests
            ├── Approvals.jsx        ← Manager approval queue
            ├── Analytics.jsx        ← Spend charts, compliance scorecard
            ├── Chat.jsx             ← Gemini AI chat assistant
            └── OtisDashboard.jsx    ← OTIS voice session history and settings
```

---

## Local Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- npm 9+

### Step 1 — Python environment
```bash
cd Travel_Sync_12thMarch
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2 — Environment variables
```bash
cp .env.example backend/.env
# Open backend/.env and add at minimum: GEMINI_API_KEY
```

### Step 3 — Frontend
```bash
cd frontend && npm install && cd ..
```

### Step 4 — Run (development)
```bash
# Terminal 1 — Flask backend
source venv/bin/activate && python run.py

# Terminal 2 — React frontend with hot reload
cd frontend && npm run dev
```

Open **http://localhost:5173** — Vite automatically proxies all `/api/*` calls to Flask on port 3399.

### Production build (single server)
```bash
cd frontend && npm run build && cd ..
source venv/bin/activate && python run.py
# Open http://localhost:3399
```

### Testing with WhatsApp or Cliq locally
```bash
# Expose local port 3399 to the internet via ngrok
ngrok http 3399
# Copy the https URL and update the webhook in Twilio / Cliq bot Message Handler
```

---

## Environment Variables

All variables go in `backend/.env`. Copy from `.env.example`.

```env
# ── Core ──────────────────────────────────────────────────────
FLASK_SECRET_KEY=change-this-in-production
PORT=3399
DEBUG=False

# ── AI (required for planning, chat, checklists) ──────────────
GEMINI_API_KEY=                  # aistudio.google.com (free)

# ── Flights and Hotels ────────────────────────────────────────
AMADEUS_CLIENT_ID=               # developers.amadeus.com
AMADEUS_CLIENT_SECRET=
AMADEUS_ENV=test                 # test | production

# ── Maps ──────────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY=             # Enable: Maps, Distance Matrix, Geocoding, Places

# ── Weather ───────────────────────────────────────────────────
OPENWEATHER_API_KEY=             # openweathermap.org/api

# ── Currency ──────────────────────────────────────────────────
OPEN_EXCHANGE_APP_ID=            # openexchangerates.org

# ── Receipt OCR ───────────────────────────────────────────────
GOOGLE_VISION_API_KEY=           # Enable: Cloud Vision API (can reuse Maps key)

# ── Database ──────────────────────────────────────────────────
DATABASE_URL=                    # Leave blank for SQLite in dev
                                 # postgresql://user:pass@host/db for Cloud SQL

# ── CORS ──────────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:5173,http://localhost:3399

# ── Zoho CRM ──────────────────────────────────────────────────
ZOHO_CLIENT_ID=
ZOHO_CLIENT_SECRET=
ZOHO_REFRESH_TOKEN=
ZOHO_ACCESS_TOKEN=
ZOHO_ORG_ID=

# ── WhatsApp (Twilio) ─────────────────────────────────────────
TWILIO_ACCOUNT_SID=              # twilio.com
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=+14155238886

# ── Zoho Cliq Bot ─────────────────────────────────────────────
ZOHO_CLIQ_API_ENDPOINT=https://cliq.zoho.com/api/v2/bots/travelsyncpro/message
ZOHO_CLIQ_CLIENT_ID=
ZOHO_CLIQ_CLIENT_SECRET=
ZOHO_CLIQ_REFRESH_TOKEN=
ZOHO_CLIQ_ACCESS_TOKEN=
CLIQ_WEBHOOK_TOKEN=              # shared secret — must match bot handler token

# ── Email (SMTP) ──────────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=TravelSync Pro

# ── OTIS Voice Assistant ──────────────────────────────────────
OTIS_ENABLED=true
OTIS_ADMIN_ONLY=false
OTIS_REQUIRE_CONFIRMATION=false
OTIS_WAKE_WORD=Hey Otis
OTIS_TTS_PROVIDER=google         # google | elevenlabs
OTIS_STT_PROVIDER=google         # google | deepgram
GOOGLE_TTS_VOICE=en-IN-Neural2-C # Indian English male voice
DEEPGRAM_API_KEY=                # console.deepgram.com
ELEVENLABS_API_KEY=              # elevenlabs.io
OTIS_VOICE_ID=                   # ElevenLabs voice ID
OTIS_VOICE_MODEL_ID=eleven_multilingual_v2

# ── GCP (production only) ─────────────────────────────────────
GCP_PROJECT_ID=
GCP_REGION=asia-south1
GCS_BUCKET=
GOOGLE_APPLICATION_CREDENTIALS=
REDIS_URL=
```

---

## API Reference

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/logout` | Logout |
| POST | `/api/auth/register` | Register new account |
| GET | `/api/auth/me` | Current user info |

### Trip Planning
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/plan-trip` | Full AI trip plan — all agents in parallel |
| GET | `/api/requests` | List travel requests |
| POST | `/api/requests` | Submit new travel request |
| POST | `/api/requests/:id/submit` | Submit request for approval |

### Accommodation
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/accommodation/search` | Hotel search (Amadeus) |
| POST | `/api/accommodation/pg-options` | PG / long-stay search |

### Expenses
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/expenses` | List expenses |
| POST | `/api/expenses` | Submit expense |
| POST | `/api/expense/upload-and-extract` | Upload receipt + OCR extraction |

### Meetings
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/meetings` | List meetings |
| POST | `/api/meetings` | Create meeting |
| PUT | `/api/meetings/:id` | Update meeting |
| DELETE | `/api/meetings/:id` | Delete meeting |
| POST | `/api/meetings/suggest-schedule` | AI schedule optimization |

### Approvals
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/approvals` | Pending approvals queue |
| POST | `/api/approvals/:id/approve` | Approve request |
| POST | `/api/approvals/:id/reject` | Reject with reason |

### Analytics
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/analytics/dashboard` | KPI stats |
| GET | `/api/analytics/spend` | Spend breakdown by category |
| GET | `/api/analytics/compliance` | Policy compliance scorecard |

### OTIS Voice
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/otis/session` | Start a voice session |
| POST | `/api/otis/command` | Process voice command (text or audio) |
| POST | `/api/otis/tts` | Text-to-speech synthesis |
| GET | `/api/otis/history` | Voice session history |

### Bots
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/whatsapp` | Twilio WhatsApp webhook |
| POST | `/api/cliq/bot` | Zoho Cliq bot webhook |

### Utilities
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/weather` | Travel weather forecast |
| GET | `/api/weather/current?city=X` | Current weather |
| POST | `/api/currency/convert` | Currency conversion |
| POST | `/api/chat` | AI chat message |
| GET | `/api/chat/history` | Chat history |
| GET | `/api/health` | All service statuses |

---

## GCP Deployment

### CI/CD Pipeline (cloudbuild.yaml)

```
Push to main branch
  → Step 0a: Run pytest (gates deployment — fails here if tests break)
  → Step 0b: flake8 lint (advisory, never blocks)
  → Step 1:  Docker build (React build inside Dockerfile)
  → Step 2:  Push to Artifact Registry
  → Step 3:  Deploy to Cloud Run (asia-south1)
```

### Deploy command
```bash
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD) \
  --project=beta-ai-travel-agent
```

### Cloud Run configuration
- **Service:** `travelsync-pro`
- **Region:** `asia-south1`
- **CPU:** 2 vCPU
- **Memory:** 2 GiB
- **Min instances:** 1 (always warm)
- **Max instances:** 10
- **Concurrency:** 80
- **Timeout:** 300s

### Secret Manager

All API keys are stored in GCP Secret Manager and fetched at runtime via `config.py:_get_env_or_secret()`. No secrets are baked into the Docker image.

To add a new secret:
```bash
echo -n "your-secret-value" | gcloud secrets create SECRET_NAME \
  --data-file=- --replication-policy=automatic \
  --project=beta-ai-travel-agent

# Grant Cloud Run service account access
gcloud secrets add-iam-policy-binding SECRET_NAME \
  --member="serviceAccount:travelsync-runtime@beta-ai-travel-agent.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

To update an existing secret value:
```bash
echo -n "new-value" | gcloud secrets versions add SECRET_NAME --data-file=-
```

To force a new Cloud Run revision to pick up a new secret (no code change needed):
```bash
gcloud run services update travelsync-pro \
  --region=asia-south1 \
  --project=beta-ai-travel-agent \
  --update-secrets="SECRET_NAME=SECRET_NAME:latest"
```

### Secrets in production

| Secret Name | Purpose |
|---|---|
| `FLASK_SECRET_KEY` | Flask session signing |
| `JWT_SECRET_KEY` | JWT token signing |
| `GEMINI_API_KEY` | Gemini AI |
| `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` | Flights and Hotels |
| `GOOGLE_MAPS_API_KEY` | Maps Platform |
| `OPENWEATHER_API_KEY` | Weather |
| `OPEN_EXCHANGE_APP_ID` | Currency |
| `GOOGLE_VISION_API_KEY` | Receipt OCR |
| `DATABASE_URL` | Cloud SQL PostgreSQL |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | WhatsApp bot |
| `ZOHO_CLIQ_CLIENT_ID` / `ZOHO_CLIQ_CLIENT_SECRET` / `ZOHO_CLIQ_REFRESH_TOKEN` | Cliq OAuth |
| `CLIQ_WEBHOOK_TOKEN` | Cliq bot webhook verification |
| `SMTP_USER` / `SMTP_PASSWORD` | Email notifications |
| `DEEPGRAM_API_KEY` | OTIS STT |
| `ELEVENLABS_API_KEY` | OTIS TTS |

---

## Troubleshooting

### Flask won't start
```bash
pip install -r requirements.txt --upgrade
```

### React proxy not working
Make sure Flask is running on port 3399 before starting `npm run dev`. Vite's proxy in `vite.config.js` requires the backend to be up.

### Cliq bot returning 403
1. Check `CLIQ_WEBHOOK_TOKEN` is set in `backend/.env` (local) or Secret Manager (production)
2. Verify the Cliq bot Message Handler Authorization header matches the token exactly
3. In production, run: `gcloud run services update travelsync-pro --region=asia-south1 --update-secrets="CLIQ_WEBHOOK_TOKEN=CLIQ_WEBHOOK_TOKEN:latest"`

### WhatsApp not receiving messages
1. Check Twilio Console → WhatsApp Sandbox → Webhook URL is set to `https://your-domain/api/whatsapp`
2. Verify `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` are correct
3. Check logs: `gcloud logging read 'resource.labels.service_name="travelsync-pro"' --limit=20`

### OTIS voice not working
1. Ensure `OTIS_ENABLED=true` in env
2. For Google TTS: enable Cloud Text-to-Speech API in GCP Console (same project as other Google APIs)
3. Browser must allow microphone access
4. Check `/api/health` response — confirms which OTIS services are live

### Gemini quota exceeded
The app falls back to demo data automatically. Check quota at https://aistudio.google.com.

### SQLite database locked
Stop all running Flask instances, then restart.

### Port conflict
```bash
PORT=8080 python run.py
```

### Cloud Build failing
```bash
# Check build logs
gcloud builds list --project=beta-ai-travel-agent --limit=5
gcloud builds log BUILD_ID --project=beta-ai-travel-agent
```

---

*Built for Indian enterprises. Powered by Google Gemini AI, Amadeus, and Google Cloud Platform.*
