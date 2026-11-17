"""Deprecated shim. Configuration lives in app.settings; this module only delegates to it."""
from app.settings import get_settings


def load_env() -> None:
    """No-op: app.settings reads .env itself."""


def llm_review_enabled() -> bool:
    return get_settings().llm_enabled()
