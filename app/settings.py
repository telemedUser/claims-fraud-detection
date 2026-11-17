"""Typed application settings. The only module that reads the process environment or .env.

Values come from real environment variables first, then the git-ignored ``.env`` (development).
Empty values are treated as unset, so a blank variable falls back to its default.
``get_settings()`` builds a fresh object on every call so changes to the environment (tests,
operators) take effect immediately. ``validate_required()`` fails fast at startup and names the
missing variables without ever printing a value (Requirements 1.5-1.7).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
DEFAULT_GEMINI_MODELS = "gemini-3.5-flash-lite,gemini-3-flash-preview,gemini-3.1-flash-lite"
_FALSE = ("0", "false", "no", "off")


class SettingsError(RuntimeError):
    """Raised when required configuration is missing. The message never contains values."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    # LLM
    gemini_api_key: SecretStr | None = None
    gemini_model: str = DEFAULT_GEMINI_MODELS
    gemini_timeout_s: float = 20.0
    bedrock_model_id: str | None = None
    aws_region: str = "us-east-1"
    llm_review_enabled: bool = True

    lookup_rate: str = "5/minute"

    # Agent run settings
    agent_timeout_s: float = 30.0
    agent_retries: int = 1

    # Persistence
    database_url: str = "sqlite:///./claims_fraud.db"

    # Auth. JWT_SECRET is required at startup: every internal route is role-protected.
    jwt_secret: SecretStr | None = None
    login_rate: str = "10/minute"
    jwt_ttl_minutes: int = 30

    # Local-login seed passwords (never hardcoded). Per-role value wins over the shared one; the
    # explicit DEV_SEED_DEFAULT_PASSWORDS flag enables clearly-dev per-user defaults.
    seed_user_password: SecretStr | None = None
    seed_password_investigator: SecretStr | None = None
    seed_password_ops_manager: SecretStr | None = None
    seed_password_fraud_team: SecretStr | None = None
    seed_password_admin: SecretStr | None = None
    dev_seed_default_passwords: bool = False

    # Adapter selections (local defaults)
    llm_adapter: str = "local"
    extraction_adapter: str = "local"
    storage_adapter: str = "local"
    queue_adapter: str = "local"
    hospital_adapter: str = "local"
    storage_dir: str = "storage"

    @model_validator(mode="before")
    @classmethod
    def _blank_is_unset(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not (isinstance(v, str) and v.strip() == "")}
        return data

    def llm_enabled(self) -> bool:
        """Server-controlled LLM switch: off if LLM_REVIEW_ENABLED is false, else on only when
        a provider is configured."""
        if not self.llm_review_enabled:
            return False
        return bool(self.gemini_api_key or self.bedrock_model_id)


def get_settings() -> Settings:
    return Settings()


def validate_required(settings: Settings | None = None) -> Settings:
    """Raise SettingsError naming each missing required variable (never its value)."""
    s = settings or get_settings()
    missing = []
    if not (s.jwt_secret and s.jwt_secret.get_secret_value().strip()):
        missing.append("JWT_SECRET")
    if missing:
        raise SettingsError("Missing required environment variable(s): " + ", ".join(missing))
    return s
