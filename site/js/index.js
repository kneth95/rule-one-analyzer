import { badge, initPage, loadResults, toast } from "./common.js";
import { attachTerms } from "./glossary.js";
import { escapeHtml, money, num, signedPct } from "./format.js";
import { actionsUrl, getToken, readJsonFile, runAnalysisNow, updateJsonFile } from "./github.js";
import { addToWatchlist, normalizeTicker } from "./watchlist.js";

const RANK = { buy: 0, close: 1, not_yet: 2 };
const SORTERS = {
  symbol: (s) => s.symbol,
  tier: (s) => RANK[s.tier] ?? 3,
  price: (s) => s.price,
  mos: (s) => s.valuation?.mos_price,
  sticker: (s) => s.valuation?.sticker_price,
  pct: (s) => s.valuation?.pct_from_mos,
  score: (s) => -(s.big_five?.score ?? -1),
  debt: (s) => s.big_five?.debt?.payoff_years,
};
let stocks = [];
let sortKey = "tier";
let sortDir = 1;

function sorted() {
  const f = SORTERS[sortKey];
  return [...stocks].sort((a, b) => {
    const x = f(a), y = f(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
  });
}

function row(s) {
  const v = s.valuation || {}, bf = s.big_five || {};
  const flags = [s.stale ? `<span class="term" data-term="stale" title="${escapeHtml(s.stale_reason)}">stale</span>` : "",
    s.error ? `<span class="fail" title="${escapeHtml(s.error)}">error</span>` : "",
    s.pending ? `<span class="muted">waiting for analysis</span>` : ""].filter(Boolean).join(" ");
  const debt = bf.debt;
  const debtCell = !debt ? "—" : `<span class="${debt.pass ? "pass" : "fail"}">${debt.payoff_years == null ? "n/a" : num(debt.payoff_years, 1)}</span>`;
  return `<tr class="clickable" data-symbol="${escapeHtml(s.symbol)}" data-pending="${s.pending ? "1" : ""}">
    <td><b>${escapeHtml(s.symbol)}</b><br><span class="muted">${escapeHtml(s.name || "")}</span> ${flags}</td>
    <td class="left">${badge(s.tier || "not_yet")}</td>
    <td>${money(s.price)}</td>
    <td>${money(v.mos_price)}</td>
    <td>${money(v.sticker_price)}</td>
    <td>${signedPct(v.pct_from_mos)}</td>
    <td>${bf.score == null ? "—" : `${bf.score}/5`}</td>
    <td>${debtCell}</td>
    <td class="owner-only"><button class="danger" data-remove="${escapeHtml(s.symbol)}" title="Remove from watchlist">✕</button></td>
  </tr>`;
}

function render() {
  const tbody = document.querySelector("#watchlist tbody");
  tbody.innerHTML = sorted().map(row).join("");
  document.querySelector("#empty").hidden = stocks.length > 0;
  attachTerms(tbody);
}

function queued(what) {
  toast(`${what} Results in about 1–2 minutes. <a href="${actionsUrl()}" target="_blank" rel="noopener">Watch the run</a>`, "ok");
}

async function addPending() {
  if (!getToken()) return;
  try {
    const { data } = await readJsonFile("watchlist.json");
    const known = new Set(stocks.map((s) => s.symbol));
    for (const t of data.tickers) {
      if (!known.has(t.symbol)) stocks.push({ symbol: t.symbol, name: "", tier: "not_yet", pending: true });
    }
    render();
  } catch { /* token problems are reported when the owner acts */ }
}

async function onAdd(e) {
  e.preventDefault();
  const input = document.querySelector("#add-symbol");
  const symbol = normalizeTicker(input.value);
  if (!symbol) return toast("That doesn't look like a ticker symbol.", "error");
  const btn = e.submitter;
  btn.disabled = true;
  try {
    await addToWatchlist(symbol);
    input.value = "";
    stocks.push({ symbol, name: "", tier: "not_yet", pending: true });
    render();
    queued(`${symbol} added.`);
  } catch (err) {
    toast(escapeHtml(err.message), "error");
  } finally {
    btn.disabled = false;
  }
}

async function onRemove(symbol) {
  if (!confirm(`Remove ${symbol} from the watchlist?`)) return;
  try {
    await updateJsonFile("watchlist.json", (w) => ({ ...w, tickers: w.tickers.filter((t) => t.symbol !== symbol) }),
      `Remove ${symbol} from watchlist`);
    stocks = stocks.filter((s) => s.symbol !== symbol);
    render();
    queued(`${symbol} removed.`);
  } catch (err) {
    toast(escapeHtml(err.message), "error");
  }
}

async function onRunNow(e) {
  e.target.disabled = true;
  try {
    await runAnalysisNow();
    queued("Analysis started.");
  } catch (err) {
    toast(escapeHtml(err.message), "error");
  } finally {
    e.target.disabled = false;
  }
}

async function main() {
  initPage();
  document.querySelector("#add-form").addEventListener("submit", onAdd);
  document.querySelector("#run-now").addEventListener("click", onRunNow);
  document.querySelectorAll("th.sortable").forEach((th) => th.addEventListener("click", (e) => {
    if (e.target.closest(".info")) return;
    const key = th.dataset.sort;
    sortDir = key === sortKey ? -sortDir : 1;
    sortKey = key;
    render();
  }));
  document.querySelector("#watchlist tbody").addEventListener("click", (e) => {
    const remove = e.target.closest("[data-remove]");
    if (remove) return onRemove(remove.dataset.remove);
    if (e.target.closest(".info")) return;
    const tr = e.target.closest("tr[data-symbol]");
    if (tr && !tr.dataset.pending) location.href = `stock.html?t=${encodeURIComponent(tr.dataset.symbol)}`;
  });
  try {
    const results = await loadResults();
    stocks = results.stocks;
    document.querySelector("#updated").textContent = `Last analyzed ${new Date(results.generated_at).toLocaleString()}`;
  } catch (err) {
    document.querySelector("#updated").textContent = err.message;
  }
  render();
  addPending();
}

main();
