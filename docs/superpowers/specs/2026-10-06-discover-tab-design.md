# Discover Tab — Design

Date: 2026-10-06
Status: Draft for review
Builds on: `2026-10-06-rule-one-analyzer-design.md`

## 1. Purpose

A **Discover** tab that surfaces S&P 500 companies the owner doesn't follow yet
that look like Rule #1 opportunities: they pass the Big Five and trade at or near
their MOS price. They are research leads, not buy signals. The owner still judges
Meaning, Moat and Management, then adds a lead to the watchlist with one click to
get daily analysis and email alerts.

### Decisions made

| Topic | Decision |
|---|---|
| What "best to buy" means | Rule #1 discoveries (Big Five + discount to MOS), not price momentum |
| Universe | S&P 500 constituents (~503 tickers) |
| Analysis | The existing per-company engine (`analyze_ticker`), unchanged |
| Schedule | Weekly (Saturday) plus manual run, in its own workflow |
| Notifications | None. Dashboard only; emails stay reserved for the watchlist |

### Out of scope

- Momentum / "trending" lists, market-wide (non-S&P) scanning, Discover emails
- Changes to how the watchlist is analyzed or alerted

## 2. Architecture

```
engine/universe.py     S&P 500 list from Wikipedia, fallback to last saved list
engine/discover.py     scan the universe with analyze_ticker, write outputs
.github/workflows/discover.yml   weekly scan → publish to the discover-data branch → deploy site
site/discover.html, site/js/discover.js, site/js/discover-rank.js (pure ranking/filtering)
```

Reused unchanged: `SecClient`, `fetch_market`, `build_financials`,
`analyze_big_five`, `analyze_valuation`, `assign_tier`, `analyze_ticker`.

### Universe (`engine/universe.py`)

- Source: `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`, the table
  with `id="constituents"`. Columns used: Symbol, Security (company name),
  GICS Sector.
- Parsed with the standard library `html.parser` (no new dependency).
- Symbols are normalized like the watchlist (`BRK.B` → `BRK-B`).
- Sanity check: fewer than 400 rows means the page changed; the parser fails.
- Fallback: if the download or parse fails, use the list saved by the previous
  scan (`sp500.json` on the `discover-data` branch) and add a scan warning.
  If there is no saved list either, the scan fails and the previous Discover
  data stays published.

### Scan (`engine/discover.py`)

For each constituent, run `analyze_ticker` with the current `settings.json`.

- Pacing: 0.5 s pause between companies to avoid Yahoo throttling. The SEC client
  already throttles itself.
- A company that fails to download keeps its previous week's entry marked
  **stale** if one exists, otherwise it is listed under "couldn't analyze" with
  the reason. Companies that analyze but have errors (e.g. no 10-K data) are also
  listed under "couldn't analyze".
- One company crashing never stops the scan.

Outputs (written to an output directory, default `discover-out/`):
- `discover.json`: `{"generated_at", "settings", "universe_source", "warnings",
  "counts": {"total", "analyzed", "failed"}, "stocks": [summary...],
  "failed": [{"symbol", "name", "reason"}]}`. Each summary has: symbol, name,
  sector, price, tier, tier_reason, stale, mos_price, sticker_price,
  pct_from_mos, score, debt_years, debt_pass, growth_rate, warnings_count.
  Target size under 300 KB.
- `stocks/<SYMBOL>.json`: the full `analyze_ticker` result, the same shape as an
  entry in `results.json`, for the stock page.
- `csv/discover.csv`: the summary in the watchlist CSV column layout, plus Sector.
- `sp500.json`: the constituent list used, for next week's fallback.

### Storage: the `discover-data` branch

The full scan is ~500 detail files (~5–10 MB). Committing them to `main` every
week would grow the repo history without bound. Instead:

- The discover workflow publishes the output directory as a **single orphan
  commit force-pushed to the `discover-data` branch**. History stays one commit
  deep.
- Before scanning, it checks out the current `discover-data` (if it exists) to
  read last week's entries for the stale fallback and the saved S&P list.
- **Both** deploy jobs (the existing `analyze.yml` and the new `discover.yml`)
  copy `discover-data` into `site/data/discover/` when building the site, so a
  daily watchlist deploy never drops the Discover data.

### Workflow (`discover.yml`)

- Triggers: `schedule: "0 6 * * 6"` (Saturday 06:00 UTC) and `workflow_dispatch`.
- Concurrency group `discover` (separate from `analyze`, so dashboard edits on
  Saturdays aren't stuck behind a 20-minute scan).
- Steps: checkout main → run tests → fetch `discover-data` into `prev/` →
  `python -m engine.discover --out discover-out --previous prev` (a `--limit N` flag scans only the first N companies, for local testing) → force-push
  `discover-out` as `discover-data` → deploy.
- The two workflows' deploy jobs share concurrency group `pages` so they never
  deploy over each other mid-flight.
- Secrets used: `SEC_USER_AGENT` only. No email.

## 3. Ranking (`site/js/discover-rank.js`, pure and unit-tested)

Inputs: the summary list, the owner's watchlist symbols (from `results.json`),
the settings, and the filter state.

1. **🟢 Buy zone**: tier `buy`, sorted by `pct_from_mos` ascending (deepest
   discount first).
2. **🟡 Getting close**: tier `close`, same order.
3. **⭐ Wonderful companies to watch**: tier `not_yet`, `score ≥
   big_five_min_score`, `debt_pass`, `mos_price` not null, sorted by
   `pct_from_mos` ascending (closest to MOS first), top 25.

Stale stocks are included and labeled stale. Filters apply to all three lists:
- Sector (all / one GICS sector)
- Minimum Big Five score: the settings value or 5
- Hide stocks already on my watchlist

## 4. Dashboard

### Discover page (`discover.html`)

- Nav gets a **Discover** link on every page.
- Header: "Last scanned <date> · N companies · A analyzed, F couldn't be
  analyzed", plus a toggle listing failures with reasons, and any scan warnings
  (e.g. "Used last week's S&P 500 list").
- Note: "These are research leads, not buy signals. Rule #1 still needs you to
  judge Meaning, Moat and Management before buying."
- The three lists from §3, each with a one-line ⓘ explanation and a "nothing
  here this week" message when empty.
- Row: ticker + company, sector, price, MOS price, vs MOS, Big Five score, debt
  years, ⭐ if already on the watchlist, "stale" marker when stale.
- Clicking a row opens `stock.html?t=<SYMBOL>&src=discover`.
- Owner-only **+ Watch** button per row: adds the symbol to `watchlist.json`
  through the existing `updateJsonFile`, then shows the usual "results in 1–2
  minutes" toast and turns the button into "✓ Watching".
- "Download CSV" for the full scan.
- Before the first scan: "Discover hasn't run yet. Owner: Actions → Discover
  S&P 500 → Run workflow."

### Stock page changes (`stock.js`)

- Look up the symbol in `results.json` first (watchlist data, updated daily).
- If not found, load `data/discover/stocks/<SYMBOL>.json`. Show a banner:
  "From the weekly S&P 500 scan on <date>. Add it to your watchlist for daily
  updates and email alerts" with a **+ Watch** button for the owner.
- "Your inputs" (notes / growth override) only appear for watchlist stocks.
- CSV download for a Discover-only stock points to a per-stock CSV generated on
  the fly in the browser (from the same `historyRows` used by Copy as table),
  since only the summary CSV is published for Discover.

### Glossary and guide

- New glossary entries: `discover`, `wonderful_watch`, `sector`.
- Guide gets a section "Using Discover": what the three lists mean, why Buy zone
  is often empty, and how to move a lead to the watchlist.

## 5. Error handling

| Situation | Behavior |
|---|---|
| Wikipedia unreachable or page layout changed | Use last saved S&P list + scan warning; none saved → scan fails, old data stays |
| A company's SEC/Yahoo fetch fails | Last week's entry marked stale, else listed under "couldn't analyze" |
| A company has no usable 10-K data (foreign filer, odd tags) | Listed under "couldn't analyze" with the reason |
| Yahoo throttles mid-scan | Existing retries + 0.5 s pacing; failures fall into the row above |
| Invalid settings.json | Scan fails before starting; old data stays |
| No `discover-data` branch yet | First scan starts with no previous data; site shows "hasn't run yet" until it finishes |
| Daily deploy while no Discover data exists | Deploy skips the copy; Discover page shows "hasn't run yet" |

## 6. Testing

- `universe.py`: parse a saved Wikipedia HTML fixture (trimmed to a few rows plus
  the table structure); normalization; the "fewer than 400 rows" check; fallback
  to a saved list; failure when neither works.
- `discover.py`: with fake SEC/market clients (as in `test_main.py`), verify the
  summary fields, the failed list, stale fallback from a previous directory,
  crash isolation, and the output files.
- `discover-rank.js`: Node tests for the three lists, sort order, top-25 cut,
  filters, watchlist marking.
- Workflow YAML parsed in tests (both workflows have the `pages` deploy
  concurrency group and copy `discover-data`).
- Manual: run a scan locally on a 20-company slice of the list, serve the site,
  check the Discover page, the stock page fallback and phone width.
