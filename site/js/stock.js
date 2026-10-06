import { badge, initPage, loadResults, term, toast } from "./common.js";
import { attachTerms } from "./glossary.js";
import { bigMoney, escapeHtml, historyRows, money, num, pct, signedPct, stockMarkdown, toTsv } from "./format.js";
import { actionsUrl, updateJsonFile } from "./github.js";

const METRIC_TERMS = { roic: "roic", sales: "sales_growth", eps: "eps_growth", equity: "equity_growth", fcf: "fcf_growth" };
const CHARTS = [["revenue", "Revenue", bigMoney], ["eps_diluted", "EPS", money], ["bvps", "Book value per share", money],
  ["fcf", "Free cash flow", bigMoney], ["roic", "ROIC", pct]];

const stat = (label, value, key) => `<div class="stat"><div class="label">${key ? term(key, label) : escapeHtml(label)}</div><div class="value">${value}</div></div>`;

function windowCell(w) {
  if (!w.available) return `<td class="muted" title="Not enough history">—</td>`;
  if (w.value == null) return `<td class="fail" title="${escapeHtml(w.note || "")}">n/a</td>`;
  return `<td class="${w.pass ? "pass" : "fail"}" title="${escapeHtml(w.note || `${w.start_year}–${w.end_year}`)}">${pct(w.value)} ${w.pass ? "✓" : "✗"}</td>`;
}

function bigFiveSection(bf) {
  const rows = Object.entries(bf.metrics).map(([key, m]) => `<tr>
      <td>${term(METRIC_TERMS[key], m.label)}</td>
      ${["10", "5", "3", "1"].map((k) => windowCell(m.windows[k])).join("")}
      <td class="${m.pass ? "pass" : "fail"}">${m.pass ? "Pass" : "Fail"}${m.trend_ok ? "" : " (falling)"}</td>
    </tr>`).join("");
  const d = bf.debt;
  return `<section class="card">
    <h2>${term("big_five", "Big Five")}: ${bf.score} of 5 pass</h2>
    <p class="muted">Each number should be at least 10% over the ${term("windows", "10, 5, 3 and 1-year windows")}. Hover a cell to see the years used.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Number</th><th>10 yr</th><th>5 yr</th><th>3 yr</th><th>1 yr</th><th>Result</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <p>${term("debt", "Debt payoff")}: <b class="${d.pass ? "pass" : "fail"}">${d.payoff_years == null ? "can't be paid from cash flow" : num(d.payoff_years, 1) + " years"}</b>
      <span class="muted">(${bigMoney(d.total_debt)} long-term debt ÷ ${bigMoney(d.fcf)} free cash flow in ${d.year}; should be 3 years or less)</span></p>
  </section>`;
}

function valuationSection(v, settings) {
  const step = (label, key, value, explain) => `<li><div>${term(key, label)}<div class="muted">${explain}</div></div><div class="value">${value}</div></li>`;
  const steps = v.computable ? [
    step("Growth rate used", "growth_rate", pct(v.growth_rate), `Source: ${escapeHtml(v.growth_source)}. Historical equity growth ${pct(v.equity_growth)}, analyst estimate ${pct(v.analyst_growth)}.`),
    step("Current EPS", "eps", money(v.current_eps), `From the ${v.eps_year} annual report (diluted, split-adjusted).`),
    step("Future EPS", "future_eps", money(v.future_eps), `${money(v.current_eps)} × (1 + ${pct(v.growth_rate)})¹⁰`),
    step("Future P/E", "future_pe", num(v.future_pe, 1), `Lower of 2 × growth (${num(v.pe_from_growth, 1)}) and the ${v.historical_pe_years}-year average P/E (${num(v.historical_pe_avg, 1)}), max ${settings.pe_cap}.`),
    step("Future price", "future_price", money(v.future_price), `${money(v.future_eps)} × ${num(v.future_pe, 1)}`),
    step("Sticker Price", "sticker_price", money(v.sticker_price), `${money(v.future_price)} ÷ (1 + ${pct(settings.marr, 0)})¹⁰, discounted at the ${term("marr", "MARR")}`),
    step("MOS price", "mos_price", money(v.mos_price), `${money(v.sticker_price)} × ${pct(settings.mos_fraction, 0)}`),
  ].join("") : "";
  return `<section class="card">
    <h2>Valuation, step by step</h2>
    ${v.computable ? `<ol class="steps">${steps}</ol>` : `<p class="banner">The Sticker Price couldn't be calculated. See the warnings below.</p>`}
    <h2 style="margin-top:20px">Extra checks</h2>
    <div class="grid">
      ${stat("Ten Cap price", money(v.ten_cap_price), "ten_cap")}
      ${stat("Payback Time price", money(v.payback_price), "payback_time")}
      ${stat("Owner earnings / share", money(v.owner_earnings_ps), "owner_earnings")}
      ${stat("Free cash flow / share", money(v.fcf_ps), "fcf")}
    </div>
  </section>`;
}

function inputsSection(s) {
  return `<section class="card owner-only">
    <h2>Your inputs</h2>
    <form id="inputs-form" class="grid">
      <label>Notes (your Meaning / Moat / Management thoughts)<textarea name="notes">${escapeHtml(s.notes || "")}</textarea></label>
      <label>${term("growth_override", "Growth override")} <span class="muted">(decimal, e.g. 0.12; leave empty for automatic)</span>
        <input name="override" inputmode="decimal" value="${s.growth_override ?? ""}" /></label>
      <div class="row"><button class="primary">Save inputs</button></div>
    </form>
  </section>`;
}

function render(s, results) {
  const v = s.valuation;
  document.title = `${s.symbol} – Rule #1`;
  const banners = [
    s.error ? `<p class="banner error">${escapeHtml(s.error)}</p>` : "",
    s.stale ? `<p class="banner">${term("stale", "Stale data")}: ${escapeHtml(s.stale_reason)}</p>` : "",
    s.growth_override != null ? `<p class="banner">Using your growth override of ${pct(s.growth_override)}.</p>` : "",
  ].join("");
  const head = `<h1>${escapeHtml(s.symbol)} <span class="muted">${escapeHtml(s.name)}</span></h1>
    <p>${badge(s.tier)} ${escapeHtml(s.tier_reason)}</p>${banners}`;
  if (s.error) return head + inputsSection(s);
  return head + `
    <section class="card grid">
      ${stat("Price", money(s.price))}
      ${stat("MOS price", money(v.mos_price), "mos_price")}
      ${stat("Sticker Price", money(v.sticker_price), "sticker_price")}
      ${stat("Price vs MOS", signedPct(v.pct_from_mos), "pct_from_mos")}
      ${stat("Big Five score", `${s.big_five.score} / 5`, "big_five_score")}
    </section>
    ${bigFiveSection(s.big_five)}
    <section class="card"><h2>Trends by year</h2><div class="charts">
      ${CHARTS.map(([f, label]) => `<div class="chart"><canvas data-field="${f}" aria-label="${label} by year"></canvas></div>`).join("")}
    </div></section>
    ${valuationSection(v, results.settings)}
    ${s.warnings.length ? `<section class="card"><h2>Data warnings</h2><ul class="warnings">${s.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul></section>` : ""}
    ${inputsSection(s)}
    <section class="card">
      <h2>Use this data</h2>
      <p class="muted">Copy everything for a spreadsheet or for an AI chat / notes.</p>
      <div class="row">
        <button id="copy-table">Copy as table</button>
        <button id="copy-md">Copy for AI / notes</button>
        <a class="button" href="data/csv/${encodeURIComponent(s.symbol)}.csv" download>Download CSV</a>
      </div>
    </section>
    <p class="muted">Analyzed ${new Date(s.as_of).toLocaleString()}. Data: SEC EDGAR and Yahoo Finance. Not financial advice.</p>`;
}

function drawCharts(s) {
  if (!window.Chart) return;
  const css = getComputedStyle(document.documentElement);
  const color = css.getPropertyValue("--accent").trim();
  const grid = css.getPropertyValue("--border").trim();
  const text = css.getPropertyValue("--muted").trim();
  for (const canvas of document.querySelectorAll("canvas[data-field]")) {
    const [field, label, fmt] = CHARTS.find(([f]) => f === canvas.dataset.field);
    const years = s.history.years;
    const data = years.map((y) => s.history[field]?.[String(y)] ?? null);
    new window.Chart(canvas, {
      type: "bar",
      data: { labels: years, datasets: [{ label, data, backgroundColor: color, borderRadius: 3 }] },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, title: { display: true, text: label, color: text },
                   tooltip: { callbacks: { label: (c) => fmt(c.raw) } } },
        scales: { x: { ticks: { color: text }, grid: { display: false } },
                  y: { ticks: { color: text, callback: (v) => fmt(v) }, grid: { color: grid } } },
      },
    });
  }
}

async function copy(text, what) {
  try {
    await navigator.clipboard.writeText(text);
    toast(`${what} copied.`, "ok");
  } catch {
    toast("Your browser blocked copying. Use Download CSV instead.", "error");
  }
}

function wire(s, results) {
  document.querySelector("#copy-table")?.addEventListener("click", () => copy(toTsv(historyRows(s, results.columns)), "Table"));
  document.querySelector("#copy-md")?.addEventListener("click", () => copy(stockMarkdown(s, results.columns), "Summary"));
  document.querySelector("#inputs-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    const raw = String(form.get("override") || "").trim();
    const override = raw === "" ? null : Number(raw);
    if (override !== null && !(override > 0 && override <= 1)) return toast("Growth override must be a decimal between 0 and 1, e.g. 0.12.", "error");
    const btn = e.submitter;
    btn.disabled = true;
    try {
      await updateJsonFile("watchlist.json", (w) => {
        const t = w.tickers.find((x) => x.symbol === s.symbol);
        if (!t) throw new Error(`${s.symbol} is no longer on the watchlist.`);
        t.notes = String(form.get("notes") || "");
        t.growth_override = override;
        return w;
      }, `Update ${s.symbol} inputs`);
      toast(`Saved. The analysis re-runs in about 1–2 minutes. <a href="${actionsUrl()}" target="_blank" rel="noopener">Watch the run</a>`, "ok");
    } catch (err) {
      toast(escapeHtml(err.message), "error");
    } finally {
      btn.disabled = false;
    }
  });
}

async function main() {
  initPage();
  const container = document.querySelector("#content");
  const symbol = new URLSearchParams(location.search).get("t");
  try {
    const results = await loadResults();
    const s = results.stocks.find((x) => x.symbol === symbol);
    if (!s) {
      container.innerHTML = `<p class="banner">${escapeHtml(symbol || "That stock")} isn't in the latest results. <a href="index.html">Back to the watchlist</a></p>`;
      return;
    }
    container.innerHTML = render(s, results);
    attachTerms(container);
    wire(s, results);
    if (s.history) drawCharts(s);
  } catch (err) {
    container.innerHTML = `<p class="banner error">${escapeHtml(err.message)}</p>`;
  }
}

main();
