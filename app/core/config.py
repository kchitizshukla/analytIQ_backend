"""Application configuration, loaded from environment / .env.

Secrets (DB credentials, API keys) are never hardcoded — they come from the
environment. See backend/.env.example for the full list.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- App ---
    app_name: str = "AnalytIQ"
    app_tagline: str = "Turn your data into decisions."
    environment: str = "development"
    api_prefix: str = "/api"

    # --- Authentication / sessions ---
    # Secret used to sign session tokens. MUST be overridden via env in any
    # non-local deployment. A random per-process fallback is used if unset so
    # the app still boots, but sessions won't survive a restart.
    jwt_secret_key: str = ""
    session_cookie_name: str = "analytiq_session"
    session_ttl_hours: int = 24 * 7  # 7 days
    cookie_secure: bool = False  # set True behind HTTPS in production

    # --- Database (credentials via env only) ---
    database_url: str = Field(
        default="postgresql+psycopg://postgres@localhost:5432/DAT",
        description="SQLAlchemy URL. Password supplied via env, never committed.",
    )

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_db_scheme(cls, v: str) -> str:
        """Force the psycopg 3 dialect.

        This app installs psycopg 3 (not psycopg2). Managed providers (Neon,
        Render, Heroku, Supabase) hand out `postgresql://` / `postgres://`
        URLs, which SQLAlchemy maps to the *psycopg2* dialect and then fails
        with `No module named 'psycopg2'`. Rewriting the scheme here means a
        pasted provider URL works unchanged.
        """
        for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    # --- CORS / frontend ---
    frontend_url: str = "http://localhost:3000"

    # --- Uploads ---
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50
    allowed_extensions: List[str] = ["xlsx", "xls", "csv", "pdf"]

    # --- LLM provider abstraction ---
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def _split_ext(cls, v):
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        return v

    @property
    def cors_origins(self) -> List[str]:
        origins = {self.frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"}
        return [o for o in origins if o]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def llm_enabled(self) -> bool:
        return bool(self.gemini_api_key) and self.llm_provider.lower() == "gemini"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
