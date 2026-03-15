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

from app import socketio, create_app, log_startup_banner  # noqa: E402
from config import Config                                  # noqa: E402

app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log_startup_banner()
    socketio.run(app, host="0.0.0.0", port=Config.PORT,
                 debug=Config.DEBUG, use_reloader=False)
