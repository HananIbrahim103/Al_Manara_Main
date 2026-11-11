/* =========================================================
   The eight agent icons as line art, on a 120 x 120 grid.
   Each entry is a list of separate strokes (SVG path data).
   ========================================================= */
const AGENT_ICONS = (() => {
  const circle = (cx, cy, r) => `M${cx + r} ${cy}a${r} ${r} 0 1 1 ${-2 * r} 0a${r} ${r} 0 1 1 ${2 * r} 0z`;
  const box = (x, y, w, h, r) => `M${x + r} ${y}h${w - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 ${-r} ${r}h${-(w - 2 * r)}a${r} ${r} 0 0 1 ${-r} ${-r}v${-(h - 2 * r)}a${r} ${r} 0 0 1 ${r} ${-r}z`;
  return [
    /* 1 Risk tier: a gauge */
    ["M12 78a48 48 0 0 1 96 0H88a28 28 0 0 0-56 0z", "M47 55.5L35 34.7", "M73 55.5l12-20.8", "M76.7 58.1L63.4 80.9 56.6 75.1z", circle(60, 78, 8.5), box(30, 93, 60, 7, 3.5)],
    /* 2 Compliance: a raised fist holding scales */
    ["M17 49L6 84", "M17 49l11 35", "M103 36L92 71", "M103 36l11 35", "M21 46.5L41 44", "M79 41.5l20-2.500", circle(17, 47, 4.2), circle(103, 36, 4.2), "M3 84h28c0 7-6 11-14 11S3 91 3 84z", "M89 71h28c0 7-6 11-14 11s-14-4-14-11z",
      "M43 60c0 8 6 13 7 21l1 28a6 6 0 0 0 6 5.7h6a6 6 0 0 0 6-5.7l1-28c1-8 7-13 7-21", box(41, 30, 10, 24, 5), box(50.3, 27, 10, 27, 5), box(59.7, 27, 10, 27, 5), box(69, 30, 10, 24, 5),
      "M46 49.5h22.500a5.200 5.200 0 0 1 0 10.400H53c-5 0-10-2.500-11-6.500-.5-2.200 1.400-3.900 4-3.900z"],
    /* 3 Test creator: a clipboard checklist */
    ["M43 16H34a8 8 0 0 0-8 8v80a8 8 0 0 0 8 8h52a8 8 0 0 0 8-8V24a8 8 0 0 0-8-8h-9", box(43, 7, 34, 19, 5.5), "M37 46l5 5 8.5-10", "M60 46.5h23", "M37 67l5 5 8.5-10", "M60 67.5h23", "M44 83v13", "M37.5 89.5h13", "M60 89.5h23"],
    /* 4 Red team: a crosshair target */
    [circle(60, 60, 40), circle(60, 60, 26), circle(60, 60, 11), "M60 7v24", "M60 89v24", "M7 60h24", "M89 60h24"],
    /* 5 User testing: a person and a speech bubble */
    [circle(44, 54, 18), "M10 110c0-23 15-36 34-36s34 13 34 36z", "M72 10h32a9 9 0 0 1 9 9v22a9 9 0 0 1-9 9H85L72 62V50a9 9 0 0 1-9-9V19a9 9 0 0 1 9-9z", circle(76, 30, 3.5), circle(88, 30, 3.5), circle(100, 30, 3.5)],
    /* 6 Concluder: a report with a seal */
    ["M61 108H22V7h48l26 26v31", "M70 7v26h26", "M34 48h46", "M34 62h20", "M34 76h16", circle(82, 84, 21), "M71 102l-5 16 16-7 16 7-5-16", "M73 84l6.5 6.5L92 77"],
    /* 7 Approval: a pen nib and a signature */
    [box(42, 6, 36, 13, 3.5), "M41 24h38l13 30-32 45-32-45z", "M60 97V61.500", circle(60, 54, 7.5), "M13 110c7-11 13 4 21-1s11-5 15 0", "M71 110h36"],
    /* 8 Monitor: an eye and a looping arrow */
    ["M7 48c15-26 33-37 53-37s38 11 53 37c-15 26-33 37-53 37S22 74 7 48z", circle(60, 48, 22), circle(60, 48, 10), "M26 99c20 13 46 13 66 0", "M84 92.500l8 6.500-3.500 10"],
  ];
})();

/* Deployment is a step rather than an agent, but it appears beside them. */
const DEPLOY_ICON = ["M60 10c16 12 24 30 24 50v22H36V60c0-20 8-38 24-50z", "M69 46a9 9 0 1 1-18 0a9 9 0 1 1 18 0z", "M36 66L20 86v14l16-8", "M84 66l16 20v14l-16-8", "M50 92v14", "M60 92v22", "M70 92v14"];
const agentIconSVG = a => `<svg viewBox="0 0 120 120" aria-hidden="true">${(a.n === "D" ? DEPLOY_ICON : AGENT_ICONS[a.n - 1]).map(d => `<path d="${d}"/>`).join("")}</svg>`;
const agentIcon = (a, cls = "", title = "") => `<span class="orb${cls ? " " + cls : ""}"${title ? ` title="${title}"` : ""}>${agentIconSVG(a)}</span>`;

let agentIconPaths = null;
function drawAgentIcon(g, x, y, r, a, alpha) {
  if (r < .5 || alpha < .004) return;
  agentIconPaths = agentIconPaths || AGENT_ICONS.map(list => list.map(d => new Path2D(d)));
  const s = r / 60;
  g.save(); g.globalAlpha = alpha; g.fillStyle = "#14301f"; g.beginPath(); g.arc(x, y, r * 1.14, 0, Math.PI * 2); g.fill();
  g.translate(x - 60 * s, y - 60 * s); g.scale(s, s); g.strokeStyle = EMBLEM_COLOR; g.lineJoin = g.lineCap = "round"; g.lineWidth = Math.min(2.2, Math.max(1.2, r * .1)) / s;
  agentIconPaths[a].forEach(p => g.stroke(p)); g.restore();
}

/* The same icons in the evaluation pipeline's disc, which carries the run states. */
const lineIcon = (a, cls = "") => `<span class="lic${cls ? " " + cls : ""}" aria-hidden="true">${agentIconSVG(a)}</span>`;
