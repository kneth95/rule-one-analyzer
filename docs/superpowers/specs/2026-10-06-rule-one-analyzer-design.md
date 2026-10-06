# Rule #1 Analyzer — Design

Date: 2026-10-06
Status: Draft for review

## 1. Purpose

A personal tool that analyzes a watchlist of US stocks using Phil Town's Rule #1
method and emails the owner when a stock reaches a buy price. A web dashboard
shows the analysis, explains every term in plain English, and makes all data
easy to copy for deeper research.

The owner judges Meaning, Moat and Management (three of the 4 Ms) by choosing
what goes on the watchlist. The tool covers the numbers: the Big Five, debt,
valuation and Margin of Safety.

### Decisions made

| Topic | Decision |
|---|---|
| Stock universe | Owner-curated watchlist, not a market-wide screener |
| Markets | US only |
| Notifications | Email via Gmail SMTP (app password). No Telegram, no LLM/API usage |
| Hosting | Public GitHub repo, GitHub Actions for scheduled runs, GitHub Pages for the dashboard |
| Dashboard tech | Plain HTML/CSS/JS, no build step, libraries from CDN |
| Alerts | Tiered: Buy zone / Getting close, emailed only when a stock enters a tier |

### Out of scope (YAGNI)

- Market-wide screening, non-US markets
- Chat assistants, Telegram, any LLM integration
- Technical timing indicators (MACD, stochastics, moving averages)
- Portfolio / position tracking
- Multi-user support

## 2. Architecture

```
rule-one-analyzer/            (public GitHub repo)
├── watchlist.json            what is tracked; edited from the dashboard or by hand
├── settings.json             all thresholds (see §5)
├── engine/                   Python package: fetch → compute → output → notify
│   ├── sec.py                SEC EDGAR client (companyfacts XBRL API)
│   ├── market.py             Yahoo Finance client (price, history, analyst growth)
│   ├── financials.py         maps raw XBRL facts → clean yearly series
│   ├── bigfive.py            Big Five + debt check
│   ├── valuation.py          Sticker Price, MOS, Ten Cap, Payback Time
│   ├── tiers.py              tier assignment
│   ├── alerts.py             tier-change detection + email composition/sending
│   ├── output.py             results.json + CSV writing
│   └── main.py               orchestrates one run
├── tests/                    pytest, offline, fixture-based
├── data/
│   ├── results.json          latest full results (committed each run)
│   └── alert_state.json      last emailed tier per ticker
├── site/                     dashboard (deployed to GitHub Pages)
│   ├── index.html            watchlist page
│   ├── stock.html            per-stock detail page
│   ├── guide.html            Rule #1 guide + glossary
│   ├── settings.html         view/edit thresholds
│   ├── app.js, github.js, glossary.js, style.css
└── .github/workflows/
    └── analyze.yml           schedule + manual "Run now" + on watchlist/settings change
```

Each engine module has one job and is testable without the network: `sec.py`
and `market.py` are the only modules that do I/O against outside services.

### Run flow (`analyze.yml`)

Triggers:
- Schedule: weekdays at 22:00 UTC (after US market close)
- `workflow_dispatch`: the dashboard's "Analyze now" button
- `push` that changes `watchlist.json` or `settings.json`

Steps:
1. Read `watchlist.json` and `settings.json`.
2. For each ticker: fetch SEC EDGAR company facts (10+ years of annual 10-K data)
   and Yahoo data (current price, daily price history, analyst 5-year growth
   estimate, shares outstanding).
3. Build clean yearly series and compute Big Five, debt check, valuation, tier.
4. Write `data/results.json`, then copy it plus CSV exports into `site/data/`.
5. Compare each tier against `data/alert_state.json`. If any stock moved *up*
   into Getting close or Buy zone, send one summary email. Update the state file.
   A stock that drops out of a tier is reset, so a later re-entry alerts again.
6. Commit `data/` changes and deploy `site/` to GitHub Pages.

### Secrets (GitHub Actions secrets, never in the repo)

- `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`: sender account
- `ALERT_EMAIL_TO`: recipient (may equal sender)
- `SEC_USER_AGENT`: SEC requires a contact string such as `"Name email@example.com"`

## 3. Data

### SEC EDGAR

- Ticker → CIK via `https://www.sec.gov/files/company_tickers.json`
- Facts via `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`
- Use annual values from 10-K filings (`fp == "FY"`, form `10-K`/`10-K/A`), the
  latest filed value per fiscal year.
- Respect the SEC limit of 10 requests/second and send the `SEC_USER_AGENT` header.
- Companies tag the same concept differently. `financials.py` holds an ordered
  fallback list per field, e.g. revenue: `RevenueFromContractWithCustomerExcludingAssessedTax`
  → `Revenues` → `SalesRevenueNet`. The first concept with data for a year wins.

Yearly fields extracted: revenue, operating income, pre-tax income, income tax,
net income, diluted EPS, diluted shares, stockholders' equity, long-term debt
(plus current portion), operating cash flow, capital expenditures, depreciation
& amortization, change in accounts receivable, change in accounts payable.

### Yahoo Finance (via `yfinance`)

- Current price and daily close history (for historical year-end P/E)
- Analyst 5-year EPS growth estimate when available
- If Yahoo fails, the stock keeps its previous results, marked **stale** with a
  warning. Stale results never trigger alerts.

### watchlist.json

```json
{
  "tickers": [
    { "symbol": "AAPL", "added": "2026-10-06", "notes": "", "growth_override": null }
  ]
}
```

`growth_override` lets the owner force a growth rate (e.g. `0.12`) when the
automatic estimate looks wrong. The dashboard shows when an override is used.

## 4. Analysis rules

All thresholds come from `settings.json`. Defaults are shown here.

### Big Five

Windows: 10, 5, 3, 1 years (or as many as the data allows).

| Metric | Formula | Window value |
|---|---|---|
| ROIC | operating income × (1 − effective tax rate) ÷ (equity + total debt) | average ROIC over the window |
| Sales growth | revenue | CAGR |
| EPS growth | diluted EPS | CAGR |
| Equity growth | equity ÷ diluted shares (book value per share) | CAGR |
| FCF growth | operating cash flow − capex | CAGR |

- A window passes if its value is ≥ 10%.
- A metric **passes** if at least 3 of its available windows pass **and** the
  1-year value is not more than 10 percentage points below the 10-year value
  (the trend is not collapsing).
- **Big Five score** = number of passing metrics, from 0 to 5.
- CAGR needs positive start and end values. If the window's start year is ≤ 0,
  the tool uses the nearest later positive year and shows a warning. If none
  exists, the window is `n/a`, which counts as not passing.
- Fewer than 10 years of history: the tool computes what it can and warns.

### Debt check

Payoff years = long-term debt ÷ latest free cash flow. Passes if ≤ 3. Shown next
to the Big Five score but not counted in it. Negative FCF with any debt fails.

### Valuation

1. **Growth rate** = min(10-year equity growth, analyst 5-year estimate), capped
   at 15%. If the analyst estimate is missing, the tool uses equity growth alone
   and warns. `growth_override` replaces this step.
2. **Future EPS** = current (latest fiscal year) EPS × (1 + growth)^10
3. **Future P/E** = min(growth × 100 × 2, 10-year average historical P/E), capped
   at 50. Historical P/E for each year = the stock price at fiscal year end ÷ that
   year's EPS. Years with EPS ≤ 0 are excluded.
4. **Future price** = Future EPS × Future P/E
5. **Sticker Price** = Future price ÷ (1 + MARR)^10, with MARR = 15%
6. **MOS price** = Sticker Price × 50%

Not computable, with a warning: current EPS ≤ 0, or growth ≤ 0. The stock is
then tier "Not yet".

### Extra confirmations (shown, not used for tiers)

- **Owner earnings** = net income + D&A + income tax + Δaccounts payable
  − Δaccounts receivable − 50% of capex (the 50% approximates maintenance capex)
- **Ten Cap price** = owner earnings per share × 10
- **Payback Time price** = sum over years 1–8 of FCF per share × (1 + growth)^t.
  Buying at or below this price means the company's cash flow pays the price
  back within 8 years.

### Tiers

- 🟢 **Buy zone**: price ≤ MOS price **and** Big Five score ≥ 4
- 🟡 **Getting close**: price ≤ MOS price × 1.10 **and** Big Five score ≥ 4
- ⚪ **Not yet**: everything else, including stocks with missing data

## 5. settings.json

```json
{
  "marr": 0.15,
  "mos_fraction": 0.5,
  "growth_cap": 0.15,
  "pe_cap": 50,
  "big_five_threshold": 0.10,
  "big_five_min_score": 4,
  "windows_to_pass": 3,
  "trend_tolerance": 0.10,
  "debt_payoff_max_years": 3,
  "getting_close_margin": 0.10,
  "payback_years": 8
}
```

The engine validates settings on load. An invalid file fails the run with a
clear error and sends no email. The previous results stay published.

## 6. Dashboard

Static pages served by GitHub Pages. They read `data/results.json` and work
read-only for every visitor.

### Watchlist page (`index.html`)

- Table: ticker, company, price, MOS price, Sticker Price, % from MOS, Big Five
  score, debt check, status badge, data warnings indicator. Sortable.
- "Last analyzed" timestamp; stale stocks marked.
- Owner controls (shown only when a token is saved): add ticker, remove ticker,
  Analyze now.

### Stock detail page (`stock.html?t=AAPL`)

- Header: price, status badge, Big Five score, MOS price.
- Big Five table: metric × window, value, ✓/✗. Plus a small chart of each
  underlying series by year (Chart.js from CDN).
- Valuation walkthrough: each step from §4 with the actual numbers and the
  inputs used (growth source, P/E source).
- Ten Cap, Payback Time, debt payoff years.
- Warnings list.
- Notes field from the watchlist (editable by the owner).

### Explaining terms

- `glossary.js` holds one entry per term: ROIC, CAGR, EPS, Book value per share,
  Free cash flow, Big Five, Sticker Price, MOS, MARR, Future P/E, Ten Cap, Owner
  earnings, Payback Time, Debt payoff years, the 4 Ms, and each status tier.
  Each entry has: what it is, why Rule #1 uses it, what a good value looks like.
- Every term on every page has an ⓘ icon. Hover (desktop) or tap (mobile) shows
  the entry.
- `guide.html` explains the Rule #1 method and how to read the dashboard, linking
  to glossary entries.
- Badges and warnings use plain sentences, e.g. "Getting close: the price is
  within 10% of the MOS price."

### Copying and exporting data

On each stock page:
- **Copy as table**: all yearly raw data and computed metrics as tab-separated
  text that pastes cleanly into Excel or Google Sheets.
- **Copy for AI / notes**: a Markdown summary of key numbers, Big Five table,
  valuation steps and warnings.
- **Download CSV**: the yearly data for that stock.

On the watchlist page:
- **Download CSV** for the whole watchlist summary.
- A link to the raw `results.json`.

The engine generates the CSV files; the copy buttons build text in the browser.

### Settings page (`settings.html`)

Shows every setting with its glossary explanation. The owner can edit and save.

### Owner editing (GitHub token)

- The owner creates a **fine-grained personal access token** scoped to this one
  repo with Contents: read/write and Actions: read/write. They paste it once on
  the dashboard. It is stored in the browser's localStorage only.
- Add/remove/notes/settings changes commit the JSON file through the GitHub
  Contents API. The push triggers the workflow automatically.
- "Analyze now" calls the workflow_dispatch API.
- The page shows "Update queued; results in about 1–2 minutes" and a link to the
  run.
- Visitors without a token see no edit controls. Without a valid token,
  GitHub rejects all writes.

## 7. Email

One email per run, only when at least one stock moved up into a tier.

- Subject: `Rule #1: AAPL in Buy zone, MSFT getting close`
- Body (HTML with plain-text fallback), one block per stock: price, MOS price,
  % from MOS, Sticker Price, Big Five score, debt check, Ten Cap and Payback
  Time prices, warnings, and a link to its dashboard page.
- Sending failure fails the workflow run. GitHub then emails the owner that the
  run failed. Alert state is only updated after a successful send, so the alert
  retries next run.

## 8. Error handling

| Situation | Behavior |
|---|---|
| Unknown ticker (not in SEC list) | Stock shown with error "Not found in SEC filings (US companies only)"; no alert |
| Missing XBRL concept for some years | Compute what is possible; per-metric `n/a`; warning |
| SEC or Yahoo request fails | Retry 3× with backoff; then keep previous results marked stale |
| Invalid settings/watchlist JSON | Run fails with a clear message; previous site stays up |
| One ticker crashes the calculation | Logged and shown as error for that ticker; other tickers continue |

## 9. Testing

- **pytest** unit tests for `financials`, `bigfive`, `valuation`, `tiers` and
  `alerts` with small hand-computed fixtures. One test per rule in §4, including
  the edge cases (negative start values, missing years, EPS ≤ 0, caps).
- Recorded SEC companyfacts JSON for 2–3 real companies stored as fixtures to
  test concept mapping. Tests never use the network.
- Email sending tested with a fake SMTP class.
- The workflow runs tests before analysis. Failing tests stop the run.
- The dashboard is checked by hand against a sample `results.json`, including
  phone width.

## 10. Setup (owner, one time)

1. Create the public GitHub repo and push.
2. Add the four secrets (§2).
3. Enable GitHub Pages with source "GitHub Actions".
4. Create the fine-grained token and paste it into the dashboard.
5. Click "Analyze now".

The README walks through each step, including creating a Gmail app password and
optionally disabling issues/pull requests.
