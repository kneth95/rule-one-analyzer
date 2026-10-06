import { initPage, loadResults, term, toast } from "./common.js";
import { attachTerms } from "./glossary.js";
import { escapeHtml } from "./format.js";
import { actionsUrl, getToken, readJsonFile, updateJsonFile } from "./github.js";
import { FIELDS, parseSettingsForm, toInput } from "./settings-schema.js";

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

// The owner edits the current settings.json (which may be newer than the last results); visitors see the applied settings.
async function currentSettings() {
  if (getToken()) {
    try {
      return { ...(await loadResults().then((r) => r.settings).catch(() => ({}))), ...(await readJsonFile("settings.json")).data };
    } catch (err) {
      toast(escapeHtml(err.message), "error");
    }
  }
  return (await loadResults()).settings;
}

async function main() {
  initPage();
  const form = document.querySelector("#settings-form");
  try {
    render(form, await currentSettings());
  } catch (err) {
    form.innerHTML = `<p class="banner">${escapeHtml(err.message)}</p>`;
    return;
  }
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const { settings, errors } = parseSettingsForm(Object.fromEntries(new FormData(form)));
    if (errors.length) return toast(errors.map(escapeHtml).join("<br>"), "error");
    const btn = e.submitter;
    btn.disabled = true;
    try {
      await updateJsonFile("settings.json", () => settings, "Update analyzer settings");
      toast(`Settings saved. The analysis re-runs in about 1–2 minutes. <a href="${actionsUrl()}" target="_blank" rel="noopener">Watch the run</a>`, "ok");
    } catch (err) {
      toast(escapeHtml(err.message), "error");
    } finally {
      btn.disabled = false;
    }
  });
}

main();
