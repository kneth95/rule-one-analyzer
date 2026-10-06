# Discover Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a weekly S&P 500 Rule #1 scan and a Discover tab that ranks Buy zone, Getting close, and "wonderful companies to watch", with one-click "+ Watch".

**Architecture:** `engine/universe.py` loads S&P 500 constituents from Wikipedia (fallback: last saved list). `engine/discover.py` runs the existing `analyze_ticker` (via a new shared `analyze_with_fallback`) over every constituent and writes a compact `discover.json`, per-stock detail JSON, a CSV and the saved list. A new `discover.yml` workflow force-pushes that output as a single orphan commit to the `discover-data` branch; both deploy jobs copy it into `site/data/discover/`. The dashboard gets `discover.html` with pure ranking in `discover-rank.js`, and the stock page falls back to Discover detail files.

**Tech Stack:** Python 3.12/3.14 (`requests`, `yfinance`, stdlib `html.parser`), `pyyaml` (tests only), vanilla JS ES modules, Node 22 `node --test`, GitHub Actions + Pages.

**Spec:** `docs/superpowers/specs/2026-10-06-discover-tab-design.md` (builds on `docs/superpowers/specs/2026-10-06-rule-one-analyzer-design.md`)

## Global Constraints

- Universe: S&P 500 from `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`, table `id="constituents"`, columns Symbol, Security, GICS Sector; fewer than 400 rows = parse failure.
- Analysis: existing `analyze_ticker` unchanged; same `settings.json`.
- Pacing: 0.5 s between companies.
- Schedule: `0 6 * * 6` (Saturday 06:00 UTC) + `workflow_dispatch`; concurrency group `discover`; deploy jobs in both workflows use concurrency group `pages`.
- Storage: `discover-data` branch, single orphan commit, force-pushed each scan. Never commit scan output to `main`.
- Site paths: `data/discover/discover.json`, `data/discover/stocks/<SYMBOL>.json`, `data/discover/csv/discover.csv`, `data/discover/sp500.json`.
- No email from Discover. Secrets used: `SEC_USER_AGENT` only.
- Lists: Buy zone (tier `buy`), Getting close (tier `close`), both by `pct_from_mos` ascending; Watch = tier `not_yet`, score ≥ min score, `debt_pass`, `mos_price` not null, by `pct_from_mos` ascending, top 25.
- Tests never touch the network. JS test command: `node --test "tests/js/*.test.mjs"`.

## Review Focus

1. **Yahoo throttling across ~500 sequential tickers** — expected: individual failures become stale/failed entries, the scan finishes, nothing crashes. Test: `test_run_isolates_crashes_and_fetch_errors` (Task 2).
2. **Wikipedia layout change or outage** — expected: last saved list used with a visible warning; no saved list → exit 2 and previous data stays live. Tests: `test_falls_back_to_saved_list`, `test_fails_without_saved_list`, `test_rejects_short_table` (Task 1).
3. **Daily watchlist deploy wiping Discover data** — expected: both deploy jobs copy `discover-data`. Test: `test_both_deploys_bundle_discover_data` (Task 3).
4. **First run before any scan exists** — expected: deploy skips the copy, Discover page shows "hasn't run yet", stock page falls back cleanly. Tests: `test_deploy_copy_is_conditional` (Task 3) + manual check (Task 5).
5. **Stock opened from Discover that's not on the watchlist** — expected: detail loads from the scan, no notes/override form, CSV built in the browser, "+ Watch" offered. Test: `toCsv` tests (Task 4) + manual check (Task 5).

---

## File Structure

```
engine/universe.py         parse_constituents(), fetch_wikipedia(), load_universe(), UniverseError
engine/main.py             (modify) extract analyze_with_fallback() used by run()
engine/discover.py         summarize(), discover_csv(), run(), CLI
tests/fixtures/sp500_sample.html
tests/test_universe.py, tests/test_discover.py, tests/test_workflows.py
.github/workflows/discover.yml           new
.github/workflows/analyze.yml            (modify) deploy job: pages concurrency + discover copy
requirements.txt                         (modify) + pyyaml
site/js/format.js                        (modify) + toCsv()
site/js/discover-rank.js                 buildLists()
site/js/watchlist.js                     addToWatchlist()
tests/js/discover-rank.test.mjs, tests/js/format.test.mjs (modify)
site/discover.html, site/js/discover.js  new page
site/js/stock.js                         (modify) Discover fallback
site/js/glossary.js                      (modify) + discover, wonderful_watch, sector
site/index.html, stock.html, guide.html, settings.html   (modify) nav link; guide section
README.md                                (modify) Discover section
```

---

### Task 1: S&P 500 universe

**Files:**
- Create: `engine/universe.py`, `tests/fixtures/sp500_sample.html`
- Test: `tests/test_universe.py`

**Interfaces:**
- Consumes: `normalize_symbol(s)` from `engine/config.py`; `read_json(path, default)` from `engine/output.py`.
- Produces:
  - `WIKI_URL: str`
  - `class UniverseError(Exception)`
  - `parse_constituents(html: str, min_rows: int = 400) -> list[dict]` — each `{"symbol", "name", "sector"}`
  - `fetch_wikipedia() -> str`
  - `load_universe(fetch_html: Callable[[], str], saved_path: Path, min_rows: int = 400) -> tuple[list[dict], str, list[str]]` — `(constituents, source "wikipedia"|"saved", warnings)`

- [ ] **Step 1: Create the HTML fixture** — `tests/fixtures/sp500_sample.html`

```html
<html><body>
<table class="wikitable"><tr><th>Other</th></tr><tr><td>NOT</td><td>Me</td><td>Ignore</td></tr></table>
<table class="wikitable sortable mw-collapsible sticky-header" id="constituents">
<tbody id="mwIA"><tr id="mwIQ">
<th><a href="https://en.wikipedia.org/wiki/Ticker_symbol">Symbol</a></th>
<th>Security</th><th><a href="x">GICS</a> Sector</th><th>GICS Sub-Industry</th><th>Headquarters Location</th><th>Date added</th><th>CIK</th><th>Founded</th></tr>
<tr>
<td><a class="external text" href="https://www.nyse.com/quote/XNYS:MMM">MMM</a></td>
<td><a href="https://en.wikipedia.org/wiki/3M">3M</a></td>
<td>Industrials</td>
<td>Industrial Conglomerates</td>
<td><a href="x">Saint Paul, Minnesota</a></td>
<td>1957-03-04</td>
<td>0000066740</td>
<td>1902</td></tr>
<tr>
<td><a class="external text" href="https://www.nyse.com/quote/XNYS:BRK.B">BRK.B</a></td>
<td><a href="https://en.wikipedia.org/wiki/Berkshire_Hathaway">Berkshire Hathaway</a></td>
<td>Financials</td>
<td>Multi-Sector Holdings</td>
<td><a href="x">Omaha</a>, Nebraska</td>
<td>2010-02-16</td>
<td>0001067983</td>
<td>1839</td></tr>
<tr>
<td><a class="external text" href="https://www.nasdaq.com/market-activity/stocks/aapl">AAPL</a></td>
<td><a href="https://en.wikipedia.org/wiki/Apple_Inc.">Apple Inc.</a></td>
<td>Information Technology</td>
<td>Technology Hardware, Storage &amp; Peripherals</td>
<td><a href="x">Cupertino, California</a></td>
<td>1982-11-30</td>
<td>0000320193</td>
<td>1977</td></tr>
</tbody></table>
<table><tr><td>AFTER</td><td>Table</td><td>Ignore</td></tr></table>
</body></html>
```

- [ ] **Step 2: Write the failing tests** — `tests/test_universe.py`

```python
from pathlib import Path

import pytest

from engine.output import write_json
from engine.universe import UniverseError, load_universe, parse_constituents

SAMPLE = (Path(__file__).parent / "fixtures" / "sp500_sample.html").read_text(encoding="utf-8")


def test_parses_constituents_table_only():
    rows = parse_constituents(SAMPLE, min_rows=1)
    assert rows == [
        {"symbol": "MMM", "name": "3M", "sector": "Industrials"},
        {"symbol": "BRK-B", "name": "Berkshire Hathaway", "sector": "Financials"},
        {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Information Technology"},
    ]


def test_rejects_short_table():
    with pytest.raises(UniverseError, match="only 3 rows"):
        parse_constituents(SAMPLE)


def test_rejects_missing_table():
    with pytest.raises(UniverseError, match="only 0 rows"):
        parse_constituents("<html><table><tr><td>a</td><td>b</td><td>c</td></tr></table></html>", min_rows=1)


def test_load_from_wikipedia(tmp_path):
    rows, source, warnings = load_universe(lambda: SAMPLE, tmp_path / "sp500.json", min_rows=1)
    assert source == "wikipedia" and len(rows) == 3 and warnings == []


def test_falls_back_to_saved_list(tmp_path):
    saved = tmp_path / "sp500.json"
    write_json(saved, [{"symbol": "KO", "name": "Coca-Cola", "sector": "Consumer Staples"}])

    def down():
        raise OSError("no network")

    rows, source, warnings = load_universe(down, saved, min_rows=1)
    assert source == "saved" and rows[0]["symbol"] == "KO"
    assert "last week's saved list" in warnings[0] and "no network" in warnings[0]


def test_fails_without_saved_list(tmp_path):
    with pytest.raises(UniverseError, match="no saved list"):
        load_universe(lambda: "<html></html>", tmp_path / "missing.json")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_universe.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.universe'`

- [ ] **Step 4: Implement** — `engine/universe.py`

```python
"""The S&P 500 list: parsed from Wikipedia, with last week's saved list as a fallback."""
from html.parser import HTMLParser

import requests

from engine.config import normalize_symbol
from engine.output import read_json

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class UniverseError(Exception):
    pass


class _ConstituentsParser(HTMLParser):
    """Collects the <td> texts of each row in <table id="constituents">."""

    def __init__(self):
        super().__init__()
        self.depth = 0  # table nesting depth inside the constituents table; 0 = outside
        self.row = None
        self.cell = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.depth:
                self.depth += 1
            elif dict(attrs).get("id") == "constituents":
                self.depth = 1
            return
        if self.depth != 1:
            return
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == "table":
            self.depth -= 1
        elif tag == "td" and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if len(self.row) >= 3:
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def parse_constituents(html, min_rows=400):
    parser = _ConstituentsParser()
    parser.feed(html)
    rows = [{"symbol": normalize_symbol(r[0]), "name": r[1], "sector": r[2]} for r in parser.rows if r[0]]
    if len(rows) < min_rows:
        raise UniverseError(f"S&P 500 table had only {len(rows)} rows (expected at least {min_rows}); "
                            "the Wikipedia page layout may have changed")
    return rows


def fetch_wikipedia():
    r = requests.get(WIKI_URL, headers={"User-Agent": "rule-one-analyzer (GitHub Actions)"}, timeout=30)
    r.raise_for_status()
    return r.text


def load_universe(fetch_html, saved_path, min_rows=400):
    try:
        return parse_constituents(fetch_html(), min_rows), "wikipedia", []
    except Exception as e:
        saved = read_json(saved_path, None)
        if saved:
            return saved, "saved", [f"Couldn't load the S&P 500 list from Wikipedia ({e}); used last week's saved list."]
        raise UniverseError(f"Couldn't load the S&P 500 list ({e}) and there is no saved list.") from e
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_universe.py -q`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add engine/universe.py tests/test_universe.py tests/fixtures/sp500_sample.html
git commit -m "feat: load S&P 500 constituents with saved-list fallback"
```

---

### Task 2: Discover scan (and shared stale fallback)

**Files:**
- Modify: `engine/main.py` (extract `analyze_with_fallback`, use it in `run`)
- Create: `engine/discover.py`
- Test: `tests/test_discover.py` (plus the existing `tests/test_main.py` as regression)

**Interfaces:**
- Consumes: `analyze_ticker`, `error_result` (engine/main.py); `load_settings`, `ConfigError`; `load_universe`, `fetch_wikipedia`, `UniverseError` (Task 1); `HISTORY_COLUMNS`, `read_json`, `write_json`, `_csv` (engine/output.py); `SecClient`; `fetch_market`; `TIER_LABEL`.
- Produces:
  - `engine.main.analyze_with_fallback(entry, sec, market_fetch, settings, now_iso, prev) -> dict`
  - `engine.discover.summarize(stock, name, sector) -> dict` with keys `symbol, name, sector, price, tier, tier_reason, stale, mos_price, sticker_price, pct_from_mos, score, debt_years, debt_pass, growth_rate, warnings_count`
  - `engine.discover.discover_csv(summaries) -> str`
  - `engine.discover.run(out_dir, previous_dir, root, env, limit=None, sec=None, market_fetch=fetch_market, fetch_html=fetch_wikipedia, sleep=time.sleep, now=None, min_rows=400, pause=0.5) -> int` (0 ok, 2 config/universe error)
  - Output files: `<out>/discover.json` (`generated_at, settings, columns, universe_source, warnings, counts{total,analyzed,failed}, stocks[summaries], failed[{symbol,name,reason}]`), `<out>/stocks/<SYM>.json`, `<out>/csv/discover.csv`, `<out>/sp500.json`
  - CLI: `python -m engine.discover --out DIR --previous DIR [--root .] [--limit N]`

- [ ] **Step 1: Write the failing tests** — `tests/test_discover.py`

```python
import json

from engine.discover import discover_csv, run, summarize
from engine.retry import FetchError
from tests.test_main import FakeSec, fake_market


def table(rows):
    body = "".join(f"<tr><td>{s}</td><td>{n}</td><td>{sec}</td></tr>" for s, n, sec in rows)
    return f'<table id="constituents"><tr><th>Symbol</th></tr>{body}</table>'


UNIVERSE = [("AAPL", "Apple Inc.", "Information Technology"), ("MSFT", "Microsoft", "Information Technology"),
            ("ZZZZ", "Unknown Co", "Financials")]


def scan(tmp_path, market=None, universe=UNIVERSE, previous=None, settings=None, **kw):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    (root / "settings.json").write_text(json.dumps(settings or {}))
    out = tmp_path / "out"
    sleeps = []
    code = run(out, previous or tmp_path / "no-prev", root, {}, sec=FakeSec(), market_fetch=market or fake_market(100.0),
               fetch_html=lambda: table(universe), sleep=sleeps.append, min_rows=1, **kw)
    return code, out, sleeps


def load(out):
    return json.loads((out / "discover.json").read_text(encoding="utf-8"))


def test_summarize_fields():
    stock = {"symbol": "AAA", "name": "AAA CORP", "price": 10.0, "tier": "close", "tier_reason": "r", "stale": False,
             "valuation": {"mos_price": 9.5, "sticker_price": 19.0, "pct_from_mos": 0.0526, "growth_rate": 0.1},
             "big_five": {"score": 4, "debt": {"payoff_years": 1.2, "pass": True}}, "warnings": ["a", "b"]}
    s = summarize(stock, "Aaa Inc.", "Energy")
    assert s == {"symbol": "AAA", "name": "Aaa Inc.", "sector": "Energy", "price": 10.0, "tier": "close",
                 "tier_reason": "r", "stale": False, "mos_price": 9.5, "sticker_price": 19.0, "pct_from_mos": 0.0526,
                 "score": 4, "debt_years": 1.2, "debt_pass": True, "growth_rate": 0.1, "warnings_count": 2}


def test_run_writes_outputs(tmp_path):
    code, out, sleeps = scan(tmp_path)
    assert code == 0
    d = load(out)
    assert d["counts"] == {"total": 3, "analyzed": 2, "failed": 1}
    assert [s["symbol"] for s in d["stocks"]] == ["AAPL", "MSFT"]
    assert d["stocks"][0]["sector"] == "Information Technology" and d["stocks"][0]["name"] == "Apple Inc."
    assert d["failed"][0]["symbol"] == "ZZZZ" and "Not found in SEC filings" in d["failed"][0]["reason"]
    assert d["universe_source"] == "wikipedia" and d["columns"][0] == ["revenue", "Revenue"]
    assert (out / "stocks" / "AAPL.json").exists() and not (out / "stocks" / "ZZZZ.json").exists()
    assert (out / "csv" / "discover.csv").read_text().startswith("Symbol,Company,Sector,Status")
    assert len(json.loads((out / "sp500.json").read_text())) == 3
    assert len(sleeps) == 2  # pause between companies, not before the first


def test_run_limit(tmp_path):
    _, out, _ = scan(tmp_path, limit=1)
    d = load(out)
    assert d["counts"]["total"] == 1
    assert len(json.loads((out / "sp500.json").read_text())) == 3  # full list saved for next week


def test_run_isolates_crashes_and_fetch_errors(tmp_path):
    def market(symbol):
        if symbol == "MSFT":
            raise ValueError("boom")
        if symbol == "AAPL":
            raise FetchError("Yahoo throttled")
        return fake_market(100.0)(symbol)

    code, out, _ = scan(tmp_path, market=market)
    d = load(out)
    assert code == 0
    reasons = {f["symbol"]: f["reason"] for f in d["failed"]}
    assert "Analysis failed: boom" in reasons["MSFT"]
    assert "Data couldn't be downloaded" in reasons["AAPL"]


def test_run_stale_fallback_from_previous_scan(tmp_path):
    _, first, _ = scan(tmp_path)
    prev = tmp_path / "prev"
    first.rename(prev)

    def market(symbol):
        if symbol == "AAPL":
            raise FetchError("Yahoo throttled")
        return fake_market(100.0)(symbol)

    _, out, _ = scan(tmp_path, market=market, previous=prev)
    stocks = {s["symbol"]: s for s in load(out)["stocks"]}
    assert stocks["AAPL"]["stale"] is True and stocks["MSFT"]["stale"] is False


def test_run_config_error(tmp_path):
    code, out, _ = scan(tmp_path, settings={"marr": 9})
    assert code == 2 and not (out / "discover.json").exists()


def test_discover_csv():
    rows = discover_csv([{"symbol": "A", "name": "A, Inc.", "sector": "Energy", "tier": "buy", "price": 1.0,
                          "mos_price": 2.0, "sticker_price": 4.0, "pct_from_mos": -0.5, "score": 5, "debt_years": None,
                          "growth_rate": 0.1, "stale": False}]).splitlines()
    assert rows[1] == 'A,"A, Inc.",Energy,Buy zone,1.0,2.0,4.0,-0.5,5,,0.1,'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_discover.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.discover'`

- [ ] **Step 3: Extract the shared fallback in `engine/main.py`**

Replace the loop body in `run()`:

```python
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
```

with:

```python
    stocks = []
    for entry in watchlist:
        print(f"Analyzing {entry['symbol']}...")
        stocks.append(analyze_with_fallback(entry, sec, market_fetch, settings, now_iso, previous.get(entry["symbol"])))
```

and add above `run()`:

```python
def analyze_with_fallback(entry, sec, market_fetch, settings, now_iso, prev):
    """analyze_ticker, falling back to the previous result (marked stale) when data can't be downloaded."""
    try:
        return analyze_ticker(entry, sec, market_fetch, settings, now_iso)
    except FetchError as e:
        if prev and not prev.get("error"):
            return {**prev, "stale": True, "stale_reason": f"{e} Showing results from {prev['as_of']}.",
                    "notes": entry.get("notes", ""), "growth_override": entry.get("growth_override")}
        return error_result(entry, f"Data couldn't be downloaded: {e}", now_iso)
    except Exception as e:
        traceback.print_exc()
        return error_result(entry, f"Analysis failed: {e}", now_iso)
```

Run: `python -m pytest tests/test_main.py -q`
Expected: 11 passed (behavior unchanged)

- [ ] **Step 4: Implement** — `engine/discover.py`

```python
"""Weekly S&P 500 scan: run the Rule #1 analysis on every constituent and write Discover data."""
import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from engine.config import ConfigError, load_settings
from engine.main import analyze_with_fallback
from engine.market import fetch_market
from engine.output import HISTORY_COLUMNS, _csv, read_json, write_json
from engine.sec import SecClient
from engine.tiers import TIER_LABEL
from engine.universe import UniverseError, fetch_wikipedia, load_universe


def summarize(stock, name, sector):
    v = stock.get("valuation") or {}
    bf = stock.get("big_five") or {}
    debt = bf.get("debt") or {}
    return {
        "symbol": stock["symbol"], "name": name, "sector": sector, "price": stock.get("price"),
        "tier": stock.get("tier", "not_yet"), "tier_reason": stock.get("tier_reason", ""),
        "stale": bool(stock.get("stale")), "mos_price": v.get("mos_price"), "sticker_price": v.get("sticker_price"),
        "pct_from_mos": v.get("pct_from_mos"), "score": bf.get("score"), "debt_years": debt.get("payoff_years"),
        "debt_pass": debt.get("pass"), "growth_rate": v.get("growth_rate"),
        "warnings_count": len(stock.get("warnings") or []),
    }


def discover_csv(summaries):
    cell = lambda v: "" if v is None else v
    rows = [["Symbol", "Company", "Sector", "Status", "Price", "MOS price", "Sticker Price", "Price vs MOS",
             "Big Five score", "Debt payoff years", "Growth rate used", "Stale"]]
    for s in summaries:
        rows.append([s["symbol"], s["name"], s["sector"], TIER_LABEL[s["tier"]], cell(s["price"]),
                     cell(s["mos_price"]), cell(s["sticker_price"]), cell(s["pct_from_mos"]), cell(s["score"]),
                     cell(s["debt_years"]), cell(s["growth_rate"]), "yes" if s["stale"] else ""])
    return _csv(rows)


def run(out_dir, previous_dir, root, env, limit=None, sec=None, market_fetch=fetch_market,
        fetch_html=fetch_wikipedia, sleep=time.sleep, now=None, min_rows=400, pause=0.5):
    out, previous_dir, root = Path(out_dir), Path(previous_dir), Path(root)
    try:
        settings = load_settings(root / "settings.json")
        universe, source, warnings = load_universe(fetch_html, previous_dir / "sp500.json", min_rows)
    except (ConfigError, UniverseError) as e:
        print(f"Discover scan can't start: {e}", file=sys.stderr)
        return 2

    now_iso = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sec = sec or SecClient(env.get("SEC_USER_AGENT", ""))
    scan_list = universe[:limit] if limit else universe
    summaries, failed = [], []
    for i, company in enumerate(scan_list):
        if i:
            sleep(pause)
        symbol = company["symbol"]
        print(f"[{i + 1}/{len(scan_list)}] {symbol}")
        prev = read_json(previous_dir / "stocks" / f"{symbol}.json", None)
        entry = {"symbol": symbol, "notes": "", "growth_override": None}
        stock = analyze_with_fallback(entry, sec, market_fetch, settings, now_iso, prev)
        if stock.get("error"):
            failed.append({"symbol": symbol, "name": company["name"], "reason": stock["error"]})
            continue
        write_json(out / "stocks" / f"{symbol}.json", stock)
        summaries.append(summarize(stock, company["name"], company["sector"]))

    write_json(out / "discover.json", {
        "generated_at": now_iso, "settings": settings, "columns": [list(c) for c in HISTORY_COLUMNS],
        "universe_source": source, "warnings": warnings,
        "counts": {"total": len(scan_list), "analyzed": len(summaries), "failed": len(failed)},
        "stocks": summaries, "failed": failed,
    })
    (out / "csv").mkdir(parents=True, exist_ok=True)
    (out / "csv" / "discover.csv").write_text(discover_csv(summaries), encoding="utf-8")
    write_json(out / "sp500.json", universe)
    print(f"Done: {len(summaries)} analyzed, {len(failed)} couldn't be analyzed.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Weekly S&P 500 Rule #1 scan")
    parser.add_argument("--out", required=True, help="directory for the scan output")
    parser.add_argument("--previous", required=True, help="directory holding the previous scan (may not exist)")
    parser.add_argument("--root", default=".", help="repo root containing settings.json")
    parser.add_argument("--limit", type=int, help="scan only the first N companies (local testing)")
    args = parser.parse_args(argv)
    return run(args.out, args.previous, args.root, os.environ, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_discover.py tests/test_main.py -q`
Expected: 18 passed

- [ ] **Step 6: Commit**

```bash
git add engine/main.py engine/discover.py tests/test_discover.py
git commit -m "feat: weekly S&P 500 discover scan reusing the watchlist analysis"
```

---

### Task 3: Workflows

**Files:**
- Create: `.github/workflows/discover.yml`, `tests/test_workflows.py`
- Modify: `.github/workflows/analyze.yml` (deploy job), `requirements.txt`

**Interfaces:**
- Consumes: `python -m engine.discover --out discover-out --previous prev` (Task 2).
- Produces: branch `discover-data` (contents of `discover-out/` at its root); site path `site/data/discover/`.

- [ ] **Step 1: Add pyyaml for workflow tests**

`requirements.txt` becomes:
```
requests>=2.31
yfinance>=1.0
pytest>=8.0
pyyaml>=6.0
```

Run: `python -m pip install -q -r requirements.txt`

- [ ] **Step 2: Write the failing tests** — `tests/test_workflows.py`

```python
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def load(name):
    d = yaml.safe_load((WF / name).read_text(encoding="utf-8"))
    d["on"] = d.pop(True, d.get("on"))  # YAML 1.1 parses the bare key `on` as True
    return d


def bundle_step(job):
    return next(s for s in job["steps"] if s.get("name") == "Bundle site with latest data")


def test_both_deploys_bundle_discover_data():
    for name in ("analyze.yml", "discover.yml"):
        deploy = load(name)["jobs"]["deploy"]
        assert deploy["concurrency"]["group"] == "pages", name
        assert "discover-data" in bundle_step(deploy)["run"], name
        assert "site/data/discover" in bundle_step(deploy)["run"], name


def test_deploy_copy_is_conditional():
    run = bundle_step(load("analyze.yml")["jobs"]["deploy"])["run"]
    assert "git ls-remote --exit-code origin discover-data" in run


def test_discover_schedule_and_concurrency():
    d = load("discover.yml")
    assert d["on"]["schedule"][0]["cron"] == "0 6 * * 6"
    assert "workflow_dispatch" in d["on"]
    assert d["concurrency"]["group"] == "discover"
    scan = d["jobs"]["scan"]
    assert any("engine.discover" in s.get("run", "") for s in scan["steps"])
    assert any("push -f" in s.get("run", "") and "discover-data" in s.get("run", "") for s in scan["steps"])
    assert not any("GMAIL" in str(s.get("env", {})) for s in scan["steps"])
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_workflows.py -q`
Expected: FAIL — `FileNotFoundError` for `discover.yml` / `KeyError: 'concurrency'`

- [ ] **Step 4: Update the analyze deploy job** — in `.github/workflows/analyze.yml`, replace

```yaml
  deploy:
    needs: analyze
    if: always()
    runs-on: ubuntu-latest
```
with
```yaml
  deploy:
    needs: analyze
    if: always()
    runs-on: ubuntu-latest
    concurrency:
      group: pages
      cancel-in-progress: false
```

and replace

```yaml
      - name: Bundle site with latest data
        run: |
          mkdir -p site/data
          if [ -d data ]; then cp -r data/. site/data/; fi
```
with
```yaml
      - name: Bundle site with latest data
        run: |
          mkdir -p site/data
          if [ -d data ]; then cp -r data/. site/data/; fi
          if git ls-remote --exit-code origin discover-data >/dev/null 2>&1; then
            git fetch --depth 1 origin discover-data
            mkdir -p site/data/discover
            git archive FETCH_HEAD | tar -x -C site/data/discover
          fi
```

- [ ] **Step 5: Create** — `.github/workflows/discover.yml`

```yaml
name: Discover S&P 500

on:
  schedule:
    - cron: "0 6 * * 6"   # Saturdays 06:00 UTC
  workflow_dispatch:

concurrency:
  group: discover
  cancel-in-progress: false

jobs:
  scan:
    runs-on: ubuntu-latest
    timeout-minutes: 90
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main
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
          node --test "tests/js/*.test.mjs"
      - name: Fetch last scan
        run: |
          mkdir -p prev
          if git ls-remote --exit-code origin discover-data >/dev/null 2>&1; then
            git fetch --depth 1 origin discover-data
            git archive FETCH_HEAD | tar -x -C prev
          fi
      - name: Scan S&P 500
        env:
          SEC_USER_AGENT: ${{ secrets.SEC_USER_AGENT }}
        run: python -m engine.discover --out discover-out --previous prev
      - name: Publish scan to discover-data
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          cd discover-out
          git init -q -b discover-data
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -A
          git commit -q -m "Discover scan $(date -u +%Y-%m-%d)"
          git push -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" discover-data

  deploy:
    needs: scan
    if: always()
    runs-on: ubuntu-latest
    concurrency:
      group: pages
      cancel-in-progress: false
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
          if git ls-remote --exit-code origin discover-data >/dev/null 2>&1; then
            git fetch --depth 1 origin discover-data
            mkdir -p site/data/discover
            git archive FETCH_HEAD | tar -x -C site/data/discover
          fi
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_workflows.py -q`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .github/workflows tests/test_workflows.py
git commit -m "feat: weekly discover workflow and shared Discover data in deploys"
```

---

### Task 4: Dashboard logic — ranking, CSV, watchlist add

**Files:**
- Create: `site/js/discover-rank.js`, `site/js/watchlist.js`, `tests/js/discover-rank.test.mjs`
- Modify: `site/js/format.js` (+ `toCsv`), `tests/js/format.test.mjs`

**Interfaces:**
- Produces:
  - `buildLists(stocks, { watchlist = new Set(), minScore = 4, sector = "", hideWatched = false }) -> { buy, close, watch, sectors }` — each list item is the summary plus `watched: boolean`; `sectors` sorted unique from all stocks.
  - `WATCH_LIMIT = 25`
  - `toCsv(rows: any[][]) -> string` (RFC 4180 quoting, `\n` line ends)
  - `addToWatchlist(symbol) -> Promise<void>` (throws if already present)

- [ ] **Step 1: Write the failing tests** — `tests/js/discover-rank.test.mjs`

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildLists, WATCH_LIMIT } from "../../site/js/discover-rank.js";

const s = (symbol, tier, pct, extra = {}) => ({ symbol, name: symbol, sector: "Tech", tier, pct_from_mos: pct, score: 5,
  debt_pass: true, mos_price: 10, ...extra });

test("splits into buy, close and watch lists sorted by discount", () => {
  const stocks = [s("B2", "buy", -0.1), s("B1", "buy", -0.4), s("C1", "close", 0.05), s("W2", "not_yet", 0.8),
    s("W1", "not_yet", 0.2)];
  const { buy, close, watch } = buildLists(stocks, {});
  assert.deepEqual(buy.map((x) => x.symbol), ["B1", "B2"]);
  assert.deepEqual(close.map((x) => x.symbol), ["C1"]);
  assert.deepEqual(watch.map((x) => x.symbol), ["W1", "W2"]);
});

test("watch list needs score, debt pass and a MOS price, and stops at the limit", () => {
  const stocks = [s("LOW", "not_yet", 0.1, { score: 3 }), s("DEBT", "not_yet", 0.1, { debt_pass: false }),
    s("NOMOS", "not_yet", null, { mos_price: null }),
    ...Array.from({ length: 30 }, (_, i) => s(`W${i}`, "not_yet", i / 10))];
  const { watch } = buildLists(stocks, { minScore: 4 });
  assert.equal(watch.length, WATCH_LIMIT);
  assert.equal(watch[0].symbol, "W0");
  assert.ok(!watch.some((x) => ["LOW", "DEBT", "NOMOS"].includes(x.symbol)));
});

test("filters by sector, min score and watched", () => {
  const stocks = [s("A", "buy", -0.2, { sector: "Energy" }), s("B", "buy", -0.3, { score: 4 }), s("C", "buy", -0.1)];
  const watchlist = new Set(["C"]);
  assert.deepEqual(buildLists(stocks, { sector: "Energy" }).buy.map((x) => x.symbol), ["A"]);
  assert.deepEqual(buildLists(stocks, { minScore: 5 }).buy.map((x) => x.symbol), ["A", "C"]);
  const lists = buildLists(stocks, { watchlist, hideWatched: true });
  assert.deepEqual(lists.buy.map((x) => x.symbol), ["B", "A"]);
  assert.equal(buildLists(stocks, { watchlist }).buy.find((x) => x.symbol === "C").watched, true);
  assert.deepEqual(lists.sectors, ["Energy", "Tech"]);
});
```

Add to `tests/js/format.test.mjs` (extend the import list with `toCsv`):

```js
test("toCsv quotes commas, quotes and newlines", () => {
  assert.equal(toCsv([["Year", "Name"], [2024, 'A, "B"'], [null, "x\ny"]]), 'Year,Name\n2024,"A, ""B"""\n,"x\ny"\n');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test "tests/js/*.test.mjs"`
Expected: FAIL — `Cannot find module .../site/js/discover-rank.js` and `toCsv` not exported

- [ ] **Step 3: Implement** — `site/js/discover-rank.js`

```js
// Pure ranking and filtering for the Discover tab (unit-tested in Node).

export const WATCH_LIMIT = 25;

const byDiscount = (a, b) => (a.pct_from_mos ?? Infinity) - (b.pct_from_mos ?? Infinity);

export function buildLists(stocks, { watchlist = new Set(), minScore = 4, sector = "", hideWatched = false } = {}) {
  const sectors = [...new Set(stocks.map((x) => x.sector).filter(Boolean))].sort();
  const pool = stocks
    .map((x) => ({ ...x, watched: watchlist.has(x.symbol) }))
    .filter((x) => (!sector || x.sector === sector) && (x.score ?? -1) >= minScore && !(hideWatched && x.watched));
  return {
    buy: pool.filter((x) => x.tier === "buy").sort(byDiscount),
    close: pool.filter((x) => x.tier === "close").sort(byDiscount),
    watch: pool.filter((x) => x.tier === "not_yet" && x.debt_pass && x.mos_price != null)
      .sort(byDiscount).slice(0, WATCH_LIMIT),
    sectors,
  };
}
```

Append to `site/js/format.js`:

```js
const csvCell = (c) => {
  if (c == null) return "";
  const s = String(c);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function toCsv(rows) {
  return rows.map((r) => r.map(csvCell).join(",")).join("\n") + "\n";
}
```

`site/js/watchlist.js`:

```js
import { updateJsonFile } from "./github.js";

export async function addToWatchlist(symbol) {
  await updateJsonFile("watchlist.json", (w) => {
    if (w.tickers.some((t) => t.symbol === symbol)) throw new Error(`${symbol} is already on the watchlist.`);
    w.tickers.push({ symbol, added: new Date().toISOString().slice(0, 10), notes: "", growth_override: null });
    return w;
  }, `Add ${symbol} to watchlist`);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test "tests/js/*.test.mjs"`
Expected: 12 pass, 0 fail

- [ ] **Step 5: Commit**

```bash
git add site/js/discover-rank.js site/js/watchlist.js site/js/format.js tests/js
git commit -m "feat: Discover ranking, CSV helper and watchlist add"
```

---

### Task 5: Discover page, stock page fallback, nav, glossary, guide

**Files:**
- Create: `site/discover.html`, `site/js/discover.js`
- Modify: `site/js/stock.js`, `site/js/glossary.js`, `site/index.html`, `site/stock.html`, `site/guide.html`, `site/settings.html`, `README.md`

**Interfaces:**
- Consumes: `buildLists`, `WATCH_LIMIT`, `toCsv`, `addToWatchlist` (Task 4); `data/discover/discover.json` and `data/discover/stocks/<SYM>.json` (Task 2); existing `common.js`, `format.js`, `github.js`, `glossary.js`.

- [ ] **Step 1: Nav link on every page**

In `site/index.html`, `site/stock.html`, `site/guide.html`, `site/settings.html`, change

```html
    <a href="guide.html">Guide</a>
```
(or the `class="active"` variant on guide.html) by inserting before the Guide link:
```html
    <a href="discover.html">Discover</a>
```

Check: `grep -c 'href="discover.html"' site/*.html` → 1 per page.

- [ ] **Step 2: Glossary entries** — in `site/js/glossary.js`, add after the `stale` entry:

```js
  discover: { term: "Discover", what: "A weekly scan of every S&P 500 company with the same Rule #1 analysis your watchlist gets.", why: "It finds wonderful companies you aren't following yet.", good: "Treat results as research leads. Judge Meaning, Moat and Management before buying." },
  wonderful_watch: { term: "⭐ Wonderful companies to watch", what: "Companies with at least 4 Big Five passes and manageable debt that are still above their MOS price, closest to it first (top 25).", why: "Rule #1 bargains are rare. Studying great businesses now means you're ready when the price drops.", good: "Add the ones you understand to your watchlist; you'll get an email when they reach Getting close or Buy zone." },
  sector: { term: "Sector", what: "The company's industry group (GICS sector), e.g. Information Technology or Consumer Staples.", why: "Filtering by sector helps you stay inside businesses you understand (Meaning).", good: "—" },
```

- [ ] **Step 3: Discover page** — `site/discover.html`

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Discover Rule #1 Stocks</title>
  <link rel="stylesheet" href="css/style.css" />
</head>
<body>
<header class="top">
  <a class="brand" href="index.html">Rule #1 Analyzer</a>
  <nav>
    <a href="index.html">Watchlist</a>
    <a href="discover.html" class="active">Discover</a>
    <a href="guide.html">Guide</a>
    <a href="settings.html">Settings</a>
  </nav>
  <button id="owner-btn" type="button" title="Owner access">🔑 Owner</button>
</header>
<main>
  <h1><span class="term" data-term="discover">Discover</span></h1>
  <p class="muted" id="summary">Loading…</p>
  <p class="banner">These are research leads, not buy signals. Rule #1 still needs you to judge
    <span class="term" data-term="meaning">Meaning</span>, <span class="term" data-term="moat">Moat</span> and
    <span class="term" data-term="management">Management</span> before buying.</p>
  <div id="scan-warnings"></div>

  <form id="filters" class="card row">
    <label><span class="term" data-term="sector">Sector</span>
      <select name="sector"><option value="">All sectors</option></select></label>
    <label><span class="term" data-term="big_five_score">Min Big Five</span>
      <select name="minScore"></select></label>
    <label class="row"><input type="checkbox" name="hideWatched" /> Hide stocks on my watchlist</label>
  </form>

  <div id="lists"></div>

  <details class="card" id="failed-box" hidden>
    <summary id="failed-summary"></summary>
    <ul id="failed-list" class="warnings"></ul>
  </details>

  <section class="row">
    <a class="button" href="data/discover/csv/discover.csv" download>Download full scan CSV</a>
  </section>
  <p class="muted">Data: S&amp;P 500 list from Wikipedia, filings from SEC EDGAR, prices from Yahoo Finance. Not financial advice.</p>
</main>
<script type="module" src="js/discover.js"></script>
</body>
</html>
```

`site/js/discover.js`:

```js
import { initPage, loadResults, term, toast } from "./common.js";
import { attachTerms } from "./glossary.js";
import { escapeHtml, money, num, signedPct } from "./format.js";
import { actionsUrl } from "./github.js";
import { addToWatchlist } from "./watchlist.js";
import { buildLists, WATCH_LIMIT } from "./discover-rank.js";

const LISTS = [
  ["buy", "🟢 Buy zone", "tier_buy", "No S&P 500 company is in the Buy zone this week. That's normal: real Rule #1 bargains are rare."],
  ["close", "🟡 Getting close", "tier_close", "Nothing is in the early-warning range this week."],
  ["watch", `⭐ Wonderful companies to watch (top ${WATCH_LIMIT})`, "wonderful_watch", "No company passes these filters right now."],
];

let scan;
let watchlist = new Set();

function row(s) {
  const action = s.watched ? `<span class="muted">✓ Watching</span>` : `<button data-watch="${escapeHtml(s.symbol)}">+ Watch</button>`;
  return `<tr class="clickable" data-symbol="${escapeHtml(s.symbol)}">
    <td><b>${escapeHtml(s.symbol)}</b>${s.watched ? ` <span title="On your watchlist">⭐</span>` : ""}<br>
      <span class="muted">${escapeHtml(s.name)}</span>${s.stale ? ` ${term("stale", "stale")}` : ""}</td>
    <td class="left">${escapeHtml(s.sector)}</td>
    <td>${money(s.price)}</td>
    <td>${money(s.mos_price)}</td>
    <td>${signedPct(s.pct_from_mos)}</td>
    <td>${s.score ?? "—"}/5</td>
    <td class="${s.debt_pass ? "pass" : "fail"}">${s.debt_years == null ? "n/a" : num(s.debt_years, 1)}</td>
    <td class="owner-only">${action}</td>
  </tr>`;
}

function table(items) {
  return `<div class="table-wrap"><table>
    <thead><tr><th>Stock</th><th class="left">${term("sector", "Sector")}</th><th>Price</th>
      <th>${term("mos_price", "MOS price")}</th><th>${term("pct_from_mos", "vs MOS")}</th>
      <th>${term("big_five_score", "Big Five")}</th><th>${term("debt", "Debt yrs")}</th><th class="owner-only"></th></tr></thead>
    <tbody>${items.map(row).join("")}</tbody></table></div>`;
}

function filters() {
  const f = new FormData(document.querySelector("#filters"));
  return { sector: f.get("sector") || "", minScore: Number(f.get("minScore")), hideWatched: f.get("hideWatched") === "on", watchlist };
}

function render() {
  const lists = buildLists(scan.stocks, filters());
  const box = document.querySelector("#lists");
  box.innerHTML = LISTS.map(([key, title, glossary, empty]) => `<section class="card">
      <h2><span class="term" data-term="${glossary}">${escapeHtml(title)}</span> <span class="muted">(${lists[key].length})</span></h2>
      ${lists[key].length ? table(lists[key]) : `<p class="muted">${escapeHtml(empty)}</p>`}
    </section>`).join("");
  attachTerms(box);
}

function setupFilters() {
  const form = document.querySelector("#filters");
  const sectorSelect = form.querySelector("[name=sector]");
  for (const sector of buildLists(scan.stocks).sectors) sectorSelect.add(new Option(sector, sector));
  const min = Number(scan.settings.big_five_min_score);
  const scoreSelect = form.querySelector("[name=minScore]");
  for (const v of [...new Set([min, 5])]) scoreSelect.add(new Option(`${v} of 5`, String(v)));
  form.addEventListener("change", render);
}

function showMeta() {
  const c = scan.counts;
  document.querySelector("#summary").textContent =
    `Last scanned ${new Date(scan.generated_at).toLocaleString()} · ${c.total} companies · ${c.analyzed} analyzed, ${c.failed} couldn't be analyzed`;
  document.querySelector("#scan-warnings").innerHTML = scan.warnings.map((w) => `<p class="banner">${escapeHtml(w)}</p>`).join("");
  if (scan.failed.length) {
    document.querySelector("#failed-box").hidden = false;
    document.querySelector("#failed-summary").textContent = `${scan.failed.length} companies couldn't be analyzed`;
    document.querySelector("#failed-list").innerHTML = scan.failed
      .map((f) => `<li><b>${escapeHtml(f.symbol)}</b> ${escapeHtml(f.name)}: ${escapeHtml(f.reason)}</li>`).join("");
  }
}

async function onClick(e) {
  const btn = e.target.closest("[data-watch]");
  if (btn) {
    btn.disabled = true;
    try {
      await addToWatchlist(btn.dataset.watch);
      watchlist.add(btn.dataset.watch);
      btn.outerHTML = `<span class="muted">✓ Watching</span>`;
      toast(`${escapeHtml(btn.dataset.watch)} added to your watchlist. Results in about 1–2 minutes. <a href="${actionsUrl()}" target="_blank" rel="noopener">Watch the run</a>`, "ok");
    } catch (err) {
      btn.disabled = false;
      toast(escapeHtml(err.message), "error");
    }
    return;
  }
  if (e.target.closest(".info")) return;
  const tr = e.target.closest("tr[data-symbol]");
  if (tr) location.href = `stock.html?t=${encodeURIComponent(tr.dataset.symbol)}`;
}

async function main() {
  initPage();
  const res = await fetch("data/discover/discover.json", { cache: "no-store" });
  if (!res.ok) {
    document.querySelector("#summary").textContent =
      "Discover hasn't run yet. Owner: on GitHub open Actions → Discover S&P 500 → Run workflow (takes about 20 minutes).";
    document.querySelector("#filters").hidden = true;
    return;
  }
  scan = await res.json();
  try {
    watchlist = new Set((await loadResults()).stocks.map((s) => s.symbol));
  } catch { /* no watchlist results yet */ }
  showMeta();
  setupFilters();
  render();
  document.querySelector("#lists").addEventListener("click", onClick);
}

main();
```

- [ ] **Step 4: Stock page fallback** — edits in `site/js/stock.js`

4a. Imports: replace
```js
import { bigMoney, escapeHtml, historyRows, money, num, pct, signedPct, stockMarkdown, toTsv } from "./format.js";
import { actionsUrl, updateJsonFile } from "./github.js";
```
with
```js
import { bigMoney, escapeHtml, historyRows, money, num, pct, signedPct, stockMarkdown, toCsv, toTsv } from "./format.js";
import { actionsUrl, updateJsonFile } from "./github.js";
import { addToWatchlist } from "./watchlist.js";
```

4b. `render`: change the signature line `function render(s, results) {` to `function render(s, results, source) {`, and replace
```js
    s.growth_override != null ? `<p class="banner">Using your growth override of ${pct(s.growth_override)}.</p>` : "",
  ].join("");
```
with
```js
    s.growth_override != null ? `<p class="banner">Using your growth override of ${pct(s.growth_override)}.</p>` : "",
    source === "discover" ? `<p class="banner">From the weekly ${term("discover", "S&P 500 scan")} on ${new Date(s.as_of).toLocaleDateString()}.
      Add it to your watchlist for daily updates and email alerts. <button id="watch-btn" class="owner-only primary">+ Watch</button></p>` : "",
  ].join("");
  const inputs = source === "watchlist" ? inputsSection(s) : "";
```
then replace `if (s.error) return head + inputsSection(s);` with `if (s.error) return head + inputs;`, replace the line `    ${inputsSection(s)}` with `    ${inputs}`, and replace
```js
        <a class="button" href="data/csv/${encodeURIComponent(s.symbol)}.csv" download>Download CSV</a>
```
with
```js
        ${source === "watchlist" ? `<a class="button" href="data/csv/${encodeURIComponent(s.symbol)}.csv" download>Download CSV</a>` : `<button id="download-csv">Download CSV</button>`}
```

4c. `wire`: after the `#copy-md` listener line, add
```js
  document.querySelector("#download-csv")?.addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([toCsv(historyRows(s, results.columns))], { type: "text/csv" }));
    Object.assign(document.createElement("a"), { href: url, download: `${s.symbol}.csv` }).click();
    URL.revokeObjectURL(url);
  });
  document.querySelector("#watch-btn")?.addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      await addToWatchlist(s.symbol);
      e.target.outerHTML = `<b>✓ Added.</b>`;
      toast(`${escapeHtml(s.symbol)} added to your watchlist. Results in about 1–2 minutes. <a href="${actionsUrl()}" target="_blank" rel="noopener">Watch the run</a>`, "ok");
    } catch (err) {
      e.target.disabled = false;
      toast(escapeHtml(err.message), "error");
    }
  });
```

4d. Replace the whole `main()` function with:
```js
async function loadStock(symbol) {
  let results = null;
  try {
    results = await loadResults();
  } catch { /* no watchlist results yet */ }
  const s = results?.stocks.find((x) => x.symbol === symbol);
  if (s) return { s, results, source: "watchlist" };
  if (!symbol) return null;
  const res = await fetch(`data/discover/stocks/${encodeURIComponent(symbol)}.json`, { cache: "no-store" });
  if (!res.ok) return null;
  const scan = await fetch("data/discover/discover.json", { cache: "no-store" }).then((r) => r.json());
  return { s: await res.json(), results: { settings: scan.settings, columns: scan.columns }, source: "discover" };
}

async function main() {
  initPage();
  const container = document.querySelector("#content");
  const symbol = new URLSearchParams(location.search).get("t");
  try {
    const found = await loadStock(symbol);
    if (!found) {
      container.innerHTML = `<p class="banner">${escapeHtml(symbol || "That stock")} isn't in your watchlist results or the latest S&amp;P 500 scan. <a href="index.html">Back to the watchlist</a></p>`;
      return;
    }
    const { s, results, source } = found;
    container.innerHTML = render(s, results, source);
    attachTerms(container);
    wire(s, results);
    if (s.history) drawCharts(s);
  } catch (err) {
    container.innerHTML = `<p class="banner error">${escapeHtml(err.message)}</p>`;
  }
}
```

Run: `node --check site/js/stock.js && node --check site/js/discover.js` → no output.

- [ ] **Step 5: Guide section** — in `site/guide.html`, insert before `<h2>7. Limits</h2>`:

```html
  <h2>7. Using Discover</h2>
  <p>Every Saturday the tool runs the same analysis on all S&amp;P 500 companies. The <span class="term" data-term="discover">Discover</span> tab shows three lists:</p>
  <ul>
    <li><b>🟢 Buy zone</b> and <b>🟡 Getting close</b>: companies you don't follow yet that already meet the alert rules. These are often empty, and that's normal: Rule #1 bargains are rare.</li>
    <li><span class="term" data-term="wonderful_watch">⭐ Wonderful companies to watch</span>: strong businesses still above their MOS price, closest first.</li>
  </ul>
  <p>Open a company to see its full analysis. If you understand the business, click <b>+ Watch</b> to add it to your watchlist: from then on it's analyzed daily and you'll get an email when it reaches a better status. Discover itself never emails you.</p>
```
and renumber the Limits heading to `<h2>8. Limits</h2>`.

- [ ] **Step 6: README** — in `README.md`, add after the "Everyday use" list:

```markdown
### Discover

Every Saturday a second workflow, **Discover S&P 500**, analyzes all S&P 500 companies (about 20 minutes) and fills
the **Discover** tab with Buy zone, Getting close and "wonderful companies to watch" lists. Click **+ Watch** to move a
company to your watchlist. To run it right away: Actions → Discover S&P 500 → Run workflow. Discover never sends email.
Its data lives on the `discover-data` branch, which is overwritten each week.
```

- [ ] **Step 7: Manual check with a real 20-company scan**

```bash
SEC_USER_AGENT="rule-one-analyzer dev admin@example.com" python -m engine.discover --out discover-out --previous prev --limit 20
rm -rf site/data && mkdir -p site/data/discover && cp -r discover-out/. site/data/discover/
python -m http.server 8765 -d site
```
Check in a browser (or headless Chrome screenshots at 1280px and in 375px iframes):
- Discover: summary line, three lists (possibly empty with their messages), filters change the lists, failures toggle, ⓘ tooltips.
- Clicking a row opens the stock page with the "From the weekly S&P 500 scan" banner, no "Your inputs" card, Download CSV produces a file.
- With `site/data/discover` removed: Discover shows "hasn't run yet"; stock page shows the not-found banner.
- No page-level horizontal scroll at 375px; no console errors.

Clean up: `rm -rf discover-out prev site/data`.

- [ ] **Step 8: Full suite and commit**

Run: `python -m pytest -q && node --test "tests/js/*.test.mjs"`
Expected: all pass

```bash
git add site README.md
git commit -m "feat: Discover tab, stock page fallback, glossary and guide"
```
