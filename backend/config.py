"""
TravelSync Pro — Configuration
All settings loaded from environment variables.
In GCP environments, missing secrets are fetched from Secret Manager automatically.
"""
import os
import logging
from dotenv import load_dotenv

# Always load from backend/.env regardless of working directory
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_env_path, override=True)
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
    try:
        PORT = int(os.getenv("PORT", 3399))
    except (ValueError, TypeError):
        PORT = 3399

    # Warn loudly if using the default secret in production
    if _is_gcp() and SECRET_KEY == "change-this-in-production":
        logger.critical(
            "FLASK_SECRET_KEY is using default value in production! "
            "Set it via Secret Manager or environment variable immediately."
        )

    # Paths — BASE_DIR is the backend/ directory; PROJECT_ROOT is one level up
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(BASE_DIR)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    REACT_BUILD = os.path.join(PROJECT_ROOT, "frontend", "dist")
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "doc", "docx",
                          "xls", "xlsx", "csv", "txt", "zip",
                          "ogg", "mp3", "wav", "m4a", "webm", "aac", "opus", "amr"}

    # AI & APIs — fetched from Secret Manager when running on GCP
    ANTHROPIC_API_KEY     = _get_env_or_secret("ANTHROPIC_API_KEY")
    GEMINI_API_KEY        = _get_env_or_secret("GEMINI_API_KEY")
    AMADEUS_CLIENT_ID     = _get_env_or_secret("AMADEUS_CLIENT_ID")
    AMADEUS_CLIENT_SECRET = _get_env_or_secret("AMADEUS_CLIENT_SECRET")
    GOOGLE_MAPS_API_KEY   = _get_env_or_secret("GOOGLE_MAPS_API_KEY")
    OPENWEATHER_API_KEY   = _get_env_or_secret("OPENWEATHER_API_KEY")
    OPEN_EXCHANGE_APP_ID  = _get_env_or_secret("OPEN_EXCHANGE_APP_ID")
    GOOGLE_VISION_API_KEY = _get_env_or_secret("GOOGLE_VISION_API_KEY")
    GOOGLE_SEARCH_CX      = _get_env_or_secret("GOOGLE_SEARCH_CX")

    # Notifications — WhatsApp (Twilio)
    TWILIO_ACCOUNT_SID    = _get_env_or_secret("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN     = _get_env_or_secret("TWILIO_AUTH_TOKEN")
    TWILIO_WHATSAPP_FROM  = os.getenv("TWILIO_WHATSAPP_FROM", "+14155238886")

    # Notifications — Email (SMTP)
    SMTP_HOST          = _get_env_or_secret("SMTP_HOST")
    try:
        SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    except (ValueError, TypeError):
        SMTP_PORT = 587
    SMTP_USER          = _get_env_or_secret("SMTP_USER")
    SMTP_PASSWORD      = _get_env_or_secret("SMTP_PASSWORD")
    SMTP_FROM_EMAIL    = os.getenv("SMTP_FROM_EMAIL")
    SMTP_FROM_NAME     = os.getenv("SMTP_FROM_NAME", "TravelSync Pro")

    # Notifications — Zoho Cliq (OAuth2 API)
    ZOHO_CLIQ_API_ENDPOINT  = _get_env_or_secret("ZOHO_CLIQ_API_ENDPOINT")
    ZOHO_CLIQ_CLIENT_ID     = _get_env_or_secret("ZOHO_CLIQ_CLIENT_ID")
    ZOHO_CLIQ_CLIENT_SECRET = _get_env_or_secret("ZOHO_CLIQ_CLIENT_SECRET")
    ZOHO_CLIQ_REFRESH_TOKEN = _get_env_or_secret("ZOHO_CLIQ_REFRESH_TOKEN")
    ZOHO_CLIQ_ACCESS_TOKEN  = _get_env_or_secret("ZOHO_CLIQ_ACCESS_TOKEN")

    # Notifications — Slack
    SLACK_WEBHOOK_URL = _get_env_or_secret("SLACK_WEBHOOK_URL")
    SLACK_BOT_TOKEN   = _get_env_or_secret("SLACK_BOT_TOKEN")
    SLACK_CHANNEL     = os.getenv("SLACK_CHANNEL", "#travel-notifications")

    # Database — Cloud SQL PostgreSQL in prod (via DATABASE_URL), SQLite in dev
    DATABASE_URL = _get_env_or_secret("DATABASE_URL")

    # JWT
    JWT_SECRET_KEY  = _get_env_or_secret("JWT_SECRET_KEY", default=SECRET_KEY)
    try:
        JWT_ACCESS_TTL = int(os.getenv("JWT_ACCESS_TTL_MINUTES", "1440"))
    except (ValueError, TypeError):
        JWT_ACCESS_TTL = 1440
    try:
        JWT_REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL_DAYS", "30"))
    except (ValueError, TypeError):
        JWT_REFRESH_TTL = 30

    # GCP
    GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    GCS_BUCKET     = os.getenv("GCS_BUCKET")

    # ── OTIS Voice Agent Configuration ────────────────────────────────────────
    OTIS_ENABLED = os.getenv("OTIS_ENABLED", "False").lower() == "true"
    OTIS_ADMIN_ONLY = os.getenv("OTIS_ADMIN_ONLY", "True").lower() == "true"
    OTIS_DEBUG = os.getenv("OTIS_DEBUG", "False").lower() == "true"

    # OTIS API Keys
    PORCUPINE_ACCESS_KEY = _get_env_or_secret("PORCUPINE_ACCESS_KEY")
    DEEPGRAM_API_KEY     = _get_env_or_secret("DEEPGRAM_API_KEY")
    ELEVENLABS_API_KEY   = _get_env_or_secret("ELEVENLABS_API_KEY")

    # OTIS Voice Settings
    OTIS_VOICE_ID = os.getenv("OTIS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
    OTIS_VOICE_GENDER = os.getenv("OTIS_VOICE_GENDER", "male")
    OTIS_VOICE_LANGUAGE = os.getenv("OTIS_VOICE_LANGUAGE", "en-IN")

    try:
        OTIS_VOICE_SPEED = float(os.getenv("OTIS_VOICE_SPEED", "1.0"))
    except (ValueError, TypeError):
        OTIS_VOICE_SPEED = 1.0

    try:
        OTIS_VOICE_PITCH = float(os.getenv("OTIS_VOICE_PITCH", "0.0"))
    except (ValueError, TypeError):
        OTIS_VOICE_PITCH = 0.0

    try:
        OTIS_VOICE_STABILITY = float(os.getenv("OTIS_VOICE_STABILITY", "0.5"))
    except (ValueError, TypeError):
        OTIS_VOICE_STABILITY = 0.5

    try:
        OTIS_VOICE_SIMILARITY = float(os.getenv("OTIS_VOICE_SIMILARITY", "0.75"))
    except (ValueError, TypeError):
        OTIS_VOICE_SIMILARITY = 0.75

    # OTIS Behavior
    OTIS_WAKE_WORD = os.getenv("OTIS_WAKE_WORD", "Hey Otis")
    OTIS_AUTO_EXECUTE = os.getenv("OTIS_AUTO_EXECUTE", "False").lower() == "true"
    OTIS_REQUIRE_CONFIRMATION = os.getenv("OTIS_REQUIRE_CONFIRMATION", "True").lower() == "true"

    try:
        OTIS_MAX_SESSION_DURATION = int(os.getenv("OTIS_MAX_SESSION_DURATION", "600"))
    except (ValueError, TypeError):
        OTIS_MAX_SESSION_DURATION = 600

    try:
        OTIS_IDLE_TIMEOUT = int(os.getenv("OTIS_IDLE_TIMEOUT", "30"))
    except (ValueError, TypeError):
        OTIS_IDLE_TIMEOUT = 30

    # OTIS Rate Limiting
    try:
        OTIS_MAX_SESSIONS_PER_HOUR = int(os.getenv("OTIS_MAX_SESSIONS_PER_HOUR", "10"))
    except (ValueError, TypeError):
        OTIS_MAX_SESSIONS_PER_HOUR = 10

    try:
        OTIS_MAX_COMMANDS_PER_SESSION = int(os.getenv("OTIS_MAX_COMMANDS_PER_SESSION", "50"))
    except (ValueError, TypeError):
        OTIS_MAX_COMMANDS_PER_SESSION = 50

    # OTIS Cost Management
    try:
        OTIS_MONTHLY_BUDGET_USD = float(os.getenv("OTIS_MONTHLY_BUDGET_USD", "500"))
    except (ValueError, TypeError):
        OTIS_MONTHLY_BUDGET_USD = 500.0

    try:
        OTIS_WARN_AT_PERCENT = int(os.getenv("OTIS_WARN_AT_PERCENT", "80"))
    except (ValueError, TypeError):
        OTIS_WARN_AT_PERCENT = 80

    @classmethod
    def services_status(cls) -> dict:
        """Returns which services are live vs fallback."""
        return {
            "claude_ai":         bool(cls.ANTHROPIC_API_KEY),
            "gemini_ai":         bool(cls.GEMINI_API_KEY),
            "flights":           True,  # AI-powered + curated flight data
            "google_maps":       bool(cls.GOOGLE_MAPS_API_KEY),
            "weather":           bool(cls.OPENWEATHER_API_KEY),
            "vision_ocr":        bool(cls.GOOGLE_VISION_API_KEY),
            "currency":          bool(cls.OPEN_EXCHANGE_APP_ID),
            "whatsapp":          bool(cls.TWILIO_ACCOUNT_SID and cls.TWILIO_AUTH_TOKEN),
            "email_smtp":        bool(cls.SMTP_HOST and cls.SMTP_USER),
            "zoho_cliq":         bool(cls.ZOHO_CLIQ_API_ENDPOINT and cls.ZOHO_CLIQ_REFRESH_TOKEN),
            "slack":             bool(cls.SLACK_WEBHOOK_URL or cls.SLACK_BOT_TOKEN),
            "otis_voice":        bool(cls.OTIS_ENABLED and
                                     cls.DEEPGRAM_API_KEY and cls.ELEVENLABS_API_KEY),
            # Wake word works with OpenWakeWord (no key) or Porcupine (with key)
            "otis_wake_word":    True,
            "otis_stt":          bool(cls.DEEPGRAM_API_KEY),
            "otis_tts":          bool(cls.ELEVENLABS_API_KEY),
        }

    @classmethod
    def allowed_file(cls, filename: str) -> bool:
        return ("." in filename and
                filename.rsplit(".", 1)[1].lower() in cls.ALLOWED_EXTENSIONS)
