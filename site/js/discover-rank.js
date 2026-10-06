// Pure ranking and filtering for the Discover tab (unit-tested in Node).

export const WATCH_LIMIT = 25;

const byDiscount = (a, b) => (a.pct_from_mos ?? Infinity) - (b.pct_from_mos ?? Infinity);

export function buildLists(stocks, { watchlist = new Set(), minScore = 4, sector = "", hideWatched = false } = {}) {
  const sectors = [...new Set(stocks.map((x) => x.sector).filter(Boolean))].sort();
  const pool = stocks
    .map((x) => ({ ...x, watched: watchlist.has(x.symbol) }))
    .filter((x) => (!sector || x.sector === sector) && (x.score ?? -1) >= minScore && !(hideWatched && x.watched));
  return {
    buy: pool.filter((x) => x.tier === "buy").sort(byDiscount),
    close: pool.filter((x) => x.tier === "close").sort(byDiscount),
    watch: pool.filter((x) => x.tier === "not_yet" && x.debt_pass && x.mos_price != null)
      .sort(byDiscount).slice(0, WATCH_LIMIT),
    sectors,
  };
}
