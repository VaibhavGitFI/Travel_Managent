
# TravelSync Pro v3.0
### AI-Powered Corporate Travel Management System

A full-stack corporate travel management platform built with **React + Flask**, powered by **Google Gemini AI**, real-time flight and hotel data from **Amadeus**, live weather, currency conversion, and 3-stage expense verification with **Google Vision OCR**.

Designed for Indian enterprises managing end-to-end business travel — from trip planning and approvals to expense reimbursement and compliance reporting.

---

## Table of Contents

1. [Use Case & Problem Statement](#use-case--problem-statement)
2. [Who Is This For](#who-is-this-for)
3. [Key Features](#key-features)
4. [Architecture Overview](#architecture-overview)
5. [Tech Stack](#tech-stack)
6. [Project Structure](#project-structure)
7. [Setup & Installation](#setup--installation)
8. [Environment Variables](#environment-variables)
9. [Running the Application](#running-the-application)
10. [API Reference](#api-reference)
11. [Demo Users](#demo-users)
12. [Deployment (GCP)](#deployment-gcp)
13. [Troubleshooting](#troubleshooting)

---

## Use Case & Problem Statement

### The Problem

Corporate travel in mid-to-large Indian enterprises is painfully fragmented:

- Employees book travel on personal accounts and claim reimbursement manually
- Finance teams receive mismatched invoices, screenshots, and UPI receipts with no verification
- Managers approve requests over WhatsApp or email with no audit trail
- There is no single system connecting trip planning → approvals → bookings → expenses → compliance
- Travel policies exist on paper but are rarely enforced at the point of booking
- Multi-city team trips require manual coordination across departments
- International travel involves currency confusion, visa requirements, and weather uncertainty

### What TravelSync Pro Solves

TravelSync Pro is a **single unified platform** that handles the entire corporate travel lifecycle:

```
Employee plans trip  →  Manager approves  →  Flights & hotels booked
       ↓                                              ↓
Expense submitted    ←  Trip completed    ←  Real-time travel data
       ↓
3-stage OCR verification (Invoice + Payment proof + Amount match)
       ↓
Finance approves  →  Analytics & compliance report generated
```

### Real-World Scenarios This Covers

**Scenario 1 — Sales Executive, Mumbai to Bangalore**
Priya needs to visit a client in Whitefield, Bangalore for 3 days. She opens TravelSync Pro, enters the client's address, and the AI instantly finds flights, hotels within 2km of the client site, a meeting schedule, packing checklist, and local restaurant guide — all in one screen.

**Scenario 2 — Multi-City Team Trip**
A 4-person team is traveling from Mumbai, Delhi, Pune, and Hyderabad to Chennai for a conference. The Team Sync feature automatically calculates the best flight for each person so they all land within 30 minutes of each other and can share a cab from the airport.

**Scenario 3 — Long-Duration Project Stay**
An engineer is deployed on-site for 3 weeks. TravelSync automatically switches to PG/serviced apartment recommendations (Stanza Living, NestAway, OYO Life) instead of hotels, which are more cost-effective for extended stays.

**Scenario 4 — Expense Reimbursement with Fraud Prevention**
After the trip, the employee submits expenses. The system requires:
- Upload of the original invoice (Google Vision OCR reads the amount)
- Upload of payment proof (bank statement or UPI screenshot)
- Manual amount entry
All three must match within ₹1. Mismatches are flagged automatically — no manual auditing needed.

**Scenario 5 — Finance Manager Reviews Compliance**
The finance manager opens the Analytics tab and sees departmental spend by category, monthly trends, policy compliance rates, top travelers by cost, and budget utilization — all from real DB data, no manual reporting.

---

## Who Is This For

| Role | How They Use It |
|---|---|
| **Employee / Traveler** | Plan trips, submit requests, log expenses, get AI travel guidance |
| **Manager** | Approve or reject travel requests with audit trail and policy check |
| **Finance / Admin** | Review verified expenses, track spend, generate compliance reports |
| **HR / Operations** | Monitor travel patterns, enforce travel policies, handle SOS alerts |

---

## Key Features

### AI Trip Planner
- Gemini 2.0 Flash generates a complete trip plan in seconds
- Covers flights, trains, buses, and cab options via Amadeus API
- Hotel recommendations with proximity to client site (2km radius for rural/outstation trips)
- Automatic PG/long-stay suggestions when duration is 5+ days
- Weather forecast for travel dates via OpenWeatherMap
- City-specific local guide: food, transport, cultural tips
- AI-powered packing checklist based on weather and trip purpose
- Multi-traveler team sync — coordinates arrivals from different cities

### Travel Modes Supported
- Flights — real data via Amadeus Flights v2 API
- Trains — IRCTC, ixigo, ConfirmTkt links
- Buses — RedBus integration
- Cabs — Ola Outstation, Zoom Car for rural sites
- All modes show cost comparison side by side

### Accommodation Search
- Hotel search via Amadeus Hotels v3 API
- Rural mode: filters within 2km of client address using Google Maps Distance Matrix
- Budget tiers: Budget / Moderate / Premium
- PG / Long-Stay mode (Stanza Living, NestAway, OYO Life, CoHo, Colive)
- Veg restaurant filter
- Proximity to railway station, airport, metro shown on each result

### Client Meetings Module
- Full meeting management — no CRM dependency
- Import meetings from any source: manual entry, email, WhatsApp forward, phone note, calendar
- AI-powered schedule optimization via Gemini
- Nearby venue suggestions via Google Maps Places
- Meeting source tracking (manual / email / whatsapp / phone / calendar / linkedin)

### 3-Stage Expense Verification
- **Stage 1**: Upload invoice → Google Vision OCR extracts amount, date, vendor, GST number
- **Stage 2**: Upload payment proof (bank statement or UPI receipt)
- **Stage 3**: System checks all three amounts match within ₹1 tolerance
- Discrepancies flagged automatically — submitted to Finance only on full match
- Expense categories: Flight, Train, Bus, Cab, Hotel, Meals, Client Entertainment, etc.

### Approval Workflow
- Employees submit travel requests with destination, dates, budget, purpose
- Gemini checks request against travel policy (flight class, hotel budget cap, advance booking days)
- Auto-approval for requests under the configured threshold
- Manager receives pending approvals with full policy compliance report
- Full audit trail with timestamps and comments

### Real-Time Analytics
- Monthly spend by category (bar chart)
- Department-wise budget utilization
- Top destinations by frequency and cost
- Policy compliance scorecard with violation breakdown
- Pending approvals count and aging
- All data from live SQLite (dev) or Cloud SQL (prod) — nothing hardcoded

### AI Chat Assistant
- Powered by Gemini 2.0 Flash
- Context-aware travel assistant (knows your current trip details)
- Answers questions about visa, weather, local transport, restaurants
- Emergency guidance: medical first aid, SOS contacts, hospital locator
- Full conversation history persisted in DB

### Weather & Currency
- Live weather widget on dashboard (OpenWeatherMap)
- Travel weather forecast for destination and dates
- Real-time currency conversion (Open Exchange Rates, USD pivot)
- Destination currency info and travel tips

### Emergency Features
- Floating SOS button available on every screen
- Emergency contacts: Police (100), Ambulance (108), Fire (101), Women Helpline (1091)
- Location-aware emergency message dispatch
- AI medical guidance for symptom description

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     React SPA (Port 5173)                    │
│  Vite + Tailwind + React Router + Zustand + Axios           │
└───────────────────────┬─────────────────────────────────────┘
                        │  REST API + WebSocket
┌───────────────────────▼─────────────────────────────────────┐
│                  Flask API Server (Port 3399)                 │
│  Flask Blueprints │ Flask-SocketIO │ Flask-CORS              │
│                                                               │
│  routes/auth      routes/trips     routes/expenses           │
│  routes/meetings  routes/approvals routes/analytics          │
│  routes/weather   routes/currency  routes/chat               │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│              A2A Orchestrator (ThreadPoolExecutor)            │
│  Runs all agents in parallel for maximum response speed      │
│                                                               │
│  orchestrator.py                                              │
│   ├── hotel_agent.py        ← Amadeus Hotels v3              │
│   ├── travel_mode_agent.py  ← Amadeus Flights v2             │
│   ├── weather_agent.py      ← OpenWeatherMap                 │
│   ├── meeting_agent.py      ← Client meetings CRUD           │
│   ├── guide_agent.py        ← Google Maps + Gemini           │
│   ├── checklist_agent.py    ← Gemini packing lists           │
│   ├── expense_agent.py      ← Vision OCR verification        │
│   ├── analytics_agent.py    ← Real DB analytics              │
│   ├── chat_agent.py         ← Gemini conversation            │
│   ├── policy_agent.py       ← Travel policy compliance       │
│   └── request_agent.py      ← Approval workflow              │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                    External Services                          │
│                                                               │
│  Google Gemini 2.0 Flash    — AI planning, chat, OCR        │
│  Amadeus Self-Service API   — Flights + Hotels               │
│  Google Maps Platform       — Geocoding, Distance, Places    │
│  OpenWeatherMap             — Current weather + forecast     │
│  Open Exchange Rates        — Currency conversion            │
│  Google Cloud Vision        — Receipt OCR                    │
│  SQLite (dev) / Cloud SQL   — Data persistence              │
└─────────────────────────────────────────────────────────────┘
```

### Agent-to-Agent (A2A) Design

The orchestrator uses Python's `ThreadPoolExecutor` to run all 6 planning agents simultaneously. A full trip plan — flights, hotels, weather, meetings, guide, checklist — is generated in one parallel pass, typically under 10 seconds even with all APIs live.

Each agent is completely independent:
- Has its own service dependency (injected via service classes)
- Returns a structured dict with a `source` field: `"live"` or `"fallback"`
- Never blocks another agent — failures are isolated and return demo data

### Service Fallback Pattern

Every external service has an intelligent fallback so the app is always functional:

```python
# Example: if Amadeus is not configured
if not self.configured:
    return {
        "source": "fallback",
        "note": "Set AMADEUS_CLIENT_ID + AMADEUS_CLIENT_SECRET for live data",
        "flights": [...]  # Realistic demo data
    }
```

---

## Tech Stack

### Frontend
| Technology | Version | Purpose |
|---|---|---|
| React | 18.3 | UI framework |
| Vite | 5.4 | Build tool and dev server |
| Tailwind CSS | 3.4 | Utility-first styling |
| React Router | v6 | Client-side routing |
| Zustand | 5.0 | Lightweight state management |
| Axios | 1.7 | HTTP client with interceptors |
| Lucide React | 0.462 | Icon library |
| Socket.IO Client | 4.8 | Real-time WebSocket |
| React Hot Toast | 2.4 | Notifications |

### Backend
| Technology | Version | Purpose |
|---|---|---|
| Flask | 3.x | REST API framework |
| Flask-SocketIO | 5.x | WebSocket support |
| Flask-CORS | 4.x | Cross-origin requests |
| eventlet | latest | Async WSGI server |
| SQLite / Cloud SQL | — | Database |
| Werkzeug | — | Password hashing |

### AI & External APIs
| Service | API | Used For |
|---|---|---|
| Google Gemini 2.0 Flash | Generative AI | Trip planning, chat, schedules, checklists |
| Amadeus Self-Service | Flights v2, Hotels v3 | Real flight and hotel search |
| Google Maps Platform | Distance Matrix, Geocoding, Places | Proximity, venue suggestions |
| OpenWeatherMap | Current + Forecast | Travel weather |
| Open Exchange Rates | Latest + Historical | Currency conversion |
| Google Cloud Vision | OCR | Receipt and invoice extraction |

### Deployment
| Platform | Service | Purpose |
|---|---|---|
| Google Cloud Run | asia-south1 | Serverless container hosting |
| Google Cloud Build | cloudbuild.yaml | CI/CD pipeline |
| Google Secret Manager | — | API key management in prod |
| Cloud SQL (PostgreSQL) | — | Production database |

---

## Project Structure

```
Travel_Sync_12thMarch/
│
├── run.py                        ← Start the server from project root
├── requirements.txt              ← Python dependencies
├── .env.example                  ← Environment variable template
├── .gitignore
├── Dockerfile                    ← Container build
├── cloudbuild.yaml               ← GCP Cloud Build CI/CD
│
├── backend/                      ← All Python backend code
│   ├── .env                      ← API keys (never commit this)
│   ├── app.py                    ← Flask application factory
│   ├── auth.py                   ← Session auth helpers + decorators
│   ├── config.py                 ← Centralized environment config
│   ├── database.py               ← SQLite init, schema, seed data
│   ├── travelsync.db             ← SQLite database (auto-created)
│   │
│   ├── agents/                   ← AI agent modules
│   │   ├── orchestrator.py       ← Parallel A2A coordinator
│   │   ├── hotel_agent.py        ← Amadeus hotel search + PG options
│   │   ├── travel_mode_agent.py  ← Flights, trains, buses, cabs
│   │   ├── weather_agent.py      ← Forecast for travel dates
│   │   ├── meeting_agent.py      ← Client meetings CRUD + AI scheduling
│   │   ├── guide_agent.py        ← Local guide via Maps + Gemini
│   │   ├── checklist_agent.py    ← AI packing lists
│   │   ├── expense_agent.py      ← 3-stage OCR verification
│   │   ├── analytics_agent.py    ← DB analytics + compliance scoring
│   │   ├── chat_agent.py         ← Gemini conversational assistant
│   │   ├── policy_agent.py       ← Travel policy compliance checker
│   │   └── request_agent.py      ← Approval workflow engine
│   │
│   ├── routes/                   ← Flask Blueprint API routes
│   │   ├── auth.py               ← POST /api/auth/login|logout, GET /api/auth/me
│   │   ├── trips.py              ← POST /api/plan-trip
│   │   ├── weather.py            ← POST /api/weather, GET /api/weather/current
│   │   ├── currency.py           ← POST /api/currency/convert
│   │   ├── meetings.py           ← CRUD /api/meetings
│   │   ├── expenses.py           ← CRUD /api/expenses + OCR upload
│   │   ├── requests.py           ← CRUD /api/requests
│   │   ├── approvals.py          ← POST /api/approvals/:id/approve|reject
│   │   ├── analytics.py          ← GET /api/analytics/dashboard|spend|compliance
│   │   ├── chat.py               ← POST /api/chat, GET /api/chat/history
│   │   ├── uploads.py            ← POST /api/uploads
│   │   └── health.py             ← GET /api/health
│   │
│   ├── services/                 ← External API client wrappers
│   │   ├── gemini_service.py     ← Gemini 2.0 Flash + 1.5 Pro
│   │   ├── amadeus_service.py    ← Flights + Hotels + PG
│   │   ├── maps_service.py       ← Geocoding, Distance Matrix, Places
│   │   ├── weather_service.py    ← OpenWeatherMap
│   │   ├── currency_service.py   ← Open Exchange Rates
│   │   └── vision_service.py     ← Google Vision OCR
│   │
│   └── static/
│       └── uploads/              ← Uploaded receipts and invoices
│
└── frontend/                     ← React + Vite application
    ├── package.json
    ├── vite.config.js            ← Dev proxy: /api → localhost:3399
    ├── tailwind.config.js
    ├── index.html
    │
    └── src/
        ├── App.jsx               ← React Router v6 routes + auth guard
        ├── main.jsx              ← React entry point
        ├── index.css             ← Tailwind + CSS variables + global styles
        │
        ├── api/                  ← Axios API call modules
        │   ├── client.js         ← Axios instance with 401 interceptor
        │   ├── auth.js
        │   ├── trips.js
        │   ├── expenses.js
        │   ├── meetings.js
        │   ├── analytics.js
        │   ├── chat.js
        │   └── ...
        │
        ├── store/
        │   └── useStore.js       ← Zustand: auth, sidebar, notifications
        │
        ├── components/
        │   ├── layout/
        │   │   ├── Layout.jsx    ← Sidebar + Topbar wrapper
        │   │   ├── Sidebar.jsx   ← Dark navy nav with all 9 sections
        │   │   └── Topbar.jsx    ← Page title, health dot, notifications
        │   └── ui/
        │       ├── Button.jsx    ← Variants: primary, secondary, danger, ghost
        │       ├── Card.jsx
        │       ├── Input.jsx
        │       ├── Modal.jsx
        │       ├── Badge.jsx
        │       ├── Select.jsx
        │       ├── Spinner.jsx
        │       └── StatCard.jsx
        │
        └── pages/
            ├── Login.jsx         ← Split panel, demo quick-fill buttons
            ├── Dashboard.jsx     ← Stats, weather widget, recent activity
            ├── TripPlanner.jsx   ← Full AI trip planning + results
            ├── Accommodation.jsx ← Hotel + PG search
            ├── Expenses.jsx      ← 3-stage OCR expense submission
            ├── Meetings.jsx      ← Client meeting management
            ├── Requests.jsx      ← Submit travel requests
            ├── Approvals.jsx     ← Manager approval queue
            ├── Analytics.jsx     ← Spend charts, compliance scorecard
            └── Chat.jsx          ← Gemini AI travel assistant
```

---

## Setup & Installation

### Prerequisites

- Python 3.10 or higher
- Node.js 18 or higher
- npm 9 or higher
- A Google account (for Gemini API key — free at aistudio.google.com)

### Step 1 — Clone and set up Python environment

```bash
git clone <repo-url>
cd Travel_Sync_12thMarch

python -m venv venv

# Mac / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

### Step 2 — Configure environment variables

```bash
cp .env.example backend/.env
```

Open `backend/.env` and fill in your API keys. At minimum, add your **Gemini API key** — the app works in demo mode without the others:

```env
GEMINI_API_KEY=your_key_here
```

See the [Environment Variables](#environment-variables) section for the full list.

### Step 3 — Install React frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### Step 4 — Run

```bash
# Terminal 1 — Flask backend API
source venv/bin/activate   # or venv\Scripts\activate on Windows
python run.py              # API starts on http://localhost:3399

# Terminal 2 — React dev server
cd frontend
npm run dev                # UI starts on http://localhost:5173
```

Open **http://localhost:5173** in your browser.

> **Note**: In development, Vite proxies all `/api/*` requests to `localhost:3399` automatically. You never need to configure CORS manually during development.

---

## Environment Variables

All keys go in `backend/.env`. Copy from `.env.example` to get started.

```env
# ── Core ────────────────────────────────────────────────────
FLASK_SECRET_KEY=your-secret-key-change-in-production
DEBUG=True
PORT=3399

# ── AI — Required for planning, chat, checklists ────────────
GEMINI_API_KEY=                  # aistudio.google.com (free)

# ── Flights & Hotels — Real booking data ────────────────────
AMADEUS_CLIENT_ID=               # developers.amadeus.com
AMADEUS_CLIENT_SECRET=

# ── Maps — Hotel proximity, venue suggestions ────────────────
GOOGLE_MAPS_API_KEY=             # console.cloud.google.com
                                 # Enable: Maps, Distance Matrix, Geocoding, Places

# ── Weather ──────────────────────────────────────────────────
OPENWEATHER_API_KEY=             # openweathermap.org/api (free tier)

# ── Currency ─────────────────────────────────────────────────
OPEN_EXCHANGE_APP_ID=            # openexchangerates.org (free tier)

# ── Receipt OCR ──────────────────────────────────────────────
GOOGLE_VISION_API_KEY=           # console.cloud.google.com
                                 # Enable: Cloud Vision API
                                 # Can reuse GOOGLE_MAPS_API_KEY if both APIs enabled

# ── Database (leave blank for SQLite in dev) ─────────────────
DATABASE_URL=                    # postgres://user:pass@host/db (Cloud SQL in prod)

# ── GCP Deployment (optional) ────────────────────────────────
GCP_PROJECT_ID=
GCS_BUCKET=
```

### Service Status at Startup

When you run `python run.py`, the console shows which services are live:

```
══════════════════════════════════════════════════════════════
  TravelSync Pro v3.0 — AI-Powered Corporate Travel
══════════════════════════════════════════════════════════════
  gemini_ai                    ✅ Live
  amadeus_flights              ⚠️  Fallback
  google_maps                  ⚠️  Fallback
  weather                      ✅ Live
  vision_ocr                   ⚠️  Fallback
  currency                     ⚠️  Fallback
──────────────────────────────────────────────────────────────
  API     : http://localhost:3399/api
  React   : http://localhost:5173  (cd frontend && npm run dev)
══════════════════════════════════════════════════════════════
```

Services in `⚠️ Fallback` mode return realistic demo data so every feature remains usable.

---

## Running the Application

### Development (two terminals)

```bash
# Terminal 1
source venv/bin/activate && python run.py

# Terminal 2
cd frontend && npm run dev
```

Open: **http://localhost:5173**

### Production (single server)

Build the React app first, then Flask serves it:

```bash
cd frontend && npm run build && cd ..
source venv/bin/activate && python run.py
```

Open: **http://localhost:3399**

Flask serves `frontend/dist/index.html` for all non-API routes (SPA fallback routing).

### Override port

```bash
PORT=8080 python run.py
```

---

## API Reference

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/login` | Login with `{username, password}` |
| POST | `/api/auth/logout` | Clear session |
| GET | `/api/auth/me` | Current user info |

### Trip Planning

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/plan-trip` | Full AI trip plan — all agents in parallel |
| GET | `/api/requests` | List travel requests |
| POST | `/api/requests` | Submit new travel request |
| GET | `/api/requests/:id` | Single request details |

### Accommodation

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/accommodation/search` | Hotel search (Amadeus) |
| POST | `/api/accommodation/pg-options` | PG / long-stay search |

### Expenses

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/expenses?trip_id=X` | List expenses for a trip |
| POST | `/api/expenses` | Submit expense (3-stage) |
| GET | `/api/expenses/summary?trip_id=X` | Expense totals and breakdown |
| POST | `/api/expense/upload-and-extract` | Upload receipt + instant OCR |

### Meetings

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/meetings?trip_id=X` | List meetings |
| POST | `/api/meetings` | Create meeting |
| PUT | `/api/meetings/:id` | Update meeting |
| DELETE | `/api/meetings/:id` | Delete meeting |
| POST | `/api/meetings/suggest-schedule` | AI schedule optimization |
| POST | `/api/meetings/nearby-venues` | Google Maps venue suggestions |

### Approvals

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/approvals` | Pending approvals (manager/admin only) |
| POST | `/api/approvals/:id/approve` | Approve a request |
| POST | `/api/approvals/:id/reject` | Reject with `{reason}` |

### Analytics

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/analytics/dashboard` | Stats: active trips, spend, compliance |
| GET | `/api/analytics/spend` | Spend breakdown by category + department |
| GET | `/api/analytics/compliance` | Policy compliance scorecard |

### Weather & Currency

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/weather` | Travel forecast for `{city, travel_dates}` |
| GET | `/api/weather/current?city=X` | Current weather for dashboard widget |
| POST | `/api/currency/convert` | Convert `{amount, from_currency, to_currency}` |
| GET | `/api/currency/travel-info?destination=X` | Destination currency info |

### Chat & Health

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/chat` | Send message to Gemini assistant |
| GET | `/api/chat/history` | Conversation history |
| GET | `/api/health` | Service status for all APIs |

---

## Demo Users

The database is seeded with these accounts on first run:

| Username | Password | Role | Department |
|---|---|---|---|
| `vaibhav` | `admin123` | Admin | Operations |
| `rohit` | `admin123` | Admin | Finance |
| `manager1` | `mgr123` | Manager | Sales |
| `employee1` | `emp123` | Employee | Sales |
| `employee2` | `emp123` | Employee | Engineering |

The Login page also has **demo quick-fill buttons** — click any role to auto-fill credentials.

---

## Deployment (GCP)

### Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated
- Enable APIs: Cloud Run, Cloud Build, Cloud SQL, Secret Manager, Artifact Registry

### Deploy to Cloud Run

```bash
# Set your project
gcloud config set project YOUR_PROJECT_ID

# Build and deploy (Cloud Build handles everything)
gcloud builds submit --config=cloudbuild.yaml
```

The `cloudbuild.yaml` will:
1. Build the React frontend (`npm run build`)
2. Build the Docker container
3. Push to Artifact Registry
4. Deploy to Cloud Run in `asia-south1`
5. Inject secrets from Secret Manager

### Store API Keys in Secret Manager

```bash
# Create secrets for each API key
echo -n "your-gemini-key" | gcloud secrets create GEMINI_API_KEY --data-file=-
echo -n "your-amadeus-id" | gcloud secrets create AMADEUS_CLIENT_ID --data-file=-
# ... repeat for all keys
```

### Set Up Cloud SQL (Production Database)

```bash
# Create Cloud SQL PostgreSQL instance
gcloud sql instances create travelsync-db \
  --database-version=POSTGRES_15 \
  --region=asia-south1 \
  --tier=db-f1-micro

# Set DATABASE_URL in Cloud Run environment
# postgresql://user:pass@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE
```

---

## Troubleshooting

### Port already in use

```bash
PORT=8080 python run.py
```

### Python module not found

```bash
pip install -r requirements.txt --upgrade
```

### React dev server CORS issues

Make sure both servers are running. Vite's proxy in `vite.config.js` handles CORS in development — you should never see CORS errors if both `python run.py` (port 3399) and `npm run dev` (port 5173) are running.

### Gemini API errors

- Verify key at https://aistudio.google.com
- Check quota: free tier allows 15 requests/minute
- App continues in fallback/demo mode if key is invalid

### Amadeus "No results" for flights

- Amadeus test environment has limited routes
- Try major city pairs: BOM→BLR, DEL→BOM, BLR→HYD
- Production keys have full coverage

### SQLite database locked

```bash
# Stop all running instances of the app, then restart
python run.py
```

### React build fails

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run build
```

---

## Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes in `backend/` or `frontend/src/`
3. Test backend: `python run.py` and verify `/api/health`
4. Test frontend: `cd frontend && npm run dev`
5. Build check: `cd frontend && npm run build` (must succeed with zero errors)
6. Open a pull request

---

*Built for Indian enterprises. Powered by Google Gemini AI, Amadeus, and Google Cloud.*
