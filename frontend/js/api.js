/* =========================================================
   LIVE DATA (add-on)
   Connects the prototype to the governance backend without
   changing any other file. Loaded last. Until someone connects,
   the page runs on its own sample data exactly as before.

   Once connected it reads the backend (read-only) and puts its
   departments, use cases, assessments, deployments, alerts and
   lessons into the same records the pages already draw from
   (DEPTS, SYSTEMS, ASSESSMENTS, EVENTS, LIVE, APPROVED_MODELS),
   then redraws the pages.

   Still the prototype's own simulation, and labelled as such:
   the New use case wizard and its pipeline, the ROI figures, and
   the Monitor's Pause / Re-check buttons (nothing is sent back).

   Where the backend is:  ?api=https://host  (remembered), or
   window.ALMANARA_API, else localhost:8000 when opened locally
   and the deployed service otherwise.  ?sample=1 stays on samples.
   ========================================================= */
(() => {
  const DEPLOYED = "https://tdra-gov-api.onrender.com";
  const store = { get: k => { try { return localStorage.getItem(k) } catch { return null } }, set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v) } catch {} } };
  const params = new URLSearchParams(location.search);
  if (params.get("api")) store.set("almanara.api", params.get("api").replace(/\/+$/, ""));
  const local = ["localhost", "127.0.0.1", ""].includes(location.hostname);
  const API = (window.ALMANARA_API || store.get("almanara.api") || (local ? "http://localhost:8000" : DEPLOYED)).replace(/\/+$/, "");
  const TOKEN_KEY = "almanara.token:" + API;   /* one sign-in per backend: a local token is never sent to the deployed one */
  const session = { get token() { try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null } }, set token(v) { try { v ? sessionStorage.setItem(TOKEN_KEY, v) : sessionStorage.removeItem(TOKEN_KEY) } catch {} } };
  const live = { on: false, user: null, notes: [], loadedAt: null, evidenceItems: 0 };

  async function get(path) {
    const res = await fetch(API + path, { headers: session.token ? { Authorization: "Bearer " + session.token } : {} });
    if (res.status === 401) { session.token = null; throw new Error("Your sign-in has expired. Connect again."); }
    if (!res.ok) throw new Error(`${path} answered ${res.status}`);
    return res.json();
  }
  const day = iso => iso ? String(iso).slice(0, 10) : null;
  const pct = v => +(v * 100).toFixed(1);
  const html = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const words = s => String(s || "").replace(/_/g, " ");

  /* ---------- how the backend's vocabulary maps onto the prototype's ---------- */
  const TIER = { low: "low", medium: "medium", high: "high", critical: "high" };   /* the pages know three levels */
  /* which of the prototype's eight agents shows each backend check */
  const CHECK_AGENT = {
    data_residency: 2, sensitive_data_handling: 2, human_oversight: 2, transparency: 2, licence_terms: 2, vendor_lock_in: 2, update_practices: 2, cost: 2, exit_options: 2,
    task_accuracy: 4, hallucination: 4, english: 4, prompt_injection: 4, pii_leakage: 4, name_transliteration: 4,
    arabic_msa: 5, arabic_gulf: 5, fairness: 5, accessibility: 5, plain_language: 5, contestability: 5, critic_review: 5,
  };
  const CHECK_WHAT = {
    task_accuracy: "Does it do the job it is meant for correctly?", hallucination: "Does it state things that are not in its source?",
    english: "Quality of its English answers.", arabic_msa: "Quality of its Modern Standard Arabic answers.", arabic_gulf: "Does it understand and answer Gulf dialect?",
    name_transliteration: "Are Arabic and Latin spellings of a name matched correctly?", prompt_injection: "Testers try to make it break its own rules.",
    pii_leakage: "Can it be made to reveal someone else's personal data?", fairness: "The same case with one attribute changed gets the same treatment.",
    accessibility: "Works for People of Determination and people with low digital skills.", plain_language: "Answers are clear to a member of the public.",
    contestability: "People are told it is an AI and how to reach a human.", critic_review: "An independent critic argues against deploying it, on behalf of the people affected.",
    data_residency: "Where data is processed and whether the provider keeps it.", sensitive_data_handling: "Security controls for personal data.",
    human_oversight: "A person stays in control, in proportion to the risk.", transparency: "AI use is disclosed and the model is documented.",
    licence_terms: "The licence allows this use.", vendor_lock_in: "The model can be replaced without rebuilding the service.",
    update_practices: "The provider announces changes and the version can be pinned.", cost: "Running cost at the expected volume.", exit_options: "The department can leave the provider and take its data.",
  };
  const STANDARD_SOURCE = { data_residency: "Data protection", sensitive_data_handling: "Data protection", human_oversight: "AI governance", transparency: "AI governance" };
  const STAGE = { draft: 2, planned: 2, evaluating: 4, failed: 4, sent_back: 4, evaluated: 6, in_review: 7, awaiting_decision: 7 };
  const OPEN = Object.keys(STAGE);
  const TRIGGER = { new_model_version: "model", provider_terms_change: "terms", data_source_change: "data", autonomy_increase: "used", new_service_context: "used",
    incident: "incident", complaint_spike: "complaints", performance_drift: "drift", condition_breach: "breach", quarterly_standards_check: "quarterly", monitor_scan: "quarterly", exit_rule: "exit" };
  const NEXT = { pause: "Paused. Only the department's named approver can resume it, once the cause is dealt with.", reassess: "Sent back for reassessment. The approved version stays as it is until that is decided.", review: "A named person in the department needs to look at this." };

  /* additions to the prototype's lookup tables (new keys only; nothing existing is changed) */
  function extendTables() {
    Object.assign(STATUS, { failed: { label: "Failed", icon: "✕", cls: "bad" } });
    Object.assign(OUTCOME_CLS, { "Approved": "ok", "Blocked": "no", "Evaluation failed": "bad" });
    Object.assign(TRIGGERS, {
      drift: { name: "Performance drift", plain: "A measured score in live use fell below its threshold.", route: [4, 5] },
      breach: { name: "Condition broken", plain: "A condition the model was approved with is not being followed.", route: [2, 7] },
      quarterly: { name: "Standards check", plain: "The regular re-run of the compliance rules found something.", route: [2] },
      exit: { name: "Exit rule", plain: "A rule for pausing, replacing or retiring applies.", route: [7] },
    });
  }

  /* ---------- read everything ---------- */
  async function load() {
    const [depts, useCases, models, assessments, deployments, incidents, lessons, users, catalog, alerts, events] = await Promise.all([
      get("/departments"), get("/use-cases"), get("/models"), get("/registry/assessments"), get("/registry/deployments"), get("/registry/incidents"),
      get("/registry/lessons"), get("/users"), get("/catalog"), get("/alerts?status="), get("/lifecycle/events?limit=500")]);
    const [modelDetails, details] = await Promise.all([
      Promise.all(models.map(m => get("/models/" + m.slug))),
      Promise.all(assessments.slice(-80).map(a => get("/registry/assessments/" + a.id).catch(() => null)))]);
    const detail = Object.fromEntries(details.filter(Boolean).map(d => [d.id, d]));
    const liveDeps = deployments.filter(d => d.status !== "retired");
    const runs = Object.fromEntries(await Promise.all(liveDeps.map(d => get(`/assessments/${d.assessment_id}/test-runs`).then(r => [d.assessment_id, r]).catch(() => [d.assessment_id, []]))));
    return { depts, useCases, models, modelDetails, assessments, detail, deployments, incidents, lessons, users, catalog, alerts, events, runs };
  }

  /* ---------- turn it into the prototype's records ---------- */
  function build(b) {
    const notes = [];
    const title = Object.fromEntries(b.catalog.checks.map(c => [c.key, c.title]));
    const person = Object.fromEntries(b.users.map(u => [u.id, u]));
    const versionOf = {}, modelOfVersion = {};
    b.modelDetails.forEach(m => m.versions.forEach(v => { versionOf[v.id] = v; modelOfVersion[v.id] = m; }));
    const eventById = Object.fromEntries(b.events.map(e => [e.id, e]));
    const lessonByIncident = Object.fromEntries(b.lessons.filter(l => l.incident_id).map(l => [l.incident_id, l]));
    const ucById = Object.fromEntries(b.useCases.map(u => [u.id, u]));
    const byUc = {};
    b.assessments.forEach(a => (byUc[a.use_case_id] = byUc[a.use_case_id] || []).push(a));

    const depts = [], systems = [], allEvents = [];
    const deptIndex = {};
    b.depts.forEach(dp => {
      const approver = b.users.find(u => u.department_id === dp.id && u.can_approve);
      const dept = { code: dp.code, short: dp.name.split(/\s*(?:&|and)\s*/)[0].trim(), name: dp.name, systems: [], agents: [], _id: dp.id };
      b.useCases.filter(u => u.department_id === dp.id).forEach(uc => {
        const mine = (byUc[uc.id] || []).slice().sort((x, y) => x.id - y.id);
        const dep = b.deployments.filter(d => d.use_case_id === uc.id && d.status !== "retired").sort((x, y) => y.id - x.id)[0];
        const open = mine.filter(a => OPEN.includes(a.status)).pop();
        const base = dep ? b.detail[dep.assessment_id] : open ? b.detail[open.id] : null;
        if (!base) { notes.push(mine.length ? `${uc.title} (${dp.code}) has no live deployment or open assessment; its past assessments are in the Registry` : `${uc.title} (${dp.code}) has no assessment yet`); return; }
        const sy = system(dept, uc, base, dep, open, approver);
        dept.systems.push([sy.name, sy.tier, sy.stage, sy.model]);
        dept.agents.push(sy);
      });
      if (!dept.agents.length) { notes.push(`${dp.name} has nothing live or in progress and is not shown`); return; }
      deptIndex[dp.id] = depts.length;
      dept.agents.forEach((sy, k) => { sy.d = depts.length; sy.k = k; systems.push(sy); });
      depts.push(dept);
    });

    function system(dept, uc, base, dep, open, approver) {
      const version = versionOf[base.model_version_id] || base.model_version, model = modelOfVersion[base.model_version_id] || base.model;
      const tier = TIER[base.risk_tier] || "medium", lim0 = LIMITS[tier], stage = dep ? 8 : STAGE[base.status];
      const res = Object.fromEntries(base.check_results.map(r => [r.check_key, r]));
      const thr = k => res[k] && res[k].threshold != null ? res[k].threshold : uc.thresholds[k];
      const score = k => res[k] && res[k].score != null ? res[k].score : null;
      const plan = base.plan || {}, evidence = (base.summary || {}).evidence || {}, gaps = evidence.gaps || [];
      const lim = { acc: thr("task_accuracy") != null ? pct(thr("task_accuracy")) : lim0.acc, hal: thr("hallucination") != null ? +(100 - pct(thr("hallucination"))).toFixed(1) : lim0.hal, gap: lim0.gap, lat: lim0.lat };
      const lats = (b.runs[base.id] || []).map(r => r.latency_ms).filter(Boolean).sort((x, y) => x - y);
      const m = { acc: score("task_accuracy") != null ? pct(score("task_accuracy")) : lim.acc, hal: score("hallucination") != null ? +(100 - pct(score("hallucination"))).toFixed(1) : lim.hal,
        gap: score("english") != null && score("arabic_msa") != null ? +Math.abs(pct(score("english")) - pct(score("arabic_msa"))).toFixed(1) : 0,
        lat: lats.length ? +(lats[lats.length >> 1] / 1000).toFixed(1) : null };
      const reviews = base.reviews || [], round = Math.max(0, ...reviews.map(r => r.round)), current = reviews.filter(r => r.round === round);
      const decided = base.approval ? person[base.approval.approver_id] : null;
      const sy = {
        name: uc.title, tier, stage, seed: hashOf(dept.code + uc.title), reused: !!plan.source, lim, m, dept,
        model: `${model.name} ${version.version}`, modelName: model.name, unknowns: gaps.length,
        teams: current.map(r => words(r.reviewer_role)), approver: (decided || approver || { full_name: "Not named" }).full_name,
        num: base.id, id: base.reference, state: stage === 8 ? "live" : stage === 7 ? "signoff" : "checking",
        skipped: base.track === "fast" ? (plan.dropped_checks || []).length : 0,
        conditions: dep ? (dep.condition_status.length ? dep.condition_status : dep.conditions.map(c => ({ condition: c }))).map(c => ({ text: c.condition, ok: c.status !== "breached" })) : [],
        _uc: uc, _base: base, _dep: dep, _open: open,
      };

      /* the checks, from what the backend actually recorded */
      const running = base.status === "evaluating", tests = [];
      const add = (a, name, what, st, result, note = "") => tests.push({ a, name, what, st, result: html(result), note: html(note) });
      const decisive = (base.tier_rationale || []).filter(r => r.decisive).map(r => r.reason).join(" ");
      add(1, "Risk level set", "How much harm could this cause if it went wrong?", "checked", `${CAPITAL(base.risk_tier || tier)} risk, ${base.track} track. ${decisive}`);
      add(1, "Looked for an approved AI that already fits", "Avoids testing from scratch if another department already has evidence.", "checked",
        plan.source ? `${(plan.reuse || []).length} checks reused from ${plan.source.reference} (${plan.source.outcome} reuse). ${(plan.run || []).length} run fresh.` : "Nothing in the registry could be reused. Every check runs fresh.");
      const counts = evidence.counts || {};
      add(3, "Supplier's claims put in one standard format", "So every supplier can be compared fairly.", "checked", `${counts.verified || 0} verified, ${counts.claimed || 0} claimed, ${counts.unsupported || 0} unsupported, ${counts.missing || 0} missing`);
      add(3, "Missing supplier information flagged", "Anything the supplier didn't tell us counts as a risk.", "checked", gaps.length ? `${gaps.length} gap${gaps.length > 1 ? "s" : ""} recorded as risk` : "Nothing missing");
      (plan.required_checks || Object.keys(res)).forEach(key => {
        const a = CHECK_AGENT[key] || 4, r = res[key], name = title[key] || words(key), what = CHECK_WHAT[key] || "";
        if (!r) return add(a, name, what, running ? "review" : "todo", running ? `Agent ${a} is working on this now` : base.status === "failed" ? "Did not finish. The evaluation has to be run again." : "Not run yet");
        const note = (r.details || {}).note || "", marks = r.score != null && r.threshold != null ? `${pct(r.score)}% (needs ${pct(r.threshold)}%)` : "";
        const result = r.status === "passed" ? (marks || note || "Passed") : r.status === "warning" ? `Passes with conditions. ${marks || note}` : `${r.status === "error" ? "Could not be completed" : "Did not pass"}. ${marks || note}`;
        add(a, name, what, r.status === "failed" || r.status === "error" ? "failed" : "checked", result, r.source === "reused" ? `Evidence reused from ${(r.details || {}).reused_via || "an earlier assessment"}, not re-run here.` : "");
      });
      const rec = base.recommendation;
      add(6, "Results summarised in plain language", "The Assurance Package: results, limits, risks and conditions.", rec ? "checked" : "todo", rec ? `System recommendation: ${words(rec)}. A named person decides.` : "Starts when the checks finish");
      const answered = current.filter(r => r.status !== "pending").length;
      add(7, "Specialist reviewers looked at it", "Every reviewer needed for this risk level, at the same time.", !current.length ? "todo" : answered === current.length ? "checked" : "review",
        !current.length ? "Not sent for review yet" : `${answered} of ${current.length} reviewers have answered`);
      add(7, "A named person decided", "A real person accepts the remaining risk, never the AI.", base.approval ? "checked" : base.status === "awaiting_decision" ? "review" : "todo",
        base.approval ? `${CAPITAL(words(base.approval.decision))} by ${sy.approver}` : base.status === "awaiting_decision" ? `Waiting for ${sy.approver}` : "Follows the reviews");
      add(8, "Live monitoring switched on", "Agent 8 watches it for as long as it runs.", dep ? "checked" : "todo", dep ? `Watching ${sy.conditions.length} condition${sy.conditions.length === 1 ? "" : "s"}` : "Starts after approval");
      sy.tests = tests;
      sy.counts = { checked: 0, review: 0, todo: 0, failed: 0 };
      tests.forEach(t => sy.counts[t.st]++);

      /* what Agent 8 has reacted to: the alerts raised for this deployment */
      sy.events = [];
      if (dep) {
        b.alerts.filter(al => al.deployment_id === dep.id && al.action_required !== "info").sort((x, y) => y.id - x.id).forEach(al => {
          const src = eventById[al.event_id] || {}, key = TRIGGER[src.trigger_type] || "incident", incidentId = (src.payload || {}).incident_id;
          let status = al.status === "closed" ? "resolved" : al.action_required === "pause" ? "paused" : al.action_required === "reassess" ? (open ? "rechecking" : "attention") : "attention";
          if (status === "paused" && dep.status !== "paused") status = "attention";
          sy.events.push({ sys: sy.name, sy, trigger: key, t: TRIGGERS[key], date: day(al.created_at), status, at: 0, title: html(al.title), means: html(al.message),
            next: NEXT[al.action_required] || "", lesson: lessonByIncident[incidentId] ? html(lessonByIncident[incidentId].detail) : "" });
        });
        const openStates = sy.events.filter(e => e.status !== "resolved").map(e => e.status);
        if (dep.status === "paused" && !openStates.includes("paused"))
          sy.events.unshift({ sys: sy.name, sy, trigger: "exit", t: TRIGGERS.exit, date: day(dep.deployed_at), status: "paused", at: 0, title: "Paused", means: html(dep.status_reason), next: NEXT.pause, lesson: "" });
        else if (dep.status === "under_reassessment" && !openStates.length)
          sy.events.unshift({ sys: sy.name, sy, trigger: "exit", t: TRIGGERS.exit, date: day(dep.deployed_at), status: open ? "rechecking" : "attention", at: 0, title: "Sent back for reassessment", means: html(dep.status_reason), next: NEXT.reassess, lesson: "" });
        allEvents.push(...sy.events);
      }

      /* live readings: the tested figure unless the department has reported a measured one since */
      const observed = {};
      b.events.filter(e => dep && e.deployment_id === dep.id && e.trigger_type === "performance_drift").sort((x, y) => x.id - y.id).forEach(e => { observed[e.payload.check_key] = e.payload.observed; });
      sy.live = { ...m };
      if (observed.task_accuracy != null) sy.live.acc = pct(observed.task_accuracy);
      if (observed.hallucination != null) sy.live.hal = +(100 - pct(observed.hallucination)).toFixed(1);
      sy.trend = {};
      ["acc", "hal", "gap", "lat"].forEach(k => { sy.trend[k] = Array.from({ length: 8 }, (_, i) => i === 7 ? sy.live[k] : m[k]); });

      if (dep) {
        const all = model.versions.slice().sort((x, y) => y.id - x.id), latest = all.find(v => v.status === "current") || all[0];
        sy.version = { label: model.name, current: version.version, latest: latest.version, newer: latest.id !== version.id,
          history: all.map(v => ({ v: v.version, date: day(v.released_at), notes: html(v.changelog || (v.status === "current" ? "Current version." : `Status: ${v.status}.`)) })) };
      }
      return sy;
    }

    /* the standards table: the backend's compliance checks, per live deployment */
    const standards = b.catalog.checks.filter(c => c.agent === "compliance").map(c => ({ id: c.key, name: c.title, short: c.title, source: STANDARD_SOURCE[c.key] || "Procurement" }));
    const liveSystems = systems.filter(s => s.state === "live");
    liveSystems.forEach(s => {
      const res = Object.fromEntries(s._base.check_results.map(r => [r.check_key, r.status]));
      const word = st => st === "failed" || st === "error" ? "fail" : "pass";
      /* only the rules this deployment was actually checked against: a rule its risk level did not require is never shown as passed */
      s.standards = standards.filter(std => res[std.id]).map(std => {
        let now = word(res[std.id]);
        if (now === "pass" && s._dep.compliance_status !== "compliant" && res[std.id] === "warning") now = "review";   /* a conditional rule on a deployment that is at risk */
        return { ...std, last: word(res[std.id]), now };
      });
      s.passed = which => s.standards.filter(x => x[which] === "pass").length;
      deriveHealth(s);
    });

    /* the side-by-side table can only compare rules every live deployment was checked against */
    const shared = standards.filter(std => liveSystems.every(s => s.standards.some(x => x.id === std.id)));
    if (shared.length < standards.length) notes.push(`The Standards table compares the ${shared.length} rules every live deployment was checked against; ${standards.length - shared.length} more apply only at higher risk levels and are listed in each model's own report`);

    /* the assessment history: one record per backend assessment */
    const records = [];
    const OUT = { approved: ["Approved", "approved"], approved_with_conditions: ["Approved with conditions", "approved"], rejected: ["Not approved", "closed"], blocked: ["Blocked", "closed"],
      in_review: ["Waiting for sign-off", "progress"], awaiting_decision: ["Waiting for sign-off", "progress"], failed: ["Evaluation failed", "progress"] };
    b.assessments.forEach(a => {
      const uc = ucById[a.use_case_id]; if (!uc || deptIndex[a.department_id] == null) return;
      const d = b.detail[a.id], sy = systems.find(s => s._uc.id === uc.id), isBase = sy && sy._base.id === a.id;
      const dep = b.deployments.find(x => x.assessment_id === a.id);
      let [outcome, group] = OUT[a.status] || ["Being checked", "progress"];
      if (dep && dep.status === "retired") [outcome, group] = ["Retired", "closed"];
      const decidedStage = ["approved", "approved_with_conditions"].includes(a.status) ? 8 : ["rejected", "blocked"].includes(a.status) ? 0 : STAGE[a.status] || 2;
      const steps = decidedStage ? STEP_LABELS.map((label, i) => {
        const n = i + 1, state = decidedStage === 8 || n < decidedStage ? "done" : n === decidedStage || (decidedStage === 4 && n === 5) ? "now" : "later";
        return { label, state, date: state === "done" ? day(n <= 3 ? a.started_at : a.completed_at || a.started_at) : null };
      }) : [];
      const sum = a.summary || {}, rec = sum.recommendation && sum.recommendation.value;
      const summary = d && d.decision_record ? d.decision_record.plain_summary
        : sum.blocked_reason ? `Blocked. ${sum.blocked_reason}`
        : `${CAPITAL(a.risk_tier || "unrated")} risk, ${a.track || "no"} track.${rec ? ` System recommendation: ${words(rec)}.` : ""}${a.is_history ? " Seeded example history." : ""}`;
      const record = { key: a.reference, id: a.reference, sy: isBase ? sy : undefined, name: uc.title, d: deptIndex[a.department_id], tier: TIER[a.risk_tier] || "medium",
        kind: a.reassessment_of_deployment_id ? "Reassessment" : "First assessment", started: day(a.started_at), finished: day(a.completed_at), steps,
        outcome, group, summary: html(summary), evidence: d ? d.check_results.length : ((a.plan || {}).counts || {}).required || 0 };
      records.push(record);
      if (isBase) sy.first = record;
    });
    systems.forEach(s => { if (!s.first) { s.first = { key: s.id, id: s.id, sy: s, name: s.name, d: s.d, tier: s.tier, kind: "First assessment", started: day(s._base.started_at), finished: day(s._base.completed_at), steps: [], outcome: "Being checked", group: "progress", summary: "", evidence: s._base.check_results.length }; records.push(s.first); } });
    records.sort((x, y) => (y.finished || y.started) > (x.finished || x.started) ? 1 : -1);

    /* lessons already in the shared registry, shown with the events */
    b.lessons.forEach(l => {
      const inc = b.incidents.find(i => i.id === l.incident_id), dep = inc && b.deployments.find(x => x.id === inc.deployment_id);
      const sy = (dep && systems.find(s => s._uc.id === dep.use_case_id)) || systems.find(s => s.dept._id === l.department_id);
      if (!sy || allEvents.some(e => e.lesson === html(l.detail))) return;
      allEvents.push({ sys: sy.name, sy, trigger: "incident", t: TRIGGERS.incident, date: day(inc ? inc.occurred_at : l.created_at), status: "resolved", at: 0,
        title: html(inc ? inc.title : l.title), means: html(inc ? inc.description : ""), next: html(inc ? inc.resolution : ""), lesson: html(inc ? `${l.title}. ${l.detail}` : l.detail) });
    });
    allEvents.sort((x, y) => (y.date || "") > (x.date || "") ? 1 : -1);

    const approved = b.modelDetails.map(mo => {
      const users = liveSystems.filter(s => s.modelName === mo.name); if (!users.length) return null;
      const order = ["public", "internal", "personal", "sensitive_personal"], top = users.map(s => s._uc.data_sensitivity).sort((x, y) => order.indexOf(y) - order.indexOf(x))[0];
      const langs = [...new Set(users.flatMap(s => s._uc.languages))].map(l => ({ en: "English", "ar-msa": "Arabic", "ar-gulf": "Gulf dialect" }[l] || l));
      return { name: html(mo.name), maker: html(mo.provider), version: [...new Set(users.map(s => s.version.current))].join(", "), data: `Up to ${words(top)} data`, language: langs.join(", "),
        people: users.some(s => s._uc.audience_type === "citizen_facing") ? "The public and staff" : "Staff", ready: users.length > 1, users, depts: [...new Set(users.map(s => s.dept.short))] };
    }).filter(Boolean);

    const evidenceItems = Object.values(b.detail).reduce((n, d) => n + d.check_results.length, 0)
      + b.modelDetails.reduce((n, mo) => n + mo.versions.reduce((k, v) => k + v.evidence.filter(e => e.status !== "missing").length, 0), 0);
    return { depts, entities: b.depts.map(d => d.name), systems, liveSystems, records, events: allEvents, approved, standards: shared, evidenceItems, notes, hasLatency: liveSystems.length > 0 && liveSystems.every(s => s.m.lat != null) };
  }

  /* ---------- put the records in place and redraw ---------- */
  const fill = (target, items) => { target.length = 0; target.push(...items); };
  let wrapped = false;
  function apply(r) {
    extendTables();
    fill(DEPTS, r.depts); fill(ENTITIES, r.entities); fill(SYSTEMS, r.systems); fill(LIVE, r.liveSystems);
    fill(ASSESSMENTS, r.records); fill(EVENTS, r.events); fill(APPROVED_MODELS, r.approved); fill(UAE_STANDARDS, r.standards);
    if (!r.hasLatency) { const i = MEASURES.findIndex(x => x.k === "lat"); if (i >= 0) MEASURES.splice(i, 1); r.systems.forEach(s => { s.m.lat = s.live.lat = 0; s.trend.lat = Array(8).fill(0); }); }
    AGENTS.forEach((a, i) => { const n = r.systems.filter(s => s.stage === i + 1).length; a.load = i === 7 ? `${r.liveSystems.length} systems watched` : i === 6 ? `${n} awaiting humans` : `${n} with this agent`; });
    Object.assign(dView, { d: 0, s: 0, filter: "all" }); Object.assign(regView, { q: "", dept: "", tier: "", group: "", open: null }); Object.assign(monView, { open: null, dept: "", status: "", q: "" });

    if (!wrapped) {
      wrapped = true;
      /* Registry: the prototype counts one wording of "approved" and a fixed evidence total */
      const drawRegistry = renderRegistry;
      renderRegistry = PAGE_HOOKS.registry = function () {
        drawRegistry();
        const cards = $$("#p-registry .m-stats .card b");
        if (cards[1]) cards[1].textContent = ASSESSMENTS.filter(a => a.outcome.startsWith("Approved")).length;
        if (cards[3]) cards[3].textContent = live.evidenceItems.toLocaleString("en-GB");
      };
      /* Monitor: the value figures stay the prototype's sample model; say so where they show */
      const drawMonitorBody = renderMonitorBody;
      renderMonitorBody = function () { drawMonitorBody(); const n = $("#monValNote"); if (n) n.textContent += " · sample figures"; };
      /* Pause and Re-check are not sent to the backend in this read-only connection */
      monitorAction = function () { toast("This connection is read-only. Pausing and re-checks are done in the backend by the department's named people."); };
    }
    live.evidenceItems = r.evidenceItems;
    drawOverview(r);
    if (typeof showAgent === "function") { const keep = hero.focus; showAgent(Math.max(0, keep)); hero.focus = keep; }
    const sel = $("#fEntity"); if (sel) sel.innerHTML = `<option value="">Select entity…</option>${ENTITIES.map(e => `<option>${html(e)}</option>`).join("")}`;
    if (!$("#liveNewNote")) { const n = document.createElement("p"); n.id = "liveNewNote"; n.className = "hint"; n.style.margin = "0 0 14px";
      n.textContent = "Prototype simulation: a use case built here, its risk tier and its agent pipeline are not yet saved to or run by the registry."; const at = $("#v-define"); at.parentNode.insertBefore(n, at); }
    if (currentPage !== "overview" && currentPage !== "new" && PAGE_HOOKS[currentPage]) { PAGE_HOOKS[currentPage](); syncRoute(); }
  }

  function drawOverview(r) {
    $("#dIndex").innerHTML = DEPTS.map((d, i) => `<button data-d="${i}" data-i="${i}"><span>${html(d.short)}</span><em style="margin-left:${i * 7}px">${String(i + 1).padStart(2, "0")}</em></button>`).join("");
    $("#gCount").textContent = `${DEPTS.length} departments · ${SYSTEMS.length} agentic systems`;
    const big = document.querySelector("#p-overview .stack .card:nth-child(2) div[style*='font-size:30px']");
    if (big) big.firstChild.textContent = r.evidenceItems.toLocaleString("en-GB") + " ";
    const recent = ASSESSMENTS.filter(a => a.sy).slice(0, 6);
    $("#rows").innerHTML = recent.map(a => { const s = a.sy;
      return `<button class="trow" data-d="${s.d}" data-s="${s.k}" aria-label="Open ${html(a.name)} in Departments"><span class="mono">${a.id}</span><span>${html(a.name)}</span><small>${html(s.dept.name)}</small>
        <span><span class="tier ${a.tier}">${CAPITAL(a.tier)}</span></span>
        <span class="stages">${AGENTS.map((_, i) => `<i class="${s.stage === 8 || i < s.stage - 1 ? "d" : i === s.stage - 1 ? "c" : ""}"></i>`).join("")}</span><small>${a.outcome}</small></button>`; }).join("");
    const awaiting = SYSTEMS.filter(s => s.state === "signoff");
    $("#signoffCount").textContent = String(awaiting.length).padStart(2, "0");
    $("#signoffList").innerHTML = awaiting.length ? awaiting.map(s => `<button data-d="${s.d}" data-s="${s.k}"><b>${html(s.name)}</b><small>${html(s.dept.short)} · ${s.teams.length} reviewers · decision belongs to ${html(s.approver)}</small><span class="tier ${s.tier}">${CAPITAL(s.tier)}</span></button>`).join("")
      : `<p style="color:var(--mute);font-size:12.5px;margin:14px 0 0">Nothing is waiting for a decision.</p>`;
    /* the network graph lays itself out when its canvas changes size: nudge it so it rebuilds from the new departments */
    const cv = $("#heroCanvas"), was = cv.style.width;
    cv.style.width = "calc(100% - 2px)";
    requestAnimationFrame(() => requestAnimationFrame(() => { cv.style.width = was; }));
  }

  /* ---------- the small connection control in the header ---------- */
  let chip, panel, toastEl;
  function toast(text) {
    if (!toastEl) { toastEl = document.createElement("div"); toastEl.setAttribute("role", "status");
      toastEl.style.cssText = "position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:9999;max-width:min(560px,90vw);padding:12px 18px;border-radius:12px;background:#262626;color:#fff;font-size:13px;line-height:1.45;box-shadow:0 8px 30px rgba(0,0,0,.25)";
      document.body.appendChild(toastEl); }
    toastEl.textContent = text; toastEl.style.display = "block"; clearTimeout(toast.t); toast.t = setTimeout(() => { toastEl.style.display = "none"; }, 5200);
  }
  function setChip(text, state) {
    chip.innerHTML = `<i style="display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:7px;background:${state === "live" ? "#21633e" : state === "busy" ? "#c58a2a" : state === "error" ? "#b3402e" : "#9a9a9a"}"></i>${html(text)}`;
  }
  async function openPanel() {
    panel.style.display = "block";
    const signedIn = live.on;
    panel.innerHTML = `<div style="font-weight:600;margin-bottom:4px">${signedIn ? "Live data" : "Connect to the registry"}</div>
      <p style="margin:0 0 10px;color:var(--mute);font-size:12px;line-height:1.5">${signedIn ? `Signed in as ${html(live.user.full_name)}, ${html(live.user.title)}. Read-only. Loaded ${live.loadedAt}.` : "The page is showing its own sample data. Choose a seeded person to load the registry's real records (read-only; the data is synthetic, so there are no passwords)."}</p>
      <div id="livePanelBody" style="font-size:12px;color:var(--mute)">${signedIn ? "" : "Looking for the backend…"}</div>
      ${signedIn && live.notes.length ? `<details style="margin:8px 0;font-size:12px;color:var(--mute)"><summary>${live.notes.length} thing${live.notes.length > 1 ? "s" : ""} not shown</summary><ul style="margin:6px 0 0;padding-left:16px">${live.notes.map(n => `<li>${html(n)}</li>`).join("")}</ul></details>` : ""}
      <p style="margin:10px 0 0;font-size:11px;color:var(--mute);word-break:break-all">Backend: ${html(API)}</p>
      ${signedIn ? `<div style="display:flex;gap:8px;margin-top:10px"><button class="pill solid" id="liveRefresh">Refresh</button><button class="pill" id="liveOff">Back to sample data</button></div>` : ""}`;
    if (signedIn) { $("#liveRefresh").onclick = () => connect(); $("#liveOff").onclick = () => { session.token = null; location.reload(); }; return; }
    try {
      /* the list of people is the only thing the backend gives out before sign-in, so group them by their email's organisation */
      const users = await get("/auth/users"), groups = {};
      const org = u => ((u.email.split("@")[1] || "").split(".")[0] || "registry").toUpperCase();
      users.forEach(u => (groups[org(u)] = groups[org(u)] || []).push(u));
      $("#livePanelBody").innerHTML = `<select class="select" id="liveUser" aria-label="Sign in as" style="width:100%">${Object.entries(groups).map(([g, list]) => `<optgroup label="${html(g)}">${list.map(u => `<option value="${html(u.email)}">${html(u.full_name)} · ${html(u.title)}</option>`).join("")}</optgroup>`).join("")}</select>
        <button class="pill solid" id="liveGo" style="margin-top:10px">Connect</button>`;
      $("#liveGo").onclick = () => connect($("#liveUser").value);
    } catch (e) {
      $("#livePanelBody").innerHTML = `<span style="color:#b3402e">The backend did not answer.</span> If it is the hosted one it may be waking up (up to a minute); try again. If it is local, start it on port 8000 and make sure this page's address is in its CORS_ORIGINS.`;
    }
  }
  async function connect(email) {
    try {
      setChip("Connecting…", "busy");
      if (email) { const res = await fetch(API + "/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
        if (!res.ok) throw new Error("Sign-in was refused"); session.token = (await res.json()).access_token; }
      live.user = await get("/auth/me");
      const records = build(await load());
      if (!records.systems.length) throw new Error("The registry has no assessed use cases to show yet");
      live.notes = records.notes; live.on = true; live.loadedAt = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
      apply(records);
      const who = document.querySelector(".topright .user");
      if (who) { who.children[0].textContent = live.user.full_name; who.children[1].textContent = live.user.full_name.split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase(); }
      setChip("Live data", "live"); panel.style.display = "none";
    } catch (e) {
      console.error("[live data]", e);
      setChip(live.on ? "Live data" : "Sample data", live.on ? "live" : "error"); toast(`Could not load live data: ${e.message}. ${live.on ? "Showing the last loaded data." : "Still showing sample data."}`);
    }
  }
  function mount() {
    const right = document.querySelector(".topright"); if (!right) return;
    const wrap = document.createElement("div"); wrap.style.cssText = "position:relative";
    chip = document.createElement("button"); chip.className = "pill"; chip.id = "liveChip"; chip.setAttribute("aria-haspopup", "dialog"); chip.style.cssText = "white-space:nowrap";
    panel = document.createElement("div"); panel.className = "card"; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "Data connection");
    panel.style.cssText = "display:none;position:absolute;right:0;top:calc(100% + 10px);width:330px;z-index:900;padding:16px;text-align:left;box-shadow:0 12px 40px rgba(0,0,0,.14)";
    wrap.append(chip, panel); right.insertBefore(wrap, right.querySelector(".user"));
    setChip("Sample data", "off");
    chip.onclick = () => panel.style.display === "block" ? (panel.style.display = "none") : openPanel();
    document.addEventListener("click", e => { if (!wrap.contains(e.target)) panel.style.display = "none"; });
    if (params.get("sample") === "1") return;
    if (session.token) connect();   /* already signed in on this tab: go straight to live data */
  }
  mount();
})();
