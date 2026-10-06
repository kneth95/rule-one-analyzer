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
