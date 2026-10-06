import { test } from "node:test";
import assert from "node:assert/strict";

const calls = [];
globalThis.window = { location: { hostname: "kneth95.github.io", pathname: "/rule-one-analyzer/discover.html" } };
const store = { "r1.token": "github_pat_test" };
globalThis.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; }, removeItem: (k) => { delete store[k]; } };
globalThis.fetch = async (url, opts) => { calls.push({ url, opts }); return { ok: true, status: 204, json: async () => ({}) }; };

const { runAnalysisNow, runDiscoverNow } = await import("../../site/js/github.js");

test("runDiscoverNow dispatches the discover workflow on main", async () => {
  calls.length = 0;
  await runDiscoverNow();
  assert.equal(calls[0].url, "https://api.github.com/repos/kneth95/rule-one-analyzer/actions/workflows/discover.yml/dispatches");
  assert.equal(calls[0].opts.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].opts.body), { ref: "main" });
  assert.equal(calls[0].opts.headers.Authorization, "Bearer github_pat_test");
});

test("runAnalysisNow still dispatches the analyze workflow", async () => {
  calls.length = 0;
  await runAnalysisNow();
  assert.match(calls[0].url, /\/actions\/workflows\/analyze\.yml\/dispatches$/);
});
