"""Turn SEC XBRL company facts into clean, split-adjusted yearly series."""
from dataclasses import dataclass
from datetime import date, timedelta

# Ordered fallbacks: for each year the first concept that has a value wins.
CONCEPTS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
    ],
    "operating_income": ["OperatingIncomeLoss"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "income_tax": ["IncomeTaxExpenseBenefit"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps_diluted": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
    "shares_diluted": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
    ],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "lt_debt_total": ["LongTermDebt"],
    "lt_debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "lt_debt_current": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "dep_amort": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "Depreciation",
    ],
    "change_ar": ["IncreaseDecreaseInAccountsReceivable"],
    "change_ap": ["IncreaseDecreaseInAccountsPayable", "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities"],
}
INSTANT_FIELDS = {"equity", "lt_debt_total", "lt_debt_noncurrent", "lt_debt_current"}
DEFAULT_TAX_RATE = 0.21


class NoFinancialsError(Exception):
    pass


@dataclass
class Financials:
    name: str
    years: list
    fy_end: dict
    data: dict
    warnings: list

    def series(self, field):
        return self.data.get(field, {})

    def get(self, field, year):
        return self.data.get(field, {}).get(year)

    @property
    def latest_year(self):
        return self.years[-1] if self.years else None


def fiscal_year_label(end_iso):
    """Label a fiscal year by the calendar year holding most of it."""
    return (date.fromisoformat(end_iso) - timedelta(days=180)).year


def _rows(gaap, concept):
    node = gaap.get(concept)
    if not node:
        return
    for rows in node.get("units", {}).values():
        for row in rows:
            if str(row.get("form", "")).startswith("10-K") and "end" in row and "val" in row:
                yield row


def _annual_durations(gaap, concept):
    """year -> (value, end, filed) for ~1-year periods; latest end, then latest filing wins."""
    best = {}
    for row in _rows(gaap, concept):
        start = row.get("start")
        if not start:
            continue
        days = (date.fromisoformat(row["end"]) - date.fromisoformat(start)).days
        if not 350 <= days <= 380:
            continue
        year = fiscal_year_label(row["end"])
        key = (row["end"], row.get("filed", ""))
        if year not in best or key > best[year][1:]:
            best[year] = (row["val"], row["end"], row.get("filed", ""))
    return best


def _instants(gaap, concept, end_to_year):
    best = {}
    for row in _rows(gaap, concept):
        if row.get("start") or row["end"] not in end_to_year:
            continue
        year = end_to_year[row["end"]]
        filed = row.get("filed", "")
        if year not in best or filed > best[year][2]:
            best[year] = (row["val"], row["end"], filed)
    return best


def _split_factor(filed, splits):
    factor = 1.0
    for split_date, ratio in splits:
        if split_date > filed and ratio > 0:
            factor *= ratio
    return factor


def build_financials(facts, splits):
    gaap = facts.get("facts", {}).get("us-gaap", {})
    raw = {}  # field -> year -> (value, end, filed)
    fy_end = {}
    for field, concepts in CONCEPTS.items():
        if field in INSTANT_FIELDS:
            continue
        merged = {}
        for concept in concepts:
            for year, item in _annual_durations(gaap, concept).items():
                merged.setdefault(year, item)
        raw[field] = merged
        for year, (_, end, _) in merged.items():
            if year not in fy_end or end > fy_end[year]:
                fy_end[year] = end

    years = sorted(set(raw["revenue"]) | set(raw["net_income"]))
    if not years:
        raise NoFinancialsError("No annual 10-K financial data found in SEC filings")
    fy_end = {y: fy_end[y] for y in years}
    end_to_year = {end: y for y, end in fy_end.items()}

    for field in INSTANT_FIELDS:
        merged = {}
        for concept in CONCEPTS[field]:
            for year, item in _instants(gaap, concept, end_to_year).items():
                merged.setdefault(year, item)
        raw[field] = merged

    data = {}
    for field, items in raw.items():
        values = {}
        for year, (val, _, filed) in items.items():
            if year not in fy_end:
                continue
            if field == "eps_diluted":
                val = val / _split_factor(filed, splits)
            elif field == "shares_diluted":
                val = val * _split_factor(filed, splits)
            values[year] = float(val)
        data[field] = values

    warnings = []
    _derive(data, years, warnings)
    return Financials(name=facts.get("entityName", ""), years=years, fy_end=fy_end, data=data, warnings=warnings)


def _derive(data, years, warnings):
    total_debt, fcf, bvps, roic = {}, {}, {}, {}
    any_debt = False
    default_tax_used = False
    for y in years:
        g = lambda f: data.get(f, {}).get(y)
        if g("lt_debt_total") is not None:
            total_debt[y] = g("lt_debt_total")
            any_debt = True
        elif g("lt_debt_noncurrent") is not None:
            total_debt[y] = g("lt_debt_noncurrent") + (g("lt_debt_current") or 0.0)
            any_debt = True
        elif any_debt and y == years[-1]:
            total_debt[y] = None
            warnings.append(f"No long-term debt figure found for {y} although earlier years had debt; "
                            f"{y} debt is treated as unknown and the debt check fails.")
        else:
            total_debt[y] = 0.0

        if g("operating_cash_flow") is not None and g("capex") is not None:
            fcf[y] = g("operating_cash_flow") - g("capex")

        if g("equity") is not None and g("shares_diluted"):
            bvps[y] = g("equity") / g("shares_diluted")

        op, eq = g("operating_income"), g("equity")
        if op is not None and eq is not None and total_debt[y] is not None:
            pretax, tax = g("pretax_income"), g("income_tax")
            if pretax and pretax > 0 and tax is not None:
                rate = min(max(tax / pretax, 0.0), 0.5)
            else:
                rate = DEFAULT_TAX_RATE
                default_tax_used = True
            invested = eq + total_debt[y]
            if invested > 0:
                roic[y] = op * (1 - rate) / invested

    data["total_debt"], data["fcf"], data["bvps"], data["roic"] = total_debt, fcf, bvps, roic
    if not any_debt:
        warnings.append("No long-term debt found in the filings, so debt is treated as zero.")
    if default_tax_used:
        warnings.append("Some years had no usable tax rate; ROIC used a 21% tax rate for those years.")
