"""Property tests for risk configuration round trip and validation."""
from __future__ import annotations

import pytest
from hypothesis import assume, given, settings, strategies as st
from pydantic import ValidationError

from app.core.risk_config import (
    DEFAULT_CONFIG_PATH,
    Bands,
    RiskConfig,
    dump_risk_config,
    load_risk_config,
    parse_risk_config,
)

nonneg = st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)
pos = st.floats(min_value=0.001, max_value=1000, allow_nan=False, allow_infinity=False)
band_value = st.floats(min_value=-50, max_value=150, allow_nan=False, allow_infinity=False)


@st.composite
def valid_bands(draw):
    review = draw(st.floats(min_value=0.01, max_value=99.9, allow_nan=False))
    investigate = draw(st.floats(min_value=review, max_value=100, allow_nan=False))
    assume(review < investigate)
    return {"review_at": review, "investigate_at": investigate}


@st.composite
def valid_configs(draw):
    data = {
        "version": draw(st.text(min_size=1, max_size=20).filter(lambda s: s.strip() == s and s)),
        "label": draw(st.text(max_size=30)),
        "severity_points": {k: draw(nonneg) for k in ("low", "medium", "high")},
        "status_multiplier": {
            k: draw(nonneg) for k in ("CONFIRMED_RULE_VIOLATION", "POTENTIAL_ANOMALY")
        },
        "bands": draw(valid_bands()),
        "thresholds": {
            "policy_purchase_gap_days": draw(st.integers(min_value=0, max_value=3650)),
            "preauth_overrun_pct": draw(nonneg),
            "invoice_total_tolerance": draw(nonneg),
            "doc_modification_gap_hours": {
                k: draw(pos) for k in ("invoice", "discharge_summary", "default")
            },
            "provider_volume_multiple": draw(pos),
        },
        "gst_exempt_categories": draw(st.lists(st.text(min_size=1, max_size=15), max_size=5)),
    }
    return RiskConfig.model_validate(data)


# Feature: claims-fraud-detection-service, Property 6: Risk configuration round trip and validation
# **Validates: Requirements 5.1, 5.6, 5.7**
@settings(max_examples=100)
@given(valid_configs())
def test_risk_config_round_trip(config):
    assert parse_risk_config(dump_risk_config(config)) == config


def test_risk_config_round_trip_control_chars():
    """Regression: NEL and other non-printable characters must survive a YAML round trip."""
    config = load_risk_config(DEFAULT_CONFIG_PATH).model_copy(
        update={"label": "\x85\u2028\x00\ttab", "gst_exempt_categories": ["\x85", "é"]}
    )
    assert parse_risk_config(dump_risk_config(config)) == config


# Feature: claims-fraud-detection-service, Property 6: Risk configuration round trip and validation
# **Validates: Requirements 5.1, 5.6, 5.7**
@settings(max_examples=100)
@given(band_value, band_value)
def test_bands_accepted_iff_ordered_within_range(review_at, investigate_at):
    expected = 0 < review_at < investigate_at <= 100
    try:
        Bands(review_at=review_at, investigate_at=investigate_at)
        accepted = True
    except ValidationError:
        accepted = False
    assert accepted == expected


# Feature: claims-fraud-detection-service, Property 6: Risk configuration round trip and validation
# **Validates: Requirements 5.1, 5.6, 5.7**
def test_shipped_config_round_trips():
    config = load_risk_config(DEFAULT_CONFIG_PATH)
    assert parse_risk_config(dump_risk_config(config)) == config


def test_non_mapping_yaml_rejected():
    with pytest.raises(ValueError):
        parse_risk_config("- a\n- b\n")
