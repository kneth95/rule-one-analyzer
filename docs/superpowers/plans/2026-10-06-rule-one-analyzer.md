# Rule #1 Analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub-hosted tool that analyzes a watchlist of US stocks with Phil Town's Rule #1 method, emails tier-change alerts, and publishes a plain-HTML dashboard with explanations and copyable data.

**Architecture:** A Python package (`engine/`) fetches SEC EDGAR XBRL facts and Yahoo Finance prices, builds clean split-adjusted yearly series, computes the Big Five, valuation and tiers, writes `data/results.json` + CSVs, and emails on tier upgrades. A GitHub Actions workflow runs it daily/on demand, commits `data/`, and deploys `site/` (static HTML/JS ES modules, no build step) with `data/` copied in to GitHub Pages.

**Tech Stack:** Python 3.12 (CI) / 3.14 (local), `requests`, `yfinance`, `pytest`; vanilla HTML/CSS/JS ES modules, Chart.js 4.4.1 from cdnjs; Node 22 `node --test` for JS pure functions; GitHub Actions + Pages.

**Spec:** `docs/superpowers/specs/2026-10-06-rule-one-analyzer-design.md`

## Global Constraints

- US stocks only; data from SEC EDGAR (`companyfacts` XBRL API) and Yahoo Finance via `yfinance`.
- No LLM/API usage, no Telegram. Notifications by Gmail SMTP (`smtp.gmail.com:465`) with an app password.
- SEC requests send the `SEC_USER_AGENT` header and stay under 10 requests/second.
- Secrets come only from env vars: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `ALERT_EMAIL_TO`, `SEC_USER_AGENT`. Nothing secret is committed.
- Default settings (verbatim): `marr 0.15, mos_fraction 0.5, growth_cap 0.15, pe_cap 50, big_five_threshold 0.10, big_five_min_score 4, windows_to_pass 3, trend_tolerance 0.10, debt_payoff_max_years 3, getting_close_margin 0.10, payback_years 8`.
- Tiers: `buy` = price ≤ MOS and score ≥ 4; `close` = price ≤ MOS × 1.10 and score ≥ 4; `not_yet` otherwise.
- Email only when a stock moves *up* a tier; stale or errored stocks never alert; alert state updates only after a successful send.
- Dashboard: no build step; every term has an ⓘ explanation; copy-as-table (TSV), copy-for-AI (Markdown), CSV downloads; owner edits through a fine-grained GitHub token kept in localStorage.
- Tests never touch the network.
- Workflow schedule: `0 22 * * 1-5` (UTC), plus `workflow_dispatch` and push to `watchlist.json`/`settings.json`.

## Review Focus

1. **Stock splits** — SEC reports EPS and share counts as filed, so a 10-year EPS series spans splits (AAPL 2015 EPS 9.22 is 2.305 in today's shares). Expected: per-share values split-adjusted using filing date vs split date. Test: `test_split_adjusts_eps_filed_before_split` + AAPL fixture test (Task 3).
2. **Mixed XBRL concepts across years** — a company switches from `SalesRevenueNet` to `RevenueFromContractWithCustomerExcludingAssessedTax`. Expected: one continuous revenue series. Test: `test_concept_fallback_per_year` + AAPL fixture (Task 3).
3. **Quarterly rows inside 10-K filings and restatements** — 10-Ks include Q4 durations and repeat prior years. Expected: only ~1-year durations, latest filing wins. Tests: `test_excludes_quarterly_durations`, `test_latest_filing_wins` (Task 3).
4. **Data source outage for one ticker** — Yahoo/SEC down. Expected: previous results kept and marked stale, no alert, other tickers continue. Test: `test_run_marks_stale_on_fetch_error` (Task 9).
5. **Email failure** — Gmail rejects the login. Expected: results still written, run exits non-zero, alert state unchanged so the alert retries. Test: `test_run_keeps_state_when_email_fails` (Task 9).

---

## File Structure

```
requirements.txt, pyproject.toml, .gitignore, README.md
watchlist.json, settings.json
engine/__init__.py
engine/config.py        settings + watchlist loading/validation
engine/retry.py         with_retries(), FetchError
engine/sec.py           SecClient (ticker→CIK, company facts)
engine/market.py        MarketData, fetch_market() via yfinance
engine/financials.py    Financials, build_financials(), fiscal_year_label()
engine/bigfive.py       cagr(), growth_window(), analyze_big_five()
engine/valuation.py     choose_growth(), historical_pe(), analyze_valuation()
engine/tiers.py         TIER_RANK, assign_tier()
engine/alerts.py        detect_changes(), compose_email(), send_email(), email_config_from_env()
engine/output.py        HISTORY_COLUMNS, read_json(), write_json(), stock_csv(), watchlist_csv(), write_csvs()
engine/main.py          analyze_ticker(), run(), CLI
scripts/record_fixture.py
tests/helpers.py, tests/test_*.py, tests/fixtures/sec/{AAPL,MSFT,COST}.json
tests/js/format.test.mjs
site/index.html, stock.html, guide.html, settings.html
site/css/style.css
site/js/format.js, glossary.js, github.js, common.js, index.js, stock.js, settings.js
.github/workflows/analyze.yml
data/   (generated: results.json, alert_state.json, csv/)
```

---

### Task 1: Project scaffold and config loading

**Files:**
- Create: `requirements.txt`, `pyproject.toml`, `.gitignore`, `watchlist.json`, `settings.json`, `engine/__init__.py`, `engine/config.py`, `tests/__init__.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `DEFAULT_SETTINGS: dict`, `ConfigError(ValueError)`, `load_settings(path) -> dict`, `load_watchlist(path) -> list[dict]` (each `{"symbol","added","notes","growth_override"}`), `normalize_symbol(s) -> str`.

- [ ] **Step 1: Create scaffold files**

`requirements.txt`:
```
requests>=2.31
yfinance>=1.0
pytest>=8.0
```

`pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
.venv/
site/data/
```

`watchlist.json`:
```json
{
  "tickers": []
}
```

`settings.json`:
```json
{
  "marr": 0.15,
  "mos_fraction": 0.5,
  "growth_cap": 0.15,
  "pe_cap": 50,
  "big_five_threshold": 0.10,
  "big_five_min_score": 4,
  "windows_to_pass": 3,
  "trend_tolerance": 0.10,
  "debt_payoff_max_years": 3,
  "getting_close_margin": 0.10,
  "payback_years": 8
}
```

`engine/__init__.py` and `tests/__init__.py`: empty files.

Run: `python -m pip install -r requirements.txt`

- [ ] **Step 2: Write the failing tests** — `tests/test_config.py`

```python
import json

import pytest

from engine.config import DEFAULT_SETTINGS, ConfigError, load_settings, load_watchlist


def write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
    return p


def test_settings_defaults_fill_missing_keys(tmp_path):
    s = load_settings(write(tmp_path, "s.json", {"marr": 0.12}))
    assert s["marr"] == 0.12
    assert s["mos_fraction"] == DEFAULT_SETTINGS["mos_fraction"]


def test_settings_rejects_unknown_key(tmp_path):
    with pytest.raises(ConfigError, match="unknown keys: bogus"):
        load_settings(write(tmp_path, "s.json", {"bogus": 1}))


def test_settings_rejects_out_of_range(tmp_path):
    with pytest.raises(ConfigError, match="marr"):
        load_settings(write(tmp_path, "s.json", {"marr": 5}))


def test_settings_rejects_non_integer_score(tmp_path):
    with pytest.raises(ConfigError, match="whole number"):
        load_settings(write(tmp_path, "s.json", {"big_five_min_score": 3.5}))


def test_settings_rejects_bad_json(tmp_path):
    with pytest.raises(ConfigError, match="could not be read"):
        load_settings(write(tmp_path, "s.json", "{not json"))


def test_watchlist_normalizes_and_dedupes(tmp_path):
    p = write(tmp_path, "w.json", {"tickers": [
        {"symbol": " aapl "}, {"symbol": "BRK.B", "notes": "insurance"}, {"symbol": "AAPL"}]})
    w = load_watchlist(p)
    assert [t["symbol"] for t in w] == ["AAPL", "BRK-B"]
    assert w[1]["notes"] == "insurance"
    assert w[0]["growth_override"] is None


def test_watchlist_rejects_bad_symbol(tmp_path):
    with pytest.raises(ConfigError, match="symbol"):
        load_watchlist(write(tmp_path, "w.json", {"tickers": [{"symbol": "not a ticker!"}]}))


def test_watchlist_rejects_bad_override(tmp_path):
    with pytest.raises(ConfigError, match="growth_override"):
        load_watchlist(write(tmp_path, "w.json", {"tickers": [{"symbol": "KO", "growth_override": 3}]}))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.config'`

- [ ] **Step 4: Implement** — `engine/config.py`

```python
"""Loading and validating settings.json and watchlist.json."""
import json
import re
from pathlib import Path

DEFAULT_SETTINGS = {
    "marr": 0.15,
    "mos_fraction": 0.5,
    "growth_cap": 0.15,
    "pe_cap": 50,
    "big_five_threshold": 0.10,
    "big_five_min_score": 4,
    "windows_to_pass": 3,
    "trend_tolerance": 0.10,
    "debt_payoff_max_years": 3,
    "getting_close_margin": 0.10,
    "payback_years": 8,
}

_RANGES = {
    "marr": (0.01, 1.0),
    "mos_fraction": (0.05, 1.0),
    "growth_cap": (0.01, 1.0),
    "pe_cap": (1, 500),
    "big_five_threshold": (0.0, 1.0),
    "big_five_min_score": (0, 5),
    "windows_to_pass": (1, 4),
    "trend_tolerance": (0.0, 1.0),
    "debt_payoff_max_years": (0, 100),
    "getting_close_margin": (0.0, 1.0),
    "payback_years": (1, 30),
}
_INT_KEYS = {"big_five_min_score", "windows_to_pass", "payback_years"}
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9\-]{0,9}$")


class ConfigError(ValueError):
    pass


def _read(path: Path, label: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"{label} could not be read: {e}") from e


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load_settings(path) -> dict:
    raw = _read(path, "settings.json")
    if not isinstance(raw, dict):
        raise ConfigError("settings.json must be a JSON object")
    unknown = set(raw) - set(DEFAULT_SETTINGS)
    if unknown:
        raise ConfigError(f"settings.json has unknown keys: {', '.join(sorted(unknown))}")
    settings = {**DEFAULT_SETTINGS, **raw}
    for key, (lo, hi) in _RANGES.items():
        v = settings[key]
        if not _is_number(v):
            raise ConfigError(f"settings.{key} must be a number")
        if key in _INT_KEYS and int(v) != v:
            raise ConfigError(f"settings.{key} must be a whole number")
        if not lo <= v <= hi:
            raise ConfigError(f"settings.{key} must be between {lo} and {hi}, got {v}")
    return settings


def normalize_symbol(symbol: str) -> str:
    return str(symbol).strip().upper().replace(".", "-")


def load_watchlist(path) -> list[dict]:
    raw = _read(path, "watchlist.json")
    if not isinstance(raw, dict) or not isinstance(raw.get("tickers"), list):
        raise ConfigError('watchlist.json must look like {"tickers": [...]}')
    seen, out = set(), []
    for item in raw["tickers"]:
        if not isinstance(item, dict) or "symbol" not in item:
            raise ConfigError("each watchlist entry needs a symbol")
        symbol = normalize_symbol(item["symbol"])
        if not _SYMBOL_RE.match(symbol):
            raise ConfigError(f"watchlist symbol {item['symbol']!r} is not a valid ticker")
        override = item.get("growth_override")
        if override is not None and (not _is_number(override) or not 0 < override <= 1):
            raise ConfigError(f"{symbol}: growth_override must be a decimal between 0 and 1 (e.g. 0.12)")
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append({
            "symbol": symbol,
            "added": item.get("added", ""),
            "notes": item.get("notes", ""),
            "growth_override": override,
        })
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -q`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: project scaffold and settings/watchlist loading"
```

---

### Task 2: Retry helper and SEC client

**Files:**
- Create: `engine/retry.py`, `engine/sec.py`
- Test: `tests/test_sec.py`

**Interfaces:**
- Produces: `FetchError(Exception)`, `with_retries(fn, attempts=3, base_delay=1.0, sleep=time.sleep, retry_on=(Exception,))`; `NotFoundError(Exception)`, `SecClient(user_agent, session=None, min_interval=0.12, sleep=time.sleep, clock=time.monotonic)` with `.cik_for(symbol) -> str | None` and `.company_facts(cik) -> dict`. Network failures after retries raise `FetchError`; HTTP 404 raises `NotFoundError`.

- [ ] **Step 1: Write the failing tests** — `tests/test_sec.py`

```python
import pytest
import requests

from engine.retry import FetchError, with_retries
from engine.sec import NotFoundError, SecClient


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, routes):
        self.routes = routes  # url -> list of responses (or exceptions), consumed in order
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        item = self.routes[url].pop(0)
        if isinstance(item, Exception):
            raise item
        return item


TICKERS = "https://www.sec.gov/files/company_tickers.json"
TICKER_PAYLOAD = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
                  "1": {"cik_str": 1067983, "ticker": "BRK-B", "title": "Berkshire"}}


def client(routes):
    return SecClient("Test test@example.com", session=FakeSession(routes), sleep=lambda s: None)


def test_with_retries_retries_then_succeeds():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("boom")
        return "ok"

    assert with_retries(flaky, sleep=lambda s: None) == "ok"
    assert len(attempts) == 3


def test_requires_user_agent():
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        SecClient("")


def test_sets_user_agent_header():
    c = client({})
    assert c.session.headers["User-Agent"] == "Test test@example.com"


def test_cik_lookup_pads_and_normalizes():
    c = client({TICKERS: [FakeResponse(payload=TICKER_PAYLOAD)]})
    assert c.cik_for("aapl") == "0000320193"
    assert c.cik_for("BRK.B") == "0001067983"
    assert c.cik_for("ZZZZ") is None
    assert len(c.session.calls) == 1  # ticker map cached


def test_company_facts_404_raises_not_found():
    url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"
    c = client({url: [FakeResponse(status=404)]})
    with pytest.raises(NotFoundError):
        c.company_facts("0000000001")


def test_network_failure_becomes_fetch_error_after_retries():
    url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    c = client({url: [requests.ConnectionError("down")] * 3})
    with pytest.raises(FetchError, match="SEC"):
        c.company_facts("0000320193")
    assert len(c.session.calls) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sec.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.retry'`

- [ ] **Step 3: Implement** — `engine/retry.py`

```python
"""Retry helper and the error type for data that could not be downloaded."""
import time


class FetchError(Exception):
    """Raised when outside data (SEC, Yahoo) could not be downloaded."""


def with_retries(fn, attempts=3, base_delay=1.0, sleep=time.sleep, retry_on=(Exception,)):
    for i in range(attempts):
        try:
            return fn()
        except retry_on:
            if i == attempts - 1:
                raise
            sleep(base_delay * 2 ** i)
```

`engine/sec.py`:
```python
"""SEC EDGAR client: ticker -> CIK lookup and XBRL company facts."""
import time

import requests

from engine.config import normalize_symbol
from engine.retry import FetchError, with_retries

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


class NotFoundError(Exception):
    pass


class SecClient:
    def __init__(self, user_agent, session=None, min_interval=0.12, sleep=time.sleep, clock=time.monotonic):
        if not user_agent:
            raise ValueError("SEC_USER_AGENT is required, e.g. 'Your Name you@example.com'")
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self._min_interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self._last = None
        self._tickers = None

    def _throttle(self):
        if self._last is not None:
            wait = self._min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def _get_json(self, url):
        def do():
            self._throttle()
            r = self.session.get(url, timeout=30)
            if r.status_code == 404:
                raise NotFoundError(url)
            r.raise_for_status()
            return r.json()

        try:
            return with_retries(do, sleep=self._sleep, retry_on=(requests.RequestException,))
        except requests.RequestException as e:
            raise FetchError(f"SEC request failed: {e}") from e

    def cik_for(self, symbol):
        if self._tickers is None:
            data = self._get_json(TICKERS_URL)
            self._tickers = {
                normalize_symbol(row["ticker"]): str(row["cik_str"]).zfill(10) for row in data.values()
            }
        return self._tickers.get(normalize_symbol(symbol))

    def company_facts(self, cik):
        return self._get_json(FACTS_URL.format(cik=cik))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sec.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: SEC EDGAR client with retries and throttling"
```

---

### Task 3: Financials — clean yearly series from XBRL facts

**Files:**
- Create: `engine/financials.py`, `tests/helpers.py`, `scripts/record_fixture.py`, `tests/fixtures/sec/AAPL.json`, `tests/fixtures/sec/MSFT.json`, `tests/fixtures/sec/COST.json`
- Test: `tests/test_financials.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure).
- Produces:
  - `CONCEPTS: dict[str, list[str]]`
  - `fiscal_year_label(end_iso: str) -> int`
  - `class NoFinancialsError(Exception)`
  - `@dataclass Financials(name: str, years: list[int], fy_end: dict[int, str], data: dict[str, dict[int, float]], warnings: list[str])` with `.series(field) -> dict[int, float]`, `.get(field, year) -> float | None`, `.latest_year -> int`
  - `build_financials(facts: dict, splits: list[tuple[str, float]]) -> Financials`
  - Fields in `data`: `revenue, operating_income, pretax_income, income_tax, net_income, eps_diluted, shares_diluted, equity, operating_cash_flow, capex, dep_amort, change_ar, change_ap` (raw, per-share split-adjusted) plus derived `total_debt, fcf, bvps, roic`.
  - `tests/helpers.py`: `fact(start, end, val, filed, form="10-K")`, `facts_doc(concepts: dict[str, list[dict]], unit="USD")`, `make_fin(series: dict[str, dict[int, float]]) -> Financials`.

- [ ] **Step 1: Write test helpers** — `tests/helpers.py`

```python
from engine.financials import Financials


def fact(start, end, val, filed, form="10-K"):
    row = {"end": end, "val": val, "filed": filed, "form": form, "fp": "FY"}
    if start:
        row["start"] = start
    return row


def facts_doc(concepts, units=None):
    """concepts: {concept_name: [rows]}; units: optional {concept_name: unit}."""
    units = units or {}
    return {
        "entityName": "Test Co",
        "facts": {"us-gaap": {
            name: {"units": {units.get(name, "USD"): rows}} for name, rows in concepts.items()
        }},
    }


def make_fin(series, name="Test Co"):
    years = sorted({y for s in series.values() for y in s})
    return Financials(
        name=name,
        years=years,
        fy_end={y: f"{y}-12-31" for y in years},
        data={k: dict(v) for k, v in series.items()},
        warnings=[],
    )
```

- [ ] **Step 2: Write the failing unit tests** — `tests/test_financials.py`

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_financials.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.financials'`

- [ ] **Step 4: Implement** — `engine/financials.py`

```python
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
        else:
            total_debt[y] = 0.0

        if g("operating_cash_flow") is not None and g("capex") is not None:
            fcf[y] = g("operating_cash_flow") - g("capex")

        if g("equity") is not None and g("shares_diluted"):
            bvps[y] = g("equity") / g("shares_diluted")

        op, eq = g("operating_income"), g("equity")
        if op is not None and eq is not None:
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
```

- [ ] **Step 5: Run unit tests (fixtures not recorded yet)**

Run: `python -m pytest tests/test_financials.py -q -k "not fixture"`
Expected: 11 passed, 3 deselected

- [ ] **Step 6: Write the fixture recorder** — `scripts/record_fixture.py`

```python
"""Download SEC company facts for tickers and save trimmed copies as test fixtures.

Usage:  SEC_USER_AGENT="Your Name you@example.com" python scripts/record_fixture.py AAPL MSFT COST
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.financials import CONCEPTS  # noqa: E402
from engine.sec import SecClient  # noqa: E402


def trim(facts):
    wanted = {c for concepts in CONCEPTS.values() for c in concepts}
    gaap = facts.get("facts", {}).get("us-gaap", {})
    out = {}
    for name in sorted(wanted & gaap.keys()):
        out[name] = {"units": {
            unit: [r for r in rows if str(r.get("form", "")).startswith("10-K")]
            for unit, rows in gaap[name]["units"].items()
        }}
    return {"cik": facts.get("cik"), "entityName": facts.get("entityName"), "facts": {"us-gaap": out}}


def main(symbols):
    sec = SecClient(os.environ.get("SEC_USER_AGENT", ""))
    out_dir = ROOT / "tests" / "fixtures" / "sec"
    out_dir.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        cik = sec.cik_for(symbol)
        trimmed = trim(sec.company_facts(cik))
        (out_dir / f"{symbol.upper()}.json").write_text(json.dumps(trimmed, separators=(",", ":")), encoding="utf-8")
        print(f"saved {symbol} ({cik})")


if __name__ == "__main__":
    main(sys.argv[1:])
```

Run: `SEC_USER_AGENT="rule-one-analyzer fixtures admin@example.com" python scripts/record_fixture.py AAPL MSFT COST`
Expected: three `saved ...` lines; files in `tests/fixtures/sec/`.

- [ ] **Step 7: Run all financials tests**

Run: `python -m pytest tests/test_financials.py -q`
Expected: 14 passed

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: build split-adjusted yearly financials from SEC XBRL facts"
```

---

### Task 4: Big Five and debt check

**Files:**
- Create: `engine/bigfive.py`
- Test: `tests/test_bigfive.py`

**Interfaces:**
- Consumes: `Financials` (`.years`, `.series()`, `.get()`, `.latest_year`) from Task 3; settings dict from Task 1.
- Produces:
  - `WINDOWS = (10, 5, 3, 1)`; `METRICS = {"roic": "ROIC", "sales": "Sales growth", "eps": "EPS growth", "equity": "Equity growth", "fcf": "Free cash flow growth"}`; `SERIES_FOR = {"roic": "roic", "sales": "revenue", "eps": "eps_diluted", "equity": "bvps", "fcf": "fcf"}`
  - `cagr(start, end, years) -> float | None`
  - `growth_window(series, last_year, first_year, n) -> dict` keys `available, value, start_year, end_year, note`
  - `roic_window(series, last_year, first_year, n) -> dict` (same keys)
  - `longest_value(windows: dict) -> float | None` (first non-None value among "10","5","3")
  - `analyze_big_five(fin, settings) -> dict`: `{"score": int, "metrics": {key: {"label", "windows": {"10": {...,"pass"}, "5", "3", "1"}, "passes", "required", "trend_ok", "pass"}}, "debt": {"year","total_debt","fcf","payoff_years","pass"}, "warnings": [str]}`

- [ ] **Step 1: Write the failing tests** — `tests/test_bigfive.py`

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bigfive.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.bigfive'`

- [ ] **Step 3: Implement** — `engine/bigfive.py`

```python
"""The Big Five numbers and the debt check."""

WINDOWS = (10, 5, 3, 1)
METRICS = {
    "roic": "ROIC",
    "sales": "Sales growth",
    "eps": "EPS growth",
    "equity": "Equity growth",
    "fcf": "Free cash flow growth",
}
SERIES_FOR = {"roic": "roic", "sales": "revenue", "eps": "eps_diluted", "equity": "bvps", "fcf": "fcf"}


def cagr(start, end, years):
    if start is None or end is None or years <= 0 or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1 / years) - 1


def _window(available, value=None, start_year=None, end_year=None, note=None):
    return {"available": available, "value": value, "start_year": start_year, "end_year": end_year, "note": note}


def growth_window(series, last_year, first_year, n):
    start = last_year - n
    if start < first_year:
        return _window(False)
    end_val = series.get(last_year)
    if end_val is None or end_val <= 0:
        return _window(True, end_year=last_year, note=f"{last_year} value is missing or not positive")
    for y in range(start, last_year):
        v = series.get(y)
        if v is not None and v > 0:
            note = None if y == start else f"start moved from {start} to {y} (missing or negative value)"
            return _window(True, cagr(v, end_val, last_year - y), y, last_year, note)
    return _window(True, end_year=last_year, note="no positive starting value")


def roic_window(series, last_year, first_year, n):
    start = last_year - n + 1
    if start < first_year:
        return _window(False)
    values = [series[y] for y in range(start, last_year + 1) if series.get(y) is not None]
    if not values:
        return _window(True, start_year=start, end_year=last_year, note="no ROIC data")
    note = None if len(values) == n else f"average of {len(values)} of {n} years (some missing)"
    return _window(True, sum(values) / len(values), start, last_year, note)


def longest_value(windows):
    for key in ("10", "5", "3"):
        v = windows.get(key, {}).get("value")
        if v is not None:
            return v
    return None


def _metric(key, fin, settings, warnings):
    series = fin.series(SERIES_FOR[key])
    last, first = fin.latest_year, fin.years[0]
    fn = roic_window if key == "roic" else growth_window
    windows = {}
    for n in WINDOWS:
        w = fn(series, last, first, n)
        w["pass"] = w["available"] and w["value"] is not None and w["value"] >= settings["big_five_threshold"]
        if w["note"]:
            warnings.append(f"{METRICS[key]} {n}-year: {w['note']}.")
        windows[str(n)] = w
    available = [w for w in windows.values() if w["available"]]
    passes = sum(1 for w in available if w["pass"])
    required = min(int(settings["windows_to_pass"]), len(available))
    long_v, one_v = longest_value(windows), windows["1"]["value"]
    trend_ok = long_v is None or one_v is None or one_v >= long_v - settings["trend_tolerance"]
    return {
        "label": METRICS[key],
        "windows": windows,
        "passes": passes,
        "required": required,
        "trend_ok": trend_ok,
        "pass": bool(available) and passes >= required and trend_ok,
    }


def _debt(fin, settings):
    y = fin.latest_year
    debt = fin.get("total_debt", y) or 0.0
    fcf = fin.get("fcf", y)
    if debt <= 0:
        years, ok = 0.0, True
    elif fcf is None or fcf <= 0:
        years, ok = None, False
    else:
        years = debt / fcf
        ok = years <= settings["debt_payoff_max_years"]
    return {"year": y, "total_debt": debt, "fcf": fcf, "payoff_years": years, "pass": ok}


def analyze_big_five(fin, settings):
    warnings = []
    span = len(fin.years)
    if span < 11:
        warnings.append(f"Only {span} years of annual data available; the 10-year checks use what exists.")
    metrics = {key: _metric(key, fin, settings, warnings) for key in METRICS}
    return {
        "score": sum(1 for m in metrics.values() if m["pass"]),
        "metrics": metrics,
        "debt": _debt(fin, settings),
        "warnings": warnings,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bigfive.py -q`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: Big Five windows, scoring and debt check"
```

---

### Task 5: Market data (Yahoo Finance)

**Files:**
- Create: `engine/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Consumes: `with_retries`, `FetchError` (Task 2).
- Produces: `@dataclass MarketData(price: float, analyst_growth: float | None, splits: list[tuple[str, float]], monthly_closes: dict[str, float])`; `fetch_market(symbol, ticker_factory=None, sleep=time.sleep) -> MarketData` raising `FetchError` on failure. `monthly_closes` keys are `"YYYY-MM"`.

- [ ] **Step 1: Write the failing tests** — `tests/test_market.py`

```python
import math

import pandas as pd
import pytest

from engine.market import fetch_market
from engine.retry import FetchError


class FakeTicker:
    def __init__(self, price=150.0, growth=None, splits=None, fail_history=False):
        self._price = price
        self.growth_estimates = growth
        self.splits = splits if splits is not None else pd.Series(dtype=float)
        self._fail_history = fail_history

    @property
    def fast_info(self):
        return {"lastPrice": self._price}

    def history(self, **kwargs):
        if self._fail_history:
            raise RuntimeError("yahoo down")
        idx = pd.to_datetime(["2024-08-01", "2024-09-01", "2024-10-01"]).tz_localize("America/New_York")
        return pd.DataFrame({"Close": [10.0, 11.0, float("nan")]}, index=idx)


def fetch(ticker):
    return fetch_market("TEST", ticker_factory=lambda s: ticker, sleep=lambda s: None)


def test_basic_fields():
    splits = pd.Series([4.0], index=pd.to_datetime(["2020-08-31"]).tz_localize("America/New_York"))
    m = fetch(FakeTicker(splits=splits))
    assert m.price == 150.0
    assert m.splits == [("2020-08-31", 4.0)]
    assert m.monthly_closes == {"2024-08": 10.0, "2024-09": 11.0}
    assert m.analyst_growth is None


def test_analyst_growth_from_ltg_row():
    ge = pd.DataFrame({"stockTrend": [0.07, 0.11], "indexTrend": [0.2, 0.12]}, index=["0q", "LTG"])
    assert fetch(FakeTicker(growth=ge)).analyst_growth == pytest.approx(0.11)


def test_analyst_growth_nan_is_none():
    ge = pd.DataFrame({"stockTrend": [math.nan], "indexTrend": [0.12]}, index=["LTG"])
    assert fetch(FakeTicker(growth=ge)).analyst_growth is None


def test_missing_price_raises_fetch_error():
    with pytest.raises(FetchError, match="price"):
        fetch(FakeTicker(price=None))


def test_history_failure_raises_fetch_error():
    with pytest.raises(FetchError):
        fetch(FakeTicker(fail_history=True))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_market.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.market'`

- [ ] **Step 3: Implement** — `engine/market.py`

```python
"""Current price, split history, monthly closes and analyst growth from Yahoo Finance."""
import time
from dataclasses import dataclass

from engine.retry import FetchError, with_retries


@dataclass
class MarketData:
    price: float
    analyst_growth: float | None
    splits: list
    monthly_closes: dict


def _analyst_growth(ticker):
    try:
        ge = ticker.growth_estimates
    except Exception:
        return None
    if ge is None or getattr(ge, "empty", True):
        return None
    for row in ("LTG", "+5y"):
        if row in ge.index and "stockTrend" in ge.columns:
            v = ge.loc[row, "stockTrend"]
            if v is not None and v == v:  # v == v is False for NaN
                return float(v)
    return None


def fetch_market(symbol, ticker_factory=None, sleep=time.sleep):
    if ticker_factory is None:
        import yfinance as yf
        ticker_factory = yf.Ticker
    try:
        ticker = ticker_factory(symbol)

        def price():
            p = ticker.fast_info["lastPrice"]
            if p is None or not p > 0:
                raise ValueError(f"Yahoo returned no price for {symbol}")
            return float(p)

        current = with_retries(price, sleep=sleep)
        hist = with_retries(lambda: ticker.history(period="max", interval="1mo", auto_adjust=False), sleep=sleep)
        splits = [(ts.strftime("%Y-%m-%d"), float(r)) for ts, r in ticker.splits.items() if r and r > 0]
    except Exception as e:
        raise FetchError(f"Yahoo Finance request failed for {symbol}: {e}") from e
    closes = {ts.strftime("%Y-%m"): float(c) for ts, c in hist["Close"].dropna().items()}
    return MarketData(price=current, analyst_growth=_analyst_growth(ticker), splits=splits, monthly_closes=closes)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_market.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: Yahoo Finance market data with retries"
```

---

### Task 6: Valuation — Sticker Price, MOS, Ten Cap, Payback Time

**Files:**
- Create: `engine/valuation.py`
- Test: `tests/test_valuation.py`

**Interfaces:**
- Consumes: `Financials` (Task 3), `MarketData` (Task 5), `analyze_big_five` result + `longest_value` (Task 4).
- Produces:
  - `choose_growth(equity_growth, analyst_growth, override, cap) -> tuple[float | None, str | None, list[str]]`
  - `historical_pe(fin, monthly_closes) -> dict[int, float]`
  - `analyze_valuation(fin, market, big_five, override, settings) -> dict` with keys: `computable, growth_rate, growth_source, equity_growth, analyst_growth, price, current_eps, eps_year, historical_pe_avg, historical_pe_years, pe_from_growth, future_eps, future_pe, future_price, sticker_price, mos_price, pct_from_mos, owner_earnings_ps, ten_cap_price, fcf_ps, payback_price, warnings`. Values not computable are `None`.

- [ ] **Step 1: Write the failing tests** — `tests/test_valuation.py`

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_valuation.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.valuation'`

- [ ] **Step 3: Implement** — `engine/valuation.py`

```python
"""Sticker Price, Margin of Safety, Ten Cap and Payback Time."""
from engine.bigfive import longest_value


def choose_growth(equity_growth, analyst_growth, override, cap):
    if override is not None:
        return override, "your override", []
    warnings = []
    if analyst_growth is None:
        warnings.append("No analyst 5-year growth estimate available; using historical equity growth only.")
    options = [(g, s) for g, s in ((equity_growth, "historical equity growth"),
                                   (analyst_growth, "analyst estimate")) if g is not None]
    if not options:
        return None, None, warnings + ["No growth rate could be determined."]
    growth, source = min(options, key=lambda o: o[0])
    if growth > cap:
        growth, source = cap, f"{source} (capped at {cap:.0%})"
    return growth, source, warnings


def historical_pe(fin, monthly_closes):
    out = {}
    for y in fin.years:
        eps, end = fin.get("eps_diluted", y), fin.fy_end.get(y)
        if eps is None or eps <= 0 or end is None:
            continue
        price = monthly_closes.get(end[:7])
        if price is not None:
            out[y] = price / eps
    return out


def analyze_valuation(fin, market, big_five, override, settings):
    y = fin.latest_year
    equity_growth = longest_value(big_five["metrics"]["equity"]["windows"])
    growth, source, warnings = choose_growth(equity_growth, market.analyst_growth, override, settings["growth_cap"])
    pe_by_year = historical_pe(fin, market.monthly_closes)
    recent = [pe for year, pe in pe_by_year.items() if year > y - 10]
    avg_pe = sum(recent) / len(recent) if recent else None
    eps = fin.get("eps_diluted", y)

    v = {
        "computable": False, "growth_rate": growth, "growth_source": source,
        "equity_growth": equity_growth, "analyst_growth": market.analyst_growth,
        "price": market.price, "current_eps": eps, "eps_year": y,
        "historical_pe_avg": avg_pe, "historical_pe_years": len(recent),
        "pe_from_growth": None, "future_eps": None, "future_pe": None, "future_price": None,
        "sticker_price": None, "mos_price": None, "pct_from_mos": None,
        "owner_earnings_ps": None, "ten_cap_price": None, "fcf_ps": None, "payback_price": None,
        "warnings": warnings,
    }

    if eps is None or eps <= 0:
        warnings.append("Latest EPS is missing, zero or negative, so a Sticker Price can't be calculated.")
    elif growth is None or growth <= 0:
        warnings.append("Growth rate is missing or not positive, so a Sticker Price can't be calculated.")
    else:
        pe_from_growth = growth * 100 * 2
        if avg_pe is None:
            warnings.append("No historical P/E available; Future P/E uses 2 × growth rate only.")
            future_pe = pe_from_growth
        else:
            future_pe = min(pe_from_growth, avg_pe)
        future_pe = min(future_pe, settings["pe_cap"])
        future_eps = eps * (1 + growth) ** 10
        future_price = future_eps * future_pe
        sticker = future_price / (1 + settings["marr"]) ** 10
        mos = sticker * settings["mos_fraction"]
        v.update(computable=True, pe_from_growth=pe_from_growth, future_eps=future_eps, future_pe=future_pe,
                 future_price=future_price, sticker_price=sticker, mos_price=mos,
                 pct_from_mos=market.price / mos - 1)

    shares = fin.get("shares_diluted", y)
    if shares:
        g = lambda f: fin.get(f, y)
        if None not in (g("net_income"), g("dep_amort"), g("income_tax"), g("capex")):
            oe = (g("net_income") + g("dep_amort") + g("income_tax") + (g("change_ap") or 0.0)
                  - (g("change_ar") or 0.0) - 0.5 * g("capex"))
            v["owner_earnings_ps"] = oe / shares
            if oe > 0:
                v["ten_cap_price"] = oe / shares * 10
        fcf = fin.get("fcf", y)
        if fcf is not None:
            fcf_ps = fcf / shares
            v["fcf_ps"] = fcf_ps
            if fcf_ps > 0:
                rate = growth if growth and growth > 0 else 0.0
                v["payback_price"] = sum(fcf_ps * (1 + rate) ** t for t in range(1, int(settings["payback_years"]) + 1))
    return v
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_valuation.py -q`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: Sticker Price, MOS, Ten Cap and Payback Time valuation"
```

---

### Task 7: Tiers and email alerts

**Files:**
- Create: `engine/tiers.py`, `engine/alerts.py`
- Test: `tests/test_tiers.py`, `tests/test_alerts.py`

**Interfaces:**
- Produces:
  - `TIER_RANK = {"not_yet": 0, "close": 1, "buy": 2}`; `TIER_LABEL = {"buy": "Buy zone", "close": "Getting close", "not_yet": "Not yet"}`
  - `assign_tier(price, mos_price, score, settings) -> tuple[str, str]` (tier, plain-English reason)
  - `detect_changes(stocks: list[dict], state: dict[str, str]) -> tuple[list[dict], dict[str, str]]`
  - `@dataclass EmailConfig(address, password, to)`; `email_config_from_env(env) -> EmailConfig | None`
  - `compose_email(alerts, site_url) -> tuple[str, str, str]` (subject, text, html)
  - `send_email(subject, text, html, cfg, smtp_factory=smtplib.SMTP_SSL) -> None`
- Stock dict fields used: `symbol, name, tier, tier_reason, price, stale, error, big_five.score, big_five.debt, valuation.{mos_price, sticker_price, pct_from_mos, ten_cap_price, payback_price}, warnings`.

- [ ] **Step 1: Write the failing tests** — `tests/test_tiers.py`

```python
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
```

`tests/test_alerts.py`:
```python
import pytest

from engine.alerts import EmailConfig, compose_email, detect_changes, email_config_from_env, send_email


def stock(symbol, tier, **extra):
    s = {"symbol": symbol, "name": f"{symbol} Inc.", "tier": tier, "tier_reason": f"{tier} reason",
         "price": 90.0, "stale": False, "error": None, "warnings": [],
         "big_five": {"score": 5, "debt": {"payoff_years": 1.5, "pass": True}},
         "valuation": {"mos_price": 100.0, "sticker_price": 200.0, "pct_from_mos": -0.1,
                       "ten_cap_price": 95.0, "payback_price": 120.0}}
    s.update(extra)
    return s


def test_detects_upgrades_only():
    stocks = [stock("AAA", "buy"), stock("BBB", "close"), stock("CCC", "not_yet"), stock("DDD", "close")]
    state = {"AAA": "close", "BBB": "close", "CCC": "buy", "DDD": "buy"}
    alerts, new_state = detect_changes(stocks, state)
    assert [a["symbol"] for a in alerts] == ["AAA"]
    assert new_state == {"AAA": "buy", "BBB": "close", "CCC": "not_yet", "DDD": "close"}


def test_new_symbol_alerts_from_not_yet():
    alerts, _ = detect_changes([stock("NEW", "close")], {})
    assert [a["symbol"] for a in alerts] == ["NEW"]


def test_stale_and_error_never_alert_and_keep_state():
    stocks = [stock("OLD", "buy", stale=True), stock("BAD", "not_yet", error="boom")]
    alerts, new_state = detect_changes(stocks, {"OLD": "close", "BAD": "close"})
    assert alerts == []
    assert new_state == {"OLD": "close", "BAD": "close"}


def test_removed_symbols_dropped_from_state():
    _, new_state = detect_changes([stock("AAA", "not_yet")], {"AAA": "not_yet", "GONE": "buy"})
    assert new_state == {"AAA": "not_yet"}


def test_email_config_from_env():
    env = {"GMAIL_ADDRESS": "me@gmail.com", "GMAIL_APP_PASSWORD": "pw", "ALERT_EMAIL_TO": "you@x.com"}
    assert email_config_from_env(env) == EmailConfig("me@gmail.com", "pw", "you@x.com")
    assert email_config_from_env({"GMAIL_ADDRESS": "me@gmail.com"}) is None


def test_compose_email():
    subject, text, html = compose_email([stock("AAPL", "buy"), stock("MSFT", "close")], "https://me.github.io/r1/")
    assert subject == "Rule #1: AAPL in Buy zone, MSFT getting close"
    assert "https://me.github.io/r1/stock.html?t=AAPL" in text
    assert "$100.00" in text
    assert "<a href=\"https://me.github.io/r1/stock.html?t=MSFT\">" in html


def test_compose_email_escapes_html():
    s = stock("XYZ", "buy", name="<b>Evil</b> & Co")
    _, _, html = compose_email([s], "https://x/")
    assert "&lt;b&gt;Evil&lt;/b&gt; &amp; Co" in html


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.sent, self.login_args = host, port, [], None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)


def test_send_email_uses_gmail_ssl():
    cfg = EmailConfig("me@gmail.com", "pw", "you@x.com")
    send_email("Subj", "plain", "<p>html</p>", cfg, smtp_factory=FakeSMTP)
    smtp = FakeSMTP.instances[-1]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 465)
    assert smtp.login_args == ("me@gmail.com", "pw")
    msg = smtp.sent[0]
    assert msg["To"] == "you@x.com" and msg["Subject"] == "Subj"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tiers.py tests/test_alerts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.tiers'`

- [ ] **Step 3: Implement** — `engine/tiers.py`

```python
"""Assign each stock a status tier with a plain-English reason."""

TIER_RANK = {"not_yet": 0, "close": 1, "buy": 2}
TIER_LABEL = {"buy": "Buy zone", "close": "Getting close", "not_yet": "Not yet"}


def assign_tier(price, mos_price, score, settings):
    min_score = int(settings["big_five_min_score"])
    if price is None or mos_price is None:
        return "not_yet", "Not yet: a MOS price couldn't be calculated (see the warnings)."
    if score < min_score:
        return "not_yet", f"Not yet: only {score} of 5 Big Five numbers pass (needs {min_score})."
    pct = price / mos_price - 1
    if price <= mos_price:
        return "buy", (f"Buy zone: the price (${price:,.2f}) is at or below the MOS price "
                       f"(${mos_price:,.2f}) and {score} of 5 Big Five numbers pass.")
    margin = settings["getting_close_margin"]
    if price <= mos_price * (1 + margin):
        return "close", (f"Getting close: the price is {pct:.1%} above the MOS price, "
                         f"within the {margin:.0%} early-warning range.")
    return "not_yet", f"Not yet: the price is {pct:.0%} above the MOS price."
```

`engine/alerts.py`:
```python
"""Tier-change detection and Gmail alert emails."""
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape

from engine.tiers import TIER_LABEL, TIER_RANK


@dataclass
class EmailConfig:
    address: str
    password: str
    to: str


def email_config_from_env(env):
    address, password, to = env.get("GMAIL_ADDRESS"), env.get("GMAIL_APP_PASSWORD"), env.get("ALERT_EMAIL_TO")
    if not (address and password and to):
        return None
    return EmailConfig(address, password, to)


def detect_changes(stocks, state):
    alerts, new_state = [], dict(state)
    for s in stocks:
        if s.get("stale") or s.get("error"):
            continue
        previous = state.get(s["symbol"], "not_yet")
        if TIER_RANK[s["tier"]] > TIER_RANK[previous]:
            alerts.append(s)
        new_state[s["symbol"]] = s["tier"]
    symbols = {s["symbol"] for s in stocks}
    return alerts, {k: v for k, v in new_state.items() if k in symbols}


def _money(v):
    return "n/a" if v is None else f"${v:,.2f}"


def _pct(v):
    return "n/a" if v is None else f"{v:+.1%}"


def _lines(s):
    val, bf = s["valuation"], s["big_five"]
    debt = bf["debt"]
    debt_text = "n/a" if debt["payoff_years"] is None else f"{debt['payoff_years']:.1f} years"
    return [
        ("Price", _money(s["price"])),
        ("MOS price", _money(val["mos_price"])),
        ("Price vs MOS", _pct(val["pct_from_mos"])),
        ("Sticker Price", _money(val["sticker_price"])),
        ("Big Five score", f"{bf['score']} of 5"),
        ("Debt payoff", f"{debt_text} ({'pass' if debt['pass'] else 'fail'})"),
        ("Ten Cap price", _money(val["ten_cap_price"])),
        ("Payback Time price", _money(val["payback_price"])),
    ]


def compose_email(alerts, site_url):
    parts = [f"{s['symbol']} in Buy zone" if s["tier"] == "buy" else f"{s['symbol']} getting close" for s in alerts]
    subject = "Rule #1: " + ", ".join(parts)
    text, html = [], ["<div style=\"font-family:system-ui,sans-serif;max-width:600px\">"]
    for s in alerts:
        link = f"{site_url}stock.html?t={s['symbol']}"
        label = TIER_LABEL[s["tier"]]
        text.append(f"{s['symbol']} — {s['name']}: {label}")
        text.append(s["tier_reason"])
        text += [f"  {k}: {v}" for k, v in _lines(s)]
        text += [f"  Warning: {w}" for w in s.get("warnings", [])]
        text += [f"  Details: {link}", ""]
        rows = "".join(f"<tr><td style=\"padding:2px 12px 2px 0;color:#555\">{escape(k)}</td>"
                       f"<td><b>{escape(v)}</b></td></tr>" for k, v in _lines(s))
        warns = "".join(f"<li>{escape(w)}</li>" for w in s.get("warnings", []))
        html.append(
            f"<h2 style=\"margin-bottom:4px\">{escape(s['symbol'])} — {escape(s['name'])}</h2>"
            f"<p style=\"margin-top:0\"><b>{escape(label)}</b>: {escape(s['tier_reason'])}</p>"
            f"<table>{rows}</table>"
            + (f"<p>Warnings:</p><ul>{warns}</ul>" if warns else "")
            + f"<p><a href=\"{escape(link)}\">Open {escape(s['symbol'])} on the dashboard</a></p><hr>"
        )
    footer = "You get this email when a stock on your watchlist moves into a better tier."
    text.append(footer)
    html.append(f"<p style=\"color:#777;font-size:12px\">{footer}</p></div>")
    return subject, "\n".join(text), "".join(html)


def send_email(subject, text, html, cfg, smtp_factory=smtplib.SMTP_SSL):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, cfg.address, cfg.to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtp_factory("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(cfg.address, cfg.password)
        smtp.send_message(msg)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tiers.py tests/test_alerts.py -q`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: tier assignment and tier-change email alerts"
```

---

### Task 8: Output — results JSON and CSV exports

**Files:**
- Create: `engine/output.py`
- Test: `tests/test_output.py`

**Interfaces:**
- Produces:
  - `HISTORY_COLUMNS: list[tuple[str, str]]` (field key, human label) — also written into `results.json` as `"columns"` for the dashboard.
  - `read_json(path, default)`, `write_json(path, obj)`
  - `stock_csv(stock) -> str` (one row per year; columns `Year` + labels)
  - `watchlist_csv(stocks) -> str`
  - `write_csvs(stocks, out_dir: Path) -> None` writes `out_dir/watchlist.csv` and `out_dir/<SYMBOL>.csv`
- Stock `history` shape (produced by Task 9): `{"years": [int], "fy_end": {str(year): iso}, "<field>": {str(year): float}}`.

- [ ] **Step 1: Write the failing tests** — `tests/test_output.py`

```python
import csv
import io

from engine.output import HISTORY_COLUMNS, read_json, stock_csv, watchlist_csv, write_csvs, write_json


def sample_stock():
    return {
        "symbol": "AAA", "name": "Aaa, Inc.", "price": 50.0, "tier": "close", "stale": False, "error": None,
        "big_five": {"score": 4, "debt": {"payoff_years": 2.0, "pass": True}},
        "valuation": {"mos_price": 48.0, "sticker_price": 96.0, "pct_from_mos": 0.0417,
                      "ten_cap_price": 40.0, "payback_price": 55.0, "growth_rate": 0.12},
        "history": {"years": [2023, 2024], "fy_end": {"2023": "2023-12-31", "2024": "2024-12-31"},
                    "revenue": {"2023": 100.0, "2024": 112.0}, "roic": {"2024": 0.2}},
    }


def test_json_roundtrip(tmp_path):
    p = tmp_path / "sub" / "x.json"
    write_json(p, {"a": 1})
    assert read_json(p, None) == {"a": 1}
    assert read_json(tmp_path / "missing.json", {"d": 0}) == {"d": 0}


def test_stock_csv_rows_per_year():
    rows = list(csv.reader(io.StringIO(stock_csv(sample_stock()))))
    labels = dict(HISTORY_COLUMNS)
    assert rows[0][:3] == ["Year", "Fiscal year end", labels["revenue"]]
    assert rows[1][:3] == ["2023", "2023-12-31", "100.0"]
    roic_col = rows[0].index(labels["roic"])
    assert rows[1][roic_col] == "" and rows[2][roic_col] == "0.2"


def test_watchlist_csv():
    rows = list(csv.reader(io.StringIO(watchlist_csv([sample_stock()]))))
    assert rows[0][:4] == ["Symbol", "Company", "Status", "Price"]
    assert rows[1][:4] == ["AAA", "Aaa, Inc.", "Getting close", "50.0"]


def test_write_csvs(tmp_path):
    write_csvs([sample_stock(), {"symbol": "BAD", "name": "", "error": "x", "tier": "not_yet"}], tmp_path)
    assert (tmp_path / "watchlist.csv").exists()
    assert (tmp_path / "AAA.csv").exists()
    assert not (tmp_path / "BAD.csv").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_output.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.output'`

- [ ] **Step 3: Implement** — `engine/output.py`

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_output.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: results JSON and CSV exports"
```

---

### Task 9: Orchestration — `engine/main.py`

**Files:**
- Create: `engine/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `analyze_ticker(entry, sec, market_fetch, settings, now_iso) -> dict` (stock result)
  - `error_result(entry, message, now_iso) -> dict`
  - `site_url_from_env(env) -> str`
  - `run(root: Path, env: Mapping, sec=None, market_fetch=fetch_market, smtp_factory=smtplib.SMTP_SSL, now=None, send=True) -> int` (0 ok, 1 email failed, 2 config error)
  - CLI: `python -m engine.main [--root PATH] [--no-email]`
- Stock result shape: `{"symbol","name","as_of","stale","stale_reason","error","notes","growth_override","price","tier","tier_reason","big_five","valuation","history","warnings"}`; `results.json`: `{"generated_at","settings","columns": [[key,label]...],"stocks": [...]}`.

- [ ] **Step 1: Write the failing tests** — `tests/test_main.py`

```python
import json
from pathlib import Path

import pytest

from engine.main import analyze_ticker, run, site_url_from_env
from engine.config import DEFAULT_SETTINGS
from engine.market import MarketData
from engine.retry import FetchError

FIXTURES = Path(__file__).parent / "fixtures" / "sec"
AAPL_SPLITS = [("2014-06-09", 7.0), ("2020-08-31", 4.0)]


class FakeSec:
    def __init__(self, fail=False):
        self.fail = fail

    def cik_for(self, symbol):
        return {"AAPL": "0000320193", "MSFT": "0000789019", "COST": "0000909832"}.get(symbol)

    def company_facts(self, cik):
        if self.fail:
            raise FetchError("SEC request failed: down")
        name = {"0000320193": "AAPL", "0000789019": "MSFT", "0000909832": "COST"}[cik]
        return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def fake_market(price):
    def fetch(symbol):
        return MarketData(price=price, analyst_growth=0.08, splits=AAPL_SPLITS if symbol == "AAPL" else [],
                          monthly_closes={})
    return fetch


class FakeSMTP:
    sent = []
    fail = False

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a):
        if FakeSMTP.fail:
            raise OSError("auth failed")

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


ENV = {"GMAIL_ADDRESS": "me@gmail.com", "GMAIL_APP_PASSWORD": "pw", "ALERT_EMAIL_TO": "me@gmail.com",
       "GITHUB_REPOSITORY": "Me/rule-one-analyzer"}


def make_root(tmp_path, symbols, settings=None):
    (tmp_path / "watchlist.json").write_text(json.dumps({"tickers": [{"symbol": s} for s in symbols]}))
    (tmp_path / "settings.json").write_text(json.dumps(settings or {}))
    return tmp_path


def results(root):
    return json.loads((root / "data" / "results.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def reset_smtp():
    FakeSMTP.sent, FakeSMTP.fail = [], False


def test_site_url_from_env():
    assert site_url_from_env({"GITHUB_REPOSITORY": "Me/rule-one-analyzer"}) == "https://me.github.io/rule-one-analyzer/"
    assert site_url_from_env({"SITE_URL": "https://x.test/"}) == "https://x.test/"


@pytest.mark.parametrize("symbol", ["AAPL", "MSFT", "COST"])
def test_analyze_real_fixtures(symbol):
    entry = {"symbol": symbol, "notes": "", "growth_override": None}
    s = analyze_ticker(entry, FakeSec(), fake_market(100.0), DEFAULT_SETTINGS, "2026-10-06T22:00:00Z")
    assert s["error"] is None
    assert 0 <= s["big_five"]["score"] <= 5
    assert s["tier"] in ("buy", "close", "not_yet")
    assert s["history"]["years"] and str(s["history"]["years"][-1]) in s["history"]["revenue"]
    json.dumps(s)  # serializable


def test_unknown_ticker_is_error_result():
    s = analyze_ticker({"symbol": "ZZZZ", "notes": "", "growth_override": None}, FakeSec(), fake_market(1.0),
                       DEFAULT_SETTINGS, "t")
    assert "Not found in SEC filings" in s["error"]
    assert s["tier"] == "not_yet"


def test_run_writes_results_csv_and_sends_alert(tmp_path):
    root = make_root(tmp_path, ["COST"], {"big_five_min_score": 0})
    code = run(root, ENV, sec=FakeSec(), market_fetch=fake_market(0.01), smtp_factory=FakeSMTP)
    assert code == 0
    r = results(root)
    assert r["stocks"][0]["tier"] == "buy"
    assert r["columns"][0] == ["revenue", "Revenue"]
    assert (root / "data" / "csv" / "COST.csv").exists()
    assert len(FakeSMTP.sent) == 1
    assert json.loads((root / "data" / "alert_state.json").read_text()) == {"COST": "buy"}
    # Second run: same tier, no new email
    run(root, ENV, sec=FakeSec(), market_fetch=fake_market(0.01), smtp_factory=FakeSMTP)
    assert len(FakeSMTP.sent) == 1


def test_run_keeps_state_when_email_fails(tmp_path):
    root = make_root(tmp_path, ["COST"], {"big_five_min_score": 0})
    FakeSMTP.fail = True
    code = run(root, ENV, sec=FakeSec(), market_fetch=fake_market(0.01), smtp_factory=FakeSMTP)
    assert code == 1
    assert results(root)["stocks"][0]["tier"] == "buy"
    assert not (root / "data" / "alert_state.json").exists()


def test_run_marks_stale_on_fetch_error(tmp_path):
    root = make_root(tmp_path, ["AAPL", "MSFT"], {"big_five_min_score": 0})
    run(root, ENV, sec=FakeSec(), market_fetch=fake_market(1000.0), smtp_factory=FakeSMTP)
    FakeSMTP.sent = []

    def failing_market(symbol):
        if symbol == "AAPL":
            raise FetchError("Yahoo down")
        return fake_market(0.01)(symbol)

    code = run(root, ENV, sec=FakeSec(), market_fetch=failing_market, smtp_factory=FakeSMTP)
    assert code == 0
    stocks = {s["symbol"]: s for s in results(root)["stocks"]}
    assert stocks["AAPL"]["stale"] is True and "Yahoo down" in stocks["AAPL"]["stale_reason"]
    assert stocks["AAPL"]["price"] == 1000.0
    assert stocks["MSFT"]["stale"] is False
    subjects = [m["Subject"] for m in FakeSMTP.sent]
    assert subjects and "AAPL" not in subjects[0]


def test_fetch_error_without_previous_is_error(tmp_path):
    root = make_root(tmp_path, ["AAPL"])
    run(root, ENV, sec=FakeSec(fail=True), market_fetch=fake_market(1.0), smtp_factory=FakeSMTP)
    s = results(root)["stocks"][0]
    assert s["error"].startswith("Data couldn't be downloaded")


def test_config_error_returns_2_and_writes_nothing(tmp_path):
    root = make_root(tmp_path, ["AAPL"], {"marr": 9})
    assert run(root, ENV, sec=FakeSec(), market_fetch=fake_market(1.0), smtp_factory=FakeSMTP) == 2
    assert not (root / "data").exists()


def test_missing_email_config_skips_send_and_state(tmp_path):
    root = make_root(tmp_path, ["COST"], {"big_five_min_score": 0})
    code = run(root, {}, sec=FakeSec(), market_fetch=fake_market(0.01), smtp_factory=FakeSMTP)
    assert code == 0 and FakeSMTP.sent == []
    assert not (root / "data" / "alert_state.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_main.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.main'`

- [ ] **Step 3: Implement** — `engine/main.py`

```python
"""Run one analysis pass: fetch, compute, write results, send alerts."""
import argparse
import os
import smtplib
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from engine.alerts import compose_email, detect_changes, email_config_from_env, send_email
from engine.bigfive import analyze_big_five
from engine.config import ConfigError, load_settings, load_watchlist
from engine.financials import NoFinancialsError, build_financials
from engine.market import fetch_market
from engine.output import HISTORY_COLUMNS, read_json, write_csvs, write_json
from engine.retry import FetchError
from engine.sec import NotFoundError, SecClient
from engine.tiers import assign_tier
from engine.valuation import analyze_valuation, historical_pe


def site_url_from_env(env):
    if env.get("SITE_URL"):
        return env["SITE_URL"]
    owner, _, repo = env.get("GITHUB_REPOSITORY", "owner/rule-one-analyzer").partition("/")
    return f"https://{owner.lower()}.github.io/{repo}/"


def error_result(entry, message, now_iso):
    return {"symbol": entry["symbol"], "name": "", "as_of": now_iso, "stale": False, "stale_reason": None,
            "error": message, "notes": entry.get("notes", ""), "growth_override": entry.get("growth_override"),
            "price": None, "tier": "not_yet", "tier_reason": "Not yet: the analysis couldn't run (see the error).",
            "big_five": None, "valuation": None, "history": None, "warnings": []}


def _history(fin, pe_by_year):
    h = {"years": fin.years, "fy_end": {str(y): e for y, e in fin.fy_end.items()}}
    for field, _ in HISTORY_COLUMNS:
        source = pe_by_year if field == "pe" else fin.series(field)
        h[field] = {str(y): v for y, v in source.items()}
    return h


def analyze_ticker(entry, sec, market_fetch, settings, now_iso):
    symbol = entry["symbol"]
    cik = sec.cik_for(symbol)
    if cik is None:
        return error_result(entry, "Not found in SEC filings. This tool covers US companies that file 10-K reports.",
                            now_iso)
    try:
        facts = sec.company_facts(cik)
    except NotFoundError:
        return error_result(entry, "The SEC has no XBRL financial data for this company.", now_iso)
    market = market_fetch(symbol)
    try:
        fin = build_financials(facts, market.splits)
    except NoFinancialsError as e:
        return error_result(entry, str(e), now_iso)
    big_five = analyze_big_five(fin, settings)
    valuation = analyze_valuation(fin, market, big_five, entry.get("growth_override"), settings)
    tier, reason = assign_tier(market.price, valuation["mos_price"], big_five["score"], settings)
    warnings = fin.warnings + big_five.pop("warnings") + valuation.pop("warnings")
    return {
        "symbol": symbol, "name": fin.name, "as_of": now_iso, "stale": False, "stale_reason": None,
        "error": None, "notes": entry.get("notes", ""), "growth_override": entry.get("growth_override"),
        "price": market.price, "tier": tier, "tier_reason": reason,
        "big_five": big_five, "valuation": valuation,
        "history": _history(fin, historical_pe(fin, market.monthly_closes)),
        "warnings": warnings,
    }


def run(root, env, sec=None, market_fetch=fetch_market, smtp_factory=smtplib.SMTP_SSL, now=None, send=True):
    root = Path(root)
    try:
        settings = load_settings(root / "settings.json")
        watchlist = load_watchlist(root / "watchlist.json")
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    now_iso = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data_dir = root / "data"
    previous = {s["symbol"]: s for s in read_json(data_dir / "results.json", {"stocks": []}).get("stocks", [])}
    sec = sec or SecClient(env.get("SEC_USER_AGENT", ""))

    stocks = []
    for entry in watchlist:
        symbol = entry["symbol"]
        print(f"Analyzing {symbol}...")
        try:
            stock = analyze_ticker(entry, sec, market_fetch, settings, now_iso)
        except FetchError as e:
            prev = previous.get(symbol)
            if prev and not prev.get("error"):
                stock = {**prev, "stale": True, "stale_reason": f"{e} Showing results from {prev['as_of']}.",
                         "notes": entry.get("notes", ""), "growth_override": entry.get("growth_override")}
            else:
                stock = error_result(entry, f"Data couldn't be downloaded: {e}", now_iso)
        except Exception as e:
            traceback.print_exc()
            stock = error_result(entry, f"Analysis failed: {e}", now_iso)
        stocks.append(stock)

    write_json(data_dir / "results.json", {
        "generated_at": now_iso, "settings": settings,
        "columns": [list(c) for c in HISTORY_COLUMNS], "stocks": stocks,
    })
    write_csvs(stocks, data_dir / "csv")

    if not send:
        return 0
    state_path = data_dir / "alert_state.json"
    alerts, new_state = detect_changes(stocks, read_json(state_path, {}))
    if alerts:
        cfg = email_config_from_env(env)
        if cfg is None:
            print("Alerts found but email isn't configured (GMAIL_ADDRESS, GMAIL_APP_PASSWORD, ALERT_EMAIL_TO).")
            for a in alerts:
                print(f"  {a['symbol']}: {a['tier_reason']}")
            return 0
        subject, text, html = compose_email(alerts, site_url_from_env(env))
        try:
            send_email(subject, text, html, cfg, smtp_factory=smtp_factory)
        except Exception as e:
            print(f"Email failed: {e}. Alerts will retry next run.", file=sys.stderr)
            return 1
        print(f"Sent: {subject}")
    write_json(state_path, new_state)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rule #1 watchlist analyzer")
    parser.add_argument("--root", default=".", help="repo root containing watchlist.json and settings.json")
    parser.add_argument("--no-email", action="store_true", help="skip alerts (and leave alert state untouched)")
    args = parser.parse_args(argv)
    return run(Path(args.root), os.environ, send=not args.no_email)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_main.py -q`
Expected: 11 passed

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all passed (≈ 85 tests)

- [ ] **Step 6: Live smoke run (network)**

Run:
```bash
python - <<'EOF'
import json; json.dump({"tickers":[{"symbol":"AAPL"},{"symbol":"COST"},{"symbol":"KO"}]}, open("watchlist.json","w"), indent=2)
EOF
SEC_USER_AGENT="rule-one-analyzer dev admin@example.com" python -m engine.main --no-email
python -c "import json;[print(s['symbol'],s['tier'],s['big_five'] and s['big_five']['score'],s['valuation'] and s['valuation']['mos_price'],s['error']) for s in json.load(open('data/results.json'))['stocks']]"
```
Expected: three lines with tiers, scores 0–5, numeric MOS (or None with a warning), no errors. Sanity-check that AAPL's 10-year EPS growth is around 10–15% (not negative, which would mean split adjustment failed).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: orchestrate analysis runs with stale fallback and alert emails"
```

---

### Task 10: Dashboard foundation — styles, formatting, glossary, GitHub helpers

**Files:**
- Create: `site/css/style.css`, `site/js/format.js`, `site/js/glossary.js`, `site/js/github.js`, `site/js/common.js`
- Test: `tests/js/format.test.mjs`

**Interfaces:**
- Produces (ES modules):
  - `format.js`: `money(v, digits=2)`, `bigMoney(v)`, `pct(v, digits=1)`, `signedPct(v, digits=1)`, `num(v, digits=2)`, `TIERS` (`{buy|close|not_yet: {label, emoji, cls}}`), `historyRows(stock, columns) -> any[][]`, `toTsv(rows) -> string`, `stockMarkdown(stock, columns) -> string`, `escapeHtml(s)`
  - `glossary.js`: `GLOSSARY` (`{key: {term, what, why, good}}`), `attachTerms(root=document)`
  - `github.js`: `getToken()`, `setToken(t)`, `repoInfo(loc=window.location)`, `readJsonFile(path)`, `updateJsonFile(path, mutate, message)`, `runAnalysisNow()`, `checkToken()`, `actionsUrl()`
  - `common.js`: `loadResults()`, `initPage()` (header owner button + token dialog + glossary + owner class), `badge(tier)`, `toast(msg, kind)`, `term(key, text)` (HTML string `<span class="term" data-term="key">text</span>`)

- [ ] **Step 1: Write the failing JS tests** — `tests/js/format.test.mjs`

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { money, bigMoney, pct, signedPct, historyRows, toTsv, stockMarkdown, escapeHtml } from "../../site/js/format.js";

const columns = [["revenue", "Revenue"], ["roic", "ROIC"]];
const stock = {
  symbol: "AAA", name: "Aaa Inc.", price: 50, tier: "close", tier_reason: "Getting close: ...",
  big_five: { score: 4, metrics: { sales: { label: "Sales growth", pass: true,
    windows: { "10": { value: 0.12, pass: true, available: true }, "5": { value: 0.1, pass: true, available: true },
               "3": { value: null, pass: false, available: true }, "1": { value: null, pass: false, available: false } } } },
    debt: { payoff_years: 2, pass: true } },
  valuation: { computable: true, growth_rate: 0.1, growth_source: "analyst estimate", current_eps: 2, future_eps: 5.19,
    future_pe: 20, future_price: 103.75, sticker_price: 25.65, mos_price: 12.82, pct_from_mos: 0.05,
    ten_cap_price: 25, payback_price: 12.58 },
  history: { years: [2023, 2024], fy_end: { "2023": "2023-12-31", "2024": "2024-12-31" },
             revenue: { "2023": 100, "2024": 112 }, roic: { "2024": 0.2 } },
  warnings: ["Only 2 years of annual data available."],
};

test("money and pct formatting", () => {
  assert.equal(money(1234.5), "$1,234.50");
  assert.equal(money(-3), "-$3.00");
  assert.equal(money(null), "—");
  assert.equal(bigMoney(416161000000), "$416.16B");
  assert.equal(bigMoney(-2500000), "-$2.50M");
  assert.equal(pct(0.1234), "12.3%");
  assert.equal(signedPct(0.05), "+5.0%");
  assert.equal(signedPct(-0.04), "−4.0%");
});

test("historyRows builds a year-by-column grid", () => {
  const rows = historyRows(stock, columns);
  assert.deepEqual(rows[0], ["Year", "Fiscal year end", "Revenue", "ROIC"]);
  assert.deepEqual(rows[1], [2023, "2023-12-31", 100, null]);
  assert.deepEqual(rows[2], [2024, "2024-12-31", 112, 0.2]);
});

test("toTsv joins with tabs and blanks nulls", () => {
  assert.equal(toTsv([["a", null], [1, "x\ty"]]), "a\t\n1\tx y");
});

test("stockMarkdown includes key numbers and warnings", () => {
  const md = stockMarkdown(stock, columns);
  assert.match(md, /^# AAA — Aaa Inc\./);
  assert.match(md, /MOS price \| \$12\.82/);
  assert.match(md, /\| Sales growth \| 12\.0% \| 10\.0% \| n\/a \| — \| ✓ \|/);
  assert.match(md, /Only 2 years/);
  assert.match(md, /\| 2024 \| 2024-12-31 \| 112 \| 0\.2 \|/);
});

test("escapeHtml", () => {
  assert.equal(escapeHtml(`<a href="x">&</a>`), "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/js/`
Expected: FAIL — `Cannot find module .../site/js/format.js`

- [ ] **Step 3: Implement** — `site/js/format.js`

```js
// Pure formatting helpers shared by all pages (also unit-tested in Node).

const isNum = (v) => typeof v === "number" && Number.isFinite(v);

export function money(v, digits = 2) {
  if (!isNum(v)) return "—";
  const s = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return (v < 0 ? "-$" : "$") + s;
}

export function bigMoney(v) {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  const [div, suffix] = a >= 1e12 ? [1e12, "T"] : a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
  return (v < 0 ? "-$" : "$") + (a / div).toFixed(2) + suffix;
}

export function pct(v, digits = 1) {
  return isNum(v) ? (v * 100).toFixed(digits) + "%" : "—";
}

export function signedPct(v, digits = 1) {
  if (!isNum(v)) return "—";
  return (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(digits) + "%";
}

export function num(v, digits = 2) {
  return isNum(v) ? v.toLocaleString("en-US", { maximumFractionDigits: digits }) : "—";
}

export const TIERS = {
  buy: { label: "Buy zone", emoji: "🟢", cls: "buy" },
  close: { label: "Getting close", emoji: "🟡", cls: "close" },
  not_yet: { label: "Not yet", emoji: "⚪", cls: "not-yet" },
};

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function historyRows(stock, columns) {
  const h = stock.history;
  const rows = [["Year", "Fiscal year end", ...columns.map(([, label]) => label)]];
  for (const y of h.years) {
    const k = String(y);
    rows.push([y, h.fy_end[k] ?? "", ...columns.map(([field]) => h[field]?.[k] ?? null)]);
  }
  return rows;
}

export function toTsv(rows) {
  return rows.map((r) => r.map((c) => (c == null ? "" : String(c).replace(/[\t\r\n]+/g, " "))).join("\t")).join("\n");
}

const windowCell = (w) => (!w || !w.available ? "—" : w.value == null ? "n/a" : pct(w.value));

export function stockMarkdown(stock, columns) {
  const v = stock.valuation || {};
  const bf = stock.big_five || { metrics: {}, debt: {} };
  const lines = [
    `# ${stock.symbol} — ${stock.name}`,
    "",
    `Status: ${TIERS[stock.tier].label}. ${stock.tier_reason}`,
    "",
    "| Number | Value |",
    "|---|---|",
    `| Price | ${money(stock.price)} |`,
    `| MOS price | ${money(v.mos_price)} |`,
    `| Sticker Price | ${money(v.sticker_price)} |`,
    `| Price vs MOS | ${signedPct(v.pct_from_mos)} |`,
    `| Growth rate used | ${pct(v.growth_rate)} (${v.growth_source ?? "n/a"}) |`,
    `| Current EPS | ${money(v.current_eps)} |`,
    `| Future EPS (10 yr) | ${money(v.future_eps)} |`,
    `| Future P/E | ${num(v.future_pe, 1)} |`,
    `| Future price | ${money(v.future_price)} |`,
    `| Ten Cap price | ${money(v.ten_cap_price)} |`,
    `| Payback Time price | ${money(v.payback_price)} |`,
    `| Big Five score | ${bf.score ?? "n/a"} of 5 |`,
    `| Debt payoff | ${bf.debt?.payoff_years == null ? "n/a" : num(bf.debt.payoff_years, 1) + " years"} |`,
    "",
    "## Big Five",
    "",
    "| Metric | 10 yr | 5 yr | 3 yr | 1 yr | Pass |",
    "|---|---|---|---|---|---|",
    ...Object.values(bf.metrics).map((m) =>
      `| ${m.label} | ${["10", "5", "3", "1"].map((k) => windowCell(m.windows[k])).join(" | ")} | ${m.pass ? "✓" : "✗"} |`),
  ];
  if (stock.warnings?.length) lines.push("", "## Warnings", "", ...stock.warnings.map((w) => `- ${w}`));
  if (stock.history) {
    const rows = historyRows(stock, columns);
    lines.push("", "## Yearly data", "", `| ${rows[0].join(" | ")} |`, `|${rows[0].map(() => "---").join("|")}|`,
      ...rows.slice(1).map((r) => `| ${r.map((c) => (c == null ? "" : c)).join(" | ")} |`));
  }
  return lines.join("\n");
}
```

- [ ] **Step 4: Run JS tests to verify they pass**

Run: `node --test tests/js/`
Expected: 5 passing tests

- [ ] **Step 5: Implement glossary** — `site/js/glossary.js`

```js
// Plain-English explanations for every Rule #1 term, plus the ⓘ tooltip behavior.

export const GLOSSARY = {
  rule1: { term: "Rule #1", what: "Phil Town's investing method, named after Warren Buffett's \"Rule #1: don't lose money.\"", why: "Buy wonderful companies at attractive prices so the downside is limited.", good: "A company that passes the 4 Ms and trades below its MOS price." },
  four_ms: { term: "The 4 Ms", what: "Meaning (you understand it), Moat (durable advantage), Management (honest, capable owners), Margin of Safety (bought cheap).", why: "Rule #1 only buys businesses that pass all four.", good: "This tool checks the numbers behind Moat and Margin of Safety. You judge Meaning, Moat and Management when you add a stock." },
  meaning: { term: "Meaning", what: "You understand how the business makes money and would be proud to own all of it.", why: "You can only judge a company's future if you understand it.", good: "You could explain the business to a friend in two minutes." },
  moat: { term: "Moat", what: "A durable competitive advantage: brand, switching costs, network effects, low costs, or a toll-bridge position.", why: "A moat protects profits from competitors for years.", good: "Big Five numbers that stay ≥ 10% for 10 years are evidence of a moat." },
  management: { term: "Management", what: "The leaders running the company.", why: "Rule #1 wants owner-oriented managers who are honest and allocate money well.", good: "High, steady ROIC and clear, candid shareholder letters." },
  big_five: { term: "Big Five", what: "Five numbers Rule #1 uses to test for a moat: ROIC, Sales growth, EPS growth, Equity growth and Free cash flow growth.", why: "Consistently high numbers over 10 years suggest a durable business.", good: "Each one at 10% or more over 10, 5, 3 and 1 years." },
  big_five_score: { term: "Big Five score", what: "How many of the five numbers pass (0 to 5). A number passes when most of its 10/5/3/1-year checks are at least 10% and the latest year isn't collapsing.", why: "Real data has noisy years, so the tool counts mostly-passing numbers instead of demanding perfection.", good: "4 or 5. Alerts need at least 4 by default." },
  roic: { term: "ROIC (Return on Invested Capital)", what: "After-tax operating profit ÷ (shareholders' equity + debt). How much profit the business earns on the money invested in it.", why: "Phil Town calls it the most important Big Five number: it shows how well management uses capital.", good: "10% or higher, every year." },
  sales_growth: { term: "Sales growth", what: "How fast revenue (total sales) grew per year.", why: "A growing business usually has products people keep wanting.", good: "10% or more per year." },
  eps: { term: "EPS (Earnings Per Share)", what: "Net profit divided by the number of shares. Here it's diluted and adjusted for stock splits.", why: "Profit per share is what each share you own earns.", good: "Growing 10% or more per year." },
  eps_growth: { term: "EPS growth", what: "How fast earnings per share grew per year.", why: "Growing earnings drive a growing stock price over time.", good: "10% or more per year." },
  equity_growth: { term: "Equity growth (book value per share)", what: "How fast shareholders' equity per share grew per year. Equity is what the company owns minus what it owes.", why: "Phil Town treats it as the best measure of how fast the owners' stake is growing. It also feeds the growth rate used for the Sticker Price.", good: "10% or more per year." },
  bvps: { term: "Book value per share", what: "Shareholders' equity ÷ number of shares.", why: "It's the per-share version of equity, used for Equity growth.", good: "Rising steadily." },
  fcf: { term: "Free cash flow (FCF)", what: "Cash from operations minus capital expenditures. The cash left over after keeping the business running and growing.", why: "Profits can be massaged with accounting; cash is harder to fake.", good: "Positive and growing 10% or more per year." },
  fcf_growth: { term: "Free cash flow growth", what: "How fast free cash flow grew per year.", why: "Growing cash flow funds dividends, buybacks and debt payoff.", good: "10% or more per year." },
  cagr: { term: "CAGR (Compound Annual Growth Rate)", what: "The steady yearly growth rate that would turn the starting value into the ending value.", why: "It summarizes growth over many years as one comparable number.", good: "For the Big Five: 10% or more." },
  windows: { term: "10 / 5 / 3 / 1-year windows", what: "Each Big Five number is measured over the last 10, 5, 3 and 1 years.", why: "Long windows show durability; short windows show whether things are getting worse.", good: "All at 10% or more, with no sharp drop in the recent windows." },
  debt: { term: "Debt payoff years", what: "Long-term debt ÷ latest free cash flow: how many years of cash flow it would take to pay off all long-term debt.", why: "Too much debt can sink even a good business in a bad year.", good: "3 years or less." },
  growth_rate: { term: "Growth rate used", what: "The yearly growth rate assumed for the next 10 years: the lower of historical equity growth and the analysts' 5-year estimate, capped at 15%.", why: "Using the lower number keeps the valuation conservative.", good: "Something you believe the company can actually sustain. You can override it per stock." },
  analyst_growth: { term: "Analyst 5-year growth estimate", what: "Wall Street analysts' average forecast for yearly earnings growth over the next five years (from Yahoo Finance).", why: "Rule #1 compares it with historical growth and uses the lower one.", good: "Not always available; the tool warns when it's missing." },
  future_eps: { term: "Future EPS", what: "Current EPS grown at the growth rate for 10 years.", why: "It estimates what each share will earn a decade from now.", good: "—" },
  future_pe: { term: "Future P/E", what: "The P/E the stock is expected to trade at in 10 years: the lower of 2 × the growth rate and the stock's 10-year average P/E, capped at 50.", why: "Using the lower value avoids paying for an unrealistically high future price.", good: "—" },
  pe: { term: "P/E (Price-to-Earnings)", what: "Share price ÷ earnings per share. How many dollars investors pay for each dollar of yearly profit.", why: "It's used to turn future earnings into a future price.", good: "Depends on growth. Rule #1 caps it at 2 × the growth rate." },
  future_price: { term: "Future price", what: "Future EPS × Future P/E: the estimated share price 10 years from now.", why: "It's the starting point for working back to today's value.", good: "—" },
  marr: { term: "MARR (Minimum Acceptable Rate of Return)", what: "The yearly return you require: 15% in Rule #1.", why: "The future price is discounted back to today at this rate to find what you can pay and still earn 15% a year.", good: "15% is Phil Town's standard." },
  sticker_price: { term: "Sticker Price", what: "Future price discounted back 10 years at the MARR. Rule #1's estimate of what the business is worth today.", why: "It's the fair value. Rule #1 never pays fair value; it waits for a discount.", good: "—" },
  mos: { term: "MOS (Margin of Safety)", what: "Buying well below the Sticker Price, by default at 50% of it.", why: "The discount protects you if your estimates turn out too optimistic.", good: "Buy at or below the MOS price." },
  mos_price: { term: "MOS price", what: "Sticker Price × 50%: the price at or below which Rule #1 says to buy.", why: "This is the buy target that triggers the 🟢 Buy zone alert.", good: "Current price at or below it." },
  pct_from_mos: { term: "Price vs MOS", what: "How far the current price is above (+) or below (−) the MOS price.", why: "It shows how close a stock is to a buy.", good: "0% or negative means it's in the Buy zone." },
  owner_earnings: { term: "Owner earnings", what: "Net income + depreciation & amortization + income tax + change in payables − change in receivables − maintenance capital spending (estimated as half of capex).", why: "Buffett's measure of the cash an owner could take out of the business. It's used for the Ten Cap price.", good: "Positive and growing." },
  ten_cap: { term: "Ten Cap price", what: "Owner earnings per share × 10. The price at which owner earnings would be a 10% yearly return, like buying a rental property for its rent.", why: "It's a second, simpler valuation to confirm the Sticker Price.", good: "Current price at or below it." },
  payback_time: { term: "Payback Time price", what: "The total free cash flow per share over the next 8 years, growing at the growth rate.", why: "If you pay this or less, the company's own cash flow pays you back within 8 years.", good: "Current price at or below it." },
  tier_buy: { term: "🟢 Buy zone", what: "Price is at or below the MOS price and at least 4 of the Big Five pass.", why: "This is a Rule #1 buy signal, assuming you're happy with Meaning, Moat and Management.", good: "Do your own final research before buying." },
  tier_close: { term: "🟡 Getting close", what: "Price is within 10% above the MOS price and at least 4 of the Big Five pass.", why: "An early warning so you can finish your research before it hits the Buy zone.", good: "—" },
  tier_not_yet: { term: "⚪ Not yet", what: "The price is too high, the Big Five are too weak, or the numbers couldn't be calculated.", why: "Wonderful companies are worth waiting for.", good: "—" },
  stale: { term: "Stale", what: "The latest data couldn't be downloaded, so the last good results are shown.", why: "Stale results never send alerts, to avoid acting on old prices.", good: "It usually fixes itself on the next run." },
  growth_override: { term: "Growth override", what: "A growth rate you set yourself for this stock, replacing the automatic one.", why: "Use it when the automatic estimate looks wrong, e.g. after a one-off year.", good: "Be conservative. A decimal like 0.12 means 12%." },
};

let tip;
let current;

function hide() {
  if (tip) tip.hidden = true;
  current = null;
}

function show(btn) {
  const entry = GLOSSARY[btn.dataset.key];
  if (!entry) return;
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "tip";
    tip.setAttribute("role", "tooltip");
    document.body.append(tip);
  }
  tip.innerHTML = "";
  const h = document.createElement("strong");
  h.textContent = entry.term;
  tip.append(h);
  for (const [label, text] of [["What it is", entry.what], ["Why it matters", entry.why], ["What's good", entry.good]]) {
    if (!text || text === "—") continue;
    const p = document.createElement("p");
    const b = document.createElement("b");
    b.textContent = label + ": ";
    p.append(b, text);
    tip.append(p);
  }
  tip.hidden = false;
  const r = btn.getBoundingClientRect();
  const width = Math.min(320, window.innerWidth - 32);
  tip.style.width = width + "px";
  tip.style.left = Math.max(16, Math.min(r.left + window.scrollX - 8, window.scrollX + window.innerWidth - width - 16)) + "px";
  tip.style.top = r.bottom + window.scrollY + 6 + "px";
  current = btn;
}

export function attachTerms(root = document) {
  for (const el of root.querySelectorAll("[data-term]")) {
    if (el.querySelector(":scope > .info")) continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "info";
    btn.dataset.key = el.dataset.term;
    btn.textContent = "ⓘ";
    btn.setAttribute("aria-label", `What is ${GLOSSARY[el.dataset.term]?.term ?? el.textContent}?`);
    btn.addEventListener("click", (e) => { e.stopPropagation(); current === btn ? hide() : show(btn); });
    btn.addEventListener("mouseenter", () => { if (matchMedia("(hover: hover)").matches) show(btn); });
    btn.addEventListener("mouseleave", () => { if (matchMedia("(hover: hover)").matches) hide(); });
    el.append(btn);
  }
  if (!attachTerms.bound) {
    document.addEventListener("click", hide);
    document.addEventListener("keydown", (e) => e.key === "Escape" && hide());
    window.addEventListener("scroll", hide, { passive: true });
    attachTerms.bound = true;
  }
}
```

- [ ] **Step 6: Implement GitHub helpers** — `site/js/github.js`

```js
// Owner-only writes through the GitHub REST API using a fine-grained token kept in this browser.

const TOKEN_KEY = "r1.token";
const REPO_KEY = "r1.repo"; // optional override "owner/repo" for local testing
const BRANCH = "main";

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
}

export function setToken(token) {
  try { token ? localStorage.setItem(TOKEN_KEY, token.trim()) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
}

export function repoInfo(loc = window.location) {
  try {
    const override = localStorage.getItem(REPO_KEY);
    if (override && override.includes("/")) {
      const [owner, repo] = override.split("/");
      return { owner, repo };
    }
  } catch { /* storage blocked */ }
  const m = loc.hostname.match(/^([^.]+)\.github\.io$/i);
  if (!m) return null;
  const first = loc.pathname.split("/").filter(Boolean)[0];
  const repo = first && !first.endsWith(".html") ? first : `${m[1]}.github.io`;
  return { owner: m[1], repo };
}

export function actionsUrl() {
  const info = repoInfo();
  return info ? `https://github.com/${info.owner}/${info.repo}/actions` : "#";
}

async function api(path, options = {}) {
  const info = repoInfo();
  if (!info) throw new Error("Can't tell which GitHub repo this is. Open the dashboard from its github.io address.");
  const token = getToken();
  if (!token) throw new Error("Add your GitHub token first (🔑 Owner button at the top).");
  const res = await fetch(`https://api.github.com/repos/${info.owner}/${info.repo}${path}`, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const hint = res.status === 401 ? " Your token may be wrong or expired." :
      res.status === 403 || res.status === 404 ? " Check the token has Contents and Actions read/write access to this repo." : "";
    throw new Error(`GitHub said ${res.status}: ${body.message || res.statusText}.${hint}`);
  }
  return res.status === 204 ? null : res.json();
}

function encode(text) {
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function decode(b64) {
  const bin = atob(b64.replace(/\s/g, ""));
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}

export async function readJsonFile(path) {
  const file = await api(`/contents/${path}?ref=${BRANCH}`, { cache: "no-store" });
  return { sha: file.sha, data: JSON.parse(decode(file.content)) };
}

export async function updateJsonFile(path, mutate, message) {
  const { sha, data } = await readJsonFile(path);
  const next = mutate(structuredClone(data));
  await api(`/contents/${path}`, {
    method: "PUT",
    body: JSON.stringify({ message, content: encode(JSON.stringify(next, null, 2) + "\n"), sha, branch: BRANCH }),
  });
  return next;
}

export async function runAnalysisNow() {
  await api("/actions/workflows/analyze.yml/dispatches", { method: "POST", body: JSON.stringify({ ref: BRANCH }) });
}

export async function checkToken() {
  return api("");
}
```

- [ ] **Step 7: Implement shared page code** — `site/js/common.js`

```js
import { attachTerms } from "./glossary.js";
import { checkToken, getToken, setToken } from "./github.js";
import { TIERS, escapeHtml } from "./format.js";

export async function loadResults() {
  const res = await fetch("data/results.json", { cache: "no-store" });
  if (!res.ok) throw new Error("No results yet. The first analysis run hasn't finished.");
  return res.json();
}

export function term(key, text) {
  return `<span class="term" data-term="${key}">${escapeHtml(text)}</span>`;
}

export function badge(tier) {
  const t = TIERS[tier] || TIERS.not_yet;
  return `<span class="badge ${t.cls}" data-term="tier_${tier}">${t.emoji} ${t.label}</span>`;
}

export function toast(message, kind = "info") {
  let box = document.querySelector(".toasts");
  if (!box) {
    box = document.createElement("div");
    box.className = "toasts";
    box.setAttribute("aria-live", "polite");
    document.body.append(box);
  }
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = message;
  box.append(el);
  setTimeout(() => el.remove(), kind === "error" ? 12000 : 7000);
}

function refreshOwnerState() {
  document.body.classList.toggle("owner", !!getToken());
}

function ownerDialog() {
  const dlg = document.createElement("dialog");
  dlg.className = "owner-dialog";
  dlg.innerHTML = `
    <form method="dialog">
      <h2>Owner access</h2>
      <p>Paste a <b>fine-grained GitHub token</b> for this repo to add or remove stocks, edit settings and run the analysis.
         It's saved only in this browser. Visitors without it see a read-only dashboard.</p>
      <p class="muted">Create one at GitHub → Settings → Developer settings → Fine-grained tokens. Repository access: only this repo.
         Permissions: <b>Contents: read and write</b>, <b>Actions: read and write</b>.</p>
      <label>Token <input name="token" type="password" autocomplete="off" placeholder="github_pat_..." /></label>
      <div class="row">
        <button value="save" class="primary">Save</button>
        <button value="remove" class="danger">Remove token</button>
        <button value="cancel">Cancel</button>
      </div>
    </form>`;
  document.body.append(dlg);
  dlg.addEventListener("close", async () => {
    if (dlg.returnValue === "remove") {
      setToken("");
      toast("Token removed from this browser.");
    } else if (dlg.returnValue === "save") {
      const value = dlg.querySelector("input").value.trim();
      if (!value) return;
      setToken(value);
      try {
        await checkToken();
        toast("Token saved. Owner controls are on.", "ok");
      } catch (e) {
        toast(escapeHtml(e.message), "error");
      }
    }
    dlg.querySelector("input").value = "";
    refreshOwnerState();
  });
  return dlg;
}

export function initPage() {
  refreshOwnerState();
  const dlg = ownerDialog();
  document.querySelector("#owner-btn")?.addEventListener("click", () => dlg.showModal());
  attachTerms();
}
```

- [ ] **Step 8: Implement styles** — `site/css/style.css`

```css
:root {
  --bg: #f7f7f5; --surface: #ffffff; --text: #1d1d1f; --muted: #6b6b70; --border: #e2e2e0;
  --accent: #2f6fdb; --accent-text: #ffffff;
  --buy: #1f8a4c; --buy-bg: #e3f4ea; --close: #9a6b00; --close-bg: #fdf3d8; --not: #5f6368; --not-bg: #eeeeee;
  --bad: #c0392b; --warn-bg: #fff6e0; --tip-bg: #1d1d1f; --tip-text: #f5f5f5;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #131315; --surface: #1c1c1f; --text: #ececee; --muted: #9a9aa2; --border: #2e2e33;
    --accent: #6b9cff; --accent-text: #0b0b0c;
    --buy: #5fd394; --buy-bg: #163524; --close: #f2c14e; --close-bg: #3a2f12; --not: #b0b3b8; --not-bg: #2a2a2e;
    --bad: #ff7b6b; --warn-bg: #352b14; --tip-bg: #f5f5f5; --tip-text: #1d1d1f;
  }
}
:root[data-theme="dark"] {
  --bg: #131315; --surface: #1c1c1f; --text: #ececee; --muted: #9a9aa2; --border: #2e2e33;
  --accent: #6b9cff; --accent-text: #0b0b0c;
  --buy: #5fd394; --buy-bg: #163524; --close: #f2c14e; --close-bg: #3a2f12; --not: #b0b3b8; --not-bg: #2a2a2e;
  --bad: #ff7b6b; --warn-bg: #352b14; --tip-bg: #f5f5f5; --tip-text: #1d1d1f;
}

* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
a { color: var(--accent); }
header.top { display: flex; align-items: center; gap: 16px; padding: 12px 16px; background: var(--surface); border-bottom: 1px solid var(--border); flex-wrap: wrap; }
header.top .brand { font-weight: 700; text-decoration: none; color: var(--text); }
header.top nav { display: flex; gap: 14px; flex: 1; }
header.top nav a { text-decoration: none; color: var(--muted); }
header.top nav a.active { color: var(--text); font-weight: 600; }
main { max-width: 1100px; margin: 0 auto; padding: 20px 16px 60px; }
h1 { font-size: 1.6rem; margin: 0 0 4px; }
h2 { font-size: 1.15rem; margin: 0 0 12px; }
.muted { color: var(--muted); }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin: 16px 0; }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
.stat .label { color: var(--muted); font-size: 0.85rem; }
.stat .value { font-size: 1.35rem; font-weight: 650; }
.row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
button, .button { font: inherit; padding: 7px 12px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text); cursor: pointer; text-decoration: none; display: inline-block; }
button.primary, .button.primary { background: var(--accent); color: var(--accent-text); border-color: var(--accent); }
button.danger { color: var(--bad); }
button:disabled { opacity: 0.5; cursor: wait; }
input, select, textarea { font: inherit; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--bg); color: var(--text); }
textarea { width: 100%; min-height: 80px; }
label { display: grid; gap: 4px; }

.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }
th:first-child, td:first-child, th.left, td.left { text-align: left; }
th { font-size: 0.85rem; color: var(--muted); font-weight: 600; }
th.sortable { cursor: pointer; }
tr.clickable { cursor: pointer; }
tr.clickable:hover { background: var(--bg); }
.pass { color: var(--buy); font-weight: 600; }
.fail { color: var(--bad); font-weight: 600; }

.badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border-radius: 999px; font-size: 0.85rem; font-weight: 600; white-space: nowrap; }
.badge.buy { background: var(--buy-bg); color: var(--buy); }
.badge.close { background: var(--close-bg); color: var(--close); }
.badge.not-yet { background: var(--not-bg); color: var(--not); }
.banner { padding: 10px 14px; border-radius: 10px; background: var(--warn-bg); margin: 12px 0; }
.banner.error { color: var(--bad); }
ul.warnings { margin: 0; padding-left: 20px; }

.term { white-space: nowrap; }
.info { border: none; background: none; padding: 0 2px; margin-left: 2px; color: var(--muted); cursor: help; font-size: 0.85em; vertical-align: super; line-height: 1; }
.tip { position: absolute; z-index: 50; background: var(--tip-bg); color: var(--tip-text); padding: 10px 12px; border-radius: 10px; font-size: 0.85rem; box-shadow: 0 6px 24px rgba(0,0,0,.25); }
.tip p { margin: 6px 0 0; white-space: normal; }

.owner-only { display: none !important; }
body.owner .owner-only { display: revert !important; }
body.owner .owner-only.row { display: flex !important; }
dialog.owner-dialog { max-width: 520px; width: calc(100% - 32px); border: 1px solid var(--border); border-radius: 12px; background: var(--surface); color: var(--text); }
dialog.owner-dialog input { width: 100%; }
.toasts { position: fixed; bottom: 16px; left: 16px; right: 16px; display: grid; gap: 8px; justify-items: center; z-index: 60; pointer-events: none; }
.toast { max-width: 560px; background: var(--tip-bg); color: var(--tip-text); padding: 10px 14px; border-radius: 10px; pointer-events: auto; }
.toast a { color: inherit; }
.toast.error { background: var(--bad); color: #fff; }

.steps { counter-reset: step; list-style: none; padding: 0; margin: 0; }
.steps li { counter-increment: step; display: grid; grid-template-columns: 28px 1fr auto; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--border); align-items: baseline; }
.steps li::before { content: counter(step); font-weight: 700; color: var(--muted); }
.steps .value { font-weight: 650; font-variant-numeric: tabular-nums; text-align: right; }
.charts { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
.charts .chart { background: var(--bg); border-radius: 10px; padding: 8px; height: 200px; }
.prose { max-width: 720px; }
.prose h2 { margin-top: 28px; }
@media (max-width: 600px) {
  body { font-size: 14px; }
  .steps li { grid-template-columns: 24px 1fr; }
  .steps .value { grid-column: 2; text-align: left; }
}
```

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: dashboard foundation - styles, formatting, glossary, GitHub helpers"
```

---

### Task 11: Dashboard pages

**Files:**
- Create: `site/index.html`, `site/js/index.js`, `site/stock.html`, `site/js/stock.js`, `site/settings.html`, `site/js/settings.js`, `site/guide.html`

**Interfaces:**
- Consumes: `format.js`, `glossary.js`, `github.js`, `common.js` (Task 10); `results.json` shape (Task 9); `data/csv/*.csv` (Task 8).

- [ ] **Step 1: Shared page header** — every page uses this header (with the matching `active` class):

```html
<header class="top">
  <a class="brand" href="index.html">Rule #1 Analyzer</a>
  <nav>
    <a href="index.html">Watchlist</a>
    <a href="guide.html">Guide</a>
    <a href="settings.html">Settings</a>
  </nav>
  <button id="owner-btn" type="button" title="Owner access">🔑 Owner</button>
</header>
```

- [ ] **Step 2: Watchlist page** — `site/index.html`

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Rule #1 Watchlist</title>
  <link rel="stylesheet" href="css/style.css" />
</head>
<body>
<header class="top">
  <a class="brand" href="index.html">Rule #1 Analyzer</a>
  <nav>
    <a href="index.html" class="active">Watchlist</a>
    <a href="guide.html">Guide</a>
    <a href="settings.html">Settings</a>
  </nav>
  <button id="owner-btn" type="button" title="Owner access">🔑 Owner</button>
</header>
<main>
  <h1>Watchlist</h1>
  <p class="muted" id="updated">Loading…</p>

  <section class="card owner-only">
    <form id="add-form" class="row">
      <input id="add-symbol" placeholder="Ticker, e.g. COST" aria-label="Ticker to add" maxlength="10" required />
      <button class="primary">Add stock</button>
      <button type="button" id="run-now">Analyze now</button>
      <span class="muted">Changes show up after the analysis finishes (about 1–2 minutes).</span>
    </form>
  </section>

  <section class="card">
    <div class="table-wrap">
      <table id="watchlist">
        <thead><tr>
          <th class="sortable" data-sort="symbol">Stock</th>
          <th class="sortable left" data-sort="tier">Status</th>
          <th class="sortable" data-sort="price">Price</th>
          <th class="sortable" data-sort="mos"><span class="term" data-term="mos_price">MOS price</span></th>
          <th class="sortable" data-sort="sticker"><span class="term" data-term="sticker_price">Sticker</span></th>
          <th class="sortable" data-sort="pct"><span class="term" data-term="pct_from_mos">vs MOS</span></th>
          <th class="sortable" data-sort="score"><span class="term" data-term="big_five_score">Big Five</span></th>
          <th class="sortable" data-sort="debt"><span class="term" data-term="debt">Debt yrs</span></th>
          <th class="owner-only"></th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <p id="empty" class="muted" hidden>No stocks yet. Use 🔑 Owner to add your token, then add a ticker.</p>
  </section>

  <section class="row">
    <a class="button" href="data/csv/watchlist.csv" download>Download watchlist CSV</a>
    <a class="button" href="data/results.json" target="_blank" rel="noopener">Raw results JSON</a>
  </section>
  <p class="muted">Data: SEC EDGAR filings and Yahoo Finance. This is a research tool, not financial advice.</p>
</main>
<script type="module" src="js/index.js"></script>
</body>
</html>
```

`site/js/index.js`:
```js
import { badge, initPage, loadResults, toast } from "./common.js";
import { attachTerms } from "./glossary.js";
import { escapeHtml, money, num, signedPct } from "./format.js";
import { actionsUrl, getToken, readJsonFile, runAnalysisNow, updateJsonFile } from "./github.js";

const RANK = { buy: 0, close: 1, not_yet: 2 };
const SORTERS = {
  symbol: (s) => s.symbol,
  tier: (s) => RANK[s.tier] ?? 3,
  price: (s) => s.price,
  mos: (s) => s.valuation?.mos_price,
  sticker: (s) => s.valuation?.sticker_price,
  pct: (s) => s.valuation?.pct_from_mos,
  score: (s) => -(s.big_five?.score ?? -1),
  debt: (s) => s.big_five?.debt?.payoff_years,
};
let stocks = [];
let sortKey = "tier";
let sortDir = 1;

function sorted() {
  const f = SORTERS[sortKey];
  return [...stocks].sort((a, b) => {
    const x = f(a), y = f(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
  });
}

function row(s) {
  const v = s.valuation || {}, bf = s.big_five || {};
  const flags = [s.stale ? `<span class="term" data-term="stale" title="${escapeHtml(s.stale_reason)}">stale</span>` : "",
    s.error ? `<span class="fail" title="${escapeHtml(s.error)}">error</span>` : "",
    s.pending ? `<span class="muted">waiting for analysis</span>` : ""].filter(Boolean).join(" ");
  const debt = bf.debt;
  const debtCell = !debt ? "—" : `<span class="${debt.pass ? "pass" : "fail"}">${debt.payoff_years == null ? "n/a" : num(debt.payoff_years, 1)}</span>`;
  return `<tr class="clickable" data-symbol="${escapeHtml(s.symbol)}" data-pending="${s.pending ? "1" : ""}">
    <td><b>${escapeHtml(s.symbol)}</b><br><span class="muted">${escapeHtml(s.name || "")}</span> ${flags}</td>
    <td class="left">${badge(s.tier || "not_yet")}</td>
    <td>${money(s.price)}</td>
    <td>${money(v.mos_price)}</td>
    <td>${money(v.sticker_price)}</td>
    <td>${signedPct(v.pct_from_mos)}</td>
    <td>${bf.score == null ? "—" : `${bf.score}/5`}</td>
    <td>${debtCell}</td>
    <td class="owner-only"><button class="danger" data-remove="${escapeHtml(s.symbol)}" title="Remove from watchlist">✕</button></td>
  </tr>`;
}

function render() {
  const tbody = document.querySelector("#watchlist tbody");
  tbody.innerHTML = sorted().map(row).join("");
  document.querySelector("#empty").hidden = stocks.length > 0;
  attachTerms(tbody);
}

function queued(what) {
  toast(`${what} Results in about 1–2 minutes. <a href="${actionsUrl()}" target="_blank" rel="noopener">Watch the run</a>`, "ok");
}

async function addPending() {
  if (!getToken()) return;
  try {
    const { data } = await readJsonFile("watchlist.json");
    const known = new Set(stocks.map((s) => s.symbol));
    for (const t of data.tickers) {
      if (!known.has(t.symbol)) stocks.push({ symbol: t.symbol, name: "", tier: "not_yet", pending: true });
    }
    render();
  } catch { /* token problems are reported when the owner acts */ }
}

async function onAdd(e) {
  e.preventDefault();
  const input = document.querySelector("#add-symbol");
  const symbol = input.value.trim().toUpperCase().replace(".", "-");
  if (!/^[A-Z][A-Z0-9-]{0,9}$/.test(symbol)) return toast("That doesn't look like a ticker symbol.", "error");
  const btn = e.submitter;
  btn.disabled = true;
  try {
    await updateJsonFile("watchlist.json", (w) => {
      if (w.tickers.some((t) => t.symbol === symbol)) throw new Error(`${symbol} is already on the watchlist.`);
      w.tickers.push({ symbol, added: new Date().toISOString().slice(0, 10), notes: "", growth_override: null });
      return w;
    }, `Add ${symbol} to watchlist`);
    input.value = "";
    stocks.push({ symbol, name: "", tier: "not_yet", pending: true });
    render();
    queued(`${symbol} added.`);
  } catch (err) {
    toast(escapeHtml(err.message), "error");
  } finally {
    btn.disabled = false;
  }
}

async function onRemove(symbol) {
  if (!confirm(`Remove ${symbol} from the watchlist?`)) return;
  try {
    await updateJsonFile("watchlist.json", (w) => ({ ...w, tickers: w.tickers.filter((t) => t.symbol !== symbol) }),
      `Remove ${symbol} from watchlist`);
    stocks = stocks.filter((s) => s.symbol !== symbol);
    render();
    queued(`${symbol} removed.`);
  } catch (err) {
    toast(escapeHtml(err.message), "error");
  }
}

async function onRunNow(e) {
  e.target.disabled = true;
  try {
    await runAnalysisNow();
    queued("Analysis started.");
  } catch (err) {
    toast(escapeHtml(err.message), "error");
  } finally {
    e.target.disabled = false;
  }
}

async function main() {
  initPage();
  document.querySelector("#add-form").addEventListener("submit", onAdd);
  document.querySelector("#run-now").addEventListener("click", onRunNow);
  document.querySelectorAll("th.sortable").forEach((th) => th.addEventListener("click", (e) => {
    if (e.target.closest(".info")) return;
    const key = th.dataset.sort;
    sortDir = key === sortKey ? -sortDir : 1;
    sortKey = key;
    render();
  }));
  document.querySelector("#watchlist tbody").addEventListener("click", (e) => {
    const remove = e.target.closest("[data-remove]");
    if (remove) return onRemove(remove.dataset.remove);
    if (e.target.closest(".info")) return;
    const tr = e.target.closest("tr[data-symbol]");
    if (tr && !tr.dataset.pending) location.href = `stock.html?t=${encodeURIComponent(tr.dataset.symbol)}`;
  });
  try {
    const results = await loadResults();
    stocks = results.stocks;
    document.querySelector("#updated").textContent = `Last analyzed ${new Date(results.generated_at).toLocaleString()}`;
  } catch (err) {
    document.querySelector("#updated").textContent = err.message;
  }
  render();
  addPending();
}

main();
```

- [ ] **Step 3: Stock detail page** — `site/stock.html`

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Stock Analysis</title>
  <link rel="stylesheet" href="css/style.css" />
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
</head>
<body>
<header class="top">
  <a class="brand" href="index.html">Rule #1 Analyzer</a>
  <nav>
    <a href="index.html">Watchlist</a>
    <a href="guide.html">Guide</a>
    <a href="settings.html">Settings</a>
  </nav>
  <button id="owner-btn" type="button" title="Owner access">🔑 Owner</button>
</header>
<main id="content"><p class="muted">Loading…</p></main>
<script type="module" src="js/stock.js"></script>
</body>
</html>
```

`site/js/stock.js`:
```js
import { badge, initPage, loadResults, term, toast } from "./common.js";
import { attachTerms } from "./glossary.js";
import { bigMoney, escapeHtml, historyRows, money, num, pct, signedPct, stockMarkdown, toTsv } from "./format.js";
import { actionsUrl, updateJsonFile } from "./github.js";

const METRIC_TERMS = { roic: "roic", sales: "sales_growth", eps: "eps_growth", equity: "equity_growth", fcf: "fcf_growth" };
const CHARTS = [["revenue", "Revenue", bigMoney], ["eps_diluted", "EPS", money], ["bvps", "Book value per share", money],
  ["fcf", "Free cash flow", bigMoney], ["roic", "ROIC", pct]];

const stat = (label, value, key) => `<div class="stat"><div class="label">${key ? term(key, label) : escapeHtml(label)}</div><div class="value">${value}</div></div>`;

function windowCell(w) {
  if (!w.available) return `<td class="muted" title="Not enough history">—</td>`;
  if (w.value == null) return `<td class="fail" title="${escapeHtml(w.note || "")}">n/a</td>`;
  return `<td class="${w.pass ? "pass" : "fail"}" title="${escapeHtml(w.note || `${w.start_year}–${w.end_year}`)}">${pct(w.value)} ${w.pass ? "✓" : "✗"}</td>`;
}

function bigFiveSection(bf) {
  const rows = Object.entries(bf.metrics).map(([key, m]) => `<tr>
      <td>${term(METRIC_TERMS[key], m.label)}</td>
      ${["10", "5", "3", "1"].map((k) => windowCell(m.windows[k])).join("")}
      <td class="${m.pass ? "pass" : "fail"}">${m.pass ? "Pass" : "Fail"}${m.trend_ok ? "" : " (falling)"}</td>
    </tr>`).join("");
  const d = bf.debt;
  return `<section class="card">
    <h2>${term("big_five", "Big Five")}: ${bf.score} of 5 pass</h2>
    <p class="muted">Each number should be at least 10% over the ${term("windows", "10, 5, 3 and 1-year windows")}. Hover a cell to see the years used.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Number</th><th>10 yr</th><th>5 yr</th><th>3 yr</th><th>1 yr</th><th>Result</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <p>${term("debt", "Debt payoff")}: <b class="${d.pass ? "pass" : "fail"}">${d.payoff_years == null ? "can't be paid from cash flow" : num(d.payoff_years, 1) + " years"}</b>
      <span class="muted">(${bigMoney(d.total_debt)} long-term debt ÷ ${bigMoney(d.fcf)} free cash flow in ${d.year}; should be 3 years or less)</span></p>
  </section>`;
}

function valuationSection(v, settings) {
  const step = (label, key, value, explain) => `<li><div>${term(key, label)}<div class="muted">${explain}</div></div><div class="value">${value}</div></li>`;
  const steps = v.computable ? [
    step("Growth rate used", "growth_rate", pct(v.growth_rate), `Source: ${escapeHtml(v.growth_source)}. Historical equity growth ${pct(v.equity_growth)}, analyst estimate ${pct(v.analyst_growth)}.`),
    step("Current EPS", "eps", money(v.current_eps), `From the ${v.eps_year} annual report (diluted, split-adjusted).`),
    step("Future EPS", "future_eps", money(v.future_eps), `${money(v.current_eps)} × (1 + ${pct(v.growth_rate)})¹⁰`),
    step("Future P/E", "future_pe", num(v.future_pe, 1), `Lower of 2 × growth (${num(v.pe_from_growth, 1)}) and the ${v.historical_pe_years}-year average P/E (${num(v.historical_pe_avg, 1)}), max ${settings.pe_cap}.`),
    step("Future price", "future_price", money(v.future_price), `${money(v.future_eps)} × ${num(v.future_pe, 1)}`),
    step("Sticker Price", "sticker_price", money(v.sticker_price), `${money(v.future_price)} ÷ (1 + ${pct(settings.marr, 0)})¹⁰, discounted at the ${term("marr", "MARR")}`),
    step("MOS price", "mos_price", money(v.mos_price), `${money(v.sticker_price)} × ${pct(settings.mos_fraction, 0)}`),
  ].join("") : "";
  return `<section class="card">
    <h2>Valuation, step by step</h2>
    ${v.computable ? `<ol class="steps">${steps}</ol>` : `<p class="banner">The Sticker Price couldn't be calculated. See the warnings below.</p>`}
    <h2 style="margin-top:20px">Extra checks</h2>
    <div class="grid">
      ${stat("Ten Cap price", money(v.ten_cap_price), "ten_cap")}
      ${stat("Payback Time price", money(v.payback_price), "payback_time")}
      ${stat("Owner earnings / share", money(v.owner_earnings_ps), "owner_earnings")}
      ${stat("Free cash flow / share", money(v.fcf_ps), "fcf")}
    </div>
  </section>`;
}

function inputsSection(s) {
  return `<section class="card owner-only">
    <h2>Your inputs</h2>
    <form id="inputs-form" class="grid">
      <label>Notes (your Meaning / Moat / Management thoughts)<textarea name="notes">${escapeHtml(s.notes || "")}</textarea></label>
      <label>${term("growth_override", "Growth override")} <span class="muted">(decimal, e.g. 0.12; leave empty for automatic)</span>
        <input name="override" inputmode="decimal" value="${s.growth_override ?? ""}" /></label>
      <div class="row"><button class="primary">Save inputs</button></div>
    </form>
  </section>`;
}

function render(s, results) {
  const v = s.valuation;
  document.title = `${s.symbol} – Rule #1`;
  const banners = [
    s.error ? `<p class="banner error">${escapeHtml(s.error)}</p>` : "",
    s.stale ? `<p class="banner">${term("stale", "Stale data")}: ${escapeHtml(s.stale_reason)}</p>` : "",
    s.growth_override != null ? `<p class="banner">Using your growth override of ${pct(s.growth_override)}.</p>` : "",
  ].join("");
  const head = `<h1>${escapeHtml(s.symbol)} <span class="muted">${escapeHtml(s.name)}</span></h1>
    <p>${badge(s.tier)} ${escapeHtml(s.tier_reason)}</p>${banners}`;
  if (s.error) return head + inputsSection(s);
  return head + `
    <section class="card grid">
      ${stat("Price", money(s.price))}
      ${stat("MOS price", money(v.mos_price), "mos_price")}
      ${stat("Sticker Price", money(v.sticker_price), "sticker_price")}
      ${stat("Price vs MOS", signedPct(v.pct_from_mos), "pct_from_mos")}
      ${stat("Big Five score", `${s.big_five.score} / 5`, "big_five_score")}
    </section>
    ${bigFiveSection(s.big_five)}
    <section class="card"><h2>Trends by year</h2><div class="charts">
      ${CHARTS.map(([f, label]) => `<div class="chart"><canvas data-field="${f}" aria-label="${label} by year"></canvas></div>`).join("")}
    </div></section>
    ${valuationSection(v, results.settings)}
    ${s.warnings.length ? `<section class="card"><h2>Data warnings</h2><ul class="warnings">${s.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul></section>` : ""}
    ${inputsSection(s)}
    <section class="card">
      <h2>Use this data</h2>
      <p class="muted">Copy everything for a spreadsheet or for an AI chat / notes.</p>
      <div class="row">
        <button id="copy-table">Copy as table</button>
        <button id="copy-md">Copy for AI / notes</button>
        <a class="button" href="data/csv/${encodeURIComponent(s.symbol)}.csv" download>Download CSV</a>
      </div>
    </section>
    <p class="muted">Analyzed ${new Date(s.as_of).toLocaleString()}. Data: SEC EDGAR and Yahoo Finance. Not financial advice.</p>`;
}

function drawCharts(s) {
  if (!window.Chart) return;
  const css = getComputedStyle(document.documentElement);
  const color = css.getPropertyValue("--accent").trim();
  const grid = css.getPropertyValue("--border").trim();
  const text = css.getPropertyValue("--muted").trim();
  for (const canvas of document.querySelectorAll("canvas[data-field]")) {
    const [field, label, fmt] = CHARTS.find(([f]) => f === canvas.dataset.field);
    const years = s.history.years;
    const data = years.map((y) => s.history[field]?.[String(y)] ?? null);
    new window.Chart(canvas, {
      type: "bar",
      data: { labels: years, datasets: [{ label, data, backgroundColor: color, borderRadius: 3 }] },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, title: { display: true, text: label, color: text },
                   tooltip: { callbacks: { label: (c) => fmt(c.raw) } } },
        scales: { x: { ticks: { color: text }, grid: { display: false } },
                  y: { ticks: { color: text, callback: (v) => fmt(v) }, grid: { color: grid } } },
      },
    });
  }
}

async function copy(text, what) {
  try {
    await navigator.clipboard.writeText(text);
    toast(`${what} copied.`, "ok");
  } catch {
    toast("Your browser blocked copying. Use Download CSV instead.", "error");
  }
}

function wire(s, results) {
  document.querySelector("#copy-table")?.addEventListener("click", () => copy(toTsv(historyRows(s, results.columns)), "Table"));
  document.querySelector("#copy-md")?.addEventListener("click", () => copy(stockMarkdown(s, results.columns), "Summary"));
  document.querySelector("#inputs-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    const raw = String(form.get("override") || "").trim();
    const override = raw === "" ? null : Number(raw);
    if (override !== null && !(override > 0 && override <= 1)) return toast("Growth override must be a decimal between 0 and 1, e.g. 0.12.", "error");
    const btn = e.submitter;
    btn.disabled = true;
    try {
      await updateJsonFile("watchlist.json", (w) => {
        const t = w.tickers.find((x) => x.symbol === s.symbol);
        if (!t) throw new Error(`${s.symbol} is no longer on the watchlist.`);
        t.notes = String(form.get("notes") || "");
        t.growth_override = override;
        return w;
      }, `Update ${s.symbol} inputs`);
      toast(`Saved. The analysis re-runs in about 1–2 minutes. <a href="${actionsUrl()}" target="_blank" rel="noopener">Watch the run</a>`, "ok");
    } catch (err) {
      toast(escapeHtml(err.message), "error");
    } finally {
      btn.disabled = false;
    }
  });
}

async function main() {
  initPage();
  const container = document.querySelector("#content");
  const symbol = new URLSearchParams(location.search).get("t");
  try {
    const results = await loadResults();
    const s = results.stocks.find((x) => x.symbol === symbol);
    if (!s) {
      container.innerHTML = `<p class="banner">${escapeHtml(symbol || "That stock")} isn't in the latest results. <a href="index.html">Back to the watchlist</a></p>`;
      return;
    }
    container.innerHTML = render(s, results);
    attachTerms(container);
    wire(s, results);
    if (s.history) drawCharts(s);
  } catch (err) {
    container.innerHTML = `<p class="banner error">${escapeHtml(err.message)}</p>`;
  }
}

main();
```

- [ ] **Step 4: Settings page** — `site/settings.html`

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Analyzer Settings</title>
  <link rel="stylesheet" href="css/style.css" />
</head>
<body>
<header class="top">
  <a class="brand" href="index.html">Rule #1 Analyzer</a>
  <nav>
    <a href="index.html">Watchlist</a>
    <a href="guide.html">Guide</a>
    <a href="settings.html" class="active">Settings</a>
  </nav>
  <button id="owner-btn" type="button" title="Owner access">🔑 Owner</button>
</header>
<main>
  <h1>Settings</h1>
  <p class="muted">The thresholds the analysis uses. Defaults follow Phil Town's Rule #1 book. Only the owner can change them.</p>
  <form id="settings-form" class="card"></form>
</main>
<script type="module" src="js/settings.js"></script>
</body>
</html>
```

`site/js/settings.js`:
```js
import { initPage, loadResults, term, toast } from "./common.js";
import { attachTerms } from "./glossary.js";
import { escapeHtml } from "./format.js";
import { actionsUrl, getToken, updateJsonFile } from "./github.js";

// kind "pct": stored as a decimal, edited as a percent.
const FIELDS = [
  { key: "marr", label: "Minimum acceptable return (MARR)", kind: "pct", glossary: "marr", help: "Yearly return you require. Rule #1 uses 15%." },
  { key: "mos_fraction", label: "MOS price as % of Sticker Price", kind: "pct", glossary: "mos", help: "Rule #1 buys at 50% of the Sticker Price." },
  { key: "growth_cap", label: "Maximum growth rate", kind: "pct", glossary: "growth_rate", help: "Caps the growth rate used for the Sticker Price." },
  { key: "pe_cap", label: "Maximum Future P/E", kind: "num", glossary: "future_pe", help: "Caps the Future P/E." },
  { key: "big_five_threshold", label: "Big Five passing bar", kind: "pct", glossary: "big_five", help: "Each window must reach this. Rule #1 uses 10%." },
  { key: "big_five_min_score", label: "Big Five numbers needed for alerts", kind: "int", glossary: "big_five_score", help: "How many of the 5 must pass for Buy zone / Getting close." },
  { key: "windows_to_pass", label: "Windows needed per number", kind: "int", glossary: "windows", help: "How many of the 10/5/3/1-year windows must pass." },
  { key: "trend_tolerance", label: "Allowed recent drop", kind: "pct", glossary: "windows", help: "A number fails if its 1-year value is more than this below its longest window." },
  { key: "debt_payoff_max_years", label: "Maximum debt payoff years", kind: "num", glossary: "debt", help: "Rule #1 wants debt payable within 3 years of free cash flow." },
  { key: "getting_close_margin", label: "Getting close range", kind: "pct", glossary: "tier_close", help: "Alert when price is within this % above the MOS price." },
  { key: "payback_years", label: "Payback Time years", kind: "int", glossary: "payback_time", help: "Years of cash flow used for the Payback Time price." },
];

const toInput = (f, v) => (f.kind === "pct" ? +(v * 100).toFixed(4) : v);
const fromInput = (f, raw) => (f.kind === "pct" ? Number(raw) / 100 : Number(raw));

function render(form, settings) {
  const owner = !!getToken();
  form.innerHTML = FIELDS.map((f) => `
    <label>
      <span>${term(f.glossary, f.label)}</span>
      <span class="row"><input name="${f.key}" type="number" step="${f.kind === "int" ? 1 : "any"}" value="${toInput(f, settings[f.key])}" ${owner ? "" : "disabled"} />
        ${f.kind === "pct" ? "%" : ""}</span>
      <span class="muted">${escapeHtml(f.help)}</span>
    </label>`).join("<hr>") + `<div class="row owner-only" style="margin-top:16px"><button class="primary">Save settings</button></div>`;
  attachTerms(form);
}

async function main() {
  initPage();
  const form = document.querySelector("#settings-form");
  let settings;
  try {
    settings = (await loadResults()).settings;
  } catch (err) {
    form.innerHTML = `<p class="banner">${escapeHtml(err.message)}</p>`;
    return;
  }
  render(form, settings);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = new FormData(form);
    const next = {};
    for (const f of FIELDS) {
      const value = fromInput(f, data.get(f.key));
      if (!Number.isFinite(value)) return toast(`${escapeHtml(f.label)} needs a number.`, "error");
      next[f.key] = f.kind === "int" ? Math.round(value) : value;
    }
    const btn = e.submitter;
    btn.disabled = true;
    try {
      await updateJsonFile("settings.json", () => next, "Update analyzer settings");
      toast(`Settings saved. The analysis re-runs in about 1–2 minutes. <a href="${actionsUrl()}" target="_blank" rel="noopener">Watch the run</a>`, "ok");
    } catch (err) {
      toast(escapeHtml(err.message), "error");
    } finally {
      btn.disabled = false;
    }
  });
}

main();
```

- [ ] **Step 5: Guide page** — `site/guide.html`

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Rule #1 Guide</title>
  <link rel="stylesheet" href="css/style.css" />
</head>
<body>
<header class="top">
  <a class="brand" href="index.html">Rule #1 Analyzer</a>
  <nav>
    <a href="index.html">Watchlist</a>
    <a href="guide.html" class="active">Guide</a>
    <a href="settings.html">Settings</a>
  </nav>
  <button id="owner-btn" type="button" title="Owner access">🔑 Owner</button>
</header>
<main class="prose">
  <h1>How Rule #1 works, and how to read this dashboard</h1>
  <p>Tap or hover any <b>ⓘ</b> for a plain-English explanation of a term.</p>

  <h2>1. The idea</h2>
  <p><span class="term" data-term="rule1">Rule #1</span> means buying wonderful businesses at a big discount to what they're worth, so you're unlikely to lose money. A business is "wonderful" when it passes <span class="term" data-term="four_ms">the 4 Ms</span>.</p>

  <h2>2. What you decide, and what the tool checks</h2>
  <p>You decide <span class="term" data-term="meaning">Meaning</span>, <span class="term" data-term="moat">Moat</span> and <span class="term" data-term="management">Management</span> when you put a company on your watchlist. Write your reasoning in the notes on each stock page.</p>
  <p>The tool checks the numbers: the <span class="term" data-term="big_five">Big Five</span>, the <span class="term" data-term="debt">debt</span>, and the price compared with the <span class="term" data-term="mos_price">MOS price</span>.</p>

  <h2>3. The Big Five</h2>
  <p>Five numbers should each be at least 10% over the last <span class="term" data-term="windows">10, 5, 3 and 1 years</span>:</p>
  <ul>
    <li><span class="term" data-term="roic">ROIC</span>: profit earned on the money invested in the business.</li>
    <li><span class="term" data-term="sales_growth">Sales growth</span>: revenue growth per year.</li>
    <li><span class="term" data-term="eps_growth">EPS growth</span>: profit-per-share growth per year.</li>
    <li><span class="term" data-term="equity_growth">Equity growth</span>: growth of what shareholders own, per share.</li>
    <li><span class="term" data-term="fcf_growth">Free cash flow growth</span>: growth of the spare cash the business produces.</li>
  </ul>
  <p>Growth numbers use <span class="term" data-term="cagr">CAGR</span>. The <span class="term" data-term="big_five_score">Big Five score</span> counts how many pass.</p>

  <h2>4. What the business is worth</h2>
  <ol>
    <li>Pick a <span class="term" data-term="growth_rate">growth rate</span>: the lower of past equity growth and the <span class="term" data-term="analyst_growth">analysts' estimate</span>.</li>
    <li>Grow today's <span class="term" data-term="eps">EPS</span> for 10 years to get <span class="term" data-term="future_eps">Future EPS</span>.</li>
    <li>Multiply by a conservative <span class="term" data-term="future_pe">Future P/E</span> to get the <span class="term" data-term="future_price">Future price</span>.</li>
    <li>Discount it back 10 years at the 15% <span class="term" data-term="marr">MARR</span>. That's the <span class="term" data-term="sticker_price">Sticker Price</span>.</li>
    <li>Halve it for a <span class="term" data-term="mos">Margin of Safety</span>. That's the <span class="term" data-term="mos_price">MOS price</span>: the buy price.</li>
  </ol>
  <p>Two simpler checks confirm the result: the <span class="term" data-term="ten_cap">Ten Cap price</span> and the <span class="term" data-term="payback_time">Payback Time price</span>.</p>

  <h2>5. Status and email alerts</h2>
  <ul>
    <li><span class="term" data-term="tier_buy">🟢 Buy zone</span>: at or below the MOS price, with at least 4 of the Big Five passing.</li>
    <li><span class="term" data-term="tier_close">🟡 Getting close</span>: within 10% above the MOS price.</li>
    <li><span class="term" data-term="tier_not_yet">⚪ Not yet</span>: everything else.</li>
  </ul>
  <p>The analysis runs every weekday after the US market closes. You get one email when a stock moves <b>into</b> a better status, not every day it stays there.</p>

  <h2>6. Reading a stock page</h2>
  <ul>
    <li><b>Big Five table:</b> ✓ and ✗ for each window. Hover a cell to see which years were used.</li>
    <li><b>Valuation, step by step:</b> every number with the formula that produced it.</li>
    <li><b>Data warnings:</b> where the data was thin or unusual. Read them before trusting a number.</li>
    <li><b>Use this data:</b> copy the yearly numbers into a spreadsheet, or a summary into an AI chat or your notes.</li>
  </ul>

  <h2>7. Limits</h2>
  <p>Numbers come from company filings with the SEC and from Yahoo Finance. Filings vary between companies, so check the warnings. Rule #1 also uses judgement the tool can't do for you. This is a research tool, not financial advice.</p>
</main>
<script type="module">
  import { initPage } from "./js/common.js";
  initPage();
</script>
</body>
</html>
```

- [ ] **Step 6: Manual check in the browser**

Run (after Task 9 Step 6 produced `data/`):
```bash
rm -rf site/data && cp -r data site/data && python -m http.server 8000 -d site
```
Open `http://localhost:8000/`. Check:
- Watchlist table shows 3 stocks with badges; sorting by each column works; clicking a row opens the stock page.
- ⓘ tooltips appear on hover and tap and close with Escape or clicking elsewhere.
- Stock page: Big Five table, 5 charts, valuation steps with real numbers, warnings, copy buttons (paste the TSV into a spreadsheet and the Markdown into a text editor), and the CSV download works.
- Settings and Guide pages render; Guide ⓘ icons work.
- Owner controls are hidden without a token.
- Phone width (DevTools 375px): no horizontal page scroll, except inside table wrappers.
- Dark mode (OS setting) is readable.

Stop the server with Ctrl+C.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: dashboard pages - watchlist, stock detail, settings, guide"
```

---

### Task 12: GitHub Actions workflow, README, publish

**Files:**
- Create: `.github/workflows/analyze.yml`, `README.md`

- [ ] **Step 1: Workflow** — `.github/workflows/analyze.yml`

```yaml
name: Analyze watchlist

on:
  schedule:
    - cron: "0 22 * * 1-5"   # weekdays 22:00 UTC, after the US market closes
  workflow_dispatch:
  push:
    branches: [main]
    paths: [watchlist.json, settings.json]

concurrency:
  group: analyze
  cancel-in-progress: false

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: pip install -r requirements.txt
      - name: Run tests
        run: |
          python -m pytest -q
          node --test tests/js/
      - name: Analyze and send alerts
        env:
          SEC_USER_AGENT: ${{ secrets.SEC_USER_AGENT }}
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          ALERT_EMAIL_TO: ${{ secrets.ALERT_EMAIL_TO }}
        run: python -m engine.main
      - name: Save results
        if: always()
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data
          if git diff --cached --quiet; then echo "No result changes"; exit 0; fi
          git commit -m "Update analysis results"
          git pull --rebase origin main
          git push

  deploy:
    needs: analyze
    if: always()
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main
      - name: Bundle site with latest data
        run: |
          mkdir -p site/data
          if [ -d data ]; then cp -r data/. site/data/; fi
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: README** — `README.md`

````markdown
# Rule #1 Analyzer

Analyzes your watchlist of US stocks with Phil Town's **Rule #1** method, emails you when a stock gets
close to (or into) its buy price, and publishes a dashboard that explains every number.

- **Daily**: on weekdays after the US market closes, GitHub Actions downloads SEC filings and Yahoo prices,
  computes the Big Five, Sticker Price, MOS price, Ten Cap and Payback Time, and updates the dashboard.
- **Email**: one message when a stock moves into 🟡 Getting close or 🟢 Buy zone.
- **Dashboard**: plain-English ⓘ explanations, step-by-step valuation, and copy/CSV buttons for deeper research.

## One-time setup

1. **Create the repo.** Make a new **public** GitHub repo and push this folder to its `main` branch.
   (A free account needs a public repo for GitHub Pages. Your secrets stay private, see "Privacy" below.)
2. **Gmail app password.** Turn on 2-Step Verification for your Google account, then create an app password at
   <https://myaccount.google.com/apppasswords>. Copy the 16-character password.
3. **Add repo secrets.** In the repo: Settings → Secrets and variables → Actions → New repository secret.
   | Name | Value |
   |---|---|
   | `GMAIL_ADDRESS` | the Gmail address that sends alerts |
   | `GMAIL_APP_PASSWORD` | the app password from step 2 |
   | `ALERT_EMAIL_TO` | where alerts go (can be the same address) |
   | `SEC_USER_AGENT` | your name and email, e.g. `Jane Doe jane@example.com` (the SEC requires a contact) |
4. **Turn on Pages.** Settings → Pages → Source: **GitHub Actions**.
5. **Create a dashboard token.** GitHub → Settings → Developer settings → Fine-grained tokens → Generate.
   Repository access: **only this repo**. Permissions: **Contents: read and write**, **Actions: read and write**.
6. **First run.** Actions tab → "Analyze watchlist" → Run workflow. When it finishes, open
   `https://<your-username>.github.io/<repo-name>/`, click **🔑 Owner**, paste the token, and add tickers.

## Everyday use

- Add or remove stocks and click **Analyze now** on the dashboard. Results appear in about 1–2 minutes.
- Open a stock to see the Big Five, the valuation steps and warnings. Use **Copy as table** for a spreadsheet,
  or **Copy for AI / notes** for a Markdown summary.
- Change thresholds on the **Settings** page.

## Privacy

Anyone with the link can **view** the dashboard, your watchlist and settings. Only you can **change** them:
edits need your token, which lives only in your browser. The Gmail password lives in GitHub Secrets and is never
shown. Pull requests from strangers can't read secrets; you can also turn off Issues and Pull requests in the
repo settings.

## Running locally

```bash
python -m pip install -r requirements.txt
python -m pytest -q && node --test tests/js/
SEC_USER_AGENT="Your Name you@example.com" python -m engine.main --no-email
cp -r data site/data && python -m http.server 8000 -d site    # open http://localhost:8000
```

To test owner features locally, set the repo in the browser console: `localStorage.setItem("r1.repo", "owner/repo")`.

## How the numbers are calculated

See [the design spec](docs/superpowers/specs/2026-10-06-rule-one-analyzer-design.md) §4 and the dashboard's Guide page.
This is a research tool, not financial advice.
````

- [ ] **Step 3: Validate workflow YAML and run the full suite**

Run:
```bash
python -c "import yaml" 2>/dev/null || python -m pip install -q pyyaml
python -c "import yaml;d=yaml.safe_load(open('.github/workflows/analyze.yml'));print(sorted(d['jobs']))"
python -m pytest -q && node --test tests/js/
```
Expected: `['analyze', 'deploy']`; all tests pass.

- [ ] **Step 4: Reset the smoke-test watchlist and commit**

Put back a starter watchlist and keep generated `data/` out of the first commit (the workflow creates it):
```bash
printf '{\n  "tickers": []\n}\n' > watchlist.json
rm -rf data site/data
git add -A
git commit -m "feat: GitHub Actions workflow and setup README"
```

- [ ] **Step 5: Publish (if `gh` is authenticated)**

Run: `gh auth status`
- If authenticated: `gh repo create rule-one-analyzer --public --source . --push`, then
  `gh api -X POST repos/{owner}/rule-one-analyzer/pages -f build_type=workflow`.
  Secrets need the owner's Gmail app password, so leave README steps 2, 3, 5 and 6 to the owner.
- If not authenticated: stop and give the owner README step 1.
````
