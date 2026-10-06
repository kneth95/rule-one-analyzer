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
