import { attachTerms } from "./glossary.js";
import { checkToken, getToken, setToken } from "./github.js";
import { TIERS, escapeHtml } from "./format.js";

export async function loadResults() {
  const res = await fetch("data/results.json", { cache: "no-store" });
  if (!res.ok) throw new Error("No results yet. The first analysis run hasn't finished.");
  return res.json();
}

export function term(key, text) {
  return `<span class="term" data-term="${key}">${escapeHtml(text)}</span>`;
}

export function badge(tier) {
  const t = TIERS[tier] || TIERS.not_yet;
  return `<span class="badge ${t.cls}" data-term="tier_${tier}">${t.emoji} ${t.label}</span>`;
}

export function toast(message, kind = "info") {
  let box = document.querySelector(".toasts");
  if (!box) {
    box = document.createElement("div");
    box.className = "toasts";
    box.setAttribute("aria-live", "polite");
    document.body.append(box);
  }
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = message;
  box.append(el);
  setTimeout(() => el.remove(), kind === "error" ? 12000 : 7000);
}

function refreshOwnerState() {
  document.body.classList.toggle("owner", !!getToken());
}

function ownerDialog() {
  const dlg = document.createElement("dialog");
  dlg.className = "owner-dialog";
  dlg.innerHTML = `
    <form method="dialog">
      <h2>Owner access</h2>
      <p>Paste a <b>fine-grained GitHub token</b> for this repo to add or remove stocks, edit settings and run the analysis.
         It's saved only in this browser. Visitors without it see a read-only dashboard.</p>
      <p class="muted">Create one at GitHub → Settings → Developer settings → Fine-grained tokens. Repository access: only this repo.
         Permissions: <b>Contents: read and write</b>, <b>Actions: read and write</b>.</p>
      <label>Token <input name="token" type="password" autocomplete="off" placeholder="github_pat_..." /></label>
      <div class="row">
        <button value="save" class="primary">Save</button>
        <button value="remove" class="danger">Remove token</button>
        <button value="cancel">Cancel</button>
      </div>
    </form>`;
  document.body.append(dlg);
  dlg.addEventListener("close", async () => {
    if (dlg.returnValue === "remove") {
      setToken("");
      toast("Token removed from this browser.");
    } else if (dlg.returnValue === "save") {
      const value = dlg.querySelector("input").value.trim();
      if (!value) return;
      setToken(value);
      try {
        await checkToken();
        toast("Token saved. Owner controls are on.", "ok");
      } catch (e) {
        toast(escapeHtml(e.message), "error");
      }
    }
    dlg.querySelector("input").value = "";
    refreshOwnerState();
  });
  return dlg;
}

export function initPage() {
  refreshOwnerState();
  const dlg = ownerDialog();
  document.querySelector("#owner-btn")?.addEventListener("click", () => dlg.showModal());
  attachTerms();
}
