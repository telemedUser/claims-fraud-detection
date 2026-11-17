import pytest

from app.core.risk_config import load_risk_config
from app.core.routing import SCORE_LABEL, route

BANDS = load_risk_config().bands


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "low"),
        (29.9, "low"),
        (30, "manual_review"),
        (59.9, "manual_review"),
        (60, "investigate"),
        (100, "investigate"),
    ],
)
def test_band_boundaries(value, expected):
    assert route(value, BANDS) == expected


def test_label_matches_config():
    assert load_risk_config().label == SCORE_LABEL
