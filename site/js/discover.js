import { initPage, loadResults, term, toast } from "./common.js";
import { attachTerms } from "./glossary.js";
import { escapeHtml, money, num, signedPct } from "./format.js";
import { actionsUrl, runDiscoverNow } from "./github.js";
import { addToWatchlist } from "./watchlist.js";
import { buildLists, WATCH_LIMIT } from "./discover-rank.js";

const LISTS = [
  ["buy", "🟢 Buy zone", "tier_buy", "No S&P 500 company is in the Buy zone this week. That's normal: real Rule #1 bargains are rare."],
  ["close", "🟡 Getting close", "tier_close", "Nothing is in the early-warning range this week."],
  ["watch", `⭐ Wonderful companies to watch (top ${WATCH_LIMIT})`, "wonderful_watch", "No company passes these filters right now."],
];

let scan;
let watchlist = new Set();

function row(s) {
  const action = s.watched ? `<span class="muted">✓ Watching</span>` : `<button data-watch="${escapeHtml(s.symbol)}">+ Watch</button>`;
  return `<tr class="clickable" data-symbol="${escapeHtml(s.symbol)}">
    <td><b>${escapeHtml(s.symbol)}</b>${s.watched ? ` <span title="On your watchlist">⭐</span>` : ""}<br>
      <span class="muted">${escapeHtml(s.name)}</span>${s.stale ? ` ${term("stale", "stale")}` : ""}</td>
    <td class="left">${escapeHtml(s.sector)}</td>
    <td>${money(s.price)}</td>
    <td>${money(s.mos_price)}</td>
    <td>${signedPct(s.pct_from_mos)}</td>
    <td>${s.score ?? "—"}/5</td>
    <td class="${s.debt_pass ? "pass" : "fail"}">${s.debt_years == null ? "n/a" : num(s.debt_years, 1)}</td>
    <td class="owner-only">${action}</td>
  </tr>`;
}

function table(items) {
  return `<div class="table-wrap"><table>
    <thead><tr><th>Stock</th><th class="left">${term("sector", "Sector")}</th><th>Price</th>
      <th>${term("mos_price", "MOS price")}</th><th>${term("pct_from_mos", "vs MOS")}</th>
      <th>${term("big_five_score", "Big Five")}</th><th>${term("debt", "Debt yrs")}</th><th class="owner-only"></th></tr></thead>
    <tbody>${items.map(row).join("")}</tbody></table></div>`;
}

function filters() {
  const f = new FormData(document.querySelector("#filters"));
  return { sector: f.get("sector") || "", minScore: Number(f.get("minScore")), hideWatched: f.get("hideWatched") === "on", watchlist };
}

function render() {
  const lists = buildLists(scan.stocks, filters());
  const box = document.querySelector("#lists");
  box.innerHTML = LISTS.map(([key, title, glossary, empty]) => `<section class="card">
      <h2><span class="term" data-term="${glossary}">${escapeHtml(title)}</span> <span class="muted">(${lists[key].length})</span></h2>
      ${lists[key].length ? table(lists[key]) : `<p class="muted">${escapeHtml(empty)}</p>`}
    </section>`).join("");
  attachTerms(box);
}

function setupFilters() {
  const form = document.querySelector("#filters");
  const sectorSelect = form.querySelector("[name=sector]");
  for (const sector of buildLists(scan.stocks).sectors) sectorSelect.add(new Option(sector, sector));
  const min = Number(scan.settings.big_five_min_score);
  const scoreSelect = form.querySelector("[name=minScore]");
  for (const v of [...new Set([min, 5])]) scoreSelect.add(new Option(`${v} of 5`, String(v)));
  form.addEventListener("change", render);
}

function showMeta() {
  const c = scan.counts;
  document.querySelector("#summary").textContent =
    `Last scanned ${new Date(scan.generated_at).toLocaleString()} · ${c.total} companies · ${c.analyzed} analyzed, ${c.failed} couldn't be analyzed`;
  document.querySelector("#scan-warnings").innerHTML = scan.warnings.map((w) => `<p class="banner">${escapeHtml(w)}</p>`).join("");
  if (scan.failed.length) {
    document.querySelector("#failed-box").hidden = false;
    document.querySelector("#failed-summary").textContent = `${scan.failed.length} companies couldn't be analyzed`;
    document.querySelector("#failed-list").innerHTML = scan.failed
      .map((f) => `<li><b>${escapeHtml(f.symbol)}</b> ${escapeHtml(f.name)}: ${escapeHtml(f.reason)}</li>`).join("");
  }
}

async function onClick(e) {
  const btn = e.target.closest("[data-watch]");
  if (btn) {
    btn.disabled = true;
    try {
      await addToWatchlist(btn.dataset.watch);
      watchlist.add(btn.dataset.watch);
      btn.outerHTML = `<span class="muted">✓ Watching</span>`;
      toast(`${escapeHtml(btn.dataset.watch)} added to your watchlist. Results in about 1–2 minutes. <a href="${actionsUrl()}" target="_blank" rel="noopener">Watch the run</a>`, "ok");
    } catch (err) {
      btn.disabled = false;
      toast(escapeHtml(err.message), "error");
    }
    return;
  }
  if (e.target.closest(".info")) return;
  const tr = e.target.closest("tr[data-symbol]");
  if (tr) location.href = `stock.html?t=${encodeURIComponent(tr.dataset.symbol)}`;
}

async function onScanNow(e) {
  e.target.disabled = true;
  try {
    await runDiscoverNow();
    toast(`Scan started. Reload this page in about 15 minutes. <a href="${actionsUrl()}" target="_blank" rel="noopener">Watch the run</a>`, "ok");
  } catch (err) {
    toast(escapeHtml(err.message), "error");
  } finally {
    e.target.disabled = false;
  }
}

async function main() {
  initPage();
  document.querySelector("#scan-now").addEventListener("click", onScanNow);
  const res = await fetch("data/discover/discover.json", { cache: "no-store" });
  if (!res.ok) {
    document.querySelector("#summary").textContent =
      "Discover hasn't run yet. Owner: click Scan now (or on GitHub: Actions → Discover S&P 500 → Run workflow). It takes about 15 minutes.";
    document.querySelector("#filters").hidden = true;
    return;
  }
  scan = await res.json();
  try {
    watchlist = new Set((await loadResults()).stocks.map((s) => s.symbol));
  } catch { /* no watchlist results yet */ }
  showMeta();
  setupFilters();
  render();
  document.querySelector("#lists").addEventListener("click", onClick);
}

main();
