/* =========================================================
   AGENT PIPELINE (front-end simulation)
   Runs on the normal page. The working agent's orb sits on the
   left; a line reaches out to each item as it is being checked.
   When the agent finishes, a line runs from its orb to the next
   orb, and the next orb glides along it into the left position.
   The activity log and Approval & Accountability appear only at
   the end, with the whole pipeline.
   ========================================================= */
const RUN_GLIDE = 1200;       /* ms for an orb to glide into the left position */
const RUN_BEAT = 800;         /* ms each item spends being checked */
const RUN_FLAG_HOLD = 900;    /* ms to pause on an item that needs attention */
const RUN_ICON = 190;         /* px diameter of the working agent's icon: 5cm at the browser's 96px per inch */
let pipelineRun = 0;

/* ---------- the on-page run: orbs, lines and checklists ---------- */
function openRun(wait) {
  const run = $("#run"), svg = run.querySelector("svg"), NS = "http://www.w3.org/2000/svg";
  const EASE = "cubic-bezier(.45,.05,.25,1)";
  let lanes = [];

  function geo(i, total) {
    const W = run.clientWidth, H = run.clientHeight, narrow = W < 640;
    const size = narrow ? 84 : RUN_ICON, r = size / 2; /* 5cm leaves no room for the checklist on a phone */
    const cx = Math.max(r + 12, narrow ? 56 : 110), cy = H * (total > 1 ? (i ? .71 : .21) : .44);
    return { W, H, size, r, cx, cy, listX: cx + r + (narrow ? 24 : 96), rowH: narrow ? 36 : 38, nextX: W - r - (narrow ? 4 : 40) };
  }
  const at = (x, g) => `translate(${x - g.r}px,${g.cy - g.r}px)`;
  function addPath(cls, d) {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("class", cls); p.setAttribute("d", d); p.setAttribute("pathLength", "1");
    svg.appendChild(p); p.getBoundingClientRect(); /* lets the line draw itself in */
    p.classList.add("in");
    return p;
  }
  const curve = (ax, ay, bx, by) => { const m = Math.max(30, (bx - ax) * .5); return `M${ax} ${ay}C${ax + m} ${ay} ${bx - m} ${by} ${bx} ${by}`; };
  function rowPath(l, row) {
    const y = l.g.cy - (l.total - 1) * l.g.rowH / 2 + row.i * l.g.rowH, a = Math.atan2(y - l.g.cy, l.g.listX - l.g.cx) * .75;
    return curve(l.g.cx + Math.cos(a) * (l.g.r + 4), l.g.cy + Math.sin(a) * (l.g.r + 4), l.g.listX - 8, y);
  }
  function placeList(l) {
    l.list.style.left = l.g.listX + "px";
    l.list.style.top = (l.g.cy - l.total * l.g.rowH / 2) + "px";
    l.list.style.setProperty("--row", l.g.rowH + "px");
  }
  addEventListener("resize", relayout);
  function relayout() {
    if (!run.isConnected) return removeEventListener("resize", relayout);
    lanes.forEach(l => {
      l.g = geo(l.i, l.keys);
      l.el.style.width = l.el.style.height = l.g.size + "px";
      l.el.style.transform = at(l.g.cx, l.g);
      placeList(l);
      l.rows.forEach(row => row.path.setAttribute("d", rowPath(l, row)));
    });
  }
  function makeLane(key, i, keys, total) {
    const a = AGENTS[key], g = geo(i, keys), el = document.createElement("div");
    el.className = "ra"; el.style.width = el.style.height = g.size + "px";
    el.innerHTML = `${lineIcon(a, "working")}<div class="ra-text"><span>Agent ${a.n} of 8</span><b>${a.short}</b></div>`;
    const list = document.createElement("div");
    list.className = "chk-list"; list.setAttribute("aria-live", "polite");
    const l = { key, i, keys, total, g, el, list, rows: [] };
    placeList(l);
    return l;
  }

  return {
    /* glide the next agent(s) into the left position, linked from the previous one */
    async enter(items) {
      const olds = lanes, nexts = items.map(({ key, total }, i) => makeLane(key, i, items.length, total));
      const links = [];
      if (olds.length) {
        olds.forEach(l => { l.list.classList.add("gone"); l.rows.forEach(r => r.path.classList.add("gone")); });
        await wait(380);
        olds.forEach(l => { l.list.remove(); l.rows.forEach(r => r.path.remove()); });
      }
      nexts.forEach(l => {
        l.el.style.transform = at(l.g.nextX, l.g);
        run.appendChild(l.el);
        l.el.animate([{ transform: `translate(${l.g.nextX - l.g.r + 60}px,${l.g.cy - l.g.r}px)`, opacity: 0 }, { transform: at(l.g.nextX, l.g), opacity: 1 }], { duration: 650, easing: EASE });
      });
      if (olds.length) {
        await wait(260);
        olds.forEach(o => nexts.forEach(n => links.push(addPath("link", curve(o.g.cx + o.g.r + 4, o.g.cy, n.g.nextX - n.g.r - 6, n.g.cy)))));
        await wait(850);
        olds.forEach(l => l.el.querySelector(".lic").classList.remove("working"));
      } else await wait(500);
      olds.forEach(l => l.el.animate([{ transform: at(l.g.cx, l.g), opacity: 1 }, { transform: at(-l.g.size, l.g), opacity: 0 }], { duration: RUN_GLIDE, easing: EASE, fill: "forwards" }));
      links.forEach(p => p.classList.add("retract"));
      nexts.forEach(l => { l.el.animate([{ transform: at(l.g.nextX, l.g) }, { transform: at(l.g.cx, l.g) }], { duration: RUN_GLIDE, easing: EASE }); l.el.style.transform = at(l.g.cx, l.g); });
      await wait(RUN_GLIDE);
      olds.forEach(l => l.el.remove());
      links.forEach(p => p.remove());
      nexts.forEach(l => run.appendChild(l.list));
      lanes = nexts;
      return nexts;
    },
    row(l, label) {
      const el = document.createElement("div");
      el.className = "chk run";
      el.innerHTML = `<i aria-hidden="true"></i><b>${label}</b><span>being checked</span>`;
      l.list.appendChild(el);
      const row = { i: l.rows.length, el };
      row.path = addPath("ln on", rowPath(l, row));
      l.rows.push(row);
      return (cls, text) => { el.className = `chk ${cls}`; el.querySelector("span").textContent = text; row.path.classList.remove("on"); };
    },
    settle(key) { lanes.filter(l => l.key === key).forEach(l => { const ic = l.el.querySelector(".lic"); ic.classList.remove("working"); ic.classList.add("done"); }); },
    async close() { await run.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 450, easing: "ease-in-out", fill: "forwards" }).finished; removeEventListener("resize", relayout); run.remove(); },
  };
}

function runPipeline() {
  const me = ++pipelineRun, A = AGENTS, RISK = `${cap(card.tier)} risk`;
  const DEPLOY = { n: "D", short: "Deploy with conditions" };
  const who = k => k === "D" ? DEPLOY : A[k];

  $("#v-pipeline").innerHTML = `<div class="pipe-run" id="run"><svg aria-hidden="true"></svg></div><div id="finale"></div>`;
  step(3);

  /* A newer run replaces this one, so this one stops quietly. */
  const wait = ms => new Promise((ok, stop) => setTimeout(() => me === pipelineRun ? ok() : stop(new Error("replaced")), reduce ? 0 : ms));
  const stage = reduce ? null : openRun(wait);

  /* ---------- the record: every step is kept for the activity panel at the end ---------- */
  const entries = [], nodeState = {}, concerns = [];
  let refreshLog = () => {};
  const log = (name, msg, cls = "") => {
    /* "Agents 4+5" belongs to both; deployment belongs to the approver and the monitor. */
    const tags = name === "Deploy" ? [6, 7] : name.match(/\d/g).map(n => +n - 1);
    entries.push({ who: name, msg, cls, tags, time: new Date().toTimeString().slice(0, 8) });
    refreshLog();
  };

  /* ---------- the end: the whole pipeline, the activity and the approval panel ---------- */
  const concernsHTML = () => concerns.length ? `<div class="eyebrow" style="margin-top:14px">Problems raised · ${concerns.length}</div><ul class="concerns">${concerns.map(c => `<li>${lineIcon(A[c.i])}<span><b>Agent ${A[c.i].n} · ${A[c.i].short}</b>${c.msg}</span></li>`).join("")}</ul>` : "";
  function finale() {
    nodeState[6] = { ...nodeState[6], cls: "wait", txt: "awaiting human" };
    nodeState.D = { cls: "later", txt: "after sign-off" };
    nodeState[7] = { cls: "later", txt: "after sign-off" };
    const nodeHTML = k => {
      const a = who(k), s = nodeState[k], orb = lineIcon(a);
      return `<div class="node ${s.cls}${s.flagged ? " flagged" : ""}" id="n${k}">${k === "D" ? `<div class="o">${orb}</div>` : `<button class="o" data-agent="${k}" aria-label="Show only Agent ${a.n}, ${a.short}">${orb}</button>`}<b>${a.short}</b><small>${s.txt}</small></div>`;
    };
    const wire = `<div class="wire"><i></i></div>`;
    $("#finale").innerHTML = `<div class="flow">${nodeHTML(0)}${wire}${nodeHTML(1)}${wire}${nodeHTML(2)}${wire}<div class="par on">${nodeHTML(3)}${nodeHTML(4)}</div>${wire}${nodeHTML(5)}${wire}${nodeHTML(6)}${wire}${nodeHTML("D")}${wire}${nodeHTML(7)}</div>
      <div class="pl">
        <div class="card activity ${card.tier}"><div class="eyebrow">All activity · ${card.id} · ${RISK}</div><div class="afilter" id="afilter" role="group" aria-label="Choose whose activity to show"></div><div class="log" id="finalLog"></div></div>
        <div class="card approve" id="approve">
          <div class="eyebrow">Approval & accountability</div>
          ${concernsHTML()}
          <div style="margin-top:10px">${card.reviewers.map((r, i) => `<div class="row"><span>${r}</span><span class="st ${i < card.reviewers.length - 1 ? "k" : "p"}">${i < card.reviewers.length - 1 ? "cleared" : "1 concern open"}</span></div>`).join("")}</div>
          <div class="eyebrow" style="margin-top:18px">Deployment conditions</div>
          <ul class="conds"><li>Only for ${lc(card.purpose[0])}</li><li>${card.oversight === "None" ? "Human review of a 10% sample" : "Human review when confidence is low"}</li><li>No access to personal data beyond the task</li><li>Tell users that AI is used, and offer a way to appeal</li></ul>
          <div class="eyebrow" style="margin-top:18px">Named approver · accepts residual risk</div>
          <div style="display:flex;gap:8px;margin-top:10px"><select class="select" id="approver" style="flex:1"><option value="">Select approver…</option><option>M. Al Mansoori — Director, Digital Services</option><option>S. Al Hashimi — CIO</option><option>R. Khoury — Head of Data Governance</option></select></div>
          <div style="display:flex;gap:8px;margin-top:10px"><button class="pill" id="sendBack" style="flex:1;justify-content:center">Send back</button><button class="pill solid" id="approveBtn" style="flex:1.4;justify-content:center" disabled>Approve & record</button></div>
        </div>
      </div>`;

    /* activity: everything together, or one agent at a time */
    let view = "all";
    const row = e => `<div><time>${e.time}</time><span class="who">${e.who}</span><span class="${e.cls}">${e.msg}</span></div>`;
    refreshLog = () => {
      const count = t => entries.filter(e => e.tags.includes(t)).length;
      $("#afilter").innerHTML = `<button data-agent="all" class="${view === "all" ? "on" : ""}" aria-pressed="${view === "all"}">All activity<em>${entries.length}</em></button>` +
        A.map((a, i) => `<button data-agent="${i}" class="${view === String(i) ? "on" : ""}" aria-pressed="${view === String(i)}" ${count(i) ? "" : "disabled"}>${lineIcon(a)}${a.n} ${a.short}<em>${count(i)}</em></button>`).join("");
      $("#finalLog").innerHTML = entries.filter(e => view === "all" || e.tags.includes(+view)).map(row).join("");
      $$("#finale .node").forEach(n => n.classList.toggle("picked", n.id === "n" + view));
    };
    refreshLog();
    $("#v-pipeline").onclick = e => { const b = e.target.closest("[data-agent]"); if (b) { view = view === b.dataset.agent ? "all" : b.dataset.agent; refreshLog(); } };

    /* sign-off: Deployment and Monitor can only follow a named person's approval */
    const flow = $("#finale .flow"), wires = [...flow.querySelectorAll(".wire")];
    const setNode = (k, cls, txt) => {
      const n = $("#n" + k), wasPicked = n.classList.contains("picked"), flagged = n.classList.contains("flagged");
      n.className = `node ${cls}${flagged ? " flagged" : ""}${wasPicked ? " picked" : ""}`;
      n.querySelector("small").textContent = txt;
    };
    $("#approver").onchange = e => $("#approveBtn").disabled = !e.target.value;
    $("#sendBack").onclick = () => { log("Agent 7", "Sent back to Agent 5 · fix the appeal route wording", "warn"); setNode(6, "wait", "returned"); };
    $("#approveBtn").onclick = () => {
      const approver = $("#approver").value.split(" — ")[0];
      $("#approveBtn").disabled = true; $("#sendBack").disabled = true; $("#approver").disabled = true;
      log("Agent 7", `Approved by ${approver} · residual risk accepted and recorded`, "ok");
      setNode(6, "done", "approved"); wires[5].classList.add("on");
      setTimeout(() => { setNode("D", "done", "live"); log("Deploy", "Live with 4 conditions · these are now monitored by Agent 8", "ok"); wires[6].classList.add("on"); }, 900);
      setTimeout(() => { setNode(7, "run", "watching"); log("Agent 8", "Watching: model updates, terms changes, data drift, complaints · standards check every quarter", "ok"); }, 1800);
    };

    wires.forEach((x, i) => { if (i < 5) setTimeout(() => x.classList.add("on"), reduce ? 0 : 1100 + i * 130); });
    if (reduce) return;
    const order = [...flow.querySelectorAll(".node")];
    flow.classList.add("sliding");
    order.forEach((n, i) => n.animate([{ transform: `translateX(${innerWidth * .5}px)`, opacity: 0 }, { transform: "none", opacity: 1 }], { duration: 1300, delay: 100 + i * 110, easing: "cubic-bezier(.22,.8,.3,1)", fill: "backwards" }));
    setTimeout(() => flow.classList.remove("sliding"), 1500 + order.length * 110);
    $("#finale .pl").animate([{ opacity: 0, transform: "translateY(16px)" }, { opacity: 1, transform: "none" }], { duration: 800, delay: 700, easing: "ease-out", fill: "backwards" });
    if (concerns.length) { const ap = $("#approve"); setTimeout(() => ap.classList.add("pointed"), 1700); setTimeout(() => ap.classList.remove("pointed"), 5000); }
  }

  /* ---------- what each agent checks: one line out of the orb per item ---------- */
  const fast = card.tier === "low", reuse = card.purpose.includes("Answer citizen FAQs");
  const unk = card.model ? card.model.unknowns.length : 2, noModel = !reuse && !card.model;
  const tests = fast ? 9 : 26, controls = fast ? 18 : 34, attacks = fast ? 40 : 120;
  const hal = "1.1", gap = "3.4"; /* simulated test results */
  const PLAN = [
    { keys: [0], checks: { 0: [
      { label: "Data and authority", msg: "Use-Case Card received · reading data, authority and consequences of errors" },
      { label: "Risk tier", msg: `Tier confirmed: ${card.tier.toUpperCase()} → ${TIERINFO[card.tier].lane.toLowerCase()}`, cls: "ok" },
      { label: "Shared registry", msg: "Checked the shared registry for an approved model in the same context" },
      { label: "Model to evaluate", msg: reuse ? "Registry match: Tawasul FAQ Assistant v2.1 (84% context match). Reusing its evidence and re-testing only the differences." : card.model ? `No registry match · using the candidate model from ${card.model.provider}` : "No registry match · a model API is needed for evaluation", cls: reuse ? "ok" : "warn", flag: noModel && "No approved model fits and none was supplied. A model is needed for evaluation." },
    ] } },
    { keys: [1], checks: { 1: [
      { label: "UAE AI framework", msg: "Mapped the UAE AI framework to evidence" },
      { label: "Data-protection rules", msg: "Checked data-protection rules against the Use-Case Card" },
      { label: "Evidence for every control", msg: `${controls}/${controls} controls mapped to evidence`, cls: "ok" },
    ] } },
    { keys: [2], checks: { 2: [
      { label: "Provider benchmarks and terms", msg: "Put provider benchmarks, licences and terms into the standard format" },
      { label: "Similar past assessments", msg: "Looked for similar past assessments to reuse" },
      { label: "Tests for this use case", msg: `${tests} tests generated from the card`, cls: "ok" },
      { label: "Missing provider information", msg: `${unk} provider unknown${unk === 1 ? "" : "s"} flagged as risk`, cls: unk ? "warn" : "ok", flag: unk && `The provider left ${unk} item${unk === 1 ? "" : "s"} unanswered, and unknown information counts as risk.` },
    ] } },
    { keys: [3, 4], open: ["Agents 4+5", "Running in parallel on synthetic and masked data only"], checks: {
      3: [
        { label: "Accuracy and speed", msg: "Accuracy and speed compared with the benchmarks ✓" },
        { label: "Data hallucination", msg: `Hallucination ${hal}% ✓`, cls: "ok" },
        { label: "Prompt injection", msg: `Prompt injection: 0 of ${attacks} attempts succeeded ✓`, cls: "ok" },
        { label: "Data leakage", msg: "No data leakage found ✓", cls: "ok" },
        { label: "Supplier dependency", msg: "Supplier dependency checked: licence, data residency, exit plan ✓", cls: "ok" },
      ],
      4: [
        { label: "Arabic scenarios", msg: `Arabic scenarios ✓ · AR–EN gap ${gap}%` },
        { label: "Fairness across groups", msg: "Fairness across groups ✓" },
        { label: "Accessibility", msg: "Accessibility and screen reader ✓" },
        { label: "Frontline staff feedback", msg: "Frontline staff feedback collected" },
        { label: "Appeal route", msg: "Appeal route needs clearer wording", cls: "warn", flag: "People may not be able to find how to appeal. The wording needs to be clearer." },
      ],
    } },
    { keys: [5], checks: { 5: [
      { label: "Combining all results", msg: "Combined the results from Agents 2–5" },
      { label: "Limits and risks", msg: "Wrote up the results, limits and risks in plain language" },
      { label: "Deployment conditions", msg: "Deployment conditions drafted" },
      { label: "Recommendation", msg: "Assurance Package ready · recommendation: APPROVE WITH CONDITIONS", cls: "ok" },
    ] } },
    { keys: [6], checks: { 6: [
      { label: "Reviewers notified", msg: `Package sent to ${card.reviewers.length} reviewers at the same time · waiting for a named approver`, cls: "warn" },
      { label: "Named approver", waiting: true },
    ] } },
  ];

  async function runLane(lane, key, list, delay) {
    await wait(delay);
    for (const item of list) {
      const finishRow = stage ? stage.row(lane, item.label) : () => {};
      await wait(RUN_BEAT);
      if (item.msg) log(`Agent ${key + 1}`, item.msg, item.cls || "");
      if (item.flag) {
        concerns.push({ i: key, msg: item.flag });
        nodeState[key].flagged = true;
        finishRow("issue", "needs attention");
        await wait(RUN_FLAG_HOLD);
      } else if (item.waiting) finishRow("waiting", "waiting for a person");
      else finishRow("ok", "checked");
    }
    nodeState[key] = { ...nodeState[key], cls: "done", txt: nodeState[key].flagged ? "problem found" : "done" };
    if (stage) stage.settle(key);
  }

  (async () => {
    for (const s of PLAN) {
      s.keys.forEach(k => { nodeState[k] = { cls: "run", txt: "running" }; });
      const lanes = stage ? await stage.enter(s.keys.map(key => ({ key, total: s.checks[key].length }))) : s.keys.map(() => null);
      if (s.open) log(s.open[0], s.open[1]);
      await Promise.all(s.keys.map((key, i) => runLane(lanes[i], key, s.checks[key], i * 340)));
      await wait(500);
    }
    if (stage) await stage.close(); else $("#run").remove();
    finale();
  })().catch(() => {});
}
