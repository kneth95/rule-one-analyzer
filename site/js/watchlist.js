import { updateJsonFile } from "./github.js";

// Same rule as engine/config.py: an invalid symbol in watchlist.json would stop every daily analysis.
const SYMBOL_RE = /^[A-Z][A-Z0-9-]{0,9}$/;

export function normalizeTicker(symbol) {
  const s = String(symbol ?? "").trim().toUpperCase().replace(/\./g, "-");
  return SYMBOL_RE.test(s) ? s : null;
}

export async function addToWatchlist(symbol) {
  const ticker = normalizeTicker(symbol);
  if (!ticker) throw new Error(`"${symbol}" isn't a valid ticker symbol.`);
  await updateJsonFile("watchlist.json", (w) => {
    if (w.tickers.some((t) => t.symbol === ticker)) throw new Error(`${ticker} is already on the watchlist.`);
    w.tickers.push({ symbol: ticker, added: new Date().toISOString().slice(0, 10), notes: "", growth_override: null });
    return w;
  }, `Add ${ticker} to watchlist`);
  return ticker;
}
