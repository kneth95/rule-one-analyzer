// Owner-only writes through the GitHub REST API using a fine-grained token kept in this browser.

const TOKEN_KEY = "r1.token";
const REPO_KEY = "r1.repo"; // optional override "owner/repo" for local testing
const BRANCH = "main";

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
}

export function setToken(token) {
  try { token ? localStorage.setItem(TOKEN_KEY, token.trim()) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
}

export function repoInfo(loc = window.location) {
  try {
    const override = localStorage.getItem(REPO_KEY);
    if (override && override.includes("/")) {
      const [owner, repo] = override.split("/");
      return { owner, repo };
    }
  } catch { /* storage blocked */ }
  const m = loc.hostname.match(/^([^.]+)\.github\.io$/i);
  if (!m) return null;
  const first = loc.pathname.split("/").filter(Boolean)[0];
  const repo = first && !first.endsWith(".html") ? first : `${m[1]}.github.io`;
  return { owner: m[1], repo };
}

export function actionsUrl() {
  const info = repoInfo();
  return info ? `https://github.com/${info.owner}/${info.repo}/actions` : "#";
}

async function api(path, options = {}) {
  const info = repoInfo();
  if (!info) throw new Error("Can't tell which GitHub repo this is. Open the dashboard from its github.io address.");
  const token = getToken();
  if (!token) throw new Error("Add your GitHub token first (🔑 Owner button at the top).");
  const res = await fetch(`https://api.github.com/repos/${info.owner}/${info.repo}${path}`, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const hint = res.status === 401 ? " Your token may be wrong or expired." :
      res.status === 403 || res.status === 404 ? " Check the token has Contents and Actions read/write access to this repo." : "";
    throw new Error(`GitHub said ${res.status}: ${body.message || res.statusText}.${hint}`);
  }
  return res.status === 204 ? null : res.json();
}

function encode(text) {
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function decode(b64) {
  const bin = atob(b64.replace(/\s/g, ""));
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}

export async function readJsonFile(path) {
  const file = await api(`/contents/${path}?ref=${BRANCH}`, { cache: "no-store" });
  return { sha: file.sha, data: JSON.parse(decode(file.content)) };
}

export async function updateJsonFile(path, mutate, message) {
  const { sha, data } = await readJsonFile(path);
  const next = mutate(structuredClone(data));
  await api(`/contents/${path}`, {
    method: "PUT",
    body: JSON.stringify({ message, content: encode(JSON.stringify(next, null, 2) + "\n"), sha, branch: BRANCH }),
  });
  return next;
}

export async function runAnalysisNow() {
  await api("/actions/workflows/analyze.yml/dispatches", { method: "POST", body: JSON.stringify({ ref: BRANCH }) });
}

export async function checkToken() {
  return api("");
}
