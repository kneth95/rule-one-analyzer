import { test } from "node:test";
import assert from "node:assert/strict";
import { addToWatchlist, normalizeTicker } from "../../site/js/watchlist.js";

test("normalizeTicker uppercases and converts dots", () => {
  assert.equal(normalizeTicker(" brk.b "), "BRK-B");
  assert.equal(normalizeTicker("Apple Inc."), null);
  assert.equal(normalizeTicker("ABCDEFGHIJK"), null);
});

test("addToWatchlist rejects an invalid symbol before touching GitHub", async () => {
  await assert.rejects(addToWatchlist("APPLE INC-"), /isn't a valid ticker/);
});
