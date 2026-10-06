"""Current price, split history, monthly closes and analyst growth from Yahoo Finance."""
import time
from dataclasses import dataclass, field

from engine.retry import FetchError, with_retries


@dataclass
class MarketData:
    price: float
    analyst_growth: float | None
    splits: list
    monthly_closes: dict
    warnings: list = field(default_factory=list)


def _analyst_growth(ticker):
    """Returns (growth or None, warning or None)."""
    try:
        ge = ticker.growth_estimates
    except Exception as e:
        return None, f"The analyst growth estimate couldn't be downloaded ({e}); it may exist but is missing this run."
    if ge is None or getattr(ge, "empty", True):
        return None, None
    for row in ("LTG", "+5y"):
        if row in ge.index and "stockTrend" in ge.columns:
            v = ge.loc[row, "stockTrend"]
            if v is not None and v == v:  # v == v is False for NaN
                return float(v), None
    return None, None


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
        splits = {ts.strftime("%Y-%m-%d"): float(r) for ts, r in ticker.splits.items() if r and r > 0}
    except Exception as e:
        raise FetchError(f"Yahoo Finance request failed for {symbol}: {e}") from e
    if hist is None or hist.empty or "Close" not in hist or hist["Close"].dropna().empty:
        raise FetchError(f"Yahoo Finance returned no price history for {symbol}")
    if "Stock Splits" in hist:
        # Monthly bars date a split at the start of its month; only use them for months the split list lacks.
        known_months = {d[:7] for d in splits}
        for ts, r in hist["Stock Splits"].items():
            if r and r > 0 and ts.strftime("%Y-%m") not in known_months:
                splits[ts.strftime("%Y-%m-%d")] = float(r)
    closes = {ts.strftime("%Y-%m"): float(c) for ts, c in hist["Close"].dropna().items()}
    growth, warning = _analyst_growth(ticker)
    return MarketData(price=current, analyst_growth=growth, splits=sorted(splits.items()), monthly_closes=closes,
                      warnings=[warning] if warning else [])
