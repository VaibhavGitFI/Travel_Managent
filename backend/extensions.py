"""
TravelSync Pro — Shared Flask Extensions
SocketIO and Limiter instances live here so route blueprints can import them
without creating circular dependencies with app.py.
"""
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

socketio = SocketIO()

# Rate limiter — limits are applied via @limiter.limit() decorators in route files
limiter = Limiter(key_func=get_remote_address, default_limits=[])
