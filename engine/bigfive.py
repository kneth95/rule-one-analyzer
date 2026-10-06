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
    if len(available) < 2:
        warnings.append(f"{METRICS[key]}: Not enough history to judge (needs at least 2 of the 10/5/3/1-year windows).")
    long_v, one_v = longest_value(windows), windows["1"]["value"]
    trend_ok = long_v is None or one_v is None or one_v >= long_v - settings["trend_tolerance"]
    return {
        "label": METRICS[key],
        "windows": windows,
        "passes": passes,
        "required": required,
        "trend_ok": trend_ok,
        "pass": len(available) >= 2 and passes >= required and trend_ok,
    }


def _debt(fin, settings):
    y = fin.latest_year
    debt = fin.get("total_debt", y)
    fcf = fin.get("fcf", y)
    if debt is None:
        years, ok = None, False
    elif debt <= 0:
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
