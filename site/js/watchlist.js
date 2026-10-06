import { updateJsonFile } from "./github.js";

export async function addToWatchlist(symbol) {
  await updateJsonFile("watchlist.json", (w) => {
    if (w.tickers.some((t) => t.symbol === symbol)) throw new Error(`${symbol} is already on the watchlist.`);
    w.tickers.push({ symbol, added: new Date().toISOString().slice(0, 10), notes: "", growth_override: null });
    return w;
  }, `Add ${symbol} to watchlist`);
}
