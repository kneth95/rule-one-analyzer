import json

from engine.discover import discover_csv, run, summarize
from engine.retry import FetchError
from tests.test_main import FakeSec, fake_market


def table(rows):
    body = "".join(f"<tr><td>{s}</td><td>{n}</td><td>{sec}</td></tr>" for s, n, sec in rows)
    return f'<table id="constituents"><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th></tr>{body}</table>'


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

    code, out, _ = scan(tmp_path, market=market, min_success=0)
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


def test_run_refuses_to_publish_when_most_companies_fail(tmp_path):
    def broken(symbol):
        raise ValueError("yfinance changed")

    universe = UNIVERSE[:2] + [("COST", "Costco", "Consumer Staples")]
    code, out, _ = scan(tmp_path, market=broken, universe=universe)
    assert code == 3
    assert not (out / "discover.json").exists()
