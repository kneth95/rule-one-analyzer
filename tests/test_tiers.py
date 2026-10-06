from engine.config import DEFAULT_SETTINGS
from engine.tiers import assign_tier


def test_buy_zone():
    tier, reason = assign_tier(9.0, 10.0, 4, DEFAULT_SETTINGS)
    assert tier == "buy" and reason.startswith("Buy zone")


def test_getting_close_within_margin():
    tier, reason = assign_tier(10.9, 10.0, 5, DEFAULT_SETTINGS)
    assert tier == "close" and "9.0%" in reason


def test_not_yet_when_price_too_high():
    assert assign_tier(11.5, 10.0, 5, DEFAULT_SETTINGS)[0] == "not_yet"


def test_not_yet_when_score_too_low():
    tier, reason = assign_tier(5.0, 10.0, 3, DEFAULT_SETTINGS)
    assert tier == "not_yet" and "3 of 5" in reason


def test_not_yet_without_mos():
    tier, reason = assign_tier(5.0, None, 5, DEFAULT_SETTINGS)
    assert tier == "not_yet" and "couldn't be calculated" in reason
