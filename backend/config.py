"""
TravelSync Pro — Configuration
All settings loaded from environment variables. Nothing hardcoded.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Core
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-this-in-production")
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"
    PORT = int(os.getenv("PORT", 3399))

    # Paths — BASE_DIR is the backend/ directory; PROJECT_ROOT is one level up
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(BASE_DIR)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    REACT_BUILD = os.path.join(PROJECT_ROOT, "frontend", "dist")
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "doc", "docx",
                          "xls", "xlsx", "csv", "txt", "zip"}

    # AI & APIs
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID")
    AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET")
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
    OPEN_EXCHANGE_APP_ID = os.getenv("OPEN_EXCHANGE_APP_ID")
    GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL")  # Cloud SQL in prod, SQLite in dev

    # GCP
    GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    GCS_BUCKET = os.getenv("GCS_BUCKET")

    @classmethod
    def services_status(cls) -> dict:
        """Returns which services are live vs fallback."""
        return {
            "gemini_ai":         bool(cls.GEMINI_API_KEY),
            "amadeus_flights":   bool(cls.AMADEUS_CLIENT_ID),
            "google_maps":       bool(cls.GOOGLE_MAPS_API_KEY),
            "weather":           bool(cls.OPENWEATHER_API_KEY),
            "vision_ocr":        bool(cls.GOOGLE_VISION_API_KEY),
            "currency":          bool(cls.OPEN_EXCHANGE_APP_ID),
        }

    @classmethod
    def allowed_file(cls, filename: str) -> bool:
        return ("." in filename and
                filename.rsplit(".", 1)[1].lower() in cls.ALLOWED_EXTENSIONS)
