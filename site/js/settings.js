import { initPage, loadResults, term, toast } from "./common.js";
import { attachTerms } from "./glossary.js";
import { escapeHtml } from "./format.js";
import { actionsUrl, getToken, updateJsonFile } from "./github.js";

// kind "pct": stored as a decimal, edited as a percent.
const FIELDS = [
  { key: "marr", label: "Minimum acceptable return (MARR)", kind: "pct", glossary: "marr", help: "Yearly return you require. Rule #1 uses 15%." },
  { key: "mos_fraction", label: "MOS price as % of Sticker Price", kind: "pct", glossary: "mos", help: "Rule #1 buys at 50% of the Sticker Price." },
  { key: "growth_cap", label: "Maximum growth rate", kind: "pct", glossary: "growth_rate", help: "Caps the growth rate used for the Sticker Price." },
  { key: "pe_cap", label: "Maximum Future P/E", kind: "num", glossary: "future_pe", help: "Caps the Future P/E." },
  { key: "big_five_threshold", label: "Big Five passing bar", kind: "pct", glossary: "big_five", help: "Each window must reach this. Rule #1 uses 10%." },
  { key: "big_five_min_score", label: "Big Five numbers needed for alerts", kind: "int", glossary: "big_five_score", help: "How many of the 5 must pass for Buy zone / Getting close." },
  { key: "windows_to_pass", label: "Windows needed per number", kind: "int", glossary: "windows", help: "How many of the 10/5/3/1-year windows must pass." },
  { key: "trend_tolerance", label: "Allowed recent drop", kind: "pct", glossary: "windows", help: "A number fails if its 1-year value is more than this below its longest window." },
  { key: "debt_payoff_max_years", label: "Maximum debt payoff years", kind: "num", glossary: "debt", help: "Rule #1 wants debt payable within 3 years of free cash flow." },
  { key: "getting_close_margin", label: "Getting close range", kind: "pct", glossary: "tier_close", help: "Alert when price is within this % above the MOS price." },
  { key: "payback_years", label: "Payback Time years", kind: "int", glossary: "payback_time", help: "Years of cash flow used for the Payback Time price." },
];

const toInput = (f, v) => (f.kind === "pct" ? +(v * 100).toFixed(4) : v);
const fromInput = (f, raw) => (f.kind === "pct" ? Number(raw) / 100 : Number(raw));

function render(form, settings) {
  const owner = !!getToken();
  form.innerHTML = FIELDS.map((f) => `
    <label>
      <span>${term(f.glossary, f.label)}</span>
      <span class="row"><input name="${f.key}" type="number" step="${f.kind === "int" ? 1 : "any"}" value="${toInput(f, settings[f.key])}" ${owner ? "" : "disabled"} />
        ${f.kind === "pct" ? "%" : ""}</span>
      <span class="muted">${escapeHtml(f.help)}</span>
    </label>`).join("<hr>") + `<div class="row owner-only" style="margin-top:16px"><button class="primary">Save settings</button></div>`;
  attachTerms(form);
}

async function main() {
  initPage();
  const form = document.querySelector("#settings-form");
  let settings;
  try {
    settings = (await loadResults()).settings;
  } catch (err) {
    form.innerHTML = `<p class="banner">${escapeHtml(err.message)}</p>`;
    return;
  }
  render(form, settings);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = new FormData(form);
    const next = {};
    for (const f of FIELDS) {
      const value = fromInput(f, data.get(f.key));
      if (!Number.isFinite(value)) return toast(`${escapeHtml(f.label)} needs a number.`, "error");
      next[f.key] = f.kind === "int" ? Math.round(value) : value;
    }
    const btn = e.submitter;
    btn.disabled = true;
    try {
      await updateJsonFile("settings.json", () => next, "Update analyzer settings");
      toast(`Settings saved. The analysis re-runs in about 1–2 minutes. <a href="${actionsUrl()}" target="_blank" rel="noopener">Watch the run</a>`, "ok");
    } catch (err) {
      toast(escapeHtml(err.message), "error");
    } finally {
      btn.disabled = false;
    }
  });
}

main();
