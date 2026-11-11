/* =========================================================
   INTRO: the eight line-art icons draw themselves. One line then runs
   through every icon, taking each up as it goes, sweeps around the
   screen, slowly thickening, and writes the Almanara logo stroke by
   stroke, with the English name beneath it. The logo then becomes the
   hub of the network while the panel docks into the page.
   Hooks: window "intro:complete" event fires when the dashboard is live.
   ========================================================= */
(function(){
  const intro=$("#intro"),cv=$("#introCanvas"),c=cv.getContext("2d"),gate=$("#gate"),skipB=$("#introSkip");
  const NOTES=[294,330,392,440,494,587,659,784];
  const T={first:.3,gap:.2,drawFor:.6,unspool:2.5,write:6.2,inkEnd:12,settle:12.4,pre:13.6,hand:14.2,handEnd:15.7};
  const MARK=.26;   /* emblem radius as a share of the smaller screen side */
  /* network arrival, in network-clock seconds (1 real second = 1.18 on this clock) */
  const RATE=1.18,DOCK={at:1.4,travel:1.2,stagger:.08,stretch:.65,wordAt:1.75,wordTravel:1.05,done:3};
  const n=AGENTS.length,formAt=AGENTS.map((_,i)=>T.first+i*T.gap);
  const MONO='"Sohne Mono","IBM Plex Mono",ui-monospace,Menlo,monospace';
  let W,H,D,S;
  let start=null,fired=new Set(),landed=false,measured=false,netStart=0,docks=true;
  let full=null,wide=null,slot=null;
  function size(){D=Math.min(devicePixelRatio||1,2);W=cv.clientWidth||innerWidth;H=cv.clientHeight||innerHeight;S=Math.min(W,H);cv.width=W*D;cv.height=H*D;
    if(!start){c.setTransform(D,0,0,D,0,0);c.fillStyle="#14301f";c.fillRect(0,0,W,H)}}
  addEventListener("resize",()=>{if(!measured)size()});size();

  function finish(){document.body.classList.remove("intro","intrograph");
    graph.go(performance.now());
    if(reduce||docks)intro.remove();else{intro.classList.add("out");setTimeout(()=>intro.remove(),600)}
    window.dispatchEvent(new CustomEvent("intro:complete"))}
  if(reduce||/^#\/(?!overview)\w/.test(location.hash)){finish();return}

  const lerp=(a,b,t)=>a+(b-a)*t,cl=v=>Math.max(0,Math.min(1,v)),sm=(a,b,v)=>{const t=cl((v-a)/(b-a));return t*t*(3-2*t)};
  const eIO=t=>t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2,eOut=t=>1-Math.pow(1-t,3);
  /* cubic-bezier(.83,0,.17,1) */
  const bez=x=>{const f=(a,b,u)=>3*a*u*(1-u)*(1-u)+3*b*u*u*(1-u)+u*u*u;let lo=0,hi=1,u=x;for(let i=0;i<22;i++){if(f(.83,.17,u)<x)lo=u;else hi=u;u=(lo+hi)/2}return f(0,1,u)};
  const lerpRect=(a,b,q)=>({x:lerp(a.x,b.x,q),y:lerp(a.y,b.y,q),w:lerp(a.w,b.w,q),h:lerp(a.h,b.h,q),r:lerp(a.r,b.r,q)});
  const mid=r=>({x:r.x+r.w/2,y:r.y+r.h/2});

  /* ---- sound: synthesised, very quiet ---- */
  let ac=null,master,verb;
  function initAudio(){try{ac=new(window.AudioContext||window.webkitAudioContext)()}catch(e){return}
    master=ac.createGain();master.gain.value=.5;master.connect(ac.destination);
    const cv2=ac.createConvolver(),len=ac.sampleRate*3,b=ac.createBuffer(2,len,ac.sampleRate);
    for(let ch=0;ch<2;ch++){const d=b.getChannelData(ch);for(let i=0;i<len;i++)d[i]=(Math.random()*2-1)*Math.pow(1-i/len,3.2)}
    cv2.buffer=b;const wet=ac.createGain();wet.gain.value=.4;verb=ac.createGain();verb.connect(cv2);cv2.connect(wet);wet.connect(master)}
  const out=nd=>{nd.connect(master);nd.connect(verb)};
  function bubble(f,vol=.09){if(!ac)return;const t0=ac.currentTime+.01,lp=ac.createBiquadFilter();lp.type="lowpass";lp.frequency.value=2200;out(lp);
    [[1,2.3,2.05,vol,.34],[.5,.62,.62,vol*.45,.6]].forEach(([a,b2,c2,v,dur])=>{const o=ac.createOscillator(),g=ac.createGain();o.type="sine";
      o.frequency.setValueAtTime(f*a,t0);o.frequency.exponentialRampToValueAtTime(f*b2,t0+.085);o.frequency.exponentialRampToValueAtTime(f*c2,t0+.35);
      g.gain.setValueAtTime(.0001,t0);g.gain.exponentialRampToValueAtTime(v,t0+.012);g.gain.exponentialRampToValueAtTime(.0001,t0+dur);
      o.connect(g).connect(lp);o.start(t0);o.stop(t0+dur+.1)})}
  function whoosh(dur){if(!ac)return;const t0=ac.currentTime+.01,len=ac.sampleRate*(dur+.5),b=ac.createBuffer(1,len,ac.sampleRate),d=b.getChannelData(0);
    for(let i=0;i<len;i++)d[i]=Math.random()*2-1;const src=ac.createBufferSource();src.buffer=b;const bp=ac.createBiquadFilter();bp.type="bandpass";bp.Q.value=1.4;
    bp.frequency.setValueAtTime(260,t0);bp.frequency.exponentialRampToValueAtTime(1500,t0+dur);const g=ac.createGain();g.gain.setValueAtTime(.0001,t0);
    g.gain.exponentialRampToValueAtTime(.045,t0+dur*.8);g.gain.exponentialRampToValueAtTime(.0001,t0+dur+.4);src.connect(bp).connect(g);out(g);src.start(t0);src.stop(t0+dur+.5)}
  function pad(){if(!ac)return;const t0=ac.currentTime+.01,lp=ac.createBiquadFilter();lp.type="lowpass";lp.frequency.value=1100;out(lp);
    [130.8,196,261.6,329.6,392].forEach((f,i)=>[-4,4].forEach(det=>{const o=ac.createOscillator(),g=ac.createGain();o.type=i<2?"sine":"triangle";o.frequency.value=f;o.detune.value=det;
      g.gain.setValueAtTime(.0001,t0);g.gain.exponentialRampToValueAtTime(.02,t0+1.4);g.gain.setValueAtTime(.02,t0+2.6);g.gain.exponentialRampToValueAtTime(.0001,t0+7);o.connect(g).connect(lp);o.start(t0);o.stop(t0+7.2)}))}
  function chime(){if(!ac)return;const t0=ac.currentTime+.01;[1318.5,1975.5].forEach((f,i)=>{const o=ac.createOscillator(),g=ac.createGain();o.type="sine";o.frequency.value=f;
    g.gain.setValueAtTime(.0001,t0+i*.09);g.gain.exponentialRampToValueAtTime(.022,t0+i*.09+.01);g.gain.exponentialRampToValueAtTime(.0001,t0+i*.09+2.2);o.connect(g);out(g);o.start(t0+i*.09);o.stop(t0+2.5)})}
  const cues=[...formAt.map((ft,i)=>({t:ft+.02,fn:()=>bubble(NOTES[i],i?.075:.1)})),
    {t:T.unspool,fn:()=>whoosh(T.write-T.unspool)},{t:T.write,fn:()=>pad()},{t:T.inkEnd-.2,fn:()=>bubble(150,.15)},{t:T.handEnd-.15,fn:()=>{bubble(220,.08);chime()}}];

  function begin(){if(start)return;initAudio();if(ac&&ac.state==="suspended")ac.resume();gate.classList.add("hide");start=performance.now();requestAnimationFrame(frame)}
  gate.addEventListener("click",begin);gate.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();begin()}});gate.focus();
  skipB.addEventListener("click",()=>{if(!start){gate.classList.add("hide");start=performance.now();requestAnimationFrame(frame)}
    start=performance.now()-T.pre*1000;cues.forEach((q,i)=>{if(q.t<T.hand)fired.add(i)})});

  function panelPath(r){c.beginPath();c.roundRect(r.x,r.y,r.w,r.h,r.r)}
  function panelEdge(r){if(!docks||!r.r)return;c.strokeStyle="rgba(38,38,38,.2)";c.lineWidth=1;panelPath({x:r.x+.5,y:r.y+.5,w:r.w-1,h:r.h-1,r:r.r});c.stroke()}

  /* reveal the page behind the intro and work out where the panel has to land */
  function measure(){
    measured=true;
    document.body.classList.remove("intro");size();graph.sync();
    full={x:0,y:0,w:W,h:H,r:0};
    const g=graph.rect(),ov=$(".ov2").getBoundingClientRect();
    docks=innerWidth>1180;
    slot=docks?{x:g.left,y:g.top,w:g.width,h:g.height,r:8}:full;
    wide=docks?{x:ov.left,y:g.top,w:g.right-ov.left,h:g.height,r:8}:full;
  }
  /* the sidebar cards and the wordmark slide in from the left as the panel's edge moves right */
  function dock(){
    if(!docks)return;
    const toMs=s=>s/RATE*1000,N=20,frames=f=>Array.from({length:N+1},(_,i)=>({...f(i/N),offset:i/N}));
    const opts={delay:toMs(DOCK.at),duration:toMs(DOCK.travel),easing:"cubic-bezier(.83,0,.17,1)",fill:"backwards"};
    const travel=slot.x-(document.documentElement.clientWidth-slot.x-slot.w),fade=t=>{const q=cl(t/.5);return q*q*(3-2*q)};
    $$(".stack>.card").forEach((el,i)=>el.animate(frames(t=>({transform:`translateX(${(-1.11*travel*(1-t)).toFixed(2)}px)`,marginLeft:`${(-100*DOCK.stretch*Math.pow(1-t,1.5)).toFixed(2)}%`,opacity:fade(t)})),{...opts,delay:toMs(DOCK.at+i*DOCK.stagger)}));
    const w=$(".wordcol");if(w&&getComputedStyle(w).display!=="none")w.animate(frames(t=>({translate:`${(-140*(1-t)).toFixed(2)}px 0`,opacity:fade(t)})),{...opts,delay:toMs(DOCK.wordAt),duration:toMs(DOCK.wordTravel)});
  }

  /* ---- the story: one line runs through every icon, taking each one up as it goes,
          then sweeps around the screen and writes the logo. It is a single motion. ---- */
  const SAND=EMBLEM_COLOR,soft=x=>x*x*x*(x*(x*6-15)+10),ICON_LINE=.0056;
  if(document.fonts)document.fonts.load('700 40px Amiri');
  const sampleStroke=d=>{const p=document.createElementNS("http://www.w3.org/2000/svg","path");p.setAttribute("d",d);const L=p.getTotalLength(),k=Math.max(4,Math.round(L/2.4)),a=[];
    for(let i=0;i<=k;i++){const q=p.getPointAtLength(L*i/k);a.push([q.x-60,q.y-60])}return a};
  const iconStrokes=AGENT_ICONS.map(list=>list.map(sampleStroke));

  /* the single route: through the strokes of all eight icons, around the screen, through the pen strokes */
  let M=null;
  const ringPos=i=>{const a=-Math.PI/2+i*TAU/n;return[Math.cos(a)*S*.31,Math.sin(a)*S*.31]};
  function buildRoute(){
    const R=S*MARK,unit=S*.17/120,px=[],icons=[];let last=null,len=0;
    const add=(x,y,tag,pen)=>{if(last)len+=Math.hypot(x-last[0],y-last[1]);px.push([x,y,tag,pen]);last=[x,y]};
    iconStrokes.forEach((list,i)=>{
      const [ox,oy]=ringPos(i);let pool=list.map(s=>s.map(p=>[ox+p[0]*unit,oy+p[1]*unit]));
      /* take the strokes in the order a hand would: always the nearest next one */
      const ic={strokes:[],len:0,start:0};
      while(pool.length){
        const from=last||pool[0][0];let best=0,flip=false,d=1e12;
        pool.forEach((s,k)=>{const a=Math.hypot(s[0][0]-from[0],s[0][1]-from[1]),b=Math.hypot(s[s.length-1][0]-from[0],s[s.length-1][1]-from[1]);if(a<d){d=a;best=k;flip=false}if(b<d){d=b;best=k;flip=true}});
        const s=pool.splice(best,1)[0];if(flip)s.reverse();
        if(last&&!ic.strokes.length){/* a gentle arc over to the next icon */
          const [mx,my]=[(last[0]+s[0][0])/2,(last[1]+s[0][1])/2],q=Math.hypot(mx,my)||1,bow=d*.28,cx=mx+mx/q*bow,cy=my+my/q*bow,x0=last[0],y0=last[1];
          for(let k=1;k<24;k++){const u=k/24;add((1-u)*(1-u)*x0+2*u*(1-u)*cx+u*u*s[0][0],(1-u)*(1-u)*y0+2*u*(1-u)*cy+u*u*s[0][1],-2,0)}
        }
        if(!ic.strokes.length)ic.start=len;
        add(s[0][0],s[0][1],-2,0);const s0=len;
        for(let k=1;k<s.length;k++)add(s[k][0],s[k][1],-2,0);
        ic.strokes.push({s0,s1:len});ic.len+=len-s0;
      }
      icons.push(ic);
    });
    const iconEnd=len,ctrl=[],flight=[[last[0],last[1]],[-.2*W,-.3*H],[-.42*W,.02*H],[-.2*W,.36*H],[.18*W,.33*H],[.44*W,.05*H],[.36*W,-.3*H]];
    flight.forEach(p=>ctrl.push([p[0],p[1],-1]));
    EMBLEM_PEN.forEach(st=>st.pts.forEach(p=>ctrl.push([p[0]*R,p[1]*R,st.w])));
    const g=i=>ctrl[Math.max(0,Math.min(ctrl.length-1,i))];
    for(let i=0;i<ctrl.length-1;i++){
      const [p0,p1,p2,p3]=[g(i-1),g(i),g(i+1),g(i+2)],steps=24;
      for(let k=i?0:1;k<steps;k++){const u=k/steps,u2=u*u,u3=u2*u,f=(a,b,c,d)=>.5*(2*b+(c-a)*u+(2*a-5*b+4*c-d)*u2+(3*b-a-3*c+d)*u3);
        add(f(p0[0],p1[0],p2[0],p3[0]),f(p0[1],p1[1],p2[1],p3[1]),p1[2]===p2[2]?p1[2]:(p1[2]>0&&p2[2]>0?p1[2]:0),i>=flight.length?1:0)}
    }
    add(ctrl[ctrl.length-1][0],ctrl[ctrl.length-1][1],0,1);
    const step=3,xs=[],ys=[],tag=[];let acc=0,next=0,flyEnd=0;
    for(let i=0;i<px.length-1;i++){const a=px[i],b=px[i+1],seg=Math.hypot(b[0]-a[0],b[1]-a[1])||1e-6;
      while(next<=acc+seg){const q=(next-acc)/seg;xs.push(a[0]+(b[0]-a[0])*q);ys.push(a[1]+(b[1]-a[1])*q);tag.push(a[2]);if(!flyEnd&&a[3])flyEnd=next;next+=step}
      acc+=seg}
    /* the moving line follows a softened copy of the route, so tight corners never jerk */
    const blur=src=>{const r=Math.max(2,Math.round(S*.014/step));let a=src;for(let pass=0;pass<2;pass++){const o=new Float32Array(a.length);let sum=0;
      for(let i=-r;i<=r;i++)sum+=a[Math.max(0,i)];
      for(let i=0;i<a.length;i++){o[i]=sum/(2*r+1);sum+=a[Math.min(a.length-1,i+r+1)]-a[Math.max(0,i-r)]}a=o}return a};
    /* one continuous speed curve for the whole journey, gliding in and gliding out */
    const total=(xs.length-1)*step,v1=iconEnd/3.5,v2=(total-iconEnd)/5.8,times=new Float32Array(xs.length);let clock=0;
    for(let i=0;i<xs.length;i++){const s=i*step,v=lerp(v1,v2,soft(cl((s-iconEnd+S*.3)/(S*1.2))))*lerp(.16,1,soft(cl(s/(S*.9))))*lerp(.16,1,soft(cl((total-s)/(S*.9))));times[i]=clock;clock+=step/v}
    const k=(T.inkEnd-T.unspool)/clock;for(let i=0;i<times.length;i++)times[i]*=k;
    M={xs,ys,sx:blur(xs),sy:blur(ys),tag,step,total,flyEnd,iconEnd,icons,times};
    /* each small ornament of the logo blooms when the line passes closest to it */
    M.ornaments=EMBLEM.filter(f=>f.o).map(f=>{let cx=0,cy=0;for(let i=0;i<f.m.length;i+=2){cx+=f.m[i];cy+=f.m[i+1]}cx*=2*R/f.m.length;cy*=2*R/f.m.length;
      let best=1e12,at=M.flyEnd;for(let i=Math.floor(flyEnd/step);i<xs.length;i++){if(tag[i]<=0)continue;const q=(xs[i]-cx)**2+(ys[i]-cy)**2;if(q<best){best=q;at=i*step}}
      return{at,path:emblemShape([f])}});
  }
  const at=s=>{const q=cl(s/M.total)*(M.sx.length-1),i=Math.min(M.sx.length-2,Math.floor(q)),f=q-i;return[lerp(M.sx[i],M.sx[i+1],f),lerp(M.sy[i],M.sy[i+1],f)]};
  const headAt=t=>{const u=t-T.unspool,tm=M.times;if(u<=0)return 0;if(u>=tm[tm.length-1])return M.total;let lo=0,hi=tm.length-1;while(hi-lo>1){const m=(lo+hi)>>1;tm[m]<=u?lo=m:hi=m}return(lo+(u-tm[lo])/(tm[hi]-tm[lo]||1))*M.step};
  const NAME='Almanara';
  function drawName(alpha,x,y){
    const R=S*MARK;c.globalAlpha=alpha;c.fillStyle=SAND;c.textAlign="center";c.textBaseline="alphabetic";c.font=`700 ${Math.round(S*.06)}px "Amiri",Georgia,serif`;
    c.fillText(NAME,x,y+R*1.08+S*.075);c.globalAlpha=1;
  }

  /* the part of each icon the line has not reached yet */
  function drawIcons(t){
    const head=headAt(t);
    c.strokeStyle=SAND;c.lineJoin=c.lineCap="round";c.lineWidth=S*ICON_LINE;
    M.icons.forEach((ic,i)=>{
      const shown=(t-formAt[i])/T.drawFor;if(shown<=0)return;
      let room=ic.len*eOut(cl(shown));
      ic.strokes.forEach(st=>{
        const L=st.s1-st.s0,vis=Math.min(L,room);room-=L;if(vis<=0)return;
        const i0=Math.ceil(Math.max(st.s0,head)/M.step),i1=Math.floor((st.s0+vis)/M.step);if(i1<=i0)return;
        c.beginPath();c.moveTo(M.xs[i0],M.ys[i0]);for(let k=i0+1;k<=i1;k++)c.lineTo(M.xs[k],M.ys[k]);c.stroke();
      });
      const la=sm(0,.6,shown)*(1-sm(ic.start-S*.15,ic.start+S*.1,head));
      if(la>0){const [ox,oy]=ringPos(i);c.globalAlpha=la*.85;c.fillStyle="#fff";c.textAlign="center";c.textBaseline="alphabetic";c.font=`300 ${Math.max(10.5,S*.014)}px ${MONO}`;
        c.fillText(`${String(i+1).padStart(2,"0")} ${AGENTS[i].short}`,ox,oy+S*.085+Math.max(16,S*.026));c.globalAlpha=1}
    });
  }
  /* the travelling line: as wide as the icon strokes at first, thickening as it goes */
  function drawLine(t){
    const head=headAt(t),base=lerp(S*.55,S*1.25,soft(cl((head-M.iconEnd+S*.4)/(S*1.6)))),fade=1-soft(cl(((head-M.flyEnd)/(M.total-M.flyEnd)-.3)/.7)),L=Math.min(head,base*fade*soft(cl(head/(S*.4))));
    if(L<6)return;
    const half=lerp(S*ICON_LINE/2,S*.0078,soft(cl(head/M.flyEnd))),count=Math.max(8,Math.round(L/6)),left=[],right=[];
    for(let i=0;i<=count;i++){
      const f=i/count,s=head-L*(1-f),[x,y]=at(s),[ax,ay]=at(s-5),[bx,by]=at(s+5),dl=Math.hypot(bx-ax,by-ay)||1,nx=-(by-ay)/dl,ny=(bx-ax)/dl;
      const w=half*Math.pow(cl(f/.25),.7)*Math.pow(cl((1-f)/.02),.5);
      left.push([x+nx*w,y+ny*w]);right.push([x-nx*w,y-ny*w]);
    }
    c.fillStyle=SAND;c.beginPath();left.forEach((p,i)=>i?c.lineTo(p[0],p[1]):c.moveTo(p[0],p[1]));right.reverse().forEach(p=>c.lineTo(p[0],p[1]));c.closePath();c.fill();
  }
  /* the logo appears only where the pen has already passed */
  let ink=null,inkC=null;
  function drawInk(t){
    if(!ink||ink.width!==Math.round(W*D)||ink.height!==Math.round(H*D)){ink=document.createElement("canvas");ink.width=Math.round(W*D);ink.height=Math.round(H*D);inkC=ink.getContext("2d")}
    const R=S*MARK,head=headAt(t),last=Math.min(M.xs.length-1,Math.floor(head/M.step));
    inkC.setTransform(1,0,0,1,0,0);inkC.globalCompositeOperation="source-over";inkC.clearRect(0,0,ink.width,ink.height);
    inkC.setTransform(D,0,0,D,W/2*D,H/2*D);inkC.strokeStyle="#000";inkC.lineCap=inkC.lineJoin="round";
    let i=Math.floor(M.flyEnd/M.step);
    while(i<last){
      const w=M.tag[i];
      if(w<=0){i++;continue}
      inkC.beginPath();inkC.moveTo(M.xs[i],M.ys[i]);
      while(i<last&&M.tag[i]===w){i++;inkC.lineTo(M.xs[i],M.ys[i])}
      inkC.lineWidth=w*R;inkC.stroke();
    }
    inkC.globalCompositeOperation="source-in";inkC.fillStyle=EMBLEM_COLOR;inkC.save();inkC.scale(R,R);inkC.fill(emblemMainOutline());inkC.restore();
    inkC.globalCompositeOperation="source-over";inkC.save();inkC.scale(R,R);
    M.ornaments.forEach(o=>{const a=soft(cl((head-o.at)/(S*.5)));if(a>0){inkC.globalAlpha=a;inkC.fill(o.path)}});
    inkC.restore();inkC.globalAlpha=1;
    c.drawImage(ink,-W/2,-H/2,W,H);
  }
  function drawStory(t){
    if(!M)buildRoute();
    const bloom=sm(T.settle-.35,T.settle+.15,t)*(1-sm(T.settle+.15,T.settle+1.2,t));
    if(t>=T.settle){if(bloom>0)drawEmblem(c,0,0,S*MARK,bloom);drawEmblem(c,0,0,S*MARK);const na=sm(T.settle,T.settle+.75,t);if(na>0)drawName(na,0,0);return}
    const head=headAt(t);
    if(head<M.iconEnd)drawIcons(t);
    if(head>M.flyEnd)drawInk(t);
    if(bloom>0)drawEmblem(c,0,0,S*MARK,bloom);
    const fin=sm(T.inkEnd-.2,T.settle,t);
    if(fin>0)drawEmblem(c,0,0,S*MARK,fin);
    if(t>=T.unspool)drawLine(t);
  }

  function frame(now){
    if(landed)return;requestAnimationFrame(frame);
    const t=(now-start)/1000;
    cues.forEach((q,i)=>{if(t>=q.t&&!fired.has(i)){fired.add(i);q.fn()}});

    if(t>=T.pre&&!measured)measure();

    /* ---- the network arrives ---- */
    if(t>=T.hand){
      if(!netStart){netStart=now;graph.start(S*MARK);skipB.style.display="none";dock()}
      const k=(now-netStart)/1000*RATE,e=k<DOCK.at?0:bez(cl((k-DOCK.at)/DOCK.travel)),r=lerpRect(wide,slot,e),a=mid(wide),b=mid(slot);
      c.setTransform(D,0,0,D,0,0);c.clearRect(0,0,W,H);c.save();panelPath(r);c.clip();c.fillStyle="#14301f";c.fillRect(r.x,r.y,r.w,r.h);
      graph.render(c,lerp(a.x,b.x,e),lerp(a.y,b.y,e),Math.min(k,DOCK.done),now/1000);{const na=1-sm(0,.5,k);if(na>0)drawName(na,lerp(a.x,b.x,e),lerp(a.y,b.y,e))}c.restore();panelEdge(r);
      if(k>=DOCK.done){landed=true;finish()}
      return;
    }

    /* just before the hand-off the emblem eases to the centre of the panel it is about to fill */
    const pq=measured?eIO(sm(T.pre,T.hand,t)):0,clip=measured?lerpRect(full,wide,pq):null,to=measured?mid(wide):{x:W/2,y:H/2},cx=lerp(W/2,to.x,pq),cy=lerp(H/2,to.y,pq);
    c.setTransform(D,0,0,D,0,0);c.clearRect(0,0,W,H);c.save();
    if(clip){panelPath(clip);c.clip();c.fillStyle="#14301f";c.fillRect(clip.x,clip.y,clip.w,clip.h)}else{c.fillStyle="#14301f";c.fillRect(0,0,W,H)}
    c.translate(cx,cy);
    drawStory(t);
    c.restore();
  }
})();
