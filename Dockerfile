FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create uploads directory
RUN mkdir -p static/uploads

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Cloud Run uses PORT env var
ENV PORT=8080
EXPOSE 8080

CMD exec gunicorn --bind 0.0.0.0:$PORT --worker-class eventlet -w 1 --timeout 120 app:app
