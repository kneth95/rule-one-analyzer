import { test } from "node:test";
import assert from "node:assert/strict";
import { buildLists, WATCH_LIMIT } from "../../site/js/discover-rank.js";

const s = (symbol, tier, pct, extra = {}) => ({ symbol, name: symbol, sector: "Tech", tier, pct_from_mos: pct, score: 5,
  debt_pass: true, mos_price: 10, ...extra });

test("splits into buy, close and watch lists sorted by discount", () => {
  const stocks = [s("B2", "buy", -0.1), s("B1", "buy", -0.4), s("C1", "close", 0.05), s("W2", "not_yet", 0.8),
    s("W1", "not_yet", 0.2)];
  const { buy, close, watch } = buildLists(stocks, {});
  assert.deepEqual(buy.map((x) => x.symbol), ["B1", "B2"]);
  assert.deepEqual(close.map((x) => x.symbol), ["C1"]);
  assert.deepEqual(watch.map((x) => x.symbol), ["W1", "W2"]);
});

test("watch list needs score, debt pass and a MOS price, and stops at the limit", () => {
  const stocks = [s("LOW", "not_yet", 0.1, { score: 3 }), s("DEBT", "not_yet", 0.1, { debt_pass: false }),
    s("NOMOS", "not_yet", null, { mos_price: null }),
    ...Array.from({ length: 30 }, (_, i) => s(`W${i}`, "not_yet", i / 10))];
  const { watch } = buildLists(stocks, { minScore: 4 });
  assert.equal(watch.length, WATCH_LIMIT);
  assert.equal(watch[0].symbol, "W0");
  assert.ok(!watch.some((x) => ["LOW", "DEBT", "NOMOS"].includes(x.symbol)));
});

test("filters by sector, min score and watched", () => {
  const stocks = [s("A", "buy", -0.2, { sector: "Energy" }), s("B", "buy", -0.3, { score: 4 }), s("C", "buy", -0.1)];
  const watchlist = new Set(["C"]);
  assert.deepEqual(buildLists(stocks, { sector: "Energy" }).buy.map((x) => x.symbol), ["A"]);
  assert.deepEqual(buildLists(stocks, { minScore: 5 }).buy.map((x) => x.symbol), ["A", "C"]);
  const lists = buildLists(stocks, { watchlist, hideWatched: true });
  assert.deepEqual(lists.buy.map((x) => x.symbol), ["B", "A"]);
  assert.equal(buildLists(stocks, { watchlist }).buy.find((x) => x.symbol === "C").watched, true);
  assert.deepEqual(lists.sectors, ["Energy", "Tech"]);
});
