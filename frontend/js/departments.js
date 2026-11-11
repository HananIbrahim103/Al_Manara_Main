/* =========================================================
   DEPARTMENTS: pick a department, pick one of its AI agents,
   see exactly what has and hasn't been checked.
   ========================================================= */
const dView = { d: 0, s: 0, filter: "all" };

function openDept(i, s) {
  dView.d = i; dView.s = s == null ? 0 : s; dView.filter = "all";
  go("dept");
}
const dCount = (d, st) => d.agents.filter(a => a.state === st).length;

function statePill(sy) {
  if (sy.state === "live") { const h = HEALTH[sy.health]; return `<span class="flag ${h.cls}"><i>${h.icon}</i>${sy.health === "healthy" ? "Live" : h.label}</span>`; }
  return sy.state === "signoff" ? `<span class="flag rev"><i>◐</i>Waiting for sign-off</span>` : `<span class="flag info"><i>◐</i>Being checked</span>`;
}
function statusSentence(sy) {
  if (sy.state === "live") {
    const open = sy.events.find(e => e.status !== "resolved");
    if (open && sy.health === "broken") return `It is approved, but one of its conditions is being broken: ${open.title.toLowerCase()}.`;
    return open ? `It is approved, but Agent 8 raised something: ${open.title.toLowerCase()}.` : "It is approved and running. Agent 8 is watching it.";
  }
  if (sy.state === "signoff") return "All testing is finished. A named person now has to approve it.";
  return `It is being checked right now by Agent ${sy.stage}, ${AGENTS[sy.stage - 1].name}. ${sy.counts.checked} of ${sy.tests.length} checks are done.`;
}
function journey(sy) {
  return `<ol class="journey" aria-label="Progress through the eight assurance agents">${AGENTS.map((a, i) => {
    const n = i + 1, state = sy.stage === 8 || n < sy.stage ? "done" : n === sy.stage || (sy.stage === 4 && n === 5) ? "now" : "later";
    return `<li class="${state}">${agentIcon(a)}<b>${n}</b><small>${a.plain}</small></li>`;
  }).join("")}</ol>`;
}
function testsBlock(sy) {
  const shown = sy.tests.filter(t => dView.filter === "all" || t.st === dView.filter);
  if (!shown.length) return `<p class="empty">Nothing in this group for this agent.</p>`;
  return AGENTS.map(a => {
    const rows = shown.filter(t => t.a === a.n);
    if (!rows.length) return "";
    return `<section class="tgroup"><h4>${agentIcon(a)}Agent ${a.n} · ${a.name}</h4><ul>${rows.map(t => {
      const s = STATUS[t.st];
      return `<li class="test"><span class="ticon ${s.cls}" aria-hidden="true">${s.icon}</span><div><b>${t.name}</b><small>${t.what}</small><em class="${s.cls}">${t.result}</em>${t.note ? `<small class="reuse">${t.note}</small>` : ""}</div><span class="flag ${s.cls}">${s.label}</span></li>`;
    }).join("")}</ul></section>`;
  }).join("");
}
function agentDetail(sy) {
  const f = [["all", "All checks", sy.tests.length], ["checked", "✓ Checked", sy.counts.checked], ["review", "◐ Under review", sy.counts.review], ["todo", "○ Not checked yet", sy.counts.todo]];
  return `
    <header class="ad-h">
      <div><div class="eyebrow">${sy.dept.code} · ${sy.id}</div><h3>${sy.name}</h3></div>
      <div class="ad-tags"><span class="tier ${sy.tier}">${CAPITAL(sy.tier)} risk</span>${statePill(sy)}</div>
    </header>
    <p class="ad-say">${statusSentence(sy)}</p>
    <dl class="facts"><div><dt>AI model</dt><dd>${sy.modelName}${sy.reused ? " (from the Registry)" : ""}</dd></div><div><dt>Started</dt><dd>${fmtDate(sy.first.started)}</dd></div><div><dt>Approved by</dt><dd>${sy.state === "live" ? sy.approver : "Not yet"}</dd></div></dl>
    <div class="eyebrow ad-sub">Where it is in the process</div>
    ${journey(sy)}
    <div class="eyebrow ad-sub">What has been checked</div>
    <div class="filters" role="group" aria-label="Filter checks">${f.map(([v, l, n]) => `<button class="chip ${dView.filter === v ? "on" : ""}" data-filter="${v}" aria-pressed="${dView.filter === v}">${l}<span class="w">${n}</span></button>`).join("")}</div>
    ${sy.skipped ? `<p class="note">This is a low-risk agent, so it took the fast lane and skipped ${sy.skipped} deeper checks.</p>` : ""}
    ${testsBlock(sy)}
    ${sy.state === "live" ? `<div class="eyebrow ad-sub">Rules it must follow while live</div><ul class="conds2">${sy.conditions.map(c => `<li class="${c.ok ? "ok" : "bad"}"><i aria-hidden="true">${c.ok ? "✓" : "✕"}</i>${c.text}${c.ok ? "" : " <b>(not being followed)</b>"}</li>`).join("")}</ul>` : ""}
    <div class="ad-foot">
      <button class="pill" data-history="${sy.id}">See its history in the Registry</button>
      ${sy.state === "live" ? `<button class="pill" data-monitor="${sy.id}">See it in Monitor</button>` : ""}
    </div>`;
}

function renderDept() {
  const d = DEPTS[dView.d], sy = d.agents[dView.s] || d.agents[0];
  /* keep each list where the reader left it when the page re-renders */
  const keep = {};
  $$("#p-dept [data-scroll]").forEach(el => { keep[el.dataset.scroll] = [el.scrollTop, el.scrollLeft]; });
  $("#p-dept").innerHTML = `
    <div class="ph">
      <div><div class="eyebrow">Departments</div><h2>${d.name}</h2><p class="ph-say">Choose an AI agent to see what has been checked, what is under review and what hasn't started.</p></div>
      <button class="pill solid" id="deptNew">+ New use case for ${d.code}</button>
    </div>
    <div class="d-stats">
      <div class="card"><b>${d.agents.length}</b><span>AI agents</span></div>
      <div class="card"><b>${dCount(d, "live")}</b><span>Live and running</span></div>
      <div class="card"><b>${dCount(d, "checking")}</b><span>Being checked</span></div>
      <div class="card"><b>${dCount(d, "signoff")}</b><span>Waiting for sign-off</span></div>
    </div>
    <div class="d-board" id="dBoard">
      <nav class="card d-col" aria-label="Departments">
        <div class="d-colh">Departments<span>${DEPTS.length}</span></div>
        <div class="d-scroll d-rail" data-scroll="rail">${DEPTS.map((x, i) => `<button class="${i === dView.d ? "on" : ""}" data-d="${i}" ${i === dView.d ? 'aria-current="true"' : ""}><b>${x.short}</b><small>${x.agents.length} agents · ${dCount(x, "live")} live</small></button>`).join("")}</div>
      </nav>
      <div class="card d-col">
        <div class="d-colh">AI agents in ${d.short}<span>${d.agents.length}</span></div>
        <div class="d-scroll d-agents" data-scroll="agents" role="list" aria-label="AI agents in ${d.short}">${d.agents.map((a, k) => `<button role="listitem" class="agentcard ${a === sy ? "on" : ""}" data-pick="${k}" ${a === sy ? 'aria-current="true"' : ""}>
            <span class="sq" aria-hidden="true"></span><span class="ac-b"><b>${a.name}</b><small>${a.counts.checked} of ${a.tests.length} checks done</small><span class="bar"><i style="width:${Math.round(a.counts.checked / a.tests.length * 100)}%"></i></span></span>${statePill(a)}</button>`).join("")}</div>
      </div>
      <article class="card d-col agentdetail" id="agentDetail" tabindex="0" aria-label="Details for ${sy.name}">${agentDetail(sy)}</article>
    </div>`;
  $("#deptNew").onclick = () => { state.entity = d.name; $("#fEntity").value = d.name; update(); step(1); go("new"); };
  fitBoard();
  $$("#p-dept [data-scroll]").forEach(el => { const k = keep[el.dataset.scroll]; if (k) { el.scrollTop = k[0]; el.scrollLeft = k[1]; } });
}
PAGE_HOOKS.dept = renderDept;

/* The three columns share one height that fills the rest of the screen; each scrolls on its own. */
function fitBoard() {
  const el = $("#dBoard");
  if (!el || !el.offsetParent) return;
  if (innerWidth <= 1180) return el.style.removeProperty("--board-h");
  const top = el.getBoundingClientRect().top + window.scrollY;
  el.style.setProperty("--board-h", Math.max(520, innerHeight - top - 48) + "px"); /* 48 leaves room for the page's bottom padding */
}
addEventListener("resize", fitBoard);

$("#p-dept").addEventListener("click", e => {
  const pick = e.target.closest("[data-pick]");
  if (pick) {
    dView.s = +pick.dataset.pick; dView.filter = "all"; renderDept(); syncRoute();
    if (innerWidth <= 1180) $("#agentDetail").scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  const f = e.target.closest("[data-filter]");
  if (f) {
    dView.filter = f.dataset.filter;
    const sy = DEPTS[dView.d].agents[dView.s];
    $("#agentDetail").innerHTML = agentDetail(sy);
    return;
  }
  const h = e.target.closest("[data-history]");
  if (h) return openRegistryFor(h.dataset.history);
  const m = e.target.closest("[data-monitor]");
  if (m) return openMonitorFor(m.dataset.monitor);
});
