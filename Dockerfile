FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --prefer-offline
COPY frontend/ .
RUN npm run build

# ── Python backend ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./

# Copy compiled React build from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Uploads directory
RUN mkdir -p static/uploads

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Cloud Run uses PORT env var
ENV PORT=8080
EXPOSE 8080

CMD exec gunicorn --bind 0.0.0.0:$PORT --worker-class eventlet -w 1 --timeout 120 app:app
