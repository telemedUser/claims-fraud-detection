import pytest
from pydantic import ValidationError

from app.core.risk_config import dump_risk_config, load_risk_config, parse_risk_config


def test_default_yaml_loads():
    cfg = load_risk_config()
    assert cfg.version == "risk-2025.1"
    assert cfg.bands.review_at == 30 and cfg.bands.investigate_at == 60
    assert cfg.severity_points.high == 45
    assert cfg.status_multiplier.POTENTIAL_ANOMALY == 0.6
    assert cfg.scored_statuses == ("CONFIRMED_RULE_VIOLATION", "POTENTIAL_ANOMALY")


def test_round_trip():
    cfg = load_risk_config()
    assert parse_risk_config(dump_risk_config(cfg)) == cfg


@pytest.mark.parametrize(
    "review,investigate",
    [(0, 60), (-1, 60), (60, 60), (70, 60), (30, 101)],
)
def test_invalid_bands_rejected(review, investigate):
    cfg = load_risk_config()
    data = cfg.model_dump()
    data["bands"] = {"review_at": review, "investigate_at": investigate}
    with pytest.raises(ValidationError):
        type(cfg).model_validate(data)


def test_investigate_at_100_allowed():
    cfg = load_risk_config()
    data = cfg.model_dump()
    data["bands"] = {"review_at": 1, "investigate_at": 100}
    assert type(cfg).model_validate(data).bands.investigate_at == 100


def test_unscored_status_rejected():
    cfg = load_risk_config()
    data = cfg.model_dump()
    data["status_multiplier"]["NOT_CHECKED"] = 1.0
    with pytest.raises(ValidationError):
        type(cfg).model_validate(data)
