"""Weekly S&P 500 scan: run the Rule #1 analysis on every constituent and write Discover data."""
import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from engine.config import ConfigError, load_settings
from engine.main import analyze_with_fallback
from engine.market import fetch_market
from engine.output import HISTORY_COLUMNS, _csv, read_json, write_json
from engine.sec import SecClient
from engine.tiers import TIER_LABEL
from engine.universe import UniverseError, fetch_wikipedia, load_universe


def summarize(stock, name, sector):
    v = stock.get("valuation") or {}
    bf = stock.get("big_five") or {}
    debt = bf.get("debt") or {}
    return {
        "symbol": stock["symbol"], "name": name, "sector": sector, "price": stock.get("price"),
        "tier": stock.get("tier", "not_yet"), "tier_reason": stock.get("tier_reason", ""),
        "stale": bool(stock.get("stale")), "mos_price": v.get("mos_price"), "sticker_price": v.get("sticker_price"),
        "pct_from_mos": v.get("pct_from_mos"), "score": bf.get("score"), "debt_years": debt.get("payoff_years"),
        "debt_pass": debt.get("pass"), "growth_rate": v.get("growth_rate"),
        "warnings_count": len(stock.get("warnings") or []),
    }


def discover_csv(summaries):
    cell = lambda v: "" if v is None else v
    rows = [["Symbol", "Company", "Sector", "Status", "Price", "MOS price", "Sticker Price", "Price vs MOS",
             "Big Five score", "Debt payoff years", "Growth rate used", "Stale"]]
    for s in summaries:
        rows.append([s["symbol"], s["name"], s["sector"], TIER_LABEL[s["tier"]], cell(s["price"]),
                     cell(s["mos_price"]), cell(s["sticker_price"]), cell(s["pct_from_mos"]), cell(s["score"]),
                     cell(s["debt_years"]), cell(s["growth_rate"]), "yes" if s["stale"] else ""])
    return _csv(rows)


def run(out_dir, previous_dir, root, env, limit=None, sec=None, market_fetch=fetch_market,
        fetch_html=fetch_wikipedia, sleep=time.sleep, now=None, min_rows=400, pause=0.5):
    out, previous_dir, root = Path(out_dir), Path(previous_dir), Path(root)
    try:
        settings = load_settings(root / "settings.json")
        universe, source, warnings = load_universe(fetch_html, previous_dir / "sp500.json", min_rows)
    except (ConfigError, UniverseError) as e:
        print(f"Discover scan can't start: {e}", file=sys.stderr)
        return 2

    now_iso = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sec = sec or SecClient(env.get("SEC_USER_AGENT", ""))
    scan_list = universe[:limit] if limit else universe
    summaries, failed = [], []
    for i, company in enumerate(scan_list):
        if i:
            sleep(pause)
        symbol = company["symbol"]
        print(f"[{i + 1}/{len(scan_list)}] {symbol}")
        prev = read_json(previous_dir / "stocks" / f"{symbol}.json", None)
        entry = {"symbol": symbol, "notes": "", "growth_override": None}
        stock = analyze_with_fallback(entry, sec, market_fetch, settings, now_iso, prev)
        if stock.get("error"):
            failed.append({"symbol": symbol, "name": company["name"], "reason": stock["error"]})
            continue
        write_json(out / "stocks" / f"{symbol}.json", stock)
        summaries.append(summarize(stock, company["name"], company["sector"]))

    write_json(out / "discover.json", {
        "generated_at": now_iso, "settings": settings, "columns": [list(c) for c in HISTORY_COLUMNS],
        "universe_source": source, "warnings": warnings,
        "counts": {"total": len(scan_list), "analyzed": len(summaries), "failed": len(failed)},
        "stocks": summaries, "failed": failed,
    })
    (out / "csv").mkdir(parents=True, exist_ok=True)
    (out / "csv" / "discover.csv").write_text(discover_csv(summaries), encoding="utf-8")
    write_json(out / "sp500.json", universe)
    print(f"Done: {len(summaries)} analyzed, {len(failed)} couldn't be analyzed.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Weekly S&P 500 Rule #1 scan")
    parser.add_argument("--out", required=True, help="directory for the scan output")
    parser.add_argument("--previous", required=True, help="directory holding the previous scan (may not exist)")
    parser.add_argument("--root", default=".", help="repo root containing settings.json")
    parser.add_argument("--limit", type=int, help="scan only the first N companies (local testing)")
    args = parser.parse_args(argv)
    return run(args.out, args.previous, args.root, os.environ, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())
