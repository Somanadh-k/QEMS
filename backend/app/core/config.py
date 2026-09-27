from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://qems:qems@localhost:5432/qems"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cors_origins: str = "http://localhost:5173"

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    # Per-feature kill switch. Turning narration off degrades the Quality Signal Engine to
    # its deterministic half rather than erroring — the metrics are unaffected.
    ai_narration_enabled: bool = True

    max_upload_size_mb: int = 15

    login_rate_limit_per_minute: int = 5
    # Separate, far higher bucket for ordinary reads: one detail page fans out to several
    # sub-resource calls, so the login limit throttled normal use.
    api_rate_limit_per_minute: int = 120

    # --- Object storage (Section 6.2: Supabase Storage / Azure Blob / S3-compatible) ---
    # Points at a local MinIO instance for dev; swap for a real S3-compatible endpoint in prod.
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "qems_minio"
    s3_secret_key: str = "qems_minio_secret"
    s3_bucket: str = "qems-evidence"
    s3_region: str = "us-east-1"

    # --- Email (Section 4.7: transactional email API) ---
    # Points at a local Mailpit instance for dev; swap for SendGrid/Resend/real SMTP in prod.
    # Also the fallback provider notification_service.py uses when Gmail OAuth below
    # isn't configured -- Gmail is never required for the app to send notifications.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_use_tls: bool = False
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = "qems@qemscorp.dev"

    # --- Gmail OAuth (Feature 2: notification_providers.GmailProvider) ---
    # See backend/README.md "Gmail notification setup" for how to obtain each of these.
    # Unset by default -> GmailProvider.is_configured() is False -> the notification
    # service transparently falls back to the SMTP settings above.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Only used as documentation of what's registered in Google Cloud Console -- the
    # running app never redirects a browser through Google (see scripts/gmail_oauth_setup.py,
    # which is what actually listens on this URI, once, to mint the refresh token below).
    google_redirect_uri: str = "http://localhost:8765/"
    google_refresh_token: str = ""
    gmail_sender: str = ""
    # Base URL used to build the "View Error" / "Reply here" link embedded in every
    # notification email ({{qems_url}}). Never derived from request headers, which are
    # attacker-controlled.
    app_base_url: str = "http://localhost:5173"
    # Failed notifications are retried this many times (exponential backoff) before
    # being left FAILED for good -- see workers/scheduler.py:run_notification_retry_tick.
    notification_max_retries: int = 3

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
