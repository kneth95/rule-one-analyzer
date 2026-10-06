// Plain-English explanations for every Rule #1 term, plus the ⓘ tooltip behavior.

export const GLOSSARY = {
  rule1: { term: "Rule #1", what: "Phil Town's investing method, named after Warren Buffett's \"Rule #1: don't lose money.\"", why: "Buy wonderful companies at attractive prices so the downside is limited.", good: "A company that passes the 4 Ms and trades below its MOS price." },
  four_ms: { term: "The 4 Ms", what: "Meaning (you understand it), Moat (durable advantage), Management (honest, capable owners), Margin of Safety (bought cheap).", why: "Rule #1 only buys businesses that pass all four.", good: "This tool checks the numbers behind Moat and Margin of Safety. You judge Meaning, Moat and Management when you add a stock." },
  meaning: { term: "Meaning", what: "You understand how the business makes money and would be proud to own all of it.", why: "You can only judge a company's future if you understand it.", good: "You could explain the business to a friend in two minutes." },
  moat: { term: "Moat", what: "A durable competitive advantage: brand, switching costs, network effects, low costs, or a toll-bridge position.", why: "A moat protects profits from competitors for years.", good: "Big Five numbers that stay ≥ 10% for 10 years are evidence of a moat." },
  management: { term: "Management", what: "The leaders running the company.", why: "Rule #1 wants owner-oriented managers who are honest and allocate money well.", good: "High, steady ROIC and clear, candid shareholder letters." },
  big_five: { term: "Big Five", what: "Five numbers Rule #1 uses to test for a moat: ROIC, Sales growth, EPS growth, Equity growth and Free cash flow growth.", why: "Consistently high numbers over 10 years suggest a durable business.", good: "Each one at 10% or more over 10, 5, 3 and 1 years." },
  big_five_score: { term: "Big Five score", what: "How many of the five numbers pass (0 to 5). A number passes when most of its 10/5/3/1-year checks are at least 10% and the latest year isn't collapsing.", why: "Real data has noisy years, so the tool counts mostly-passing numbers instead of demanding perfection.", good: "4 or 5. Alerts need at least 4 by default." },
  roic: { term: "ROIC (Return on Invested Capital)", what: "After-tax operating profit ÷ (shareholders' equity + debt). How much profit the business earns on the money invested in it.", why: "Phil Town calls it the most important Big Five number: it shows how well management uses capital.", good: "10% or higher, every year." },
  sales_growth: { term: "Sales growth", what: "How fast revenue (total sales) grew per year.", why: "A growing business usually has products people keep wanting.", good: "10% or more per year." },
  eps: { term: "EPS (Earnings Per Share)", what: "Net profit divided by the number of shares. Here it's diluted and adjusted for stock splits.", why: "Profit per share is what each share you own earns.", good: "Growing 10% or more per year." },
  eps_growth: { term: "EPS growth", what: "How fast earnings per share grew per year.", why: "Growing earnings drive a growing stock price over time.", good: "10% or more per year." },
  equity_growth: { term: "Equity growth (book value per share)", what: "How fast shareholders' equity per share grew per year. Equity is what the company owns minus what it owes.", why: "Phil Town treats it as the best measure of how fast the owners' stake is growing. It also feeds the growth rate used for the Sticker Price.", good: "10% or more per year." },
  bvps: { term: "Book value per share", what: "Shareholders' equity ÷ number of shares.", why: "It's the per-share version of equity, used for Equity growth.", good: "Rising steadily." },
  fcf: { term: "Free cash flow (FCF)", what: "Cash from operations minus capital expenditures. The cash left over after keeping the business running and growing.", why: "Profits can be massaged with accounting; cash is harder to fake.", good: "Positive and growing 10% or more per year." },
  fcf_growth: { term: "Free cash flow growth", what: "How fast free cash flow grew per year.", why: "Growing cash flow funds dividends, buybacks and debt payoff.", good: "10% or more per year." },
  cagr: { term: "CAGR (Compound Annual Growth Rate)", what: "The steady yearly growth rate that would turn the starting value into the ending value.", why: "It summarizes growth over many years as one comparable number.", good: "For the Big Five: 10% or more." },
  windows: { term: "10 / 5 / 3 / 1-year windows", what: "Each Big Five number is measured over the last 10, 5, 3 and 1 years.", why: "Long windows show durability; short windows show whether things are getting worse.", good: "All at 10% or more, with no sharp drop in the recent windows." },
  debt: { term: "Debt payoff years", what: "Long-term debt ÷ latest free cash flow: how many years of cash flow it would take to pay off all long-term debt.", why: "Too much debt can sink even a good business in a bad year.", good: "3 years or less." },
  growth_rate: { term: "Growth rate used", what: "The yearly growth rate assumed for the next 10 years: the lower of historical equity growth and the analysts' 5-year estimate, capped at 15%.", why: "Using the lower number keeps the valuation conservative.", good: "Something you believe the company can actually sustain. You can override it per stock." },
  analyst_growth: { term: "Analyst 5-year growth estimate", what: "Wall Street analysts' average forecast for yearly earnings growth over the next five years (from Yahoo Finance).", why: "Rule #1 compares it with historical growth and uses the lower one.", good: "Not always available; the tool warns when it's missing." },
  future_eps: { term: "Future EPS", what: "Current EPS grown at the growth rate for 10 years.", why: "It estimates what each share will earn a decade from now.", good: "—" },
  future_pe: { term: "Future P/E", what: "The P/E the stock is expected to trade at in 10 years: the lower of 2 × the growth rate and the stock's 10-year average P/E, capped at 50.", why: "Using the lower value avoids paying for an unrealistically high future price.", good: "—" },
  pe: { term: "P/E (Price-to-Earnings)", what: "Share price ÷ earnings per share. How many dollars investors pay for each dollar of yearly profit.", why: "It's used to turn future earnings into a future price.", good: "Depends on growth. Rule #1 caps it at 2 × the growth rate." },
  future_price: { term: "Future price", what: "Future EPS × Future P/E: the estimated share price 10 years from now.", why: "It's the starting point for working back to today's value.", good: "—" },
  marr: { term: "MARR (Minimum Acceptable Rate of Return)", what: "The yearly return you require: 15% in Rule #1.", why: "The future price is discounted back to today at this rate to find what you can pay and still earn 15% a year.", good: "15% is Phil Town's standard." },
  sticker_price: { term: "Sticker Price", what: "Future price discounted back 10 years at the MARR. Rule #1's estimate of what the business is worth today.", why: "It's the fair value. Rule #1 never pays fair value; it waits for a discount.", good: "—" },
  mos: { term: "MOS (Margin of Safety)", what: "Buying well below the Sticker Price, by default at 50% of it.", why: "The discount protects you if your estimates turn out too optimistic.", good: "Buy at or below the MOS price." },
  mos_price: { term: "MOS price", what: "Sticker Price × 50%: the price at or below which Rule #1 says to buy.", why: "This is the buy target that triggers the 🟢 Buy zone alert.", good: "Current price at or below it." },
  pct_from_mos: { term: "Price vs MOS", what: "How far the current price is above (+) or below (−) the MOS price.", why: "It shows how close a stock is to a buy.", good: "0% or negative means it's in the Buy zone." },
  owner_earnings: { term: "Owner earnings", what: "Net income + depreciation & amortization + income tax + change in payables − change in receivables − maintenance capital spending (estimated as half of capex).", why: "Buffett's measure of the cash an owner could take out of the business. It's used for the Ten Cap price.", good: "Positive and growing." },
  ten_cap: { term: "Ten Cap price", what: "Owner earnings per share × 10. The price at which owner earnings would be a 10% yearly return, like buying a rental property for its rent.", why: "It's a second, simpler valuation to confirm the Sticker Price.", good: "Current price at or below it." },
  payback_time: { term: "Payback Time price", what: "The total free cash flow per share over the next 8 years, growing at the growth rate.", why: "If you pay this or less, the company's own cash flow pays you back within 8 years.", good: "Current price at or below it." },
  tier_buy: { term: "🟢 Buy zone", what: "Price is at or below the MOS price and at least 4 of the Big Five pass.", why: "This is a Rule #1 buy signal, assuming you're happy with Meaning, Moat and Management.", good: "Do your own final research before buying." },
  tier_close: { term: "🟡 Getting close", what: "Price is within 10% above the MOS price and at least 4 of the Big Five pass.", why: "An early warning so you can finish your research before it hits the Buy zone.", good: "—" },
  tier_not_yet: { term: "⚪ Not yet", what: "The price is too high, the Big Five are too weak, or the numbers couldn't be calculated.", why: "Wonderful companies are worth waiting for.", good: "—" },
  stale: { term: "Stale", what: "The latest data couldn't be downloaded, so the last good results are shown.", why: "Stale results never send alerts, to avoid acting on old prices.", good: "It usually fixes itself on the next run." },
  discover: { term: "Discover", what: "A weekly scan of every S&P 500 company with the same Rule #1 analysis your watchlist gets.", why: "It finds wonderful companies you aren't following yet.", good: "Treat results as research leads. Judge Meaning, Moat and Management before buying." },
  wonderful_watch: { term: "⭐ Wonderful companies to watch", what: "Companies with at least 4 Big Five passes and manageable debt that are still above their MOS price, closest to it first (top 25).", why: "Rule #1 bargains are rare. Studying great businesses now means you're ready when the price drops.", good: "Add the ones you understand to your watchlist; you'll get an email when they reach Getting close or Buy zone." },
  sector: { term: "Sector", what: "The company's industry group (GICS sector), e.g. Information Technology or Consumer Staples.", why: "Filtering by sector helps you stay inside businesses you understand (Meaning).", good: "—" },
  growth_override: { term: "Growth override", what: "A growth rate you set yourself for this stock, replacing the automatic one.", why: "Use it when the automatic estimate looks wrong, e.g. after a one-off year.", good: "Be conservative. A decimal like 0.12 means 12%." },
};

let tip;
let current;

function hide() {
  if (tip) tip.hidden = true;
  current = null;
}

function show(btn) {
  const entry = GLOSSARY[btn.dataset.key];
  if (!entry) return;
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "tip";
    tip.setAttribute("role", "tooltip");
    document.body.append(tip);
  }
  tip.innerHTML = "";
  const h = document.createElement("strong");
  h.textContent = entry.term;
  tip.append(h);
  for (const [label, text] of [["What it is", entry.what], ["Why it matters", entry.why], ["What's good", entry.good]]) {
    if (!text || text === "—") continue;
    const p = document.createElement("p");
    const b = document.createElement("b");
    b.textContent = label + ": ";
    p.append(b, text);
    tip.append(p);
  }
  tip.hidden = false;
  const r = btn.getBoundingClientRect();
  const width = Math.min(320, window.innerWidth - 32);
  tip.style.width = width + "px";
  tip.style.left = Math.max(16, Math.min(r.left + window.scrollX - 8, window.scrollX + window.innerWidth - width - 16)) + "px";
  tip.style.top = r.bottom + window.scrollY + 6 + "px";
  current = btn;
}

export function attachTerms(root = document) {
  for (const el of root.querySelectorAll("[data-term]")) {
    if (el.querySelector(":scope > .info")) continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "info";
    btn.dataset.key = el.dataset.term;
    btn.textContent = "ⓘ";
    btn.setAttribute("aria-label", `What is ${GLOSSARY[el.dataset.term]?.term ?? el.textContent}?`);
    btn.addEventListener("click", (e) => { e.stopPropagation(); current === btn ? hide() : show(btn); });
    btn.addEventListener("mouseenter", () => { if (matchMedia("(hover: hover)").matches) show(btn); });
    btn.addEventListener("mouseleave", () => { if (matchMedia("(hover: hover)").matches) hide(); });
    el.append(btn);
  }
  if (!attachTerms.bound) {
    document.addEventListener("click", hide);
    document.addEventListener("keydown", (e) => e.key === "Escape" && hide());
    window.addEventListener("scroll", hide, { passive: true });
    attachTerms.bound = true;
  }
}
