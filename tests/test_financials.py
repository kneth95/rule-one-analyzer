import json
from pathlib import Path

import pytest

from engine.financials import NoFinancialsError, build_financials, fiscal_year_label
from tests.helpers import fact, facts_doc

FIXTURES = Path(__file__).parent / "fixtures" / "sec"


def annual(year, val, filed=None, end_md="12-31"):
    return fact(f"{year}-01-01" if end_md == "12-31" else f"{year - 1}-10-01",
                f"{year}-{end_md}", val, filed or f"{year + 1}-02-15")


def test_fiscal_year_label():
    assert fiscal_year_label("2025-09-27") == 2025
    assert fiscal_year_label("2024-12-31") == 2024
    assert fiscal_year_label("2025-02-01") == 2024   # retailer year ending early Feb
    assert fiscal_year_label("2026-06-30") == 2026


def test_excludes_quarterly_durations():
    doc = facts_doc({"Revenues": [
        fact("2024-01-01", "2024-12-31", 1000, "2025-02-15"),
        fact("2024-10-01", "2024-12-31", 300, "2025-02-15"),
    ]})
    fin = build_financials(doc, [])
    assert fin.series("revenue") == {2024: 1000}


def test_latest_filing_wins():
    doc = facts_doc({"Revenues": [
        fact("2023-01-01", "2023-12-31", 900, "2024-02-15"),
        fact("2023-01-01", "2023-12-31", 950, "2025-02-15"),
    ]})
    assert build_financials(doc, []).get("revenue", 2023) == 950


def test_ignores_non_10k_forms():
    doc = facts_doc({"Revenues": [fact("2023-01-01", "2023-12-31", 900, "2024-02-15", form="8-K")],
                     "NetIncomeLoss": [annual(2023, 10)]})
    assert build_financials(doc, []).series("revenue") == {}


def test_concept_fallback_per_year():
    doc = facts_doc({
        "SalesRevenueNet": [annual(2016, 500)],
        "RevenueFromContractWithCustomerExcludingAssessedTax": [annual(2019, 700)],
    })
    fin = build_financials(doc, [])
    assert fin.series("revenue") == {2016: 500, 2019: 700}
    assert fin.years == [2016, 2019]


def test_split_adjusts_eps_filed_before_split():
    doc = facts_doc(
        {"EarningsPerShareDiluted": [annual(2015, 9.22, "2016-02-15"), annual(2021, 5.61, "2022-02-15")],
         "WeightedAverageNumberOfDilutedSharesOutstanding": [annual(2015, 100, "2016-02-15")],
         "NetIncomeLoss": [annual(2015, 1), annual(2021, 1)]},
        units={"EarningsPerShareDiluted": "USD/shares", "WeightedAverageNumberOfDilutedSharesOutstanding": "shares"},
    )
    fin = build_financials(doc, [("2020-08-31", 4.0)])
    assert fin.get("eps_diluted", 2015) == pytest.approx(2.305)
    assert fin.get("eps_diluted", 2021) == pytest.approx(5.61)
    assert fin.get("shares_diluted", 2015) == pytest.approx(400)


def test_instant_values_match_fiscal_year_ends():
    doc = facts_doc({
        "NetIncomeLoss": [fact("2023-10-01", "2024-09-28", 10, "2024-11-01")],
        "StockholdersEquity": [fact(None, "2024-09-28", 500, "2024-11-01"),
                               fact(None, "2024-03-30", 999, "2024-11-01")],
    })
    fin = build_financials(doc, [])
    assert fin.series("equity") == {2024: 500}


def test_derived_fields():
    doc = facts_doc({
        "NetIncomeLoss": [annual(2024, 80)],
        "OperatingIncomeLoss": [annual(2024, 120)],
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": [annual(2024, 100)],
        "IncomeTaxExpenseBenefit": [annual(2024, 20)],
        "StockholdersEquity": [fact(None, "2024-12-31", 400, "2025-02-15")],
        "LongTermDebtNoncurrent": [fact(None, "2024-12-31", 90, "2025-02-15")],
        "LongTermDebtCurrent": [fact(None, "2024-12-31", 10, "2025-02-15")],
        "NetCashProvidedByUsedInOperatingActivities": [annual(2024, 150)],
        "PaymentsToAcquirePropertyPlantAndEquipment": [annual(2024, 30)],
        "WeightedAverageNumberOfDilutedSharesOutstanding": [annual(2024, 40)],
    }, units={"WeightedAverageNumberOfDilutedSharesOutstanding": "shares"})
    fin = build_financials(doc, [])
    assert fin.get("total_debt", 2024) == 100
    assert fin.get("fcf", 2024) == 120
    assert fin.get("bvps", 2024) == 10
    # ROIC = 120 * (1 - 20/100) / (400 + 100)
    assert fin.get("roic", 2024) == pytest.approx(0.192)


def test_total_debt_prefers_long_term_debt_total():
    doc = facts_doc({
        "NetIncomeLoss": [annual(2024, 1)],
        "LongTermDebt": [fact(None, "2024-12-31", 77, "2025-02-15")],
        "LongTermDebtNoncurrent": [fact(None, "2024-12-31", 50, "2025-02-15")],
    })
    assert build_financials(doc, []).get("total_debt", 2024) == 77


def test_missing_debt_is_zero_with_warning():
    doc = facts_doc({"NetIncomeLoss": [annual(2024, 1)]})
    fin = build_financials(doc, [])
    assert fin.get("total_debt", 2024) == 0
    assert any("debt" in w for w in fin.warnings)


def test_no_annual_data_raises():
    with pytest.raises(NoFinancialsError):
        build_financials(facts_doc({}), [])


def load(symbol):
    return json.loads((FIXTURES / f"{symbol}.json").read_text(encoding="utf-8"))


AAPL_SPLITS = [("1987-06-16", 2.0), ("2000-06-21", 2.0), ("2005-02-28", 2.0),
               ("2014-06-09", 7.0), ("2020-08-31", 4.0)]


def test_aapl_fixture():
    fin = build_financials(load("AAPL"), AAPL_SPLITS)
    assert fin.name == "Apple Inc."
    assert fin.get("revenue", 2015) == 233715000000
    assert fin.get("revenue", 2025) == 416161000000
    assert fin.get("eps_diluted", 2015) == pytest.approx(2.305)
    assert fin.get("eps_diluted", 2025) == pytest.approx(7.46)
    assert fin.get("total_debt", 2025) == 90678000000
    assert fin.get("total_debt", 2015) == 53329000000 + 2500000000
    assert fin.fy_end[2025] == "2025-09-27"
    assert all(fin.get(f, 2025) is not None for f in ("roic", "fcf", "bvps"))


def test_msft_fixture_june_year_end():
    fin = build_financials(load("MSFT"), [])
    assert fin.fy_end[2026] == "2026-06-30"
    assert fin.get("revenue", 2026) == 331839000000


def test_cost_fixture_53_week_years():
    fin = build_financials(load("COST"), [])
    assert fin.fy_end[2017] == "2017-09-03"
    assert fin.get("equity", 2017) == 10778000000
