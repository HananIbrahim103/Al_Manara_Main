/* =========================================================
   RECORDS (sample data)
   One shared set of records behind Departments, Registry and
   Monitor, so an agent shows the same facts on every page.
   Replace this file's output with real data when the backend exists.
   ========================================================= */
const hashOf = s => { let h = 2166136261; for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619); return h >>> 0; };
const addDays = (iso, n) => { const d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + Math.round(n)); return d.toISOString().slice(0, 10); };
const fmtDate = iso => iso ? new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "";
const CAPITAL = s => s[0].toUpperCase() + s.slice(1);

/* Pass marks for each risk level. */
const LIMITS = {
  low:    { acc: 88, hal: 3, gap: 8, lat: 4 },
  medium: { acc: 92, hal: 2, gap: 5, lat: 3 },
  high:   { acc: 95, hal: 1, gap: 3, lat: 3 },
};
const REVIEW_TEAMS = {
  low:    ["Business owner", "Data governance"],
  medium: ["Business owner", "Data governance", "Cybersecurity", "Legal & privacy"],
  high:   ["Business owner", "Data governance", "Cybersecurity", "Legal & privacy", "Procurement"],
};
const APPROVERS = ["M. Al Mansoori", "S. Al Hashimi", "R. Khoury"];

/* Everything the eight assurance agents check, in plain language.
   lowSkip: left out on the low-risk fast lane. reusable: can rely on evidence from an approved model. */
const TESTS = [
  { a: 1, name: "Risk level set", what: "How much harm could this cause if it went wrong?", ok: s => `${CAPITAL(s.tier)} risk` },
  { a: 1, name: "Looked for an approved AI that already fits", what: "Avoids testing from scratch if another department already has one.", ok: s => s.reused ? `Found ${s.modelName}. Earlier evidence reused.` : `None fitted, so ${s.model} was brought in.` },
  { a: 2, name: "UAE AI rules", what: "Each rule in the UAE AI framework is matched to proof.", ok: s => { const n = s.tier === "low" ? 12 : 22; return `${n} of ${n} rules matched to proof`; } },
  { a: 2, name: "Data protection rules", what: "Personal information is handled the way the law requires.", ok: s => { const n = s.tier === "low" ? 6 : 12; return `${n} of ${n} rules matched to proof`; } },
  { a: 3, name: "Supplier's claims put in one standard format", what: "So every supplier can be compared fairly.", ok: () => "Benchmarks, licence and terms standardised" },
  { a: 3, name: "Missing supplier information flagged", what: "Anything the supplier didn't tell us counts as a risk.", ok: s => s.unknowns ? `${s.unknowns} item${s.unknowns > 1 ? "s" : ""} missing, recorded as risk` : "Nothing missing" },
  { a: 3, name: "Tests written for this job", what: "Tests are based on what this agent will actually do.", ok: s => `${s.tier === "low" ? 9 : 26} tests created` },
  { a: 4, name: "Accuracy and speed", what: "Does it give correct answers quickly enough?", reusable: true, ok: s => `${s.m.acc}% correct (needs ${s.lim.acc}%) in ${s.m.lat}s` },
  { a: 4, name: "Making things up", what: "How often does it state something false as fact?", reusable: true, ok: s => `${s.m.hal}% of answers (limit ${s.lim.hal}%)` },
  { a: 4, name: "Attempts to trick it", what: "Testers try to make it break its own rules.", reusable: true, ok: s => `0 of ${s.tier === "low" ? 40 : 120} attempts worked` },
  { a: 4, name: "Leaking private information", what: "Can it be made to reveal something it shouldn't?", reusable: true, ok: () => "No leaks found" },
  { a: 4, name: "Reliance on the supplier", what: "Licence, where data is kept, and what happens if the supplier stops.", lowSkip: true, ok: () => "Data stays in the UAE. Exit plan in place." },
  { a: 5, name: "Arabic conversations", what: "Is it as good in Arabic as it is in English?", ok: s => `${s.m.gap}% quality gap (limit ${s.lim.gap}%)` },
  { a: 5, name: "Fair to every group", what: "No group of people gets worse answers than another.", lowSkip: true, ok: () => "No group treated worse" },
  { a: 5, name: "Accessible to everyone", what: "Works for people with disabilities or low digital skills.", ok: () => "Works with screen readers and plain language" },
  { a: 5, name: "People can challenge it", what: "Citizens know AI was used and can appeal.", ok: () => "AI use is disclosed and an appeal route exists" },
  { a: 5, name: "Feedback from frontline staff", what: "The people who will use it every day have tried it.", lowSkip: true, ok: s => `${6 + s.seed % 18} staff tried it, feedback recorded` },
  { a: 6, name: "Results summarised in plain language", what: "The Assurance Package: results, limits, risks and conditions.", ok: () => "Recommendation: approve with conditions" },
  { a: 7, name: "Specialist teams reviewed it", what: "All the teams needed for this risk level, at the same time.", ok: s => `${s.teams.length} of ${s.teams.length} teams cleared it` },
  { a: 7, name: "A named person approved it", what: "A real person accepts the remaining risk, never the AI.", ok: s => `Approved by ${s.approver}` },
  { a: 8, name: "Live monitoring switched on", what: "Agent 8 watches it for as long as it runs.", ok: s => `Watching ${s.conditions.length} conditions` },
];
const STATUS = {
  checked: { label: "Checked", icon: "✓", cls: "ok" },
  review:  { label: "Under review", icon: "◐", cls: "rev" },
  todo:    { label: "Not checked yet", icon: "○", cls: "no" },
};

/* ---------- agents run by each department ---------- */
const FIXED_IDS = { "Visa FAQ assistant": 139, "Benefit eligibility triage": 137, "Meeting minutes drafter": 135, "Clinic appointment router": 131, "Traffic fine explainer": 128 };
const SYSTEMS = [];
DEPTS.forEach((dept, d) => {
  dept.agents = dept.systems.map((row, k) => {
    const [name, tier, stage, model] = row, seed = hashOf(dept.code + name), reused = model.startsWith("Registry"), lim = LIMITS[tier];
    const r = (i, span) => ((seed >>> (i * 3)) % 1000) / 1000 * span;
    const sy = {
      d, k, name, tier, stage, model, seed, reused, lim, dept,
      modelName: model.replace("Registry · ", ""),
      unknowns: reused ? 0 : seed % 3,
      teams: REVIEW_TEAMS[tier], approver: APPROVERS[seed % APPROVERS.length],
      m: { acc: +(Math.min(99.4, lim.acc + 1 + r(1, 3.4))).toFixed(1), hal: +(lim.hal * (.3 + r(2, .5))).toFixed(1), gap: +(lim.gap * (.3 + r(3, .5))).toFixed(1), lat: +(lim.lat * (.4 + r(4, .4))).toFixed(1) },
      conditions: [
        { text: `Only used for its approved job (${name})`, ok: true },
        { text: tier === "high" ? "A person reviews every decision" : "A person reviews any answer it is unsure about", ok: true },
        { text: "No access to personal data beyond the task", ok: true },
        { text: "People are told AI is used and can appeal", ok: true },
      ],
    };
    SYSTEMS.push(sy);
    return sy;
  });
});
/* Reference numbers: most advanced first, so live agents have the oldest numbers. */
{
  let next = 101; const taken = new Set(Object.values(FIXED_IDS));
  [...SYSTEMS].sort((a, b) => b.stage - a.stage).forEach(s => {
    let n = FIXED_IDS[s.name];
    if (!n) { while (taken.has(next)) next++; n = next++; }
    s.num = n; s.id = `UC-2026-${String(n).padStart(4, "0")}`;
  });
}
const sysByName = name => SYSTEMS.find(s => s.name === name);

/* Each agent's checks, with status worked out from where it is in the process. */
SYSTEMS.forEach(s => {
  const list = TESTS.filter(t => !(s.tier === "low" && t.lowSkip));
  const cur = s.stage === 8 ? 9 : s.stage;
  s.skipped = TESTS.length - list.length;
  s.tests = [];
  [1, 2, 3, 4, 5, 6, 7, 8].forEach(a => {
    const group = list.filter(t => t.a === a), active = a === cur || (cur === 4 && a === 5), done = active ? (s.seed >>> a) % group.length : 0;
    group.forEach((t, i) => {
      let st = a < cur ? "checked" : active ? (i < done ? "checked" : "review") : "todo";
      if (a === 7 && active) st = i === 0 ? "review" : "todo";
      const useReused = s.reused && t.reusable && st === "checked";
      s.tests.push({
        ...t, st,
        result: st === "checked" ? t.ok(s) : st === "review" ? (a === 7 ? "Waiting for the review teams to finish" : `Agent ${a} is working on this now`) : "Starts when the earlier checks finish",
        note: useReused ? `Evidence reused from ${s.modelName}. Only the differences were re-tested.` : "",
      });
    });
  });
  s.counts = { checked: 0, review: 0, todo: 0 };
  s.tests.forEach(t => s.counts[t.st]++);
  s.state = s.stage === 8 ? "live" : s.stage === 7 ? "signoff" : "checking";
});
/* Everyday names for the eight steps, used wherever a progress trail is shown. */
["Risk level", "Rules", "Test plan", "Accuracy and safety", "User testing", "Summary", "Sign-off", "Monitoring"].forEach((p, i) => { AGENTS[i].plain = p; });

/* ---------- what Agent 8 reacts to, and which agents it sends a system back to ---------- */
const TRIGGERS = {
  model:      { name: "Model update",        plain: "The company behind the AI releases a new version.",       route: [3, 4, 5] },
  terms:      { name: "Supplier terms change", plain: "The supplier changes its licence, price or data rules.", route: [2, 4] },
  data:       { name: "Data changes",        plain: "The information the AI relies on is changed or added to.", route: [2, 3, 4] },
  used:       { name: "Used in a new way",   plain: "People start using it for something it wasn't approved for.", route: [1, 2, 3] },
  incident:   { name: "Something goes wrong", plain: "An error, outage or leak is reported.",                   route: [4, 6, 7] },
  complaints: { name: "Citizen complaints",  plain: "People complain about or appeal its answers.",             route: [5, 7] },
  manual:     { name: "Requested by a person", plain: "A reviewer asks for a re-check or a pause from the Monitor page.", route: [3, 4, 5] },
};
const HEALTH = {
  paused:     { label: "Paused", icon: "■", cls: "bad", rank: 0 },
  broken:     { label: "Condition broken", icon: "✕", cls: "bad", rank: 1 },
  attention:  { label: "Needs attention", icon: "!", cls: "rev", rank: 2 },
  rechecking: { label: "Being re-checked", icon: "◐", cls: "info", rank: 3 },
  healthy:    { label: "Healthy", icon: "✓", cls: "ok", rank: 4 },
};
/* at = position in the trigger's route the re-check has reached. */
const EVENTS = [
  { sys: "Medical licence FAQ", trigger: "incident", date: "2026-11-08", status: "paused", at: 0, breach: "acc",
    title: "Showed an out-of-date renewal fee in Arabic",
    means: "12 people saw the old fee. No payments were affected.",
    next: "Paused under the exit rules. Staff answer these questions until it passes its re-check.",
    lesson: "Fees should come from the official fee table, never from stored documents." },
  { sys: "Contract clause extractor", trigger: "terms", date: "2026-11-06", status: "attention", at: 0,
    title: "The supplier updated where it can store data",
    means: "Contract text could be stored outside the UAE, which its conditions don't allow.",
    next: "Compliance and supplier checks are running again. A named person must accept the new terms, or the AI is replaced.",
    lesson: "" },
  { sys: "Work permit FAQ", trigger: "complaints", date: "2026-11-02", status: "attention", at: 0, breach: "gap",
    title: "14 complaints about unclear Arabic answers",
    means: "People may be getting less reliable answers in Arabic than in English.",
    next: "User testing is being repeated with the complaints as test cases.",
    lesson: "" },
  { sys: "Policy document search", trigger: "used", date: "2026-10-29", status: "attention", at: 1, brokenCondition: 0,
    title: "Staff started using it to draft legal advice",
    means: "It was approved only for finding documents. Legal advice carries more risk and was never tested.",
    next: "Its risk level is being reassessed. The department has been asked to stop this use until a decision is made.",
    lesson: "Tell staff what a tool is not approved for at the moment they open it." },
  { sys: "Application router", trigger: "model", date: "2026-11-04", status: "rechecking", at: 1,
    title: "The supplier released a new model version",
    means: "Its answers may change, so earlier test results can't be relied on.",
    next: "Tests are being repeated. The approved version stays live until the new one passes.",
    lesson: "" },
  { sys: "Traffic fine explainer", trigger: "data", date: "2026-11-01", status: "rechecking", at: 2,
    title: "A new list of traffic fines was added",
    means: "It needs to explain the new amounts correctly in both languages.",
    next: "Tests are being rewritten and repeated using the new fines.",
    lesson: "" },
  { sys: "Curriculum Q&A for teachers", trigger: "data", date: "2026-09-18", status: "resolved",
    title: "Next term's curriculum was added",
    means: "Teachers needed correct answers about the new material.",
    next: "Passed its re-check and returned to normal monitoring.",
    lesson: "Schedule a re-check whenever content is refreshed for a new school term." },
  { sys: "Licence renewal assistant", trigger: "complaints", date: "2026-08-27", status: "resolved",
    title: "People couldn't find how to appeal",
    means: "The appeal route existed, but the wording hid it.",
    next: "Wording rewritten, re-tested and approved.",
    lesson: "Put the appeal link in the first answer, not at the end of the conversation." },
  { sys: "Budget circular search", trigger: "incident", date: "2026-07-15", status: "resolved",
    title: "A draft circular appeared in search results",
    means: "Staff saw a document that hadn't been published yet.",
    next: "Draft folders removed. Checked again and cleared.",
    lesson: "Exclude draft folders before connecting any document search." },
  { sys: "Lost-item report intake", trigger: "model", date: "2026-06-30", status: "resolved",
    title: "The approved model received a small update",
    means: "Earlier evidence no longer matched the exact version in use.",
    next: "Only the differences were re-tested, and it passed.",
    lesson: "Small updates can reuse most evidence if the version change is recorded." },
];
EVENTS.forEach(ev => { ev.sy = sysByName(ev.sys); ev.t = TRIGGERS[ev.trigger]; });

/* Worst open problem wins. A broken condition outranks everything except a pause. */
function deriveHealth(s) {
  if (s.state !== "live") { s.health = null; return; }
  const states = s.events.filter(e => e.status !== "resolved").map(e => e.status);
  if (s.conditions.some(c => !c.ok)) states.push("broken");
  s.health = states.sort((a, b) => HEALTH[a].rank - HEALTH[b].rank)[0] || "healthy";
}
SYSTEMS.forEach(s => {
  s.events = EVENTS.filter(e => e.sy === s);
  const open = s.events.find(e => e.status !== "resolved");
  /* Live readings sit close to the tested figures, unless an open event has pushed one past its limit. */
  const j = (i, span) => (((s.seed >>> (i * 2 + 1)) % 100) / 100 - .5) * span;
  s.live = { acc: +(Math.min(99.5, s.m.acc + j(1, .8))).toFixed(1), hal: +Math.max(.1, s.m.hal + j(2, .3)).toFixed(1), gap: +Math.max(.2, s.m.gap + j(3, .6)).toFixed(1), lat: +Math.max(.4, s.m.lat + j(4, .3)).toFixed(1) };
  if (open && open.breach === "acc") s.live.acc = +(s.lim.acc - 1.6).toFixed(1);
  if (open && open.breach === "gap") s.live.gap = +(s.lim.gap + 1.4).toFixed(1);
  if (open && open.brokenCondition !== undefined) s.conditions[open.brokenCondition].ok = false;
  deriveHealth(s);
  /* Eight weekly readings ending at today's value. A measure past its limit drifts there over the last four weeks. */
  s.trend = {};
  ["acc", "hal", "gap", "lat"].forEach((k, n) => {
    const breached = open && open.breach === k;
    s.trend[k] = Array.from({ length: 8 }, (_, i) => {
      const noise = (((s.seed >>> (i + n * 4)) % 100) / 100 - .5) * (k === "acc" ? .9 : .35);
      if (i === 7) return s.live[k];
      if (breached && i >= 4) return +(s.m[k] + (s.live[k] - s.m[k]) * ((i - 3) / 4)).toFixed(1);
      return +Math.max(.1, s.m[k] + noise).toFixed(1);
    });
  });
});
const LIVE = SYSTEMS.filter(s => s.state === "live");
AGENTS[7].load = `${LIVE.length} systems watched`;

/* ---------- model versions (sample data) ---------- */
const MODEL_VERSIONS = {
  "GovLLM-S": { current: "1.4", latest: "1.4", history: [
    { v: "1.4", date: "2026-06-25", notes: "Better Arabic search and small fixes to how documents are quoted." },
    { v: "1.3", date: "2026-02-10", notes: "Faster answers on long policy documents." },
    { v: "1.2", date: "2025-09-02", notes: "First version approved for government use." } ] },
  "Tawasul v2.1": { current: "2.1", latest: "2.2", history: [
    { v: "2.2", date: "2026-10-20", notes: "Clearer answers in Gulf dialect and fewer repeated questions. Not yet assessed." },
    { v: "2.1", date: "2026-03-14", notes: "Added Arabic follow-up questions and a clearer route to a human." },
    { v: "2.0", date: "2025-11-30", notes: "Replaced the earlier visa chatbot engine." } ] },
  "Microsoft": { current: "2026.05", latest: "2026.10", history: [
    { v: "2026.10", date: "2026-10-28", notes: "New supplier release. Re-check needed before it can be used." },
    { v: "2026.05", date: "2026-05-12", notes: "Version approved for application routing." } ] },
  "Google": { current: "2026.04", latest: "2026.04", history: [
    { v: "2026.04", date: "2026-04-08", notes: "Version approved for contract clause extraction." },
    { v: "2025.12", date: "2025-12-01", notes: "Earlier version, used only during testing." } ] },
};

/* ---------- UAE standards checked every quarter (sample list, to be confirmed by governance) ---------- */
const UAE_STANDARDS = [
  { id: "oversight", name: "A person stays in control", short: "Human control", source: "UAE AI Charter" },
  { id: "transparency", name: "People are told AI is used", short: "AI disclosed", source: "UAE AI Charter" },
  { id: "safety", name: "Safe and reliable answers", short: "Safety", source: "UAE AI Charter" },
  { id: "fairness", name: "Fair treatment of every group", short: "Fairness", source: "UAE AI Ethics" },
  { id: "accountability", name: "A named owner is accountable", short: "Named owner", source: "UAE AI Ethics" },
  { id: "privacy", name: "Privacy built in by design", short: "Privacy", source: "UAE AI Ethics" },
  { id: "lawful", name: "Personal data handled lawfully", short: "Lawful data", source: "Data protection law" },
  { id: "residency", name: "Data kept in approved locations", short: "Data location", source: "Data protection law" },
  { id: "security", name: "Cybersecurity controls in place", short: "Cyber controls", source: "Information assurance" },
  { id: "arabic", name: "Arabic quality matches English", short: "Arabic quality", source: "Digital services" },
  { id: "access", name: "Accessible to everyone", short: "Accessible", source: "Digital services" },
  { id: "appeal", name: "People can challenge outcomes", short: "Right to appeal", source: "Digital services" },
];
const STANDARD_RESULT = { pass: { label: "Passed", icon: "✓", cls: "ok" }, fail: { label: "Failed", icon: "✕", cls: "bad" }, review: { label: "Under review", icon: "◐", cls: "info" } };
/* What each open problem does to this quarter's standards result. */
const STANDARD_HITS = { "Medical licence FAQ": ["safety", "fail"], "Contract clause extractor": ["residency", "fail"], "Work permit FAQ": ["arabic", "fail"], "Policy document search": ["oversight", "fail"], "Application router": ["safety", "review"], "Traffic fine explainer": ["safety", "review"] };
LIVE.forEach(s => {
  const facts = MODEL_VERSIONS[s.modelName], hit = STANDARD_HITS[s.name];
  s.version = { label: s.modelName.replace(/ v[\d.]+$/, ""), current: facts.current, latest: facts.latest, newer: facts.latest !== facts.current, history: facts.history };
  s.standards = UAE_STANDARDS.map((std, i) => ({ ...std, last: (s.seed >>> i) % 11 === 0 ? "review" : "pass", now: hit && hit[0] === std.id ? hit[1] : "pass" }));
  s.passed = which => s.standards.filter(x => x[which] === "pass").length;
});

/* ---------- the assessment history ---------- */
const STEP_LABELS = ["Risk level set", "Rules and compliance checked", "Tests written", "Accuracy and security tested", "User testing done", "Results summarised", "Human sign-off", "Live and monitored"];
const TIER_DAYS = { low: 2, medium: 6, high: 12 };
const ASSESSMENTS = [];
SYSTEMS.forEach(s => {
  /* Live agents were assessed earlier in the year; anything still open started recently. */
  const started = s.state === "live" ? addDays("2026-04-01", (s.num - 101) * 5.2) : addDays("2026-09-22", (s.num - 112) * 1.6), span = TIER_DAYS[s.tier] + s.seed % 3;
  const finished = s.stage === 8 ? addDays(started, span) : null;
  const steps = STEP_LABELS.map((label, i) => {
    const n = i + 1, state = n < s.stage || s.stage === 8 ? "done" : n === s.stage || (s.stage === 4 && n === 5) ? "now" : "later";
    return { label, state, date: state === "done" ? addDays(started, span * (n / 8)) : null };
  });
  s.first = {
    key: s.id, id: s.id, sy: s, name: s.name, d: s.d, tier: s.tier, kind: "First assessment", started, finished, steps,
    outcome: s.state === "live" ? "Approved with conditions" : s.state === "signoff" ? "Waiting for sign-off" : "Being checked",
    group: s.state === "live" ? "approved" : "progress",
    summary: s.state === "live" ? `Checked in ${span} working days. Approved by ${s.approver} with ${s.conditions.length} conditions.` : s.state === "signoff" ? "All testing is finished. A named person still has to approve it." : `Currently with Agent ${s.stage}. ${s.counts.checked} of ${s.tests.length} checks finished.`,
    evidence: s.counts.checked * 3 + (s.seed % 5),
  };
  ASSESSMENTS.push(s.first);
  s.events.forEach((ev, i) => ASSESSMENTS.push(recheckRecord(s, ev, `R${i + 2}`)));
});
function recheckRecord(s, ev, tag) {
  const done = ev.status === "resolved", at = done ? ev.t.route.length : ev.at;
  return {
    key: `${s.id}-${tag}`, id: `${s.id} · re-check`, sy: s, name: s.name, d: s.d, tier: s.tier, kind: `Re-check: ${ev.t.name.toLowerCase()}`, started: ev.date, finished: done ? addDays(ev.date, 3 + s.seed % 4) : null,
    steps: ev.t.route.map((a, j) => ({ label: `${AGENTS[a - 1].name} (Agent ${a})`, state: j < at ? "done" : j === at ? "now" : "later", date: j < at ? addDays(ev.date, j + 1) : null })),
    outcome: done ? "Re-check passed" : ev.status === "paused" ? "Paused, re-check running" : "Re-check running",
    group: done ? "approved" : "progress", event: ev,
    summary: `${ev.title}. ${ev.next}`,
    evidence: done ? 8 + s.seed % 9 : 2 + s.seed % 4,
  };
}
/* The Monitor page's buttons: recorded so Departments and the Registry show the same thing. */
function monitorAction(s, kind) {
  const paused = kind === "pause";
  const ev = {
    sys: s.name, sy: s, trigger: "manual", t: TRIGGERS.manual, date: new Date().toISOString().slice(0, 10), status: paused ? "paused" : "rechecking", at: 0, lesson: "",
    title: paused ? "Paused by a reviewer" : "Re-check requested by a reviewer",
    means: paused ? "It has stopped answering until it passes a re-check." : "Its results are being tested again.",
    next: paused ? "Staff take over this service until the re-check passes." : "It stays live while the checks are repeated.",
  };
  EVENTS.unshift(ev); s.events.unshift(ev);
  ASSESSMENTS.unshift(recheckRecord(s, ev, `M${s.events.length}`));
  deriveHealth(s);
}
/* Earlier use cases that never reached, or have left, live service. */
[
  { id: "UC-2025-0412", name: "Customs declaration helper", dept: "MOF", tier: "high", started: "2025-11-12", finished: "2025-12-02", outcome: "Not approved", summary: "Failed the Arabic conversations test twice. The department withdrew it." },
  { id: "UC-2025-0388", name: "Clinic wait-time estimator", dept: "MOHAP", tier: "medium", started: "2025-10-20", finished: "2025-11-04", outcome: "Not approved", summary: "The supplier wouldn't confirm where data is stored, which counted as a risk." },
  { id: "UC-2025-0341", name: "Legacy visa chatbot", dept: "ICP", tier: "medium", started: "2025-08-05", finished: "2026-03-30", outcome: "Retired", summary: "Replaced by Tawasul v2.1 under the exit rules, after repeated complaints." },
  { id: "UC-2025-0297", name: "School transport FAQ", dept: "MOE", tier: "low", started: "2025-06-16", finished: "2026-02-11", outcome: "Retired", summary: "No longer needed once the service moved to the main ministry portal." },
].forEach(o => {
  ASSESSMENTS.push({ ...o, key: o.id, d: DEPTS.findIndex(x => x.code === o.dept), kind: "First assessment", group: "closed", steps: [], evidence: 18 + hashOf(o.id) % 22 });
});
ASSESSMENTS.sort((a, b) => (b.finished || b.started) > (a.finished || a.started) ? 1 : -1);

const EVIDENCE_TOTAL = 1284;
const MODEL_FACTS = {
  "GovLLM-S":     { version: "1.4", maker: "Built within government", data: "Public and internal documents", language: "Arabic and English", people: "Staff and citizens", ready: true },
  "Tawasul v2.1": { version: "2.1", maker: "Tawasul FAQ Assistant", data: "Public service information", language: "Arabic and English", people: "Citizens and residents", ready: true },
  "Microsoft":    { version: "As approved", maker: "Outside supplier", data: "Application details", language: "Arabic and English", people: "Staff", ready: false },
  "Google":       { version: "As approved", maker: "Outside supplier", data: "Internal contract text", language: "English", people: "Staff", ready: false },
};
const APPROVED_MODELS = Object.keys(MODEL_FACTS).map(name => {
  const users = LIVE.filter(s => s.modelName === name);
  return { name, ...MODEL_FACTS[name], users, depts: [...new Set(users.map(s => s.dept.short))] };
});
