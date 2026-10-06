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
