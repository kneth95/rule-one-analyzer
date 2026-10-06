"""Download SEC company facts for tickers and save trimmed copies as test fixtures.

Usage:  SEC_USER_AGENT="Your Name you@example.com" python scripts/record_fixture.py AAPL MSFT COST
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.financials import CONCEPTS  # noqa: E402
from engine.sec import SecClient  # noqa: E402


def trim(facts):
    wanted = {c for concepts in CONCEPTS.values() for c in concepts}
    gaap = facts.get("facts", {}).get("us-gaap", {})
    out = {}
    for name in sorted(wanted & gaap.keys()):
        out[name] = {"units": {
            unit: [r for r in rows if str(r.get("form", "")).startswith("10-K")]
            for unit, rows in gaap[name]["units"].items()
        }}
    return {"cik": facts.get("cik"), "entityName": facts.get("entityName"), "facts": {"us-gaap": out}}


def main(symbols):
    sec = SecClient(os.environ.get("SEC_USER_AGENT", ""))
    out_dir = ROOT / "tests" / "fixtures" / "sec"
    out_dir.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        cik = sec.cik_for(symbol)
        trimmed = trim(sec.company_facts(cik))
        (out_dir / f"{symbol.upper()}.json").write_text(json.dumps(trimmed, separators=(",", ":")), encoding="utf-8")
        print(f"saved {symbol} ({cik})")


if __name__ == "__main__":
    main(sys.argv[1:])
