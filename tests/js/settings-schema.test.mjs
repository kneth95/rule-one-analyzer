import { test } from "node:test";
import assert from "node:assert/strict";
import { FIELDS, parseSettingsForm } from "../../site/js/settings-schema.js";

const defaults = { marr: "15", mos_fraction: "50", growth_cap: "15", pe_cap: "50", big_five_threshold: "10",
  big_five_min_score: "4", windows_to_pass: "3", trend_tolerance: "10", debt_payoff_max_years: "3",
  getting_close_margin: "10", payback_years: "8" };

test("valid form converts percents to decimals", () => {
  const { settings, errors } = parseSettingsForm(defaults);
  assert.deepEqual(errors, []);
  assert.equal(settings.marr, 0.15);
  assert.equal(settings.pe_cap, 50);
  assert.equal(Object.keys(settings).length, FIELDS.length);
});

test("empty field is rejected, not saved as 0", () => {
  const { errors } = parseSettingsForm({ ...defaults, pe_cap: "" });
  assert.equal(errors.length, 1);
  assert.match(errors[0], /Maximum Future P\/E/);
});

test("out-of-range and non-whole values are rejected", () => {
  assert.match(parseSettingsForm({ ...defaults, marr: "500" }).errors[0], /between 1% and 100%/);
  assert.match(parseSettingsForm({ ...defaults, windows_to_pass: "2.5" }).errors[0], /whole number/);
});
