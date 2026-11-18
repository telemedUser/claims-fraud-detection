"""Server-side LLM analysis switch, changed by an Administrator in the internal console.

Requirement 8.2: whether the LLM is used comes from server configuration, never from a claim submission.
The switch is that configuration: it is stored in ``app_settings``, every change is audited, and each
claim job reads it when the claim is submitted.

Effective state = a provider key is configured AND (the stored switch, or ``LLM_REVIEW_ENABLED`` when the
switch has never been set).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db import audit
from app.db import models as m
from app.db.session import get_session
from app.settings import get_settings

LLM_SWITCH = "llm_analysis_enabled"


def _provider_configured() -> bool:
    s = get_settings()
    return bool(s.gemini_api_key or s.bedrock_model_id)


def llm_switch() -> dict:
    """The stored switch and whether it can take effect."""
    s = get_settings()
    with get_session() as session:
        row = session.get(m.AppSetting, LLM_SWITCH)
        stored = None if row is None else bool(row.value)
        updated_by = row.updated_by if row else None
        updated_at = row.updated_at.isoformat() if row and row.updated_at else None
    requested = s.llm_review_enabled if stored is None else stored
    configured = _provider_configured()
    provider = "Google Gemini" if s.gemini_api_key else ("Amazon Bedrock" if s.bedrock_model_id else None)
    return {"requested": requested, "provider_configured": configured, "effective": requested and configured,
            "provider": provider, "source": "default" if stored is None else "console",
            "updated_by": updated_by, "updated_at": updated_at}


def llm_effective() -> bool:
    """True when the next submitted claim should use the LLM."""
    return llm_switch()["effective"]


def set_llm_switch(enabled: bool, actor_id: str) -> dict:
    """Store the switch and audit the change (old and new value as 0/1, no personal data)."""
    with get_session() as session:
        row = session.get(m.AppSetting, LLM_SWITCH)
        old = None if row is None else bool(row.value)
        if row is None:
            row = m.AppSetting(key=LLM_SWITCH)
            session.add(row)
        row.value = bool(enabled)
        row.updated_by = str(actor_id)[:64]
        row.updated_at = datetime.now(timezone.utc)
        session.flush()
        audit.log_config_change(session, str(actor_id), LLM_SWITCH,
                                old_version=None if old is None else int(old), new_version=int(bool(enabled)))
    return llm_switch()
