# Rule #1 Analyzer

Analyzes your watchlist of US stocks with Phil Town's **Rule #1** method, emails you when a stock gets
close to (or into) its buy price, and publishes a dashboard that explains every number.

- **Daily**: on weekdays after the US market closes, GitHub Actions downloads SEC filings and Yahoo prices,
  computes the Big Five, Sticker Price, MOS price, Ten Cap and Payback Time, and updates the dashboard.
- **Email**: one message when a stock moves into 🟡 Getting close or 🟢 Buy zone.
- **Dashboard**: plain-English ⓘ explanations, step-by-step valuation, and copy/CSV buttons for deeper research.

## One-time setup

1. **Create the repo.** Make a new **public** GitHub repo and push this folder to its `main` branch.
   (A free account needs a public repo for GitHub Pages. Your secrets stay private, see "Privacy" below.)
2. **Gmail app password.** Turn on 2-Step Verification for your Google account, then create an app password at
   <https://myaccount.google.com/apppasswords>. Copy the 16-character password.
3. **Add repo secrets.** In the repo: Settings → Secrets and variables → Actions → New repository secret.
   | Name | Value |
   |---|---|
   | `GMAIL_ADDRESS` | the Gmail address that sends alerts |
   | `GMAIL_APP_PASSWORD` | the app password from step 2 |
   | `ALERT_EMAIL_TO` | where alerts go (can be the same address) |
   | `SEC_USER_AGENT` | your name and email, e.g. `Jane Doe jane@example.com` (the SEC requires a contact) |
4. **Turn on Pages.** Settings → Pages → Source: **GitHub Actions**.
5. **Create a dashboard token.** GitHub → Settings → Developer settings → Fine-grained tokens → Generate.
   Repository access: **only this repo**. Permissions: **Contents: read and write**, **Actions: read and write**.
6. **First run.** Actions tab → "Analyze watchlist" → Run workflow. When it finishes, open
   `https://<your-username>.github.io/<repo-name>/`, click **🔑 Owner**, paste the token, and add tickers.

## Everyday use

- Add or remove stocks and click **Analyze now** on the dashboard. Results appear in about 1–2 minutes.
- Open a stock to see the Big Five, the valuation steps and warnings. Use **Copy as table** for a spreadsheet,
  or **Copy for AI / notes** for a Markdown summary.
- Change thresholds on the **Settings** page.

### Discover

Every Saturday a second workflow, **Discover S&P 500**, analyzes all S&P 500 companies (about 20 minutes) and fills
the **Discover** tab with Buy zone, Getting close and "wonderful companies to watch" lists. Click **+ Watch** to move a
company to your watchlist. To run it right away: Actions → Discover S&P 500 → Run workflow. Discover never sends email.
Its data lives on the `discover-data` branch, which is overwritten each week.

## Privacy

Anyone with the link can **view** the dashboard, your watchlist and settings. Only you can **change** them:
edits need your token, which lives only in your browser. The Gmail password lives in GitHub Secrets and is never
shown. Pull requests from strangers can't read secrets; you can also turn off Issues and Pull requests in the
repo settings.

## Running locally

```bash
python -m pip install -r requirements.txt
python -m pytest -q && node --test "tests/js/*.test.mjs"
SEC_USER_AGENT="Your Name you@example.com" python -m engine.main --no-email
cp -r data site/data && python -m http.server 8000 -d site    # open http://localhost:8000
```

To test owner features locally, set the repo in the browser console: `localStorage.setItem("r1.repo", "owner/repo")`.

## How the numbers are calculated

See [the design spec](docs/superpowers/specs/2026-10-06-rule-one-analyzer-design.md) §4 and the dashboard's Guide page.
This is a research tool, not financial advice.
