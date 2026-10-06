"""Write results.json and CSV exports."""
import csv
import io
import json
from pathlib import Path

from engine.tiers import TIER_LABEL

HISTORY_COLUMNS = [
    ("revenue", "Revenue"),
    ("operating_income", "Operating income"),
    ("pretax_income", "Pre-tax income"),
    ("income_tax", "Income tax"),
    ("net_income", "Net income"),
    ("eps_diluted", "EPS (diluted, split-adjusted)"),
    ("shares_diluted", "Diluted shares (split-adjusted)"),
    ("equity", "Shareholders' equity"),
    ("bvps", "Book value per share"),
    ("total_debt", "Long-term debt"),
    ("operating_cash_flow", "Operating cash flow"),
    ("capex", "Capital expenditures"),
    ("fcf", "Free cash flow"),
    ("dep_amort", "Depreciation & amortization"),
    ("change_ar", "Change in accounts receivable"),
    ("change_ap", "Change in accounts payable"),
    ("roic", "ROIC"),
    ("pe", "P/E at fiscal year end"),
]


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _csv(rows):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def stock_csv(stock):
    h = stock["history"]
    rows = [["Year", "Fiscal year end"] + [label for _, label in HISTORY_COLUMNS]]
    for y in h["years"]:
        key = str(y)
        row = [y, h["fy_end"].get(key, "")]
        for field, _ in HISTORY_COLUMNS:
            v = h.get(field, {}).get(key)
            row.append("" if v is None else v)
        rows.append(row)
    return _csv(rows)


def watchlist_csv(stocks):
    rows = [["Symbol", "Company", "Status", "Price", "MOS price", "Sticker Price", "Price vs MOS",
             "Big Five score", "Debt payoff years", "Growth rate used", "Ten Cap price", "Payback Time price",
             "Stale", "Error"]]
    for s in stocks:
        val, bf = s.get("valuation") or {}, s.get("big_five") or {}
        debt = bf.get("debt") or {}
        cell = lambda v: "" if v is None else v
        rows.append([s["symbol"], s.get("name", ""), TIER_LABEL[s.get("tier", "not_yet")], cell(s.get("price")),
                     cell(val.get("mos_price")), cell(val.get("sticker_price")), cell(val.get("pct_from_mos")),
                     cell(bf.get("score")), cell(debt.get("payoff_years")), cell(val.get("growth_rate")),
                     cell(val.get("ten_cap_price")), cell(val.get("payback_price")),
                     "yes" if s.get("stale") else "", s.get("error") or ""])
    return _csv(rows)


def write_csvs(stocks, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.csv"):
        old.unlink()
    (out_dir / "watchlist.csv").write_text(watchlist_csv(stocks), encoding="utf-8")
    for s in stocks:
        if s.get("history"):
            (out_dir / f"{s['symbol']}.csv").write_text(stock_csv(s), encoding="utf-8")
