"""Sticker Price, Margin of Safety, Ten Cap and Payback Time."""
from engine.bigfive import longest_value


def choose_growth(equity_growth, analyst_growth, override, cap):
    if override is not None:
        return override, "your override", []
    warnings = []
    if analyst_growth is None:
        warnings.append("No analyst 5-year growth estimate available; using historical equity growth only.")
    elif equity_growth is None:
        warnings.append("No historical equity growth available; using the analyst estimate only.")
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
