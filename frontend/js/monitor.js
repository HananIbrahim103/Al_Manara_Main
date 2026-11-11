/* =========================================================
   MONITOR: Agent 8's job, as a daily view.
   Models tab: one report card per deployed AI model, most urgent first.
   Standards tab: every UAE rule against every model for the quarterly check.
   Detail and explanations open in a side sheet.
   ========================================================= */
const monView = { tab: "models", open: null, q: "", dept: "", sort: "urgency", status: "", rtab: "live" };
const MEASURES = [
  { k: "acc", label: "Correct answers", unit: "%", high: true },
  { k: "hal", label: "Made-up answers", unit: "%" },
  { k: "gap", label: "Arabic vs English gap", unit: "%" },
  { k: "lat", label: "Response time", unit: "s" },
];
const EXIT_RULES = [
  { name: "Pause", when: "A serious error reaches the public, a safety limit is crossed, or data goes somewhere it shouldn't.", does: "It stops at once and staff take over until it passes a re-check.", list: () => LIVE.filter(s => s.health === "paused").map(s => s.name) },
  { name: "Replace", when: "It fails a re-check twice, or the supplier's new terms can't be accepted.", does: "An approved alternative from the Registry takes over.", list: () => [] },
  { name: "Retire", when: "The service no longer needs it, the supplier shuts down, or it can't be brought back within the rules.", does: "It is switched off and its record stays in the Registry.", list: () => ASSESSMENTS.filter(a => a.outcome === "Retired").map(a => a.name) },
];
const TIER_ORDER = { high: 0, medium: 1, low: 2 };
const measureOk = (s, m) => m.high ? s.live[m.k] >= s.lim[m.k] : s.live[m.k] <= s.lim[m.k];
const onTarget = s => MEASURES.filter(m => measureOk(s, m)).length;
const isPinned = s => HEALTH[s.health].cls === "bad";

function openMonitorFor(id) { monView.open = id; monView.tab = "models"; go("monitor"); }

/* ---------- AI value: what each live model returns for what it costs ----------
   Sample figures until finance and usage data are connected. Every number is
   derived from a small set of stated assumptions so the sums can be checked. */
const ROI_RATE = 115;          /* AED per staff hour, fully loaded */
const ROI_FTE_HOURS = 1700;    /* working hours in a staff year */
const ROI_TODAY = new Date("2026-11-10");
const ROI_PROFILES = [
  { k: /faq|assistant|q&a|explainer/i, work: "questions answered", cases: [3000, 12000], mins: [4, 7], resolved: [.3, .5] },
  { k: /summar/i, work: "documents summarised", cases: [700, 2400], mins: [14, 24], resolved: [.7, .85] },
  { k: /draft/i, work: "drafts prepared", cases: [400, 1600], mins: [18, 30], resolved: [.65, .8] },
  { k: /search/i, work: "searches answered", cases: [1500, 5000], mins: [6, 10], resolved: [.55, .75] },
  { k: /route|router|classif|triage|intake/i, work: "cases routed", cases: [1500, 6000], mins: [3, 6], resolved: [.6, .8] },
  { k: /extract/i, work: "documents processed", cases: [800, 3000], mins: [7, 12], resolved: [.7, .85] },
  { k: /detect|checker|anomal/i, work: "items checked", cases: [1500, 6000], mins: [8, 14], resolved: [.6, .8] },
];
const ROI_DEFAULT = { work: "cases handled", cases: [1000, 4000], mins: [6, 12], resolved: [.6, .8] };
const ROI_TIER = {
  low:    { review: .1,  oneTime: 160000, assurance: 25000 },
  medium: { review: .3,  oneTime: 320000, assurance: 50000 },
  high:   { review: 1,   oneTime: 560000, assurance: 90000 },
};
const ROI_STATUS = {
  strong: { label: "Strong return", cls: "ok" },
  modest: { label: "Modest return", cls: "rev" },
  losing: { label: "Not paying back yet", cls: "bad" },
  hold:   { label: "Value on hold", cls: "bad" },
};
const aed = n => { const a = Math.abs(n), s = n < 0 ? "−" : ""; return a >= 1e6 ? `${s}AED ${(a / 1e6).toFixed(2)}M` : a >= 1e3 ? `${s}AED ${Math.round(a / 1e3)}k` : `${s}AED ${Math.round(a)}`; };
const num = n => Math.round(n).toLocaleString("en-GB");

function roiOf(s) {
  if (s._roi) return s._roi;
  const p = ROI_PROFILES.find(x => x.k.test(s.name)) || ROI_DEFAULT, t = ROI_TIER[s.tier];
  const u = i => ((s.seed >>> (i * 3 + 2)) % 1000) / 1000, span = (r, i) => r[0] + u(i) * (r[1] - r[0]);
  const cases = Math.round(span(p.cases, 1) / 50) * 50;         /* per month */
  const manualMin = +span(p.mins, 2).toFixed(1);                 /* staff minutes per case without AI */
  const resolved = +span(p.resolved, 3).toFixed(2);              /* share of cases the AI completes */
  const reviewMin = +(manualMin * .3).toFixed(1);                /* minutes for a person to check one output */
  const errRate = (s.live.hal + (100 - s.live.acc) * .25) / 100; /* outputs that need fixing */
  const fixMin = +(manualMin * 1.5).toFixed(1);
  const N = cases * 12, hourly = m => m / 60 * ROI_RATE;

  const gross = N * resolved * hourly(manualMin);
  const review = N * t.review * hourly(reviewMin);
  const rework = N * errRate * hourly(fixMin);
  const compute = N / 1000 * (s.reused ? 18 : 42);
  const platform = s.reused ? 60000 : 120000;   /* hosting, integration and support */
  const ownership = .35 * ROI_FTE_HOURS * ROI_RATE; /* business owner and service team time */
  const oneTimeFull = t.oneTime, oneTime = s.reused ? Math.round(oneTimeFull * .55) : oneTimeFull;
  const yearlyCost = compute + platform + ownership + t.assurance + oneTime / 3;
  const benefit = gross - review - rework;
  const net = benefit - yearlyCost;
  const roi = net / yearlyCost;
  const monthlyNet = (benefit - (yearlyCost - oneTime / 3)) / 12;
  const payback = monthlyNet > 0 ? oneTime / monthlyNet : Infinity;
  const hours = benefit / ROI_RATE;

  /* Monthly net value since go-live (up to 12 months): usage ramps up over the first months. */
  const live = new Date(s.first.finished || "2026-05-01");
  const monthsLive = Math.max(1, (ROI_TODAY.getFullYear() - live.getFullYear()) * 12 + ROI_TODAY.getMonth() - live.getMonth() + 1);
  const shown = Math.min(12, monthsLive), paused = s.health === "paused";
  const months = Array.from({ length: shown }, (_, i) => {
    const age = monthsLive - shown + i, ramp = Math.min(1, .55 + age * .09), wobble = 1 + ((((s.seed >>> (i + 3)) % 100) / 100) - .5) * .12;
    const d = new Date(ROI_TODAY.getFullYear(), ROI_TODAY.getMonth() - (shown - 1 - i), 1);
    let v = (benefit / 12) * ramp * wobble - (yearlyCost - oneTime / 3) / 12;
    if (paused && i === shown - 1) v = (benefit / 12) * .25 - (yearlyCost - oneTime / 3) / 12;
    return { label: d.toLocaleDateString("en-GB", { month: "short" }), year: d.getFullYear(), v };
  });
  const toDate = months.reduce((a, m) => a + m.v, 0) - oneTime;
  const manualCost = hourly(manualMin);
  const aiCost = manualCost - net / N;
  const status = paused ? "hold" : roi >= 1 ? "strong" : roi >= 0 ? "modest" : "losing";

  return s._roi = { p, cases, manualMin, resolved, reviewMin, reviewShare: t.review, errRate, fixMin, N, gross, review, rework, compute, platform, ownership, assurance: t.assurance,
    oneTime, oneTimeFull, reuseSaved: oneTimeFull - oneTime, yearlyCost, benefit, net, roi, payback, hours, fte: hours / ROI_FTE_HOURS, months, toDate, manualCost, aiCost, status, paused,
    pausedLoss: paused ? benefit / 12 : 0, monthsLive };
}
const roiPct = r => `${r.roi >= 0 ? "" : "−"}${Math.abs(Math.round(r.roi * 100))}%`;
const paybackText = r => r.payback === Infinity ? "Not on current figures" : r.payback < 1 ? "Under 1 month" : `${Math.ceil(r.payback)} months`;

function roiChart(s, r) {
  const W = 600, H = 200, padL = 56, padR = 8, padT = 12, padB = 26, vals = r.months.map(m => m.v);
  const hi = Math.max(0, ...vals), lo = Math.min(0, ...vals), range = hi - lo || 1;
  const y = v => padT + (hi - v) / range * (H - padT - padB), slot = (W - padL - padR) / vals.length, bw = Math.min(34, slot * .62);
  const ticks = [hi, (hi + lo) / 2, lo].filter((v, i, a) => a.findIndex(w => Math.abs(w - v) < range * .05) === i);
  return `<svg class="roi-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Net value per month for ${s.name}, from ${aed(vals[0])} in ${r.months[0].label} to ${aed(vals[vals.length - 1])} in ${r.months[vals.length - 1].label}.">
    ${ticks.map(v => `<line class="roi-grid" x1="${padL}" x2="${W - padR}" y1="${y(v)}" y2="${y(v)}"/><text class="roi-ax" x="${padL - 8}" y="${y(v) + 4}" text-anchor="end">${aed(v).replace("AED ", "")}</text>`).join("")}
    <line class="roi-zero" x1="${padL}" x2="${W - padR}" y1="${y(0)}" y2="${y(0)}"/>
    ${r.months.map((m, i) => {
      const x = padL + i * slot + (slot - bw) / 2, top = Math.min(y(m.v), y(0)), h = Math.max(2, Math.abs(y(m.v) - y(0))), neg = m.v < 0;
      const rad = Math.min(4, h / 2), path = neg
        ? `M${x} ${top}h${bw}v${h - rad}a${rad} ${rad} 0 0 1 ${-rad} ${rad}h${-(bw - 2 * rad)}a${rad} ${rad} 0 0 1 ${-rad} ${-rad}z`
        : `M${x} ${top + h}v${-(h - rad)}a${rad} ${rad} 0 0 1 ${rad} ${-rad}h${bw - 2 * rad}a${rad} ${rad} 0 0 1 ${rad} ${rad}v${h - rad}z`;
      return `<g class="roi-bar${neg ? " neg" : ""}"><rect class="roi-hit" x="${padL + i * slot}" y="${padT}" width="${slot}" height="${H - padT - padB}"/><path d="${path}"/><text class="roi-ax" x="${x + bw / 2}" y="${H - 8}" text-anchor="middle">${m.label}</text><title>${m.label} ${m.year}: ${aed(m.v)} net value</title></g>`;
    }).join("")}
  </svg>`;
}

function roiTab(s) {
  const r = roiOf(s), st = ROI_STATUS[r.status];
  const line = (label, v, note, cls = "") => `<li class="${cls}"><span>${label}<small>${note}</small></span><b>${v < 0 ? "−" : "+"} ${aed(Math.abs(v))}</b></li>`;
  return `
    <div class="roi-head"><span class="hstat ${st.cls}"><i aria-hidden="true"></i>${st.label}</span><span class="roi-say">${r.paused
      ? `Paused since ${fmtDate((s.events.find(e => e.status === "paused") || s.events[0]).date)}. About ${aed(r.pausedLoss)} of staff time a month goes back to manual work until it passes its re-check.`
      : r.status === "losing" ? "Running costs are higher than the staff time it saves. Review volume, oversight level or whether a Registry model would cost less."
      : r.status === "modest" ? "It saves more than it costs, but the margin is thin. Most of the cost is human review and running the service."
      : `Every AED 1 spent returns about AED ${(1 + r.roi).toFixed(1)} in staff time.`}</span></div>

    <div class="roi-kpis">
      <div><small>Net value a year</small><b>${aed(r.net)}</b><span>${r.paused ? "when running normally" : "after all running costs"}</span></div>
      <div><small>Return on investment</small><b>${roiPct(r)}</b><span>per year</span></div>
      <div><small>Payback period</small><b>${paybackText(r)}</b><span>to recover ${aed(r.oneTime)} set-up</span></div>
      <div><small>Staff time returned</small><b>${num(r.hours)} h</b><span>a year · ${r.fte.toFixed(1)} full-time staff</span></div>
    </div>

    <h3>Net value per month <em>${r.months.length} months since it went live</em></h3>
    ${roiChart(s, r)}
    <p class="rp-note">Value to date, after the set-up cost: <b>${aed(r.toDate)}</b>${r.toDate < 0 ? " (still recovering the set-up cost)" : ""}.</p>

    <h3>Where the value comes from <em>per year</em></h3>
    <ul class="roi-flow">
      ${line("Staff time saved", r.gross, `${num(r.N)} ${r.p.work} · ${Math.round(r.resolved * 100)}% completed by the AI · ${r.manualMin} min each by hand`)}
      ${line("Human review of its work", -r.review, `${Math.round(r.reviewShare * 100)}% of outputs checked · ${r.reviewMin} min each`)}
      ${line("Fixing wrong answers", -r.rework, `${(r.errRate * 100).toFixed(1)}% of outputs need fixing, based on live accuracy`)}
      ${line("Model and hosting", -(r.compute + r.platform), s.reused ? "Shared Registry model: hosting, integration and support" : "Supplier licence, hosting, integration and support")}
      ${line("Ownership, assurance and monitoring", -(r.ownership + r.assurance), `Business owner time and Agent 8 re-checks for a ${s.tier}-risk model`)}
      ${line("Set-up cost spread over 3 years", -r.oneTime / 3, `${aed(r.oneTime)} to build, test and approve`)}
      <li class="total"><span>Net value a year</span><b>${aed(r.net)}</b></li>
    </ul>

    <h3>Per case</h3>
    <div class="roi-cmp">
      <div><small>Cost by hand</small><b>AED ${r.manualCost.toFixed(2)}</b></div>
      <div><small>Cost with AI</small><b>AED ${r.aiCost.toFixed(2)}</b></div>
      <div><small>Answer time</small><b>${s.live.lat}s</b><span>vs about ${Math.round(r.manualMin)} min by hand</span></div>
      <div><small>Volume</small><b>${num(r.cases)}</b><span>${r.p.work} a month</span></div>
    </div>
    ${r.reuseSaved ? `<p class="roi-reuse"><b>${aed(r.reuseSaved)} saved at set-up</b> by reusing evidence for ${s.modelName} from the Registry instead of testing from scratch.</p>` : ""}

    <details class="rp-table"><summary>How this is calculated</summary><div class="roi-how">
      <p><b>Net value</b> = staff time saved − review time − time spent fixing errors − yearly running cost.</p>
      <p><b>ROI</b> = net value ÷ yearly cost, where yearly cost includes a third of the set-up cost.</p>
      <p><b>Payback</b> = set-up cost ÷ monthly value after running costs.</p>
      <p>Staff time is costed at AED ${ROI_RATE} an hour and a staff year at ${num(ROI_FTE_HOURS)} hours. Volumes and costs are sample figures until usage and finance data are connected.</p>
    </div></details>`;
}

function roiPortfolio() {
  const all = LIVE.map(roiOf), net = all.reduce((a, r) => a + r.net, 0), cost = all.reduce((a, r) => a + r.yearlyCost, 0);
  return { net, roi: net / cost, hours: all.reduce((a, r) => a + r.hours, 0) };
}

function quarter() {
  const now = new Date(), q = Math.floor(now.getMonth() / 3), next = new Date(now.getFullYear(), (q + 1) * 3, 1);
  return { next: next.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }), days: Math.ceil((next - now) / 864e5) };
}
function compliance() {
  const all = LIVE.flatMap(s => s.standards), pass = all.filter(x => x.now === "pass").length;
  return { pct: Math.round(pass / all.length * 100), pass, total: all.length };
}

/* ---------- the report cards ---------- */
function card_(s) {
  const h = HEALTH[s.health], r = roiOf(s), on = onTarget(s), std = s.passed("now");
  return `<button class="mc ${h.cls}" data-card="${s.id}" aria-haspopup="dialog">
    <span class="mc-top"><span class="mc-name">${s.name}</span><span class="hstat ${h.cls}"><i aria-hidden="true"></i>${h.label}</span></span>
    <span class="mc-sub">${s.dept.short}<span class="dot" aria-hidden="true"></span>${CAPITAL(s.tier)} risk</span>
    <span class="mc-kpis">
      <span><em>Standards</em><strong class="${std < s.standards.length ? "warn" : ""}">${std}/${s.standards.length}</strong></span>
      <span><em>On target</em><strong class="${on < MEASURES.length ? "warn" : ""}">${on}/${MEASURES.length}</strong></span>
      <span><em>Net value / yr</em><strong class="${r.net < 0 ? "warn" : ""}">${aed(r.net)}</strong></span>
    </span>
    <span class="mc-foot">${s.version.label} v${s.version.current}${s.version.newer ? `<span class="mc-new">Newer version available</span>` : ""}</span>
  </button>`;
}
const STATUS_GROUPS = [
  { v: "bad", label: "Action required", note: "Paused or a condition broken" },
  { v: "rev", label: "Needs attention", note: "A problem is being handled" },
  { v: "info", label: "Being re-checked", note: "No action yet" },
  { v: "ok", label: "Healthy", note: "No action needed" },
];
function visibleCards() {
  const q = monView.q.trim().toLowerCase();
  const list = LIVE.filter(s => (!q || `${s.name} ${s.dept.name} ${s.dept.short} ${s.version.label} ${HEALTH[s.health].label}`.toLowerCase().includes(q)) && (monView.dept === "" || s.d === +monView.dept) && (!monView.status || HEALTH[s.health].cls === monView.status));
  const by = {
    urgency: (a, b) => HEALTH[a.health].rank - HEALTH[b.health].rank,
    name: (a, b) => a.name.localeCompare(b.name),
    dept: (a, b) => a.dept.short.localeCompare(b.dept.short),
    risk: (a, b) => TIER_ORDER[a.tier] - TIER_ORDER[b.tier],
    standards: (a, b) => a.passed("now") - b.passed("now"),
  }[monView.sort];
  /* Red cards stay pinned to the top whichever sort is chosen. */
  return list.sort((a, b) => (isPinned(b) - isPinned(a)) || by(a, b) || HEALTH[a.health].rank - HEALTH[b.health].rank || a.name.localeCompare(b.name));
}
function drawCards() {
  const list = visibleCards();
  $("#monCount").textContent = `Showing ${list.length} of ${LIVE.length} models`;
  $("#monCards").innerHTML = list.length ? list.map(card_).join("") : `<p class="empty">No models match. Try clearing the search, status or department filter.</p>`;
}
function modelsTab() {
  const lessons = EVENTS.filter(e => e.lesson).slice(0, 3);
  const depts = DEPTS.map((d, i) => [i, d.short, LIVE.filter(s => s.d === i).length]).filter(x => x[2]);
  return `<div class="mon-status" role="group" aria-label="Filter by status">${STATUS_GROUPS.map(g => { const n = LIVE.filter(x => HEALTH[x.health].cls === g.v).length, on = monView.status === g.v; return `<button class="ms ${g.v}${on ? " on" : ""}" data-status="${g.v}" aria-pressed="${on}"><b>${n}</b><span>${g.label}<small>${g.note}</small></span></button>`; }).join("")}</div>
    <div class="mon-tools">
      <input class="input" id="monSearch" type="search" placeholder="Search by name, department or model" aria-label="Search models" value="${esc(monView.q)}">
      <label class="mon-sort">Sort by <select class="select" id="monSort" aria-label="Sort models">${[["urgency", "Most urgent first"], ["name", "Name"], ["dept", "Department"], ["risk", "Risk level"], ["standards", "Fewest standards passed"]].map(([v, l]) => `<option value="${v}" ${monView.sort === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    </div>
    <div class="filters" role="group" aria-label="Filter by department">${[["", "All departments", LIVE.length], ...depts].map(([v, l, n]) => `<button class="chip ${String(monView.dept) === String(v) ? "on" : ""}" data-dept="${v}" aria-pressed="${String(monView.dept) === String(v)}">${l}<span class="w">${n}</span></button>`).join("")}</div>
    <div class="mon-count" id="monCount" aria-live="polite"></div>
    <div class="mon-cards" id="monCards"></div>
    <section class="mon-lessons">
      <h3>Latest lessons sent to the Registry</h3>
      <ul>${lessons.map(e => `<li><span>${fmtDate(e.date)} · ${e.sy.dept.short}</span>${e.lesson}</li>`).join("")}</ul>
      <button class="linky" id="toLessons">See all incidents and lessons</button>
    </section>`;
}

/* ---------- the Standards tab ---------- */
function standardsTab() {
  const q = quarter(), c = compliance(), total = UAE_STANDARDS.length;
  const resultOf = (s, id) => s.standards.find(x => x.id === id).now;
  const badge = (r, label) => { const m = STANDARD_RESULT[r]; return `<span class="mx-c ${m.cls}" title="${label}"><span aria-hidden="true">${m.icon}</span><span class="vh">${m.label}</span></span>`; };
  const groups = [...new Set(UAE_STANDARDS.map(r => r.source))].map(source => ({ source, rules: UAE_STANDARDS.filter(r => r.source === source) }));
  const rows = [...LIVE].sort((a, b) => a.passed("now") - b.passed("now") || a.name.localeCompare(b.name));
  const issues = LIVE.flatMap(s => s.standards.filter(x => x.now !== "pass").map(x => ({ s, x }))).sort((a, b) => (a.x.now === "fail" ? 0 : 1) - (b.x.now === "fail" ? 0 : 1));
  const firstOf = r => groups.some(g => g.rules[0] === r);
  const bySource = groups.map(g => {
    const all = LIVE.length * g.rules.length, pass = g.rules.reduce((n, r) => n + LIVE.filter(s => resultOf(s, r.id) === "pass").length, 0);
    return { source: g.source, pct: Math.round(pass / all * 100) };
  });
  return `<div class="std-sum">
      <div class="card"><h3>Quarterly check · ${q.next}</h3><div class="sum-big">${c.pct}%</div><div class="sum-note">${c.pass} of ${c.total} rule checks passed</div><span class="hbar"><i style="width:${c.pct}%"></i></span></div>
      <div class="card"><h3>By source of the rules</h3><ul class="src-rows">${bySource.map(b => `<li><b>${b.source}</b><em>${b.pct}%</em><span class="hbar"><i style="width:${b.pct}%"></i></span></li>`).join("")}</ul></div>
      <div class="card"><h3>To resolve before the check · ${issues.length}</h3><ul class="fix-list">${issues.map(({ s, x }) => `<li><button data-card="${s.id}">${badge(x.now, STANDARD_RESULT[x.now].label)}<span><b>${s.name}</b><small>${x.name}</small></span><span class="when">${STANDARD_RESULT[x.now].label}</span></button></li>`).join("")}</ul></div>
    </div>
    <div class="legend">${Object.entries(STANDARD_RESULT).map(([k, m]) => `<span class="lg">${badge(k, m.label)}${m.label}</span>`).join("")}<span class="sum-note" style="margin:0">Hover a column title for the full rule. Select a model to open its report.</span></div>
    <div class="card mx-wrap" tabindex="0" role="region" aria-label="UAE rules checked for each model">
      <table class="mx">
        <thead>
          <tr><th scope="col" rowspan="2" class="mx-m">Model</th>${groups.map(g => `<th scope="colgroup" colspan="${g.rules.length}" class="gs">${g.source}</th>`).join("")}<th scope="col" rowspan="2" class="mx-score">Passed</th></tr>
          <tr>${UAE_STANDARDS.map(r => `<th scope="col" class="${firstOf(r) ? "gs" : ""}" title="${r.name}">${r.short}</th>`).join("")}</tr>
        </thead>
        <tbody>${rows.map(s => `<tr>
          <th scope="row" class="mx-m"><button class="mx-name" data-card="${s.id}">${s.name}</button><small>${s.dept.short}</small></th>
          ${UAE_STANDARDS.map(r => `<td class="${firstOf(r) ? "gs" : ""}">${badge(resultOf(s, r.id), `${s.name}: ${r.name}, ${STANDARD_RESULT[resultOf(s, r.id)].label}`)}</td>`).join("")}
          <td class="mx-score">${s.passed("now")} of ${total}<span class="hbar"><i style="width:${s.passed("now") / total * 100}%"></i></span></td>
        </tr>`).join("")}</tbody>
        <tfoot><tr><th scope="row" class="mx-m">Models passing</th>${UAE_STANDARDS.map(r => `<td class="${firstOf(r) ? "gs" : ""}">${LIVE.filter(s => resultOf(s, r.id) === "pass").length}</td>`).join("")}<td class="mx-score">of ${LIVE.length}</td></tr></tfoot>
      </table>
    </div>`;
}

/* ---------- the side sheet ---------- */
let sheetReturn = null;
function closeSheet() {
  const el = document.getElementById("sheet"); if (!el) return;
  el.remove(); document.body.style.overflow = ""; monView.open = null;
  if (sheetReturn && sheetReturn.isConnected) sheetReturn.focus({ preventScroll: true });
  sheetReturn = null;
}
function openSheet(title, kicker, body, foot = "") {
  const existed = document.getElementById("sheet");
  if (existed) existed.remove(); else sheetReturn = document.activeElement;
  document.body.insertAdjacentHTML("beforeend", `<div id="sheet" class="sheet-scrim"><aside class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheetTitle">
    <header><div><div class="eyebrow">${kicker}</div><h2 id="sheetTitle">${title}</h2></div><button class="sheet-x" id="sheetClose" aria-label="Close">✕</button></header>
    <div class="sheet-body">${body}</div>${foot ? `<footer>${foot}</footer>` : ""}
  </aside></div>`);
  document.body.style.overflow = "hidden";
  const el = document.getElementById("sheet");
  if (!existed && !reduce) { el.querySelector(".sheet").animate([{ transform: "translateX(60px)", opacity: 0 }, { transform: "none", opacity: 1 }], { duration: 320, easing: "cubic-bezier(.2,.7,.2,1)" }); }
  el.querySelector("#sheetClose").focus({ preventScroll: true });
}
addEventListener("hashchange", () => { if (!location.hash.startsWith("#/monitor")) closeSheet(); });
document.addEventListener("keydown", e => {
  const el = document.getElementById("sheet"); if (!el) return;
  if (e.key === "Escape") return closeSheet();
  if (e.key !== "Tab") return;
  const f = [...el.querySelectorAll("button:not(:disabled),summary,[href]")], first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});

function sparkline(s, m) {
  const v = s.trend[m.k], w = 132, h = 40, pad = 6, lim = s.lim[m.k], all = [...v, lim], lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || 1;
  const x = i => pad + i * (w - pad * 2) / (v.length - 1), y = n => h - pad - (n - lo) / span * (h - pad * 2);
  const label = i => i === v.length - 1 ? "This week" : `${v.length - 1 - i} week${v.length - 1 - i > 1 ? "s" : ""} ago`;
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${m.label} over the last 8 weeks, from ${v[0]}${m.unit} to ${v[7]}${m.unit}. Limit ${lim}${m.unit}.">
    <line class="spark-limit" x1="0" x2="${w}" y1="${y(lim)}" y2="${y(lim)}"/>
    <polyline class="spark-line" points="${v.map((n, i) => `${x(i).toFixed(1)},${y(n).toFixed(1)}`).join(" ")}"/>
    <circle class="spark-end" cx="${x(7)}" cy="${y(v[7])}" r="4"/>
    ${v.map((n, i) => `<rect class="spark-hit" x="${x(i) - 9}" y="0" width="18" height="${h}"><title>${label(i)}: ${n}${m.unit}</title></rect>`).join("")}
  </svg>`;
}
function trendWord(s, m) {
  const v = s.trend[m.k], change = v[7] - v[0];
  if (Math.abs(change) < (m.k === "acc" ? .5 : .2)) return "Steady";
  return (m.high ? change > 0 : change < 0) ? "Improving" : "Getting worse";
}
function advice(s) {
  const open = s.events.find(e => e.status !== "resolved");
  if (s.health === "paused") return "Keep it paused until the re-check passes, and make sure staff are covering this service.";
  if (s.health === "broken") return "Ask the department to stop the unapproved use today, then send it for a re-check at the higher risk level.";
  if (s.health === "attention") return open.next;
  if (s.health === "rechecking") return "No action needed yet. Review the result when the re-check finishes.";
  if (s.version.newer) return `Healthy. Plan a re-check before moving to v${s.version.latest}.`;
  return "Healthy. No action needed before the next quarterly check.";
}
function openReport(id) {
  const s = LIVE.find(x => x.id === id); if (!s) return;
  monView.open = id;
  const h = HEALTH[s.health], broken = s.conditions.filter(c => !c.ok).length, nowP = s.passed("now"), lastP = s.passed("last");
  const changeWord = x => x.now === x.last ? "No change" : x.now === "pass" ? "Improved" : x.now === "fail" ? "Newly failing" : "Now under review";
  const r = v => { const m = STANDARD_RESULT[v]; return `<span class="res ${m.cls}"><i aria-hidden="true">${m.icon}</i>${m.label}</span>`; };
  const open = s.events.some(e => e.status !== "resolved");
  const tabs = `<div class="rp-tabs" role="tablist" aria-label="Report views">${[["live", "Live measures"], ["roi", "ROI"]].map(([v, l]) => `<button role="tab" id="rtab-${v}" aria-selected="${monView.rtab === v}" class="${monView.rtab === v ? "on" : ""}" data-rtab="${v}">${l}</button>`).join("")}</div>`;
  const head = `<div class="rp-head"><span class="hstat ${h.cls}"><i aria-hidden="true"></i>${h.label}</span><span class="tier ${s.tier}">${CAPITAL(s.tier)} risk</span><span class="rp-model">${s.version.label} v${s.version.current}${s.version.newer ? ` <span class="badge">Newer version available</span>` : ""}</span></div>`;
  const live = `
    <h3>Live measures</h3>
    <div class="rp-meas">${MEASURES.map(m => { const ok = measureOk(s, m); return `<div class="${ok ? "ok" : "bad"}"><div><small>${m.label}</small><b>${s.live[m.k]}${m.unit}</b><span class="lim"><i aria-hidden="true">${ok ? "✓" : "✕"}</i>${m.high ? "At least" : "No more than"} ${s.lim[m.k]}${m.unit}</span></div><div class="rp-trend">${sparkline(s, m)}<span>${trendWord(s, m)}</span></div></div>`; }).join("")}</div>
    <p class="rp-note">Dashed line shows the limit. Trends cover the last 8 weeks.</p>
    <details class="rp-table"><summary>See the weekly numbers</summary><div><table><thead><tr><th>Measure</th>${[7, 6, 5, 4, 3, 2, 1].map(n => `<th>${n}w ago</th>`).join("")}<th>Now</th></tr></thead><tbody>${MEASURES.map(m => `<tr><th>${m.label}</th>${s.trend[m.k].map(n => `<td>${n}${m.unit}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>

    <h3>Conditions it was approved with ${broken ? `<em class="bad">${broken} broken</em>` : ""}</h3>
    <ul class="conds2">${s.conditions.map(c => `<li class="${c.ok ? "ok" : "bad"}"><i aria-hidden="true">${c.ok ? "✓" : "✕"}</i>${c.text}${c.ok ? "" : " <b>(being broken)</b>"}</li>`).join("")}</ul>

    <h3>UAE standards <em>${nowP} of ${s.standards.length} passed · last quarter ${lastP} of ${s.standards.length}</em></h3>
    <table class="rp-std"><thead><tr><th>Rule</th><th>Last quarter</th><th>This quarter</th><th>Change</th></tr></thead><tbody>${s.standards.map(x => `<tr class="${x.now !== x.last ? "chg" : ""}"><th scope="row">${x.name}<small>${x.source}</small></th><td>${r(x.last)}</td><td>${r(x.now)}</td><td>${changeWord(x)}</td></tr>`).join("")}</tbody></table>

    <h3>Version history</h3>
    <ol class="rp-vers">${s.version.history.map(v => `<li><b>v${v.v}</b>${v.v === s.version.current ? `<span class="badge cur">In use</span>` : v.v === s.version.latest ? `<span class="badge">Newer</span>` : ""}<span>${fmtDate(v.date)}</span><p>${v.notes}</p></li>`).join("")}</ol>

    <h3>What Agent 8 has reacted to</h3>
    ${s.events.length ? `<ul class="evs">${s.events.map(e => { const st = e.status === "resolved" ? "Resolved" : HEALTH[e.status].label; return `<li><span>${fmtDate(e.date)}</span><b>${e.title}</b><small>${st}</small></li>`; }).join("")}</ul>` : `<p class="empty left">Nothing so far. No re-checks have been needed.</p>`}`;
  const body = `${head}${tabs}<div class="rp-panel" role="tabpanel" aria-labelledby="rtab-${monView.rtab}">${monView.rtab === "roi" ? roiTab(s) : live}</div>`;
  const foot = `<div class="rp-next"><span>Recommended next action</span><p>${advice(s)}</p></div>
    <div class="rp-btns">
      <button class="pill solid" id="doRecheck" ${open ? "disabled" : ""}>${open ? "Re-check running" : "Send for re-check"}</button>
      <button class="pill" id="doPause" ${s.health === "paused" ? "disabled" : ""}>${s.health === "paused" ? "Paused" : "Pause"}</button>
      <button class="pill" id="doHistory">Open history in Registry</button>
    </div>`;
  openSheet(s.name, `${s.dept.name} · ${s.id}`, body, foot);
  const refresh = () => { renderMonitorBody(); openReport(id); };
  $("#doRecheck").onclick = () => { monitorAction(s, "recheck"); refresh(); };
  $("#doPause").onclick = e => {
    const b = e.currentTarget;
    if (b.dataset.sure) { monitorAction(s, "pause"); return refresh(); }
    b.dataset.sure = "1"; b.textContent = "Confirm: stop this model"; b.classList.add("danger");
  };
  $("#doHistory").onclick = () => { closeSheet(); openRegistryFor(s.id); };
  $$("#sheet [data-rtab]").forEach(b => b.onclick = () => { monView.rtab = b.dataset.rtab; openReport(id); $(`#rtab-${monView.rtab}`).focus({ preventScroll: true }); });
}
function howSheet() {
  const q = quarter();
  const body = `
    <p class="sub2">Approval isn't the end. Agent 8 keeps watching every live AI model and sends it back whenever something changes. Only the right checks are repeated.</p>
    <h3>What makes it re-check</h3>
    <ul class="trig">${Object.entries(TRIGGERS).filter(([k]) => k !== "manual").map(([k, t]) => `<li><div><b>${t.name}</b><small>${t.plain}</small></div><div class="t-orbs" aria-label="Goes back to agents ${t.route.join(", ")}">${t.route.map(a => agentIcon(AGENTS[a - 1], "", `Agent ${a}: ${AGENTS[a - 1].name}`)).join("")}</div></li>`).join("")}</ul>
    <h3>Quarterly standards check</h3>
    <p class="sub2">Every three months, all live models are checked against the latest UAE rules. The next check is on ${q.next}.</p>
    <h3>When a model is stopped</h3>
    <ul class="exit">${EXIT_RULES.map(r => { const l = r.list(); return `<li><b>${r.name}</b><p>${r.when}</p><small>${r.does}</small><em>${l.length ? `Currently: ${l.join(", ")}` : "None at the moment"}</em></li>`; }).join("")}</ul>`;
  openSheet("How this works", "Monitor · Agent 8", body);
}

/* ---------- the page ---------- */
function renderMonitorBody() {
  const healthy = LIVE.filter(s => s.health === "healthy").length, need = LIVE.length - healthy, q = quarter(), c = compliance();
  $("#monSummary").textContent = `${healthy} of ${LIVE.length} healthy, ${need} need action`;
  const pf = roiPortfolio();
  $("#monDays").textContent = q.days + " days";
  $("#monVal").textContent = aed(pf.net);
  $("#monValNote").textContent = `${roiPct(pf)} ROI · ${num(pf.hours)} staff hours`;
  $("#monNext").textContent = q.next;
  $("#monPct").textContent = c.pct + "%";
  $("#monPctNote").textContent = `${c.pass} of ${c.total} rule checks passed`;
  $("#monBody").innerHTML = monView.tab === "models" ? modelsTab() : standardsTab();
  if (monView.tab === "models") drawCards();
}
function renderMonitor() {
  const a8 = AGENTS[7];
  $("#p-monitor").innerHTML = `
    <div class="mon-top">
      <div class="mon-lead">${agentIcon(a8)}<div><div class="eyebrow">Monitor · Agent 8</div><h2 id="monSummary"></h2></div></div>
      <div class="mon-tiles">
        <div class="mon-tile"><small>Next quarterly check</small><b id="monDays"></b><span id="monNext"></span></div>
        <div class="mon-tile"><small>Compliance so far</small><b id="monPct"></b><span id="monPctNote"></span></div>
        <div class="mon-tile"><small>Net AI value a year</small><b id="monVal"></b><span id="monValNote"></span></div>
        <button class="pill" id="monHow">How this works</button>
      </div>
    </div>
    <div class="seg" role="tablist" aria-label="Monitor views">${[["models", "Models"], ["standards", "Standards"]].map(([v, l]) => `<button role="tab" aria-selected="${monView.tab === v}" class="${monView.tab === v ? "on" : ""}" data-montab="${v}">${l}</button>`).join("")}</div>
    <div id="monBody"></div>`;
  renderMonitorBody();
  if (monView.open) openReport(monView.open);
}
PAGE_HOOKS.monitor = renderMonitor;

$("#p-monitor").addEventListener("click", e => {
  const c = e.target.closest("[data-card]");
  if (c) { sheetReturn = c; return openReport(c.dataset.card); }
  const t = e.target.closest("[data-montab]");
  if (t) { monView.tab = t.dataset.montab; return renderMonitor(); }
  const st = e.target.closest("[data-status]");
  if (st) { monView.status = monView.status === st.dataset.status ? "" : st.dataset.status; return renderMonitorBody(); }
  const d = e.target.closest("[data-dept]");
  if (d) {
    monView.dept = d.dataset.dept;
    $$("[data-dept]").forEach(b => { const on = b.dataset.dept === monView.dept; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); });
    return drawCards();
  }
  if (e.target.closest("#monHow")) return howSheet();
  if (e.target.closest("#toLessons")) { regView.tab = "lessons"; go("registry"); }
});
$("#p-monitor").addEventListener("input", e => { if (e.target.id === "monSearch") { monView.q = e.target.value; drawCards(); } });
$("#p-monitor").addEventListener("change", e => { if (e.target.id === "monSort") { monView.sort = e.target.value; drawCards(); } });
document.addEventListener("click", e => {
  const el = document.getElementById("sheet"); if (!el) return;
  if (e.target === el || e.target.closest("#sheetClose")) closeSheet();
});
