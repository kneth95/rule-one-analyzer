"""Run one analysis pass: fetch, compute, write results, send alerts."""
import argparse
import os
import smtplib
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from engine.alerts import compose_email, detect_changes, email_config_from_env, send_email
from engine.bigfive import analyze_big_five
from engine.config import ConfigError, load_settings, load_watchlist
from engine.financials import NoFinancialsError, build_financials
from engine.market import fetch_market
from engine.output import HISTORY_COLUMNS, read_json, write_csvs, write_json
from engine.retry import FetchError
from engine.sec import NotFoundError, SecClient
from engine.tiers import assign_tier
from engine.valuation import analyze_valuation, historical_pe


def site_url_from_env(env):
    if env.get("SITE_URL"):
        return env["SITE_URL"]
    owner, _, repo = env.get("GITHUB_REPOSITORY", "owner/rule-one-analyzer").partition("/")
    return f"https://{owner.lower()}.github.io/{repo}/"


def error_result(entry, message, now_iso):
    return {"symbol": entry["symbol"], "name": "", "as_of": now_iso, "stale": False, "stale_reason": None,
            "error": message, "notes": entry.get("notes", ""), "growth_override": entry.get("growth_override"),
            "price": None, "tier": "not_yet", "tier_reason": "Not yet: the analysis couldn't run (see the error).",
            "big_five": None, "valuation": None, "history": None, "warnings": []}


def _history(fin, pe_by_year):
    h = {"years": fin.years, "fy_end": {str(y): e for y, e in fin.fy_end.items()}}
    for field, _ in HISTORY_COLUMNS:
        source = pe_by_year if field == "pe" else fin.series(field)
        h[field] = {str(y): v for y, v in source.items()}
    return h


def analyze_ticker(entry, sec, market_fetch, settings, now_iso):
    symbol = entry["symbol"]
    cik = sec.cik_for(symbol)
    if cik is None:
        return error_result(entry, "Not found in SEC filings. This tool covers US companies that file 10-K reports.",
                            now_iso)
    try:
        facts = sec.company_facts(cik)
    except NotFoundError:
        return error_result(entry, "The SEC has no XBRL financial data for this company.", now_iso)
    market = market_fetch(symbol)
    try:
        fin = build_financials(facts, market.splits)
    except NoFinancialsError as e:
        return error_result(entry, str(e), now_iso)
    big_five = analyze_big_five(fin, settings)
    valuation = analyze_valuation(fin, market, big_five, entry.get("growth_override"), settings)
    tier, reason = assign_tier(market.price, valuation["mos_price"], big_five["score"], settings)
    warnings = market.warnings + fin.warnings + big_five.pop("warnings") + valuation.pop("warnings")
    return {
        "symbol": symbol, "name": fin.name, "as_of": now_iso, "stale": False, "stale_reason": None,
        "error": None, "notes": entry.get("notes", ""), "growth_override": entry.get("growth_override"),
        "price": market.price, "tier": tier, "tier_reason": reason,
        "big_five": big_five, "valuation": valuation,
        "history": _history(fin, historical_pe(fin, market.monthly_closes)),
        "warnings": warnings,
    }


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


def run(root, env, sec=None, market_fetch=fetch_market, smtp_factory=smtplib.SMTP_SSL, now=None, send=True):
    root = Path(root)
    try:
        settings = load_settings(root / "settings.json")
        watchlist = load_watchlist(root / "watchlist.json")
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    now_iso = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data_dir = root / "data"
    previous = {s["symbol"]: s for s in read_json(data_dir / "results.json", {"stocks": []}).get("stocks", [])}
    sec = sec or SecClient(env.get("SEC_USER_AGENT", ""))

    stocks = []
    for entry in watchlist:
        print(f"Analyzing {entry['symbol']}...")
        stocks.append(analyze_with_fallback(entry, sec, market_fetch, settings, now_iso, previous.get(entry["symbol"])))

    write_json(data_dir / "results.json", {
        "generated_at": now_iso, "settings": settings,
        "columns": [list(c) for c in HISTORY_COLUMNS], "stocks": stocks,
    })
    write_csvs(stocks, data_dir / "csv")

    if not send:
        return 0
    state_path = data_dir / "alert_state.json"
    alerts, new_state = detect_changes(stocks, read_json(state_path, {}))
    if alerts:
        cfg = email_config_from_env(env)
        if cfg is None:
            print("Alerts found but email isn't configured (GMAIL_ADDRESS, GMAIL_APP_PASSWORD, ALERT_EMAIL_TO).")
            for a in alerts:
                print(f"  {a['symbol']}: {a['tier_reason']}")
            return 0
        subject, text, html = compose_email(alerts, site_url_from_env(env))
        try:
            send_email(subject, text, html, cfg, smtp_factory=smtp_factory)
        except Exception as e:
            print(f"Email failed: {e}. Alerts will retry next run.", file=sys.stderr)
            return 1
        print(f"Sent: {subject}")
    write_json(state_path, new_state)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rule #1 watchlist analyzer")
    parser.add_argument("--root", default=".", help="repo root containing watchlist.json and settings.json")
    parser.add_argument("--no-email", action="store_true", help="skip alerts (and leave alert state untouched)")
    args = parser.parse_args(argv)
    return run(Path(args.root), os.environ, send=not args.no_email)


if __name__ == "__main__":
    sys.exit(main())
