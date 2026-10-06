import pytest

from engine.bigfive import analyze_big_five, cagr, growth_window, longest_value, roic_window
from engine.config import DEFAULT_SETTINGS
from tests.helpers import make_fin

YEARS = range(2015, 2026)  # 11 data points -> full 10-year windows


def grow(rate, start=100.0):
    return {y: start * (1 + rate) ** (y - 2015) for y in YEARS}


def healthy(rate=0.12, roic=0.20):
    return {
        "roic": {y: roic for y in YEARS},
        "revenue": grow(rate),
        "eps_diluted": grow(rate, 1.0),
        "bvps": grow(rate, 10.0),
        "fcf": grow(rate, 50.0),
        "total_debt": {y: 100.0 for y in YEARS},
    }


def test_cagr():
    assert cagr(100, 200, 10) == pytest.approx(0.0717735, rel=1e-5)
    assert cagr(-5, 200, 10) is None
    assert cagr(100, -1, 10) is None
    assert cagr(None, 200, 10) is None


def test_growth_window_shifts_start_past_negative_value():
    series = {2015: -5.0, 2016: 100.0, 2025: 259.37424601}
    w = growth_window(series, 2025, 2015, 10)
    assert w["available"] is True
    assert w["start_year"] == 2016
    assert w["value"] == pytest.approx(0.1117109, rel=1e-5)
    assert "2016" in w["note"]


def test_growth_window_unavailable_when_history_too_short():
    w = growth_window({2020: 1.0, 2025: 2.0}, 2025, 2020, 10)
    assert w["available"] is False


def test_growth_window_na_when_latest_negative():
    w = growth_window({2015: 1.0, 2025: -2.0}, 2025, 2015, 10)
    assert w["available"] is True and w["value"] is None


def test_roic_window_averages_last_n_years():
    series = {2023: 0.10, 2024: 0.20, 2025: 0.30}
    assert roic_window(series, 2025, 2023, 3)["value"] == pytest.approx(0.20)
    assert roic_window(series, 2025, 2023, 5)["available"] is False


def test_healthy_company_scores_five():
    result = analyze_big_five(make_fin(healthy()), DEFAULT_SETTINGS)
    assert result["score"] == 5
    assert result["metrics"]["sales"]["windows"]["10"]["value"] == pytest.approx(0.12)
    assert result["metrics"]["sales"]["windows"]["10"]["pass"] is True
    assert result["warnings"] == []


def test_slow_growth_fails():
    series = healthy()
    series["revenue"] = grow(0.05)
    result = analyze_big_five(make_fin(series), DEFAULT_SETTINGS)
    assert result["metrics"]["sales"]["pass"] is False
    assert result["score"] == 4


def test_three_of_four_windows_is_enough():
    series = healthy(rate=0.20)
    series["revenue"][2025] = series["revenue"][2024]  # 1-year growth 0%, 3/5/10-year windows still >= 10%
    m = analyze_big_five(make_fin(series), {**DEFAULT_SETTINGS, "trend_tolerance": 0.5})["metrics"]["sales"]
    assert m["windows"]["1"]["pass"] is False
    assert m["passes"] == 3
    assert m["pass"] is True


def test_collapsing_trend_fails():
    series = healthy(rate=0.20)
    series["revenue"][2025] = series["revenue"][2024] * 1.05  # 1-year 5% vs 10-year ~19%
    m = analyze_big_five(make_fin(series), DEFAULT_SETTINGS)["metrics"]["sales"]
    assert m["passes"] == 3
    assert m["trend_ok"] is False
    assert m["pass"] is False


def test_short_history_warns_and_uses_available_windows():
    series = {k: {y: v for y, v in s.items() if y >= 2020} for k, s in healthy().items()}
    result = analyze_big_five(make_fin(series), DEFAULT_SETTINGS)
    m = result["metrics"]["sales"]
    assert m["windows"]["10"]["available"] is False
    assert m["required"] == 3
    assert m["pass"] is True
    assert any("6 years" in w for w in result["warnings"])


def test_debt_check():
    fin = make_fin({**healthy(), "total_debt": {2025: 300.0}, "fcf": {2025: 100.0}})
    debt = analyze_big_five(fin, DEFAULT_SETTINGS)["debt"]
    assert debt["payoff_years"] == pytest.approx(3.0)
    assert debt["pass"] is True


def test_debt_fails_with_negative_fcf():
    fin = make_fin({**healthy(), "fcf": {2025: -10.0}})
    debt = analyze_big_five(fin, DEFAULT_SETTINGS)["debt"]
    assert debt["pass"] is False and debt["payoff_years"] is None


def test_no_debt_passes():
    fin = make_fin({**healthy(), "total_debt": {2025: 0.0}})
    assert analyze_big_five(fin, DEFAULT_SETTINGS)["debt"]["pass"] is True


def test_longest_value():
    assert longest_value({"10": {"value": None}, "5": {"value": 0.2}, "3": {"value": 0.1}, "1": {"value": 0.3}}) == 0.2
    assert longest_value({"10": {"value": None}, "5": {"value": None}, "3": {"value": None}, "1": {"value": 0.3}}) is None


def test_metric_needs_at_least_two_windows():
    series = {k: {y: v for y, v in s.items() if y >= 2024} for k, s in healthy(rate=0.30).items()}
    result = analyze_big_five(make_fin(series), DEFAULT_SETTINGS)
    assert result["metrics"]["sales"]["pass"] is False
    assert result["score"] == 0
    assert any("Not enough history" in w for w in result["warnings"])


def test_missing_latest_debt_fails_debt_check():
    fin = make_fin({**healthy(), "total_debt": {2024: 500.0, 2025: None}})
    debt = analyze_big_five(fin, DEFAULT_SETTINGS)["debt"]
    assert debt["pass"] is False and debt["total_debt"] is None
