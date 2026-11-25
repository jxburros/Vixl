"use strict";
// Vixl Lab page. Keys are sent with a request and never stored in the browser; form choices are remembered in
// localStorage per browser (provider, model, arms, prices), wrapped in try/catch so a blocked store changes nothing.

const TOKEN = document.querySelector('meta[name="lab-token"]').content;
const $ = (selector, root = document) => root.querySelector(selector);
const state = { config: null, run: null, runId: null, events: {}, open: new Set(), poll: null, revealed: new Set() };

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Lab-Token": TOKEN, ...(options.headers || {}) },
  });
  let data = null;
  try { data = await response.json(); } catch (_) { data = {}; }
  if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
  return data;
}

const store = {
  get(key, fallback) { try { const v = localStorage.getItem("vixl-lab:" + key); return v === null ? fallback : JSON.parse(v); } catch (_) { return fallback; } },
  set(key, value) { try { localStorage.setItem("vixl-lab:" + key, JSON.stringify(value)); } catch (_) { /* private mode */ } },
};

// --- views ------------------------------------------------------------------------------------------------------

function show(view) {
  for (const section of document.querySelectorAll(".view")) section.hidden = section.id !== `view-${view}`;
  for (const tab of document.querySelectorAll(".tab")) tab.classList.toggle("active", tab.dataset.view === view);
  if (view !== "run") stopPolling();
  if (view === "runs") loadRuns();
  if (view === "stats") loadStats();
}

for (const tab of document.querySelectorAll(".tab")) tab.addEventListener("click", () => {
  if (tab.dataset.view === "new") location.hash = "";
  show(tab.dataset.view);
});

// --- new run form -----------------------------------------------------------------------------------------------

const form = $("#run-form");

function providerOptions(select, chosen) {
  select.replaceChildren(...Object.entries(state.config.providers).map(([name, p]) =>
    h("option", { value: name, selected: name === chosen }, p.label)));
}

function applyProvider(remember = true) {
  const name = $("#provider").value;
  const preset = state.config.providers[name];
  const urls = store.get("base_urls", {});
  $("#base_url").value = urls[name] ?? preset.base_url;
  $("#model").value = store.get("models", {})[name] || preset.suggestions[0] || "";
  $("#model-list").replaceChildren(...preset.suggestions.map(m => h("option", { value: m })));
  const envNote = preset.env.length ? `or set ${preset.env.join(" / ")}` : "";
  $("#key-hint").textContent = preset.key_known ? "(a key is already available)" :
    preset.key_required ? envNote : "(not needed for local servers)";
  $("#api_key").placeholder = preset.key_known ? "Leave blank to use the key already given" : "Kept in memory only, never saved";
  if (remember) store.set("provider", name);
  updatePrice();
}

function updatePrice() {
  const prices = store.get("prices", {})[`${$("#provider").value}:${$("#model").value}`] || {};
  form.price_in.value = prices.in ?? "";
  form.price_out.value = prices.out ?? "";
}

async function loadConfig() {
  state.config = await api("/api/config");
  providerOptions($("#provider"), store.get("provider", "anthropic"));
  providerOptions($("#judge-provider"), "anthropic");
  const chosen = store.get("arms", Object.keys(state.config.arms));
  $("#arm-list").replaceChildren(...Object.entries(state.config.arms).map(([name, arm]) =>
    h("label", { class: "arm-option" },
      h("input", { type: "checkbox", name: "arms", value: name, checked: chosen.includes(name) }),
      h("span", {}, h("strong", {}, h("span", { class: `dot ${name}`, style: "display:inline-block;margin-right:6px" }), arm.label),
        h("small", {}, arm.description)))));
  applyProvider(false);
  const caps = state.config.capabilities;
  const notes = [
    caps.render_html ? "HTML and SVG rendering: on." : "HTML and SVG rendering is off: pip install playwright && playwright install chromium.",
    caps.network_isolation ? "The code arm's Python has no network." : "The code arm's Python can reach the network on this system.",
    `Python libraries for the code arm: ${caps.python_libraries.join(", ") || "standard library only"}.`,
    `Results are saved in ${state.config.results}.`,
  ];
  $("#capabilities").textContent = notes.join(" ");
  $("#prompt").value = store.get("draft", "");
}

$("#provider").addEventListener("change", () => applyProvider());
$("#model").addEventListener("change", updatePrice);
$("#prompt").addEventListener("input", () => store.set("draft", $("#prompt").value));
$("#base_url").addEventListener("change", () => {
  const urls = store.get("base_urls", {}); urls[$("#provider").value] = $("#base_url").value; store.set("base_urls", urls);
});

$("#load-models").addEventListener("click", async () => {
  const button = $("#load-models");
  button.disabled = true; setMessage("#form-message", "Loading models…");
  try {
    const data = await api("/api/models", { method: "POST", body: JSON.stringify({
      provider: $("#provider").value, base_url: $("#base_url").value, api_key: $("#api_key").value }) });
    $("#model-list").replaceChildren(...data.models.map(m => h("option", { value: m })));
    setMessage("#form-message", `${data.models.length} models. Type to filter in the Model field.`);
    state.config.providers[$("#provider").value].key_known = true;
  } catch (error) { setMessage("#form-message", error.message, true); }
  button.disabled = false;
});

function setMessage(selector, text, error = false) {
  const node = $(selector); node.textContent = text; node.classList.toggle("error", error);
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  let extra = {};
  if ((data.extra || "").trim()) {
    try { extra = JSON.parse(data.extra); } catch (_) { return setMessage("#form-message", "Extra request fields must be JSON.", true); }
  }
  const arms = [...form.querySelectorAll('input[name="arms"]:checked')].map(i => i.value);
  const body = {
    provider: data.provider, base_url: data.base_url, api_key: data.api_key, model: data.model.trim(), prompt: data.prompt,
    arms, repeats: +data.repeats, max_turns: +data.max_turns, session_minutes: +data.session_minutes,
    parallel: +data.parallel, max_tokens: +data.max_tokens, effort: data.effort, extra,
    vision: form.vision.checked, skill: form.skill.checked,
    price_in: data.price_in === "" ? null : +data.price_in, price_out: data.price_out === "" ? null : +data.price_out,
  };
  store.set("arms", arms);
  const models = store.get("models", {}); models[data.provider] = body.model; store.set("models", models);
  const prices = store.get("prices", {});
  prices[`${data.provider}:${body.model}`] = { in: body.price_in, out: body.price_out }; store.set("prices", prices);
  $("#start").disabled = true; setMessage("#form-message", "Starting…");
  try {
    const { run_id } = await api("/api/runs", { method: "POST", body: JSON.stringify(body) });
    $("#api_key").value = "";
    state.config.providers[data.provider].key_known = true;
    applyProvider(false);
    setMessage("#form-message", "");
    openRun(run_id);
  } catch (error) { setMessage("#form-message", error.message, true); }
  $("#start").disabled = false;
});

// --- run view ---------------------------------------------------------------------------------------------------
// A run has rounds: round 1 is the brief, each later round a follow-up sent to every session. The grid shows one
// round at a time; votes, judging and the log follow the selected round.

function openRun(runId) {
  if (state.runId !== runId) {
    state.events = {}; state.open = new Set(); state.revealed = new Set(); state.round = null; state.followLatest = true;
  }
  state.runId = runId;
  location.hash = `run=${runId}`;
  show("run");
  $("#judge-form").hidden = true;
  setMessage("#run-message", "");
  refreshRun();
  startPolling(1500);
}

function startPolling(ms) { stopPolling(); state.poll = setInterval(refreshRun, ms); }
function stopPolling() { if (state.poll) clearInterval(state.poll); state.poll = null; }

async function refreshRun() {
  let run;
  try { run = await api(`/api/runs/${state.runId}`); } catch (error) { setMessage("#run-message", error.message, true); stopPolling(); return; }
  state.run = run;
  const latest = run.rounds.length;
  if (state.followLatest || !state.round || state.round > latest) state.round = latest;
  await Promise.all(run.sessions.filter(s => state.open.has(s.id) || s.status === "running").map(loadEvents));
  renderRun();
  if (!run.judging && $("#run-message").textContent.startsWith("Judging")) setMessage("#run-message", "Judging finished.");
  if (!run.busy && !run.judging) stopPolling();
}

async function loadEvents(session) {
  const known = state.events[session.id] || [];
  try {
    const data = await api(`/api/sessions/${session.id}/events?since=${known.length}`);
    state.events[session.id] = known.concat(data.events);
  } catch (_) { /* shown on the next refresh */ }
}

function hash(text) { let n = 2166136261; for (const c of text) n = Math.imul(n ^ c.charCodeAt(0), 16777619); return n >>> 0; }
function blindOrder(sessions, seed) {
  return sessions.map(s => [hash(seed + s.id), s]).sort((a, b) => a[0] - b[0]).map(pair => pair[1]);
}
function fmtSeconds(s) { return s >= 90 ? `${(s / 60).toFixed(1)} min` : `${Math.round(s)} s`; }
function fmtTokens(n) { return n >= 1e6 ? `${(n / 1e6).toFixed(2)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : `${n}`; }
const LIVE = ["queued", "running"];
const armLabel = name => (state.config.arms[name] || {}).label || name;
const generationOf = (session, round) => (session.generations || []).find(g => g.round === round);
const fileUrl = (session, round, path) =>
  `/files/${state.run.id}/${session.id}/${round}/files/${path.split("/").map(encodeURIComponent).join("/")}`;

function renderRun() {
  const run = state.run, round = state.round;
  const provider = (state.config.providers[run.provider] || {}).label || run.provider;
  $("#run-meta").textContent = `${provider} · ${run.model} · ${run.spec.arms.map(armLabel).join(" vs ")} · ` +
    `${run.spec.repeats} repeat${run.spec.repeats > 1 ? "s" : ""} · ${run.rounds.length} round${run.rounds.length > 1 ? "s" : ""} · ` +
    `${run.busy ? "running" : run.status}${run.judging ? " · judging…" : ""}`;
  $("#run-prompt").textContent = run.prompt;
  $("#cancel-run").disabled = !run.busy;
  $("#delete-run").disabled = run.busy;
  $("#export-run").disabled = run.busy;

  $("#round-tabs").replaceChildren(...run.rounds.map(r => h("button", {
    class: `tab${r.round === round ? " active" : ""}`, role: "tab", title: r.prompt,
    onclick: () => { state.round = r.round; state.followLatest = r.round === run.rounds.length; renderRun(); },
  }, r.round === 1 ? "Round 1 · brief" : `Round ${r.round}`)));
  const current = run.rounds.find(r => r.round === round);
  $("#round-prompt").replaceChildren(
    h("span", { class: "eyebrow" }, round === 1 ? "The brief" : `Follow-up ${round - 1}, sent to every session`),
    h("span", { class: "prompt" }, current ? current.prompt : ""));

  const followup = $("#followup-form");
  followup.hidden = false;
  for (const control of followup.elements) control.disabled = run.busy;
  $("#followup-hint").textContent = run.busy ? "Available when every session has finished this round." :
    `Becomes round ${run.rounds.length + 1}. Each session continues its own conversation and workspace.`;

  const blind = $("#blind").checked;
  const repeats = [...new Set(run.sessions.map(s => s.repeat))].sort((a, b) => a - b);
  const sections = repeats.map(repeat => {
    const members = run.sessions.filter(s => s.repeat === repeat && generationOf(s, round));
    const key = `${round}:${repeat}`;
    const winner = run.votes[key];
    const hide = blind && winner === undefined && !state.revealed.has(key);
    const ordered = hide ? blindOrder(members, run.id + key) : members;
    const finished = members.every(s => !LIVE.includes(generationOf(s, round).status));
    const verdict = winner === undefined ? "" : winner === "tie" ? "Voted: tie" : winner === "none" ? "Voted: none is good" :
      `Voted: ${armLabel((members.find(s => s.id === winner) || {}).arm)}`;
    const canVote = finished && members.length > 1;
    return h("section", { class: "repeat" },
      h("div", { class: "repeat-head" },
        h("h2", {}, `Repeat ${repeat + 1}`, verdict ? h("span", { class: "hint", style: "margin-left:10px" }, verdict) : null),
        canVote ? h("div", { class: "row" },
          h("button", { class: "ghost", onclick: () => vote(repeat, "tie") }, "Tie"),
          h("button", { class: "ghost", onclick: () => vote(repeat, "none") }, "None is good"),
          hide ? h("button", { class: "ghost", onclick: () => { state.revealed.add(key); renderRun(); } }, "Reveal") : null) : null),
      h("div", { class: "cards" }, ordered.map((session, index) => card(session, index, hide, canVote, winner))));
  });
  $("#repeats").replaceChildren(...sections);
}

function card(session, index, hide, canVote, winner) {
  const run = state.run, round = state.round;
  const g = generationOf(session, round);
  const label = hide ? `Output ${String.fromCharCode(65 + index)}` : armLabel(session.arm);
  const m = g.metrics || {};
  const done = !LIVE.includes(g.status);
  const previewUrl = `/files/${run.id}/${session.id}/${round}/preview.png?${g.finished || 0}`;
  // Without a browser on the server, SVG and HTML have no PNG preview: show the file itself (HTML sandboxed).
  const direct = !g.preview && done ? (g.files || []).find(f => f.kind === "svg" || f.kind === "html") : null;
  const directUrl = direct ? fileUrl(session, round, direct.path) : "";
  const preview = g.preview
    ? h("div", { class: "preview", onclick: () => zoom(previewUrl) }, h("img", { src: previewUrl, alt: `Preview of ${label}`, loading: "lazy" }))
    : direct && direct.kind === "svg" ? h("div", { class: "preview", onclick: () => zoom(directUrl) }, h("img", { src: directUrl, alt: `Preview of ${label}` }))
    : direct ? h("div", { class: "preview" }, h("iframe", { src: directUrl, sandbox: "allow-scripts", title: `Preview of ${label}` }))
    : h("div", { class: "preview" }, h("div", { class: "empty" },
        done ? (g.preview_note || "Nothing to preview") : g.status === "queued" ? "Waiting to start…" : "Working…"));
  const tokens = (m.input || 0) + (m.output || 0) + (m.cache_read || 0) + (m.cache_write || 0);
  const metrics = done && !hide ? h("div", { class: "metrics" },
    h("span", {}, h("b", {}, fmtSeconds(m.seconds || 0))),
    h("span", {}, h("b", {}, m.turns || 0), " turns"),
    h("span", {}, h("b", {}, m.tool_calls || 0), " tool calls", m.tool_errors ? ` (${m.tool_errors} errors)` : ""),
    h("span", {}, h("b", {}, fmtTokens(tokens)), " tokens", m.output ? ` (${fmtTokens(m.output)} out)` : ""),
    m.cost !== null && m.cost !== undefined ? h("span", {}, h("b", {}, `$${m.cost.toFixed(3)}`)) : null,
    m.images ? h("span", {}, h("b", {}, m.images), " images seen") : null) : null;
  const changes = Object.fromEntries((g.changed || []).map(c => [c.path, c.change]));
  const files = !hide && (g.files || []).length ? h("div", { class: "files" },
    g.files.slice(0, 24).map(f => h("a", {
      href: fileUrl(session, round, f.path) + (["pptx", "docx", "xlsx", "vixl", "other"].includes(f.kind) ? "?download=1" : ""),
      target: "_blank", rel: "noopener", class: changes[f.path] ? "changed" : "",
      title: changes[f.path] ? `${changes[f.path]} in this round` : "unchanged in this round" }, f.path))) : null;
  const judged = (g.judgments || []).filter(j => j.mean);
  const judgeErrors = (g.judgments || []).filter(j => j.error);
  const scores = judged.length ? h("div", { class: "scores" }, judged.map(j => h("div", {},
    h("b", {}, j.mean.toFixed(2)), ` / 5 · ${j.judge} · `,
    Object.entries(j.scores).map(([k, v]) => `${k} ${v}`).join(", "), j.notes ? h("div", {}, j.notes) : null))) : null;
  const events = (state.events[session.id] || []).filter(e => (e.round || 1) === round);
  const log = !hide ? h("details", { class: "log", open: state.open.has(session.id), ontoggle: async e => {
      if (e.target.open) { state.open.add(session.id); await loadEvents(session); renderRun(); } else state.open.delete(session.id);
    } },
    h("summary", {}, `Log of round ${round}${events.length ? ` (${events.length})` : ""}`),
    h("div", { class: "log-lines" }, events.length ? events.map(logLine) : "Open to load the log.")) : null;
  const isWinner = winner === session.id;
  return h("article", { class: `card${isWinner ? " winner" : ""}` },
    h("div", { class: "card-head" },
      h("div", { class: "card-title" }, hide ? null : h("span", { class: `dot ${session.arm}` }), label),
      h("span", { class: `badge ${g.status.replace(" ", "-")}` }, hide && done ? "done" : g.status)),
    preview,
    h("div", { class: "card-body" },
      canVote ? h("button", { class: isWinner ? "primary" : "ghost", onclick: () => vote(session.repeat, session.id) },
        isWinner ? "Picked as best" : "Pick as best") : null,
      metrics,
      !hide && g.preview_note && g.preview ? h("div", { class: "note" }, g.preview_note) : null,
      !hide && g.error ? h("div", { class: "error-text" }, g.error) : null,
      files, scores,
      judgeErrors.length && !hide ? h("div", { class: "error-text" }, `Judge: ${judgeErrors[judgeErrors.length - 1].error}`) : null,
      log));
}

function logLine(event) {
  if (event.kind === "turn") {
    return h("div", {}, h("span", { class: "say" }, `[${event.t}s] turn ${event.n}`, event.text ? `: ${event.text.slice(0, 2000)}` : ""),
      (event.calls || []).map(call => h("div", { class: "call" }, `→ ${call}`)));
  }
  if (event.kind === "tool") {
    return h("div", { class: event.error ? "tool-error" : "" },
      `  ${event.error ? "✗" : "✓"} ${event.name}${event.images ? ` (+${event.images} image)` : ""}: ${(event.output || "").slice(0, 1500)}`);
  }
  if (event.kind === "error") return h("div", { class: "tool-error" }, `[${event.t}s] ${event.text}`);
  if (event.kind === "status") return h("div", {}, `[${event.t}s] ${event.status}${event.note ? ` · ${event.note}` : ""}`);
  return h("div", {}, `[${event.t}s] ${event.text || ""}`);
}

async function vote(repeat, winner) {
  try {
    await api(`/api/runs/${state.runId}/votes`, { method: "POST", body: JSON.stringify({ round: state.round, repeat, winner }) });
    state.revealed.add(`${state.round}:${repeat}`);
    await refreshRun();
  } catch (error) { setMessage("#run-message", error.message, true); }
}

function zoom(src) { const dialog = $("#viewer"); $("img", dialog).src = src; dialog.showModal(); }

async function download(runs, messageSelector) {
  setMessage(messageSelector, "Building the export…");
  try {
    const response = await fetch("/api/export", { method: "POST", body: JSON.stringify({ runs }),
      headers: { "Content-Type": "application/json", "X-Lab-Token": TOKEN } });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const match = (response.headers.get("content-disposition") || "").match(/filename="?([^";]+)/);
    const url = URL.createObjectURL(blob);
    const link = h("a", { href: url, download: match ? match[1] : "vixl-lab-export.zip" });
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    setMessage(messageSelector, `Exported ${(blob.size / 1e6).toFixed(1)} MB.`);
  } catch (error) { setMessage(messageSelector, error.message, true); }
}

$("#blind").addEventListener("change", () => state.run && renderRun());
$("#cancel-run").addEventListener("click", async () => {
  await api(`/api/runs/${state.runId}/cancel`, { method: "POST" });
  setMessage("#run-message", "Cancelling: sessions stop after their current model call.");
});
$("#delete-run").addEventListener("click", async () => {
  if (!confirm("Delete this run, its files and its votes?")) return;
  try { await api(`/api/runs/${state.runId}`, { method: "DELETE" }); location.hash = ""; show("runs"); }
  catch (error) { setMessage("#run-message", error.message, true); }
});
$("#export-run").addEventListener("click", () => download([state.runId], "#run-message"));
$("#open-judge").addEventListener("click", () => {
  const judgeForm = $("#judge-form");
  judgeForm.hidden = !judgeForm.hidden;
  if (!judgeForm.hidden) {
    $("#judge-provider").value = store.get("judge-provider", state.run.provider);
    $("#judge-model").value = store.get("judge-model", state.run.model);
  }
});
$("#judge-form").addEventListener("submit", async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  store.set("judge-provider", data.provider); store.set("judge-model", data.model);
  try {
    const result = await api(`/api/runs/${state.runId}/judge`, { method: "POST", body: JSON.stringify({ ...data, round: state.round }) });
    event.target.api_key.value = "";
    setMessage("#run-message", `Judging ${result.judging} preview${result.judging > 1 ? "s" : ""} of round ${state.round}…`);
    $("#judge-form").hidden = true;
    startPolling(2000); refreshRun();
  } catch (error) { setMessage("#run-message", error.message, true); }
});
$("#followup-form").addEventListener("submit", async event => {
  event.preventDefault();
  const prompt = event.target.prompt.value.trim();
  if (!prompt) return setMessage("#followup-message", "Write the change first.", true);
  try {
    const { round } = await api(`/api/runs/${state.runId}/rounds`, { method: "POST", body: JSON.stringify({ prompt }) });
    event.target.prompt.value = "";
    setMessage("#followup-message", "");
    state.round = round; state.followLatest = true;
    startPolling(1500); refreshRun();
  } catch (error) { setMessage("#followup-message", error.message, true); }
});

// --- runs and scoreboard ----------------------------------------------------------------------------------------

async function loadRuns() {
  const { runs } = await api("/api/runs");
  const table = $("#runs-table");
  $("#export-selected").disabled = true;
  $("#export-all").disabled = !runs.length;
  if (!runs.length) { table.replaceChildren(h("tr", {}, h("td", {}, "No runs yet."))); return; }
  const updateSelection = () => { $("#export-selected").disabled = !table.querySelector("input:checked"); };
  table.replaceChildren(
    h("tr", {}, h("th", {}, h("input", { type: "checkbox", "aria-label": "Select every run", onchange: event => {
      for (const box of table.querySelectorAll("td input")) box.checked = event.target.checked;
      updateSelection();
    } })), ["When", "Brief", "Provider", "Model", "Rounds", "Sessions", "Votes", "Status"].map(t => h("th", {}, t))),
    ...runs.map(run => h("tr", { class: "link", onclick: event => { if (event.target.tagName !== "INPUT") openRun(run.id); } },
      h("td", {}, h("input", { type: "checkbox", value: run.id, "aria-label": `Select run ${run.id}`, onchange: updateSelection })),
      h("td", {}, new Date(run.created * 1000).toLocaleString()),
      h("td", { class: "clip", title: run.prompt }, run.prompt),
      h("td", {}, (state.config.providers[run.provider] || {}).label || run.provider),
      h("td", {}, run.model), h("td", { class: "num" }, run.rounds), h("td", { class: "num" }, run.sessions),
      h("td", { class: "num" }, run.votes), h("td", {}, run.status))));
}

$("#export-selected").addEventListener("click", () =>
  download([...$("#runs-table").querySelectorAll("td input:checked")].map(box => box.value), "#runs-message"));
$("#export-all").addEventListener("click", () => download(null, "#runs-message"));

async function loadStats() {
  const { rows } = await api("/api/stats");
  const table = $("#stats-table");
  if (!rows.length) { table.replaceChildren(h("tr", {}, h("td", {}, "Finish a run to see results here."))); return; }
  const pct = (a, b) => b ? `${Math.round(100 * a / b)}%` : "–";
  table.replaceChildren(
    h("tr", {}, ["Model", "Arm", "Generations", "Delivered", "Blind wins", "Judge", "Median time", "Median tokens", "Mean cost", "Tool errors"]
      .map((t, i) => h("th", { class: i > 1 ? "num" : "" }, t))),
    ...rows.map(row => h("tr", {},
      h("td", {}, row.model), h("td", {}, h("span", { class: `dot ${row.arm}`, style: "display:inline-block;margin-right:6px" }),
        armLabel(row.arm)),
      h("td", { class: "num" }, row.generations, row.followups ? h("span", { class: "hint" }, ` (${row.followups} follow-ups)`) : null),
      h("td", { class: "num" }, pct(row.delivered, row.generations)),
      h("td", { class: "num" }, row.votes ? `${row.wins} / ${row.votes}` : "–"),
      h("td", { class: "num" }, row.judge_mean === null ? "–" : `${row.judge_mean.toFixed(2)} (${row.judged})`),
      h("td", { class: "num" }, row.median_seconds === null ? "–" : fmtSeconds(row.median_seconds)),
      h("td", { class: "num" }, row.median_tokens === null ? "–" : fmtTokens(row.median_tokens)),
      h("td", { class: "num" }, row.mean_cost === null ? "–" : `$${row.mean_cost.toFixed(3)}`),
      h("td", { class: "num" }, row.tool_calls ? pct(row.tool_errors, row.tool_calls) : "–"))));
}

// --- start ------------------------------------------------------------------------------------------------------

loadConfig().then(() => {
  const match = location.hash.match(/run=([\w-]+)/);
  if (match) openRun(match[1]); else show("new");
}).catch(error => setMessage("#form-message", error.message, true));
