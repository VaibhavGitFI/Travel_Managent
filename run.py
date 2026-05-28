"""
TravelSync Pro — Root launcher
Run from the project root: python run.py

This serves the pre-built React app AND the Flask REST API on a single port (3399).
For development with hot-reload, use: cd frontend && npm start
"""
import sys
import os
import logging

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)
os.environ.setdefault("FLASK_APP", os.path.join(BACKEND, "app.py"))

# Import the already-created app instance from app.py.
# app.py creates the Flask app exactly once at module level (for Gunicorn
# compatibility). Importing `app` here reuses that instance — we must NOT call
# create_app() again, as that would double-register all 26 blueprints, run
# init_db() twice, and register every SocketIO event handler twice.
from app import app, socketio, log_startup_banner  # noqa: E402
from config import Config                          # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log_startup_banner()
    socketio.run(app, host="0.0.0.0", port=Config.PORT,
                 debug=Config.DEBUG, use_reloader=False)
