import { test } from "node:test";
import assert from "node:assert/strict";
import { money, bigMoney, pct, signedPct, historyRows, toTsv, stockMarkdown, escapeHtml, toCsv } from "../../site/js/format.js";

const columns = [["revenue", "Revenue"], ["roic", "ROIC"]];
const stock = {
  symbol: "AAA", name: "Aaa Inc.", price: 50, tier: "close", tier_reason: "Getting close: ...",
  big_five: { score: 4, metrics: { sales: { label: "Sales growth", pass: true,
    windows: { "10": { value: 0.12, pass: true, available: true }, "5": { value: 0.1, pass: true, available: true },
               "3": { value: null, pass: false, available: true }, "1": { value: null, pass: false, available: false } } } },
    debt: { payoff_years: 2, pass: true } },
  valuation: { computable: true, growth_rate: 0.1, growth_source: "analyst estimate", current_eps: 2, future_eps: 5.19,
    future_pe: 20, future_price: 103.75, sticker_price: 25.65, mos_price: 12.82, pct_from_mos: 0.05,
    ten_cap_price: 25, payback_price: 12.58 },
  history: { years: [2023, 2024], fy_end: { "2023": "2023-12-31", "2024": "2024-12-31" },
             revenue: { "2023": 100, "2024": 112 }, roic: { "2024": 0.2 } },
  warnings: ["Only 2 years of annual data available."],
};

test("money and pct formatting", () => {
  assert.equal(money(1234.5), "$1,234.50");
  assert.equal(money(-3), "-$3.00");
  assert.equal(money(null), "—");
  assert.equal(bigMoney(416161000000), "$416.16B");
  assert.equal(bigMoney(-2500000), "-$2.50M");
  assert.equal(pct(0.1234), "12.3%");
  assert.equal(signedPct(0.05), "+5.0%");
  assert.equal(signedPct(-0.04), "−4.0%");
});

test("historyRows builds a year-by-column grid", () => {
  const rows = historyRows(stock, columns);
  assert.deepEqual(rows[0], ["Year", "Fiscal year end", "Revenue", "ROIC"]);
  assert.deepEqual(rows[1], [2023, "2023-12-31", 100, null]);
  assert.deepEqual(rows[2], [2024, "2024-12-31", 112, 0.2]);
});

test("toTsv joins with tabs and blanks nulls", () => {
  assert.equal(toTsv([["a", null], [1, "x\ty"]]), "a\t\n1\tx y");
});

test("stockMarkdown includes key numbers and warnings", () => {
  const md = stockMarkdown(stock, columns);
  assert.match(md, /^# AAA — Aaa Inc\./);
  assert.match(md, /MOS price \| \$12\.82/);
  assert.match(md, /\| Sales growth \| 12\.0% \| 10\.0% \| n\/a \| — \| ✓ \|/);
  assert.match(md, /Only 2 years/);
  assert.match(md, /\| 2024 \| 2024-12-31 \| 112 \| 0\.2 \|/);
});

test("escapeHtml", () => {
  assert.equal(escapeHtml(`<a href="x">&</a>`), "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;");
});

test("toCsv quotes commas, quotes and newlines", () => {
  assert.equal(toCsv([["Year", "Name"], [2024, 'A, "B"'], [null, "x\ny"]]), 'Year,Name\n2024,"A, ""B"""\n,"x\ny"\n');
});
