"""
TravelSync Pro — Shared Flask Extensions
SocketIO and Limiter instances live here so route blueprints can import them
without creating circular dependencies with app.py.
"""
import os
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

socketio = SocketIO()

# Rate limiter — when REDIS_URL is set, limits are enforced globally across all
# Cloud Run instances. Without Redis, limits are per-process (acceptable for
# single-instance dev, but multiple instances let an attacker bypass limits by
# hitting different backends).
_redis_url = os.getenv("REDIS_URL", "").strip()
_limiter_storage = f"redis://{_redis_url.split('://', 1)[-1]}" if _redis_url else "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute", "5000 per hour"],
    storage_uri=_limiter_storage,
)
