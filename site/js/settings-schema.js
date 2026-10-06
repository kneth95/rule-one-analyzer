// Settings fields, their allowed ranges (mirrors engine/config.py) and form parsing. Pure; unit-tested in Node.

// kind "pct": stored as a decimal, edited as a percent. min/max are in stored units.
export const FIELDS = [
  { key: "marr", label: "Minimum acceptable return (MARR)", kind: "pct", min: 0.01, max: 1, glossary: "marr", help: "Yearly return you require. Rule #1 uses 15%." },
  { key: "mos_fraction", label: "MOS price as % of Sticker Price", kind: "pct", min: 0.05, max: 1, glossary: "mos", help: "Rule #1 buys at 50% of the Sticker Price." },
  { key: "growth_cap", label: "Maximum growth rate", kind: "pct", min: 0.01, max: 1, glossary: "growth_rate", help: "Caps the growth rate used for the Sticker Price." },
  { key: "pe_cap", label: "Maximum Future P/E", kind: "num", min: 1, max: 500, glossary: "future_pe", help: "Caps the Future P/E." },
  { key: "big_five_threshold", label: "Big Five passing bar", kind: "pct", min: 0, max: 1, glossary: "big_five", help: "Each window must reach this. Rule #1 uses 10%." },
  { key: "big_five_min_score", label: "Big Five numbers needed for alerts", kind: "int", min: 0, max: 5, glossary: "big_five_score", help: "How many of the 5 must pass for Buy zone / Getting close." },
  { key: "windows_to_pass", label: "Windows needed per number", kind: "int", min: 1, max: 4, glossary: "windows", help: "How many of the 10/5/3/1-year windows must pass." },
  { key: "trend_tolerance", label: "Allowed recent drop", kind: "pct", min: 0, max: 1, glossary: "windows", help: "A number fails if its 1-year value is more than this below its longest window." },
  { key: "debt_payoff_max_years", label: "Maximum debt payoff years", kind: "num", min: 0, max: 100, glossary: "debt", help: "Rule #1 wants debt payable within 3 years of free cash flow." },
  { key: "getting_close_margin", label: "Getting close range", kind: "pct", min: 0, max: 1, glossary: "tier_close", help: "Alert when price is within this % above the MOS price." },
  { key: "payback_years", label: "Payback Time years", kind: "int", min: 1, max: 30, glossary: "payback_time", help: "Years of cash flow used for the Payback Time price." },
];

export const toInput = (f, v) => (f.kind === "pct" ? +(v * 100).toFixed(4) : v);

const show = (f, v) => (f.kind === "pct" ? `${+(v * 100).toFixed(4)}%` : String(v));

export function parseSettingsForm(values) {
  const settings = {};
  const errors = [];
  for (const f of FIELDS) {
    const raw = String(values[f.key] ?? "").trim();
    const n = Number(raw);
    if (raw === "" || !Number.isFinite(n)) {
      errors.push(`${f.label} needs a number.`);
      continue;
    }
    if (f.kind === "int" && !Number.isInteger(n)) {
      errors.push(`${f.label} must be a whole number.`);
      continue;
    }
    const value = f.kind === "pct" ? n / 100 : n;
    if (value < f.min - 1e-12 || value > f.max + 1e-12) {
      errors.push(`${f.label} must be between ${show(f, f.min)} and ${show(f, f.max)}.`);
      continue;
    }
    settings[f.key] = value;
  }
  return { settings, errors };
}
