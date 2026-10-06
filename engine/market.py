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
