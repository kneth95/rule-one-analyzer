// Pure formatting helpers shared by all pages (also unit-tested in Node).

const isNum = (v) => typeof v === "number" && Number.isFinite(v);

export function money(v, digits = 2) {
  if (!isNum(v)) return "—";
  const s = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return (v < 0 ? "-$" : "$") + s;
}

export function bigMoney(v) {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  const [div, suffix] = a >= 1e12 ? [1e12, "T"] : a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
  return (v < 0 ? "-$" : "$") + (a / div).toFixed(2) + suffix;
}

export function pct(v, digits = 1) {
  return isNum(v) ? (v * 100).toFixed(digits) + "%" : "—";
}

export function signedPct(v, digits = 1) {
  if (!isNum(v)) return "—";
  return (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(digits) + "%";
}

export function num(v, digits = 2) {
  return isNum(v) ? v.toLocaleString("en-US", { maximumFractionDigits: digits }) : "—";
}

export const TIERS = {
  buy: { label: "Buy zone", emoji: "🟢", cls: "buy" },
  close: { label: "Getting close", emoji: "🟡", cls: "close" },
  not_yet: { label: "Not yet", emoji: "⚪", cls: "not-yet" },
};

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function historyRows(stock, columns) {
  const h = stock.history;
  const rows = [["Year", "Fiscal year end", ...columns.map(([, label]) => label)]];
  for (const y of h.years) {
    const k = String(y);
    rows.push([y, h.fy_end[k] ?? "", ...columns.map(([field]) => h[field]?.[k] ?? null)]);
  }
  return rows;
}

export function toTsv(rows) {
  return rows.map((r) => r.map((c) => (c == null ? "" : String(c).replace(/[\t\r\n]+/g, " "))).join("\t")).join("\n");
}

const windowCell = (w) => (!w || !w.available ? "—" : w.value == null ? "n/a" : pct(w.value));

export function stockMarkdown(stock, columns) {
  const v = stock.valuation || {};
  const bf = stock.big_five || { metrics: {}, debt: {} };
  const lines = [
    `# ${stock.symbol} — ${stock.name}`,
    "",
    `Status: ${TIERS[stock.tier].label}. ${stock.tier_reason}`,
    "",
    "| Number | Value |",
    "|---|---|",
    `| Price | ${money(stock.price)} |`,
    `| MOS price | ${money(v.mos_price)} |`,
    `| Sticker Price | ${money(v.sticker_price)} |`,
    `| Price vs MOS | ${signedPct(v.pct_from_mos)} |`,
    `| Growth rate used | ${pct(v.growth_rate)} (${v.growth_source ?? "n/a"}) |`,
    `| Current EPS | ${money(v.current_eps)} |`,
    `| Future EPS (10 yr) | ${money(v.future_eps)} |`,
    `| Future P/E | ${num(v.future_pe, 1)} |`,
    `| Future price | ${money(v.future_price)} |`,
    `| Ten Cap price | ${money(v.ten_cap_price)} |`,
    `| Payback Time price | ${money(v.payback_price)} |`,
    `| Big Five score | ${bf.score ?? "n/a"} of 5 |`,
    `| Debt payoff | ${bf.debt?.payoff_years == null ? "n/a" : num(bf.debt.payoff_years, 1) + " years"} |`,
    "",
    "## Big Five",
    "",
    "| Metric | 10 yr | 5 yr | 3 yr | 1 yr | Pass |",
    "|---|---|---|---|---|---|",
    ...Object.values(bf.metrics).map((m) =>
      `| ${m.label} | ${["10", "5", "3", "1"].map((k) => windowCell(m.windows[k])).join(" | ")} | ${m.pass ? "✓" : "✗"} |`),
  ];
  if (stock.warnings?.length) lines.push("", "## Warnings", "", ...stock.warnings.map((w) => `- ${w}`));
  if (stock.history) {
    const rows = historyRows(stock, columns);
    lines.push("", "## Yearly data", "", `| ${rows[0].join(" | ")} |`, `|${rows[0].map(() => "---").join("|")}|`,
      ...rows.slice(1).map((r) => `| ${r.map((c) => (c == null ? "" : c)).join(" | ")} |`));
  }
  return lines.join("\n");
}
