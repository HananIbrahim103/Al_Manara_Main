/* =========================================================
   REGISTRY: the shared memory. Every assessment, approved
   model, incident and lesson, so departments can reuse them.
   ========================================================= */
const regView = { tab: "history", q: "", dept: "", tier: "", group: "", open: null };
const OUTCOME_CLS = { "Approved with conditions": "ok", "Re-check passed": "ok", "Waiting for sign-off": "rev", "Being checked": "info", "Re-check running": "info", "Paused, re-check running": "bad", "Not approved": "bad", "Retired": "no" };
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function openRegistryFor(id) {
  const rec = ASSESSMENTS.find(a => a.sy && a.sy.id === id);
  Object.assign(regView, { tab: "history", q: rec.name, dept: "", tier: "", group: "", open: rec.key });
  go("registry");
}
function regMatches() {
  const q = regView.q.trim().toLowerCase();
  return ASSESSMENTS.filter(a => (!q || `${a.name} ${a.id} ${DEPTS[a.d].name} ${DEPTS[a.d].short} ${a.outcome} ${a.kind}`.toLowerCase().includes(q))
    && (regView.dept === "" || a.d === +regView.dept) && (!regView.tier || a.tier === regView.tier) && (!regView.group || a.group === regView.group));
}
function regDetail(a) {
  const tally = a.sy && a.kind === "First assessment" ? `<div><dt>Checks</dt><dd>${a.sy.counts.checked} checked · ${a.sy.counts.review} under review · ${a.sy.counts.todo} not checked yet</dd></div>` : "";
  const steps = a.steps.length ? `<div class="eyebrow ad-sub">What happened, step by step</div><ol class="tline">${a.steps.map(s => `<li class="${s.state}"><i aria-hidden="true"></i><b>${s.label}</b><span>${s.state === "done" ? fmtDate(s.date) : s.state === "now" ? "In progress now" : "Not started"}</span></li>`).join("")}</ol>` : "";
  return `<div class="rd">
    <p class="ad-say">${a.summary}</p>
    <dl class="facts">
      <div><dt>Started</dt><dd>${fmtDate(a.started)}</dd></div>
      <div><dt>Finished</dt><dd>${a.finished ? fmtDate(a.finished) : "Still open"}</dd></div>
      <div><dt>Evidence on file</dt><dd>${a.evidence} items</dd></div>
      <div><dt>Accountable</dt><dd>${DEPTS[a.d].name}</dd></div>
      ${tally}
    </dl>
    ${steps}
    ${a.sy ? `<div class="ad-foot"><button class="pill" data-d="${a.sy.d}" data-s="${a.sy.k}">Open this agent in Departments</button></div>` : ""}
  </div>`;
}
function regRows() {
  const rows = regMatches(), el = $("#regRows");
  $("#regCount").textContent = `Showing ${rows.length} of ${ASSESSMENTS.length} assessments`;
  el.innerHTML = rows.length ? rows.map(a => {
    const open = regView.open === a.key;
    return `<div class="rrow-wrap ${open ? "open" : ""}"><button class="rrow" data-rec="${a.key}" aria-expanded="${open}">
      <span class="r-date">${fmtDate(a.finished || a.started)}</span>
      <span class="r-name"><b>${a.name}</b><small class="mono">${a.id}</small></span>
      <span class="r-dept">${DEPTS[a.d].short}</span>
      <span><span class="tier ${a.tier}">${CAPITAL(a.tier)}</span></span>
      <span class="r-kind">${a.kind}</span>
      <span class="flag ${OUTCOME_CLS[a.outcome]}">${a.outcome}</span>
      <span class="r-chev" aria-hidden="true">${open ? "−" : "+"}</span>
    </button>${open ? regDetail(a) : ""}</div>`;
  }).join("") : `<p class="empty">No assessments match. Try clearing the search or filters.</p>`;
}
function historyTab() {
  const chips = (key, opts) => opts.map(([v, l]) => `<button class="chip ${regView[key] === v ? "on" : ""}" data-set="${key}" data-val="${v}" aria-pressed="${regView[key] === v}">${l}</button>`).join("");
  return `<div class="card">
    <div class="r-tools">
      <input class="input" id="regSearch" type="search" placeholder="Search by name, reference or department" aria-label="Search assessments" value="${esc(regView.q)}">
      <select class="select" id="regDept" aria-label="Filter by department"><option value="">All departments</option>${DEPTS.map((d, i) => `<option value="${i}" ${regView.dept === String(i) ? "selected" : ""}>${d.short}</option>`).join("")}</select>
    </div>
    <div class="r-chips">
      <div class="filters" role="group" aria-label="Filter by result">${chips("group", [["", "All results"], ["approved", "Approved"], ["progress", "In progress"], ["closed", "Not approved or retired"]])}</div>
      <div class="filters" role="group" aria-label="Filter by risk">${chips("tier", [["", "Any risk"], ["low", "Low"], ["medium", "Medium"], ["high", "High"]])}</div>
    </div>
    <div class="r-count" id="regCount" aria-live="polite"></div>
    <div class="rhead" aria-hidden="true"><span>Date</span><span>Use case</span><span>Department</span><span>Risk</span><span>Type</span><span>Result</span><span></span></div>
    <div id="regRows"></div>
  </div>`;
}
function modelsTab() {
  return `<p class="note wide">Before a department reuses an approved AI, Agent 1 compares five things: <b>version, risk level, data, language and users</b>. Whatever is different gets tested again. The department using it always stays accountable.</p>
  <div class="m-grid">${APPROVED_MODELS.map(m => `<article class="card model">
    <header><div><div class="eyebrow">${m.maker}</div><h3>${m.name}</h3></div><span class="flag ${m.ready ? "ok" : "no"}"><i>${m.ready ? "✓" : "○"}</i>${m.ready ? "Ready to reuse" : "One agent so far"}</span></header>
    <dl class="facts tight"><div><dt>Version</dt><dd>${m.version}</dd></div><div><dt>Approved for data</dt><dd>${m.data}</dd></div><div><dt>Languages</dt><dd>${m.language}</dd></div><div><dt>Used with</dt><dd>${m.people}</dd></div></dl>
    <div class="eyebrow ad-sub">In use by</div>
    <ul class="m-users">${m.users.map(s => `<li><button class="linky" data-d="${s.d}" data-s="${s.k}">${s.name}</button><small>${s.dept.short}</small></li>`).join("")}</ul>
  </article>`).join("")}</div>`;
}
function lessonsTab() {
  return `<p class="note wide">Everything Agent 8 finds is recorded here, so one department's problem doesn't have to happen again somewhere else.</p>
  <div class="l-list">${EVENTS.map(ev => {
    const open = ev.status !== "resolved", h = HEALTH[ev.status] || { label: "Resolved", icon: "✓", cls: "ok" };
    return `<article class="card lesson">
      <header><div><div class="eyebrow">${fmtDate(ev.date)} · ${ev.t.name}</div><h3>${ev.title}</h3></div><span class="flag ${h.cls}"><i>${h.icon}</i>${open ? h.label : "Resolved"}</span></header>
      <p class="l-where"><button class="linky" data-d="${ev.sy.d}" data-s="${ev.sy.k}">${ev.sy.name}</button> · ${ev.sy.dept.short}</p>
      <div class="l-learned"><span>Lesson for everyone</span><p>${ev.lesson || "Still being worked out. It will be added when the re-check finishes."}</p></div>
    </article>`;
  }).join("")}</div>`;
}
function renderRegistry() {
  const inProgress = ASSESSMENTS.filter(a => a.group === "progress").length, approved = ASSESSMENTS.filter(a => a.outcome === "Approved with conditions").length;
  const tabs = [["history", "Assessment history"], ["models", "Approved AI models"], ["lessons", "Incidents and lessons"]];
  $("#p-registry").innerHTML = `
    <div class="ph"><div><div class="eyebrow">Registry</div><h2>Everything ever assessed</h2><p class="ph-say">The shared record of every assessment, approved AI model, incident and lesson, so no department has to start from zero.</p></div></div>
    <div class="m-stats">
      <div class="card"><b>${ASSESSMENTS.length}</b><span>Assessments on record</span></div>
      <div class="card"><b>${approved}</b><span>Approved</span></div>
      <div class="card"><b>${inProgress}</b><span>In progress</span></div>
      <div class="card"><b>${EVIDENCE_TOTAL.toLocaleString("en-GB")}</b><span>Evidence items to reuse</span></div>
    </div>
    <div class="seg" role="tablist" aria-label="Registry sections">${tabs.map(([v, l]) => `<button role="tab" aria-selected="${regView.tab === v}" class="${regView.tab === v ? "on" : ""}" data-tab="${v}">${l}</button>`).join("")}</div>
    <div id="regBody">${regView.tab === "history" ? historyTab() : regView.tab === "models" ? modelsTab() : lessonsTab()}</div>`;
  if (regView.tab === "history") regRows();
}
PAGE_HOOKS.registry = renderRegistry;

$("#p-registry").addEventListener("click", e => {
  const t = e.target.closest("[data-tab]");
  if (t) { regView.tab = t.dataset.tab; return renderRegistry(); }
  const r = e.target.closest("[data-rec]");
  if (r) { regView.open = regView.open === r.dataset.rec ? null : r.dataset.rec; return regRows(); }
  const c = e.target.closest("[data-set]");
  if (c) { regView[c.dataset.set] = c.dataset.val; regView.open = null; return renderRegistry(); }
});
$("#p-registry").addEventListener("input", e => { if (e.target.id === "regSearch") { regView.q = e.target.value; regView.open = null; regRows(); } });
$("#p-registry").addEventListener("change", e => { if (e.target.id === "regDept") { regView.dept = e.target.value; regView.open = null; regRows(); } });
