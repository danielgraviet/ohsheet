from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Legacy single-tenant (CRON) ──────────────────────────────────────────
    canvas_token: str = ""
    canvas_domain: str = ""
    spreadsheet_id: str = ""
    google_creds_json: str = ""

    # ── Always required ───────────────────────────────────────────────────────
    redis_url: str
    local_timezone: str = "America/Denver"

    # ── Multi-tenant ─────────────────────────────────────────────────────────
    database_url: str = ""
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""
    session_secret_key: str = ""
    # base64-encoded Fernet key — generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: str = ""
    app_base_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# Instantiated at import time — fails fast if required vars are missing.
settings = Settings()
