# ── Stage 1: React build ───────────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --prefer-offline
COPY frontend/ .
RUN npm run build

# ── Stage 2: Python backend ────────────────────────────────────────────────────
FROM python:3.11-slim

# System dependencies (gcc for C extensions, libpq-dev for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching)
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source into /app/backend/ — mirrors the dev project layout:
#
#   Dev:                              Container:
#   Travel_Sync_12thMarch/            /app/
#     backend/                          backend/    ← BASE_DIR
#       config.py                         config.py
#     frontend/dist/                    frontend/dist/  ← REACT_BUILD
#
#   config.py computes:
#     BASE_DIR    = dirname(__file__)   →  /app/backend
#     PROJECT_ROOT = dirname(BASE_DIR) →  /app
#     REACT_BUILD  = PROJECT_ROOT/frontend/dist  →  /app/frontend/dist  ✓
COPY backend/ ./backend/

# Copy compiled React build from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Uploads directory (path = BASE_DIR/static/uploads = /app/backend/static/uploads)
RUN mkdir -p backend/static/uploads

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Cloud Run injects PORT; PYTHONUNBUFFERED sends logs to Cloud Logging immediately;
# PYTHONDONTWRITEBYTECODE avoids writing .pyc files into the container FS.
ENV PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

# Healthcheck — used by Docker / local runs. Cloud Run ignores this and uses its
# own startup probe; /api/health is still the right target for both.
# start-period=40s gives gunicorn + eventlet time to finish booting.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:$PORT/api/health')" || exit 1

# Run from /app/backend so `app:app` resolves to /app/backend/app.py.
# Gunicorn flags:
#   --worker-class eventlet  — required; matches async_mode in app.py
#   -w 1                     — eventlet uses green threads; multiple OS workers
#                              would fight over the same in-process state
#   --max-requests 1000      — recycle worker after 1000 req (prevents slow leaks)
#   --max-requests-jitter 50 — randomise restart timing (avoids mid-traffic hard stop)
#   --graceful-timeout 30    — flush in-flight requests before SIGKILL on shutdown
#   --keep-alive 5           — reuse idle HTTP connections from the load balancer
WORKDIR /app/backend
CMD exec gunicorn \
    --bind 0.0.0.0:$PORT \
    --worker-class eventlet \
    -w 1 \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --log-level warning \
    app:app
