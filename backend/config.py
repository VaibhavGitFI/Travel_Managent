"""
TravelSync Pro — Configuration
All settings loaded from environment variables.
In GCP environments, missing secrets are fetched from Secret Manager automatically.
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── GCP Secret Manager helper ──────────────────────────────────────────────────

def _is_gcp() -> bool:
    """Detect whether we are running inside a GCP managed environment."""
    return bool(
        os.getenv("K_SERVICE")          # Cloud Run
        or os.getenv("GAE_APPLICATION") # App Engine
        or os.getenv("CLOUD_RUN_JOB")   # Cloud Run jobs
        or os.getenv("GCP_PROJECT_ID")  # Explicitly set
    )


def _fetch_secret(project_id: str, secret_name: str) -> str | None:
    """Fetch a secret value from GCP Secret Manager."""
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        resource_name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": resource_name})
        return response.payload.data.decode("utf-8").strip()
    except Exception as exc:
        logger.debug("[Config] Secret Manager fetch failed for %s: %s", secret_name, exc)
        return None


def _get_env_or_secret(env_key: str, secret_name: str | None = None, default: str | None = None) -> str | None:
    """Return env var if present; if on GCP and missing, try Secret Manager; else default."""
    val = os.getenv(env_key)
    if val:
        return val
    if _is_gcp():
        project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            secret_key = secret_name or env_key
            secret_val = _fetch_secret(project_id, secret_key)
            if secret_val:
                return secret_val
    return default


class Config:
    # Core
    SECRET_KEY = _get_env_or_secret("FLASK_SECRET_KEY", default="change-this-in-production")
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

    # AI & APIs — fetched from Secret Manager when running on GCP
    GEMINI_API_KEY        = _get_env_or_secret("GEMINI_API_KEY")
    AMADEUS_CLIENT_ID     = _get_env_or_secret("AMADEUS_CLIENT_ID")
    AMADEUS_CLIENT_SECRET = _get_env_or_secret("AMADEUS_CLIENT_SECRET")
    GOOGLE_MAPS_API_KEY   = _get_env_or_secret("GOOGLE_MAPS_API_KEY")
    OPENWEATHER_API_KEY   = _get_env_or_secret("OPENWEATHER_API_KEY")
    OPEN_EXCHANGE_APP_ID  = _get_env_or_secret("OPEN_EXCHANGE_APP_ID")
    GOOGLE_VISION_API_KEY = _get_env_or_secret("GOOGLE_VISION_API_KEY")

    # Database — Cloud SQL PostgreSQL in prod (via DATABASE_URL), SQLite in dev
    DATABASE_URL = _get_env_or_secret("DATABASE_URL")

    # JWT
    JWT_SECRET_KEY  = _get_env_or_secret("JWT_SECRET_KEY", default=SECRET_KEY)
    JWT_ACCESS_TTL  = int(os.getenv("JWT_ACCESS_TTL_MINUTES", "1440"))   # 24 h
    JWT_REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL_DAYS", "30"))

    # GCP
    GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    GCS_BUCKET     = os.getenv("GCS_BUCKET")

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
