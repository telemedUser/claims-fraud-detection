"""Settings: defaults, blank-as-unset, and fail-fast naming of missing variables (Req 1.5-1.7)."""
import pytest
from hypothesis import given, settings as hsettings, strategies as st

from app.settings import Settings, SettingsError, get_settings, validate_required


def _clean(**kw):
    # _env_file=None isolates the test from a developer's real .env
    return Settings(_env_file=None, **kw)


def test_defaults_are_local():
    s = _clean()
    assert (s.llm_adapter, s.queue_adapter, s.storage_adapter) == ("local", "local", "local")
    assert s.database_url.startswith("sqlite")


def test_missing_jwt_secret_named_unconditionally(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(SettingsError) as e:
        validate_required(_clean())
    assert "JWT_SECRET" in str(e.value)


def test_blank_jwt_secret_counts_as_missing():
    with pytest.raises(SettingsError, match="JWT_SECRET"):
        validate_required(_clean(jwt_secret="  "))


@given(secret=st.text(min_size=8, alphabet=st.characters(min_codepoint=33, max_codepoint=126)))
@hsettings(max_examples=25)
def test_error_and_repr_never_leak_secret_value(secret):
    ok = _clean(jwt_secret=secret)
    assert validate_required(ok) is ok
    assert secret not in repr(ok) and secret not in str(ok)
    with pytest.raises(SettingsError) as e:
        validate_required(_clean(jwt_secret=None, seed_user_password=secret))
    assert secret not in str(e.value)


def test_get_settings_reads_current_environment(monkeypatch):
    monkeypatch.setenv("LOOKUP_RATE", "9/minute")
    assert get_settings().lookup_rate == "9/minute"
    monkeypatch.setenv("LOOKUP_RATE", "")
    assert get_settings().lookup_rate == "5/minute"


def test_llm_enabled_requires_provider_and_flag():
    assert not _clean().llm_enabled()
    assert _clean(gemini_api_key="k").llm_enabled()
    assert not _clean(gemini_api_key="k", llm_review_enabled=False).llm_enabled()
