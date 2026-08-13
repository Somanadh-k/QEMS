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

    max_upload_size_mb: int = 15

    login_rate_limit_per_minute: int = 5

    # --- Object storage (Section 6.2: Supabase Storage / Azure Blob / S3-compatible) ---
    # Points at a local MinIO instance for dev; swap for a real S3-compatible endpoint in prod.
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_url: str = "http://localhost:9000"
    s3_access_key: str = "qems_minio"
    s3_secret_key: str = "qems_minio_secret"
    s3_bucket: str = "qems-evidence"
    s3_region: str = "us-east-1"

    # --- Email (Section 4.7: transactional email API) ---
    # Points at a local Mailpit instance for dev; swap for SendGrid/Resend/real SMTP in prod.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_use_tls: bool = False
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = "qems@qemscorp.dev"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
