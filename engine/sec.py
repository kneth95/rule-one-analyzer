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
