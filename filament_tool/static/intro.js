// PixxelSpool intro: an animated tour of the principle, shown as a card in the setup wizard.
// Pure SVG with a tiny cancellable tween engine, no library. Texts go through L() like the rest of the app.
// mountIntro(host) builds the player into host and returns a function that stops it.
function mountIntro(host) {

const NS = "http://www.w3.org/2000/svg", PB = "PLA Basic ", S23 = "S-2-3";   // kept outside L() so they are not taken as texts
host.classList.add("ps-intro");
host.innerHTML = `<nav class="pi-bars" aria-label="${esc(L("Chapters"))}"></nav>
  <div class="pi-stage"><svg viewBox="0 0 400 260" role="img" aria-label="${esc(L("Animated tour of PixxelSpool"))}"></svg></div>
  <p class="pi-cap" aria-live="polite"></p>
  <div class="pi-ctl">
    <button type="button" data-c="replay" title="${esc(L("Start over"))}" aria-label="${esc(L("Start over"))}"><svg viewBox="0 0 24 24"><path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 4v4.5H9"/></svg></button>
    <button type="button" data-c="prev" title="${esc(L("One step back"))}" aria-label="${esc(L("One step back"))}"><svg viewBox="0 0 24 24"><path d="M14.5 6l-6 6 6 6"/></svg></button>
    <button type="button" data-c="pause" class="big" title="${esc(L("Pause"))}" aria-label="${esc(L("Pause"))}" aria-pressed="false"><svg viewBox="0 0 24 24"><path class="ico-pause" d="M9 6.5v11M15 6.5v11"/><path class="ico-play" d="M8.5 6.2v11.6L18 12z"/></svg></button>
    <button type="button" data-c="next" title="${esc(L("One step forward"))}" aria-label="${esc(L("One step forward"))}"><svg viewBox="0 0 24 24"><path d="M9.5 6l6 6-6 6"/></svg></button>
    <button type="button" data-c="slow" class="txt" title="${esc(L("Half speed"))}" aria-label="${esc(L("Half speed"))}" aria-pressed="false">0.5×</button>
  </div>`;
const root = host.querySelector("svg"), $c = (c) => host.querySelector(`[data-c="${c}"]`);
const CALM = matchMedia("(prefers-reduced-motion: reduce)").matches;
let sv = root;
const el = (tag, attrs = {}, parent = sv) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent.append(e); return e; };
const txt = (s, attrs, parent) => { const t = el("text", attrs, parent); t.textContent = s; return t; };

// ---------------------------------------------------------------- animation core (cancellable)
const STOP = Symbol("stop");
let gen = 0, SLOW = 1, PAUSED = false, pausedAt = 0, lost = 0;
let FF = 0, stepNo = 0;                                 // fast-forward until caption number FF
const frame1 = () => new Promise((r) => requestAnimationFrame(r));
const now = () => (PAUSED ? pausedAt : performance.now()) - lost;
const E = {
  io: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  out: (t) => 1 - Math.pow(1 - t, 3),
  spring: (t) => 1 - Math.cos(t * Math.PI * 2.2) * Math.exp(-5.5 * t),
  lin: (t) => t,
};
function tween(o, to, dur, { e = E.io, delay = 0, arc = 0, set = null } = {}) {
  const my = gen; dur *= SLOW; delay *= SLOW; if (CALM) { dur = 1; delay = 0; }
  if (FF) { for (const p in to) o[p] = to[p]; (set || o.draw)(o); return Promise.resolve(); }
  return new Promise((res, rej) => {
    const from = {}; for (const k in to) from[k] = o[k];
    const t0 = now() + delay;
    const step = () => {
      if (my !== gen) return rej(STOP);
      const t = Math.min(1, Math.max(0, (now() - t0) / dur)), k = e(t);
      for (const p in to) o[p] = from[p] + (to[p] - from[p]) * k;
      if (arc) o.y -= arc * 4 * t * (1 - t);
      (set || o.draw)(o);
      if (t < 1) requestAnimationFrame(step); else res();
    };
    requestAnimationFrame(step);
  });
}
const wait = (ms) => {
  if (FF) return Promise.resolve();
  const my = gen, end = now() + (CALM ? Math.min(ms, 1200) : ms * SLOW);
  return new Promise((res, rej) => { const tick = () => (my !== gen ? rej(STOP) : now() >= end ? res() : requestAnimationFrame(tick)); tick(); });
};
const go = (p) => p.catch(() => {});                  // fire and forget
const val = (v, set) => ({ v, draw: set });            // animated number with a setter
const fade = (node, to, dur = 400, delay = 0) => { const o = val(+(node.getAttribute("opacity") ?? 1), (q) => node.setAttribute("opacity", q.v)); return tween(o, { v: to }, dur, { delay }); };

// ---------------------------------------------------------------- shared look
const SP = [
  { c: "#e5483e", n: L("Red"), no: "10200", l: "PLA Basic" }, { c: "#2f6fdb", n: L("Blue"), no: "10601", l: "PLA Basic" },
  { c: "#f4c430", n: L("Yellow"), no: "10400", l: "PLA Basic" }, { c: "#3fae5a", n: L("Green"), no: "10501", l: "PLA Basic" },
  { c: "#f3f3ef", n: L("Jade White"), no: "10100", l: "PLA Basic" }, { c: "#222225", n: L("Black"), no: "11101", l: "PLA Matte" },
  { c: "#ff7a1a", n: L("Orange"), no: "10300", l: "PLA Basic" }, { c: "#8b4fd8", n: L("Purple"), no: "10700", l: "PLA Basic" },
  { c: "#18a7b5", n: L("Cyan"), no: "10603", l: "PETG HF" }, { c: "#f06292", n: L("Pink"), no: "10203", l: "PLA Basic" },
  { c: "#8fd3b6", n: L("Mint"), no: "Sunlu", l: "PLA+" },
];
const lum = (hex) => { const n = parseInt(hex.slice(1), 16); return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255; };
function defs() {
  const d = el("defs");
  // front highlight: soft light from the top left, darker rim
  const rg = el("radialGradient", { id: "pi-gFront", cx: "38%", cy: "32%", r: "75%" }, d);
  el("stop", { offset: "0", "stop-color": "#fff", "stop-opacity": ".38" }, rg);
  el("stop", { offset: ".55", "stop-color": "#fff", "stop-opacity": "0" }, rg);
  el("stop", { offset: "1", "stop-color": "#000", "stop-opacity": ".28" }, rg);
  // cylinder shading for a lying spool
  const lg = el("linearGradient", { id: "pi-gSide", x1: "0", x2: "1", y1: "0", y2: "0" }, d);
  [["0", "#000", ".30"], [".25", "#fff", ".22"], [".5", "#fff", "0"], ["1", "#000", ".32"]].forEach(([o, c, a]) => el("stop", { offset: o, "stop-color": c, "stop-opacity": a }, lg));
  const fl = el("linearGradient", { id: "pi-gFlange", x1: "0", x2: "1", y1: "0", y2: "1" }, d);
  el("stop", { offset: "0", "stop-color": "#4a4a50" }, fl); el("stop", { offset: "1", "stop-color": "#17171a" }, fl);
  const sh = el("filter", { id: "pi-fShadow", x: "-30%", y: "-30%", width: "160%", height: "170%" }, d);
  el("feDropShadow", { dx: "0", dy: "1.6", stdDeviation: "1.6", "flood-color": "#000", "flood-opacity": ".22" }, sh);
  const sh2 = el("filter", { id: "pi-fCard", x: "-10%", y: "-10%", width: "120%", height: "130%" }, d);
  el("feDropShadow", { dx: "0", dy: "3", stdDeviation: "5", "flood-color": "#000", "flood-opacity": ".10" }, sh2);
}
// a spool: upright front view and lying side view, crossfaded by "flat"
function spool(i, x, y, { flat = 0, rot = 0, s = 1, parent = sv } = {}) {
  const c = SP[i].c, g = el("g", { filter: "url(#pi-fShadow)" }, parent);
  const up = el("g", {}, g);
  el("circle", { r: 18, fill: "url(#pi-gFlange)" }, up);
  el("circle", { r: 15.6, fill: c }, up);
  [13.4, 11.2, 9.4].forEach((r) => el("circle", { r, fill: "none", stroke: "#000", "stroke-opacity": ".07", "stroke-width": ".7" }, up));
  el("circle", { r: 15.6, fill: "url(#pi-gFront)" }, up);
  el("circle", { r: 7.6, fill: "url(#pi-gFlange)" }, up);
  [0, 60, 120].forEach((a) => el("rect", { x: -0.7, y: -7.2, width: 1.4, height: 14.4, rx: .7, fill: "#5a5a60", transform: `rotate(${a})` }, up));
  el("circle", { r: 3.1, class: "pi-hole" }, up);
  const side = el("g", {}, g);
  el("rect", { x: -17.5, y: -4.2, width: 35, height: 8.4, fill: c }, side);
  el("rect", { x: -17.5, y: -4.2, width: 35, height: 8.4, fill: "url(#pi-gSide)" }, side);
  el("rect", { x: -20, y: -6.2, width: 40, height: 2.4, rx: 1.2, fill: "url(#pi-gFlange)" }, side);
  el("rect", { x: -20, y: 3.8, width: 40, height: 2.4, rx: 1.2, fill: "url(#pi-gFlange)" }, side);
  const o = { g, up, side, x, y, flat, rot, s, o: 1, i };
  o.draw = (q) => {
    q.g.setAttribute("transform", `translate(${q.x} ${q.y}) rotate(${q.rot}) scale(${q.s})`);
    q.g.setAttribute("opacity", q.o);
    q.up.setAttribute("opacity", Math.max(0, 1 - q.flat * 1.7));
    q.up.setAttribute("transform", `scale(1 ${1 - 0.72 * q.flat})`);
    q.side.setAttribute("opacity", Math.max(0, q.flat * 1.7 - 0.7));
    q.side.setAttribute("transform", `scale(1 ${0.35 + 0.65 * q.flat})`);
  };
  o.draw(o);
  return o;
}
const DISC = 12.4;   // height of a lying spool
const UP = 18.6;     // center height of an upright spool standing on a shelf
// a tile exactly like the storage grid in PixxelSpool: spool color, slot, Bambu number, line, color name
function tile(i, x, y, w, h, slot, { parent = sv, badge = "" } = {}) {
  const g = el("g", { transform: `translate(${x} ${y})` }, parent);
  if (i == null) {
    el("rect", { class: "pi-empty", x: .5, y: .5, width: w - 1, height: h - 1, rx: 7 }, g);
    txt(slot, { x: 5, y: 9, "font-size": 5.6, class: "pi-t-quiet" }, g);
    return { g, x, y, w, h };
  }
  const sp = SP[i], dark = lum(sp.c) > 0.62, ink = dark ? "#111" : "#fff";
  const bg = el("rect", { x: 0, y: 0, width: w, height: h, rx: 7, fill: sp.c, stroke: "#000", "stroke-opacity": ".08", "stroke-width": ".8" }, g);
  const t = el("g", { fill: ink }, g);
  txt(slot, { x: 5, y: 9, "font-size": 5.4, opacity: .7 }, t);
  txt(sp.no, { x: 5, y: 17.5, "font-size": 7.2, "font-weight": 700 }, t);
  txt(sp.l, { x: 5, y: h - 12, "font-size": 4.8, "font-weight": 700, opacity: .75 }, t);
  txt(sp.n, { x: 5, y: h - 5, "font-size": 6.2 }, t);
  el("circle", { cx: w - 6, cy: 6.5, r: 1.9, fill: ink, opacity: .35 }, g);
  return { g, x, y, w, h, bg, t };
}
// NFC reader pad with the PixxelSpool light
function reader(x, y, parent = sv) {
  const g = el("g", { transform: `translate(${x} ${y})` }, parent);
  el("rect", { class: "pi-padb", x: -28, y: -6, width: 56, height: 9, rx: 4.5, filter: "url(#pi-fShadow)" }, g);
  const led = el("rect", { x: -8, y: -6, width: 16, height: 1.6, rx: .8, fill: "var(--pi-accent)", opacity: .5 }, g);
  return { g, x, y, led };
}
async function scanPulse(rd, k = 1) {
  const rings = [0, 1, 2].map(() => el("circle", { class: "pi-ring", cx: rd.x, cy: rd.y - 18, r: 8, opacity: 0 }));
  go(fade(rd.led, 1, 120 * k));
  const ps = rings.map((r, j) => { const o = val(8, (q) => { r.setAttribute("r", q.v); r.setAttribute("opacity", Math.max(0, 1 - (q.v - 8) / 26)); }); return tween(o, { v: 34 }, 640 * k, { delay: j * 110 * k, e: E.out }); });
  const ck = el("g", { opacity: 0, transform: `translate(${rd.x + 34} ${rd.y - 30})` });
  el("circle", { r: 8, fill: "var(--pi-good)" }, ck);
  el("path", { d: "M-3.6 .4l2.4 2.4L3.8 -2.8", fill: "none", stroke: "#fff", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round" }, ck);
  const cs = val(0, (q) => { ck.setAttribute("opacity", Math.min(1, q.v)); ck.setAttribute("transform", `translate(${rd.x + 34} ${rd.y - 30}) scale(${q.v})`); });
  go(tween(cs, { v: 1 }, 380 * k, { delay: 150 * k, e: E.spring }));
  await Promise.all(ps);
  go(fade(rd.led, .5, 300)); go(fade(ck, 0, 250 * k));
  rings.forEach((r) => r.remove());
}
async function glowAt(x, y, w, h, k = 1) {
  const g = el("rect", { class: "pi-glow", x, y, width: w, height: h, rx: 8, opacity: 0 });
  await fade(g, .28, 240 * k);
  return g;
}
const label = (s, x, y, attrs = {}, parent = sv) => txt(s, { x, y, "font-size": 7, class: "pi-t-quiet", "text-anchor": "middle", ...attrs }, parent);

// ---------------------------------------------------------------- captions and chapters
const cap = host.querySelector(".pi-cap");
async function say(html) {
  stepNo++; progress();
  if (FF && stepNo >= FF) { FF = 0; cap.innerHTML = html; return; }
  if (FF) { cap.innerHTML = html; return; }
  cap.classList.add("out"); await wait(240); cap.innerHTML = html; cap.classList.remove("out");
}
function fresh() {
  root.textContent = ""; sv = root; defs();
  sv = el("g");                       // world group (can slide)
  return sv;
}

// 1 ------------------------------------------------------------ sorting in
const CAB = { x: 196, y: 16, w: 190, h: 218 }, COLS = [221, 266, 311, 356], SHELF = [92, 160, 228];
const CABA = { ...CAB, x: CAB.x - 410 };            // the second cabinet, out of view after the swipe
const TW = 41, TH = 60;
const slotName = (r, c) => `S-${r + 1}-${c + 1}`;
const TARGET = [[1, 2], [0, 0], [2, 3], [0, 3], [1, 0]];
function cabinet(C, parent = sv) {
  const g = el("g", {}, parent);
  el("rect", { class: "pi-cab", x: C.x, y: C.y, width: C.w, height: C.h, rx: 12, filter: "url(#pi-fCard)" }, g);
  SHELF.forEach((y) => el("line", { class: "pi-shelf", x1: C.x + 6, x2: C.x + C.w - 6, y1: y + 1.2, y2: y + 1.2 }, g));
  return g;
}
async function chSort() {
  fresh();
  // camera: start zoomed out on both cabinets, then swipe onto one
  const cam = { s: 0.633, tx: 145.5, ty: 50.9 };
  cam.draw = (q) => sv.setAttribute("transform", `translate(${q.tx} ${q.ty}) scale(${q.s})`);
  cam.draw(cam);
  const cabA = cabinet(CABA), cab = cabinet(CAB);
  const floor = el("line", { class: "pi-lineS", x1: -14, x2: 186, y1: 228.8, y2: 228.8, "stroke-width": 1.2, "stroke-linecap": "round" });
  const MESSY = [
    [-180, 228 - DISC / 2, 1, 0], [-100, 160 - UP, 0, -8],
    [236, 92 - DISC / 2, 1, 0], [238, 92 - DISC * 1.5, 1, -3], [346, 228 - UP, 0, 12],
  ];
  // many more spools, all over the place; they stay behind in the other cabinet
  const aside = el("g");
  const EXA = [[-182, 92 - UP, 0, -6, 5], [-140, 92 - DISC / 2, 1, 0, 6], [-139, 92 - DISC * 1.5, 1, 3, 9], [-98, 92 - UP, 0, 10, 8], [-56, 92 - DISC / 2, 1, 0, 7],
    [-182, 160 - UP, 0, -4, 3], [-140, 160 - DISC / 2, 1, 0, 2], [-141, 160 - DISC * 1.5, 1, -3, 4], [-54, 160 - UP, 0, 8, 6],
    [-138, 228 - UP, 0, -10, 9], [-98, 228 - DISC / 2, 1, 0, 5], [-97, 228 - DISC * 1.5, 1, 2, 1], [-56, 228 - UP, 0, 6, 0]];
  EXA.forEach(([x, y, f, r, i]) => spool(i, x, y, { flat: f, rot: r, parent: aside }));
  const EXB = [[300, 92 - UP, 0, 9, 7], [348, 92 - UP, 0, -6, 8], [236, 160 - UP, 0, -4, 6], [302, 160 - DISC / 2, 1, 0, 9], [270, 228 - DISC / 2, 1, 0, 5]];
  const DEST = [[-140, 92 - DISC * 2.5, 1, -2], [-56, 92 - DISC * 1.5, 1, 2], [-56, 92 - DISC * 2.5, 1, -1], [-140, 160 - DISC * 2.5, 1, 2], [-98, 228 - DISC * 2.5, 1, -2]];
  const exb = EXB.map(([x, y, f, r, i]) => spool(i, x, y, { flat: f, rot: r, parent: aside }));
  const sps = MESSY.map(([x, y, f, r], i) => spool(i, x, y, { flat: f, rot: r }));
  await say(L("Lots of spools, all over the place. <b>But how do you sort them sensibly?</b>"));
  await wait(1000);
  await Promise.all(sps.map((s, k) => tween(s, { rot: s.rot + (k % 2 ? 4 : -4) }, 240, { delay: k * 40 }).then(() => tween(s, { rot: MESSY[k][3] }, 300, { e: E.spring }))));
  await wait(700);
  await say(L("This is where <b>PixxelSpool</b> comes in."));
  const order = [1, 4, 0, 3, 2];
  go(Promise.all(exb.map((e, k) => tween(e, { x: DEST[k][0], y: DEST[k][1], flat: DEST[k][2], rot: DEST[k][3] }, 900, { delay: 200 + k * 140, arc: 50 }))));
  await Promise.all(order.map((idx, k) => { const s = sps[idx]; sv.append(s.g); return tween(s, { x: 52 + (k % 2 ? 1.2 : -1.2), y: 228 - DISC / 2 - k * DISC, rot: 0, flat: 1 }, 720, { delay: k * 150, arc: 40 }); }));
  await wait(500);
  // swipe onto one cabinet
  go(fade(cabA, 0, 900)); go(fade(aside, 0, 900));
  await tween(cam, { s: 1, tx: 0, ty: 0 }, 1400, { e: E.io });
  const rd = reader(128, 229);
  rd.g.setAttribute("opacity", 0);
  await say(L("Hold each spool to the reader for a moment. <b>PixxelSpool sorts it in smartly.</b>"));
  await fade(rd.g, 1, 400);
  for (let k = order.length - 1; k >= 0; k--) {
    const idx = order[k], s = sps[idx], [r, c] = TARGET[idx], f = k >= order.length - 2 ? 1 : 0.38;   // from the third spool on it goes faster
    sv.append(s.g);
    await tween(s, { x: rd.x, y: rd.y - 6 - DISC / 2 - .5 }, 480 * f, { arc: 16 });
    const pulse = scanPulse(rd, f);
    await wait(260 * f);
    const g = await glowAt(COLS[c] - TW / 2, SHELF[r] - TH, TW, TH - 2, f);
    await pulse;
    await tween(s, { x: COLS[c], y: SHELF[r] - UP, flat: 0 }, 640 * f, { arc: 30 });
    go(fade(g, 0, 300).then(() => g.remove()));
    await tween(s, { s: 1.06 }, 110, { e: E.out }); await tween(s, { s: 1 }, 220, { e: E.spring });
    if (f === 1) await wait(160);
  }
  await wait(600);
  await say(L("This is your storage in PixxelSpool: <b>clear and always up to date.</b>"));
  // the spool dissolves, the real tile appears in its place
  const tiles = [];
  [0, 1, 2].forEach((r) => COLS.forEach((x, c) => {
    const i = TARGET.findIndex(([tr, tc]) => tr === r && tc === c);
    const t = tile(i < 0 ? null : i, x - TW / 2, SHELF[r] - TH, TW, TH - 2, slotName(r, c));
    t.g.setAttribute("opacity", 0); tiles.push({ t, i, r, c });
  }));
  await Promise.all(sps.map((s, k) => tween(s, { s: 0.5, o: 0 }, 520, { delay: k * 60, e: E.io })));
  await Promise.all(tiles.map(({ t }, k) => {
    const o = val(0, (q) => { t.g.setAttribute("opacity", q.v); t.g.setAttribute("transform", `translate(${t.x + TW / 2 * (1 - (0.85 + 0.15 * q.v))} ${t.y + TH / 2 * (1 - (0.85 + 0.15 * q.v))}) scale(${0.85 + 0.15 * q.v})`); });
    return tween(o, { v: 1 }, 520, { delay: k * 35, e: E.spring });
  }));
  go(fade(cab, 0, 600)); go(fade(rd.g, 0, 400)); go(fade(floor, 0, 400));
  const w = val(0, (q) => sv.setAttribute("transform", `translate(${q.v} 0)`));
  await tween(w, { v: 200 - (CAB.x + CAB.w / 2) }, 900, { delay: 200 });
  await wait(2600);
}

// 2 ------------------------------------------------------------ AMS
async function chAms() {
  fresh();
  const tiles = {};
  [0, 1, 2].forEach((r) => COLS.forEach((x, c) => {
    const i = TARGET.findIndex(([tr, tc]) => tr === r && tc === c);
    tiles[`${r}${c}`] = tile(i < 0 ? null : i, x - TW / 2, SHELF[r] - TH, TW, TH - 2, slotName(r, c));
  }));
  // AMS unit
  const ams = el("g", { transform: "translate(18 40)" });
  el("rect", { x: 0, y: 0, width: 156, height: 72, rx: 12, fill: "var(--pi-dev)", filter: "url(#pi-fCard)" }, ams);
  el("rect", { x: 6, y: 6, width: 144, height: 48, rx: 8, fill: "var(--pi-dev2)" }, ams);
  txt("AMS", { x: 12, y: 66, "font-size": 6.5, "font-weight": 700, fill: "#9a9aa0", "letter-spacing": ".08em" }, ams);
  const AMSX = [18 + 24, 18 + 60, 18 + 96, 18 + 132], AMSY = 40 + 30;
  [0, 1, 2].forEach((k) => spool([5, 7, 8][k], AMSX[[0, 2, 3][k]], AMSY, { parent: sv, flat: 1, rot: 90 }));
  const rd = reader(96, 229);
  el("line", { class: "pi-lineS", x1: 12, x2: 186, y1: 228.8, y2: 228.8, "stroke-width": 1.2, "stroke-linecap": "round" });
  await say(L("When a spool goes into the AMS, <b>PixxelSpool checks it out automatically.</b>"));
  await wait(700);
  // red spool at S-2-3 leaves its tile and goes into AMS slot 2
  const t = tiles["12"], s = spool(0, t.x + TW / 2, t.y + TH / 2 - 2, { s: .5 });
  s.o = 0; s.draw(s);
  await tween(s, { s: 1, o: 1 }, 380, { e: E.spring });
  go(fade(t.g, 0, 300));
  const empty = tile(null, t.x, t.y, TW, TH - 2, "S-2-3"); empty.g.setAttribute("opacity", 0);
  const badge = el("g", { opacity: 0, transform: `translate(${t.x + 5} ${t.y + 22})` });
  el("rect", { width: 31, height: 11, rx: 5.5, fill: "var(--pi-accent)" }, badge);
  txt(L("in the AMS"), { x: 15.5, y: 7.6, "font-size": 5.6, "font-weight": 600, fill: "#fff", "text-anchor": "middle" }, badge);
  go(fade(empty.g, 1, 300));
  await tween(s, { x: AMSX[1], y: AMSY, flat: 1, rot: 90 }, 900, { arc: 50 });
  await fade(badge, 1, 300);
  await wait(1600);
  await say(L("Coming back from the AMS? <b>One scan and PixxelSpool shows you its slot.</b>"));
  await wait(500);
  await tween(s, { x: rd.x, y: rd.y - 6 - DISC / 2 - .5, flat: 1, rot: 0 }, 800, { arc: 20 });
  const pulse = scanPulse(rd); await wait(260);
  const g = await glowAt(t.x, t.y, TW, TH - 2); await pulse;
  go(fade(badge, 0, 200));
  await tween(s, { x: t.x + TW / 2, y: t.y + TH / 2 - 2, flat: 0 }, 750, { arc: 30 });
  go(fade(g, 0, 300)); go(fade(empty.g, 0, 200));
  await tween(s, { s: .5, o: 0 }, 380);
  t.g.setAttribute("opacity", 1);
  const o = val(0, (q) => t.g.setAttribute("transform", `translate(${t.x + TW / 2 * (1 - (0.85 + 0.15 * q.v))} ${t.y + TH / 2 * (1 - (0.85 + 0.15 * q.v))}) scale(${0.85 + 0.15 * q.v})`));
  await tween(o, { v: 1 }, 520, { e: E.spring });
  await wait(2200);
}

// 3 ------------------------------------------------------------ set up storage, reserve
async function chSetup() {
  fresh();
  // settings card on the left
  const card = el("g", { transform: "translate(12 22)" });
  el("rect", { class: "pi-glass", width: 142, height: 132, rx: 14, filter: "url(#pi-fCard)" }, card);
  txt(L("Storage"), { x: 12, y: 19, "font-size": 9, "font-weight": 700, class: "pi-t-ink" }, card);
  txt(L("Workshop shelf"), { x: 12, y: 30, "font-size": 6.4, class: "pi-t-quiet" }, card);
  const steppers = {};
  [["rows", L("Levels"), 2, 50], ["cols", L("Slots per level"), 3, 78], ["res", L("Reserve"), 0, 106]].forEach(([k, lab, v, y]) => {
    el("line", { class: "pi-lineS", x1: 12, x2: 130, y1: y - 13, y2: y - 13, "stroke-width": .6 }, card);
    txt(lab, { x: 12, y: y + 2, "font-size": 7, class: "pi-t-ink" }, card);
    const sg = el("g", { transform: `translate(84 ${y - 7})` }, card);
    el("rect", { class: "pi-fillbg", width: 46, height: 13, rx: 6.5 }, sg);
    txt("−", { x: 8, y: 9.4, "font-size": 8, class: "pi-t-quiet", "text-anchor": "middle" }, sg);
    const plusBg = el("circle", { cx: 38, cy: 6.5, r: 6, fill: "var(--pi-accent)", opacity: 0 }, sg);
    const plus = txt("+", { x: 38, y: 9.6, "font-size": 8.5, class: "pi-t-ink", "text-anchor": "middle" }, sg);
    const num = txt(String(v), { x: 23, y: 9.4, "font-size": 7.5, "font-weight": 700, class: "pi-t-ink", "text-anchor": "middle" }, sg);
    steppers[k] = { v, num, plusBg, plus };
  });
  async function press(k) {
    const st = steppers[k];
    await fade(st.plusBg, .9, 120); st.plus.setAttribute("fill", "#fff"); st.plus.removeAttribute("class");
    st.v++; st.num.textContent = st.v;
    await wait(120); go(fade(st.plusBg, 0, 250)); st.plus.setAttribute("class", "pi-t-ink"); st.plus.removeAttribute("fill");
  }
  // grid on the right
  const GX = 168, GY = 24, W = 40, H = 46, GAP = 4;
  const filled = { "00": 1, "02": 0, "11": 5, "10": 8 };
  const cells = {};
  function cell(r, c, pop = true) {
    const k = `${r}${c}`, i = filled[k];
    const t = tile(i == null ? null : i, GX + c * (W + GAP), GY + r * (H + GAP), W, H, slotName(r, c));
    cells[k] = t;
    if (pop) {
      const o = val(0, (q) => { t.g.setAttribute("opacity", Math.min(1, q.v)); t.g.setAttribute("transform", `translate(${t.x + W / 2 * (1 - q.v)} ${t.y + H / 2 * (1 - q.v)}) scale(${q.v})`); });
      return tween(o, { v: 1 }, 520, { e: E.spring });
    }
  }
  for (let r = 0; r < 2; r++) for (let c = 0; c < 3; c++) cell(r, c, false);
  await say(L("You set up your storage yourself: <b>levels and slots per level.</b>"));
  await wait(1400);
  await press("rows");
  await Promise.all([0, 1, 2].map((c) => wait(c * 70).then(() => cell(2, c))));
  await wait(500);
  await say(L("Need to expand? No problem: <b>the grid grows with you.</b>"));
  await press("cols");
  await Promise.all([0, 1, 2].map((r) => wait(r * 70).then(() => cell(r, 3))));
  await wait(1100);
  // reserve area, drawn like the reserve section in PixxelSpool: a card per reserve area with a chip per spool
  await say(L("The reserve is a place outside the storage for spare spools, <b>without fixed slots or order.</b>"));
  await press("res");
  const res = el("g", { opacity: 0 });
  txt(L("Reserve (spare spools)"), { x: GX, y: 186, "font-size": 7.4, "font-weight": 700, class: "pi-t-ink" }, res);
  el("rect", { class: "pi-glass", x: GX, y: 192, width: 4 * W + 3 * GAP, height: 62, rx: 8 }, res);
  const head = txt(`${L("Workshop shelf")} · ${L("Reserve")} 1 · ${Lp(3, "{0} spool", "{0} spools")}`, { x: GX + 7, y: 203, "font-size": 6.2, "font-weight": 700, class: "pi-t-ink" }, res);
  await fade(res, 1, 400);
  const chips = [1, 3, 9].map((i, k) => {
    const g = el("g", { opacity: 0 }), y = 208 + k * 14;
    const hl = el("rect", { x: -4, y: -1.5, width: 4 * W + 3 * GAP - 6, height: 13, rx: 4, fill: "var(--pi-accent)", opacity: 0 }, g);
    el("rect", { x: 0, y: 1, width: 9, height: 9, rx: 2.5, fill: SP[i].c, stroke: "#000", "stroke-opacity": ".12", "stroke-width": .5 }, g);
    txt(`${SP[i].l} ${SP[i].n}`, { x: 14, y: 8, "font-size": 6.4, class: "pi-t-ink" }, g);
    txt(SP[i].no, { x: 14 + (SP[i].l.length + SP[i].n.length + 1) * 3.25 + 4, y: 8, "font-size": 5.6, class: "pi-t-quiet" }, g);
    const o = { g, hl, x: GX + 7, y }; o.draw = (q) => g.setAttribute("transform", `translate(${q.x} ${q.y})`); o.draw(o);
    return o;
  });
  for (const c of chips) { await fade(c.g, 1, 260); await wait(80); }
  await wait(1400);
  await say(L("When a spool runs empty, <b>a spare moves up from the reserve.</b>"));
  // blue tile S-1-1 runs empty
  const t = cells["00"];
  await fade(t.g, .25, 500);
  const ghost = tile(null, t.x, t.y, W, H, "S-1-1");
  go(fade(t.g, 0, 300));
  const c0 = chips[0];
  await fade(c0.hl, .16, 260);
  await wait(500);
  // the spare chip lifts out of the reserve list and becomes the tile
  go(fade(c0.g, 0, 500, 300));
  await tween(c0, { x: t.x + 4, y: t.y + H / 2 }, 800, { arc: 20 });
  head.textContent = `${L("Workshop shelf")} · ${L("Reserve")} 1 · ${Lp(2, "{0} spool", "{0} spools")}`;
  go(Promise.all(chips.slice(1).map((c) => tween(c, { y: c.y - 14 }, 420))));
  ghost.g.remove();
  const nt = tile(1, t.x, t.y, W, H, "S-1-1");
  const o = val(0, (q) => { nt.g.setAttribute("opacity", Math.min(1, q.v)); nt.g.setAttribute("transform", `translate(${t.x + W / 2 * (1 - q.v)} ${t.y + H / 2 * (1 - q.v)}) scale(${q.v})`); });
  await tween(o, { v: 1 }, 520, { e: E.spring });
  await wait(2200);
}

// 4 ------------------------------------------------------------ grid and list view
async function chViews() {
  fresh();
  el("rect", { class: "pi-glass", x: 64, y: 12, width: 272, height: 236, rx: 18, filter: "url(#pi-fCard)" });
  // segmented control
  const seg = el("g", { transform: "translate(150 24)" });
  el("rect", { class: "pi-fillbg", width: 100, height: 18, rx: 9 }, seg);
  const knob = el("rect", { x: 2, y: 2, width: 48, height: 14, rx: 7, fill: "var(--pi-card-solid)", filter: "url(#pi-fShadow)" }, seg);
  txt(L("Grid"), { x: 26, y: 12.2, "font-size": 7, "font-weight": 600, class: "pi-t-ink", "text-anchor": "middle" }, seg);
  txt(L("List"), { x: 74, y: 12.2, "font-size": 7, "font-weight": 600, class: "pi-t-ink", "text-anchor": "middle" }, seg);
  const items = [1, 6, 9, 3, 5, 8].map((i, k) => {
    const gx = { x: 80 + (k % 3) * 82, y: 54 + Math.floor(k / 3) * 74, w: 76, h: 66 };
    const lx = { x: 80, y: 52 + k * 30, w: 240, h: 26 };
    const g = el("g");
    const bgList = el("rect", { rx: 8, class: "pi-fillbg", opacity: 0 }, g);
    const bgTile = el("rect", { rx: 9, fill: SP[i].c, stroke: "#000", "stroke-opacity": ".08", "stroke-width": ".8" }, g);
    const ink = lum(SP[i].c) > 0.62 ? "#111" : "#fff";
    const tg = el("g", { fill: ink }, g);
    const slot = ["S-1-1", "S-1-2", "S-1-3", "S-2-1", "S-2-2", "S-2-3"][k];
    txt(slot, { x: 6, y: 11, "font-size": 6, opacity: .7 }, tg);
    txt(SP[i].no, { x: 6, y: 21, "font-size": 8.5, "font-weight": 700 }, tg);
    txt(SP[i].l, { x: 6, y: 50, "font-size": 5.6, "font-weight": 700, opacity: .75 }, tg);
    txt(SP[i].n, { x: 6, y: 59, "font-size": 7.2 }, tg);
    const lg = el("g", { opacity: 0 }, g);
    el("circle", { cx: 13, cy: 13, r: 7, fill: SP[i].c, stroke: "#000", "stroke-opacity": ".12", "stroke-width": ".6" }, lg);
    txt(`${SP[i].l} ${SP[i].n}`, { x: 26, y: 12, "font-size": 7.2, "font-weight": 600, class: "pi-t-ink" }, lg);
    txt(`${slot} · Bambu ${SP[i].no}`, { x: 26, y: 20.5, "font-size": 5.8, class: "pi-t-quiet" }, lg);
    const bar = el("rect", { x: 186, y: 11, width: 44, height: 4, rx: 2, class: "pi-fillbg" }, lg);
    el("rect", { x: 186, y: 11, width: 44 * [0.9, 0.55, 1, 0.3, 0.75, 0.15][k], height: 4, rx: 2, fill: [0.3, 0.15].includes([0.9, 0.55, 1, 0.3, 0.75, 0.15][k]) ? "var(--pi-warn)" : "var(--pi-good)" }, lg);
    bar.setAttribute("stroke", "none");
    const o = { g, bgList, bgTile, tg, lg, gx, lx, m: 0 };
    o.draw = (q) => {
      const m = q.m, x = gx.x + (lx.x - gx.x) * m, y = gx.y + (lx.y - gx.y) * m, w = gx.w + (lx.w - gx.w) * m, h = gx.h + (lx.h - gx.h) * m;
      q.g.setAttribute("transform", `translate(${x} ${y})`);
      for (const r of [bgList, bgTile]) { r.setAttribute("width", w); r.setAttribute("height", h); }
      bgTile.setAttribute("opacity", 1 - m); bgList.setAttribute("opacity", m);
      tg.setAttribute("opacity", Math.max(0, 1 - m * 2.2)); lg.setAttribute("opacity", Math.max(0, m * 2.2 - 1.2));
    };
    o.draw(o); return o;
  });
  const kn = val(0, (q) => knob.setAttribute("x", 2 + 48 * q.v));
  await say(L("Grid or list: <b>your storage the way you need it right now.</b>"));
  await wait(1500);
  go(tween(kn, { v: 1 }, 420, { e: E.spring }));
  await Promise.all(items.map((o, k) => tween(o, { m: 1 }, 700, { delay: k * 40 })));
  await say(L("The list shows you <b>slot, number and remaining filament at a glance.</b>"));
  await wait(2600);
  await wait(1400);
}

// 5 ------------------------------------------------------------ catalog, color from picture
async function chCatalog() {
  fresh();
  // the photo: a vase and a plant, drawn softly
  const ph = el("g", { transform: "translate(16 26)" });
  const clip = el("clipPath", { id: "pi-phc" }, ph); el("rect", { width: 170, height: 196, rx: 14 }, clip);
  const pg = el("g", { "clip-path": "url(#pi-phc)" }, ph);
  el("rect", { width: 170, height: 196, fill: "#e9e3da" }, pg);
  el("rect", { y: 140, width: 170, height: 56, fill: "#cdbfae" }, pg);
  el("ellipse", { cx: 120, cy: 60, rx: 60, ry: 50, fill: "#f6efe4" }, pg);
  el("path", { d: "M70 150 C55 120 60 90 78 80 L102 80 C120 90 125 120 110 150 Z", fill: "#18a7b5" }, pg);
  el("path", { d: "M78 80 L102 80 L99 70 L81 70 Z", fill: "#14909c" }, pg);
  el("path", { d: "M74 140 C64 118 68 96 80 88", fill: "none", stroke: "#fff", "stroke-opacity": ".35", "stroke-width": 3, "stroke-linecap": "round" }, pg);
  [[-30, "#3fae5a"], [-8, "#4cbf68"], [16, "#36a050"], [36, "#4cbf68"]].forEach(([a, c]) => el("ellipse", { cx: 90, cy: 45, rx: 7, ry: 24, fill: c, transform: `rotate(${a} 90 70)` }, pg));
  el("rect", { x: 128, y: 120, width: 26, height: 30, rx: 4, fill: "#f4c430" }, pg);
  el("rect", { width: 170, height: 196, rx: 14, fill: "none", stroke: "#000", "stroke-opacity": ".08" }, ph);
  // catalog chips on the right
  const cg = el("g", { transform: "translate(206 26)" });
  el("rect", { class: "pi-glass", width: 178, height: 196, rx: 14, filter: "url(#pi-fCard)" }, cg);
  txt(`${L("Catalog")} · PLA Basic`, { x: 12, y: 18, "font-size": 7.5, "font-weight": 700, class: "pi-t-ink" }, cg);
  const CH = ["#ffffff", "#f3f3ef", "#e5483e", "#ff7a1a", "#f4c430", "#3fae5a", "#18a7b5", "#2f6fdb", "#8b4fd8", "#f06292", "#9a9aa0", "#222225", "#7a4b2a", "#c7e86a", "#0e5c99"];
  const chips = CH.map((c, k) => { const x = 22 + (k % 5) * 33, y = 42 + Math.floor(k / 5) * 34; el("circle", { cx: x, cy: y, r: 11, fill: c, stroke: "#000", "stroke-opacity": ".12", "stroke-width": ".6" }, cg); return { x: 206 + x, y: 26 + y, own: [2, 6, 7, 11].includes(k) }; });
  chips.forEach((ch) => { if (ch.own) el("circle", { cx: ch.x + 8, cy: ch.y - 8, r: 3, fill: "var(--pi-good)", stroke: "var(--pi-card-solid)", "stroke-width": 1.2 }); });
  await say(L("The catalog knows every Bambu Lab color <b>and shows which ones you already have.</b>"));
  await wait(2000);
  await say(L("Color from image: tap a photo, <b>PixxelSpool finds the matching spool.</b>"));
  // picker moves onto the vase
  const pk = el("g");
  el("circle", { r: 9, fill: "none", stroke: "#fff", "stroke-width": 2.4, filter: "url(#pi-fShadow)" }, pk);
  el("circle", { r: 2, fill: "#fff" }, pk);
  const p = val(0, () => {}); const P = { x: 150, y: 190 };
  p.draw = (q) => pk.setAttribute("transform", `translate(${P.x + (100 - P.x) * q.v} ${P.y + (140 - P.y) * q.v})`); p.draw(p);
  await tween(p, { v: 1 }, 1100, { e: E.io });
  const sw = el("g", { transform: "translate(100 140)" });
  const swc = el("circle", { r: 0, fill: "#18a7b5", stroke: "#fff", "stroke-width": 2, filter: "url(#pi-fShadow)" }, sw);
  await tween(val(0, (q) => swc.setAttribute("r", q.v)), { v: 13 }, 420, { e: E.spring });
  // the match in the catalog
  const m = chips[6], ring = el("circle", { cx: m.x, cy: m.y, r: 11, fill: "none", stroke: "var(--pi-accent)", "stroke-width": 2, opacity: 0 });
  const line = el("path", { d: `M113 140 C 160 140, 170 ${m.y}, ${m.x - 14} ${m.y}`, fill: "none", stroke: "var(--pi-accent)", "stroke-width": 1.4, "stroke-dasharray": 160, "stroke-dashoffset": 160, "stroke-linecap": "round" });
  await tween(val(160, (q) => line.setAttribute("stroke-dashoffset", q.v)), { v: 0 }, 700);
  const rr = val(18, (q) => { ring.setAttribute("r", q.v); ring.setAttribute("opacity", 1); });
  await tween(rr, { v: 14 }, 400, { e: E.spring });
  const info = el("g", { opacity: 0, transform: "translate(218 150)" });
  el("rect", { class: "pi-fillbg", width: 154, height: 30, rx: 9 }, info);
  el("circle", { cx: 14, cy: 15, r: 7, fill: "#18a7b5" }, info);
  txt(L("{0} · {1} % match", PB + L("Cyan"), 97), { x: 26, y: 13, "font-size": 6.6, "font-weight": 600, class: "pi-t-ink" }, info);
  txt(L("In storage at {0}", S23), { x: 26, y: 22, "font-size": 5.8, class: "pi-t-quiet" }, info);
  await fade(info, 1, 380);
  await wait(1800);
  await say(L("Missing a color? <b>One tap puts it on the shopping list.</b>"));
  const add = el("g", { opacity: 0, transform: "translate(218 186)" });
  el("rect", { width: 154, height: 22, rx: 11, fill: "var(--pi-accent)" }, add);
  txt("+ " + L("Add to shopping list"), { x: 77, y: 14.4, "font-size": 7, "font-weight": 600, fill: "#fff", "text-anchor": "middle" }, add);
  await fade(add, 1, 380);
  await wait(2200);
}

// 6 ------------------------------------------------------------ printer live
async function chPrinter() {
  fresh();
  const c = el("g", { transform: "translate(22 22)" });
  el("rect", { class: "pi-glass", width: 356, height: 216, rx: 18, filter: "url(#pi-fCard)" }, c);
  // printer drawing with a part growing layer by layer
  const pr = el("g", { transform: "translate(18 20)" }, c);
  el("rect", { width: 112, height: 120, rx: 12, fill: "var(--pi-dev)" }, pr);
  el("rect", { x: 8, y: 8, width: 96, height: 92, rx: 6, fill: "#3a3a40" }, pr);
  el("rect", { x: 18, y: 84, width: 76, height: 5, rx: 1.5, fill: "#5a5a62" }, pr);
  const part = el("rect", { x: 42, y: 84, width: 28, height: 0, rx: 2, fill: "#18a7b5" }, pr);
  const head = el("rect", { x: 46, y: 30, width: 20, height: 9, rx: 2.5, fill: "#d8d8de" }, pr);
  el("rect", { x: 8, y: 104, width: 96, height: 9, rx: 3, fill: "#1c1c20" }, pr);
  const live = el("g", { transform: "translate(150 32)" }, c);
  const dot = el("circle", { cx: 4, cy: -2.5, r: 3, fill: "var(--pi-good)" }, live);
  txt("Live · H2C", { x: 11, y: 0, "font-size": 7, "font-weight": 600, class: "pi-t-quiet" }, live);
  txt("Vase.3mf", { x: 150, y: 50, "font-size": 11, "font-weight": 700, class: "pi-t-ink" }, c);
  const pct = txt("0 %", { x: 336, y: 50, "font-size": 11, "font-weight": 700, class: "pi-t-ink", "text-anchor": "end" }, c);
  el("rect", { x: 150, y: 58, width: 186, height: 6, rx: 3, class: "pi-fillbg" }, c);
  const bar = el("rect", { x: 150, y: 58, width: 0, height: 6, rx: 3, fill: "var(--pi-accent)" }, c);
  const eta = txt(L("{0} min left", 112), { x: 150, y: 76, "font-size": 6.6, class: "pi-t-quiet" }, c);
  // AMS row with remaining amounts
  txt("AMS 1", { x: 150, y: 100, "font-size": 6.5, "font-weight": 700, class: "pi-t-quiet" }, c);
  const AM = [[8, 0.82], [1, 0.4], [4, 0.95], [5, 0.22]];
  const bars = AM.map(([i, r], k) => {
    const x = 150 + k * 48;
    spool(i, x + 13, 126, { parent: c, s: .62 });
    el("rect", { x, y: 144, width: 40, height: 4, rx: 2, class: "pi-fillbg" }, c);
    const b = el("rect", { x, y: 144, width: 40 * r, height: 4, rx: 2, fill: r < .3 ? "var(--pi-warn)" : "var(--pi-good)" }, c);
    txt(`${Math.round(r * 100)} %`, { x, y: 157, "font-size": 5.8, class: "pi-t-quiet" }, c);
    return { b, r, x };
  });
  const ok = el("g", { opacity: 0, transform: "translate(150 172)" }, c);
  el("rect", { width: 186, height: 26, rx: 9, fill: "color-mix(in srgb, var(--pi-good) 14%, transparent)" }, ok);
  el("circle", { cx: 13, cy: 13, r: 6, fill: "var(--pi-good)" }, ok);
  el("path", { d: "M10.4 13.2l1.8 1.8 3.6-3.8", fill: "none", stroke: "#fff", "stroke-width": 1.6, "stroke-linecap": "round", "stroke-linejoin": "round" }, ok);
  txt(L("Enough filament: {0} g needed, {1} g in the AMS", 112, 820), { x: 25, y: 15.6, "font-size": 6.4, "font-weight": 600, class: "pi-t-ink" }, ok);
  await say(L("Bambu Lab printers report live <b>progress, AMS slots and remaining filament.</b>"));
  go((async () => { while (true) { await frame1(); await fade(dot, .25, 600); await fade(dot, 1, 600); } })());
  await fade(ok, 1, 400, 600);
  const prog = val(0, (q) => {
    bar.setAttribute("width", 186 * q.v); pct.textContent = `${Math.round(q.v * 100)} %`;
    part.setAttribute("height", 46 * q.v); part.setAttribute("y", 84 - 46 * q.v);
    head.setAttribute("y", 30 + (1 - q.v) * 10); head.setAttribute("x", 46 + Math.sin(q.v * 60) * 10);
    eta.textContent = L("{0} min left", Math.max(0, Math.round(112 * (1 - q.v))));
    bars[0].b.setAttribute("width", 40 * (bars[0].r - 0.14 * q.v));
  });
  await tween(prog, { v: .64 }, 4200, { e: E.lin });
  await say(L("Before a print, PixxelSpool checks <b>whether there is enough filament.</b>"));
  await tween(prog, { v: .72 }, 2400, { e: E.lin });
}

// 7 ------------------------------------------------------------ statistics
async function chStats() {
  fresh();
  const K = [[L("Spools"), 42, ""], [L("Filament"), 31.5, " kg"], [L("Stock value"), 1094, " €"]];
  const ks = K.map(([lab, v, u], k) => {
    const g = el("g", { transform: `translate(${22 + k * 122} 20)` });
    el("rect", { class: "pi-glass", width: 112, height: 54, rx: 14, filter: "url(#pi-fCard)" }, g);
    txt(lab, { x: 12, y: 17, "font-size": 6.8, class: "pi-t-quiet" }, g);
    const t = txt("0" + u, { x: 12, y: 40, "font-size": 16, "font-weight": 700, class: "pi-t-ink" }, g);
    return { t, v, u };
  });
  const ch = el("g", { transform: "translate(22 86)" });
  el("rect", { class: "pi-glass", width: 356, height: 150, rx: 16, filter: "url(#pi-fCard)" }, ch);
  txt(L("Usage per month"), { x: 14, y: 20, "font-size": 8, "font-weight": 700, class: "pi-t-ink" }, ch);
  const M = [5, 6, 7, 8, 9, 10].map((m) => new Date(2026, m, 1).toLocaleString(LANG, { month: "short" }).replace(".", "")), V = [0.42, 0.58, 0.36, 0.71, 0.88, 0.64];
  const bs = M.map((m, k) => {
    const x = 30 + k * 54;
    txt(m, { x: x + 15, y: 140, "font-size": 6.2, class: "pi-t-quiet", "text-anchor": "middle" }, ch);
    return { r: el("rect", { x, y: 128, width: 30, height: 0, rx: 5, fill: k === 5 ? "var(--pi-accent)" : "color-mix(in srgb, var(--pi-accent) 35%, transparent)" }, ch), v: V[k] };
  });
  await say(L("The statistics show you automatically <b>usage, costs and stock value.</b>"));
  go(Promise.all(ks.map((k, j) => tween(val(0, (q) => { k.t.textContent = (k.v % 1 ? q.v.toLocaleString(LANG, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : Math.round(q.v).toLocaleString(LANG)) + k.u; }), { v: k.v }, 1200, { delay: j * 120, e: E.out }))));
  await Promise.all(bs.map((b, k) => tween(val(0, (q) => { b.r.setAttribute("height", 96 * q.v); b.r.setAttribute("y", 128 - 96 * q.v); }), { v: b.v }, 900, { delay: 200 + k * 90, e: E.spring })));
  await wait(3200);
}

// 4 ------------------------------------------------------------ own brands with NFC stickers
async function chBrands() {
  fresh();
  el("line", { class: "pi-lineS", x1: 20, x2: 380, y1: 228.8, y2: 228.8, "stroke-width": 1.2, "stroke-linecap": "round" });
  const rd = reader(250, 229);
  const s = spool(10, 104, 128, { s: 1.9 });
  s.o = 0; s.s = 1.5; s.draw(s);
  await say(L("Spools from other brands? <b>An NFC sticker is all it takes.</b>"));
  await tween(s, { o: 1, s: 1.9 }, 520, { e: E.spring });
  // sticker flies onto the flange
  const st = el("g");
  // the round PixxelSpool sticker (same design as the printable sticker sheet)
  el("circle", { r: 7.4, fill: "#fff", filter: "url(#pi-fShadow)" }, st);
  el("image", { href: "/static/logo-round.svg", x: -7.4, y: -7.4, width: 14.8, height: 14.8 }, st);
  const P = { x: 330, y: 40, s: .6, r: -30 };
  P.draw = (q) => st.setAttribute("transform", `translate(${q.x} ${q.y}) rotate(${q.r}) scale(${q.s})`); P.draw(P);
  await wait(500);
  await tween(P, { x: 104 + 22, y: 128 - 22, s: 1.2, r: 0 }, 900, { arc: 40 });
  await tween(P, { s: .95 }, 260, { e: E.spring });
  st.remove();
  const local = el("g", { transform: "translate(11 -11) scale(.75)" }, s.up); local.append(...st.childNodes);
  await wait(500);
  await say(L("Set it up once: <b>brand, line, color and empty weight.</b>"));
  const form = el("g", { opacity: 0, transform: "translate(212 34)" });
  el("rect", { class: "pi-glass", width: 170, height: 118, rx: 14, filter: "url(#pi-fCard)" }, form);
  txt(L("Own brand"), { x: 12, y: 19, "font-size": 8.5, "font-weight": 700, class: "pi-t-ink" }, form);
  const rows = [[L("Brand"), "Sunlu"], [L("Line"), "PLA+"], [L("Color"), L("Mint")], [L("Empty weight"), "165 g"]].map(([k, v], j) => {
    const g = el("g", { opacity: 0, transform: `translate(12 ${36 + j * 20})` }, form);
    el("line", { class: "pi-lineS", x1: 0, x2: 146, y1: -8, y2: -8, "stroke-width": .6 }, g);
    txt(k, { x: 0, y: 3, "font-size": 7, class: "pi-t-quiet" }, g);
    if (j === 2) el("circle", { cx: 118, cy: .6, r: 3.6, fill: SP[10].c }, g);
    txt(v, { x: 146, y: 3, "font-size": 7, "font-weight": 600, class: "pi-t-ink", "text-anchor": "end" }, g);
    return g;
  });
  await fade(form, 1, 380);
  for (const r of rows) { await fade(r, 1, 260); await wait(260); }
  await wait(900);
  await say(L("From then on PixxelSpool recognizes it <b>like any Bambu spool.</b>"));
  go(fade(form, 0, 400));
  await tween(s, { x: rd.x, y: rd.y - 6 - DISC / 2 - .5, s: 1, flat: 1 }, 900, { arc: 30 });
  const pulse = scanPulse(rd); await wait(300);
  const t = tile(10, 296, 40, TW, TH - 2, "S-1-4");
  const o = val(0, (q) => { t.g.setAttribute("opacity", Math.min(1, q.v)); t.g.setAttribute("transform", `translate(${296 + TW / 2 * (1 - q.v)} ${40 + TH / 2 * (1 - q.v)}) scale(${q.v})`); });
  await tween(o, { v: 1 }, 520, { e: E.spring }); await pulse;
  await wait(2200);
}

// 7 ------------------------------------------------------------ low filament and the shopping list
async function chRestock() {
  fresh();
  const L1 = el("g", { transform: "translate(16 58)" });
  el("rect", { class: "pi-glass", width: 170, height: 176, rx: 16, filter: "url(#pi-fCard)" }, L1);
  const s = spool(0, 101, 116, { s: 1.7 });
  const fil = s.up.children[1], hl = s.up.children[5], rings = [2, 3, 4].map((k) => s.up.children[k]);
  txt("PLA Basic Rot", { x: 101, y: 186, "font-size": 8, "font-weight": 700, class: "pi-t-ink", "text-anchor": "middle" });
  txt("S-2-3", { x: 101, y: 196, "font-size": 6.2, class: "pi-t-quiet", "text-anchor": "middle" });
  el("rect", { x: 36, y: 206, width: 130, height: 5, rx: 2.5, class: "pi-fillbg" });
  const bar = el("rect", { x: 36, y: 206, width: 130 * .42, height: 5, rx: 2.5, fill: "var(--pi-good)" });
  const gr = txt("420 g", { x: 166, y: 222, "font-size": 6.6, "font-weight": 600, class: "pi-t-quiet", "text-anchor": "end" });
  // shopping list
  const R = el("g", { transform: "translate(206 58)" });
  el("rect", { class: "pi-glass", width: 178, height: 176, rx: 16, filter: "url(#pi-fCard)" }, R);
  txt(L("Shopping list"), { x: 14, y: 22, "font-size": 9, "font-weight": 700, class: "pi-t-ink" }, R);
  el("circle", { cx: 160, cy: 19, r: 7, fill: "var(--pi-accent)" }, R);
  const cnt = txt("2", { x: 160, y: 21.6, "font-size": 7, "font-weight": 700, fill: "#fff", "text-anchor": "middle" }, R);
  const row = (i, y, sub) => {
    const g = el("g", { transform: `translate(220 ${y})` });
    el("rect", { class: "pi-fillbg", width: 150, height: 24, rx: 8 }, g);
    el("circle", { cx: 13, cy: 12, r: 6, fill: SP[i].c, stroke: "#000", "stroke-opacity": ".12", "stroke-width": .6 }, g);
    txt(`${SP[i].l} ${SP[i].n}`, { x: 25, y: 11, "font-size": 6.8, "font-weight": 600, class: "pi-t-ink" }, g);
    txt(sub, { x: 25, y: 19, "font-size": 5.6, class: "pi-t-quiet" }, g);
    return g;
  };
  const old = [row(5, 92, `Bambu 11101 · ${L("noted")}`), row(4, 120, `Bambu 10100 · ${L("noted")}`)];
  await say(L("When a spool runs low, <b>PixxelSpool lets you know.</b>"));
  await wait(500);
  const k = val(0, (q) => {
    const r = .42 - .32 * q.v;
    bar.setAttribute("width", 130 * r); bar.setAttribute("fill", r < .2 ? "var(--pi-warn)" : "var(--pi-good)");
    gr.textContent = `${Math.round(1000 * r / 10) * 10} g`;
    fil.setAttribute("r", 15.6 - 5.4 * q.v); hl.setAttribute("r", 15.6 - 5.4 * q.v);
    rings.forEach((c, j) => c.setAttribute("opacity", 15.6 - 5.4 * q.v > [13.4, 11.2, 9.4][j] ? 1 : 0));
  });
  await tween(k, { v: 1 }, 2400, { e: E.io });
  // notification banner
  const bn = el("g");
  el("rect", { class: "pi-glass", width: 300, height: 38, rx: 13, filter: "url(#pi-fCard)" }, bn);
  el("rect", { x: 9, y: 8, width: 22, height: 22, rx: 6, fill: "var(--pi-accent)" }, bn);
  el("path", { d: "M20 12.5c-3 0-4.6 2.2-4.6 4.8v3.3l-1.4 2h12l-1.4-2v-3.3c0-2.6-1.6-4.8-4.6-4.8zM18.3 24a1.8 1.8 0 0 0 3.4 0", fill: "#fff" }, bn);
  txt(L("Low filament"), { x: 39, y: 17, "font-size": 7.4, "font-weight": 700, class: "pi-t-ink" }, bn);
  txt(L("{0} on {1}: {2} g left", PB + L("Red"), S23, 100), { x: 39, y: 28, "font-size": 6.6, class: "pi-t-quiet" }, bn);
  txt(L("now"), { x: 290, y: 17, "font-size": 5.8, class: "pi-t-quiet", "text-anchor": "end" }, bn);
  const B = { y: -50 }; B.draw = (q) => bn.setAttribute("transform", `translate(50 ${q.y})`); B.draw(B);
  await tween(B, { y: 8 }, 700, { e: E.spring });
  await wait(1600);
  await say(L("The color goes straight onto the shopping list, <b>so you never run out.</b>"));
  go(tween(B, { y: -50 }, 500, { e: E.io }));
  await Promise.all(old.map((g, j) => tween(val(0, (q) => g.setAttribute("transform", `translate(220 ${[92, 120][j] + 28 * q.v})`)), { v: 1 }, 500, { e: E.io })));
  const nr = row(0, 92, `Bambu 10200 · ${L("running low")}`);
  const N = val(0, (q) => { nr.setAttribute("opacity", Math.min(1, q.v * 1.4)); nr.setAttribute("transform", `translate(${120 + 100 * q.v} ${150 - 58 * q.v}) scale(${.7 + .3 * q.v})`); });
  await tween(N, { v: 1 }, 800, { e: E.io });
  cnt.textContent = "3";
  await tween(val(1.4, (q) => cnt.setAttribute("font-size", 7 * q.v)), { v: 1 }, 400, { e: E.spring });
  await wait(2400);
}

// 9 ------------------------------------------------------------ storage climate via Home Assistant
async function chClimate() {
  fresh();
  const C = { x: 22, y: 40, w: 150, h: 190 };
  el("rect", { class: "pi-cab", x: C.x, y: C.y, width: C.w, height: C.h, rx: 12, filter: "url(#pi-fCard)" });
  [110, 170, 228].forEach((y) => el("line", { class: "pi-shelf", x1: C.x + 6, x2: C.x + C.w - 6, y1: y + 1.2, y2: y + 1.2 }));
  const sps = [[48, 110 - UP, 0, 1], [92, 110 - UP, 0, 3], [136, 110 - UP, 0, 7], [50, 170 - UP, 0, 8], [94, 170 - UP, 0, 9], [52, 228 - UP, 0, 2], [96, 228 - UP, 0, 5]].map(([x, y, f, i]) => spool(i, x, y, { flat: f }));
  // sensor on the cabinet wall
  const sen = el("g", { transform: "translate(136 136)" });
  el("rect", { x: -9, y: -11, width: 18, height: 22, rx: 4, fill: "#fff", stroke: "#000", "stroke-opacity": ".15", "stroke-width": .6, filter: "url(#pi-fShadow)" }, sen);
  el("circle", { cx: 0, cy: -4, r: 3.2, fill: "none", stroke: "#18a7b5", "stroke-width": 1.2 }, sen);
  txt("%", { x: 0, y: 7.5, "font-size": 5.6, "font-weight": 700, fill: "#333", "text-anchor": "middle" }, sen);
  sps[4].g.remove();                                 // make room for the sensor
  // card with the gauge
  const K = el("g", { transform: "translate(196 40)" });
  el("rect", { class: "pi-glass", width: 188, height: 190, rx: 16, filter: "url(#pi-fCard)" }, K);
  txt(L("Humidity in storage"), { x: 14, y: 21, "font-size": 8.5, "font-weight": 700, class: "pi-t-ink" }, K);
  txt(L("via Home Assistant"), { x: 14, y: 31, "font-size": 6.2, class: "pi-t-quiet" }, K);
  const R = 40, CIRC = 2 * Math.PI * R;
  el("circle", { cx: 94, cy: 94, r: R, fill: "none", stroke: "var(--pi-fill)", "stroke-width": 9 }, K);
  const arc = el("circle", { cx: 94, cy: 94, r: R, fill: "none", stroke: "var(--pi-good)", "stroke-width": 9, "stroke-linecap": "round", "stroke-dasharray": CIRC, transform: "rotate(-90 94 94)" }, K);
  const hv = txt("0 %", { x: 94, y: 98, "font-size": 15, "font-weight": 700, class: "pi-t-ink", "text-anchor": "middle" }, K);
  txt("21 °C", { x: 94, y: 110, "font-size": 6.6, class: "pi-t-quiet", "text-anchor": "middle" }, K);
  const chip = el("g", { transform: "translate(14 152)" }, K);
  const chipBg = el("rect", { width: 160, height: 24, rx: 9, fill: "color-mix(in srgb, var(--pi-good) 14%, transparent)" }, chip);
  const chipT = txt(L("All good"), { x: 80, y: 15.2, "font-size": 6.8, "font-weight": 600, class: "pi-t-ink", "text-anchor": "middle" }, chip);
  const col = (v) => (v < 45 ? "var(--pi-good)" : v < 52 ? "var(--pi-warn)" : "#ff453a");
  const H = val(0, (q) => { arc.setAttribute("stroke-dashoffset", CIRC * (1 - q.v / 100)); arc.setAttribute("stroke", col(q.v)); hv.textContent = `${Math.round(q.v)} %`; });
  H.draw(H);
  // data waves from the sensor to the card
  const wv = [0, 1, 2].map(() => el("path", { d: "M148 136 Q 172 120 196 128", fill: "none", stroke: "var(--pi-accent)", "stroke-width": 1.2, "stroke-dasharray": "2 60", "stroke-linecap": "round", opacity: .8 }));
  go((async () => { const f = val(0, (q) => wv.forEach((p, j) => p.setAttribute("stroke-dashoffset", -((q.v + j * 20) % 62)))); while (true) { await frame1(); f.v = 0; await tween(f, { v: 62 }, 1400, { e: E.lin }); } })());
  await say(L("With Home Assistant you see <b>humidity and temperature in your storage.</b>"));
  await tween(H, { v: 38 }, 1200, { e: E.out });
  await wait(1400);
  await tween(H, { v: 56 }, 2200, { e: E.io });
  chipBg.setAttribute("fill", "color-mix(in srgb, #ff453a 14%, transparent)"); chipT.textContent = L("Too damp: check the desiccant");
  await say(L("If it gets too damp, <b>PixxelSpool warns you.</b>"));
  await wait(2000);
  await say(L("And spools that have been open for a long time? <b>You get a reminder to dry them.</b>"));
  const s = sps[2], pill = el("g", { opacity: 0, transform: `translate(${s.x - 19} ${s.y - 34})` });
  el("rect", { width: 38, height: 11, rx: 5.5, fill: "var(--pi-warn)" }, pill);
  txt(L("dry it"), { x: 19, y: 7.6, "font-size": 5.8, "font-weight": 600, fill: "#fff", "text-anchor": "middle" }, pill);
  await tween(s, { s: 1.12 }, 260, { e: E.out }); go(tween(s, { s: 1 }, 400, { e: E.spring }));
  await fade(pill, 1, 300);
  await wait(2400);
}

// 11 ----------------------------------------------------------- runs at home, works on every device
function devLayout(kind, S) {
  const D = {
    pc:   { S: [100, 58, 208, 128], bez: 5, rx: 7, side: 36, tab: 0, stand: 1, isl: 0, cols: 4, rows: 2, list: 0 },
    pad:  { S: [126, 66, 156, 112], bez: 8, rx: 15, side: 0, tab: 0, stand: 0, isl: 0, cols: 4, rows: 2, list: 0 },
    fold: { S: [178, 56, 52, 128], bez: 4, rx: 11, side: 0, tab: 12, stand: 0, isl: 1, cols: 1, rows: 6, list: 1 },
    open: { S: [148, 56, 112, 128], bez: 4, rx: 11, side: 0, tab: 12, stand: 0, isl: 0, cols: 3, rows: 3, list: 0 },
  }[kind];
  const [x, y, w, h] = S || D.S, pad = 5, top = D.isl ? 14 : 12;
  const ax = x + D.side + pad, ay = y + top + pad, aw = w - D.side - 2 * pad, ah = h - top - D.tab - 2 * pad;
  const gp = D.list ? 3 : 4, cw = (aw - (D.cols - 1) * gp) / D.cols, ch = D.list ? 12 : (ah - (D.rows - 1) * gp) / D.rows;
  const items = [];
  for (let i = 0; i < 8; i++) {
    const c = i % D.cols, r = Math.floor(i / D.cols), on = r < D.rows;
    items.push({ x: ax + c * (cw + gp), y: ay + Math.min(r, D.rows - 1) * (ch + gp) + (on ? 0 : 8), w: cw, h: ch, v: on ? 1 : 0 });
  }
  return { x, y, w, h, top, bez: D.bez, rx: D.rx, side: D.side, tab: D.tab, stand: D.stand, isl: D.isl, L: D.list, items };
}
const mix = (a, b, t) => typeof a === "number" ? a + (b - a) * t : Array.isArray(a) ? a.map((v, i) => mix(v, b[i], t)) : Object.fromEntries(Object.keys(a).map((k) => [k, mix(a[k], b[k], t)]));
const set = (n, a) => { for (const k in a) n.setAttribute(k, a[k]); };
// the PixxelSpool screen in a device; returns a function that lays it out for a layout state
function makeUI(parent) {
  const top = el("rect", { class: "pi-fillbg" }, parent), logo = el("circle", { r: 2.4, fill: "var(--pi-accent)" }, parent);
  const brand = txt("PixxelSpool", { "font-size": 5, "font-weight": 700, class: "pi-t-ink" }, parent);
  const side = el("rect", { class: "pi-fillbg" }, parent);
  const sideL = [0, 1, 2, 3].map((k) => el("rect", { height: 2.4, rx: 1.2, fill: k ? "var(--pi-quiet)" : "var(--pi-accent)", opacity: k ? .45 : 1 }, parent));
  const tab = el("rect", { class: "pi-fillbg" }, parent);
  const tabD = [0, 1, 2, 3].map((k) => el("circle", { r: 1.7, fill: k ? "var(--pi-quiet)" : "var(--pi-accent)" }, parent));
  const IT = [0, 1, 2, 3, 4, 6, 8, 9].map((i) => {
    const g = el("g", {}, parent), ink = lum(SP[i].c) > 0.62 ? "#111" : "#fff";
    const o = { g, row: el("rect", { class: "pi-fillbg" }, g), sw: el("rect", { fill: SP[i].c, stroke: "#000", "stroke-opacity": ".08", "stroke-width": ".5" }, g) };
    o.gl = [el("rect", { fill: ink }, g), el("rect", { fill: ink }, g)];
    o.ll = [el("rect", { fill: "var(--pi-ink)" }, g), el("rect", { fill: "var(--pi-quiet)" }, g)];
    return o;
  });
  const isl = el("rect", { fill: "#000", rx: 2.4 }, parent);
  return (st) => {
    const { x, y, w, h, L } = st;
    set(top, { x, y, width: w, height: st.top }); set(logo, { cx: x + 7, cy: y + st.top - 6 }); set(brand, { x: x + 12, y: y + st.top - 4.2, opacity: 1 - st.isl });
    set(side, { x, y: y + st.top, width: st.side, height: h - st.top, opacity: st.side / 36 });
    sideL.forEach((r, k) => set(r, { x: x + 5, y: y + 20 + k * 8, width: Math.max(0, st.side - 12) * (k ? .8 : 1) }));
    set(tab, { x, y: y + h - st.tab, width: w, height: st.tab, opacity: st.tab / 12 });
    tabD.forEach((d, k) => set(d, { cx: x + w * (k + .5) / 4, cy: y + h - st.tab / 2, opacity: (st.tab / 12) * (k ? .5 : 1) }));
    set(isl, { x: x + w / 2 - 8, y: y + 2.4, width: 16, height: 4.8, opacity: st.isl });
    IT.forEach((o, k) => {
      const it = st.items[k];
      set(o.g, { opacity: it.v });
      set(o.row, { x: it.x, y: it.y, width: it.w, height: it.h, rx: 3, opacity: L });
      set(o.sw, { x: it.x + 2 * L, y: it.y + 2 * L, width: it.w + (it.h - 4 - it.w) * L, height: it.h - 4 * L, rx: 3 - L });
      set(o.gl[0], { x: it.x + 3, y: it.y + 4, width: it.w * .45, height: 2.4, rx: 1, opacity: (1 - L) * .85 });
      set(o.gl[1], { x: it.x + 3, y: it.y + it.h - 5.5, width: it.w * .6, height: 2, rx: 1, opacity: (1 - L) * .6 });
      set(o.ll[0], { x: it.x + it.h + 1, y: it.y + 3, width: it.w * .5, height: 2.2, rx: 1, opacity: L * .7 });
      set(o.ll[1], { x: it.x + it.h + 1, y: it.y + it.h - 5, width: it.w * .3, height: 1.8, rx: .9, opacity: L * .6 });
    });
  };
}
let clipN = 0;
// rounded rectangle as a path; L and R choose which side gets round corners (the hinge side stays straight)
function rr(x, y, w, h, r, L = true, R = true) {
  const a = (on, ex, ey) => (on ? `A${r} ${r} 0 0 1 ${ex} ${ey}` : `L${ex} ${ey}`);
  return `M${x + (L ? r : 0)} ${y}H${x + w - (R ? r : 0)}${a(R, x + w, y + (R ? r : 0))}V${y + h - (R ? r : 0)}${a(R, x + w - (R ? r : 0), y + h)}` +
    `H${x + (L ? r : 0)}${a(L, x, y + h - (L ? r : 0))}V${y + (L ? r : 0)}${a(L, x + (L ? r : 0), y)}Z`;
}
function clipped(parent, x, y, w, h, rx, L = true, R = true) {
  const id = `pi-c${++clipN}`;
  el("path", { d: rr(x, y, w, h, rx, L, R) }, el("clipPath", { id }, parent));
  return el("g", { "clip-path": `url(#${id})` }, parent);
}
async function chDevices() {
  fresh();
  // host: Raspberry Pi, Mac or Windows PC
  const host = el("g", { opacity: 0 });
  el("rect", { class: "pi-glass", x: 8, y: 54, width: 74, height: 132, rx: 14, filter: "url(#pi-fCard)" }, host);
  const pi = el("g", { transform: "translate(22 68)" }, host);
  el("rect", { width: 46, height: 30, rx: 3, fill: "#2e9a5a" }, pi);
  el("rect", { x: 16, y: 9, width: 13, height: 13, rx: 1.5, fill: "#26262a" }, pi);
  el("rect", { x: 4, y: 2.5, width: 38, height: 2.4, rx: 1, fill: "#e8c547", opacity: .85 }, pi);
  el("rect", { x: 34, y: 19, width: 12, height: 9, rx: 1, fill: "#c9c9cf" }, pi);
  el("rect", { x: 4, y: 20, width: 8, height: 7, rx: 1, fill: "#c9c9cf" }, pi);
  txt("Raspberry Pi", { x: 45, y: 110, "font-size": 6.4, "font-weight": 600, class: "pi-t-ink", "text-anchor": "middle" }, host);
  txt(L("or"), { x: 45, y: 123, "font-size": 6, class: "pi-t-quiet", "text-anchor": "middle" }, host);
  const pc = el("g", { transform: "translate(32 130)" }, host);
  el("rect", { width: 26, height: 34, rx: 3.5, fill: "#3a3a40" }, pc);
  el("rect", { x: 4, y: 5, width: 18, height: 2, rx: 1, fill: "#5a5a62" }, pc);
  el("rect", { x: 4, y: 9.5, width: 18, height: 2, rx: 1, fill: "#5a5a62" }, pc);
  el("circle", { cx: 13, cy: 26, r: 2.4, fill: "var(--pi-accent)" }, pc);
  txt(L("Mac or PC"), { x: 45, y: 178, "font-size": 6.4, "font-weight": 600, class: "pi-t-ink", "text-anchor": "middle" }, host);
  // connection from host to device, with data flowing
  const link = el("path", { fill: "none", stroke: "var(--pi-accent)", "stroke-width": 1.4, "stroke-dasharray": "1.5 4", "stroke-linecap": "round", opacity: 0 });
  const linkTo = (ex, ey) => link.setAttribute("d", `M84 120 C ${(84 + ex) / 2} 120, ${(84 + ex) / 2} ${ey}, ${ex} ${ey}`);
  // the device that changes shape: PC, tablet, phone
  const dev = el("g", { opacity: 0 });
  const stand = el("g", {}, dev);
  const neck = el("rect", { fill: "#2c2c30" }, stand), foot = el("rect", { rx: 2.5, fill: "#3a3a40" }, stand);
  const frame = el("rect", { fill: "#1d1d1f", stroke: "var(--pi-line)", "stroke-width": .8, filter: "url(#pi-fCard)" }, dev);
  const screen = el("rect", { fill: "var(--pi-card-solid)" }, dev);
  const clipR = el("rect", {}, el("clipPath", { id: "pi-scr" }, dev));
  const ui = makeUI(el("g", { "clip-path": "url(#pi-scr)" }, dev));
  const drawDev = (st) => {
    const { x, y, w, h, bez: b } = st;
    set(frame, { x: x - b, y: y - b, width: w + 2 * b, height: h + 2 * b, rx: st.rx });
    set(screen, { x, y, width: w, height: h, rx: Math.max(1.5, st.rx - b) });
    set(clipR, { x, y, width: w, height: h, rx: Math.max(1.5, st.rx - b) });
    set(stand, { opacity: st.stand });
    set(neck, { x: x + w / 2 - 9, y: y + h + b, width: 18, height: 16 });
    set(foot, { x: x + w / 2 - 34, y: y + h + b + 15, width: 68, height: 5 });
    ui(st); linkTo(x - b - 2, y + h / 2);
  };
  const LA = { pc: devLayout("pc"), pad: devLayout("pad"), fold: devLayout("fold") };
  let st = LA.pc; drawDev(st);
  const morph = (to, dur) => tween(val(0, (q) => drawDev(mix(st, to, q.v))), { v: 1 }, dur, { e: E.io }).then(() => { st = to; });
  // the foldable: a cover screen in front, the big inner screen opens like a book
  const HG = 204, FW = 60, FY = 52, FH = 136, inner = devLayout("open");
  const fd = el("g", { opacity: 0 });
  el("path", { d: rr(HG - FW, FY, FW, FH, 11, true, false), fill: "#1d1d1f", stroke: "var(--pi-line)", "stroke-width": .8, filter: "url(#pi-fCard)" }, fd);
  el("path", { d: rr(HG - FW + 4, FY + 4, FW - 4, FH - 8, 7, true, false), fill: "var(--pi-card-solid)" }, fd);
  makeUI(clipped(fd, HG - FW + 4, FY + 4, FW - 4, FH - 8, 7, true, false))(inner);
  const lshade = el("path", { d: rr(HG - FW, FY, FW, FH, 11, true, false), fill: "#000", opacity: 0 }, fd);
  const panel = el("g", {}, fd);
  const pin = el("g", {}, panel);                    // inner side of the right half
  el("path", { d: rr(0, FY, FW, FH, 11, false, true), fill: "#1d1d1f", stroke: "var(--pi-line)", "stroke-width": .8 }, pin);
  el("path", { d: rr(0, FY + 4, FW - 4, FH - 8, 7, false, true), fill: "var(--pi-card-solid)" }, pin);
  makeUI(el("g", { transform: `translate(${-HG} 0)` }, clipped(pin, 0, FY + 4, FW - 4, FH - 8, 7, false, true)))(inner);
  const pout = el("g", { transform: `translate(${FW} 0) scale(-1 1)` }, panel);   // cover side, mirrored so it reads right when folded
  el("rect", { x: 0, y: FY, width: FW, height: FH, rx: 11, fill: "#1d1d1f", stroke: "var(--pi-line)", "stroke-width": .8 }, pout);
  el("rect", { x: 4, y: FY + 4, width: FW - 8, height: FH - 8, rx: 7, fill: "var(--pi-card-solid)" }, pout);
  makeUI(clipped(pout, 4, FY + 4, FW - 8, FH - 8, 7))(devLayout("fold", [4, FY + 4, FW - 8, FH - 8]));
  const pshade = el("path", { d: rr(0, FY, FW, FH, 11, false, true), fill: "#000", opacity: 0 }, panel);
  const hinge = el("g", { opacity: 0 }, fd);           // fully open: one seamless screen, no line at the hinge
  el("path", { d: rr(HG - FW, FY, 2 * FW, FH, 11), fill: "#1d1d1f", stroke: "var(--pi-line)", "stroke-width": .8 }, hinge);
  el("path", { d: rr(HG - FW + 4, FY + 4, 2 * FW - 8, FH - 8, 7), fill: "var(--pi-card-solid)" }, hinge);
  makeUI(clipped(hinge, HG - FW + 4, FY + 4, 2 * FW - 8, FH - 8, 7))(inner);
  const F = { th: Math.PI, dx: 30 };
  F.draw = (q) => {
    const c = Math.cos(q.th), s = Math.sin(q.th);
    fd.setAttribute("transform", `translate(${q.dx} 0)`);
    panel.setAttribute("transform", `matrix(${c} 0 0 1 ${HG} 0)`);
    pin.setAttribute("opacity", c > 0 ? 1 : 0); pout.setAttribute("opacity", c > 0 ? 0 : 1);
    pshade.setAttribute("opacity", .5 * s); lshade.setAttribute("opacity", c < 0 ? .35 * s : 0);
    hinge.setAttribute("opacity", c > .9 ? (c - .9) * 10 : 0);
    linkTo(HG - FW + q.dx - 2, FY + FH / 2);
  };
  await say(L("PixxelSpool runs at your home: <b>on a Raspberry Pi, a Mac or a Windows PC.</b>"));
  const hp = val(0, (q) => { host.setAttribute("opacity", Math.min(1, q.v)); host.setAttribute("transform", `translate(45 120) scale(${.9 + .1 * q.v}) translate(-45 -120)`); });
  await tween(hp, { v: 1 }, 520, { e: E.spring });
  await wait(1300);
  await say(L("You use it in the browser, <b>on your PC …</b>"));
  go(fade(link, 1, 400));
  go((async () => { const f = val(0, (q) => link.setAttribute("stroke-dashoffset", -q.v)); while (true) { await frame1(); f.v = 0; await tween(f, { v: 11 }, 700, { e: E.lin }); } })());
  const dp = val(0, (q) => { dev.setAttribute("opacity", Math.min(1, q.v)); dev.setAttribute("transform", `translate(204 122) scale(${.94 + .06 * q.v}) translate(-204 -122)`); });
  await tween(dp, { v: 1 }, 600, { e: E.spring });
  await wait(1800);
  await say(L("… <b>on a tablet …</b>"));
  await morph(LA.pad, 1100); await wait(1300);
  await say(L("… <b>on your phone …</b>"));
  await morph(LA.fold, 1100); await wait(1000);
  // swap the phone for the foldable, which looks exactly the same while closed
  dev.setAttribute("opacity", 0); fd.setAttribute("opacity", 1); F.draw(F);
  await say(L("… or on foldables. <b>The interface adapts to every device.</b>"));
  await tween(F, { th: 0, dx: 0 }, 1700, { e: E.io });
  await wait(3000);
}

// ---------------------------------------------------------------- player
const CH = [[L("Sort"), chSort], [L("AMS"), chAms], [L("Storage"), chSetup], [L("Brands"), chBrands], [L("Views"), chViews], [L("Catalog"), chCatalog],
  [L("Restock"), chRestock], [L("Printer"), chPrinter], [L("Climate"), chClimate], [L("Statistics"), chStats], [L("Devices"), chDevices]];
const barsEl = host.querySelector(".pi-bars");
barsEl.innerHTML = CH.map(([n], k) => `<button type="button" data-k="${k}" aria-label="${esc(L("Chapter {0}: {1}", k + 1, n))}"><i><b></b></i><span>${esc(n)}</span></button>`).join("");
const btns = [...barsEl.querySelectorAll("button")];
let cur = 0, ended = false;
const STEPS = CH.map(([, f]) => (f.toString().match(/\bsay\(/g) || []).length);
function progress() {
  btns.forEach((b, j) => { b.classList.toggle("on", j === cur); b.querySelector("b").style.width = j < cur ? "100%" : j > cur ? "0" : Math.min(100, stepNo / STEPS[cur] * 100) + "%"; });
}
// run chapter k; with "to" it jumps straight to that caption of the chapter
async function run(k, to = 0) {
  ended = false;
  if (PAUSED) setPause(false);
  const my = ++gen; cur = k; stepNo = 0; FF = to > 1 ? to : 0; progress();
  try { await CH[k][1](); } catch (e) { if (e !== STOP) throw e; return; }
  if (my !== gen) return;
  FF = 0; stepNo = STEPS[k]; progress();
  if (k + 1 < CH.length) return run(k + 1);
  ended = true; setPause(true);        // the end: it stops here, play starts it again from the beginning
}
const back = () => (stepNo > 1 ? run(cur, stepNo - 1) : cur > 0 ? run(cur - 1, STEPS[cur - 1]) : run(0));
const fwd = () => (stepNo < STEPS[cur] ? run(cur, stepNo + 1) : run((cur + 1) % CH.length));
btns.forEach((b) => (b.onclick = () => run(+b.dataset.k)));
const pauseB = $c("pause"), slowB = $c("slow");
function setPause(p) {
  if (p === PAUSED) return;
  if (p) pausedAt = performance.now(); else lost += performance.now() - pausedAt;
  PAUSED = p; pauseB.classList.toggle("paused", p); pauseB.setAttribute("aria-pressed", p);
  pauseB.title = L(p ? "Resume" : "Pause"); pauseB.setAttribute("aria-label", pauseB.title);
}
pauseB.onclick = () => (ended ? run(0) : setPause(!PAUSED));
slowB.onclick = () => { SLOW = SLOW === 1 ? 2 : 1; slowB.setAttribute("aria-pressed", SLOW === 2); };
$c("replay").onclick = () => run(0);
$c("next").onclick = fwd;
$c("prev").onclick = back;
run(0);
return () => { gen++; host.innerHTML = ""; };       // stop: every running tween sees the new generation and ends
}
