import pytest

from engine.config import DEFAULT_SETTINGS
from engine.market import MarketData
from engine.valuation import analyze_valuation, choose_growth, historical_pe
from tests.helpers import make_fin


def test_choose_growth_takes_lower():
    g, source, warnings = choose_growth(0.12, 0.09, None, 0.15)
    assert g == 0.09 and source == "analyst estimate" and warnings == []


def test_choose_growth_caps():
    g, source, _ = choose_growth(0.30, 0.25, None, 0.15)
    assert g == 0.15 and "capped" in source


def test_choose_growth_missing_analyst_warns():
    g, source, warnings = choose_growth(0.12, None, None, 0.15)
    assert g == 0.12 and source == "historical equity growth"
    assert "analyst" in warnings[0]


def test_choose_growth_override_wins_uncapped():
    g, source, _ = choose_growth(0.12, 0.10, 0.20, 0.15)
    assert g == 0.20 and source == "your override"


def test_choose_growth_none_available():
    g, source, warnings = choose_growth(None, None, None, 0.15)
    assert g is None and warnings


def test_historical_pe_uses_fiscal_year_end_month():
    fin = make_fin({"eps_diluted": {2023: 2.0, 2024: -1.0}})
    pe = historical_pe(fin, {"2023-12": 40.0, "2024-12": 50.0})
    assert pe == {2023: 20.0}


def market(price=10.0, growth=None, closes=None):
    return MarketData(price=price, analyst_growth=growth, splits=[], monthly_closes=closes or {})


def big_five(equity_10y):
    return {"metrics": {"equity": {"windows": {"10": {"value": equity_10y}, "5": {"value": None},
                                               "3": {"value": None}, "1": {"value": None}}}}}


def base_fin(eps=2.0):
    return make_fin({
        "eps_diluted": {2024: eps},
        "shares_diluted": {2024: 100.0},
        "net_income": {2024: 200.0}, "dep_amort": {2024: 50.0}, "income_tax": {2024: 40.0},
        "change_ap": {2024: 10.0}, "change_ar": {2024: 20.0}, "capex": {2024: 60.0},
        "fcf": {2024: 100.0},
    })


def test_sticker_price_walkthrough():
    v = analyze_valuation(base_fin(), market(price=10.0), big_five(0.10), None, DEFAULT_SETTINGS)
    assert v["computable"] is True
    assert v["future_eps"] == pytest.approx(5.1874849202)
    assert v["pe_from_growth"] == pytest.approx(20.0)
    assert v["future_pe"] == pytest.approx(20.0)  # no historical P/E -> 2x growth
    assert v["future_price"] == pytest.approx(103.749698404)
    assert v["sticker_price"] == pytest.approx(25.6453387102)
    assert v["mos_price"] == pytest.approx(12.8226693551)
    assert v["pct_from_mos"] == pytest.approx(10.0 / 12.8226693551 - 1)
    assert any("historical P/E" in w for w in v["warnings"])


def test_future_pe_uses_lower_historical_and_cap():
    closes = {"2024-12": 30.0}  # P/E 15 on EPS 2.0
    v = analyze_valuation(base_fin(), market(closes=closes), big_five(0.10), None, DEFAULT_SETTINGS)
    assert v["historical_pe_avg"] == pytest.approx(15.0)
    assert v["future_pe"] == pytest.approx(15.0)
    v2 = analyze_valuation(base_fin(), market(), big_five(0.10), None, {**DEFAULT_SETTINGS, "pe_cap": 12})
    assert v2["future_pe"] == pytest.approx(12.0)


def test_negative_eps_not_computable():
    v = analyze_valuation(base_fin(eps=-1.0), market(), big_five(0.10), None, DEFAULT_SETTINGS)
    assert v["computable"] is False
    assert v["sticker_price"] is None and v["mos_price"] is None
    assert any("EPS" in w for w in v["warnings"])


def test_ten_cap_and_payback():
    v = analyze_valuation(base_fin(), market(), big_five(0.10), None, DEFAULT_SETTINGS)
    # owner earnings = 200 + 50 + 40 + 10 - 20 - 0.5*60 = 250 -> 2.5/share
    assert v["owner_earnings_ps"] == pytest.approx(2.5)
    assert v["ten_cap_price"] == pytest.approx(25.0)
    # FCF/share 1.0 growing 10% for 8 years
    assert v["fcf_ps"] == pytest.approx(1.0)
    assert v["payback_price"] == pytest.approx(12.57947691)
