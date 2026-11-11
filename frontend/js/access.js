/* =========================================================
   ACCESS: the first screen, and what each role may see and do.

   Director         every department; approve, pause, re-check; value figures
   Department head  own department; approve, pause, re-check; value figures
   Employee         own department; start and follow use cases; view only

   A department role sees only its own department because the shared
   records are cut down to it (see scope), so every page follows.
   The Registry's approved models and lessons stay shared: reuse
   between departments is what the Registry is for.

   There are no passwords: this controls what the page shows. The
   backend separately enforces who can approve or act on a department.
   ========================================================= */
const ACCESS_DEPT = { code: "TRF", sample: "RTA", name: "Traffic & Fines Department", short: "Traffic & Fines" };
const FULL_ACCESS = { approve: true, act: true, value: true, registry: true };
const ROLES = {
  director: {
    label: "Director", name: "Mariam Al Mansoori", title: "Director, Digital Services", dept: null,
    email: "registry.admin@registry.gov.example", can: FULL_ACCESS,
    grants: ["All departments", "Approve, pause and re-check", "Registry and value figures"],
  },
  head: {
    label: "Department head", name: "Sultan Al Dhaheri", title: "Head of Traffic Services", dept: ACCESS_DEPT,
    email: "sultan.aldhaheri@trf.gov.example", can: FULL_ACCESS,
    grants: [`${ACCESS_DEPT.short} only`, "Approve, pause and re-check", "Registry and value figures"],
  },
  employee: {
    label: "Employee", name: "Imran Qureshi", title: "Violation Review Officer", dept: ACCESS_DEPT,
    email: "imran.qureshi@trf.gov.example", can: { approve: false, act: false, value: false, registry: false },
    grants: [`${ACCESS_DEPT.short} only`, "Start and follow use cases", "View only, no approvals"],
  },
};

const ACCESS = (() => {
  const KEY = "almanara.role";
  const stored = () => { try { return sessionStorage.getItem(KEY); } catch { return null; } };
  const keep = (list, test) => { const kept = list.filter(test); list.length = 0; list.push(...kept); };
  const access = {
    user: ROLES[stored()] || null,
    dept: null,
    can: what => !!(access.user && access.user.can[what]),
    /* whether a system belongs to what this person may open */
    sees: system => !access.dept || system.dept === access.dept,

    /* Cut the shared records down to the signed-in department. Runs again whenever new data is loaded. */
    scope() {
      access.dept = null;
      const want = access.user && access.user.dept;
      if (!want) return;
      const own = DEPTS.find(d => d.code === want.code) || DEPTS.find(d => d.code === want.sample);
      /* the sample data's nearest department stands in until the backend's records load */
      Object.assign(own, { code: want.code, name: want.name, short: want.short });
      const index = DEPTS.indexOf(own);
      keep(ASSESSMENTS, a => a.d === index);
      ASSESSMENTS.forEach(a => { a.d = 0; });
      keep(SYSTEMS, s => s.dept === own);
      keep(LIVE, s => s.dept === own);
      SYSTEMS.forEach(s => { s.d = 0; });
      keep(DEPTS, d => d === own);
      ENTITIES.length = 0; ENTITIES.push(own.name);
      AGENTS.forEach((a, i) => { const n = SYSTEMS.filter(s => s.stage === i + 1).length; a.load = i === 7 ? `${LIVE.length} systems watched` : i === 6 ? `${n} awaiting humans` : `${n} with this agent`; });
      access.dept = own;
    },
    signIn(key) {
      access.user = ROLES[key];
      try { sessionStorage.setItem(KEY, key); } catch {}
      access.scope();
      const el = document.getElementById("login");
      setLocked(false);
      el.classList.add("out");
      setTimeout(() => el.remove(), 600);
      window.dispatchEvent(new Event("access:login"));
    },
    signOut() {
      try { sessionStorage.clear(); } catch {}
      history.replaceState(null, "", location.pathname + location.search);
      location.reload();
    },
  };
  /* the page behind the sign-in screen can't be reached by keyboard */
  const setLocked = on => document.querySelectorAll("header.top,main").forEach(el => { el.inert = on; });

  const login = document.getElementById("login");
  if (access.user) login.remove();
  else {
    setLocked(true);
    login.innerHTML = `<div class="lg-in">
      <div class="lg-brand"><span class="orb" data-emblem></span><b>Almanara</b><p>Choose how you want to log in</p></div>
      <div class="lg-roles">${Object.entries(ROLES).map(([key, r]) => `<button class="lg-card" data-role="${key}">
        <span class="lg-role">${r.label}</span>
        <span class="lg-name">${r.name}</span>
        <span class="lg-title">${r.title}${r.dept ? `<br>${r.dept.name}` : ""}</span>
        <ul>${r.grants.map(g => `<li>${g}</li>`).join("")}</ul>
        <span class="lg-go">Log in →</span>
      </button>`).join("")}</div>
    </div>`;
    login.addEventListener("click", e => { const b = e.target.closest("[data-role]"); if (b) access.signIn(b.dataset.role); });
    login.querySelector("button").focus({ preventScroll: true });
  }
  return access;
})();
ACCESS.scope();
