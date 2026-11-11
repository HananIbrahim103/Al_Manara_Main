const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const hero = {active:true,focus:0,hover:-1,theta:0,last:0};

/* =========================================================
   STATE
   ========================================================= */
const state = {entity:"",owner:"",purpose:new Set(),users:new Set(),data:null,authority:null,impact:null,oversight:null,
  lang:new Set(),thr:Object.fromEntries(THR.map(t=>[t.id,t.def])),provider:"",endpoint:"",docs:new Set()};

/* =========================================================
   NAV
   ========================================================= */
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
/* Each page can register a function that draws it when it opens. */
const PAGE_HOOKS = {};
const PATHS = {overview:"overview",new:"new",dept:"departments",registry:"registry",monitor:"monitor"};
let currentPage = "overview", lastHash = location.hash;
function routeHash(){return "#/"+PATHS[currentPage]+(currentPage==="dept"?`/${DEPTS[dView.d].code}/${dView.s+1}`:"")}
function syncRoute(){const h=routeHash();if(location.hash===h)return;lastHash=h;location.hash=h}
function go(p){
  currentPage=p;
  $$(".page").forEach(x=>x.classList.toggle("on",x.id==="p-"+p));
  $$(".nav button[data-go]").forEach(b=>{const on=b.dataset.go===p;b.classList.toggle("on",on);on?b.setAttribute("aria-current","page"):b.removeAttribute("aria-current")});
  hero.active = p==="overview";
  if(PAGE_HOOKS[p])PAGE_HOOKS[p]();
  syncRoute();
  window.scrollTo({top:0,behavior:"smooth"});
}
/* Links and the browser's back button: #/departments/RTA/2 opens that department and agent. */
function route(){
  const m=location.hash.match(/^#\/(\w+)(?:\/(\w+)\/(\d+))?/);
  lastHash=location.hash;
  if(!m)return go("overview");
  if(m[1]==="departments"){
    const d=m[2]?DEPTS.findIndex(x=>x.code===m[2]):dView.d;
    return openDept(d<0?0:d,m[3]?Math.min(+m[3]-1,DEPTS[d<0?0:d].agents.length-1):0);
  }
  const page=Object.keys(PATHS).find(k=>PATHS[k]===m[1]);
  go(page||"overview");
}
addEventListener("hashchange",()=>{if(location.hash!==lastHash)route()});
addEventListener("intro:complete",()=>{if(location.hash.length>2)route()});
document.addEventListener("click",e=>{const d=e.target.closest("[data-d]"); if(d) return openDept(+d.dataset.d,d.dataset.s==null?undefined:+d.dataset.s); const g=e.target.closest("[data-go]"); if(g) go(g.dataset.go);});

/* =========================================================
   OVERVIEW CONTENT
   ========================================================= */

const ag = $("#agentGrid"), ai = $("#agentInfo");
ag.innerHTML = AGENTS.map(a=>`<button data-a="${a.n-1}" aria-label="Agent ${a.n}: ${a.name}">${agentIcon(a)}<span class="num">${a.n}</span></button>`).join("");
function showAgent(i){
  const a=AGENTS[i]; $$("#agentGrid button").forEach((b,j)=>b.classList.toggle("on",j===i));
  ai.innerHTML=`<b>Agent ${a.n} · ${a.name}</b><p>${a.desc}<br><span style="color:var(--fg)">${a.load}</span></p>`;
  hero.focus=i;
}
ag.addEventListener("mouseover",e=>{const b=e.target.closest("button"); if(b) showAgent(+b.dataset.a);});
ag.addEventListener("focusin",e=>{const b=e.target.closest("button"); if(b) showAgent(+b.dataset.a);});
showAgent(0);hero.focus=-1;
ag.addEventListener("mouseleave",()=>hero.focus=-1);

const ROWS=[
  ["UC-2026-0139","Visa FAQ assistant","Federal Authority for Identity & Citizenship","medium",7,"Awaiting sign-off"],
  ["UC-2026-0137","Benefit eligibility triage","Ministry of Human Resources & Emiratisation","high",6,"Concluding"],
  ["UC-2026-0135","Meeting minutes drafter","Department of Government Enablement","low",7,"Fast lane · review"],
  ["UC-2026-0131","Clinic appointment router","Ministry of Health & Prevention","high",4,"Red team + user testing"],
  ["UC-2026-0128","Traffic fine explainer","Roads & Transport Authority","medium",8,"Deployed · monitored"],
];
$("#rows").innerHTML = ROWS.map(r=>{const sy=sysByName(r[1]);return `<button class="trow" data-d="${sy.d}" data-s="${sy.k}" aria-label="Open ${r[1]} in Departments"><span class="mono">${r[0]}</span><span>${r[1]}</span><small>${r[2]}</small>
  <span><span class="tier ${r[3]}">${cap(r[3])}</span></span>
  <span class="stages">${AGENTS.map((_,i)=>`<i class="${i<r[4]-1?'d':i===r[4]-1?'c':''}"></i>`).join("")}</span><small>${r[5]}</small></button>`}).join("");
const awaiting=SYSTEMS.filter(s=>s.state==="signoff");
$("#signoffCount").textContent=String(awaiting.length).padStart(2,"0");
$("#signoffList").innerHTML=awaiting.map(s=>`<button data-d="${s.d}" data-s="${s.k}"><b>${s.name}</b><small>${s.dept.short} · ${s.teams.length} review teams · needs a named approver</small><span class="tier ${s.tier}">${cap(s.tier)}</span></button>`).join("");
function cap(s){return s[0].toUpperCase()+s.slice(1)}

/* =========================================================
   ORB RENDERING (shared with the intro animation)
   ========================================================= */
const TAU=Math.PI*2;

/* ---------- department network: hub -> 8 agent orbs + departments -> their agentic systems ----------
   Hub and the 8 assurance agents are orbs. Departments and their systems are squares.
   The arrival choreography (graph.render) is driven by a single clock, k, in seconds. */
const graph={listHover:-1,live:false};
$("#dIndex").innerHTML=DEPTS.map((d,i)=>`<button data-d="${i}" data-i="${i}"><span>${d.short}</span><em style="margin-left:${i*7}px">${String(i+1).padStart(2,"0")}</em></button>`).join("");
$("#dIndex").addEventListener("mouseover",e=>{const b=e.target.closest("button");graph.listHover=b?+b.dataset.i:-1});
$("#dIndex").addEventListener("mouseleave",()=>graph.listHover=-1);
$("#dIndex").addEventListener("focusin",e=>{const b=e.target.closest("button");graph.listHover=b?+b.dataset.i:-1});
$("#dIndex").addEventListener("focusout",()=>graph.listHover=-1);
$("#gCount").textContent=`${DEPTS.length} departments · ${DEPTS.reduce((a,d)=>a+d.systems.length,0)} agentic systems`;
(function(){
  const cv=$("#heroCanvas"),c=cv.getContext("2d"),tip=$("#heroTip");
  const MONO='"Sohne Mono","IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace';
  const COL={section:"#e7c79f",update:"#6fbf93",hover:[243,205,130],related:[215,232,220],tether:[34,78,54],end:[160,210,180]};
  const SPOKE=[[111,191,147,1],[231,199,159,.5],[160,210,180,.45]];
  /* arrival settings */
  const IN={stagger:.07,travel:1.1,leafDelay:.45,leafStagger:.025,swell:.7,scale:5.6,hold:.25,release:1.75,pow:3,inOut:.2,spin:-Math.PI,leafSpin:-67*Math.PI/180,spinFor:3};
  const cl=v=>Math.max(0,Math.min(1,v)),sm=(a,b,v)=>{const q=cl((v-a)/(b-a));return q*q*(3-2*q)};
  let W=0,H=0,D=1,U=1,hubR=20,nodes=[],tips=[],agentAt=[],rects=[],ptr={x:-999,y:-999,inside:false},drag=null,down=null,moved=false,hovD=-1,hovN=-1,hovA=-1;
  let hubFrom=1,fx=0,orbit=0,liveAt=0,lastNow=0;
  const rnd=seed=>()=>(seed=(seed*16807)%2147483647)/2147483647;
  const hash=s=>{let h=2166136261;for(let i=0;i<s.length;i++)h=Math.imul(h^s.charCodeAt(i),16777619);return h>>>0};
  const staggerOf=n=>{const g=(a,b)=>b?g(b,a%b):a;let e=Math.max(1,Math.floor(n/2));while(e>1&&g(e,n)!==1)e--;return i=>i*e%n};

  /* resting positions: a short force relaxation, seeded so the layout is the same on every load */
  function layout(R){
    const pts=[],n=DEPTS.length,ring=hubR+46*U,mx=W/2-30,my=H/2-58;
    DEPTS.forEach((dp,d)=>{
      const th=-Math.PI/2+(d+.5)*TAU/n+(R()-.5)*.3,f=.66+R()*.26;
      const dept={x:Math.cos(th)*mx*f,y:Math.sin(th)*my*f,d,dept:true};pts.push(dept);
      const m=dp.systems.length,off=R()*TAU;
      dp.systems.forEach((sy,k)=>{const a=off+k/m*TAU+(R()-.5)*.5,len=(62+R()*64)*U;
        pts.push({x:dept.x+Math.cos(a)*len,y:dept.y+Math.sin(a)*len,d,k,to:dept,len})});
    });
    for(let it=0;it<320;it++){
      for(let i=0;i<pts.length;i++)for(let j=i+1;j<pts.length;j++){
        const a=pts[i],b=pts[j],gap=(a.dept&&b.dept?190:a.dept||b.dept?54:34)*U;
        let dx=b.x-a.x,dy=b.y-a.y,q=Math.hypot(dx,dy)||.01;if(q>=gap)continue;
        const f=(gap-q)*.24/q;dx*=f;dy*=f;a.x-=dx;a.y-=dy;b.x+=dx;b.y+=dy}
      pts.forEach(p=>{
        if(p.to){const dx=p.x-p.to.x,dy=p.y-p.to.y,q=Math.hypot(dx,dy)||.01,f=(p.len-q)*.2/q;p.x+=dx*f;p.y+=dy*f}
        const q=Math.hypot(p.x,p.y)||.01,min=p.dept?ring+96*U:ring+30*U;if(q<min){p.x*=min/q;p.y*=min/q}
        p.x=Math.max(-W/2+26,Math.min(W/2-26,p.x));p.y=Math.max(-H/2+62,Math.min(H/2-62,p.y));
      });
    }
    return pts;
  }
  function build(){
    U=Math.max(.5,Math.min(1.25,Math.min(W,H)/680));hubR=Math.max(22,Math.min(W,H)*.056);
    const R=rnd(11),pts=layout(R),a8=staggerOf(AGENTS.length),d8=staggerOf(DEPTS.length),ring=hubR+46*U;
    nodes=[{p:-1,ox:0,oy:0,x:W/2,y:H/2,vx:0,vy:0,d:-1,kind:"hub",rev:1,sc:1}];tips=[];agentAt=[];
    AGENTS.forEach((ag,a)=>{const th=-Math.PI/2+a*TAU/AGENTS.length;
      agentAt[a]=nodes.push({p:0,ox:Math.cos(th)*ring,oy:Math.sin(th)*ring,d:-1,kind:"agent",a,birth:a8(a)*IN.stagger})-1});
    DEPTS.forEach((dp,d)=>{
      const dPt=pts.find(p=>p.dept&&p.d===d),birth=d8(d)*IN.stagger,di=nodes.push({p:0,ox:dPt.x,oy:dPt.y,d,kind:"dept",birth})-1;
      tips[d]=di;
      pts.filter(p=>p.to===dPt).forEach(p=>{const h=hash(dp.code+p.k);
        nodes.push({p:di,ox:p.x-dPt.x,oy:p.y-dPt.y,d,kind:"sys",sys:dp.systems[p.k],k:p.k,h,ink:SPOKE[h%3],birth:birth+IN.leafDelay+p.k*IN.leafStagger,stage:dp.systems[p.k][2]-1})});
    });
    nodes.forEach((nd,i)=>{if(!i)return;const P=nodes[nd.p];nd.x=P.x+nd.ox;nd.y=P.y+nd.oy;nd.vx=nd.vy=0;nd.rev=1;nd.sc=1});
  }
  function size(){D=Math.min(devicePixelRatio||1,2);const r=cv.getBoundingClientRect();if(!r.width)return;if(r.width===W&&r.height===H&&nodes.length)return;W=r.width;H=r.height;cv.width=W*D;cv.height=H*D;build()}
  new ResizeObserver(size).observe(cv);size();

  const segDist=(px,py,ax,ay,bx,by)=>{const dx=bx-ax,dy=by-ay,l=dx*dx+dy*dy||1,t=Math.max(0,Math.min(1,((px-ax)*dx+(py-ay)*dy)/l));return Math.hypot(px-ax-dx*t,py-ay-dy*t)};
  function hit(){
    let bn=-1,bd=1e9;
    for(let i=1;i<nodes.length;i++){const nd=nodes[i],q=Math.hypot(nd.x-ptr.x,nd.y-ptr.y);if(q<(nd.kind==="sys"?13:16)&&q<bd){bd=q;bn=i}}
    if(bn<0)for(let i=1;i<nodes.length;i++){const nd=nodes[i];if(nd.kind==="agent")continue;const P=nodes[nd.p],q=segDist(ptr.x,ptr.y,P.x,P.y,nd.x,nd.y);if(q<8&&q<bd){bd=q;bn=i}}
    if(bn<0)rects.forEach((r,d)=>{if(r&&ptr.x>=r.x-6&&ptr.x<=r.x+r.w+6&&ptr.y>=r.y-6&&ptr.y<=r.y+r.h+6)bn=tips[d]});
    return bn;
  }
  function setPtr(e){const r=cv.getBoundingClientRect();const x=e.clientX-r.left,y=e.clientY-r.top,mx=x-ptr.x,my=y-ptr.y;ptr.x=x;ptr.y=y;return[mx,my]}
  function clearAgent(){if(hovA>=0){hovA=-1;hero.focus=-1}}
  cv.addEventListener("pointermove",e=>{
    if(!graph.live)return;
    const was=ptr.inside,[mx,my]=setPtr(e);ptr.inside=true;
    if(drag){if(Math.hypot(ptr.x-down.x,ptr.y-down.y)>5)moved=true;tip.style.opacity=0;return}
    if(was&&!reduce)for(let i=1;i<nodes.length;i++){const nd=nodes[i],q=Math.hypot(nd.x-ptr.x,nd.y-ptr.y);if(q<70){const f=(1-q/70)*.1;nd.vx+=Math.max(-30,Math.min(30,mx))*f;nd.vy+=Math.max(-30,Math.min(30,my))*f}}
    const n=hit(),nd=n>0?nodes[n]:null,d=nd?nd.d:-1,isAgent=nd&&nd.kind==="agent";
    if(d!==hovD&&d>=0&&!reduce)nodes.forEach(x=>{if(x.d===d){x.vx+=(Math.random()-.5)*3.2;x.vy+=(Math.random()-.5)*3.2}});
    hovD=d;hovN=n;cv.style.cursor=nd?"grab":"default";
    if(isAgent){if(nd.a!==hovA){hovA=nd.a;showAgent(nd.a)}}else clearAgent();
    if(nd){
      if(isAgent){const a=AGENTS[nd.a];tip.innerHTML=`Agent ${a.n} · ${a.name}<small>${a.load}</small>`}
      else{const dp=DEPTS[d];tip.innerHTML=nd.kind==="sys"?`${nd.sys[0]}<small>${dp.code} · ${sysStatus(nd.sys)} · click to open</small>`:`${dp.name}<small>${dp.systems.length} agentic systems · click to open</small>`}
      tip.style.left=Math.min(ptr.x+16,W-290)+"px";tip.style.top=Math.max(8,ptr.y-14)+"px";tip.style.opacity=1}else tip.style.opacity=0;
  });
  cv.addEventListener("pointerdown",e=>{if(!graph.live)return;setPtr(e);const n=hit()>0?hit():hovN;if(n>0){drag={i:n};down={x:ptr.x,y:ptr.y};moved=false;cv.setPointerCapture(e.pointerId);cv.style.cursor="grabbing";e.preventDefault()}});
  const release=e=>{if(!drag)return;const nd=nodes[drag.i],d=nd.d;drag=null;cv.style.cursor="grab";if(!moved&&e.type==="pointerup"&&d>=0)openDept(d,nd.kind==="sys"?nd.k:undefined)};
  cv.addEventListener("pointerup",release);cv.addEventListener("pointercancel",release);
  cv.addEventListener("pointerleave",()=>{if(drag)return;ptr.inside=false;hovD=hovN=-1;clearAgent();tip.style.opacity=0});

  /* resting behaviour: springs, gentle sway, and the agent ring slowly orbiting the hub */
  function step(t,ramp){
    nodes[0].x=W/2;nodes[0].y=H/2;
    for(let i=1;i<nodes.length;i++){const nd=nodes[i],P=nodes[nd.p];
      const sw=reduce?0:(nd.kind==="agent"?orbit:(.03*Math.sin(t*.45+nd.d*1.3)+.012*Math.sin(t*.9+i))*ramp),cs=Math.cos(sw),sn=Math.sin(sw);
      const tx=P.x+nd.ox*cs-nd.oy*sn,ty=P.y+nd.ox*sn+nd.oy*cs;
      if(drag&&drag.i===i){nd.x=ptr.x;nd.y=ptr.y;nd.vx=nd.vy=0}
      else{nd.vx+=(tx-nd.x)*.07;nd.vy+=(ty-nd.y)*.07;
        if(ptr.inside&&!drag){const dx=nd.x-ptr.x,dy=nd.y-ptr.y,q=Math.hypot(dx,dy);if(q<60&&q>.01){const f=(1-q/60)*.6;nd.vx+=dx/q*f;nd.vy+=dy/q*f}}
        nd.vx*=.87;nd.vy*=.87;nd.x+=nd.vx;nd.y+=nd.vy}
      if(nd.p>0){P.vx+=(nd.x-tx)*.022;P.vy+=(nd.y-ty)*.022}
    }
  }

  /* the arrival: every node travels out from its parent, spinning into place, large at first and shrinking to size */
  function breath(k,from){const o=cl((k-IN.hold)/IN.release),r=1-Math.pow(1-o,IN.pow),l=o<.5?Math.pow(2,IN.pow-1)*Math.pow(o,IN.pow):1-Math.pow(-2*o+2,IN.pow)/2;return Math.pow(from,1-(r+(l-r)*IN.inOut))}
  function pose(k){
    const q=Math.pow(1-cl(k/IN.spinFor),5),spin=IN.spin*q,leaf=IN.leafSpin*q,br=breath(k,IN.scale);
    nodes[0].x=W/2;nodes[0].y=H/2;
    nodes[0].sc=breath(k,hubFrom);
    for(let i=1;i<nodes.length;i++){const nd=nodes[i],P=nodes[nd.p],top=nd.p===0,dur=IN.travel*(top?1:.9),d=cl((k-nd.birth)/dur),ease=1-Math.pow(1-d,5),a=Math.atan2(nd.oy,nd.ox)+(top?spin:leaf),L=Math.hypot(nd.ox,nd.oy)*ease;
      nd.x=P.x+Math.cos(a)*L;nd.y=P.y+Math.sin(a)*L;nd.rev=Math.min(1,d*6);nd.sc=nd.rev*(1+Math.sin(Math.PI*d)*IN.swell)*br}
  }

  function line(g,ax,ay,bx,by,c0,a0,c1,a1,w){
    if(a0<.005&&a1<.005)return;
    const gr=g.createLinearGradient(ax,ay,bx,by);gr.addColorStop(0,`rgba(${c0[0]},${c0[1]},${c0[2]},${a0})`);gr.addColorStop(1,`rgba(${c1[0]},${c1[1]},${c1[2]},${a1})`);
    g.strokeStyle=gr;g.lineWidth=w;g.beginPath();g.moveTo(ax,ay);g.lineTo(bx,by);g.stroke();
  }
  function paint(g,t,labelA){
    const act=drag?nodes[drag.i].d:hovD>=0?hovD:graph.listHover,focus=act>=0||hero.focus>=0;
    fx+=((focus?1:0)-fx)*.16;const dim=1-.5*fx;g.lineCap="butt";
    /* faint lines: each system to the agent currently handling it */
    for(let i=1;i<nodes.length;i++){const nd=nodes[i];if(nd.kind!=="sys")continue;
      const O=nodes[agentAt[nd.stage]],vis=Math.min(nd.rev,O.rev),on=nd.d===act||nd.stage===hero.focus,a=(on?.5:.15*dim)*vis;
      line(g,nd.x,nd.y,O.x,O.y,COL.related,a,COL.related,a,on?.75:.45)}
    /* structural lines */
    for(let i=1;i<nodes.length;i++){const nd=nodes[i],P=nodes[nd.p],vis=Math.min(nd.rev,P.rev),on=nd.d>=0&&nd.d===act,a=vis*(on?1:dim);
      if(nd.kind==="sys"){
        if(on)line(g,P.x,P.y,nd.x,nd.y,COL.hover,.8,COL.hover,.8,1);
        else line(g,P.x,P.y,nd.x,nd.y,nd.ink,nd.ink[3]*a,COL.end,.4*a,1);
        /* travelling pulses */
        if(!reduce&&vis>.9)for(let j=0;j<2;j++){const rate=.1+nd.h%7*.015,raw=(t*1.5*rate+((nd.h>>>8)%1e3)/1e3+j/2)%1,pos=nd.h%2?raw:1-raw,back=nd.h%2?-.1:.1,tail=cl(pos+back),hx=P.x+(nd.x-P.x)*pos,hy=P.y+(nd.y-P.y)*pos,tx=P.x+(nd.x-P.x)*tail,ty=P.y+(nd.y-P.y)*tail,pc=on?COL.hover:nd.ink;
          line(g,tx,ty,hx,hy,pc,0,pc,.8*Math.sin(Math.PI*raw)*(on?1:nd.ink[3])*dim,1)}
      }else if(nd.kind==="dept")line(g,P.x,P.y,nd.x,nd.y,COL.tether,a,on?COL.hover:COL.end,(on?.8:.4)*a,1.2);
      else line(g,P.x,P.y,nd.x,nd.y,COL.tether,a,COL.end,.4*a,1.2);
    }
    /* squares: departments and their systems */
    for(let i=1;i<nodes.length;i++){const nd=nodes[i];if(nd.kind==="agent")continue;
      const on=nd.d===act,big=i===hovN||(drag&&drag.i===i),lit=nd.kind==="sys"&&nd.stage===hero.focus,s=(nd.kind==="dept"?5.5:3)*Math.max(.8,U)*(big?1.35:1)*nd.sc;
      if(s<=.05||nd.rev<=.01)continue;
      g.globalAlpha=nd.rev*(on||lit?1:dim);g.fillStyle=lit?"#fff":nd.kind==="dept"?COL.section:COL.update;g.fillRect(nd.x-s,nd.y-s,s*2,s*2);
      if((nd.kind==="dept"&&on)||lit){g.globalAlpha=nd.rev*.75;g.strokeStyle="#fff";g.lineWidth=1;g.strokeRect(nd.x-s-3,nd.y-s-3,s*2+6,s*2+6)}
    }
    g.globalAlpha=1;
    /* the 8 assurance agents, as line icons */
    agentAt.forEach(i=>{const nd=nodes[i],r=15*Math.max(.8,U)*nd.sc*(i===hovN?1.2:1);
      drawAgentIcon(g,nd.x,nd.y,r,nd.a,nd.rev*(act>=0?.55+.45*(1-fx):1));
      if(hero.focus===nd.a){g.strokeStyle="#fff";g.lineWidth=1;g.beginPath();g.arc(nd.x,nd.y,r+5,0,TAU);g.stroke()}});
    /* the middle agent: the Almanara emblem the intro formed */
    drawEmblem(g,nodes[0].x,nodes[0].y,hubR*nodes[0].sc);
    /* department labels */
    if(labelA>0){g.textBaseline="middle";
      DEPTS.forEach((dp,d)=>{const T=nodes[tips[d]],on=d===act,s=5.5*Math.max(.8,U);
        g.font=`300 11px ${MONO}`;const w=g.measureText(dp.short).width;g.font=`300 9px ${MONO}`;const cnt=String(dp.systems.length),w2=g.measureText(cnt).width,full=w+4+w2;
        const right=T.x<W*.74,lx=Math.max(8,Math.min(W-8-full,right?T.x+s+2:T.x-s-2-full)),ly=Math.max(10,T.y-s-12);
        g.globalAlpha=labelA*(on?1:act>=0?.5:.92);g.fillStyle="#fff";g.textAlign="left";g.font=`300 11px ${MONO}`;g.fillText(dp.short,lx,ly);
        g.globalAlpha=labelA*(on?.8:.5);g.font=`300 9px ${MONO}`;g.fillText(cnt,lx+w+4,ly-4);g.globalAlpha=1;
        rects[d]={x:lx,y:ly-8,w:full,h:16}})}
  }

  graph.sync=size;
  graph.rect=()=>cv.getBoundingClientRect();
  /* called once when the intro's emblem is ready to become the hub */
  graph.start=R=>{hubFrom=Math.max(1,R/hubR)};
  /* one frame of the arrival, drawn onto the intro's full-screen canvas with the hub at (ox,oy) */
  graph.render=(g,ox,oy,k,t)=>{g.save();g.translate(ox-W/2,oy-H/2);pose(k);paint(g,t,0);g.restore()};
  /* the arrival has finished: this canvas takes over from the same state */
  graph.go=now=>{pose(3);nodes.forEach((nd,i)=>{if(i){nd.vx=nd.vy=0;nd.rev=1;nd.sc=1}});nodes[0].sc=1;liveAt=lastNow=now;graph.live=true;c.setTransform(D,0,0,D,0,0);c.clearRect(0,0,W,H);paint(c,reduce?0:now/1000,0)};
  function frame(now){
    requestAnimationFrame(frame);
    if(!graph.live||!hero.active||document.hidden||!W)return;
    const since=(now-liveAt)/1000,ramp=sm(0,1.5,since),dt=Math.min(.05,(now-lastNow)/1000);lastNow=now;orbit+=dt*.05*ramp;
    const t=reduce?0:now/1000;step(t,ramp);
    c.setTransform(D,0,0,D,0,0);c.clearRect(0,0,W,H);paint(c,t,reduce?1:Math.min(1,since*1.18/.35));
  }
  requestAnimationFrame(frame);
})();

/* the logo in the header and the upload panel */
$$("[data-emblem]").forEach(el=>{const cv=document.createElement("canvas");cv.width=cv.height=256;drawEmblem(cv.getContext("2d"),128,128,120,1,0);el.appendChild(cv)});
