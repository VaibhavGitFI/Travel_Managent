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
    # DEBUG defaults to False — must be explicitly set to "true" to enable.
    # Flask debug mode activates the Werkzeug interactive debugger (RCE risk).
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"

    try:
        PORT = int(os.getenv("PORT", 3399))
    except (ValueError, TypeError):
        PORT = 3399

    # Flask session signing key — required; no insecure fallback.
    _raw_secret = _get_env_or_secret("FLASK_SECRET_KEY")
    if not _raw_secret:
        if _is_gcp():
            raise RuntimeError(
                "FLASK_SECRET_KEY must be configured in GCP Secret Manager "
                "for production deployments. Add it via: "
                "gcloud secrets create FLASK_SECRET_KEY --data-file=<keyfile>"
            )
        # Local dev only — never used in production.
        logger.warning(
            "[Config] FLASK_SECRET_KEY not set — using insecure dev placeholder. "
            "Set FLASK_SECRET_KEY in backend/.env before running against real data."
        )
        _raw_secret = "dev-only-insecure-placeholder-do-not-use"
    SECRET_KEY = _raw_secret

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
    CLIQ_WEBHOOK_TOKEN      = _get_env_or_secret("CLIQ_WEBHOOK_TOKEN")

    # Notifications — Slack
    SLACK_WEBHOOK_URL = _get_env_or_secret("SLACK_WEBHOOK_URL")
    SLACK_BOT_TOKEN   = _get_env_or_secret("SLACK_BOT_TOKEN")
    SLACK_CHANNEL     = os.getenv("SLACK_CHANNEL", "#travel-notifications")

    # Database — Cloud SQL PostgreSQL in prod (via DATABASE_URL), SQLite in dev
    DATABASE_URL = _get_env_or_secret("DATABASE_URL")

    # Redis — optional. Enables global rate limiting, cross-instance SocketIO,
    # and shared caching. Without Redis everything falls back to in-process memory.
    # Example: redis://localhost:6379/0 or redis://:<password>@redis-host:6379/0
    REDIS_URL = _get_env_or_secret("REDIS_URL")

    # JWT — intentionally independent from SECRET_KEY so rotating one does not
    # invalidate the other. Falls back to SECRET_KEY only in non-GCP (dev) mode.
    _raw_jwt_secret = _get_env_or_secret("JWT_SECRET_KEY")
    if not _raw_jwt_secret:
        if _is_gcp():
            raise RuntimeError(
                "JWT_SECRET_KEY must be configured in GCP Secret Manager. "
                "Add it via: gcloud secrets create JWT_SECRET_KEY --data-file=<keyfile>"
            )
        logger.warning(
            "[Config] JWT_SECRET_KEY not set — falling back to SECRET_KEY (dev only)."
        )
        _raw_jwt_secret = SECRET_KEY
    JWT_SECRET_KEY = _raw_jwt_secret

    # Access token lifetime — reduced from 24h to 60 min. Short-lived tokens
    # limit the blast radius of token theft. The frontend uses silent refresh
    # via the /api/auth/refresh endpoint + long-lived refresh token.
    try:
        JWT_ACCESS_TTL = int(os.getenv("JWT_ACCESS_TTL_MINUTES", "60"))
    except (ValueError, TypeError):
        JWT_ACCESS_TTL = 60
    try:
        JWT_REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL_DAYS", "30"))
    except (ValueError, TypeError):
        JWT_REFRESH_TTL = 30

    # CORS — comma-separated list of allowed origins.
    # Default: localhost dev servers. Override in production:
    #   CORS_ORIGINS=https://app.travelsync.pro
    CORS_ORIGINS = [
        o.strip() for o in
        os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3399,http://127.0.0.1:5173,http://127.0.0.1:3399").split(",")
        if o.strip()
    ]

    # GCP
    GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    GCS_BUCKET     = os.getenv("GCS_BUCKET")

    # ── OTIS Voice Agent Configuration ────────────────────────────────────────
    OTIS_ENABLED = os.getenv("OTIS_ENABLED", "False").lower() == "true"
    OTIS_ADMIN_ONLY = os.getenv("OTIS_ADMIN_ONLY", "True").lower() == "true"
    OTIS_DEBUG = os.getenv("OTIS_DEBUG", "False").lower() == "true"

    # OTIS API Keys
    PORCUPINE_ACCESS_KEY = _get_env_or_secret("PORCUPINE_ACCESS_KEY")
    # Deepgram + ElevenLabs no longer used — OTIS now uses Gemini Live API
    # (kept as None so existing code that checks them doesn't crash)
    DEEPGRAM_API_KEY   = None
    ELEVENLABS_API_KEY = None

    # OTIS Voice Settings — Gemini Live voices
    # Available: Puck, Charon, Kore, Fenrir, Aoede, Orus, Perseus
    # Best for Indian English: Puck (energetic), Orus (calm), Charon (deep)
    OTIS_LIVE_VOICE    = os.getenv("OTIS_LIVE_VOICE", "Puck")
    OTIS_VOICE_LANGUAGE = os.getenv("OTIS_VOICE_LANGUAGE", "en-IN")
    # Google Cloud TTS voice for REST /speak endpoint (Indian English Neural)
    OTIS_GCP_TTS_VOICE = os.getenv("OTIS_GCP_TTS_VOICE", "en-IN-Neural2-B")

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
            "otis_voice":        bool(cls.OTIS_ENABLED and cls.GEMINI_API_KEY),
            # Wake word works with OpenWakeWord (no key) or Porcupine (with key)
            "otis_wake_word":    True,
            "otis_stt":          bool(cls.GEMINI_API_KEY),   # Gemini Live STT
            "otis_tts":          bool(cls.GEMINI_API_KEY),   # Google Cloud TTS / Gemini Live TTS
        }

    @classmethod
    def allowed_file(cls, filename: str) -> bool:
        return ("." in filename and
                filename.rsplit(".", 1)[1].lower() in cls.ALLOWED_EXTENSIONS)

    @classmethod
    def validate(cls) -> None:
        """Fail fast if critical production config is missing.
        Called at the end of create_app() in app.py."""
        errors = []

        if _is_gcp():
            # These MUST be set in production
            required = {
                "SECRET_KEY": cls.SECRET_KEY,
                "JWT_SECRET_KEY": cls.JWT_SECRET_KEY,
                "DATABASE_URL": cls.DATABASE_URL,
            }
            for name, value in required.items():
                if not value or value in ("change-this-in-production", "dev-only-insecure-placeholder-do-not-use"):
                    errors.append(f"{name} is not configured")

        # Optional — warn but don't fail
        optional = {
            "GEMINI_API_KEY": cls.GEMINI_API_KEY,
            "SMTP_HOST": cls.SMTP_HOST,
        }
        for name, value in optional.items():
            if not value:
                logger.warning("[Config] Optional config missing: %s — related features disabled", name)

        if errors:
            msg = "FATAL: Missing required configuration:\n" + "\n".join(f"  - {e}" for e in errors)
            logger.critical(msg)
            raise RuntimeError(msg)
