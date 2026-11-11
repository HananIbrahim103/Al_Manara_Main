/* =========================================================
   USE-CASE LAB
   ========================================================= */
function buildLab(){
  const el=$("#m-lab");
  el.innerHTML=LAB.map((s,i)=>{
    const n=String(i+1).padStart(2,"0");let body="";
    if(s.type==="multi"||s.type==="single") body=`<div class="chips">${s.opts.map(o=>`<button class="chip" data-f="${s.id}" data-v="${o.v}" aria-pressed="false">${o.v}${o.d?` <span class="w">${o.d}</span>`:""}</button>`).join("")}</div>`;
    if(s.type==="scale") body=`<div class="scale">${s.opts.map(o=>`<button class="chip" data-f="${s.id}" data-v="${o.v}" aria-pressed="false"><b style="font-weight:500">${o.v}</b><small>${o.d}</small></button>`).join("")}</div>`;
    if(s.type==="entity") body=`<div class="field"><select class="select" id="fEntity" style="flex:1.4"><option value="">Select entity…</option>${ENTITIES.map(e=>`<option>${e}</option>`).join("")}</select><input class="input" id="fOwner" placeholder="Business owner (named person)" style="flex:1"></div>`;
    if(s.type==="thresholds") body=`<div class="sliders">${THR.map(t=>`<div class="sl"><label for="t-${t.id}">${t.label}<b id="tv-${t.id}">${t.def}${t.u}</b></label><input type="range" id="t-${t.id}" min="${t.min}" max="${t.max}" value="${t.def}" data-t="${t.id}"></div>`).join("")}</div>`;
    if(s.type==="model") body=`<div class="field"><select class="select" id="fProv" style="flex:1"><option value="">Provider…</option>${PROVIDERS.map(p=>`<option>${p}</option>`).join("")}</select><input class="input mono" id="fEnd" placeholder="https://api.provider.com/v1/…" style="flex:1.6;font-size:12.5px"></div>
      <div class="sub">Documents supplied (anything missing is flagged as unknown = risk)</div><div class="chips">${DOCS.map(d=>`<button class="chip" data-f="docs" data-v="${d}" aria-pressed="false">${d}</button>`).join("")}</div>`;
    return `<div class="card sec" id="sec-${s.id}"><div class="sec-h"><span class="n">${n}</span><h3>${s.title}</h3>${s.req?'<span class="req">Required</span>':''}<span class="src">From document</span></div><p class="sec-q">${s.q}</p>${body}</div>`;
  }).join("");
  el.addEventListener("click",e=>{const b=e.target.closest(".chip");if(!b)return;toggle(b.dataset.f,b.dataset.v);});
  el.addEventListener("input",e=>{
    if(e.target.dataset.t){const t=THR.find(x=>x.id===e.target.dataset.t);state.thr[t.id]=+e.target.value;$("#tv-"+t.id).textContent=e.target.value+t.u}
    if(e.target.id==="fOwner")state.owner=e.target.value; if(e.target.id==="fEnd")state.endpoint=e.target.value;
    update();});
  el.addEventListener("change",e=>{if(e.target.id==="fEntity")state.entity=e.target.value;if(e.target.id==="fProv")state.provider=e.target.value;update()});
}
function toggle(f,v,force){
  const def=LAB.find(s=>s.id===f);
  if(state[f] instanceof Set){ (force??!state[f].has(v))?state[f].add(v):state[f].delete(v) }
  else state[f]=(state[f]===v&&force===undefined)?null:v;
  syncChips();update();
}
function syncChips(){ $$(".chip[data-f]").forEach(b=>{const s=state[b.dataset.f],on=s instanceof Set?s.has(b.dataset.v):s===b.dataset.v;b.classList.toggle("on",on);b.setAttribute("aria-pressed",on)}) }

/* ---------- risk logic ---------- */
const optScore=(f,v)=>(LAB.find(s=>s.id===f).opts.find(o=>o.v===v)||{}).s||0;
function assess(){
  const parts=[];
  if(state.data)parts.push([optScore("data",state.data),`Data: ${lc(state.data)}`]);
  if(state.authority)parts.push([optScore("authority",state.authority),`Authority: AI ${lc(state.authority)}`]);
  if(state.impact)parts.push([optScore("impact",state.impact),`Errors could cause ${lc(state.impact)}`]);
  if(state.oversight)parts.push([optScore("oversight",state.oversight),`Oversight: ${lc(state.oversight)}`]);
  const vul=[...state.users].reduce((a,u)=>a+optScore("users",u),0); if(vul)parts.push([Math.min(vul,3),"Includes users who need extra care"]);
  const pur=[...state.purpose].reduce((a,u)=>a+optScore("purpose",u),0); if(pur)parts.push([pur,"Purpose affects decisions about people"]);
  const score=parts.reduce((a,p)=>a+p[0],0);
  const ready=state.data&&state.authority&&state.impact&&state.oversight;
  const tier=!ready?null:score<=4?"low":score<=9.5?"medium":"high";
  return {score,tier,reasons:parts.filter(p=>p[0]>0).sort((a,b)=>b[0]-a[0]).slice(0,3).map(p=>p[1])};
}
function reviewers(tier){
  if(!tier)return[];
  const r=["Business owner","Data governance"];
  if(tier!=="low")r.push("Cybersecurity");
  if(tier!=="low"||/Personal/.test(state.data||""))r.push("Legal & privacy");
  if(tier==="high"||state.provider)r.push("Procurement");
  return [...new Set(r)];
}
const TIERINFO={low:{c:"var(--low)",hex:"#2fe3a6",lane:"Fast lane · lighter checks",est:"≈ 2 working days"},
  medium:{c:"var(--med)",hex:"#ffad3d",lane:"Standard assurance",est:"≈ 6 working days"},
  high:{c:"var(--high)",hex:"#ff5a8a",lane:"Full assurance · more reviewers",est:"≈ 12 working days"}};
const REQ=["entity","purpose","users","data","authority","impact","oversight"];
const filled=f=>f==="entity"?!!state.entity:state[f] instanceof Set?state[f].size>0:!!state[f];

function update(){
  const a=assess(),ti=a.tier&&TIERINFO[a.tier];
  const done=REQ.filter(filled).length, pct=Math.round(done/REQ.length*100);
  $("#ringArc").style.strokeDashoffset=119.4*(1-pct/100);$("#ringTxt").textContent=pct+"%";
  $("#pvEntity").textContent=state.entity?abbr(state.entity):"no entity";
  $("#pvOrb").style.color=ti?ti.hex:"";
  $("#tierName").textContent=a.tier?cap(a.tier)+" risk":"—";$("#tierName").style.color=ti?ti.c:"";
  $("#tierLane").textContent=ti?ti.lane:"Risk tier pending";
  $("#meter").style.width=(a.tier?Math.min(100,8+a.score/16*92):0)+"%";$("#meter").style.background=ti?ti.c:"";
  $("#reasons").innerHTML=a.reasons.length?a.reasons.map(r=>`<li>${r}</li>`).join(""):`<li>${a.tier?"No elevated risk factors":"Fill in data, authority, errors and oversight to calculate the tier"}</li>`;
  const missing=DOCS.filter(d=>!state.docs.has(d));
  const rows=[["Purpose",[...state.purpose].join(", ")],["Affected users",[...state.users].join(", ")],["Data",state.data],["Authority",state.authority],
    ["If wrong",state.impact],["Oversight",state.oversight],["Languages",[...state.lang].join(", ")],
    ["Max response time",`≤${state.thr.lat}s`],
    ["Model",state.provider?state.provider:"Registry suggestion first"]];
  if(state.provider&&missing.length)rows.push(["Unknown = risk",missing.join(", "),"unk"]);
  $("#pvRows").innerHTML=rows.map(([k,v,cls])=>`<div class="pv-row"><dt>${k}</dt><dd class="${v?cls||"":"empty"}">${v||"Not set"}</dd></div>`).join("");
  const rv=reviewers(a.tier);$("#revs").innerHTML=rv.length?rv.map(r=>`<span>${r}</span>`).join(""):"<span>—</span>";
  $("#estTime").innerHTML=ti?`${ti.est} <span style="color:var(--dim);font-weight:400">vs ~30</span>`:"—";
  const left=REQ.length-done;$("#genBtn").disabled=left>0;
  $("#genHint").textContent=left>0?`${left} required section${left>1?"s":""} remaining`:"Ready. This will create the card and send it to Agent 1.";
}
const lc=x=>x.replace(/^[A-Z](?=[a-z])/,m=>m.toLowerCase());
const abbr=s=>s.split(/\s+/).filter(w=>/^[A-Z]/.test(w)).map(w=>w[0]).join("");

/* ---------- mode switch ---------- */
$$(".seg button").forEach(b=>b.addEventListener("click",()=>setMode(b.dataset.mode)));
function setMode(m){$$(".seg button").forEach(x=>x.classList.toggle("on",x.dataset.mode===m));$("#m-lab").style.display=m==="lab"?"":"none";$("#m-upload").style.display=m==="upload"?"":"none"}

/* ---------- upload & extraction ---------- */
const drop=$("#drop"),fileIn=$("#file");
["dragenter","dragover"].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add("over")}));
["dragleave","drop"].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove("over")}));
drop.addEventListener("drop",e=>{if(e.dataTransfer.files[0])handleFile(e.dataTransfer.files[0])});
fileIn.addEventListener("change",()=>{if(fileIn.files[0])handleFile(fileIn.files[0])});
function handleFile(f){
  const ext=(f.name.split(".").pop()||"").toLowerCase(),isText=["txt","md"].includes(ext);
  $("#fileList").innerHTML=`<div class="fileitem"><div class="ic">${ext.toUpperCase()}</div><div class="meta"><b>${f.name}</b><small id="fstat">Reading document…</small><div class="prog"><i id="fprog"></i></div></div></div>`;
  let p=0;const iv=setInterval(()=>{p=Math.min(100,p+7+Math.random()*9);$("#fprog").style.width=p+"%";if(p>=100){clearInterval(iv);(isText?f.text():Promise.resolve(null)).then(txt=>applyExtraction(txt))}},90);
}
function applyExtraction(txt){
  const found=[];
  if(txt){
    const low=txt.toLowerCase();
    LAB.forEach(s=>{if(!s.opts)return;const hits=s.opts.filter(o=>(o.k||[o.v.toLowerCase()]).some(k=>low.includes(k)));
      if(!hits.length)return;found.push(s.id);
      if(state[s.id] instanceof Set)hits.forEach(h=>state[s.id].add(h.v));else state[s.id]=hits[hits.length-1].v;});
    const ent=ENTITIES.find(e=>low.includes(e.toLowerCase()));if(ent){state.entity=ent;found.push("entity")}
  }else{ // sample extraction until the backend parser is connected
    Object.assign(state,{entity:ENTITIES[Math.min(3,ENTITIES.length-1)],data:"Personal data (PII)",authority:"Recommends",impact:"Service delay",oversight:"Low confidence"});
    ["Answer citizen FAQs","Translate Arabic ↔ English"].forEach(v=>state.purpose.add(v));
    ["Citizens","Residents","Arabic speakers","People with disabilities"].forEach(v=>state.users.add(v));
    ["Arabic (MSA)","English"].forEach(v=>state.lang.add(v));
    found.push("entity","purpose","users","data","authority","impact","oversight","lang");
  }
  const fields=[...new Set(found)];
  $("#fstat").innerHTML=fields.length?`Extracted ${fields.length} section${fields.length>1?"s":""}${txt?"":" (sample data)"} · <a href="#" id="toLab" style="color:var(--bronze)">Review in Lab →</a>`:"No fields recognised. Fill them in using the Lab.";
  if(state.entity)$("#fEntity").value=state.entity;
  $$(".sec").forEach(s=>s.classList.toggle("extracted",fields.includes(s.id.slice(4))));
  syncChips();update();
  const tl=$("#toLab");if(tl)tl.addEventListener("click",e=>{e.preventDefault();setMode("lab")});
}

/* =========================================================
   GENERATE — orbs for each selection merge into one card
   ========================================================= */
let card=null;
$("#genBtn").addEventListener("click",()=>{
  const a=assess(),n=String(143).padStart(4,"0");
  card={id:`UC-2026-${n}`,entity:state.entity,owner:state.owner||"Not named yet",purpose:[...state.purpose],users:[...state.users],data:state.data,
    authority:state.authority,impact:state.impact,oversight:state.oversight,languages:[...state.lang],thresholds:{...state.thr},
    model:state.provider?{provider:state.provider,endpoint:state.endpoint||null,documents:[...state.docs],unknowns:DOCS.filter(d=>!state.docs.has(d))}:null,
    tier:a.tier,tierReasons:a.reasons,reviewers:reviewers(a.tier)};
  concoct(a.tier,()=>showGenerated());
});
function concoct(tier,done){
  const ov=$("#concoct"),cv=$("#ccCanvas"),c=cv.getContext("2d");ov.classList.add("on");
  const picks=[...state.purpose,...state.users,state.data,state.authority,state.impact,state.oversight].filter(Boolean).slice(0,12);
  const dur=reduce?.3:2.6,t0=performance.now();
  const msgs=["Collecting your selections…","Scoring the risk tier…","Writing the Use-Case Card…"];
  (function f(now){
    const t=(now-t0)/1000,p=Math.min(1,t/dur);c.setTransform(2,0,0,2,0,0);c.clearRect(0,0,340,340);
    $("#ccText").textContent=msgs[Math.min(2,Math.floor(p*3))];
    const cx=170,cy=170,ease=p<.5?4*p*p*p:1-Math.pow(-2*p+2,3)/2,ring=110*(1-ease)+10,grow=Math.max(0,(p-.55)/.45);
    picks.forEach((_,i)=>{const ang=i/picks.length*TAU+p*3;drawAgentIcon(c,cx+Math.cos(ang)*ring,cy+Math.sin(ang)*ring,18*(1-grow*.6),i%8,1-grow)});
    if(grow>0){const R=70*(1-Math.exp(-4*grow)*Math.cos(6*grow));
      drawEmblem(c,cx,cy,Math.max(1,R))}
    if(p<1)requestAnimationFrame(f);else setTimeout(()=>{ov.classList.remove("on");done()},350);
  })(t0);
}
function step(n){[1,2,3].forEach(i=>{const s=$("#st"+i);s.classList.toggle("on",i===n);s.classList.toggle("done",i<n)});
  $("#v-define").style.display=n===1?"":"none";$("#v-generated").style.display=n===2?"":"none";$("#v-pipeline").style.display=n===3?"":"none";
  $("#newTitle").textContent=["Define the use case","Review the Use-Case Card","Agent pipeline"][n-1];window.scrollTo({top:0,behavior:"smooth"})}

function sentence(){
  const L=a=>a.length>1?a.slice(0,-1).join(", ")+" and "+a[a.length-1]:a[0]||"";
  const ov={"Every output":"A human reviews every output","Low confidence":"A human reviews low-confidence outputs","Spot checks":"Outputs are spot-checked periodically","None":"No human reviews the outputs"};
  const au={"Informs":"only gives information","Recommends":"recommends, and a human decides","Decides":"makes decisions that a human reviews afterwards","Acts alone":"acts without a human in the loop"};
  return `An AI system for ${card.entity} that will ${L(card.purpose.map(p=>lc(p)))} for ${L(card.users.map(u=>u==="Citizens"||u==="Residents"||u==="Businesses"?lc(u):lc(u)))}. It will handle ${lc(card.data)} and ${au[card.authority]}. If it gets something wrong, the worst realistic outcome is ${lc(card.impact)}. ${ov[card.oversight]}.`;
}
function showGenerated(){
  const ti=TIERINFO[card.tier];
  $("#v-generated").innerHTML=`<div class="gencard">
    <div class="card doc">
      <div class="top2"><div><div class="eyebrow">${card.id} · ${card.entity}</div><h3>${card.purpose[0]}${card.purpose.length>1?` + ${card.purpose.length-1} more`:""}</h3></div>
        <span class="tier ${card.tier}" style="font-size:12px;padding:6px 12px">${cap(card.tier)} risk</span></div>
      <p class="summary">${sentence()}</p>
      <dl>
        <dt>Business owner</dt><dd>${card.owner}</dd>
        <dt>Affected users</dt><dd>${card.users.join(", ")}</dd>
        <dt>Languages</dt><dd>${card.languages.join(", ")||"<span style='color:var(--dim)'>Not specified</span>"}</dd>
        <dt>Why this tier</dt><dd>${card.tierReasons.join(" · ")||"No elevated factors"}</dd>
        <dt>Assurance path</dt><dd>${ti.lane} · ${ti.est}</dd>
        <dt>Candidate model</dt><dd>${card.model?`${card.model.provider}${card.model.unknowns.length?` <span style="color:var(--high)">· ${card.model.unknowns.length} unknowns flagged</span>`:""}`:"None. Agent 1 will check the registry first."}</dd>
      </dl>
      <div class="eyebrow" style="margin-top:26px">Pass / fail threshold</div>
      <div class="crit"><div><small>Max response time</small><b>≤ ${card.thresholds.lat}s</b></div></div>
      <pre class="json" id="json">${JSON.stringify(card,null,2).replace(/</g,"&lt;")}</pre>
    </div>
    <div class="side">
      <div class="card"><div class="eyebrow">Next</div>
        <p style="font-size:13.5px;line-height:1.55;color:var(--mute);margin:12px 0 18px">The card goes to <b style="color:var(--fg)">Agent 1</b>. It confirms the tier and checks the shared registry for an approved model that matches this context.</p>
        <div class="actions"><button class="pill solid" id="sendBtn">Send to Agent 1 →</button><button class="pill" id="reportBtn">View report</button><button class="pill" id="jsonBtn">View payload</button><button class="pill" id="backBtn">← Back to the Lab</button></div></div>
      <div class="card"><div class="eyebrow">Reviewers (parallel)</div><div class="revs" style="margin-bottom:0">${card.reviewers.map(r=>`<span>${r}</span>`).join("")}</div></div>
    </div></div>`;
  $("#jsonBtn").onclick=e=>{const j=$("#json");j.classList.toggle("on");e.target.textContent=j.classList.contains("on")?"Hide payload":"View payload"};
  $("#backBtn").onclick=()=>step(1);$("#sendBtn").onclick=runPipeline;$("#reportBtn").onclick=showReport;step(2);
  setTimeout(showReport,reduce?0:450);
}

/* =========================================================
   USE-CASE REPORT — a plain summary that opens once the card is generated
   ========================================================= */
let reportReturn=null;
function closeReport(){
  const el=$("#ucr");if(!el)return;
  el.remove();document.body.classList.remove("ucr-open");document.body.style.overflow="";
  if(reportReturn&&reportReturn.isConnected)reportReturn.focus({preventScroll:true});reportReturn=null;
}
function showReport(){
  if(!card)return;closeReport();reportReturn=document.activeElement;
  const ti=TIERINFO[card.tier],today=new Date().toLocaleDateString("en-GB",{day:"numeric",month:"long",year:"numeric"});
  const list=a=>a.length?`<ul>${a.map(x=>`<li>${x}</li>`).join("")}</ul>`:`<p class="ucr-none">Not specified</p>`;
  const model=card.model?`${card.model.provider}${card.model.unknowns.length?` · ${card.model.unknowns.length} document${card.model.unknowns.length>1?"s":""} missing`:""}`:"Agent 1 will suggest one from the Registry";
  const steps=[
    ["Risk check","Agent 1 confirms the risk level and looks for an approved model already in use elsewhere."],
    ["Testing",`Agents 2 to 5 check it against UAE rules and the pass mark below${card.tier==="low"?", using the lighter fast-lane checks":""}.`],
    ["Review",`${card.reviewers.join(", ")} review the results at the same time.`],
    ["Sign-off","A named person approves it and accepts any remaining risk."],
    ["Monitoring","Once live, Agent 8 watches it and sends it back for re-checks when something changes."]];
  document.body.insertAdjacentHTML("beforeend",`<div id="ucr" class="ucr-scrim"><div class="ucr" role="dialog" aria-modal="true" aria-labelledby="ucrTitle">
    <header class="ucr-h">
      <div><div class="eyebrow">Use-case report · ${card.id} · ${today}</div><h2 id="ucrTitle">${card.purpose.join(", ")}</h2><p>${card.entity} · Owner: ${esc(card.owner)}</p></div>
      <button class="sheet-x" id="ucrX" aria-label="Close report">✕</button>
    </header>
    <div class="ucr-body">
      <div class="ucr-band">
        <div><small>Risk level</small><span class="tier ${card.tier}">${cap(card.tier)} risk</span></div>
        <div><small>Assurance path</small><b>${ti.lane}</b></div>
        <div><small>Expected time</small><b>${ti.est.replace("≈ ","About ")}</b></div>
        <div><small>Reviewers</small><b>${card.reviewers.length} teams</b></div>
      </div>
      <section><h3>Summary</h3><p class="ucr-lead">${sentence()}</p></section>
      <section class="ucr-two">
        <div><h3>What it will do</h3>${list(card.purpose)}</div>
        <div><h3>Who it affects</h3>${list(card.users)}</div>
      </section>
      <section><h3>Data and control</h3><dl class="ucr-dl">
        <dt>Most sensitive data</dt><dd>${card.data}</dd>
        <dt>AI's authority</dt><dd>${card.authority}</dd>
        <dt>Human oversight</dt><dd>${card.oversight}</dd>
        <dt>Worst outcome if wrong</dt><dd>${card.impact}</dd>
        <dt>Languages</dt><dd>${card.languages.join(", ")||"Not specified"}</dd>
        <dt>Model</dt><dd>${model}</dd>
      </dl></section>
      <section><h3>Why it is ${card.tier} risk</h3>${list(card.tierReasons.length?card.tierReasons:["No elevated risk factors"])}</section>
      <section><h3>Pass mark</h3><div class="ucr-crit">
        <div><small>Response time</small><b>at most ${card.thresholds.lat}s</b></div>
      </div></section>
      <section><h3>What happens next</h3><ol class="ucr-steps">${steps.map(([t,d])=>`<li><b>${t}</b><span>${d}</span></li>`).join("")}</ol></section>
    </div>
    <footer class="ucr-f"><button class="pill" id="ucrPrint">Print or save as PDF</button><button class="pill solid" id="ucrOk">Continue</button></footer>
  </div></div>`);
  document.body.classList.add("ucr-open");document.body.style.overflow="hidden";
  const el=$("#ucr");
  if(!reduce)el.querySelector(".ucr").animate([{opacity:0,transform:"translateY(12px)"},{opacity:1,transform:"none"}],{duration:280,easing:"cubic-bezier(.2,.7,.2,1)"});
  el.addEventListener("click",e=>{if(e.target===el||e.target.closest("#ucrX,#ucrOk"))closeReport()});
  $("#ucrPrint").onclick=()=>window.print();
  $("#ucrX").focus({preventScroll:true});
}
document.addEventListener("keydown",e=>{
  const el=document.getElementById("ucr");if(!el)return;
  if(e.key==="Escape")return closeReport();
  if(e.key!=="Tab")return;
  const f=[...el.querySelectorAll("button")],first=f[0],last=f[f.length-1];
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
});

/* The entity list follows the data and the person: a department role can only file for its own department. */
function syncEntity(){
  const sel=$("#fEntity"),only=ENTITIES.length===1;
  sel.innerHTML=`<option value="">Select entity…</option>${ENTITIES.map(e=>`<option>${esc(e)}</option>`).join("")}`;
  if(only)state.entity=ENTITIES[0];else if(!ENTITIES.includes(state.entity))state.entity="";
  sel.value=state.entity;sel.disabled=only;update();
}
$("#pvOrb").innerHTML=agentIconSVG(AGENTS[0]);
buildLab();syncEntity();
addEventListener("access:login",syncEntity);
