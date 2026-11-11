/* =========================================================
   DATA
   ========================================================= */
const AGENTS = [
  {n:1,name:"Inter-Department & Risk Tier",short:"Risk tier",desc:"Assigns a risk tier and checks the registry for a model that's already approved for the same context.",load:"4 running"},
  {n:2,name:"Compliance & Governance",short:"Compliance",desc:"Maps every UAE AI framework and data-protection rule to evidence.",load:"6 running"},
  {n:3,name:"Evaluation Test Creator",short:"Test creator",desc:"Puts provider benchmarks into one standard format and flags missing information as risk.",load:"3 running"},
  {n:4,name:"Testing & Red Team",short:"Red team",desc:"Tests performance, hallucination, prompt injection, data leakage and supplier dependency.",load:"5 running"},
  {n:5,name:"User Testing",short:"User testing",desc:"Tests Arabic scenarios, fairness, accessibility and contestability, and collects frontline staff feedback.",load:"5 running"},
  {n:6,name:"Concluder",short:"Concluder",desc:"Combines the results into a plain-language Assurance Package. It recommends but doesn't decide.",load:"2 running"},
  {n:7,name:"Approval & Accountability",short:"Approval",desc:"Sends the package to every reviewer at once, tracks concerns and records the named approver.",load:"7 awaiting humans"},
  {n:8,name:"Lifecycle Monitor",short:"Monitor",desc:"Always on. Watches deployment conditions and sends the model back for re-checks when something changes.",load:"11 models watched"},
];

/* Departments. Each system: [name, tier, stage (1-8 = agent currently handling it), model] */
const DEPTS = [
  {code:"DGE",short:"Enablement",name:"Department of Government Enablement",systems:[["Meeting minutes drafter","low",7,"Registry · GovLLM-S"],["Policy document search","low",8,"Registry · GovLLM-S"],["Procurement clause checker","medium",4,"Anthropic"],["HR policy assistant","low",8,"Registry · GovLLM-S"],["Service desk triage","medium",2,"Microsoft"]]},
  {code:"MOHAP",short:"Health",name:"Ministry of Health & Prevention",systems:[["Clinic appointment router","high",4,"G42 / Core42"],["Discharge summary drafter","high",6,"G42 / Core42"],["Medical licence FAQ","medium",8,"Registry · Tawasul v2.1"],["Lab report translator","high",3,"Open-weights"]]},
  {code:"MOHRE",short:"Human Resources",name:"Ministry of Human Resources & Emiratisation",systems:[["Benefit eligibility triage","high",6,"Anthropic"],["Labour complaint classifier","medium",5,"Microsoft"],["Work permit FAQ","low",8,"Registry · Tawasul v2.1"],["Contract clause extractor","medium",8,"Google"],["Inspection report summariser","medium",1,"OpenAI"],["Wage protection anomaly detector","high",4,"Open-weights"]]},
  {code:"ICP",short:"Identity",name:"Federal Authority for Identity & Citizenship",systems:[["Visa FAQ assistant","medium",7,"Registry · Tawasul v2.1"],["Document data extractor","high",5,"G42 / Core42"],["Application router","medium",8,"Microsoft"],["Residency letter drafter","medium",2,"Anthropic"]]},
  {code:"RTA",short:"Transport",name:"Roads & Transport Authority",systems:[["Traffic fine explainer","medium",8,"Registry · Tawasul v2.1"],["Licence renewal assistant","low",8,"Registry · GovLLM-S"],["Incident report summariser","medium",4,"Google"],["Route complaint classifier","low",3,"Microsoft"],["Parking appeal triage","medium",7,"Anthropic"]]},
  {code:"MOI",short:"Interior",name:"Ministry of Interior",systems:[["Lost-item report intake","low",8,"Registry · GovLLM-S"],["Call transcript summariser","high",5,"Open-weights"],["Permit enquiry assistant","medium",6,"G42 / Core42"]]},
  {code:"MOE",short:"Education",name:"Ministry of Education",systems:[["Curriculum Q&A for teachers","low",8,"Registry · GovLLM-S"],["Scholarship eligibility helper","high",3,"Anthropic"],["Certificate attestation FAQ","low",8,"Registry · Tawasul v2.1"],["Student feedback analyser","medium",4,"Google"]]},
  {code:"MOF",short:"Finance",name:"Ministry of Finance",systems:[["Invoice anomaly detector","high",4,"Open-weights"],["Budget circular search","low",8,"Registry · GovLLM-S"],["Tax enquiry assistant","medium",5,"Microsoft"],["Grant application summariser","medium",1,"OpenAI"],["Vendor due-diligence drafter","high",2,"Anthropic"]]},
];
const ENTITIES = DEPTS.map(d=>d.name);
const sysStatus = s => s[2]===8?"Deployed · monitored":s[2]===7?"Awaiting sign-off":`With Agent ${s[2]} · ${AGENTS[s[2]-1].short}`;

/* Lab sections. score = contribution to risk tier. k = keywords used when reading an uploaded text file. */
const LAB = [
  {id:"entity",title:"Entity & owner",q:"Who owns this use case and is accountable for it?",type:"entity",req:true},
  {id:"purpose",title:"Purpose",q:"What will the AI do? Pick all that apply.",type:"multi",req:true,opts:[
    {v:"Answer citizen FAQs",k:["faq","questions","enquir","inquir"]},{v:"Summarise case files",k:["summar"]},
    {v:"Classify & route applications",k:["classif","route","triage"]},{v:"Draft official correspondence",k:["draft","letter","correspond"]},
    {v:"Translate Arabic ↔ English",k:["translat"]},{v:"Detect fraud & anomalies",k:["fraud","anomal"],s:1},
    {v:"Recommend eligibility decisions",k:["eligib","recommend"],s:2},{v:"Extract data from documents",k:["extract","ocr"]}]},
  {id:"users",title:"Affected users",q:"Who is affected by the outputs? Include groups who need extra care.",type:"multi",req:true,opts:[
    {v:"Citizens",k:["citizen"]},{v:"Residents",k:["resident"]},{v:"Businesses",k:["business","compan"]},
    {v:"Arabic speakers",k:["arabic"]},{v:"People with disabilities",k:["disab","accessib"],s:1},
    {v:"Low digital literacy",k:["literacy","elderly"],s:1},{v:"Minors",k:["minor","child","student"],s:2},
    {v:"Frontline staff",k:["frontline","staff","employee"]},{v:"Internal analysts",k:["analyst"]}]},
  {id:"data",title:"Data sensitivity",q:"What's the most sensitive data the model will see?",type:"single",req:true,opts:[
    {v:"Public",s:0,k:["public data"]},{v:"Internal",s:1,k:["internal"]},{v:"Confidential",s:2,k:["confidential"]},
    {v:"Personal data (PII)",s:3,k:["personal","pii","emirates id"]},{v:"Sensitive personal",d:"health, biometric",s:4,k:["health","biometric","medical"]}]},
  {id:"authority",title:"Authority",q:"How much authority does the AI have over outcomes?",type:"scale",req:true,opts:[
    {v:"Informs",d:"Gives information only",s:0,k:["inform"]},{v:"Recommends",d:"A human makes the decision",s:1.5,k:["recommend"]},
    {v:"Decides",d:"A human reviews afterwards",s:3,k:["decide","approve"]},{v:"Acts alone",d:"No human in the loop",s:4.5,k:["autonom","automatic"]}]},
  {id:"impact",title:"Consequence of errors",q:"What is the worst realistic outcome if the AI is wrong?",type:"single",req:true,opts:[
    {v:"Minor inconvenience",s:0},{v:"Service delay",s:1,k:["delay"]},{v:"Financial loss",s:2,k:["financ","payment","fine"]},
    {v:"Legal or rights impact",s:3,k:["legal","rights","appeal"]},{v:"Health or safety impact",s:4,k:["safety","patient"]}]},
  {id:"oversight",title:"Human oversight",q:"How will people check the AI's outputs?",type:"scale",req:true,opts:[
    {v:"Every output",d:"A human reviews all outputs",s:0,k:["every output","all outputs"]},{v:"Low confidence",d:"Review when unsure",s:1,k:["low confidence","low-confidence"]},
    {v:"Spot checks",d:"Periodic sampling",s:2,k:["spot","sampl"]},{v:"None",d:"Fully automated",s:3}]},
  {id:"lang",title:"Languages",q:"Which languages must it handle well?",type:"multi",opts:[
    {v:"Arabic (MSA)",k:["arabic"]},{v:"Gulf dialect",k:["dialect","emirati"]},{v:"English",k:["english"]},
    {v:"Urdu",k:["urdu"]},{v:"Hindi",k:["hindi"]},{v:"Tagalog",k:["tagalog","filipino"]}]},
  {id:"thr",title:"Pass / fail threshold",q:"The longest the model may take to respond. Anything slower fails.",type:"thresholds"},
  {id:"model",title:"Candidate model",q:"Optional. Leave this empty if you want Agent 1 to suggest an approved model from the registry first.",type:"model"},
];
const THR = [
  {id:"lat",label:"Max response time",min:1,max:10,def:3,u:"s"},
];
const DOCS = ["Model card","Provider benchmarks","Licence & terms","Data residency statement"];
const PROVIDERS = ["OpenAI","Anthropic","Google","Microsoft","G42 / Core42","Open-weights (self-hosted)","Other"];
