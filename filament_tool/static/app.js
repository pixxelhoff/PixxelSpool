// PixxelSpool web UI – a single page without a build step or framework.
//
// Data comes from the REST API in main.py; /api/events (server-sent events) triggers a refresh when something
// changes. Every view is plain HTML rendered from template strings (always escape user data with esc()).
// User-facing texts are written in English and translated via L()/T()/tr() with the dictionaries in
// filament_tool/locales/*.json; run tools/i18n.py after adding or changing texts.
"use strict";
const $ = (s) => document.querySelector(s);
// escape text for use inside HTML
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
// ------------------------------------------------------------ i18n (English is the source text, de/es come from filament_tool/locales/*.json)
const LANG = window.PS_LANG || "en", DICT = window.PS_DICT || {};
document.documentElement.lang = LANG;
const LOCALE = { de: "de-DE", en: "en-GB", es: "es-ES" }[LANG] || "en-GB";
const fmt = (s, a) => String(s).replace(/\{(\d)\}/g, (m, i) => (a[i] ?? m));
// L(englishText, …values): translated text with {0} {1} … replaced
const L = (s, ...a) => fmt(DICT[s] || s, a);
// Lp(n, singular, plural): singular/plural, e.g. "{0} spool" / "{0} spools"
const Lp = (n, one, many) => L(n === 1 ? one : many, n);
// tr(text): translate text from the server (errors, status, history) – exact match or via a {0} pattern
let PATS = null;
function tr(s, depth = 0) {
  if (s == null || LANG === "en" || s === "") return s;
  s = String(s);
  if (DICT[s]) return DICT[s];
  if (depth > 2) return s;
  if (!PATS) PATS = Object.keys(DICT).filter((k) => DICT[k] && /\{\d\}/.test(k) && k.replace(/\{\d\}/g, "").trim().length > 2).map((k) => {
    const idx = [], re = k.split(/(\{\d\})/).map((part) => {
      const m = part.match(/^\{(\d)\}$/);
      if (m) { idx.push(+m[1]); return "(.+?)"; }
      return part.replace(/[.*+?^$()|[\]\\{}]/g, "\\$&");
    }).join("");
    return [new RegExp("^" + re + "$", "s"), k, idx];
  });
  for (const [re, k, idx] of PATS) {
    const m = s.match(re);
    if (m) { const a = []; idx.forEach((n, j) => (a[n] = tr(m[j + 1], depth + 1))); return fmt(DICT[k], a); }
  }
  // several messages joined with " · ": translate each one
  return s.includes(" · ") ? s.split(" · ").map((x) => tr(x, depth + 1)).join(" · ") : s;
}
// translate the static texts of index.html (text nodes and placeholder/title/aria-label)
function translateStatic(root) {
  if (LANG === "en") return;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: (n) => n.parentNode.closest("script,style,code") ? 2 : 1 });
  for (let n; (n = w.nextNode());) {
    const t = n.nodeValue.trim();
    if (t && DICT[t]) n.nodeValue = n.nodeValue.replace(t, DICT[t]);
  }
  root.querySelectorAll("[placeholder],[title],[aria-label]").forEach((e) => {
    for (const a of ["placeholder", "title", "aria-label"]) { const v = e.getAttribute(a); if (v && DICT[v]) e.setAttribute(a, DICT[v]); }
  });
}
translateStatic(document.body);

const I18N = {
  en: { title: "PixxelSpool", tabStorage: "Storage", tabCatalog: "Catalog", viewCompact: "Compact", viewDetail: "Detail", viewList: "List", amsSummary: (n) => L("{0} used", n), extTitle: (n) => L("External spools ({0})", n), extUnused: "not in use",
    overflowTitle: "Reserve", history: "History", search: "Search", searchLong: "Color, number, line, slot …",
    onlyMissing: "missing colors only", onlyOwnedLines: "only lines I own",
    stats: (s) => L("Slots {0}/{1} used · {2} in reserve · {3} in use · {4} not scanned yet", s.cabinet_used, s.cabinet_slots, s.overflow, s.in_use, s.unscanned),
    stored: "in storage", in_use: "in use", empty: "empty", cabinet: "Fixed slot", overflow: "Reserve", refill: "Refill",
    unscanned: "not scanned yet", known: "known spool", linkedNote: "newly linked", slot: "Storage slot",
    take: "Take out", ret: "Put back", restore: "Store again", move: "Move", markEmpty: "Empty", cancel: "Cancel",
    idleTitle: "Place a spool on the reader", tagUnderLogo: "On Bambu Lab spools the NFC tag sits under the logo, hold that spot against the reader.",
    serial: "Serial no.", variant: "Variant", weight: "Weight", produced: "Produced", nozzle: "Nozzle", bed: "Bed", drying: "Drying",
    newSpool: "New spool", proposeCab: "Suggested slot", proposeOverflow: "Color already in storage → reserve",
    storeHere: "Store here", otherSlot: "Other slot", pickNew: "Tap a slot for the new spool",
    pickMove: (n) => L("Tap a new place for {0} (occupied place: swap)", n), movedTo: (x) => L("Moved to {0}", x), storedIn: (x) => L("Stored in {0}", x),
    taken: "Taken out", putBack: "Stored", emptied: "Spool marked as empty.",
    successor: (x) => L("There is another spool of this in the reserve ({0}).", x), promote: (x) => L("Move it up to {0}", x), promoted: "Moved up.",
    freed: (x) => L("Slot {0} is free now.", x), linked: "Linked to your stock. Is it somewhere else? Then use “Move”.",
    unknownColor: "I don't know this color yet. Which filament is it? I'll remember it for all future spools.",
    fromStock: "From your stock", allOthers: "All others", alreadyMapped: "already assigned", assign: "Assign",
    orNew: "… or create a new filament", colorName: "Color name", bambuNo: "Bambu number", create: "Create",
    needName: "Please enter a color name", nothing: "Nothing found", notOwned: "not in stock",
    colorsOf: (o, t) => L("{0} of {1} colors", o, t), complete: "complete", missing: "missing", spools: (n) => Lp(n, "{0} spool", "{0} spools"),
    ha: { off: "HA off", connected: "HA connected", error: "HA error" },
    inAms: (x) => L("in AMS: {0}", x), toReturn: "to put back", remain: (n) => L("{0} % left", n),
    amsTitle: "AMS", amsEmpty: "empty", amsHome: "Storage slot", amsUnknown: "not in storage – scan it once", amsNoTag: "without Bambu tag",
    returnsTitle: (n) => Lp(n, "{0} spool taken out of the AMS, please put it back:", "{0} spools taken out of the AMS, please put them back:"),
    lowRemain: "According to the AMS the spool is almost empty. When it's empty, tap “Empty”.",
    reader: { ready: "Reader ready", simulated: "Simulation", disconnected: "Reader disconnected", missing: "No reader", starting: "Reader starting …" },
    tabTools: "Options", sysTitle: "Raspberry Pi", sysIntro: "Always shut down here before unplugging and wait until the green LED on the Pi is off. A backup is made first.", sysReboot: "Restart", sysPoweroff: "Shut down", sysConfirmPoweroff: "Shut down the Pi now? PixxelSpool will only be reachable again after replugging it.", sysConfirmReboot: "Restart the Pi now? This takes about a minute.", sysDone: "Working …", close: "Close",
    batchTitle: "Bulk inventory", batchStart: "Start bulk inventory", batchFinish: "Done – show slots", batchCancel: "Cancel",
    batchIntro: "Scan all spools you want to store, one after the other. Nothing is saved yet. When you're done, PixxelSpool assigns all spools to suitable slots and shows you a list sorted by storage and level.",
    batchRunning: (n) => Lp(n, "Bulk inventory running · {0} spool scanned · place the next spool", "Bulk inventory running · {0} spools scanned · place the next spool"),
    batchTip: "Bambu Lab spools can also be scanned in their box.", batchLogo: "On Bambu Lab spools the NFC tag sits under the logo.",
    batchDup: "This spool is already on the list.", batchDone: (n) => L("{0} spools processed. Here's where they go:", n),
    bNew: "new", bSpare: "spare spool → reserve", bLinked: "from stock", bKnown: "already registered", bUnknown: "unknown color – scan individually", bDuplicate: "already in storage – no reserve", bPrint: "Print",
    resetTitle: "Reset storage", resetBtn: "Remove all spools",
    resetIntro: "Removes all spools from storage. Color catalog, assignments and slots are kept. A database backup is made first.",
    resetType: "Type RESET to confirm", resetDone: (n, f) => L("{0} spools removed. Backup: {1}", n, f),
    shelf: (c, n) => L("{0} · reserve {1}", cabName(c), n), tabReorg: "Reorganize", reorgIntro: "These spools are not where they belong: outside the block of their line, or in a storage that does not suit the material (e.g. PETG outside the dry zone). Spools you put on a slot yourself are not listed. Work through the list from the top and tap “Done” after each move. Greyed-out steps become possible once an earlier step has freed the slot.",
    done: "Done", noRoom: "no free slot", reorgEmpty: "Everything is in the right place.",
    offline: "Lost connection to the server", received: "Received", opened: "Opened", notOpened: "unopened",
    ago: (n) => n <= 0 ? L("today") : n < 60 ? Lp(n, "{0} day ago", "{0} days ago") : n < 730 ? L("{0} months ago", Math.round(n / 30.4)) : L("{0} years ago", (n / 365).toLocaleString(LOCALE, { maximumFractionDigits: 1 })),
    change: "change" },
};
// T(key): text from the table above, translated
const T = (k, ...a) => { const v = I18N.en[k] ?? k; return typeof v === "function" ? v(...a) : L(v); };
const cname = (o) => (LANG === "de" ? o.name_de : o.name_en) || o.color_name || "";
const STATUS = new Proxy({}, { get: (_, k) => T(k) });

let overview = null;   // data from /api/overview
let insights = null, dryOpen = false, shopOpen = false, missOpen = false, usageOpen = false;
const SET = () => overview?.settings || { cabinets: [], low_remain_pct: 5 };
const CABS = () => SET().cabinets || [];
const cabOf = (key) => CABS().find((c) => c.key === key);
const cabName = (key) => cabOf(key)?.name ?? key;
const cabTitle = (key) => { const c = cabOf(key); return c ? c.name + (c.label ? " · " + c.label : "") : key; };
function rowLab(c, r) {
  if (c?.numbering !== "alpha") return String(r);
  let s = ""; for (let n = r; n > 0; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + ((n - 1) % 26)) + s; return s;
}
let panel = null;      // { kind, ... } what the side panel shows
let pick = null;       // { label, onPick(slotId) } while the user picks a slot

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && data.login) { showLogin(); return new Promise(() => {}); }   // signed out: stop here, the page reloads after sign-in
  if (!res.ok) throw new Error(tr(data.error || data.detail || res.statusText));
  return data;
}
// ------------------------------------------------------------ app password: sign-in screen
const PI_RESET = "cd ~/pixxelspool && .venv/bin/python -m filament_tool.auth reset";
// where PixxelSpool runs ("pi", "windows", "mac", "desktop"): from the overview, or from /api/auth before signing in
let authHost = "";
const hostKind = () => overview?.host?.kind || authHost;
// how to remove a forgotten password without the recovery code: only the way that fits this platform
function resetHelp() {
  const k = hostKind();
  const pi = `<p class="sub">${L("On the Raspberry Pi, enter this in the terminal. It removes the password, your data stays as it is:")}</p><code>${esc(PI_RESET)}</code>`;
  const win = `<p class="sub">${L("Windows app: right-click the PixxelSpool icon next to the clock › “Reset password”.")}</p>`;
  const mac = `<p class="sub">${L("Mac app: click the PixxelSpool icon in the menu bar › “Reset password”.")}</p>`;
  return k === "pi" ? pi : k === "windows" ? win : k === "mac" ? mac : pi + win + mac;
}
// ------------------------------------------------------------ passkeys (WebAuthn): browsers allow them only on HTTPS or localhost
const passkeyOK = () => window.isSecureContext && !!window.PublicKeyCredential && !!navigator.credentials;
const b64u = {
  dec: (s) => { s = String(s).replace(/-/g, "+").replace(/_/g, "/"); return Uint8Array.from(atob(s + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0)).buffer; },
  enc: (buf) => { let t = ""; new Uint8Array(buf).forEach((b) => { t += String.fromCharCode(b); }); return btoa(t).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); },
};
function pkError(e) {   // the browser's own errors are technical: say it in plain words
  if (e?.name === "NotAllowedError" || e?.name === "AbortError") return new Error(L("Passkey cancelled or not allowed."));
  if (e?.name === "InvalidStateError") return new Error(L("This device already has a passkey for PixxelSpool."));
  if (e?.name === "SecurityError") return new Error(L("Passkeys only work on the secure HTTPS address."));
  return e instanceof Error ? e : new Error(String(e));
}
async function pkCreate(o) {   // options from the server (JSON) -> new passkey -> JSON for the server
  const pk = { ...o, challenge: b64u.dec(o.challenge), user: { ...o.user, id: b64u.dec(o.user.id) },
    excludeCredentials: (o.excludeCredentials || []).map((c) => ({ ...c, id: b64u.dec(c.id) })) };
  let c; try { c = await navigator.credentials.create({ publicKey: pk }); } catch (e) { throw pkError(e); }
  return { id: c.id, rawId: b64u.enc(c.rawId), type: c.type, authenticatorAttachment: c.authenticatorAttachment || undefined,
    clientExtensionResults: c.getClientExtensionResults?.() || {},
    response: { clientDataJSON: b64u.enc(c.response.clientDataJSON), attestationObject: b64u.enc(c.response.attestationObject),
      transports: c.response.getTransports?.() || [] } };
}
async function pkGet(o) {
  const pk = { ...o, challenge: b64u.dec(o.challenge), allowCredentials: (o.allowCredentials || []).map((c) => ({ ...c, id: b64u.dec(c.id) })) };
  let c; try { c = await navigator.credentials.get({ publicKey: pk }); } catch (e) { throw pkError(e); }
  return { id: c.id, rawId: b64u.enc(c.rawId), type: c.type, authenticatorAttachment: c.authenticatorAttachment || undefined,
    clientExtensionResults: c.getClientExtensionResults?.() || {},
    response: { clientDataJSON: b64u.enc(c.response.clientDataJSON), authenticatorData: b64u.enc(c.response.authenticatorData),
      signature: b64u.enc(c.response.signature), userHandle: c.response.userHandle ? b64u.enc(c.response.userHandle) : undefined } };
}
async function jpost(url, body) {   // fetch without the sign-in handling of api() (used on the sign-in screen)
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(tr(d.error || r.statusText));
  return d;
}
function pkDeviceName() {   // a first guess for the passkey's name, the user can change it
  const ua = navigator.userAgent;
  return /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1) ? "iPad"
    : /Android/.test(ua) ? "Android" : /Macintosh/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "Passkey";
}
function showLogin(recover = false) {
  let el = $("#login");
  if (el && !recover && el.dataset.mode) return;   // already shown: a background request must not throw the user out of "Forgot password?"
  if (!el) { el = document.createElement("div"); el.id = "login"; el.className = "login"; document.body.append(el); }
  document.body.classList.add("locked"); document.body.classList.remove("booting");
  el.dataset.mode = recover ? "recover" : "login";
  el.innerHTML = `<form class="logincard" autocomplete="on">
      <div class="lgbrand"><img class="logo" src="/static/logo.svg?v=5" alt="">
        <h1><span class="wordmark" translate="no">Pi<span class="xx"><span>x</span><span>x</span></span>elSpool</span></h1></div>
      ${recover ? `<p class="sub">${L("Enter the recovery code you wrote down when you set the password, and choose a new password.")}</p>
        <label class="lgfield"><span>${L("Recovery code")}</span><input id="lgcode" autocomplete="off" autocapitalize="characters" spellcheck="false"></label>
        <label class="lgfield"><span>${L("New password")}</span><input id="lgpw" type="password" autocomplete="new-password"></label>
        <button class="primary" type="submit">${L("Set new password")}</button>
        <details class="lgpi"><summary>${L("No code at hand?")}</summary>
          <div id="lgreset">${resetHelp()}</div></details>
        <button type="button" class="linkbtn" id="lgback">${L("Back to sign-in")}</button>`
      : `<p class="sub">${L("Please enter the password.")}</p>
        <input id="lgpw" type="password" autocomplete="current-password" aria-label="${esc(L("Password"))}">
        <label class="check"><input type="checkbox" id="lgkeep" checked> ${L("Stay signed in on this device")}</label>
        <button class="primary" type="submit">${L("Sign in")}</button>
        <div id="lgpk" hidden></div>
        <button type="button" class="linkbtn" id="lgforgot">${L("Forgot password?")}</button>`}
      <p class="msg err" id="lgmsg" hidden></p>
    </form>`;
  const f = el.querySelector("form"), msg = $("#lgmsg");
  setTimeout(() => (recover ? $("#lgcode") : $("#lgpw")).focus(), 50);
  if (recover && !hostKind()) fetch("/api/auth").then((r) => r.json()).then((d) => {   // signed out: no overview yet
    authHost = d.host || ""; const box = $("#lgreset"); if (box && authHost) box.innerHTML = resetHelp();
  }).catch(() => {});
  if (!recover) fetch("/api/auth").then((r) => r.json()).then((d) => {   // passkey button only when some are saved
    authHost = d.host || authHost;
    const box = $("#lgpk"); if (!box || !d.passkeys || !d.passkey_lib) return;
    box.hidden = false;
    if (!passkeyOK()) { box.innerHTML = `<p class="sub">${L("Passkeys only work on the secure HTTPS address (e.g. via Tailscale). Here, please use the password.")}</p>`; return; }
    box.innerHTML = `<button type="button" class="lgpkbtn" id="lgpkbtn">${L("Sign in with passkey")}</button>`;
    $("#lgpkbtn").onclick = async () => {
      msg.hidden = true; const b = $("#lgpkbtn"); b.disabled = true;
      try {
        const o = await jpost("/api/auth/passkey/options");
        const credential = await pkGet(o.options);
        await jpost("/api/auth/passkey/login", { ticket: o.ticket, credential, remember: $("#lgkeep").checked });
        location.reload();
      } catch (err) { msg.textContent = err.message; msg.hidden = false; b.disabled = false; }
    };
  }).catch(() => {});
  const brand = el.querySelector(".lgbrand"), hop = () => { brand.classList.remove("hop"); void brand.offsetWidth; brand.classList.add("hop"); };
  if (!recover) setTimeout(hop, 350);                 // the two x greet once, and again on every tap or click on the logo
  brand.addEventListener("click", hop);
  $("#lgforgot")?.addEventListener("click", () => showLogin(true));
  $("#lgback")?.addEventListener("click", () => { el.dataset.mode = ""; showLogin(false); });
  f.onsubmit = async (e) => {
    e.preventDefault(); msg.hidden = true;
    const btn = f.querySelector("button[type=submit]"); btn.disabled = true;
    try {
      const url = recover ? "/api/auth/recover" : "/api/auth/login";
      const body = recover ? { code: $("#lgcode").value, password: $("#lgpw").value } : { password: $("#lgpw").value, remember: $("#lgkeep").checked };
      const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(tr(d.error || r.statusText));
      if (recover && d.code) await showRecoveryCode(d.code);
      location.reload();
    } catch (err) { msg.textContent = err.message; msg.hidden = false; btn.disabled = false; $("#lgpw").select(); }
  };
}
// the recovery code is shown exactly once: copy it, write it down, print it
function showRecoveryCode(code) {
  return ask(`<div class="cabhelp"><p>${L("If you ever forget the password, this code lets you set a new one. It is shown only now – write it down or print it and keep it somewhere safe.")}</p>
      <div class="rcode" translate="no">${esc(code)}</div>
      <p class="sub">${L(hostKind() === "pi" ? "Without the code, the password can only be removed on the Raspberry Pi itself (terminal)."
        : hostKind() === "windows" ? "Without the code, the password can only be removed in the Windows app (PixxelSpool icon next to the clock)."
        : hostKind() === "mac" ? "Without the code, the password can only be removed in the Mac app (PixxelSpool icon in the menu bar)."
        : "Without the code, the password can only be removed on the Pi itself (terminal) or in the Windows or Mac app.")}</p></div>`,
    { title: L("Your recovery code"), block: true, noCancel: true, ok: L("I've written it down"),
      extra: [{ label: L("Copy"), value: "copy" }, { label: L("Print"), value: "print" }] }).then((v) => {
    if (v === "copy") { navigator.clipboard?.writeText(code).then(() => toast(L("Copied"))).catch(() => {}); return showRecoveryCode(code); }
    if (v === "print") {
      const w = window.open("", "_blank");
      if (w) { w.document.write(`<title>PixxelSpool</title><body style="font-family:system-ui;padding:40px"><h2>PixxelSpool – ${esc(L("Your recovery code"))}</h2><p style="font:700 28px ui-monospace,monospace;letter-spacing:.08em">${esc(code)}</p><p>${esc(new Date().toLocaleDateString(LOCALE))}</p></body>`); w.document.close(); w.print(); }
      return showRecoveryCode(code);
    }
  });
}
function toast(text, action = null) {   // action: { label, run } adds a button (e.g. "Undo") and keeps it longer
  const t = $("#toast"); t.textContent = text; t.hidden = false;
  if (action) {
    const b = Object.assign(document.createElement("button"), { className: "toastact", textContent: action.label });
    b.onclick = () => { t.hidden = true; clearTimeout(toast.t); action.run(); };
    t.append(b);
  }
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), action ? 10000 : 2600);
}
function textOn(hex) {
  if (!hex) return "";
  const n = parseInt(hex.slice(1), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? "#111" : "#fff";
}
function swBg(o) {
  let cols = [];
  try { cols = JSON.parse(o.colors || "[]"); } catch (e) {}
  if (cols.length > 1) return `background:linear-gradient(135deg, ${cols.join(", ")})`;
  return o.hex ? `background:${o.hex}` : "";
}
const sw = (o, cls = "") => `<span class="swatch ${cls}${o && typeof o === "object" && o.is_refill ? " refill" : ""}" style="${typeof o === "string" ? `background:${o}` : o ? swBg(o) : ""}"></span>`;
const title = (o) => `${esc(o.line)} ${esc(cname(o))}`;

// ------------------------------------------------------------ dates and age
function parseDay(v) {           // "2024_08_04_22_41" or "2026-11-13"
  if (!v) return null;
  const m = String(v).match(/^(\d{4})[_-](\d{2})[_-](\d{2})/);
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
}
// date and time format from the options (auto: by language)
const DATE_FMT = () => { const f = SET().date_fmt; return f && f !== "auto" ? f : LANG === "de" ? "dmy." : "dmy/"; };
const HOUR12 = () => { const f = String(SET().time_fmt || "auto"); return f === "auto" ? LANG === "en" : f === "12"; };
function fmtDay(d) {
  const p2 = (n) => String(n).padStart(2, "0"), D = p2(d.getDate()), M = p2(d.getMonth() + 1), Y = d.getFullYear();
  return { "dmy.": `${D}.${M}.${Y}`, "dmy/": `${D}/${M}/${Y}`, "mdy/": `${M}/${D}/${Y}`, "ymd-": `${Y}-${M}-${D}` }[DATE_FMT()];
}
// text in the chosen format -> "YYYY-MM-DD" (or "" when it cannot be read)
function parseFmtDay(t) {
  const n = String(t || "").match(/\d+/g); if (!n || n.length < 3) return "";
  const f = DATE_FMT(), [y, m, d] = f === "ymd-" ? [n[0], n[1], n[2]] : f === "mdy/" ? [n[2], n[0], n[1]] : [n[2], n[1], n[0]];
  const Y = y.length === 2 ? 2000 + +y : +y, dt = new Date(Y, +m - 1, +d);
  return dt.getFullYear() === Y && dt.getMonth() === +m - 1 && dt.getDate() === +d ? `${Y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}` : "";
}
// weights: grams up to 999 g, from 1000 g on in kilograms with two decimals ("1,00 kg")
const gkg = (g) => { g = +g || 0; return Math.round(g) < 1000 ? `${Math.round(g)} g` : (g / 1000).toLocaleString(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " kg"; };
const fmtTime = (d) => d.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit", hour12: HOUR12() });
const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function daysSince(d) { const t = new Date(); t.setHours(0, 0, 0, 0); return Math.round((t - d) / 864e5); }
function ageLine(v) { const d = parseDay(v); return d ? `${fmtDay(d)} · ${T("ago", daysSince(d))}` : "–"; }
function ageBlock(s) {
  return `<dl><dt>${T("produced")}</dt><dd>${ageLine(s.production)}</dd>
    <dt>${T("received")}</dt><dd>${ageLine(s.received_at)} <a href="#" data-edit="received_at" class="sub">${T("change")}</a></dd>
    <dt>${T("opened")}</dt><dd>${s.opened_at ? ageLine(s.opened_at) : T("notOpened")} <a href="#" data-edit="opened_at" class="sub">${T("change")}</a></dd>
    ${s.last_used ? `<dt>${L("Last used")}</dt><dd>${ageLine(s.last_used)}</dd>` : ""}</dl>
    ${panel.dateEdit ? `<div class="dateedit"><b>${L(panel.dateEdit.field === "opened_at" ? "Opened on" : "Received on")}</b>
      <div class="datein"><input id="datepick" inputmode="numeric" autocomplete="off" value="${esc(panel.dateEdit.value ? fmtDay(parseDay(panel.dateEdit.value)) : "")}" placeholder="${esc(fmtDay(new Date(2026, 11, 31)).replace("2026", L("YYYY")).replace("12", L("MM")).replace("31", L("DD")))}">
        <button class="small calbtn" id="calbtn" aria-label="${esc(L("Calendar"))}" title="${esc(L("Calendar"))}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg></button>
        <input type="date" id="datenative" tabindex="-1" aria-hidden="true" value="${esc(panel.dateEdit.value)}" max="${isoDay(new Date())}"></div>
      <div class="actions"><button class="small" id="datetoday">${L("Today")}</button>${panel.dateEdit.field === "opened_at" && s.opened_at ? `<button class="small" id="dateclear">${L("Unopened")}</button>` : ""}
      <button class="small" id="datecancel">${L("Cancel")}</button><button class="small primary" id="datesave">${L("Save")}</button></div></div>` : ""}`;
}

// ------------------------------------------------------------ language
function applyLang() {
  document.querySelectorAll("[data-t]").forEach((e) => (e.textContent = T(e.dataset.t)));
  document.querySelectorAll("[data-lang]").forEach((b) => b.classList.toggle("on", b.dataset.lang === LANG));
  requestAnimationFrame(() => moveTabKnob(false));
  $("#q").placeholder = T(document.activeElement === $("#q") ? "searchLong" : "search");
  document.title = T("title");
}
// the language applies to all devices (settings.json); reload the page afterwards
async function setLang(l) {
  if (l === LANG) return;
  try {
    await api("/api/settings", { method: "PUT", body: { lang: l } });
    if (wiz.open) try { sessionStorage.setItem("wizStep", String(wiz.i)); } catch (e) {}   // reopen it after the reload
    location.reload();
  } catch (e) { toast(e.message); }
}
document.querySelectorAll("[data-lang]").forEach((b) => (b.onclick = () => setLang(b.dataset.lang)));

// ------------------------------------------------------------ views
let view = "storage", catalogData = null;
const pref = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } };
shopOpen = pref("shopFold", "0") === "1";   // shopping list: folded unless opened on this device
const setPref = (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} };
let amsOpen = pref("amsOpen", "0") === "1", logOpen = pref("logOpen", "0") === "1", cabMode = pref("cabMode", "compact");
document.querySelectorAll("[data-view]").forEach((b) => (b.onclick = () => showView(b.dataset.view)));
function openNav() { document.body.classList.add("navopen"); $("#navdim").hidden = false; }
function closeNav() { document.body.classList.remove("navopen"); $("#navdim").hidden = true; }
$("#burger").onclick = () => (document.body.classList.contains("navopen") ? closeNav() : openNav());
$("#navdim").onclick = closeNav;
// sliding glass knob behind the active tab (top bar, tab row and rail; the drawer menu keeps its plain highlight)
const tabKnob = Object.assign(document.createElement("span"), { className: "tabknob", ariaHidden: "true" });
$("#nav").prepend(tabKnob);
let knobAt = null;
function moveTabKnob(animate = false) {
  const nav = $("#nav"), b = nav.querySelector("button.on"), body = document.body;
  const drawer = matchMedia("(max-width: 700px)").matches && !body.classList.contains("rail") && !body.classList.contains("toptabs");
  if (!b || drawer || !b.offsetWidth) { nav.classList.remove("slide"); knobAt = null; return; }
  nav.classList.add("slide");   // positioned first, so the offsets are measured inside the nav
  const to = { left: b.offsetLeft, top: b.offsetTop, width: b.offsetWidth, height: b.offsetHeight };
  const still = !animate || !knobAt || matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!still) {
    // liquid: the drop stretches over both tabs on the way, then settles with a little overshoot
    const from = knobAt, mid = { left: Math.min(from.left, to.left), top: Math.min(from.top, to.top),
      width: Math.max(from.left + from.width, to.left + to.width) - Math.min(from.left, to.left),
      height: Math.max(from.top + from.height, to.top + to.height) - Math.min(from.top, to.top) };
    const px = (r, sq) => ({ left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px", transform: `scale(${sq})` });
    tabKnob.animate([px(from, 1), { ...px(mid, 0.94), offset: 0.45 }, px(to, 1)],
      { duration: 480, easing: "cubic-bezier(.3,1.25,.5,1)" });
  }
  Object.assign(tabKnob.style, { left: to.left + "px", top: to.top + "px", width: to.width + "px", height: to.height + "px" });
  knobAt = to;
}
// header height as a CSS variable (the selection bar sticks right under it; the header wraps on narrow screens)
const headRO = window.ResizeObserver && new ResizeObserver(() => document.documentElement.style.setProperty("--headh", $("header").offsetHeight + "px"));
headRO?.observe($("header"));
let knobT; addEventListener("resize", () => { clearTimeout(knobT); knobT = setTimeout(() => moveTabKnob(false), 160); });
// the tabs can change size without a window resize (labels shown or hidden in the rail, Safari toolbars): the
// highlight then stayed at the old size and position
if (window.ResizeObserver) new ResizeObserver(() => { clearTimeout(knobT); knobT = setTimeout(() => moveTabKnob(false), 60); }).observe($("#nav"));
document.fonts?.ready.then(() => moveTabKnob(false));
addEventListener("load", () => setTimeout(() => moveTabKnob(false), 300));
// the same sliding knob for every segmented switch (24 h / 7 Tage, theme, language, ...) and the options list
const KNOB_GROUPS = ".seg, #optnav", knobMem = new Map();
function knobRect(b) { return { left: b.offsetLeft, top: b.offsetTop, width: b.offsetWidth, height: b.offsetHeight }; }
function slideKnob(k, from, to) {   // liquid move: stretch over both positions, then settle
  if (!from || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (from.left === to.left && from.top === to.top && from.width === to.width) return;
  const mid = { left: Math.min(from.left, to.left), top: Math.min(from.top, to.top),
    width: Math.max(from.left + from.width, to.left + to.width) - Math.min(from.left, to.left),
    height: Math.max(from.top + from.height, to.top + to.height) - Math.min(from.top, to.top) };
  const px = (r, sq) => ({ left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px", transform: `scale(${sq})` });
  return k.animate([px(from, 1), { ...px(mid, 0.94), offset: 0.45 }, px(to, 1)], { duration: 460, easing: "cubic-bezier(.3,1.25,.5,1)" });
}
function placeSegKnob(g, b, animate) {
  if (g.id === "optnav" && getComputedStyle(g).flexDirection !== "column") { g.classList.remove("slide"); return; }  // phone: chips
  b = b || g.querySelector(":scope > button.on");
  let k = g.querySelector(":scope > .segknob");
  if (!b || !b.offsetWidth) { g.classList.remove("slide"); if (k) k._at = null; return; }
  const key = g.id || (g.classList.contains("climrange") ? "climrange" : "");   // switches that get redrawn
  if (!k) {   // a redrawn switch (e.g. the climate range) continues the slide from where the old one was
    k = Object.assign(document.createElement("span"), { className: "segknob", ariaHidden: "true" }); g.prepend(k);
    const m = key ? knobMem.get(key) : null, ago = m ? performance.now() - m.t : 1e9;
    k._at = m?.at || null;
    if (m?.from && ago < 460) {    // the old switch was mid-slide: finish that slide here
      g.classList.add("slide"); const to = knobRect(b);
      Object.assign(k.style, { left: to.left + "px", top: to.top + "px", width: to.width + "px", height: to.height + "px" });
      const a = slideKnob(k, m.from, to); if (a) a.currentTime = ago;
      k._at = to; knobMem.set(key, { ...m, at: to }); return;
    }
  }
  g.classList.add("slide");   // positioned first: the offsets below must be measured inside the switch itself
  const to = knobRect(b);
  const moved = animate && k._at && (k._at.left !== to.left || k._at.top !== to.top);
  if (animate) slideKnob(k, k._at, to);
  Object.assign(k.style, { left: to.left + "px", top: to.top + "px", width: to.width + "px", height: to.height + "px" });
  if (key) knobMem.set(key, moved ? { at: to, from: k._at, t: performance.now() } : { ...(knobMem.get(key) || {}), at: to });
  k._at = to;
}
document.addEventListener("click", (e) => {   // start the slide right away, before the view redraws
  const b = e.target.closest("button"), g = b?.parentElement;
  if (g && g.matches(KNOB_GROUPS)) placeSegKnob(g, b, true);
}, true);
let segRaf = 0;
function syncSegKnobs() { segRaf = 0; document.querySelectorAll(KNOB_GROUPS).forEach((g) => placeSegKnob(g, null, false)); }
new MutationObserver(() => { if (!segRaf) segRaf = requestAnimationFrame(syncSegKnobs); })
  .observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "hidden"] });
addEventListener("resize", () => { if (!segRaf) segRaf = requestAnimationFrame(syncSegKnobs); });
function showView(v) {
  if (v === "shop") v = "catalog";   // the shopping list lives in the catalog since 1.0.0-alpha.6
  view = v;
  document.body.dataset.view = v;
  document.querySelectorAll("[data-view]").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
  moveTabKnob(true);
  for (const id of ["storage", "printerview", "print", "catalog", "statsview", "reorg", "tools"]) $("#" + id).hidden = v !== id;
  placePrinter();
  closeNav(); window.scrollTo(0, 0);
  if (v === "catalog") loadCatalog();
  if (v === "reorg") drawReorg();
  if (v === "tools") { resetOpts(); loadRemote(); loadUpdate(); loadBrands(); loadPrices(); loadOffsite(); loadPush(); loadBambuCfg(); }
  if (v === "statsview") loadStatsView();
}
async function loadCatalog() { catalogData = await api("/api/catalog"); drawCatalog(); }
function drawCatalog() {
  if (!catalogData) return;
  const onlyMissing = $("#onlymissing").checked, onlyOwned = $("#onlyowned").checked;
  const showDisc = !!SET().show_discontinued; $("#showdisc").checked = showDisc;
  $("#catlines").innerHTML = catalogData.filter((l) => !onlyOwned || l.owned).map((l) => {
    // discontinued colours: hidden unless switched on (or you still have a spool of them)
    const prods = l.products.filter((p) => (!onlyMissing || !p.owned) && (!p.discontinued || showDisc || p.owned));
    if (!prods.length) return "";
    return `<div class="catline"><h3>${esc(l.line)} <span class="sub">${T("colorsOf", l.owned, l.total)}${l.complete ? " · ✓ " + T("complete") : ""}</span></h3>
      <div class="bar"><i style="width:${(100 * l.owned / l.total).toFixed(0)}%"></i></div>
      <div class="colors">${prods.map((p) => `<div class="color ${p.owned ? "" : "missing"}${p.discontinued ? " disc" : ""}" data-cat="${p.id}" data-slot-ref="${esc(p.cabinet_slot ?? "")}">
        ${sw(p)}<span class="cname">${esc(cname(p))}<br><span class="sub">${esc(p.bambu_no ?? "")}</span>${p.discontinued ? `<br><span class="discmark" title="${esc(L("Bambu Lab no longer sells this color"))}">${L("no longer available")}</span>` : ""}</span>
        <span class="meta">${p.owned ? `<b>${esc(p.cabinet_slot ?? "")}</b><br>${T("spools", p.owned)}` : p.discontinued || isNoted(p.id) ? "" : T("missing")}${isNoted(p.id) ? `${p.owned ? "<br>" : ""}<span class="notedmark">${L("on the list")}</span>` : ""}</span></div>`).join("")}</div></div>`;
  }).join("");
}
$("#onlymissing").onchange = drawCatalog; $("#onlyowned").onchange = drawCatalog;
$("#showdisc").onchange = async () => { await saveSettings({ show_discontinued: $("#showdisc").checked }); drawCatalog(); };
// tapping a color: a small card with the spools you have and "Add to shopping list"
$("#catlines").addEventListener("click", async (e) => {
  const el = e.target.closest("[data-cat]");
  if (!el) return;
  const pid = +el.dataset.cat, p = catalogData.flatMap((l) => l.products).find((x) => x.id === pid);
  if (!p) return;
  const sps = spoolsOf(pid), noted = isNoted(pid);
  const where = (s) => s.ams_slot ? esc(amsWhere(s)) : `${esc(s.slot_id ?? "–")}${s.in_cabinet ? "" : " (" + L("reserve") + ")"}`;
  const body = `<div class="catpop"><div class="catpophead">${sw(p, "big")}<div><b>${esc(p.line)} ${esc(cname(p))}</b><br><span class="sub">${esc(p.bambu_no ?? "")}</span></div></div>
    ${sps.length ? `<ul class="shop">${sps.map((s) => `<li>${sw(s)}<span class="grow"><b>${where(s)}</b>${s.remain_pct != null ? ` · ${shownPct(s)} %` : ""}${s.is_refill ? " · " + T("refill") : ""}</span></li>`).join("")}</ul>`
      : `<p class="sub">${L(p.owned ? "In use or in the AMS." : "Not in your storage.")}</p>`}
    ${p.discontinued ? `<p class="sub discmark">${L("Bambu Lab no longer sells this color.")}</p>` : ""}
    ${noted ? `<p class="sub">${L("This color is already on your shopping list.")}</p>` : ""}
    <p class="sub">${L("Minimum stock")}: ${minStock(pid) ? esc(Lp(minStock(pid), "{0} spool", "{0} spools")) : L("none")}</p></div>`;
  const extra = [{ label: L("Minimum stock"), value: "min" }].concat(sps.length ? [{ label: L("Show in storage"), value: "show" }] : []);
  const r = await ask(body, { block: true, extra, cancel: L("Close"), ...(p.discontinued && !noted ? { ok: L("Close"), noCancel: true } : { ok: L(noted ? "Remove from shopping list" : "Add to shopping list") }) });
  if (r === true && p.discontinued && !noted) return;
  if (r === "show") { const sp = sps.find((s) => s.in_cabinet) || sps[0]; showView("storage"); showSpool(await api(`/api/spools/${sp.id}`)); }
  else if (r === "min") { await askMinStock(pid, `${p.line} ${cname(p)}`); drawCatalog(); }
  else if (r === true) setNoted(pid, !noted);
});

let reorgData = [];
async function loadReorg() {
  reorgData = await api("/api/reorg");
  $("#reorgcount").textContent = reorgData.length ? reorgData.length : "";
  document.querySelector('[data-view="reorg"]').hidden = !reorgData.length;
  if (view === "reorg") { if (reorgData.length) drawReorg(); else { showView("storage"); toast(T("reorgEmpty")); } }
}
function drawReorg() {
  $("#reorglist").innerHTML = reorgData.length ? reorgData.map((st, i) => `<li class="${st.ready ? "" : "wait"}">
    ${sw(st.spool)}<span>${title(st.spool)}<br><span class="sub">${esc(st.spool.bambu_no ?? "")}</span></span>
    <span class="path">${esc(st.from)} → ${esc(st.to ?? T("noRoom"))}</span>
    ${st.ready ? `<button class="primary" data-step="${i}">${T("done")}</button>` : ""}</li>`).join("")
    : `<li>${T("reorgEmpty")}</li>`;
}
$("#reorglist").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-step]");
  if (!b) return;
  const st = reorgData[Number(b.dataset.step)];
  try { await api(`/api/spools/${st.spool.id}/move`, { method: "POST", body: { slot_id: st.to } }); toast(T("movedTo", st.to)); }
  catch (err) { toast(err.message); }
});

// ------------------------------------------------------------ bulk inventory, reset
let batch = { active: false, items: [] };
function batchLabel(r) {
  const o = r.product || r.spool;
  return o ? `${sw(o)}<span>${title(o)} <span class="sub">${esc(o.bambu_no ?? "")}</span></span>` : `<span>${esc(r.tag?.detailed_type ?? "?")}</span>`;
}
function drawBatch() {
  const bar = $("#batchbar");
  bar.hidden = !batch.active;
  document.body.classList.toggle("batching", !!batch.active);
  $("#batchstart").disabled = batch.active;
  if (!batch.active) return;
  bar.innerHTML = `<span class="grow">${T("batchRunning", batch.items.length)}</span>
    <button id="bfinish" style="background:#fff;color:var(--accent);font-weight:600">${T("batchFinish")}</button>
    <button id="breserve" style="background:transparent;color:#fff;border-color:#fff8">${L("All to reserve")}</button>
    <button id="bcancel" style="background:transparent;color:#fff;border-color:#fff8">${T("batchCancel")}</button>`;
  $("#bfinish").onclick = () => finishBatch(false);
  $("#breserve").onclick = () => finishBatch(true);
  $("#bcancel").onclick = async () => { batch = await api("/api/batch/cancel", { method: "POST" }); drawBatch(); };
  const kind = { new: T("bNew"), linked: T("bLinked"), known: T("bKnown"), unmapped: T("bUnknown"), duplicate: T("bDuplicate") };
  const seen = new Set();
  const rows = batch.items.map((r) => {
    const pid = r.product?.id ?? r.spool?.product_id;
    const spare = r.kind === "new" && (seen.has(pid) || !r.proposal?.in_cabinet);
    if (pid) seen.add(pid);
    return `<li>${batchLabel(r)}<span class="tag badge">${spare ? T("bSpare") : kind[r.kind]}</span></li>`;
  });
  $("#batchresult").innerHTML = `<ul class="batchlist">${rows.reverse().join("")}</ul>`;
}
// new spools in the result list can be marked as refill right away (only corrects the entry, empty spools stay as they are)
const batchRefill = (sp) => `<label class="tgl" title="${esc(L("Refill: filament without its own spool"))}"><input type="checkbox" role="switch" data-brefill="${sp.id}" ${sp.is_refill ? "checked" : ""}><span class="tglui" aria-hidden="true"></span>${T("refill")}</label>`;
document.addEventListener("change", async (e) => {
  const id = e.target.dataset?.brefill; if (!id) return;
  const on = e.target.checked;
  document.querySelectorAll(`[data-brefill="${id}"]`).forEach((c) => (c.checked = on));   // the list and the popup show the same spool
  try { await api(`/api/spools/${id}`, { method: "PATCH", body: { is_refill: on ? 1 : 0 } }); refresh(); }
  catch (err) { toast(tr(err.message)); document.querySelectorAll(`[data-brefill="${id}"]`).forEach((c) => (c.checked = !on)); }
});
async function finishBatch(reserve) {
  let res;
  try { res = await api("/api/batch/finish", { method: "POST", body: { reserve: !!reserve } }); } catch (e) { toast(tr(e.message)); return; }
  batch = { active: false, items: [] }; drawBatch(); showView("tools");
  const lbl = { new: T("bNew"), linked: T("bLinked"), known: T("bKnown"), unknown: T("bUnknown"), duplicate: T("bDuplicate") };
  const list = `<ul class="batchlist">${res.map((x) => `<li><span class="where2">${esc(x.spool?.slot_id ?? "–")}</span>
      ${x.spool ? batchLabel({ spool: x.spool }) : batchLabel({ tag: x.tag })}<span class="tag badge">${lbl[x.action]}</span>${x.action === "new" && x.spool ? batchRefill(x.spool) : ""}</li>`).join("")}</ul>`;
  $("#batchresult").innerHTML = `<p><b>${T("batchDone", res.length)}</b> <button id="bprint">${T("bPrint")}</button></p>${list}`;
  $("#bprint").onclick = () => window.print();
  if (res.length) ask(`<p>${T("batchDone", res.length)}</p>${list}`,
    { block: true, noCancel: true, title: L("Where the spools go"), ok: L("Got it") });
}
$("#batchstart").onclick = async () => { batch = await api("/api/batch/start", { method: "POST" }); $("#batchresult").innerHTML = ""; drawBatch(); };
$("#resetword").addEventListener("input", (e) => ($("#resetbtn").disabled = e.target.value.trim() !== "RESET"));
$("#factorybtn").onclick = async () => {
  const ok = await ask(`<p><b>${esc(L("Everything is deleted: storage, history, statistics, settings, printer, Home Assistant, password and push."))}</b></p>
    <p>${esc(L("No backup is made. We recommend downloading a backup first under Options › Backup."))}</p>
    <p>${esc(L("Type RESET to confirm."))}</p>`, { block: true, warn: true, red: true, wait: 10, title: L("Reset PixxelSpool?"), ok: L("Delete everything"),
    input: { placeholder: "RESET" }, extra: [{ label: L("Back up first"), value: "backup" }] });
  if (ok === "backup") return openOpt("backuptool");
  if (ok == null) return;
  if (ok.trim().toUpperCase() !== "RESET") { toast(L("Please type {0} to confirm", "RESET")); return; }
  try {
    const r = await api("/api/factory-reset", { method: "POST", body: { confirm: "RESET" } });
    if (r.restart) { toast(L("PixxelSpool is restarting …")); setTimeout(() => location.reload(), 6000); }
    else ask(L("Restart PixxelSpool now to finish the reset."), { noCancel: true, title: L("Reset PixxelSpool?") });
  } catch (e) { toast(tr(e.message)); }
};
$("#resetbtn").onclick = async () => {
  try {
    const r = await api("/api/reset", { method: "POST", body: { confirm: $("#resetword").value.trim() } });
    $("#resetword").value = ""; $("#resetbtn").disabled = true; panel = null; render();
    toast(T("resetDone", r.removed, r.backup));
  } catch (e) { toast(e.message); }
};

setTimeout(() => document.body.classList.remove("booting"), 4000);   // never stay hidden (server unreachable)
// ------------------------------------------------------------ storage view
async function refresh() {
  overview = await api("/api/overview");
  if (SORT.on) sortReplay();   // planned sort changes stay visible while new data comes in
  applyLang(); fillSettings();
  drawJob();
  drawProject(); if (imgPts.length) drawImgPick(); if (tmf) drawTmf();
  api("/api/insights").then((i) => { insights = i; drawInsights(); drawProject(); }).catch(() => {});
  loadPrinter(); loadClimate(); drawClimWarn();
  if (haSensors === null && overview.ha?.status === "connected") loadSensors();
  setBell(overview.notices);
  drawStorage(); drawStats(); drawReturns(); drawToday(); drawAms(); setReader(overview.reader); setHa(overview.ha); drawLog(); loadReorg(); wizSync();
  if (view === "catalog") loadCatalog();
  if ($("#usedtool")?.classList.contains("open")) loadUsedUp();   // a spool put back leaves the used-up list right away
  let resume = null;
  try { resume = sessionStorage.getItem("wizStep"); sessionStorage.removeItem("wizStep"); } catch (e) {}
  if ((resume !== null || overview.settings?.setup_done === false) && !wiz.open) openWizard(+resume || 0);
  document.body.classList.remove("booting");   // shown only now, so a first start goes straight to the wizard
  if (!refresh.done) { refresh.done = true; openSlotHash(); loadUpdate(); if (!wiz.open) whatsNew(); }   // version and last update check for the status menu
  setTimeout(askNewAmsSpools, 1200);
  setTimeout(askRefillAms, 1600);
}
// after an update: show the changes once on every device (the first visit only remembers the version)
async function whatsNew() {
  const seen = pref("seenVersion", "");
  let r;
  try { r = await api(`/api/whatsnew?since=${encodeURIComponent(seen)}`); } catch (e) { return; }
  if (seen === r.version) return;
  setPref("seenVersion", r.version);
  if (!seen || !r.notes) return;
  ask(`<div class="upnotesbody whatsnew">${mdNotes(r.notes)}</div>`,
    { block: true, title: L("New in PixxelSpool {0}", r.version), ok: L("Got it"), noCancel: true });
}
// ------------------------------------------------------------ donations: one-time note after two hours of use, always in Options › About
const DONATE = window.PS_DONATE || {};
function donateBody(once) {
  const links = [DONATE.github && `<a class="btn primary" href="https://github.com/sponsors/${encodeURIComponent(DONATE.github)}" target="_blank" rel="noopener">${icon("heart")}${L("GitHub Sponsors")}</a>`,
    DONATE.kofi && `<a class="btn" href="https://ko-fi.com/${encodeURIComponent(DONATE.kofi)}" target="_blank" rel="noopener">${icon("cup")}Ko-fi</a>`].filter(Boolean);
  return `<div class="donate">
    <p>${L("PixxelSpool is free and stays free. I build it in my spare time as a hobby project.")}</p>
    <p>${L("If it makes your life with filament easier, I would be glad about a small donation. Every cent goes completely into the project, for these goals:")}</p>
    <ol class="goals">
      <li class="first"><b>${L("Apple developer license")}</b> <span class="goalnow">${L("first goal")}</span>
        <span class="sub">${L("99 € a year, so the Mac app opens without a security warning and apps for iPhone and iPad (iOS and iPadOS) become possible.")}</span></li>
      <li><b>${L("Bambu Lab A1 mini")}</b>
        <span class="sub">${L("About 200–250 €. A second printer with AMS lite, to test PixxelSpool on it and make it work well there.")}</span></li>
      <li><b>${L("A printer from another brand")}</b>
        <span class="sub">${L("About 300–400 €. To test PixxelSpool with a printer that is not from Bambu Lab and make it work there too.")}</span></li>
    </ol>
    ${links.length ? `<div class="links">${links.join("")}</div>` : ""}
    ${once ? `<p class="sub donatenote">${L("Thank you for using PixxelSpool! This note appears only once. You can find it any time under Options › About.")}</p>` : ""}
  </div>`;
}
const showDonate = (once = false) => ask(donateBody(once), { block: true, title: L("Support PixxelSpool"), noCancel: true, ok: once ? L("Not now") : L("Close") });
// counts minutes while the app is open and visible; stops for good once the note was shown (on any device)
const useTimer = setInterval(async () => {
  const st = overview?.settings;
  if (!st) return;
  if (st.donate_shown) return clearInterval(useTimer);
  let wizOpen = false; try { wizOpen = wiz.open; } catch (e) {}
  if (document.visibilityState !== "visible" || !st.setup_done || wizOpen || document.body.classList.contains("locked")) return;
  try {
    const r = await api("/api/usage", { method: "POST", body: { minutes: 1, ready: !document.querySelector(".dlgwrap") } });
    if (r.done) { st.donate_shown = true; clearInterval(useTimer); }
    if (r.show) showDonate(true);
  } catch (e) { /* offline: try again next minute */ }
}, 60000);
// scanned label: #slot=L-1-03 opens that slot
function openSlotHash() {
  const m = location.hash.match(/^#slot=(.+)$/);
  if (!m || !overview) return;
  const id = decodeURIComponent(m[1]), sl = overview.slots.find((x) => x.id === id);
  history.replaceState(null, "", location.pathname + location.search);
  if (!sl) return toast(L("Slot {0} doesn't exist", id));
  showView("storage");
  if (sl.spools.length) showSpool(sl.spools[0], null, sl.spools.length > 1 ? L("There are {1} spools on {0}.", esc(id), sl.spools.length) : "");
  else { highlight(id); toast(L("Slot {0} is free", id)); }
}
window.addEventListener("hashchange", openSlotHash);
let navInfoOpen = false;
// remaining filament: red at or below the "low" threshold from the options, amber up to twice that, else green
const remainCls = (p) => { const low = +(SET().low_remain_pct ?? 5) || 5; return p <= low ? "rbad" : p <= Math.max(20, low * 2) ? "rwarn" : "rok"; };
// "not set up" = nothing configured yet (switched off on purpose still counts as set up): show no status for it
const notSetUp = (x) => !x || (x.status === "off" && (!x.detail || /not set up/.test(x.detail)));
const hasPrinter = () => (overview?.printers || []).some((p) => !notSetUp(p));
function drawStats() {
  const s = overview.stats;
  // desktop: "Status" button with a popup (reader, HA, stock numbers); the dot shows whether everything runs
  const st = $("#stats"), rd = $("#reader"), ha = $("#ha");
  const bb = overview?.bambu || {};
  const pr = { className: bb.status === "connected" ? "ok" : bb.status === "error" ? "bad" : "",
    textContent: L(bb.status === "connected" ? "Printer connected locally" : bb.status === "error" ? "Printer: error" : "Printer off"),
    title: bb.status !== "connected" && bb.detail ? tr(bb.detail) : "" };
  const rs = remoteSt;   // remote access (Tailscale), only when installed
  const rm = !rs || !rs.installed ? null : rs.state === "Running"
    ? { className: "ok", textContent: L("Remote access on") + (rs.https ? " · HTTPS" : ""), title: rs.host || "" }
    : rs.state === "error" ? { className: "bad", textContent: L("Remote access: error"), title: rs.detail ? tr(rs.detail) : "" }
    : { className: "", textContent: L("Remote access off"), title: "" };
  const ok = rd.classList.contains("ok") && !ha.classList.contains("bad") && pr.className !== "bad";
  const bad = rd.classList.contains("bad") || ha.classList.contains("bad") || pr.className === "bad";
  // occupancy bar: green up to 70 %, amber up to 90 %, red above
  const pct = s.cabinet_slots ? Math.round(100 * s.cabinet_used / s.cabinet_slots) : 0;
  const lvl = pct >= 90 ? "bad" : pct >= 70 ? "warn" : "ok";
  const capBar = (cls = "") => `<span class="capbar ${lvl} ${cls}" title="${esc(L("{0} of {1} slots in use", s.cabinet_used, s.cabinet_slots))}"><i style="width:${Math.min(100, pct)}%"></i></span>`;
  const conn = (label, el, text) => { const c = (el.className || "").replace("pill", "").trim();
    return `<li class="conn"><i class="dot ${c}"></i><span class="grow">${esc(label)}</span><span class="sub" title="${esc(el.title || "")}">${esc(text ?? el.textContent.replace(/^HA\s*/, ""))}</span></li>`; };
  const onOff = (el) => L(el.className === "ok" ? "connected" : el.className === "bad" ? "Error" : "off");
  const nums = [[s.spools, L("Spools")], [s.overflow, L("reserve")], [s.in_ams || 0, L("in the AMS")], [SET().empty_spools ?? 0, L("empty spools")]];
  const body = `<div class="capsec"><div class="caprow"><b>${L("Storage")}</b><span class="sub">${L("{0} of {1} slots", s.cabinet_used, s.cabinet_slots)} · <b class="cap-${lvl}">${pct} %</b></span></div>${capBar("big")}
      <div class="capnums">${nums.map(([n, t]) => `<span><b>${n}</b><span class="sub">${esc(t)}</span></span>`).join("")}</div>
      ${s.unscanned ? `<p class="sub"><a href="#" class="statlink" data-unscanned>${esc(Lp(s.unscanned, "{0} spool not scanned yet", "{0} spools not scanned yet"))} ›</a></p>` : ""}</div>
    <ul class="conns">${hasPrinter() ? conn(L("Printer"), pr, onOff(pr)) : ""}${conn(L("NFC reader"), rd)}${notSetUp(overview.ha) ? "" : conn("Home Assistant", ha)}${rm ? conn(L("Remote access"), rm, L(rm.className === "ok" ? "on" : rm.className === "bad" ? "Error" : "off") + (rs.https && rm.className === "ok" ? " · HTTPS" : "")) : ""}</ul>${verRow()}`;
  const wasOpen = st.classList.contains("open");
  st.innerHTML = `<button class="statsfold" aria-expanded="${wasOpen}"><i class="dot ${bad ? "bad" : ok ? "ok" : ""}"></i>${L("Status")} <span class="chev">›</span></button>
    <div class="statsbody">${body}</div>`;
  st.querySelector(".statsfold").onclick = (e) => { e.stopPropagation(); $("#bell").classList.remove("open"); st.classList.toggle("open"); fitPop(st.querySelector(".statsbody")); };   // one menu at a time
  // burger menu: status at the top, collapsible (closed after every load)
  $("#navstatus").innerHTML = `<details ${navInfoOpen ? "open" : ""}><summary><b>${L("Status")}</b></summary>${body}</details>`;
  $("#navstatus details").ontoggle = (e) => (navInfoOpen = e.target.open);   // starts closed after every load
}
// status menu: running version, result of the last update check and a round arrow to check now
const RELOAD_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66"/><path d="M20 4v5h-5"/></svg>`;
let verChecking = false;
function verRow() {
  if (!updSt) return "";
  const c = updSt.check;
  const what = verChecking ? L("Checking for updates …") : !c ? "" : c.available ? `<a href="#" class="statlink" data-goupd>${esc(L("Update {0} available", c.latest))}</a>`
    : c.error ? L("Check not possible") : L("up to date");
  return `<div class="verrow"><span class="grow"><a class="verlink" translate="no" href="${esc(document.querySelector('a.btn[href^="https://github.com/"]')?.getAttribute("href") || "https://github.com")}" target="_blank" rel="noopener">PixxelSpool ${esc(updSt.current)}</a>${what ? ` · ${what}` : ""}</span>
    <button class="verchk${verChecking ? " spin" : ""}" data-vercheck title="${esc(L("Check for updates"))}" aria-label="${esc(L("Check for updates"))}">${RELOAD_SVG}</button></div>`;
}
// "n spools not scanned yet": one opens its card, several blink in the storage view
async function showUnscanned() {
  $("#stats").classList.remove("open"); closeNav();
  const list = overview.slots.flatMap((sl) => sl.spools.map((sp) => ({ sp, sl }))).filter(({ sp }) => !sp.tray_uid);
  if (!list.length) return;
  if (view !== "storage") showView("storage");
  if (list.length === 1) return showSpool(await api(`/api/spools/${list[0].sp.id}`));
  let unfold = false;      // folded cabinets / reserve shelves holding one of them open up
  list.forEach(({ sl }) => { const k = sl.kind === "overflow" ? "overflow" : sl.cabinet; if (cabClosed.delete(k)) unfold = true; });
  if (unfold) { setPref("cabClosed", JSON.stringify([...cabClosed])); drawStorage(); }
  const els = list.flatMap(({ sp }) => [...document.querySelectorAll(`#storage [data-spool="${sp.id}"]`)]).filter((el) => el.offsetParent);
  els[0]?.scrollIntoView({ behavior: "smooth", block: "center" });
  els.forEach((el) => { el.classList.remove("blink"); void el.offsetWidth; el.classList.add("blink"); });
  setTimeout(() => els.forEach((el) => el.classList.remove("blink")), 4200);
  toast(Lp(list.length, "{0} spool not scanned yet", "{0} spools not scanned yet"));
}
document.addEventListener("click", async (e) => {
  if (e.target.closest("[data-unscanned]")) { e.preventDefault(); e.stopPropagation(); return showUnscanned(); }
  if (e.target.closest("[data-goupd]")) { e.preventDefault(); $("#stats").classList.remove("open"); closeNav(); showView("tools"); openOpt("updatetool"); return; }
  if (!e.target.closest("[data-vercheck]") || verChecking) return;
  e.stopPropagation();
  verChecking = true; drawStats();
  const t0 = Date.now();
  try { updSt = await api("/api/update", { method: "POST", body: { action: "check" } }); }
  catch (err) { updSt = { ...updSt, check: { error: err.message } }; }
  await new Promise((r) => setTimeout(r, Math.max(0, 700 - (Date.now() - t0))));   // let the arrow turn at least once
  verChecking = false; drawStats(); drawUpdate(); drawOptSums();
}, true);
document.addEventListener("click", (e) => {
  if (!e.target.closest("#stats")) $("#stats").classList.remove("open");
  if (!e.target.closest("#bell")) $("#bell").classList.remove("open");
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { $("#stats").classList.remove("open"); $("#bell").classList.remove("open"); } });

// ------------------------------------------------------------ notifications (bell)
const bell = { unread: 0, last: null, items: [] };
const NICON = { ok: "✓", bad: "!", warn: "!", info: "i" };
function setBell(n) {
  if (!n) return;
  const first = bell.last === null;
  if (!first && n.last > bell.last && n.unread > bell.unread) { beep("note"); loadBell(true); }
  bell.unread = n.unread; bell.last = n.last;
  const b = $("#bell .badge");
  b.hidden = !n.unread; b.textContent = n.unread > 9 ? "9+" : n.unread;
  $("#bell").classList.toggle("has", !!n.unread);
  if ($("#bell").classList.contains("open")) loadBell();
}
function ago(ts) {
  const d = new Date(ts.replace(" ", "T")), m = Math.round((Date.now() - d) / 60000);
  if (m < 1) return L("just now");
  if (m < 60) return L("{0} min ago", m);
  if (m < 60 * 24) return L("{0} h ago", Math.round(m / 60));
  return d.toLocaleDateString(LOCALE, { day: "numeric", month: "short" }) + " " + fmtTime(d);
}
const ntext = (n) => L(n.title, ...(n.args || []).map((a) => (typeof a === "string" ? tr(a) : a)));
async function loadBell(toastNew = false) {
  try { const r = await api("/api/notices"); bell.items = r.items; } catch (e) { return; }
  if (toastNew && bell.items[0] && !bell.items[0].read) toast(ntext(bell.items[0]));
  drawBell();
}
const CALM = matchMedia("(prefers-reduced-motion: reduce)");
// slide a notification out to the side, then close the gap it leaves
function noteOut(li, delay = 0, dir = 1) {
  if (CALM.matches || !li.animate) { li.remove(); return Promise.resolve(); }
  const h = li.offsetHeight, x = `${dir * 110}%`;
  li.style.pointerEvents = "none";
  return li.animate([
    { transform: li.style.transform || "translateX(0)", opacity: 1, height: `${h}px` },
    { transform: `translateX(${x})`, opacity: 0, height: `${h}px`, offset: 0.55 },
    { transform: `translateX(${x})`, opacity: 0, height: "0px", paddingTop: "0px", paddingBottom: "0px", marginBottom: "0px" },
  ], { duration: 380, delay, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" }).finished.then(() => li.remove());
}
async function delNote(li, dir = 1) {
  const id = +li.dataset.nid;
  bell.items = bell.items.filter((n) => n.id !== id);
  const gone = noteOut(li, 0, dir);
  try { setBell(await api(`/api/notices/${id}`, { method: "DELETE" })); } catch (err) { toast(err.message); loadBell(); return; }
  await gone;
  if (!bell.items.length) drawBell();
}
function drawBell() {
  const body = $("#bell .bellbody");
  body.innerHTML = `<div class="bellhead"><b>${L("Notifications")}</b>${bell.items.length ? `<span class="sub bellcount">${bell.items.length}</span><button class="small" id="bellclear">${L("Clear all")}</button>` : ""}</div>` +
    (bell.items.length ? `<ul>${bell.items.map((n, i) => `<li class="${n.read ? "" : "new"} ${n.link ? "go" : ""} lvl-${esc(n.level)}" data-link="${esc(n.link)}" data-nid="${n.id}" style="--i:${Math.min(i, 8)}">
      <i class="nico ${esc(n.level)}">${NICON[n.level] || "i"}</i><span class="grow">${esc(ntext(n))}<span class="sub">${ago(n.ts)}</span></span>
      <button class="ndel" data-ndel="${n.id}" title="${esc(L("Delete"))}" aria-label="${esc(L("Delete"))}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button></li>`).join("")}</ul>`
      : `<div class="bellempty"><span class="bellok" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span><b>${L("All caught up")}</b>
         <p class="sub">${L("No notifications. Finished prints, printer errors, low filament, humid storage and spools running low show up here.")}</p></div>`);
  const c = $("#bellclear");
  if (c) c.onclick = async (e) => {
    e.stopPropagation(); c.disabled = true;
    const lis = [...body.querySelectorAll("li[data-nid]")];
    const gone = Promise.all(lis.map((li, i) => noteOut(li, Math.min(i, 10) * 45)));
    try { setBell(await api("/api/notices", { method: "DELETE" })); } catch (err) { toast(err.message); loadBell(); return; }
    await gone; bell.items = []; drawBell();
  };
  body.querySelectorAll("[data-ndel]").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); delNote(b.closest("li")); }));
  // phones: swipe a notification sideways to delete it
  body.querySelectorAll("li[data-nid]").forEach((li) => {
    let x0 = null, y0 = 0, dx = 0;
    li.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; dx = 0; li.style.transition = "none"; }, { passive: true });
    li.addEventListener("touchmove", (e) => {
      if (x0 === null) return;
      dx = e.touches[0].clientX - x0;
      if (Math.abs(e.touches[0].clientY - y0) > Math.abs(dx)) { x0 = null; li.style.transform = ""; return; }   // scrolling
      li.style.transform = `translateX(${dx}px)`; li.style.opacity = String(Math.max(0.3, 1 - Math.abs(dx) / 260));
    }, { passive: true });
    li.addEventListener("touchend", () => {
      if (x0 === null) return; x0 = null; li.style.transition = "";
      if (Math.abs(dx) > 90) { li.dataset.swiped = "1"; delNote(li, dx > 0 ? 1 : -1); }
      else { li.style.transform = ""; li.style.opacity = ""; }
    });
  });
  body.querySelectorAll("li[data-link]").forEach((li) => (li.onclick = async () => {
    if (li.dataset.swiped) return;
    const link = li.dataset.link || "", i = link.indexOf(":"), k = link.slice(0, i), v = link.slice(i + 1);
    if (!k) return;
    if (k === "url") { window.open(v, "_blank", "noopener"); return; }
    $("#bell").classList.remove("open");
    if (k === "spool") { showView("storage"); try { showSpool(await api(`/api/spools/${v}`)); } catch (e) { toast(e.message); } }
    if (k === "view") showView(v);
    if (k === "opt") openOpt(v);
  }));
}
// "Report a bug": the GitHub form with version, platform, browser and printer models filled in (no names or addresses)
document.addEventListener("click", async (e) => {
  const a = e.target.closest("a.bugbtn"); if (!a) return;
  e.preventDefault();
  const w = window.open("about:blank", "_blank");     // opened right away: Safari blocks windows opened after an await
  let d = {}; try { d = await api("/api/diag"); } catch (err) {}
  const plat = { pi: "Raspberry Pi", windows: "Windows app / Windows-App", mac: "Mac app / Mac-App" }[d.platform] || "Other / Andere";
  const ua = navigator.userAgent, br = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS X/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "";
  const dev = [`${br}${os ? " (" + os + ")" : ""}`, ...(d.printers || []).map((m) => "Bambu Lab " + m), d.reader ? "Reader: " + d.reader : ""].filter(Boolean).join(", ");
  const u = new URL(a.href);
  u.searchParams.set("version", d.version || "");
  u.searchParams.set("platform", plat);
  u.searchParams.set("device", dev);
  if (w) w.location = u.toString(); else location.href = u.toString();
});
// keep a dropdown inside the screen: it hangs from the right edge of its button, which is not always at the screen edge
function fitPop(el) {
  if (!el) return;
  el.style.right = "";
  const r = el.getBoundingClientRect(), pad = 12;
  if (!r.width) return;
  const vw = document.documentElement.clientWidth;
  let shift = 0;
  if (r.left < pad) shift = r.left - pad;                       // too far left: move right
  else if (r.right > vw - pad) shift = r.right - (vw - pad);    // too far right: move left
  if (shift) el.style.right = `${parseFloat(getComputedStyle(el).right) + shift}px`;
}
window.addEventListener("resize", () => { if ($("#bell").classList.contains("open")) fitPop($("#bell .bellbody")); });
$("#bell .bellbtn").onclick = async (e) => {
  e.stopPropagation();
  const el = $("#bell"), open = !el.classList.contains("open");
  el.classList.toggle("open", open);
  if (open) $("#stats").classList.remove("open");      // one menu at a time
  if (!open) return;
  const bb = el.querySelector(".bellbody");
  fitPop(bb); bb.classList.add("fresh"); clearTimeout(bb.freshT); bb.freshT = setTimeout(() => bb.classList.remove("fresh"), 700);
  await loadBell();
  fitPop(el.querySelector(".bellbody"));
  if (bell.unread) setTimeout(async () => { setBell(await api("/api/notices/read", { method: "POST", body: {} })); }, 1500);
};
function setHa(h) {
  const el = $("#ha"); if (!h) return;
  el.hidden = notSetUp(h);      // no Home Assistant set up: nothing to show in the header
  el.textContent = L(I18N.en.ha[h.status] || "HA");
  el.className = `pill ${{ connected: "ok", error: "bad" }[h.status] || ""}`; el.title = tr(h.detail || "");
  $("#haclim")?.classList.toggle("off", h.status !== "connected");   // the wizard shows the sensors only once HA is connected
  if (overview) drawStats();
}
let lastJobAlert = "";
// Filament check per printer job. In the storage view it is only shown when no printer card shows it
// (the card has a compact version); the print view always shows it.
function drawJob() {
  const jobs = (overview?.jobs || []).filter((j) => j.rows?.length), el = $("#jobnote"), jp = $("#jobprint");
  if (!jobs.length && !hasPrinter()) {      // no printer set up: the filament check has nothing to show
    jp.hidden = el.hidden = true; jp.innerHTML = ""; lastJobAlert = ""; return;
  }
  jp.hidden = false;
  const running = !jobs.length && (overview?.printers || []).find((p) => PACTIVE.includes(p.state));
  if (running) {     // a print runs, but the amounts from its print file are missing (file not readable on the printer)
    jp.innerHTML = `<h3>${esc(L("Print running: {0}", running.name || L("Print job")))}</h3><p class="sub">${L("PixxelSpool could not read the filament amounts of this print from the printer, so it can't check whether the filament in the AMS is enough.")}</p>`;
    jp.classList.remove("warn"); el.hidden = true; lastJobAlert = ""; return;
  }
  if (!jobs.length) {
    jp.innerHTML = `<h3>${L("No print job")}</h3><p class="sub">${L("As soon as a print is running, you'll see here whether the filament in the AMS is enough.")}</p>`;
    jp.classList.remove("warn"); el.hidden = true; lastJobAlert = ""; return;
  }
  const ST = { ok: ["✓", L("enough")], tight: ["⚠︎", L("tight")], short: ["✕", L("not enough")], unknown: ["?", L("remaining unknown")] };
  const isBad = (r) => r.state === "tight" || r.state === "short";
  // only show while printing, or afterwards if something was short
  const shown = jobs.filter((j) => j.active || j.rows.some(isBad));
  if (!shown.length) { el.hidden = true; jp.classList.remove("warn"); jp.innerHTML = `<h3>${L("No print right now")}</h3><p class="sub">${L("There was enough filament for the last print.")}</p>`; lastJobAlert = ""; return; }
  const block = (j) => {
    const rest = j.remaining_min != null && j.active ? " · " + L("{0} left", fmtMin(j.remaining_min)) : "";
    const layer = j.active && j.layers ? " · " + L("Layer {0}/{1}", Math.round(j.layer || 0), Math.round(j.layers)) : "";
    const who = j.printer_name ? `${esc(j.printer_name)}: ` : "";
    const head = who + (j.active ? `${j.name ? esc(j.name) : L("Print running")}${j.progress != null ? ` · ${Math.round(j.progress)} %` : ""}${rest}${layer}` : L("Last print"));
    return `<div class="jobblock"><b>${head}</b><div class="sub">${L("Filament-Check")}</div><ul class="shop">${j.rows.map((r) => {
      const sp = r.spool;
      const what = sp ? title(sp) : esc(r.label || "?");
      const spare = r.spare ? `<br><span class="sub">${L("Spare:")} <b>${esc(r.spare.slot_id ?? "–")}</b>${r.spare.in_cabinet ? "" : " (" + L("reserve") + ")"}</span>`
        : isBad(r) && sp ? `<br><span class="sub">${L("No spare spool in storage")}</span>` : "";
      return `<li class="job-${r.state}" ${r.spare ? `data-spool="${r.spare.id}"` : ""}><span class="jobst">${ST[r.state][0]}</span>
        <span class="grow"><b>${esc(tr(r.slot))}</b> · ${what}<br><span class="sub">${L("needs {0} g", Math.round(r.need_g))}${r.have_g != null ? " · " + L("approx. {0} g left", r.have_g) : ""} · ${ST[r.state][1]}</span>${spare}</span></li>`;
    }).join("")}</ul></div>`;
  };
  const warn = shown.some((j) => j.rows.some(isBad));
  // with a direct printer connection the check is shown compactly in the printer card
  el.hidden = !!printersShown().length;
  el.classList.toggle("warn", warn);
  el.innerHTML = jp.innerHTML = shown.map(block).join("");
  jp.classList.toggle("warn", warn);
  [el, jp].forEach((c) => c.querySelectorAll("li[data-spool]").forEach((li) => (li.onclick = async () => showSpool(await api(`/api/spools/${li.dataset.spool}`)))));
  const sig = shown.filter((j) => j.active).flatMap((j) => j.rows.filter(isBad).map((r) => j.printer + r.slot + r.state)).join();
  if (sig && sig !== lastJobAlert) { beep("note"); toast(L("Filament is running low – see Storage")); }
  lastJobAlert = sig;
}
// "in AMS: AMS 1 · Slot 2", but just "External spool" for the external holder
const amsBadge = (sp) => /^AMS /.test(sp.ams_slot || "") ? T("inAms", amsWhere(sp)) : amsWhere(sp);
function amsWhere(sp) {
  if (!sp?.ams_slot) return "";
  const ps = overview?.printers || [], p = ps.length > 1 && ps.find((x) => x.id === sp.printer_id);
  return p ? `${p.name} · ${tr(sp.ams_slot)}` : tr(sp.ams_slot);
}
// external holder without a tag: the printer only reports the selected profile, not a real spool
const isExt = (t) => !/^AMS /.test(t.name);
// a spool assigned by hand is there; an AMS slot the AMS reports as occupied (no material set) is not empty
const isEmptyTray = (t) => !t.tray_uuid && !t.spool && (isExt(t) || (t.occupied !== true && (t.state === "Empty" || t.type === "Empty" || !t.type)));
// external spools belong to the printer: shown in its card when that printer has one
const extInCard = (t) => isExt(t) && printersShown().some((p) => p.id === t.printer && p.connected);
// one AMS or external-holder row (AMS card and printer card)
function amsItem(t) {
  const empty = isEmptyTray(t);
  const col = t.color && !/^#?0{6}00$/i.test(t.color) ? t.color.slice(0, 7) : null;
  const sp = t.spool, pct = !empty && typeof t.remain === "number" && t.remain >= 0 ? t.remain
    : sp?.ams_bound && sp.remain_pct != null ? shownPct(sp) : null;   // assigned by hand: PixxelSpool counts along
  const what = empty ? (isExt(t) ? T("extUnused") : T("amsEmpty"))
    : sp ? `${title(sp)}<div class="sub">${sp.ams_bound ? `<span class="beta" title="${esc(L("Experimental"))}">β</span>${esc(L("assigned by hand"))}` : esc(sp.bambu_no ?? "")} · ${T("amsHome")} ${esc(sp.slot_id ?? "–")}</div>`
    : t.match ? `${esc(t.match.line)} ${esc(cname(t.match))}<div class="sub">${esc(L("New spool, not in storage yet"))}</div>`
    : `${esc(t.state || t.type || "?")}<div class="sub">${t.tray_uuid ? T("amsUnknown") : T("amsNoTag")}</div>`;
  return `<li class="${empty ? "empty" : ""} ${t.active ? "active" : ""}" ${sp ? `data-spool="${sp.id}"` : ""}>
    <span class="slotname">${esc(tr(t.name))}</span>${empty ? "" : sp ? sw(sp) : sw(col)}
    <span class="what">${what}${pct != null ? `<div class="bar ${remainCls(pct)}"><i style="width:${pct}%"></i></div>` : ""}</span>
    ${pct != null ? `<span class="pct">${pct} %</span>` : ""}
    ${sp && pct === 0 ? `<i class="lbreak"></i><button class="danger small" data-emptyspool="${sp.id}">${L("Empty – remove?")}</button>` : ""}
    ${!sp && t.tray_uuid ? `<i class="lbreak"></i><button class="primary small" data-adopt="${esc(t.entity)}" data-printer="${esc(t.printer || "")}">${L("Add to storage")}</button>` : ""}
    ${!sp && t.assignable ? `<i class="lbreak"></i><button class="small" data-assign="${esc(t.entity)}" data-printer="${esc(t.printer || "")}" title="${esc(L("Experimental: tell PixxelSpool which of your spools this is"))}"><span class="beta">β</span>${L("Assign spool")}</button>` : ""}</li>`;
}
function drawAms() {
  const list = (overview.ams || []).filter((t) => !extInCard(t)), el = $("#ams");
  el.hidden = !list.length;
  if (!list.length) return;
  const isEmpty = isEmptyTray, item = amsItem;
  const loaded = list.filter((t) => !isEmpty(t)).length;
  // several printers: a heading per printer
  const groups = [...new Set(list.map((t) => t.printer))];
  const byPrinter = (fn) => groups.length > 1
    ? groups.map((g) => { const ts = list.filter((t) => t.printer === g); const r = fn(ts); return r ? `<li class="amsprinter">${esc(ts[0].printer_name || "")}</li>${r}` : ""; }).join("")
    : fn(list);
  const ams = list.filter((t) => !isExt(t)), ext = list.filter(isExt);
  const extUsed = ext.some((t) => !isEmpty(t));
  el.classList.toggle("open", amsOpen || view === "printerview");
  const hu = ams.find((t) => t.humidity != null);
  // humidity colored by what the loaded material needs: nylon/PC/TPU/PVA 20 %, PETG/ABS/ASA 30 %, PLA and others 40 %
  const need = (t) => { const m = `${t.type || ""} ${t.spool?.line || ""}`.toUpperCase();
    return /\b(PA|PAHT|PA6|PA12|PC|TPU|PVA|PPA)/.test(m) ? 20 : /\b(PETG|PET|ABS|ASA|HIPS)/.test(m) ? 30 : 40; };
  const limit = SET().ams_hum_max > 0 ? SET().ams_hum_max : Math.min(40, ...ams.filter((t) => !isEmpty(t)).map(need));   // own limit from the options wins
  const hcls = (h) => h <= limit ? "hum-ok" : h <= limit + 10 ? "hum-warn" : "hum-bad";
  const humid = hu ? ` · <span class="${hcls(hu.humidity)}" title="${esc(L("Target for the loaded material: at most {0} %", limit))}">${L("{0} % humidity", Math.round(hu.humidity))}</span>${hu.ams_temp != null ? `, ${Math.round(hu.ams_temp)} °C` : ""}` : "";
  el.innerHTML = `<h3 class="fold" id="amsfold">${T("amsTitle")} <span class="sub foldsum">${T("amsSummary", loaded)}${humid}</span><span class="chev">›</span></h3><ul>` +
    byPrinter((ts) => ts.filter((t) => !isExt(t)).map(item).join("")) +
    (ext.length ? `<li class="extrow"><details class="extfold" ${extUsed ? "open" : ""}><summary>${T("extTitle", ext.length)}</summary><ul>${byPrinter((ts) => ts.filter(isExt).map(item).join(""))}</ul></details></li>` : "") +
    `</ul>`;
  $("#amsfold").onclick = () => { amsOpen = !amsOpen; setPref("amsOpen", amsOpen ? "1" : "0"); el.classList.toggle("open", amsOpen); };
}
// buttons in AMS rows, also inside the printer card (capture: before the row's own click opens the spool)
document.addEventListener("click", async (e) => {
  const em = e.target.closest("[data-emptyspool]"), ad = e.target.closest("[data-adopt]"), as = e.target.closest("[data-assign]");
  if (as) {
    e.stopPropagation(); as.disabled = true;
    const t = (overview?.ams || []).find((x) => x.entity === as.dataset.assign && (!as.dataset.printer || x.printer === as.dataset.printer));
    if (!(await assignTray(t || { entity: as.dataset.assign, printer: as.dataset.printer }))) as.disabled = false;
  } else if (em) {
    e.stopPropagation();
    const sp = (overview?.ams || []).find((t) => t.spool && String(t.spool.id) === em.dataset.emptyspool)?.spool;
    if (sp) spoolAction(sp, "empty", true);      // no question: the message offers "Undo"
  } else if (ad) {
    e.stopPropagation(); ad.disabled = true;
    const t = (overview?.ams || []).find((x) => x.entity === ad.dataset.adopt && (!ad.dataset.printer || x.printer === ad.dataset.printer));
    if (!(await adoptTray(t || { entity: ad.dataset.adopt, printer: ad.dataset.printer }))) ad.disabled = false;
  }
}, true);
// take over a Bambu spool the AMS has read: links an unscanned spool of that color or adds a new one;
// a color the catalog doesn't know is chosen from a list. Resolves true when done.
async function adoptTray(t, productId = null) {
  if (!productId && t.tray_uuid && t.match === null) return pickAmsColor(t);   // color not in the catalog: choose it
  try {
    const sp = await api("/api/ams/adopt", { method: "POST", body: { entity: t.entity, printer: t.printer || "", product_id: productId } });
    amsAsked.add(t.tray_uuid);
    await refresh();
    showSpool(sp, null, sp.linked
      ? L("Linked with your spool on slot <b>{0}</b>. From now on PixxelSpool recognizes it in the AMS.", esc(sp.slot_id ?? "–"))
      : L("Added to storage. Its slot: <b>{0}</b>. It stays free while the spool is in the AMS; when you take the spool out, put it there.", esc(sp.slot_id ?? "–")));
    beep(true); return true;
  } catch (err) {
    toast(tr(err.message)); beep(false); return false;
  }
}
// experimental: a spool without a Bambu tag sits in the AMS. The user picks which stored spool it is; from then on
// it counts as in the AMS (until the slot is empty) and finished prints use it up. Resolves true when done.
async function assignTray(t) {
  let r;
  try { r = await api(`/api/ams/assign?entity=${encodeURIComponent(t.entity)}&printer=${encodeURIComponent(t.printer || "")}`); }
  catch (err) { toast(tr(err.message)); return false; }
  const list = r.spools || [], col = (t.color || "").slice(0, 7);
  if (!list.length) { toast(L("No spool in storage to choose from. Add the spool first.")); return false; }
  const pct = (c) => c.remain_pct != null ? ` · ${Math.round(c.remain_pct)} %` : "";
  const opt = (c) => `<option value="${c.id}">${esc(c.line)} · ${esc(cname(c))} · ${esc(c.slot_id ?? "–")}${pct(c)}${c.status === "in_use" ? " · " + esc(L("taken out")) : ""}</option>`;
  const same = list.filter((c) => c.same && !c.chip), other = list.filter((c) => !c.same && !c.chip), chip = list.filter((c) => c.chip);
  const grp = (label, xs) => xs.length ? `<optgroup label="${esc(label)}">${xs.map(opt).join("")}</optgroup>` : "";
  const html = `<p><span class="amscol" style="background:${esc(col)}"></span>${L("In <b>{0}</b> is a spool without a Bambu tag ({1}). Which of your spools is it?", esc(tr(t.name)), esc(t.type || "?"))}</p>
    <div class="field"><select id="assignpick">${grp(L("Same material"), same)}${grp(T("allOthers"), other)}${grp(L("With Bambu tag"), chip)}</select></div>
    <p class="sub">${esc(L("PixxelSpool then counts it as in the AMS until the slot is empty, and subtracts what finished prints use. Its storage slot stays free for it."))}</p>
    ${isExt(t) ? `<p class="sub">${esc(L("The printer can't tell when a spool is taken off the external holder. When you change it, put it back in PixxelSpool."))}</p>` : ""}
    <p class="sub expnote">${esc(L("Experimental: the AMS can't measure spools without a tag, so the remaining amount is an estimate from the print files. Weigh the spool now and then."))}</p>`;
  const ok = await ask(html, { block: true, html: true, title: L("Assign spool"), ok: L("Assign") });
  const sel = document.getElementById("assignpick");
  if (!ok || !sel) return false;
  try {
    const sp = await api("/api/ams/assign", { method: "POST", body: { entity: t.entity, printer: t.printer || "", spool_id: Number(sel.value) } });
    await refresh();
    showSpool(sp, null, L("Assigned to <b>{0}</b>. When the slot is empty again, PixxelSpool reminds you to put it back on <b>{1}</b>.", esc(tr(t.name)), esc(sp.slot_id ?? "–")));
    beep(true); return true;
  } catch (err) { toast(tr(err.message)); beep(false); return false; }
}
async function pickAmsColor(t) {
  let r;
  try { r = await api(`/api/ams/candidates?entity=${encodeURIComponent(t.entity)}&printer=${encodeURIComponent(t.printer || "")}`); }
  catch (err) { toast(tr(err.message)); return false; }
  const col = (t.color || "").slice(0, 7), list = r.candidates || [];
  if (!list.length) { toast(L("No colors in the catalog yet")); return false; }
  const opt = (c) => `<option value="${c.id}">${esc(c.line)} · ${esc(c.bambu_no ?? "–")} · ${esc(cname(c))}</option>`;
  const same = list.filter((c) => c.same), other = list.filter((c) => !c.same);
  const html = `<p><span class="amscol" style="background:${esc(col)}"></span>${esc(L("PixxelSpool doesn't know this color ({0}, {1}) yet. Which one is it?", t.label || t.type || "?", col))}</p>
    <div class="field"><select id="amspick">${same.length ? `<optgroup label="${esc(L("Similar colors"))}">${same.map(opt).join("")}</optgroup>` : ""}
    ${other.length ? `<optgroup label="${esc(T("allOthers"))}">${other.map(opt).join("")}</optgroup>` : ""}</select></div>`;
  const pickP = ask(html, { block: true, title: L("Choose color"), ok: L("Add to storage") });
  const ok = await pickP, sel = document.getElementById("amspick");
  if (!ok || !sel) return false;
  return adoptTray(t, Number(sel.value));
}
// dialog "new spool detected" once per Bambu tag the AMS reports and storage doesn't know yet
const amsAsked = new Set();
let amsAsking = false;
async function askNewAmsSpools() {
  if (amsAsking || document.body.classList.contains("wizopen") || document.body.classList.contains("locked")) return;
  if (document.querySelector(".dlgwrap, .wnwrap")) { setTimeout(askNewAmsSpools, 3000); return; }   // another dialog first
  let wizOpen = false; try { wizOpen = wiz.open; } catch (e) {}
  if (wizOpen || overview?.settings?.setup_done === false) return;
  let skipped = [];
  try { skipped = JSON.parse(sessionStorage.getItem("amsSkipped") || "[]"); } catch (e) {}
  const t = (overview?.ams || []).find((x) => x.tray_uuid && !x.spool && !amsAsked.has(x.tray_uuid) && !skipped.includes(x.tray_uuid));
  if (!t) return;
  amsAsking = true; amsAsked.add(t.tray_uuid);
  try {
    const m = t.match, slot = esc(tr(t.name)), col = (t.color || "").slice(0, 7);
    const what = m ? `<b>${esc(m.line)} ${esc(cname(m))}</b>` : `<b>${esc(t.label || t.type || "?")}</b> (${esc(col)})`;
    const text = `<p>${L("The AMS has read a Bambu Lab spool in <b>{0}</b>: {1}.", slot, what)}</p>
      <p class="sub">${m?.has_seed ? L("You already have an unscanned spool of this color on slot <b>{0}</b>. PixxelSpool links the two, nothing is added twice.", esc(m.seed_slot ?? "–"))
        : L("PixxelSpool adds it to storage and gives it a slot. When you take it out of the AMS, PixxelSpool tells you where it goes.")}</p>`;
    const ok = await ask(text, { block: true, title: L("New spool detected"), ok: m?.has_seed ? L("Link") : L("Add to storage"), cancel: L("Not now") });
    if (ok) await adoptTray(t);
    else { skipped.push(t.tray_uuid); try { sessionStorage.setItem("amsSkipped", JSON.stringify(skipped)); } catch (e) {} }
  } finally { amsAsking = false; }
  setTimeout(askNewAmsSpools, 400);   // several new spools: one after the other
}
// a refill turned up in the AMS: it sits on a spool now. Ask once whether that spool came from the stock of empty spools.
let refillAsking = false;
async function askRefillAms() {
  if (refillAsking || amsAsking || document.body.classList.contains("wizopen") || document.body.classList.contains("locked")) return;
  if (document.querySelector(".dlgwrap, .wnwrap")) { setTimeout(askRefillAms, 3000); return; }
  // any refill in the AMS (also one marked as refill while it was already there) is asked about once
  const sp = allSpools().find((x) => (x.refill_ask || x.is_refill) && x.ams_slot);
  if (!sp) return;
  refillAsking = true;
  try {
    const c = +(SET().empty_spools ?? 0);
    const used = await ask(`<p>${L("The refill {0} is now in <b>{1}</b>.", `<b>${esc(sp.line)} ${esc(cname(sp))}</b>`, esc(amsWhere(sp)))}</p>
      <p>${L("Did you put it onto an empty spool from your stock?")}</p>` +
      (c ? `<span class="dlgnote">${esc(L("Empty spools for refills: {0} → {1}", c, c - 1))}</span>` : ""),
      { html: true, block: true, title: L("Refill detected in the AMS"), ok: L("Yes, an empty spool"), cancel: L("No") });
    await api(`/api/spools/${sp.id}/refill-on-spool`, { method: "POST", body: { used_empty_spool: !!used && c > 0 } });
    await refresh();
  } catch (e) { toast(e.message); } finally { refillAsking = false; }
}
// beta.2: "Today" bar on top of the storage: what needs doing, each chip leads there
function drawToday() {
  const el = $("#today"); if (!el || !overview) return;
  const ret = overview.slots.flatMap((sl) => sl.spools).filter((sp) => sp.needs_return).length;
  const sh = insights?.shopping, low = sh ? sh.low.length + (sh.below_min || []).length : 0;
  const list = sh ? (sh.noted || []).length + (sh.below_min || []).length : 0, dry = insights?.drying?.length || 0;
  const chips = [
    ret && ["returns", "undo", Lp(ret, "{0} spool to put back", "{0} spools to put back")],
    low && ["shop", "low", Lp(low, "{0} color almost used up", "{0} colors almost used up")],
    dry && ["dry", "dry", Lp(dry, "{0} spool to dry", "{0} spools to dry")],
    list && ["shop", "cart", Lp(list, "{0} item on the shopping list", "{0} items on the shopping list")],
  ].filter(Boolean);
  el.hidden = !chips.length;
  el.innerHTML = chips.length ? `<b>${L("Today")}</b>` + chips.map(([go, ic, t]) => `<button class="tchip t-${ic}" data-today="${go}">${t}</button>`).join("") : "";
}
$("#today").addEventListener("click", (e) => {
  const b = e.target.closest("[data-today]"); if (!b) return;
  const go = b.dataset.today;
  if (go === "returns") $("#returns").scrollIntoView({ behavior: "smooth", block: "center" });
  if (go === "dry") { dryOpen = true; drawInsights(); $("#drynote").scrollIntoView({ behavior: "smooth", block: "center" }); }
  if (go === "shop") { shopOpen = true; setPref("shopFold", "1"); showView("catalog"); drawInsights(); setTimeout(() => $("#shopping").scrollIntoView({ behavior: "smooth", block: "start" }), 200); }
});
function drawReturns() {
  const list = overview.slots.flatMap((sl) => sl.spools).filter((sp) => sp.needs_return);
  const el = $("#returns"); el.hidden = !list.length;
  el.innerHTML = `<b>${T("returnsTitle", list.length)}</b> ` + list.map((sp) =>
    `<span class="chip" data-spool="${sp.id}">${sw(sp)}${title(sp)} → <b>${esc(sp.slot_id ?? "–")}</b></span>`).join("");
}
function matTag(line) {
  return line ? `<span class="mat">${esc(line)}</span>` : "";
}
// beta.2: on a computer (mouse) spools can be sorted by dragging, but only after "Sort" is switched on. Moves (free slot)
// and swaps (taken slot) are only planned and shown; nothing changes until "Apply" (#23: too easy to move by accident)
const DRAG = matchMedia("(hover: hover) and (pointer: fine)");
const SORT = { on: false, ops: [] };
let dragId = null;
function sortApplyOp(op) {   // planned change on the local copy of the slots (also replayed after every refresh)
  const sl = overview.slots, from = sl.find((x) => x.spools.some((s) => s.id === op.id)), to = sl.find((x) => x.id === op.slot);
  if (!from || !to || from === to) return;
  const sp = from.spools.find((s) => s.id === op.id);
  if (op.kind === "swap") {
    const ot = to.spools.find((s) => s.id === op.other); if (!ot) return;
    from.spools = from.spools.map((s) => (s === sp ? ot : s)); to.spools = to.spools.map((s) => (s === ot ? sp : s));
    ot.slot_id = from.id;
  } else {
    from.spools = from.spools.filter((s) => s !== sp); to.spools = [...to.spools, sp];
  }
  sp.slot_id = to.id;
}
const sortReplay = () => SORT.ops.forEach(sortApplyOp);
const sortTouched = () => new Set(SORT.ops.flatMap((o) => [o.slot, o.from]));
function drawSortBar() {
  document.body.classList.toggle("sorting", SORT.on);
  $("#sortmode")?.classList.toggle("on", SORT.on);
  const bar = $("#sortbar"); if (!bar) return;
  bar.hidden = !SORT.on;
  const n = SORT.ops.length;
  bar.innerHTML = SORT.on ? `<span class="grow">${n ? esc(Lp(n, "{0} change planned", "{0} changes planned")) : esc(L("Drag a spool onto a free slot to move it, or onto another spool to swap."))}</span>
    <button class="small" data-sortx>${n ? L("Discard") : L("Done")}</button>${n ? `<button class="small primary" data-sortok>${esc(Lp(n, "Apply {0} change", "Apply {0} changes"))}</button>` : ""}` : "";
}
async function sortEnd(apply) {
  const ops = SORT.ops; SORT.on = false; SORT.ops = [];
  if (apply) {
    for (const op of ops) {
      try {
        if (op.kind === "swap") await api(`/api/spools/${op.id}/swapwith`, { method: "POST", body: { other: op.other } });
        else await api(`/api/spools/${op.id}/move`, { method: "POST", body: { slot_id: op.slot, manual: true } });
      } catch (err) { toast(tr(err.message)); break; }
    }
    toast(Lp(ops.length, "{0} change applied", "{0} changes applied"));
  }
  drawSortBar(); await refresh();
}
document.addEventListener("click", (e) => {
  if (e.target.closest("#sortmode")) {
    if (SORT.on) { sortEnd(false); return; }
    SORT.on = true; SORT.ops = []; drawSortBar(); drawStorage(); return;
  }
  if (e.target.closest("[data-sortx]")) sortEnd(false);
  if (e.target.closest("[data-sortok]")) sortEnd(true);
});
document.addEventListener("dragstart", (e) => {
  const el = e.target.closest?.(".slot[data-spool][draggable]"); if (!el || !SORT.on) return;
  dragId = +el.dataset.spool; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", String(dragId));
  el.classList.add("dragging"); document.body.classList.add("dnd");
});
document.addEventListener("dragend", () => { dragId = null; document.body.classList.remove("dnd");
  document.querySelectorAll(".slot.dragging, .slot.dropok").forEach((x) => x.classList.remove("dragging", "dropok")); });
document.addEventListener("dragover", (e) => {
  if (dragId == null) return;
  const t = e.target.closest?.(".slot[data-slot]"); document.querySelectorAll(".slot.dropok").forEach((x) => x !== t && x.classList.remove("dropok"));
  if (!t || +t.dataset.spool === dragId) return;
  e.preventDefault(); e.dataTransfer.dropEffect = "move"; t.classList.add("dropok");
});
document.addEventListener("drop", (e) => {
  const t = e.target.closest?.(".slot[data-slot]"); if (dragId == null || !t || !SORT.on) return;
  e.preventDefault();
  const id = dragId, other = t.dataset.spool ? +t.dataset.spool : null, slot = t.dataset.slot;
  if (other === id) return;
  const from = overview.slots.find((x) => x.spools.some((s) => s.id === id))?.id;
  const op = { kind: other ? "swap" : "move", id, other, slot, from };
  SORT.ops.push(op); sortApplyOp(op); drawStorage(); drawSortBar();
});
function slotHtml(sl) {
  const sp = sl.spools[0];
  if (!sp) return `<div class="slot free${SORT.on && sortTouched().has(sl.id) ? " sorted" : ""}" data-slot="${sl.id}"><span class="id">${sl.id}</span><span class="nm"></span></div>`;
  const cls = ["slot", SORT.on && sortTouched().has(sl.id) ? "sorted" : "", sp.status === "in_use" ? "inuse" : "", sp.tray_uid ? "" : "unscanned",
sp.ams_slot ? "ams" : "", sp.needs_return ? "toreturn" : "", sp.is_refill ? "refill" : ""].join(" ");
  const style = sp.hex ? `${swBg(sp)};color:${textOn(sp.hex)}` : "";
  // a spool on the external holder is marked "Ext." instead of "AMS"
  return `<div class="${cls}" style="${style}" data-slot="${sl.id}" data-spool="${sp.id}"${SORT.on && DRAG.matches ? ' draggable="true"' : ""}${sp.ams_slot ? ` data-ams="${/^AMS /.test(sp.ams_slot) ? "AMS" : esc(L("Ext."))}"` : ""}
    title="${title(sp)} (${sp.bambu_no ?? "–"}) · ${STATUS[sp.status]}${sp.ams_slot ? " · " + esc(amsBadge(sp)) : ""}${sp.needs_return ? " · " + T("toReturn") : ""}${sp.is_refill ? " · " + L("Refill (no spool)") : ""}">
    ${sp.is_refill ? `<span class="hatch"></span>` : ""}<span class="id">${sl.id}</span><span class="no">${esc(sp.bambu_no ?? "")}</span>
    ${matTag(sp.line)}<span class="nm">${esc(cname(sp))}</span></div>`;
}
// collapsed cabinets (and the shelf with the spare spools), remembered per device
let cabClosed; try { cabClosed = new Set(JSON.parse(pref("cabClosed", "[]"))); } catch (e) { cabClosed = new Set(); }
const cabCount = (key) => overview.slots.filter((s) => s.kind === "cabinet" && s.cabinet === key).reduce((n, s) => n + s.spools.length, 0);
const foldBits = (key, n) => `<span class="foldn">${cabClosed.has(key) ? esc(Lp(n, "{0} spool", "{0} spools")) : ""}</span><span class="chev">›</span>`;
const NARROW_STORAGE = matchMedia("(max-width: 700px)");
const detailWide = () => /iPhone|iPod/.test(navigator.userAgent) || /Android.*Mobile/.test(navigator.userAgent);
NARROW_STORAGE.addEventListener?.("change", () => overview && drawStorage());
function drawStorage() {
  document.body.classList.toggle("cabdetail", cabMode === "detail");
  // wide screens have no compact/detail difference: there the switch is just cabinet view / list
  // phones in landscape (iPhone Duo unfolded) also get compact/detail: wide cabinets have small tiles there too
  const narrow = NARROW_STORAGE.matches || detailWide(), shown = !narrow && cabMode === "detail" ? "compact" : cabMode;
  document.body.classList.toggle("detailable", narrow && !NARROW_STORAGE.matches);
  // the phone option in Options › Darstellung always shows the real compact/detail choice, also on a wide screen
  const grid = cabMode === "list" ? pref("cabGrid", "compact") : cabMode;
  document.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("on", b.dataset.mode === (b.closest("#viewtool") ? grid : shown)));
  document.querySelectorAll('[data-mode="compact"]').forEach((cb) => { if (!cb.closest("#viewtool")) cb.textContent = narrow ? T("viewCompact") : L("Grid"); });
  const asList = cabMode === "list" && !pick;          // choosing a slot needs the cabinet grid
  $("#spoollist").hidden = !asList;
  $("#cabmode").hidden = false; $("#selmode").hidden = false;
  $("#sortmode").hidden = asList || !DRAG.matches;   // list view: always offered (way back to the grid)
  $("#cabs").hidden = asList;
  $("#ovhead").hidden = asList;
  if (asList) {
    $("#overflow").hidden = true;
    drawSpoolList();
    markPick(); markSel();
    return;
  }
  const cabs = CABS();
  $("#cabtitle0").innerHTML = cabs[0] ? esc(cabTitle(cabs[0].key)) + climChip(cabs[0].key) + foldBits(cabs[0].key, cabCount(cabs[0].key)) : "";
  $("#cabtitle0").className = "cabfold" + (cabs[0] && !cabClosed.has(cabs[0].key) ? " open" : "");
  if (cabs[0]) $("#cabtitle0").dataset.fold = cabs[0].key;
  $("#cabs").innerHTML = cabs.map((c, ci) => {
    const slots = overview.slots.filter((s) => s.kind === "cabinet" && s.cabinet === c.key);
    const rows = [...new Set(slots.map((s) => s.row))];
    const wide = c.per_row > 6, half = Math.ceil(c.per_row / 2);
    const grid = rows.map((r) => {
      const low = c.lower_from && r >= c.lower_from;
      return (c.lower_from && r === c.lower_from && r > 1 ? `<div class="zonesep">${esc(L(c.unit === "level" ? "Level" : "Rod"))} ${rowLab(c, r)}${r < c.rows ? "–" + rowLab(c, c.rows) : ""}</div>` : "") +
        `<div class="rowlabel${low ? " lower" : ""}" title="${esc(L(c.unit === "level" ? "Level" : "Rod"))} ${rowLab(c, r)}">${rowLab(c, r)}</div>` +
        slots.filter((s) => s.row === r).map((s, i) => (wide && i === half ? `<div class="rowlabel split"></div>` : "") +
          (low ? slotHtml(s).replace('class="', 'class="lower ') : slotHtml(s))).join("");
    }).join("");
    const shut = cabClosed.has(c.key);
    // every cabinet gets the same view switch (it changes all cabinets at once)
    // grid/list switch only next to open cabinets
    return (ci ? `<div class="cabhead"><h2 class="cabfold${shut ? "" : " open"}" data-fold="${esc(c.key)}">${esc(cabTitle(c.key))}${climChip(c.key)}${foldBits(c.key, cabCount(c.key))}</h2><span class="cabtools">${shut ? "" : `<button class="small selbtn">${L("Select")}</button>` + $("#cabmode").outerHTML.replace(' id="cabmode"', "").replace(/ hidden(="")?/, "").replace(" nodetail", "").replace('cabmode"', wide ? 'cabmode"' : 'cabmode nodetail"')}</span></div>` : "") +
      `<div id="cab-${esc(c.key)}" ${shut ? "hidden" : ""} class="grid ${wide ? "cabwide" : "cabnarrow"}" style="--cols:${c.per_row};--half:${half}">${grid}</div>`;
  }).join("");
  $("#overflow").innerHTML = overview.slots.filter((s) => s.kind === "overflow").map((sl) =>
    `<div class="shelf" data-slot="${sl.id}"><b>${T("shelf", sl.cabinet, sl.row)} · ${T("spools", sl.spools.length)}</b>` +
    sl.spools.map((sp) => `<div class="chip" data-spool="${sp.id}">${sw(sp)}${title(sp)}
      <span class="sub">${esc(sp.bambu_no ?? "")}${sp.is_refill ? " · " + T("refill") : ""}</span></div>`).join("") +
    `</div>`).join("");
  const ovN = overview.slots.filter((s) => s.kind === "overflow").reduce((n, s) => n + s.spools.length, 0);
  $("#overflow").hidden = cabClosed.has("overflow");
  $("#overflown").textContent = cabClosed.has("overflow") ? Lp(ovN, "{0} spool", "{0} spools") : "";
  document.querySelector('[data-fold="overflow"]').classList.toggle("open", !cabClosed.has("overflow"));
  // the switch above the first cabinet only while it is open; "Select" while any cabinet or the reserve is open
  $("#cabmode").hidden = !cabs[0] || cabClosed.has(cabs[0].key);
  // cabinets with up to 6 slots per row look the same in compact and detail: there the switch is just grid / list
  $("#cabmode").classList.toggle("nodetail", !!cabs[0] && cabs[0].per_row <= 6);
  document.querySelectorAll(".cabmode.nodetail").forEach((m) => {
    const b = m.querySelector('[data-mode="compact"]'); b.textContent = L("Grid"); b.classList.toggle("on", cabMode !== "list");
  });
  // "Select" next to every open cabinet and the open reserve, so nobody has to scroll up for it
  $("#selmode").hidden = !cabs[0] || cabClosed.has(cabs[0].key);
  $("#ovhead .selbtn").hidden = cabClosed.has("overflow");
  markPick(); markSel();
  if (panel?.kind === "spool") highlight(panel.spool.slot_id, false, panel.spool.id);
  fitCabs();
}
// wide screens with little room for the cabinet (iPhone Duo unfolded in landscape, camera column beside it):
// when a slot gets too narrow for the detail text, that cabinet switches to the compact tiles (color and number)
function fitCabs() {
  if (NARROW_STORAGE.matches) document.querySelectorAll("#cabs .grid.tight").forEach((g) => g.classList.remove("tight"));
  else document.querySelectorAll("#cabs .grid").forEach((g) => {
    const w = g.clientWidth; if (!w) return;
    const cols = +getComputedStyle(g).getPropertyValue("--cols") || 1;
    g.classList.toggle("tight", (w - 28) / cols < 64);
  });
  fitNums();
}
// compact tiles on small phones (iPhone Duo folded): when a spool number no longer fits its tile,
// that cabinet shows the colors only instead of cut-off numbers
function fitNums() {
  const detail = document.body.classList.contains("cabdetail");
  document.querySelectorAll("#cabs .grid").forEach((g) => {
    g.classList.remove("nonum");
    if (detail || g.hidden) return;
    for (const n of g.querySelectorAll(".slot .no")) if (n.offsetWidth && n.scrollWidth > n.clientWidth + 1) { g.classList.add("nonum"); break; }
  });
}
if (window.ResizeObserver) new ResizeObserver(() => fitCabs()).observe($("#cabs"));
// ------------------------------------------------------------ list view: every spool in stock with its remaining filament
let listSort = pref("listSort", "name"), listDesc = pref("listDesc", "0") === "1";
const LIST_SORTS = [["name", "Name"], ["rest", "Remaining"], ["place", "Place"], ["date", "Date"], ["color", "Color"], ["opened", "Opened"], ["price", "Price"]];
// filters: materials (any of them) plus flags (all of them)
let listFilter = (() => { try { const f = JSON.parse(pref("listFilter", "{}")); return { mat: f.mat || [], flags: f.flags || [] }; } catch (e) { return { mat: [], flags: [] }; } })();
const LIST_FLAGS = [["opened", "Opened", (sp) => !!sp.opened_at], ["unopened", "Unopened", (sp) => !sp.opened_at], ["ams", "In AMS", (sp) => !!sp.ams_slot], ["refill", "Refills", (sp) => !!sp.is_refill]];
// date of a spool for the list: when it arrived, else when it was added to PixxelSpool
const spoolDay = (sp) => String(sp.received_at || sp.created_at || "").slice(0, 10);
const spoolMat = (sp) => String(sp.line || "").split(" ")[0] || "–";
const spoolPrice = (sp) => sp.price ?? sp.line_price ?? null;
// colour order: by hue around the colour wheel, greys/black/white after the colours (dark to light)
function hueKey(hex) {
  const m = String(hex || "").match(/^#?([0-9a-f]{6})/i); if (!m) return 9e9;
  const n = parseInt(m[1], 16), r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn;
  if (d < 0.08) return 1000 + l;
  const h = mx === r ? ((g - b) / d + 6) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return h * 60 + l / 10;
}
// remaining filament in percent; null when the spool was opened and nothing was weighed or reported yet
// a spool that was already used (opened, in the AMS or weighed) never shows 100 %, so it is told apart from a new one
const shownPct = (sp) => sp.remain_pct == null ? null
  : Math.round(sp.remain_pct) >= 100 && (sp.opened_at || sp.ams_slot || sp.measured_at) ? 99 : Math.max(0, Math.min(100, Math.round(sp.remain_pct)));
const spoolPct = (sp) => (sp.remain_pct != null ? shownPct(sp) : sp.opened_at || sp.ams_slot ? null : 100);
function drawSpoolList() {
  const all = overview.slots.flatMap((sl) => sl.spools).map((sp) => ({ sp, pct: spoolPct(sp), g: gramsLeft(sp),
    name: `${sp.line} ${cname(sp)}`, place: amsWhere(sp) || sp.slot_id || "–", day: spoolDay(sp), mat: spoolMat(sp), price: spoolPrice(sp) }));
  const mats = [...new Set(all.map((r) => r.mat))].sort((a, b) => a.localeCompare(b, LANG));
  listFilter.mat = listFilter.mat.filter((m) => mats.includes(m));
  const flags = LIST_FLAGS.filter(([k, , f]) => all.some((r) => f(r.sp)) || listFilter.flags.includes(k));
  const rows = all.filter((r) => (!listFilter.mat.length || listFilter.mat.includes(r.mat)) &&
    listFilter.flags.every((k) => (LIST_FLAGS.find((x) => x[0] === k)?.[2] || (() => true))(r.sp)));
  const byName = (a, b) => a.name.localeCompare(b.name, LANG);
  const cmp = { name: (a, b) => byName(a, b) || a.place.localeCompare(b.place, LANG, { numeric: true }),
    place: (a, b) => a.place.localeCompare(b.place, LANG, { numeric: true }),
    rest: (a, b) => (a.pct ?? 101) - (b.pct ?? 101) || byName(a, b),
    date: (a, b) => a.day.localeCompare(b.day) || a.sp.id - b.sp.id,
    color: (a, b) => hueKey(a.sp.hex) - hueKey(b.sp.hex) || byName(a, b),
    opened: (a, b) => String(a.sp.opened_at || "").localeCompare(String(b.sp.opened_at || "")) || byName(a, b),
    price: (a, b) => (a.price ?? 0) - (b.price ?? 0) || byName(a, b) }[listSort] || (() => 0);
  rows.sort((a, b) => (listDesc ? -1 : 1) * cmp(a, b));
  // unknown values always at the end
  const unknown = { rest: (r) => r.pct == null, opened: (r) => !r.sp.opened_at, price: (r) => r.price == null }[listSort];
  if (unknown) rows.sort((a, b) => unknown(a) - unknown(b));
  $("#cabtitle0").className = "";
  $("#cabtitle0").innerHTML = esc(L("All spools")) + ` <span class="foldn">${rows.length < all.length ? `${rows.length} / ${all.length}` : rows.length}</span>`;
  const arrow = listDesc ? "↓" : "↑";
  const chip = (attr, k, lab, on) => `<button class="lchip${on ? " on" : ""}" ${attr}="${esc(k)}" aria-pressed="${on}">${esc(lab)}</button>`;
  const filt = (mats.length > 1 ? mats.map((m) => chip("data-lmat", m, m, listFilter.mat.includes(m))).join("") : "") +
    flags.map(([k, lab]) => chip("data-lflag", k, L(lab), listFilter.flags.includes(k))).join("") +
    (listFilter.mat.length || listFilter.flags.length ? `<button class="lchip clear" data-lclear>${L("All")}</button>` : "");
  const when = (v) => (parseDay(v) ? fmtDay(parseDay(v)) : "–");
  const ext = (sp, day, mat, price) => `<span class="lx lmat">${esc(mat)}</span><span class="lx ldate">${when(day)}</span>` +
    `<span class="lx lopen">${sp.dried_at ? `<span title="${esc(L("Dried"))}">♨ ${when(sp.dried_at)}</span>` : sp.opened_at ? when(sp.opened_at) : `<span class="sub">${esc(T("notOpened"))}</span>`}</span>` +
    `<span class="lx lprice">${price != null ? esc(money(price)) : "–"}</span>`;
  const sortScroll = $("#listsort")?.scrollLeft || 0;   // the sort bar starts at its beginning; a redraw keeps where the user scrolled to
  $("#spoollist").innerHTML = `<div class="listbar"><span class="sub">${L("Sort")}</span><div class="seg" id="listsort">${LIST_SORTS.map(([k, lab]) =>
      `<button data-lsort="${k}" class="${k === listSort ? "on" : ""}">${L(lab)}${k === listSort ? ` <span class="ldir">${arrow}</span>` : ""}</button>`).join("")}</div></div>
    ${filt ? `<div class="lfilter"><span class="sub">${L("Filter")}</span>${filt}</div>` : ""}
    <div class="lhead"><span></span><span>${L("Spool")}</span><span class="lx">${L("Material")}</span><span class="lx">${T("received")}</span><span class="lx">${L("Opened")}</span><span class="lx">${L("Price")}</span><span>${L("Place")}</span><span>${L("Remaining")}</span></div>
    <ul class="lrows">${rows.map(({ sp, pct, g, place, day, mat, price }) => `<li class="lrow${sp.is_refill ? " refill" : ""}" data-spool="${sp.id}" data-lslot="${esc(sp.slot_id ?? "")}">${sw(sp)}
      <span class="lname"><b>${esc(sp.line)}</b> ${esc(cname(sp))}<span class="sub">${esc(sp.bambu_no ?? "")}${sp.is_refill ? " · " + T("refill") : ""}${sp.status === "in_use" ? " · " + T("in_use") : ""}<span class="lxs">${
        listSort === "date" && parseDay(day) ? " · " + fmtDay(parseDay(day)) : listSort === "opened" && sp.opened_at ? " · " + L("opened {0}", when(sp.opened_at)) : listSort === "price" && price != null ? " · " + esc(money(price)) : ""}</span></span></span>
      ${ext(sp, day, mat, price)}
      <span class="lplace">${esc(place)}</span>
      <span class="lrest">${pct != null ? `<span class="bar ${remainCls(pct)}"><i style="width:${pct}%"></i></span><span class="sub">${pct} %${g != null ? ` · ~${g} g` : ""}</span>`
        : `<span class="bar unk"><i></i></span><span class="sub">${L("remaining unknown")}</span>`}</span></li>`).join("") ||
      `<li class="sub lempty">${L(all.length ? "No spool matches the filter." : "No spools in stock.")}</li>`}</ul>`;
  $("#spoollist").querySelectorAll("[data-lsort]").forEach((b) => (b.onclick = () => {
    const k = b.dataset.lsort;
    if (k === listSort) listDesc = !listDesc; else { listSort = k; listDesc = k === "date"; }   // dates: newest first
    setPref("listSort", listSort); setPref("listDesc", listDesc ? "1" : "0"); drawSpoolList(); markSel();
  }));
  const saveFilter = () => { setPref("listFilter", JSON.stringify(listFilter)); drawSpoolList(); markSel(); };
  const flip = (arr, k) => (arr.includes(k) ? arr.filter((x) => x !== k) : [...arr, k]);
  $("#spoollist").querySelectorAll("[data-lmat]").forEach((b) => (b.onclick = () => { listFilter.mat = flip(listFilter.mat, b.dataset.lmat); saveFilter(); }));
  $("#spoollist").querySelectorAll("[data-lflag]").forEach((b) => (b.onclick = () => {
    const k = b.dataset.lflag, other = { opened: "unopened", unopened: "opened" }[k];   // opened and unopened exclude each other
    listFilter.flags = flip(listFilter.flags, k).filter((x) => x !== other); saveFilter();
  }));
  const c = $("#spoollist [data-lclear]"); if (c) c.onclick = () => { listFilter = { mat: [], flags: [] }; saveFilter(); };
  if ($("#listsort")) $("#listsort").scrollLeft = sortScroll;
  if (panel?.kind === "spool") $("#spoollist").querySelector(`[data-spool="${panel.spool.id}"]`)?.classList.add("hl");
}
document.addEventListener("click", (e) => {
  const h = e.target.closest("#storage .cabfold"); if (!h || e.target.closest("button, a, .climchip")) return;
  const k = h.dataset.fold; if (!k) return;
  cabClosed.has(k) ? cabClosed.delete(k) : cabClosed.add(k);
  setPref("cabClosed", JSON.stringify([...cabClosed])); drawStorage();
});
// ------------------------------------------------------------ multi-select in the storage view
let selMode = false;
const sel = new Set();
function markSel() {
  document.querySelectorAll("#storage .sel").forEach((e) => e.classList.remove("sel"));
  document.body.classList.toggle("selecting", selMode);
  document.querySelectorAll("#storage .selbtn").forEach((b) => { b.classList.toggle("on", selMode); b.textContent = selMode ? L("Cancel") : L("Select"); });
  const bar = $("#selbar");
  bar.hidden = !selMode;
  if (!selMode) return;
  for (const id of sel) document.querySelectorAll(`#storage [data-spool="${id}"]`).forEach((e) => e.classList.add("sel"));
  const n = sel.size;
  bar.innerHTML = `<b>${n ? Lp(n, "{0} spool selected", "{0} spools selected") : L("Tap spools to select them")}</b>
    <span class="selacts">${n ? `<button data-bulk="price">${L("Price")}</button><button data-bulk="dried">${L("Dried")}</button>
      <button data-bulk="reserve">${L("To reserve")}</button><button data-bulk="empty">${L("Empty")}</button>
      <button class="danger" data-bulk="delete">${L("Delete")}</button>` : ""}
      <button data-bulk="cab">${L("Select all")}</button></span>`;
  bar.querySelectorAll("[data-bulk]").forEach((b) => (b.onclick = () => bulkAct(b.dataset.bulk)));
}
async function bulkAct(act) {
  if (act === "cab") { overview.slots.forEach((sl) => sl.spools.forEach((sp) => sel.add(String(sp.id)))); return markSel(); }
  const n = sel.size, body = { ids: [...sel].map(Number), action: act };
  if (act === "price") {
    const v = await ask(L("Price per spool for {0} (empty = remove price):", Lp(n, "{0} spool", "{0} spools")), { input: { inputmode: "decimal", money: true, suffix: SET().currency || "€" }, ok: L("Save") });
    if (v === null) return;
    body.price = v.trim();
  }
  if (act === "empty" && !await askConfirm(esc(L("Mark {0} as empty? Their slots become free.", Lp(n, "{0} spool", "{0} spools"))) + emptyHint(n), { ok: L("Empty"), danger: true, html: true })) return;
  if (act === "delete" && !await askConfirm(L("Delete {0} permanently? This is meant for spools added by mistake. Mark used-up spools as empty instead. A backup is made first.", Lp(n, "{0} spool", "{0} spools")), { ok: L("Delete"), danger: true })) return;
  try {
    const r = await api("/api/spools/bulk", { method: "POST", body });
    const undo = r.undo_token ? { label: L("Undo"), run: async () => {
      try { const u = await api("/api/spools/bulk/undo", { method: "POST", body: { token: r.undo_token } });
            toast(L("Undone: {0}", Lp(u.done, "{0} spool", "{0} spools")) + (u.skipped.length ? " · " + L("{0} skipped ({1})", u.skipped.length, tr(u.skipped[0].error)) : ""));
            await refresh(); markSel(); }
      catch (e) { toast(tr(e.message)); } } } : null;
    toast(L("Done: {0}", Lp(r.done, "{0} spool", "{0} spools")) + (r.skipped.length ? " · " + L("{0} skipped ({1})", r.skipped.length, tr(r.skipped[0].error)) : ""), undo);
    if (act !== "price" && act !== "dried") sel.clear();
    await refresh();
  } catch (e) { toast(tr(e.message)); }
  markSel();
}
document.addEventListener("click", (e) => { if (!e.target.closest("#storage .selbtn")) return;
  selMode = !selMode; if (!selMode) sel.clear(); pick = null; markPick(); markSel(); });
function highlight(slotId, scroll = true, spoolId = null) {
  document.querySelectorAll(".hl").forEach((e) => e.classList.remove("hl"));
  if (!slotId && spoolId == null) return;
  const list = !$("#spoollist").hidden;   // list view: mark the spool's row instead of the slot in the grid
  const el = list ? (spoolId != null && $("#spoollist").querySelector(`[data-spool="${spoolId}"]`)) || (slotId && $("#spoollist").querySelector(`[data-lslot="${CSS.escape(slotId)}"]`))
    : slotId && document.querySelector(`[data-slot="${CSS.escape(slotId)}"]`);
  if (el) { el.classList.add("hl"); if (scroll && view === "storage") el.scrollIntoView({ behavior: "smooth", block: "center" }); }
  // shelves hold several spools: mark the spool itself, not only the shelf
  if (!list && spoolId != null) $("#overflow").querySelector(`.chip[data-spool="${spoolId}"]`)?.classList.add("hl");
}
function markPick() {
  document.querySelectorAll(".target").forEach((e) => e.classList.remove("target"));
  $("#pickhint").hidden = !pick;
  if (cabMode === "list" && $("#spoollist").hidden === !pick) return drawStorage();   // grid while picking a slot, list again after
  if (!pick) return;
  $("#pickhint").innerHTML = `<span>${esc(pick.label)}</span><button id="pickcancel">${T("cancel")}</button>`;
  $("#pickcancel").onclick = () => { pick = null; markPick(); };
  document.querySelectorAll(".slot.free, .shelf").forEach((e) => e.classList.add("target"));
  // moving a spool: occupied rod slots can be picked too, to swap the two spools
  if (pick.swapFor) document.querySelectorAll("#cabs .slot:not(.free)").forEach((e) => { if (e.dataset.slot !== pick.swapFor.slot_id) e.classList.add("target", "swaptarget"); });
}
// history actions are stored as codes; these are their (English source) texts for the interface
const ACTION_LABEL = { stored: "stored", taken_out: "taken out", put_back: "put back", empty: "empty", moved: "moved",
  swapped: "swapped", to_reserve: "to reserve", to_live: "to live stock", to_ams: "into AMS", from_ams: "out of AMS", linked: "linked",
  assigned: "assignment", dried: "dried", weighed: "weighed", deleted: "deleted", tag_released: "Tag removed",
  refill_on: "Refill on", refill_off: "Refill off", reset: "reset", import: "import", opened: "opened" };
// history: one card per entry with the spool's color, what happened (colored tag) and where, grouped by day
const ACTION_KIND = { stored: "in", put_back: "in", to_live: "in", import: "in", taken_out: "out", to_ams: "ams", from_ams: "ams",
  empty: "bad", deleted: "bad", reset: "bad", tag_released: "bad", moved: "move", swapped: "move", to_reserve: "move", assigned: "move",
  weighed: "info", dried: "info", linked: "info", refill_on: "info", refill_off: "info", opened: "out" };
const ACTION_ICO = { in: '<path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/>', out: '<path d="M12 15V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/>',
  ams: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M9 5v14M15 5v14"/>', bad: '<path d="M5 7h14"/><path d="M9 7V5h6v2"/><path d="M7 7l1 12h8l1-12"/>',
  move: '<path d="M5 9h13"/><path d="m15 5 4 4-4 4"/><path d="M19 15H6"/><path d="m9 19-4-4 4-4"/>', info: '<circle cx="12" cy="12" r="8"/><path d="M12 11v5"/><path d="M12 8h.01"/>' };
function logDay(ts) {
  const d = new Date(ts.replace(" ", "T")), t = new Date(); t.setHours(0, 0, 0, 0);
  const days = Math.round((t - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
  return days === 0 ? L("Today") : days === 1 ? L("Yesterday") : d.toLocaleDateString(LOCALE, { weekday: "short", day: "numeric", month: "short" });
}
async function drawLog() {
  const ev = (await api("/api/events/recent")).slice(0, +(SET().log_rows ?? 5) || 5);
  let day = "";
  $("#log").innerHTML = ev.map((e) => {
    const kind = ACTION_KIND[e.action] || "info", d = logDay(e.ts);
    const head = d !== day ? `<li class="logday">${esc(d)}</li>` : ""; day = d;
    const detail = e.detail ? tr(e.detail).replace(/\s*->\s*/g, " → ") : "";
    const name = e.color_name ? `${esc(e.line)} ${esc(cname(e))}` : esc(detail || "–");
    const dot = e.color_name ? sw(e, "logsw") : `<span class="logsw logico k-${kind}"><svg viewBox="0 0 24 24" aria-hidden="true">${ACTION_ICO[kind]}</svg></span>`;
    return head + `<li class="logrow"${e.spool_id && e.color_name ? ` data-logspool="${e.spool_id}"` : ""}>${dot}<span class="logtxt"><span class="logname">${name}</span>
      <span class="logsub"><span class="logact k-${kind}">${esc(L(ACTION_LABEL[e.action] || e.action))}</span>${e.color_name && detail ? `<span class="logdet">${esc(detail)}</span>` : ""}</span></span>
      <time class="logtime">${esc(fmtTime(new Date(e.ts.replace(" ", "T"))))}</time></li>`;
  }).join("") || `<li class="logday">${esc(L("no data yet"))}</li>`;
  $("#log").querySelectorAll("[data-logspool]").forEach((li) => (li.onclick = async () => {
    try { showSpool(await api(`/api/spools/${li.dataset.logspool}`)); } catch (err) { toast(err.message); }
  }));
}

// ------------------------------------------------------------ side panel
// refill (spool without its own reel) as a switch
const refillSwitch = (on) => `<label class="tgl" title="${esc(L("Refill: filament without its own spool"))}"><input type="checkbox" role="switch" id="refill" ${on ? "checked" : ""}><span class="tglui" aria-hidden="true"></span>${T("refill")}</label>`;
// release notes (CHANGELOG excerpt) as simple formatted text: version and section headings, bullets, bold, code
function mdNotes(md) {
  const inl = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const out = []; let li = null, inList = false;
  const flush = () => { if (li != null) { out.push(`<li>${inl(li)}</li>`); li = null; } };
  const close = () => { flush(); if (inList) { out.push("</ul>"); inList = false; } };
  for (const raw of String(md || "").split("\n")) {
    const line = raw.trimEnd();
    if (/^\s*-\s+/.test(line)) { flush(); if (!inList) { out.push("<ul>"); inList = true; } li = line.replace(/^\s*-\s+/, ""); continue; }
    if (li != null && /^\s+\S/.test(line)) { li += " " + line.trim(); continue; }
    close();
    if (/^##\s/.test(line)) out.push(`<h4>${inl(line.replace(/^##\s+/, "").replace(/[[\]]/g, ""))}</h4>`);
    else if (/^###\s/.test(line)) out.push(`<h5>${inl(line.replace(/^###\s+/, ""))}</h5>`);
    else if (line.trim()) out.push(`<p>${inl(line)}</p>`);
  }
  close();
  return out.join("");
}
// ------------------------------------------------------------ own dialogs instead of the browser's confirm()/prompt()
// ask(text, {ok, cancel, danger, title, input: {value, placeholder, suffix, inputmode}, extra: [{label, value}]})
// resolves with true/false, or with the typed text / null when there is an input, or with an extra button's value
// line under an "empty" question: the empty reel goes to the counter of empty spools (for refills)
const emptyHint = (n = 1) => { const c = +(SET().empty_spools ?? 0); return `<span class="dlgnote">${esc(L("Empty spools for refills: {0} → {1}", c, c + n))}</span>`; };
function ask(text, o = {}) {
  return new Promise((resolve) => {
    const prev = document.activeElement;
    const wrap = document.createElement("div"); wrap.className = "dlgwrap";
    const inp = o.input ? `<div class="dlgin"><input id="dlginput" type="${o.input.type || "text"}" ${o.input.inputmode ? `inputmode="${o.input.inputmode}"` : ""}${o.input.money ? " data-money" : ""} value="${esc(o.input.value ?? "")}" placeholder="${esc(o.input.placeholder ?? "")}" autocomplete="${o.input.type === "password" ? "current-password" : "off"}">${o.input.suffix ? `<span>${esc(o.input.suffix)}</span>` : ""}</div>` : "";
    const warnIco = o.warn ? `<span class="dlgwarn" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.8 18.5A2 2 0 0 0 3.5 21.5h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4.5"/><path d="M12 17.5h.01"/></svg></span>` : "";
    wrap.innerHTML = `<div class="dlg${o.warn ? " warn" : ""}${o.red ? " red" : ""}" role="dialog" aria-modal="true">${warnIco}${o.title ? `<h3>${esc(o.title)}</h3>` : ""}${o.block ? text : `<p>${o.html ? text : esc(text)}</p>`}${inp}
      <div class="actions">${(o.extra || []).map((x, i) => `<button data-dx="${i}">${esc(x.label)}</button>`).join("")}<span class="grow"></span>
      ${o.noCancel ? "" : `<button data-dc>${esc(o.cancel || L("Cancel"))}</button>`}<button data-dok class="${o.danger || o.red ? "danger solid" : o.warn ? "warnbtn" : "primary"}">${esc(o.ok || L("OK"))}</button></div></div>`;
    document.body.append(wrap);
    requestAnimationFrame(() => wrap.classList.add("in"));
    const field = wrap.querySelector("#dlginput"), okBtn = wrap.querySelector("[data-dok]");
    let wait = o.wait | 0, waitT = null;     // o.wait: the OK button can only be pressed after this many seconds
    if (wait > 0) {
      const tick = () => { okBtn.disabled = wait > 0; okBtn.textContent = (o.ok || L("OK")) + (wait > 0 ? ` (${wait})` : ""); if (wait-- > 0) waitT = setTimeout(tick, 1000); };
      tick();
    }
    (field || (wait > 0 ? wrap.querySelector("[data-dc]") : okBtn) || okBtn).focus(); field?.select();
    const done = (v) => { clearTimeout(waitT); document.removeEventListener("keydown", key, true); wrap.classList.remove("in"); setTimeout(() => wrap.remove(), 180); prev?.focus?.(); resolve(v); };
    const okv = () => (o.input ? field.value : true), nov = o.input ? null : false;
    const key = (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); done(nov); } else if (e.key === "Enter" && (field || document.activeElement === wrap.querySelector("[data-dok]"))) { e.preventDefault(); if (!okBtn.disabled) done(okv()); } };
    document.addEventListener("keydown", key, true);
    wrap.onclick = (e) => {
      if (e.target === wrap || e.target.closest("[data-dc]")) return done(nov);
      if (e.target.closest("[data-dok]")) return okBtn.disabled ? undefined : done(okv());
      const x = e.target.closest("[data-dx]"); if (x) done(o.extra[+x.dataset.dx].value);
    };
  });
}
const askConfirm = (text, o) => ask(text, o);
function render() {
  const p = panel, el = $("#panel");
  document.body.classList.toggle("sheet", !!p);
  if (!p) {
    el.innerHTML = `<div class="idle"><span class="big" aria-hidden="true">◎</span><h3>${T("idleTitle")}</h3></div>`;
    return;
  }
  if (p.kind === "spool") renderSpool(el, p);
  else if (p.kind === "new") renderNew(el, p);
  else if (p.kind === "unmapped") renderUnmapped(el, p);
  else if (p.kind === "plain") renderPlain(el, p);
  // on phones the panel is a bottom sheet, closed with ×
  el.insertAdjacentHTML("afterbegin", `<button class="sheetclose" aria-label="${T("close")}">×</button>`);
  el.querySelector(".sheetclose").onclick = () => { panel = null; render(); highlight(null); };
  if (matchMedia("(max-width: 700px)").matches) el.scrollTop = 0;
}
addEventListener("keydown", (e) => {   // Esc closes the spool card like the ×
  if (e.key !== "Escape" || !panel || tour || document.body.classList.contains("wizopen") || e.target.closest?.("input, textarea, select")) return;
  panel = null; render(); highlight(null);
});
async function systemAction(action) {
  if (!await askConfirm(T(action === "poweroff" ? "sysConfirmPoweroff" : "sysConfirmReboot"), { ok: action === "poweroff" ? T("sysPoweroff") : T("sysReboot"), danger: action === "poweroff" })) return;
  try { await api("/api/system", { method: "POST", body: { action } }); toast(T("sysDone")); }
  catch (e) { toast(e.message); }
}
$("#sysreboot").onclick = () => systemAction("reboot");
$("#sysrestart").onclick = async () => {
  if (!await askConfirm(L("Restart PixxelSpool now? The page will be unavailable for about 20 seconds."), { ok: L("Restart") })) return;
  try { await api("/api/system", { method: "POST", body: { action: "restart" } }); } catch (e) { toast(e.message); return; }
  toast(L("PixxelSpool is restarting …"));
  const t0 = Date.now();
  await new Promise((r) => setTimeout(r, 4000));
  while (Date.now() - t0 < 120000) {
    try { const r = await fetch("/api/overview", { cache: "no-store" }); if (r.ok) { location.reload(); return; } } catch (e) {}
    await new Promise((r) => setTimeout(r, 2000));
  }
  toast(L("PixxelSpool is not responding. Please reload the page."));
};
$("#syspoweroff").onclick = () => systemAction("poweroff");
// Pi-only controls (power buttons, PN532 wiring help, Tailscale setup) are hidden in the Windows app
function drawHost() {
  const h = overview?.host || {};
  if (!h.kind) return;
  $("#sysreboot").hidden = $("#syspoweroff").hidden = !h.power;
  $("#sysrestart").hidden = !h.restart;
  document.querySelectorAll('[data-rmode="pn532"]').forEach((b) => (b.hidden = !h.pn532));
  document.querySelectorAll(".pi-only").forEach((el) => (el.hidden = h.kind !== "pi"));
  document.body.dataset.host = h.kind;
  const t = $("#systool .otitle");
  if (t && h.kind !== "pi") { t.textContent = L("PixxelSpool"); delete t.dataset.t; }
  const intro = $("#systool .foldbody > p.sub");
  if (intro && h.kind !== "pi") delete intro.dataset.t;
  if (intro && h.kind !== "pi") intro.textContent = L("A restart helps when the reader or the printer stops responding.");
  const upd = $("#updintro");
  if (upd && h.self_update === false) upd.textContent = L("New versions come straight from GitHub. PixxelSpool tells you about them and links to the download; install it over the old version. Your data stays unchanged.");
}
function tagDetails(t) {
  if (!t) return "";
  return `<dl><dt>${T("variant")}</dt><dd>${esc(t.variant_id)} / ${esc(t.material_id)}</dd>
    <dt>${T("weight")}</dt><dd>${t.weight_g} g · ${t.length_m} m</dd>
    <dt>${T("nozzle")}</dt><dd>${t.hotend_min_c}–${t.hotend_max_c} °C · ${T("bed")} ${t.bed_temp_c} °C</dd>
    <dt>${T("drying")}</dt><dd>${t.drying_temp_c} °C, ${t.drying_time_h} h</dd></dl>${serialFold(t.tray_uid)}`;
}
function serialFold(uid) {
  return uid ? `<details class="serial"><summary>${T("serial")}</summary><code>${esc(uid)}</code></details>` : "";
}
const money = (v) => v == null ? "–" : Number(v).toLocaleString(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " " + (SET().currency || "€");
const dateShort = (v) => v ? new Date(String(v).replace(" ", "T")).toLocaleDateString(LOCALE, { day: "numeric", month: "short", year: "numeric" }) : "";
const dateTimeShort = (v) => v ? new Date(String(v).replace(" ", "T")).toLocaleString(LOCALE, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
// "lasts about …": filament left of this color (all spools) divided by the usage per day of the recent prints
function reachText(pid) {
  const rate = insights?.usage?.rate?.[pid]; if (!rate) return "";
  const left = spoolsOf(pid).reduce((a, sp) => a + (gramsLeft(sp) ?? 0), 0); if (!left) return "";
  const d = left / rate;
  return d < 1.5 ? L("less than 2 days") : d < 14 ? Lp(Math.round(d), "about {0} day", "about {0} days")
    : d < 60 ? Lp(Math.round(d / 7), "about {0} week", "about {0} weeks") : d < 730 ? Lp(Math.round(d / 30), "about {0} month", "about {0} months") : L("more than 2 years");
}
function spoolFacts(s) {
  const price = s.price ?? s.line_price;
  // remaining filament: grams of the full weight and percent; colors as in the list (remainCls)
  const full = s.weight_g || s.net_g || 1000, pct = shownPct(s);
  // weighed: filament only (scale reading minus the empty spool); the rest uses it while the percent still matches
  const wnet = s.measured_g != null ? Math.max(0, s.measured_g - (s.spool_g ?? SET().spool_g_default ?? 250)) : null;
  const restG = wnet != null && pct === Math.max(0, Math.min(100, Math.round(wnet * 100 / full))) ? wnet : Math.round(full * pct / 100);
  const rest = pct != null && s.status !== "empty" ? `<dt>${L("Remaining")}</dt><dd><b class="restnow ${remainCls(pct)}">${restG} g</b> / ${full} g · ${pct} %</dd>` : "";
  const reach = s.status !== "empty" ? reachText(s.product_id) : "";
  return `<dl class="facts">${rest}${reach ? `<dt>${L("Lasts")}</dt><dd>${esc(reach)} <span class="sub" title="${esc(L("All spools of this color, at your usage of the last {0} days", insights.usage.rate_days))}">(${esc(L("this color"))})</span></dd>` : ""}${s.measured_at && wnet != null ? `<dt>${L("Weighed")}</dt><dd>${wnet} g · ${esc(dateShort(s.measured_at))}</dd>` : ""}
    <dt>${L("Price")}</dt><dd>${price != null ? money(price) + (s.price == null ? ` <span class="sub">(${L("estimate")})</span>` : "") : `<span class="sub">${L("not set")}</span>`}
      <button class="linkbtn" data-act="price">${L("change")}</button></dd>
    <dt>${L("Minimum stock")}</dt><dd>${minStock(s.product_id) ? esc(Lp(minStock(s.product_id), "{0} spool", "{0} spools")) : `<span class="sub">${L("none")}</span>`}
      <button class="linkbtn" data-act="minstock">${L("change")}</button></dd></dl>
    ${panel?.priceEdit ? `<div class="dateedit"><b>${L("Price of this spool")}</b>
      <div class="pricefield"><input id="pricein" inputmode="decimal" data-money value="${esc(panel.priceEdit.value)}" placeholder="${esc(s.line_price != null ? L("Line: {0}", money(s.line_price)) : L("e.g. 19.99"))}" autocomplete="off"><span class="cur">${esc(SET().currency || "€")}</span></div>
      ${s.price != null ? `<button class="linkbtn" id="priceline">${L("Use the line price")}</button>` : ""}
      <div class="actions"><button class="small" id="pricecancel">${L("Cancel")}</button><button class="small primary" id="pricesave1">${L("Save")}</button></div></div>` : ""}
    <dl class="facts">${s.brand ? `<dt>${L("Brand")}</dt><dd>${esc(s.brand)}${s.sku ? ` · ${esc(s.sku)}` : ""}</dd>` : ""}
    ${s.dry_temp ? `<dt>${L("Drying")}</dt><dd>${s.dry_temp} °C${s.dry_hours ? ", " + s.dry_hours + " h" : ""}</dd>` : ""}</dl>`;
}
function renderSpool(el, p) {
  const s = p.spool;
  const where = s.status === "empty" ? T("empty") : s.slot_id ?? "–";
  const badges = [
    `<span class="badge ${s.status === "in_use" ? "warn" : ""}">${STATUS[s.status]}</span>`,
    s.in_cabinet ? `<span class="badge">${T("cabinet")}</span>` : s.slot_id ? `<span class="badge">${T("overflow")}</span>` : "",
    s.is_refill ? `<span class="badge">${T("refill")}</span>` : "",
    s.tray_uid ? "" : `<span class="badge warn">${T("unscanned")}</span>`,
    s.ams_slot ? `<span class="badge info">${esc(amsBadge(s))}</span>` : "",
    s.needs_return ? `<span class="badge warn">${T("toReturn")}</span>` : "",
    p.note ? `<span class="badge info">${esc(T(p.note))}</span>` : "",
  ].join("");
  const acts = [];

  if (s.status === "in_use") acts.push(`<button class="primary" data-act="return">${T("ret")}</button>`);
  if (s.status === "empty") acts.push(`<button class="primary" data-act="return">${T("restore")}</button>`);
  acts.push(`<button data-act="move">${T("move")}</button>`);
  acts.push(`<button data-act="card">${L("Share profile card")}</button>`);
  const sib = !s.in_cabinet && s.status !== "empty" && overview?.slots.flatMap((x) => x.spools)
    .find((o) => o.product_id === s.product_id && o.in_cabinet && o.id !== s.id);
  if (s.status !== "empty" && s.in_cabinet) acts.push(`<button data-act="reserve" title="${L("Moves to the reserve, frees the fixed slot")}">${L("Move to reserve")}</button>`);
  if (s.status !== "empty" && !s.in_cabinet && s.slot_id) acts.push(`<button data-act="live" title="${sib ? L("Swaps with the spool on {0}", esc(sib.slot_id)) : L("Gets a free fixed slot")}">${L("To live stock")}${sib ? `<small>${L("swap with {0}", esc(sib.slot_id))}</small>` : ""}</button>`);
  // a refill that was never opened and is not in the AMS cannot be used up
  if (s.status !== "empty" && !(s.is_refill && !s.ams_slot && !s.opened_at)) acts.push(`<button class="danger" data-act="empty">${T("markEmpty")}</button>`);
  if (s.status !== "empty" && !s.is_refill) acts.push(`<button data-act="weigh" title="${L("Weigh the spool to find out what's left")}">${L("Weigh")}</button>`);
  if (!s.tray_uid && s.status !== "empty") acts.push(`<button data-act="linktag" title="${L("Stick an NFC sticker on the spool and link it here")}">${L("Add tag")}</button>`);
  // quiet extras in one row with the refill switch
  const links = [];
  if (s.ams_bound && s.ams_slot) links.push(`<button class="linkbtn" data-act="unassign" title="${esc(L("Assigned to the wrong AMS slot? This undoes it."))}">${L("Undo AMS assignment")}</button>`);
  if (String(s.tray_uid || "").startsWith("NFC-")) links.push(`<button class="linkbtn" data-act="unlinktag">${L("Remove sticker tag")}</button>`);
  if (s.status === "stored") links.push(`<button class="linkbtn" data-act="take" title="${L("Only needed if the spool doesn't go into the AMS")}">${L("Take out without AMS")}</button>`);
  const other = LANG === "de" ? s.name_en : s.name_de;
  el.innerHTML = `<div class="head"><button class="swbtn" data-swzoom aria-label="${esc(L("Show colour large"))}">${sw(s, "lg")}</button><div><h3>${title(s)}</h3>
    <div class="sub">${s.brand ? esc(s.brand) + (s.sku ? " " + esc(s.sku) : "") : "Bambu " + esc(s.bambu_no ?? "–")}${other && other !== cname(s) ? ` · ${esc(other)}` : ""}</div></div></div>
    <div class="where" title="${esc(T("slot"))}">${esc(where)}</div>${badges}
    <div class="actions">${acts.join("")}</div>
    <div class="spoolopts">${s.opened_at && !s.is_refill ? "" : refillSwitch(s.is_refill)}${links.join("")}</div>
    ${s.status !== "empty" && s.remain_pct === 0 ? `<div class="msg">${L("According to the AMS the spool is empty.")} <div class="actions"><button class="danger" data-act="empty">${L("Empty – remove")}</button></div></div>`
      : s.status !== "empty" && s.remain_pct != null && s.remain_pct <= SET().low_remain_pct ? `<div class="msg">${T("lowRemain")}</div>` : ""}
    ${(insights?.drying || []).some((d) => d.id === s.id) ? `<div class="msg">${L("Open for {0} days – drying recommended.", insights.drying.find((d) => d.id === s.id).open_days)} <div class="actions"><button data-act="dried">${L("Dried")}</button></div></div>` : ""}
    ${p.msg ? `<div class="msg">${typeof p.msg === "function" ? p.msg() : p.msg}</div>` : ""}
    ${ageBlock(s)}${spoolFacts(s)}
    <div class="spoolfoot"><div class="grow">${tagDetails(p.tag) || (s.tray_uid ? `<dl><dt>${T("weight")}</dt><dd>${s.weight_g || s.net_g ? (s.weight_g || s.net_g) + " g" : "–"}</dd></dl>${serialFold(s.tray_uid)}` : "")}</div>
      <button class="delspool" data-act="delete" aria-label="${esc(L("Delete spool"))}" title="${esc(L("Delete spool"))} – ${esc(L("Removes the spool for good, without counting an empty spool"))}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14"/><path d="M10 11v6M14 11v6"/></svg></button></div>`;
  highlight(s.slot_id, true, s.id);
  el.querySelectorAll("[data-act]").forEach((b) => (b.onclick = () => spoolAction(s, b.dataset.act)));
  if ($("#refill")) $("#refill").onchange = async (e) => {
    const on = e.target.checked, body = { is_refill: on ? 1 : 0 };
    // marking a spool as refill only corrects the entry. Only the way back (the refill now sits on
    // an empty spool from the stock) uses up an empty spool, and only if the user says so.
    const c = +(SET().empty_spools ?? 0);
    if (!on && c > 0) {
      body.used_empty_spool = await ask(L("Did you put this refill onto an empty spool from your stock?") +
        `<span class="dlgnote">${esc(L("Empty spools for refills: {0} → {1}", c, c - 1))}</span>`,
        { html: true, title: L("Refill"), ok: L("Yes, an empty spool"), cancel: L("No") });
    }
    panel.spool = await api(`/api/spools/${s.id}`, { method: "PATCH", body });
    if (body.used_empty_spool) refresh();
    const p0 = panel; setTimeout(() => { if (panel === p0) render(); }, 260);   // after the switch animation: "Wiegen" only without refill
  };
  el.querySelectorAll("[data-edit]").forEach((a) => (a.onclick = (ev) => {
    ev.preventDefault();
    const field = a.dataset.edit;
    panel.dateEdit = { field, value: s[field] ? String(s[field]).slice(0, 10) : isoDay(new Date()) }; panel.priceEdit = null;
    render();
  }));
  if (panel.dateEdit) {
    const inp = $("#datepick"), nat = $("#datenative"), field = panel.dateEdit.field;
    // typed in the chosen format; the calendar button opens the browser's own date picker
    inp.oninput = () => { panel.dateEdit.value = parseFmtDay(inp.value); inp.classList.toggle("bad", !!inp.value.trim() && !panel.dateEdit.value); };
    nat.onchange = () => { if (nat.value) { panel.dateEdit.value = nat.value; inp.value = fmtDay(parseDay(nat.value)); inp.classList.remove("bad"); } };
    $("#calbtn").onclick = () => { try { nat.showPicker(); } catch (e) { nat.focus(); nat.click(); } };
    inp.onkeydown = (e) => { if (e.key === "Enter") $("#datesave").click(); };
    const save = async (v) => {
      try { panel.spool = await api(`/api/spools/${s.id}`, { method: "PATCH", body: { [field]: v } }); panel.dateEdit = null; render(); toast(L("Saved")); }
      catch (e) { toast(e.message); }
    };
    $("#datesave").onclick = () => panel.dateEdit.value && panel.dateEdit.value <= isoDay(new Date()) ? save(panel.dateEdit.value)
      : toast(inp.value.trim() ? L("Date not recognised, please enter it like this: {0}", inp.placeholder) : L("Please choose a date"));
    $("#datetoday").onclick = () => save(isoDay(new Date()));
    if ($("#dateclear")) $("#dateclear").onclick = () => save(null);
    $("#datecancel").onclick = () => { panel.dateEdit = null; render(); };
  }
  if (panel.priceEdit) {
    const inp = $("#pricein");
    inp.oninput = () => { panel.priceEdit.value = inp.value; };
    const save = async (v) => {
      try { panel.spool = await api(`/api/spools/${s.id}/price`, { method: "POST", body: { price: v } }); panel.priceEdit = null; render(); toast(L("Saved")); }
      catch (e) { toast(tr(e.message)); }
    };
    $("#pricesave1").onclick = () => save(inp.value.trim());
    inp.onkeydown = (e) => { if (e.key === "Enter") save(inp.value.trim()); else if (e.key === "Escape") { panel.priceEdit = null; render(); } };
    if ($("#priceline")) $("#priceline").onclick = () => save("");
    $("#pricecancel").onclick = () => { panel.priceEdit = null; render(); };
  }
  if (p.after) p.after();
}
async function spoolAction(s, act, sure = false) {
  // beta.2: marking empty happens right away; the message offers "Undo" for a few seconds instead of asking first
  try {
    if (act === "card") return shareCard(s);
    if (act === "minstock") { if (await askMinStock(s.product_id, `${s.line} ${cname(s)}`)) render(); return; }
    if (act === "delete") {
      if (!await askConfirm(esc(L("Delete {0} permanently?", `${s.line} ${cname(s)}`)) +
        `<span class="dlgnote">${esc(L("Meant for spools added by mistake or given away. Unlike “Empty”, the counter of empty spools does not change and the spool disappears from storage and statistics. A backup is made first."))}</span>`,
        { ok: L("Delete"), danger: true, html: true, title: L("Delete spool") })) return;
      await api(`/api/spools/${s.id}`, { method: "DELETE" });
      panel = null; render(); highlight(null); await refresh(); toast(L("Spool deleted"));
      return;
    }
    if (act === "move") {
      pick = { label: T("pickMove", `${s.line} ${cname(s)}`), swapFor: s, onPick: async (slot) => {
        showSpool(await api(`/api/spools/${s.id}/move`, { method: "POST", body: { slot_id: slot, manual: true } }));
        toast(T("movedTo", slot)); } };
      if (view !== "storage") showView("storage");
      return markPick();
    }
    if (act === "weigh") {
      const tare = s.spool_g ?? SET().spool_g_default ?? 250, net = s.weight_g || s.net_g || 1000;
      const noTare = !!s.brand && s.spool_g == null;   // other brands: the empty weight is only known if the user entered it
      const msg = () => `<div class="weigh"><p>${L("Put the spool on the scale and enter the weight.")}</p>
        <div class="inline"><input id="wgross" type="number" inputmode="numeric" min="0" max="20000" placeholder="${esc(L("e.g. 640"))}"> g</div>
        <div class="actions"><button class="primary" id="wsave">${L("Apply")}</button><button id="wcancel">${L("Cancel")}</button></div>
        <p class="sub">${L("The empty spool weight is subtracted: {0} g. Full spool: {1} g of filament.", tare, net)}</p>
        ${noTare ? `<div class="msg warnmsg">${esc(L("No empty spool weight is set for {0}, so {1} g is assumed. The result can be off by quite a bit.", s.line, tare))}
          <div class="actions"><button class="small" id="wtare">${L("Enter empty spool weight")}</button></div></div>` : ""}</div>`;
      const after = () => {
        const inp = $("#wgross"); if (!inp) return; inp.focus();
        const go = async () => {
          try { const r = await api(`/api/spools/${s.id}/weigh`, { method: "POST", body: { gross_g: inp.value } });
            await refresh(); showSpool(r.spool, null, () => esc(L("Weighed: {0} g left ({1} %).", r.rest_g, r.pct))); }
          catch (e) { toast(tr(e.message)); }
        };
        $("#wsave").onclick = go; inp.onkeydown = (e) => { if (e.key === "Enter") go(); };
        $("#wcancel").onclick = () => showSpool(s);
        if ($("#wtare")) $("#wtare").onclick = () => editBrandLine(s.line_id);
      };
      panel = { kind: "spool", spool: s, msg, after }; render();
      return;
    }
    if (act === "price") {
      // inline box like the date editor (no browser prompt)
      panel.dateEdit = null;
      panel.priceEdit = { value: s.price != null ? Number(s.price).toFixed(2).replace(".", LANG === "en" ? "." : ",") : "" };
      render(); $("#pricein")?.focus();
      return;
    }
    if (act === "linktag") {
      await api(`/api/spools/${s.id}/linktag`, { method: "POST", body: {} });
      const msg = () => `<span class="upbusy"><span class="spin"></span> ${L("Now place the sticker on the reader …")}</span><div class="actions"><button id="linkcancel">${L("Cancel")}</button></div>`;
      const after = () => { const b = $("#linkcancel"); if (b) b.onclick = async () => { await api("/api/linktag/cancel", { method: "POST" }); showSpool(s); }; };
      panel = { kind: "spool", spool: s, msg, after }; render();
      clearTimeout(spoolAction.t);
      spoolAction.t = setTimeout(() => { if (panel?.kind === "spool" && panel.spool.id === s.id && panel.msg === msg) { panel.msg = L("No sticker detected. Please try again."); render(); } }, 90000);
      return;
    }
    if (act === "unassign") {
      const r = await api(`/api/spools/${s.id}/unassign`, { method: "POST" });
      await refresh(); showSpool(r.spool, null, () => esc(L("Assignment undone.")));
      return;
    }
    if (act === "unlinktag") {
      if (!await askConfirm(L("Remove the sticker tag from this spool? The sticker can then be used for another spool."), { ok: L("Unlink") })) return;
      const r = await api(`/api/spools/${s.id}/unlinktag`, { method: "POST" });
      await refresh(); showSpool(r.spool, null, () => esc(L("Tag removed.")));
      return;
    }
    if (act.startsWith("swapwith:")) {
      const res = await api(`/api/spools/${s.id}/swapwith`, { method: "POST", body: { other: +act.slice(9) } });
      await refresh(); showSpool(res.spool, null, L("Swapped: this spool now belongs on <b>{0}</b>, the other one on <b>{1}</b>.", esc(res.spool.slot_id), esc(res.other.slot_id)));
      return;
    }
    const res = await api(`/api/spools/${s.id}/${act}`, { method: "POST" });
    if (act === "reserve") { await refresh(); showSpool(res.spool, null, L("To reserve: put the spool on <b>{0}</b>. Slot <b>{1}</b> is now free.", esc(res.spool.slot_id), esc(res.freed))); return; }
    if (act === "live") { await refresh(); showSpool(res.spool, null, L("To live stock: hang the spool on <b>{0}</b>.", esc(res.spool.slot_id)) + (res.other ? " " + L("The spool that was there goes to <b>{0}</b>.", esc(res.other.slot_id)) : "")); return; }
    if (act === "swap") { await refresh(); showSpool(res.spool, null, L("Swapped: this spool now belongs on <b>{0}</b>, the other one on <b>{1}</b>.", esc(res.spool.slot_id), esc(res.other.slot_id))); return; }
    if (act === "empty") {
      const before = { slot: s.in_cabinet ? s.slot_id : null };
      toast(L("{0} marked as empty", `${s.line} ${cname(s)}`), { label: L("Undo"), run: async () => {
        try {
          // back onto its old slot if that is still free, otherwise PixxelSpool proposes one (like "Put back")
          const sp = before.slot && !overview.slots.find((x) => x.id === before.slot)?.spools.length
            ? await api(`/api/spools/${s.id}/move`, { method: "POST", body: { slot_id: before.slot } })
            : await api(`/api/spools/${s.id}/return`, { method: "POST" });
          await refresh(); showSpool(sp); toast(L("Undone"));
        } catch (e) { toast(tr(e.message)); }
      } });
      const msg = () => T("emptied") + " " + (res.successor
        ? `${esc(T("successor", res.successor.slot_id))}<div class="actions"><button class="primary" id="promote">${esc(T("promote", res.freed_slot))}</button></div>`
        : res.freed_slot ? esc(T("freed", res.freed_slot)) : "");
      const after = () => {
        const b = $("#promote");
        if (b) b.onclick = async () => showSpool(
          await api(`/api/spools/${res.successor.id}/move`, { method: "POST", body: { slot_id: res.freed_slot } }), null, T("promoted"));
      };
      panel = { kind: "spool", spool: res.spool, msg, after }; render();
      return;
    }
    showSpool(res); toast(act === "take" ? T("taken") : act === "dried" ? L("Marked as dried") : T("putBack"));
  } catch (e) { toast(e.message); }
}
function showSpool(spool, tag = null, msg = "", note = "") { panel = { kind: "spool", spool, tag, msg, note }; render(); }

const lastTyped = {};   // last price typed per line (for several spools of one delivery in a row)
function renderNew(el, p) {
  const pr = p.product, t = p.tag, slot = p.slot_id;
  el.innerHTML = `<div class="head">${sw(pr.hex || pr.colors ? pr : "#" + t.color_rgba.slice(0, 6), "lg")}<div>
    <h3>${title(pr)}</h3><div class="sub">${T("newSpool")} · ${pr.brand ? esc(pr.brand) : "Bambu " + esc(pr.bambu_no ?? "–")}</div></div></div>
    <div class="sub">${p.in_cabinet ? T("proposeCab") : T("proposeOverflow")}</div>
    <div class="where">${esc(slot)}</div>
    <div class="spoolopts">${refillSwitch(false)}</div>
    <label class="pricein"><span class="sub">${L("Price (optional)")}</span><input id="newprice" inputmode="decimal" data-money value="${esc(lastTyped[pr.line] || "")}" placeholder="${esc(p.lastPrice != null ? L("last {0}", priceStr(p.lastPrice)) : "–")}"> ${esc(SET().currency || "€")}</label>
    <div class="actions"><button class="primary" id="store">${T("storeHere")}</button>
      <button id="other">${T("otherSlot")}</button></div>
    ${p.msg ? `<div class="msg err">${esc(p.msg)}</div>` : ""}${tagDetails(t)}`;
  highlight(slot);
  if (p.lastPrice === undefined) api(`/api/prices/last/${pr.id}`).then((r) => { if (panel === p) { p.lastPrice = r.price; const i = $("#newprice"); if (i && r.price != null) i.placeholder = L("last {0}", priceStr(r.price)); } }).catch(() => {});
  const doStore = async (slotId, manual = false) => {
    try {
      const price = ($("#newprice")?.value || "").trim();
      if (price) lastTyped[pr.line] = price; else delete lastTyped[pr.line];
      const s = await api("/api/spools", { method: "POST",
        body: { tag: t, product_id: pr.id, slot_id: slotId, is_refill: $("#refill")?.checked, price, manual } });
      showSpool(s, t); toast(T("storedIn", slotId));
    } catch (e) { panel.msg = e.message; render(); }
  };
  $("#store").onclick = () => doStore(slot);
  $("#other").onclick = () => { pick = { label: T("pickNew"), onPick: (sid) => doStore(sid, sid !== slot) }; if (view !== "storage") showView("storage"); markPick(); };
}

// retrofitted sticker tag (NTAG): link it to a spool without a tag
function renderPlain(el, p) {
  const q = (p.q || "").toLowerCase();
  const list = (p.unlinked || []).filter((s) => !q || `${s.line} ${cname(s)} ${s.bambu_no ?? ""} ${s.slot_id ?? ""}`.toLowerCase().includes(q));
  el.innerHTML = `<div class="head"><span class="nfcbadge">NFC</span><div><h3>${L("New sticker tag")}</h3>
    <div class="sub">${L("ID {0}", esc(p.tag.uid))}</div></div></div>
    ${p.msg ? `<div class="msg err">${esc(p.msg)}</div>` : ""}
    ${(p.unlinked || []).length ? `<p>${L("Which spool gets this tag?")}</p>
      <input id="plainq" type="search" placeholder="${esc(L("Search …"))}" value="${esc(p.q || "")}">
      <ul class="plainlist">${list.map((s) => `<li data-id="${s.id}">${sw(s)}<span class="grow">${title(s)}<span class="sub">${esc(s.slot_id ?? "–")}${s.bambu_no ? " · " + esc(s.bambu_no) : ""}</span></span><span class="chev">›</span></li>`).join("") || `<li class="sub">${L("Nothing found")}</li>`}</ul>`
      : `<p class="sub">${L("All spools in storage already have a tag.")}</p>`}
    <p class="sub">${L("Spool missing? Create it under Options → Add spool manually, then place the sticker again.")}</p>`;
  highlight(null);
  const qi = $("#plainq");
  if (qi) qi.oninput = () => { p.q = qi.value; const pos = qi.selectionStart; renderPlain(el, p); const n = $("#plainq"); n.focus(); n.setSelectionRange(pos, pos); };
  el.querySelectorAll(".plainlist li[data-id]").forEach((li) => (li.onclick = async () => {
    try {
      const r = await api(`/api/spools/${li.dataset.id}/linktag`, { method: "POST", body: { tag: p.tag } });
      await refresh(); showSpool(r.spool, null, () => esc(L("Tag linked. From now on, just place it on the reader to find this spool.")));
    } catch (e) { p.msg = e.message; renderPlain(el, p); }
  }));
}
function renderUnmapped(el, p) {
  const t = p.tag, hex = "#" + t.color_rgba.slice(0, 6);
  const same = p.candidates.filter((c) => c.line === t.detailed_type);
  const opts = (list) => list.map((c) => `<option value="${c.id}">${esc(c.bambu_no ?? "–")} · ${esc(cname(c))}` +
    `${c.mapped ? ` (${T("alreadyMapped")})` : ""}</option>`).join("");
  el.innerHTML = `<div class="head">${sw(hex, "lg")}<div><h3>${esc(t.detailed_type)}</h3>
    <div class="sub">${hex} · ${T("variant")} ${esc(t.variant_id)}</div></div></div>
    <p>${T("unknownColor")}</p>
    <div class="field">${T("fromStock")}<select id="prod">
      ${same.length ? `<optgroup label="${esc(t.detailed_type)}">${opts(same)}</optgroup>` : ""}
      <optgroup label="${T("allOthers")}">${opts(p.candidates.filter((c) => c.line !== t.detailed_type))}</optgroup>
    </select></div>
    <div class="actions"><button class="primary" id="map">${T("assign")}</button></div>
    <div class="field">${T("orNew")}</div>
    <div class="field">${T("colorName")}<input id="np-name"></div>
    <div class="field">${T("bambuNo")}<input id="np-no" inputmode="numeric"></div>
    <div class="actions"><button id="create">${T("create")}</button></div>
    ${p.msg ? `<div class="msg err">${esc(p.msg)}</div>` : ""}${tagDetails(t)}`;
  highlight(null);
  const send = async (body) => {
    try { handleScan(await api("/api/map", { method: "POST", body: { tag: t, ...body } })); }
    catch (e) { panel.msg = e.message; render(); }
  };
  $("#map").onclick = () => send({ product_id: Number($("#prod").value) });
  $("#create").onclick = () => {
    const name = $("#np-name").value.trim();
    if (!name) return toast(T("needName"));
    send({ new_product: { line: t.detailed_type, color_name: name, bambu_no: $("#np-no").value.trim() } });
  };
}

function handleScan(r) {
  pick = null; markPick();
  if (view !== "storage") showView("storage");
  if (r.kind === "known") showSpool(r.spool, r.tag, "", "known");
  else if (r.kind === "linked") showSpool(r.spool, r.tag, () => esc(T("linked")), "linkedNote");
  else if (r.kind === "new") { panel = { kind: "new", tag: r.tag, product: r.product, ...r.proposal }; render(); }
  else if (r.kind === "duplicate") { panel = null; render(); ask(tr(r.msg), { title: title(r.product), noCancel: true, warn: true }); }
  else if (r.kind === "unmapped") { panel = { kind: "unmapped", tag: r.tag, candidates: r.candidates }; render(); }
  else if (r.kind === "plain") { panel = { kind: "plain", tag: r.tag, unlinked: r.unlinked, msg: r.msg ? tr(r.msg) : "" }; render(); }
}

// ------------------------------------------------------------ clicks, search, live updates
document.addEventListener("click", async (e) => {
  const target = e.target.closest("[data-slot], [data-spool]");
  if (!target || !target.closest("#storage, #ams, .pext")) return;
  if (selMode && target.closest("#storage")) {
    const sid = e.target.closest("[data-spool]")?.dataset.spool;
    if (sid) { sel.has(sid) ? sel.delete(sid) : sel.add(sid); markSel(); }
    return;
  }
  if (pick) {
    const slotEl = e.target.closest("[data-slot]");
    if (!slotEl) return;
    const p = pick, sid = slotEl.dataset.slot;
    const other = p.swapFor && slotEl.matches(".slot:not(.free)") && overview.slots.find((x) => x.id === sid)?.spools.find((o) => o.in_cabinet);
    if (other && other.id !== p.swapFor.id) {
      const a = p.swapFor;
      if (!await askConfirm(L("Swap {0} ({1}) and {2} ({3})?", `${a.line} ${cname(a)}`, a.slot_id || "–", `${other.line} ${cname(other)}`, sid),
        { title: L("Place is taken"), ok: L("Swap") })) return;      // stays in pick mode: another slot can be chosen
      pick = null; markPick();
      try { await spoolAction(a, "swapwith:" + other.id); } catch (err) { toast(tr(err.message)); }
      return;
    }
    pick = null; markPick();
    try { await p.onPick(sid); } catch (err) { toast(err.message); }
    return;
  }
  const spoolId = e.target.closest("[data-spool]")?.dataset.spool;
  if (spoolId) showSpool(await api(`/api/spools/${spoolId}`));
});

let searchT;
$("#q").addEventListener("input", () => {
  clearTimeout(searchT);
  searchT = setTimeout(async () => {
    const q = $("#q").value, ul = $("#results");
    if (!q.trim()) { ul.hidden = true; highlight(null); return; }
    const res = await api(`/api/search?q=${encodeURIComponent(q)}`);
    const own = res.spools.map((s) => `<li data-id="${s.id}">${sw(s)}<span>${title(s)}
      <span class="sub">${esc(s.bambu_no ?? "")}${s.status === "in_use" ? " · " + T("in_use") : ""}</span></span>
      <span class="loc">${esc(s.slot_id ?? "–")}</span></li>`);
    const miss = res.missing.map((p) => `<li class="miss">${sw(p)}<span>${title(p)}
      <span class="sub">${esc(p.bambu_no ?? "")}</span></span><span class="loc sub">${T("notOwned")}</span></li>`);
    ul.innerHTML = own.concat(miss).join("") || `<li class="sub">${T("nothing")}</li>`;
    ul.hidden = false;
    // only one hit: jump to its slot; several: the user picks one from the list
    if (res.spools.length === 1) highlight(res.spools[0].slot_id, true, res.spools[0].id); else highlight(null);
  }, 150);
});
$("#results").addEventListener("click", async (e) => {
  const li = e.target.closest("li[data-id]");
  if (!li) return;
  $("#results").hidden = true;
  if (view !== "storage") showView("storage");
  showSpool(await api(`/api/spools/${li.dataset.id}`));
});
// short placeholder at rest, the full hint while the field has focus
$("#q").addEventListener("focus", () => { $("#q").placeholder = T("searchLong"); sizeSearch(); });
// medium widths: the opened field covers exactly the bar next to it (magnifier up to the end of the tabs)
function sizeSearch() {
  const s = $(".search"), n = $("#nav"), w = n.getBoundingClientRect().right - s.getBoundingClientRect().left;
  if (w > 200) s.style.setProperty("--grp", Math.round(w) + "px");
}
addEventListener("resize", () => sizeSearch());
$("#q").addEventListener("blur", () => { $("#q").placeholder = T("search"); });
// clearing the search (× button or Esc): empty field, no results, no highlighted slot, field closed
function clearSearch() {
  clearTimeout(searchT); $("#q").value = ""; $("#results").hidden = true; $("#qclear").hidden = true; highlight(null); $("#q").blur();
}
$("#q").addEventListener("keydown", (e) => { if (e.key === "Escape") clearSearch(); });
$("#q").addEventListener("input", () => { $("#qclear").hidden = !$("#q").value; });
$("#qclear").addEventListener("pointerdown", (e) => e.preventDefault());   // keep the focus until the click (the field would collapse first)
$("#qclear").onclick = clearSearch;
// Cmd/Ctrl+K or "/" opens the search from anywhere ("/" only when not typing in a field)
const typing = (el) => el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("#q").focus(); return; }
  if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey && !typing(document.activeElement) && !document.querySelector(".dlgwrap")) {
    e.preventDefault(); $("#q").focus();
  }
});
// arrow keys move through the search results, Enter opens the marked one
$("#q").addEventListener("keydown", (e) => {
  const ul = $("#results"); if (ul.hidden || !["ArrowDown", "ArrowUp", "Enter"].includes(e.key)) return;
  const items = [...ul.querySelectorAll("li[data-id], li.miss")]; if (!items.length) return;
  let i = items.findIndex((li) => li.classList.contains("kbd"));
  if (e.key === "Enter") { if (i >= 0 && items[i].dataset.id) { e.preventDefault(); items[i].click(); } return; }
  e.preventDefault();
  i = e.key === "ArrowDown" ? (i + 1) % items.length : (i <= 0 ? items.length - 1 : i - 1);
  items.forEach((li, k) => li.classList.toggle("kbd", k === i));
  items[i].scrollIntoView({ block: "nearest" });
});

function setReader(r) {
  const el = $("#reader"), cls = { ready: "ok", disconnected: "bad", missing: "bad" }[r.status] || "";
  el.textContent = L(I18N.en.reader[r.status] || r.status); el.className = `pill ${cls}`; el.title = tr(r.detail || "");
  if (overview) { overview.reader = { ...overview.reader, ...r }; drawReaderTool(); drawStats(); wizSync(); }
}

function connectLive() {
  const es = new EventSource("/api/events");
  es.onmessage = async (m) => {
    const msg = JSON.parse(m.data);
    if (msg.type === "reader") setReader(msg);
    if (msg.type === "scan") { beep(true); await refresh(); handleScan(msg.result); }
    if (msg.type === "readerror") { beep(false); if (readerTest.on) showTestScan(null, msg.detail); }
    if (msg.type === "testscan") { beep(true); showTestScan(msg.tag); }
    if (msg.type === "toast") { beep(false); toast(tr(msg.text)); }
    if (msg.type === "changed") await refresh();
    if (msg.type === "notices") setBell(msg);
    if (msg.type === "audit") {
      if (msg.last && JSON.stringify(msg.last) !== JSON.stringify(audit.last)) beep(msg.last.kind === "ok");
      if (msg.last && JSON.stringify(msg.last) !== JSON.stringify(audit.last)) auditAuto = true;
      audit = msg; drawAudit();
    }
    if (msg.type === "batch") {
      const before = batch?.items?.length ?? 0, after = msg.items?.length ?? 0;
      if (msg.active && msg.dup) beep(false); else if (msg.active && after > before) beep(true);
      batch = msg; drawBatch(); if (msg.dup) toast(T("batchDup"));
    }
  };
  es.onerror = () => setReader({ status: "disconnected", detail: T("offline") });
}

$("#logfold").onclick = () => { logOpen = !logOpen; setPref("logOpen", logOpen ? "1" : "0"); $("#logwrap").classList.toggle("open", logOpen); };
$("#logwrap").classList.toggle("open", logOpen);
document.addEventListener("click", (e) => { const b = e.target.closest(".cabmode [data-mode], #viewtool [data-mode]"); if (b) {
  // "Grid" next to a small cabinet keeps the compact/detail choice of the wide cabinets
  cabMode = b.dataset.mode === "compact" && b.closest(".nodetail") ? (cabMode === "list" ? pref("cabGrid", "compact") : cabMode) : b.dataset.mode; setPref("cabMode", cabMode); if (cabMode !== "list") setPref("cabGrid", cabMode); drawStorage(); } });
// ------------------------------------------------------------ scan sound
// played as an <audio> WAV so iOS plays it even with the mute switch on and after locking.
function chimeWav(ok) {
  const rate = 44100, notes = ok ? [[1047, 0, 0.18], [1319, 0.09, 0.18], [1568, 0.18, 0.2], [2093, 0.28, 0.5]]
                                 : [[440, 0, 0.25], [311, 0.22, 0.45]];
  const len = Math.ceil(rate * (ok ? 0.85 : 0.75)), buf = new Float32Array(len);
  for (const [f, t, d] of notes) {
    const s0 = Math.floor(t * rate), n = Math.floor(d * rate);
    for (let i = 0; i < n && s0 + i < len; i++) {
      const x = i / rate, env = Math.min(1, x / 0.01) * Math.exp(-x * (ok ? 7 : 6));
      const w = ok ? (2 / Math.PI) * Math.asin(Math.sin(2 * Math.PI * f * x)) : Math.sign(Math.sin(2 * Math.PI * f * x)) * 0.5;
      buf[s0 + i] += env * (0.75 * w + 0.2 * Math.sin(4 * Math.PI * f * x));
    }
  }
  const peak = Math.max(...buf.map(Math.abs)) || 1, data = new DataView(new ArrayBuffer(44 + len * 2));
  const str = (o, t) => [...t].forEach((c, i) => data.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF"); data.setUint32(4, 36 + len * 2, true); str(8, "WAVEfmt "); data.setUint32(16, 16, true);
  data.setUint16(20, 1, true); data.setUint16(22, 1, true); data.setUint32(24, rate, true); data.setUint32(28, rate * 2, true);
  data.setUint16(32, 2, true); data.setUint16(34, 16, true); str(36, "data"); data.setUint32(40, len * 2, true);
  for (let i = 0; i < len; i++) data.setInt16(44 + i * 2, Math.max(-1, Math.min(1, buf[i] / peak * 0.95)) * 32767, true);
  return URL.createObjectURL(new Blob([data], { type: "audio/wav" }));
}
// notifications: two soft rising sine tones, clearly different from the low falling error buzz
function noticeWav() {
  const rate = 44100, notes = [[784, 0, 0.35], [1175, 0.14, 0.6]], len = Math.ceil(rate * 0.8), buf = new Float32Array(len);
  for (const [f, t, d] of notes) {
    const s0 = Math.floor(t * rate), n = Math.floor(d * rate);
    for (let i = 0; i < n && s0 + i < len; i++) {
      const x = i / rate, env = Math.min(1, x / 0.015) * Math.exp(-x * 5);
      buf[s0 + i] += env * (Math.sin(2 * Math.PI * f * x) + 0.15 * Math.sin(4 * Math.PI * f * x));
    }
  }
  const peak = Math.max(...buf.map(Math.abs)) || 1, data = new DataView(new ArrayBuffer(44 + len * 2));
  const str = (o, t) => [...t].forEach((c, i) => data.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF"); data.setUint32(4, 36 + len * 2, true); str(8, "WAVEfmt "); data.setUint32(16, 16, true);
  data.setUint16(20, 1, true); data.setUint16(22, 1, true); data.setUint32(24, rate, true); data.setUint32(28, rate * 2, true);
  data.setUint16(32, 2, true); data.setUint16(34, 16, true); str(36, "data"); data.setUint32(40, len * 2, true);
  for (let i = 0; i < len; i++) data.setInt16(44 + i * 2, Math.max(-1, Math.min(1, buf[i] / peak * 0.7)) * 32767, true);
  return URL.createObjectURL(new Blob([data], { type: "audio/wav" }));
}
const sounds = { ok: new Audio(chimeWav(true)), err: new Audio(chimeWav(false)), note: new Audio(noticeWav()) };
Object.values(sounds).forEach((a) => { a.preload = "auto"; a.setAttribute("playsinline", ""); });
try { if (navigator.audioSession) navigator.audioSession.type = "playback"; } catch (e) {}
let audioUnlocked = false;
function unlockAudio() {   // iOS only allows sound after a touch – play it muted once
  if (audioUnlocked) return;
  audioUnlocked = true;
  for (const a of Object.values(sounds)) {
    a.muted = true;
    a.play().then(() => { a.pause(); a.currentTime = 0; a.muted = false; }).catch(() => { a.muted = false; audioUnlocked = false; });
  }
}
["pointerdown", "touchend", "click", "keydown"].forEach((ev) => document.addEventListener(ev, unlockAudio, { passive: true }));
function beep(ok, force = false) {
  if (!force && pref("sound", "on") !== "on") return Promise.resolve();
  const a = sounds[ok === "note" ? "note" : ok ? "ok" : "err"];   // true, false or "note"
  try { a.pause(); a.currentTime = 0; a.volume = 1; a.muted = false; return a.play(); } catch (e) { return Promise.reject(e); }
}
$("#soundtest").onclick = () => {
  beep(true, true).then(() => { $("#soundinfo").textContent = L("Sound played. Heard nothing? Check your device's volume and whether it is muted."); })
    .catch((e) => { $("#soundinfo").textContent = L("The browser blocks the sound:") + " " + (e && (e.name + " " + e.message)); });
};
document.querySelectorAll("[data-sound]").forEach((b) => (b.onclick = () => {
  setPref("sound", b.dataset.sound); unlockAudio(); markSound(); if (b.dataset.sound === "on") setTimeout(() => beep(true), 50);
}));
function markSound() { document.querySelectorAll("[data-sound]").forEach((b) => b.classList.toggle("on", b.dataset.sound === pref("sound", "on"))); }
markSound();

// ------------------------------------------------------------ shopping list, drying, usage
const shopUrl = (p) => p.brand
  ? (p.shop_url || "https://www.google.com/search?q=" + encodeURIComponent(`${p.line} ${p.color_name || ""} filament`))
  : "https://eu.store.bambulab.com/search?q=" + encodeURIComponent(`${p.line} ${p.name_en || p.color_name || ""}`);
const chipP = (p, extra = "", unnote = false, note = false) => `<li>${sw(p)}<span class="grow">${esc(p.line)} ${esc(cname(p))} <span class="sub">${esc(p.bambu_no ?? "")}${extra}</span></span>
  ${p.discontinued ? `<span class="discmark" title="${esc(L("Bambu Lab no longer sells this color"))}">${L("no longer available")}</span>` : `<a class="btn small" href="${shopUrl(p)}" target="_blank" rel="noopener">${L("Shop")}</a>`}${unnote ? `<span class="qty" role="group" aria-label="${esc(L("Number of spools"))}"><button class="small" data-qty="${p.id}" data-d="-1" title="${esc(p.qty > 1 ? L("One less") : L("Remove from shopping list"))}" aria-label="${esc(p.qty > 1 ? L("One less") : L("Remove from shopping list"))}">${p.qty > 1 ? "−" : "×"}</button><b>${p.qty || 1}</b><button class="small" data-qty="${p.id}" data-d="1" title="${esc(L("One more"))}" aria-label="${esc(L("One more"))}">+</button></span>` : ""}${note ? `<button class="small" data-note="${p.id}" title="${esc(L("Add to shopping list"))}" aria-label="${esc(L("Add to shopping list"))}">+</button>` : ""}</li>`;
const isNoted = (pid) => !!insights?.shopping?.noted?.some((p) => p.id === pid);
async function setNoted(pid, on) {
  try { insights = await api("/api/shoplist", { method: "POST", body: { product_id: pid, on } }); drawInsights(); drawCatalog();
        toast(L(on ? "Added to the shopping list" : "Removed from the shopping list")); }
  catch (e) { toast(e.message); }
}
// minimum stock per color (Options › shopping list): below it the color goes on the shopping list
const minStock = (pid) => +(SET().min_stock?.[String(pid)] || 0);
async function askMinStock(pid, name) {
  const cur = minStock(pid);
  const v = await ask(L("How many spools of {0} do you always want to have? Below that number the color goes on the shopping list. 0 = only when the last spool is used up.", name),
    { input: { inputmode: "numeric", value: String(cur) }, ok: L("Save"), title: L("Minimum stock") });
  if (v === null) return false;
  const n = parseInt(String(v).trim() || "0", 10);
  if (isNaN(n) || n < 0 || n > 99) { toast(L("Please enter a number from 0 to 99.")); return false; }
  try { insights = await api("/api/minstock", { method: "POST", body: { product_id: pid, n } }); await refresh(); toast(L("Saved")); return true; }
  catch (e) { toast(e.message); return false; }
}
function foldHead(id, title, sum, open) {
  return `<h3 class="fold" id="${id}">${title} <span class="sub foldsum">${sum}</span><span class="chev">›</span></h3>`;
}
function drawInsights() {
  if (!insights) return;
  drawToday();
  // drying (storage view)
  const dry = insights.drying, dn = $("#drynote");
  dn.hidden = !dry.length;
  dn.classList.toggle("open", dryOpen);
  dn.innerHTML = foldHead("dryfold", L("Drying recommended"), T("spools", dry.length)) +
    `<div class="foldbody">` + dry.map((sp) => `<span class="chip" data-spool="${sp.id}">${sw(sp)}${title(sp)} · ${L("open for {0} days", sp.open_days)}</span>`).join("") + `</div>`;
  $("#dryfold").onclick = () => { dryOpen = !dryOpen; dn.classList.toggle("open", dryOpen); };
  // shopping list (colors view)
  const sh = insights.shopping, noted = sh.noted || [], below = sh.below_min || [], n = noted.length + below.length + sh.low.length + sh.used_up.length + sh.missing.length, se = $("#shopping");
  const onList = noted.length + below.length;   // the count in the heading: colors put on the list and below their minimum, not the suggestions
  se.classList.toggle("open", shopOpen);
  se.innerHTML = foldHead("shopfold", L("Shopping list"), onList ? Lp(onList, "{0} item", "{0} items") : L("list is empty")) + `<div class="foldbody">` +
    `<p class="sub">${L("{0} empty spools available – enough for that many refills.", SET().empty_spools ?? 0)}</p>` +
    (noted.length ? `<h4>${L("Noted by you")}</h4><ul class="shop">${noted.map((p) => chipP(p, "", true)).join("")}</ul>` : "") +
    (below.length ? `<h4>${L("Below your minimum stock")}</h4><ul class="shop">${below.map((p) => chipP(p, " · " + L("{0} of {1} in stock", p.have, p.want))).join("")}</ul>` : "") +
    (sh.low.length ? `<h4>${L("Almost empty, no spare spool")}</h4><ul class="shop">${sh.low.map((p) => chipP(p, " · " + L("{0} % remaining", p.remain_pct) + (reachText(p.product_id) ? " · " + L("lasts {0}", reachText(p.product_id)) : ""))).join("")}</ul>` : "") +
    (sh.used_up.length ? `<h4>${L("Used up")}</h4><ul class="shop">${sh.used_up.map((p) => chipP(p)).join("")}</ul>` : "") +
    (sh.missing.length ? `<div class="subfold ${missOpen ? "open" : ""}" id="missbox"><h4 class="fold" id="missfold">${L("Missing from your collection lines")} <span class="sub foldsum">${sh.missing.length}</span><span class="chev">›</span></h4>
      <ul class="shop">${sh.missing.map((p) => chipP(p, "", false, true)).join("")}</ul></div>` : "") +
    (n ? "" : `<p class="sub">${L("The list is empty. Tap a color in the catalog to add it. Lines you want to have complete can be set under Options.")}</p>`) + `</div>`;
  $("#shopfold").onclick = () => { shopOpen = !shopOpen; setPref("shopFold", shopOpen ? "1" : "0"); se.classList.toggle("open", shopOpen); };
  const mf = $("#missfold");
  if (mf) mf.onclick = () => { missOpen = !missOpen; $("#missbox").classList.toggle("open", missOpen); };
  se.querySelectorAll("[data-note]").forEach((b) => (b.onclick = () => setNoted(+b.dataset.note, true)));
  se.querySelectorAll("[data-qty]").forEach((b) => (b.onclick = async () => {
    const pid = +b.dataset.qty, cur = noted.find((x) => x.id === pid)?.qty || 1, n = cur + +b.dataset.d;
    if (n < 1) return setNoted(pid, false);
    try { insights = await api("/api/shoplist", { method: "POST", body: { product_id: pid, on: true, qty: Math.min(99, n) } }); drawInsights(); }
    catch (e) { toast(tr(e.message)); }
  }));
  // usage (colors view)
  const u = insights.usage, ue = $("#usage"), max = Math.max(1, ...u.months.map((m) => m.grams));
  const total30 = u.top30.reduce((a, p) => a + p.grams, 0);
  ue.classList.toggle("open", usageOpen);
  ue.innerHTML = foldHead("usagefold", L("Usage"), u.since ? L("{0} in 30 days", gkg(total30)) : L("no data yet")) + `<div class="foldbody">` +
    (u.since ? `<div class="months">${u.months.map((m) => `<div class="mbar"><i style="height:${(100 * m.grams / max).toFixed(0)}%"></i><b>${m.grams ? gkg(m.grams) : ""}</b><span>${m.month.slice(5)}/${m.month.slice(2, 4)}</span></div>`).join("")}</div>
      <h4>${L("Most used (30 days)")}</h4><ul class="shop">${u.top30.map((p) => `<li>${sw(p)}<span class="grow">${esc(p.line)} ${esc(cname(p))}</span><b>${gkg(p.grams)}</b></li>`).join("") || `<li class="sub">–</li>`}</ul>
      <p class="sub">${L("Calculated from the AMS percentages since {0}.", esc(u.since.slice(0, 10)))}</p>`
      : `<p class="sub">${L("Recorded from the AMS percentages from now on.")}</p>`) + `</div>`;
  $("#usagefold").onclick = () => { usageOpen = !usageOpen; ue.classList.toggle("open", usageOpen); };
}

// ------------------------------------------------------------ options
function applyTheme() {
  const t = pref("theme", "system");
  if (t === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  document.querySelectorAll("[data-theme-opt]").forEach((b) => b.classList.toggle("on", b.dataset.themeOpt === t));
}
// crossfade between light and dark instead of a hard switch (browsers without view transitions just switch)
function switchTheme(fn) {
  if (!document.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) return fn();
  document.startViewTransition(fn);
}
document.querySelectorAll("[data-theme-opt]").forEach((b) => (b.onclick = () => switchTheme(() => { setPref("theme", b.dataset.themeOpt); applyTheme(); })));
applyTheme();
// Navigation layout ("auto"), after Apple's HIG:
//  - iPhone Duo unfolded in landscape and phones in landscape (701px+): vertical controls at the side (rail)
//  - iPad and other tablets: rail at the right in landscape, tab bar at the top in portrait
//  - wide phone screens in portrait (iPhone Duo unfolded, 560-700px): tab bar at the top as a row (toptabs)
//  - narrow phones in portrait (iPhone Duo folded, iPhone Air): hamburger menu
// The rail can be forced on or off in the options. PCs never get it automatically.
const UA = navigator.userAgent;
const RAIL_AUTO = ["(horizontal-viewport-segments: 2)", "(orientation: landscape)", "(max-height: 560px)"].map((q) => matchMedia(q));
const TOUCH_DEVICE = navigator.maxTouchPoints > 0 && !/Windows|CrOS|Linux x86_64/.test(UA) && /iPad|iPhone|Android|Macintosh/.test(UA);
const PHONE = /iPhone|iPod/.test(UA) || /Android.*Mobile/.test(UA);
function railWanted() {
  if (RAIL_AUTO[0].matches) return true;
  return TOUCH_DEVICE && RAIL_AUTO[1].matches && (!PHONE || innerWidth >= 701);
}
function applyRail() {
  const p = pref("navrail", "auto");
  const on = p === "on" || (p === "auto" && railWanted());
  document.body.classList.toggle("rail", on);
  document.body.classList.toggle("railicons", on && (TOUCH_DEVICE || PHONE || RAIL_AUTO[2].matches || innerWidth < 701));
  document.body.classList.toggle("toptabs", !on && TOUCH_DEVICE && PHONE && !RAIL_AUTO[1].matches && innerWidth >= 560 && innerWidth <= 700);
  if (on) document.body.classList.remove("navopen");
  document.querySelectorAll("#nav [data-view]").forEach((b) => (b.title = b.querySelector("span")?.textContent.trim() || ""));
  document.querySelectorAll("[data-rail-opt]").forEach((b) => b.classList.toggle("on", b.dataset.railOpt === p));
  requestAnimationFrame(() => moveTabKnob(false));
}
RAIL_AUTO.forEach((m) => m.addEventListener?.("change", applyRail));
let railT; addEventListener("resize", () => { clearTimeout(railT); railT = setTimeout(applyRail, 150); });
document.querySelectorAll("[data-rail-opt]").forEach((b) => (b.onclick = () => { setPref("navrail", b.dataset.railOpt); applyRail(); }));
applyRail();
function fillSettings() {
  const st = SET(), set = (id, v) => { const e = $(id); if (e && document.activeElement !== e) e.value = v; };
  if (!cabDraft && !$("#cabeditor").contains(document.activeElement)) drawCabEditor();
  document.querySelectorAll("[data-cam]").forEach((b) => b.classList.toggle("on", b.dataset.cam === (st.camera || "off")));
  $("#datefmt").value = st.date_fmt || "auto";
  document.querySelectorAll("[data-tf]").forEach((b) => b.classList.toggle("on", b.dataset.tf === String(st.time_fmt || "auto")));
  document.querySelectorAll("[data-haon]").forEach((b) => b.classList.toggle("on", (b.dataset.haon === "1") === (st.ha_on !== false)));
  let wizOpen = false; try { wizOpen = wiz.open; } catch (e) { /* wizard not set up yet */ }
  $("#haFields").hidden = st.ha_on === false && !wizOpen;   // switched off: no input fields (the wizard has no switch)
  document.querySelectorAll("[data-upc]").forEach((b) => b.classList.toggle("on", (b.dataset.upc === "1") === (st.update_check !== false)));
  document.querySelectorAll("[data-upch]").forEach((b) => b.classList.toggle("on", b.dataset.upch === (st.update_channel || "off")));
  document.querySelectorAll("[data-logdet]").forEach((b) => b.classList.toggle("on", (b.dataset.logdet === "1") === !!st.log_detail));
  document.querySelectorAll("[data-upa]").forEach((b) => b.classList.toggle("on", (b.dataset.upa === "1") === (st.auto_security !== false)));
  if (!$("#climatecfg").contains(document.activeElement)) drawClimateCfg();
  $("#spoolcount").textContent = st.empty_spools ?? 0; drawReaderTool(); drawBambuInfo(); drawOptSums(); drawHost();
  set("#setTight", st.tight_pct ?? 15); set("#setMinAll", st.min_stock_all ?? 0); set("#setAmsHum", st.ams_hum_max ?? 0); set("#setReturn", st.return_min ?? 0);
  set("#setDryDry", st.dry_weeks_dry); set("#setDryOther", st.dry_weeks_other);
  document.querySelectorAll("[data-dryon]").forEach((b) => b.classList.toggle("on", (b.dataset.dryon === "1") === (st.dry_on !== false)));
  $("#dryfields").hidden = st.dry_on === false;
  if (allLines && !$("#collectlines").dataset.filled) {
    $("#collectlines").innerHTML = allLines.map((l) => `<label class="check"><input type="checkbox" value="${esc(l)}" ${(st.collect_lines || []).includes(l) ? "checked" : ""}> ${esc(l)}</label>`).join("");
    $("#collectlines").dataset.filled = "1";
  }
  set("#setScanPause", (st.scan_pause_ms ?? 500) / 1000);
  set("#setLogRows", st.log_rows ?? 5);
  set("#setLow", st.low_remain_pct); set("#setKeep", st.backup_keep_days); set("#setPoll", st.ha_poll_seconds);
  const ha = overview?.ha || {};
  // nothing to report as long as Home Assistant is not set up
  $("#haInfo").textContent = ha.detail === "not set up (optional)" ? "" : L("Status: {0}", L(ha.status ?? "–")) + (ha.detail ? " · " + tr(ha.detail) : "");
}
async function saveSettings(patch) {
  try { overview.settings = await api("/api/settings", { method: "PUT", body: patch }); applyLang(); drawStorage(); fillSettings(); toast(L("Saved")); }
  catch (e) { toast(e.message); }
}
// ------------------------------------------------------------ cabinet layout editor
let cabDraft = null;   // working copy while there are unapplied changes
function cabEdits() { return cabDraft || JSON.parse(JSON.stringify(CABS())); }
function spoolsIn(key) { return (overview?.slots || []).filter((s) => s.cabinet === key).reduce((n, s) => n + s.spools.length, 0); }
function occupiedIn(key) { return (overview?.slots || []).filter((s) => s.cabinet === key && s.spools.length).length; }
// in the setup assistant "Next" saves, so there is no "not applied yet" note there
function notApplied() { $("#cabmsg").innerHTML = wiz.open ? "" : `<p class="sub">${L("Not applied yet.")}</p>`; }
// setup assistant on a new installation: the storage form starts empty instead of showing the default storage
function blankCabDraft() {
  const c = CABS();
  if (SET().setup_done || c.length !== 1 || (overview?.stats?.spools ?? 0) > 0) return;
  const d = c[0];
  if (d.code !== "S" || d.name !== "1" || d.rows !== 3 || d.per_row !== 6) return;
  cabDraft = [{ ...d, name: "", code: "", label: "", rows: "", per_row: "" }];
}
const cabFilled = (c) => c.name?.trim() && c.code?.trim() && +c.rows > 0 && +c.per_row > 0;
// required fields still empty: a pop-up names them per storage, the fields are marked and the first one gets the focus
async function cabMissingAsk() {
  const need = [["name", "Name"], ["code", "Code for slot codes"], ["rows", null], ["per_row", null]];
  const lab = (c, f) => f === "rows" ? L(c.unit === "level" ? "Number of levels" : "Number of rods")
    : f === "per_row" ? L(c.unit === "level" ? "Slots per level" : "Slots per rod") : L(need.find((x) => x[0] === f)[1]);
  const empty = (c, f) => f === "rows" || f === "per_row" ? !(+c[f] > 0) : !String(c[f] ?? "").trim();
  const list = cabEdits(), lines = [];
  list.forEach((c, i) => {
    const miss = need.map(([f]) => f).filter((f) => empty(c, f));
    if (!miss.length) return;
    lines.push(`<li><b>${esc(c.name?.trim() || L("Storage {0}", i + 1))}:</b> ${miss.map((f) => esc(lab(c, f))).join(", ")}</li>`);
    const box = $("#cabeditor").querySelector(`.cabedit[data-i="${i}"]`);
    miss.forEach((f) => box?.querySelector(`[data-f="${f}"]`)?.classList.add("missing"));
  });
  await ask(`<p>${esc(L("A few details are still missing:"))}</p><ul class="missinglist">${lines.join("")}</ul>`,
    { block: true, noCancel: true, title: L("Not complete yet"), ok: L("Fill in") });
  const first = $("#cabeditor").querySelector(".missing");
  if (first) { first.scrollIntoView({ block: "center", behavior: "smooth" }); first.focus({ preventScroll: true }); }
}
function drawCabEditor() {
  const list = cabEdits();
  $("#cabeditor").innerHTML = list.map((c, i) => {
    const sample = `${c.code || "?"}-${rowLab(c, 1)}-${c.per_row >= 10 ? "01" : "1"}`;
    const occ = c.key ? occupiedIn(c.key) : 0;
    return `<div class="cabedit" data-i="${i}">
      <div class="cehead"><b>${esc(c.name || L("New storage"))}</b><span class="sub">${cabFilled(c) ? L("{0} slots", c.rows * c.per_row) : ""}${cabFilled(c) && c.shelves ? " + " + Lp(c.shelves, "{0} reserve area", "{0} reserve areas") : ""}${occ ? " · " + L("{0} used", occ) : ""}</span>
        <button class="small danger" data-cedel="${i}" ${list.length < 2 ? "disabled" : ""}>${L("Delete")}</button></div>
      <div class="cegrid">
        <label>${L("Name")}<input data-f="name" value="${esc(c.name)}" maxlength="24" placeholder="${L("e.g. Cabinet")}"></label>
        <label>${L("Code for slot codes")}<input data-f="code" value="${esc(c.code)}" maxlength="3" autocapitalize="characters" placeholder="${L("e.g. S")}"></label>
        <label>${L("Purpose / label")}<input data-f="label" value="${esc(c.label || "")}" maxlength="24" placeholder="${L("e.g. PLA")}"></label>
        <label>${L("Divided into")}<select data-f="unit">${[["rod", "Rod"], ["level", "Level"]].map(([u, name]) => `<option value="${u}" ${c.unit === u ? "selected" : ""}>${L(name)}</option>`).join("")}</select></label>
        <label>${L(c.unit === "level" ? "Number of levels" : "Number of rods")}<input data-f="rows" type="number" min="1" max="26" inputmode="numeric" value="${c.rows}" placeholder="${L("e.g. {0}", 3)}"></label>
        <label>${L(c.unit === "level" ? "Slots per level" : "Slots per rod")}<input data-f="per_row" type="number" min="1" max="40" inputmode="numeric" value="${c.per_row}" placeholder="${L("e.g. {0}", 6)}"></label>
        <label>${L("Numbering")}<select data-f="numbering"><option value="num" ${c.numbering !== "alpha" ? "selected" : ""}>1, 2, 3 …</option><option value="alpha" ${c.numbering === "alpha" ? "selected" : ""}>A, B, C …</option></select></label>
        <label>${L("Reserve areas")}<input data-f="shelves" type="number" min="0" max="9" inputmode="numeric" value="${c.shelves}"></label>
        <label>${L(c.unit === "level" ? "Divider above level" : "Divider above rod")}<select data-f="lower_from"><option value="0">${L("no divider")}</option>${Array.from({ length: c.rows - 1 }, (_, k) => k + 2).map((r) => `<option value="${r}" ${c.lower_from === r ? "selected" : ""}>${rowLab(c, r)}</option>`).join("")}</select></label>
        <span class="chk"><label><input type="checkbox" data-f="dry" ${c.dry ? "checked" : ""}> ${L("Dry zone")}</label><button type="button" class="helpq" data-dryhelp aria-label="${esc(L("What is a dry zone?"))}">i</button></span>
      </div>
      <div class="ceprev"${cabFilled(c) ? "" : " hidden"}>${L("Slot codes:")} ${esc(sample)} … ${esc(`${c.code || "?"}-${rowLab(c, c.rows)}-${c.per_row >= 10 ? String(c.per_row).padStart(2, "0") : c.per_row}`)}${c.shelves ? ` · ${L("Reserve")} Ü-${esc(c.code || "?")}1` : ""}</div>
    </div>`;
  }).join("");
  $("#cabeditor").querySelectorAll("[data-f]").forEach((el) => (el.onchange = () => {
    const d = cabEdits(), i = +el.closest(".cabedit").dataset.i, f = el.dataset.f;
    d[i][f] = el.type === "checkbox" ? el.checked : el.type === "number" && el.value === "" ? "" : el.type === "number" || f === "lower_from" ? +el.value : f === "code" ? el.value.toUpperCase().trim() : el.value;
    cabDraft = d; drawCabEditor(); notApplied();
  }));
  $("#cabeditor").querySelectorAll("[data-dryhelp]").forEach((b) => (b.onclick = () => ask(`<p>${esc(L("Mark a storage as dry zone if it is kept especially dry, e.g. a closed box with desiccant."))}</p>
    <p>${esc(L("PixxelSpool then suggests it for materials that absorb moisture quickly, such as PETG, TPU, ABS, ASA and PA. PLA goes to the other storages."))}</p>`,
    { block: true, noCancel: true, title: L("Dry zone"), ok: L("Got it") })));
  $("#cabeditor").querySelectorAll("[data-cedel]").forEach((b) => (b.onclick = () => {
    const d = cabEdits(), c = d[+b.dataset.cedel];
    const n = c.key ? spoolsIn(c.key) : 0;
    if (n) { alert(L("“{0}” still holds {1} spools. Move them to another slot or check them out first, then the storage can be deleted.", c.name || c.code, n)); return; }
    d.splice(+b.dataset.cedel, 1); cabDraft = d; drawCabEditor(); notApplied();
  }));
}
// "?" next to the storage intro: what a storage is, with two drawn examples
const HELP_COLORS = ["#e5484d", "#f5a524", "#f2d544", "#46a758", "#12a594", "#3e82f7", "#8e4ec6", "#e93d82", "#8d6e63", "#f4f4f2", "#2b2b2b", "#9aa0a6"];
function helpSpool(x, y, r, i) {
  return `<g class="hsp"><circle cx="${x}" cy="${y}" r="${r}" fill="${HELP_COLORS[i % HELP_COLORS.length]}"/>` +
    `<circle class="hub" cx="${x}" cy="${y}" r="${(r * 0.45).toFixed(2)}"/><circle class="hole" cx="${x}" cy="${y}" r="${(r * 0.17).toFixed(2)}"/></g>`;
}
function cabHelpPic(kind) {
  if (kind === "rod") {
    let out = `<rect class="wall" x="6" y="4" width="248" height="8" rx="2"/>` +
      `<path class="bracket" d="M20 12v16M240 12v16"/><path class="rod" d="M14 28h232"/>`;
    for (let i = 0; i < 8; i++) out += helpSpool(36 + i * 27, 28, 11.5, i * 5 + 2);
    out += `<path class="dim" d="M24.5 50v4h223v-4"/><text class="dimt" x="136" y="66">8</text>`;
    return `<svg class="cabpic" viewBox="0 0 260 72" aria-hidden="true">${out}</svg>`;
  }
  const X = 30, W = 216, CW = W / 3, RH = 30, Y = 6;
  let out = `<rect class="body" x="${X}" y="${Y}" width="${W}" height="${RH * 3}" rx="5"/>`;
  for (let r = 1; r < 3; r++) out += `<path class="board" d="M${X} ${Y + r * RH}h${W}"/>`;
  for (let c = 1; c < 3; c++) out += `<path class="board" d="M${X + c * CW} ${Y}v${RH * 3}"/>`;
  for (let r = 0; r < 3; r++) {
    out += `<circle class="lvl" cx="13" cy="${Y + r * RH + RH / 2}" r="8.5"/><text class="lvlt" x="13" y="${Y + r * RH + RH / 2 + 3.6}">${r + 1}</text>`;
    for (let c = 0; c < 3; c++) for (let k = 0; k < 4; k++) out += helpSpool(X + c * CW + 11 + k * 16.6, Y + r * RH + RH / 2 + 1, 7.4, (r * 5 + c * 4 + k) * 7);
  }
  out += `<rect class="hl" x="${X - 3}" y="${Y - 3}" width="${W + 6}" height="${RH + 6}" rx="7"/>` +
    `<rect class="hlpill" x="${X + W + 6}" y="${Y + RH / 2 - 9}" width="24" height="18" rx="9"/><text class="hlt" x="${X + W + 18}" y="${Y + RH / 2 + 4}">12</text>` +
    `<path class="dim" d="M${X + 4} ${Y + RH * 3 + 6}v4h${CW - 8}v-4"/><text class="dimt" x="${X + CW / 2}" y="${Y + RH * 3 + 22}">4</text>`;
  return `<svg class="cabpic" viewBox="0 0 280 124" aria-hidden="true">${out}</svg>`;
}
$("#cabhelp").onclick = () => {
  ask(`<div class="cabhelp">
    <p>${L("A storage is any place where your spools have a fixed spot – a cabinet, a shelf unit or a rod on the wall. You choose the name.")}</p>
    <p>${L("You only need two numbers: how many <b>levels</b> it has (shelves, rows or rods, counted from the top) and how many spools fit on <b>one level</b>.")}</p>
    <h4>${L("Example: shelf unit with 3 × 3 compartments")}</h4>
    ${cabHelpPic("grid")}
    <p class="sub">${L("4 spools fit in each compartment, so one level holds 3 × 4 = 12. Enter: <b>3 levels</b>, <b>12 slots per level</b>.")}</p>
    <h4>${L("Example: a rod on the wall")}</h4>
    ${cabHelpPic("rod")}
    <p class="sub">${L("Enter: <b>1 level</b> with as many slots as spools fit on the rod, here <b>8</b>.")}</p>
    <h4>${L("Reserve")}</h4>
    <p class="sub">${L("Reserve areas hold spare spools of colors that already have a place in storage. They need no fixed slots or order and can be anywhere, e.g. a box in the basement. Enter 0 if you don't need one.")}</p>
  </div>`, { title: L("Setting up storage"), block: true, noCancel: true, ok: L("Got it") });
};
$("#cabadd").onclick = () => {
  const d = cabEdits();   // a new storage starts empty, like the first one in the setup assistant
  d.push({ key: "", code: "", name: "", label: "", unit: "level", rows: "", per_row: "", numbering: "num", shelves: 0, dry: false, lower_from: 0 });
  cabDraft = d; drawCabEditor(); notApplied();
};
$("#bkha").onchange = async () => {
  if ($("#bkha").checked && !await askConfirm(esc(L("The backup will then contain your credentials (Home Assistant token, printer access code) in plain text.")) +
    `<span class="dlgnote">${esc(L("Anyone who gets the file can read them. Keep it safe and don't share it."))}</span>`,
    { ok: L("Include"), warn: true, html: true, title: L("Include credentials?") })) $("#bkha").checked = false;
  $("#bkdl").href = "/api/backup/download" + ($("#bkha").checked ? "?ha=1" : "");
};
// Restore: pick one of the automatic backups on the Pi (nightly, before updates, before risky actions) or a file
const bkLabel = (b) => ({ nightly: () => L("Daily backup"), "before-update": () => L("Before the update to {0}", b.detail),
  "before-restore": () => L("Before restoring a backup"), "before-layout-change": () => L("Before changing the storage"),
  "before-delete": () => L("Before deleting a spool"), "before-audit": () => L("Before the stock check"),
  "before-reset": () => L("Before resetting the storage") }[b.kind] || (() => L("Automatic backup")))();
const bkWhen = (t) => { const d = new Date(t); return `${dateShort(t)} · ${fmtTime(d)}`; };
// after a restore: reload everything; started from the setup wizard, the wizard is done then
async function afterRestore() {
  cabDraft = null; await refresh();
  if (wiz.open) { showView("storage"); closeWizard(true); } else drawCabEditor();
  toast(L("Backup restored"));
}
async function restoreAuto(b) {
  if (!await askConfirm(L("Restore the backup from {0}? All spools and settings will be replaced by that state. The current state is backed up first.", bkWhen(b.time)), { ok: L("Restore"), danger: true })) return;
  try { await api("/api/backups/restore", { method: "POST", body: { name: b.name } }); await afterRestore(); }
  catch (e) { toast(tr(e.message)); }
}
$("#bkrestore").onclick = async () => {
  let list = [];
  try { list = await api("/api/backups"); } catch (e) { /* only the file choice then */ }
  let chosen = null;
  const items = list.map((b, i) => `<li><button class="bkitem" data-bk="${i}"><span class="bkico">${icon(b.kind === "nightly" ? "save" : b.kind === "before-update" ? "download" : "refresh")}</span>
      <span class="grow"><b>${esc(bkWhen(b.time))}</b><span class="sub">${esc(bkLabel(b))}</span></span><span class="chev">›</span></button></li>`).join("");
  const p = ask(`<div class="cabhelp bkpick">
      <p class="sub">${L("Automatic backups made by PixxelSpool, newest first. Or choose a backup file you downloaded.")}</p>
      ${list.length ? `<ul class="bklist">${items}</ul>` : `<p class="sub">${L("No automatic backups yet.")}</p>`}
    </div>`, { title: L("Restore backup"), block: true, ok: L("Choose file …") });
  document.querySelectorAll(".bklist [data-bk]").forEach((btn) => (btn.onclick = () => { chosen = list[+btn.dataset.bk]; btn.closest(".dlgwrap").querySelector("[data-dc]").click(); }));
  const r = await p;
  if (chosen) restoreAuto(chosen); else if (r) $("#bkfile").click();
};
// password-protected backup file: the download is made by the server and saved from here
$("#bklock").onchange = () => { $("#bkpwrow").hidden = !$("#bklock").checked; if ($("#bklock").checked) $("#bkpw").focus(); };
$("#bkdl").addEventListener("click", async (e) => {
  if (!$("#bklock").checked) return;
  e.preventDefault();
  try {
    const res = await fetch("/api/backup/download", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ha: $("#bkha").checked, password: $("#bkpw").value }) });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(tr(d.error || res.statusText)); }
    const name = (res.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || "PixxelSpool.pspbackup";
    const url = URL.createObjectURL(await res.blob());
    Object.assign(document.createElement("a"), { href: url, download: name }).click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    toast(L("Backup saved. Without the password it can't be restored."));
  } catch (err) { toast(err.message); }
});
$("#bkfile").onchange = async () => {
  const f = $("#bkfile").files[0]; $("#bkfile").value = ""; if (!f) return;
  if (!await askConfirm(L("Restore “{0}”? All spools and settings will be replaced by the state from the backup. PixxelSpool backs up the current state first.", f.name), { ok: L("Restore"), danger: true })) return;
  try {
    const send = (pw) => fetch("/api/backup/restore", { method: "POST", body: f,
      headers: { "Content-Type": "application/octet-stream", ...(pw ? { "X-Backup-Password": encodeURIComponent(pw) } : {}) } });
    let res = await send(""), data = await res.json().catch(() => ({}));
    if (data.need_password) {
      const pw = await ask(L("This backup is protected with a password. Please enter it."), { title: L("Password"), ok: L("Restore"), input: { value: "" } });
      if (!pw) return;
      res = await send(pw); data = await res.json().catch(() => ({}));
    }
    if (!res.ok) throw new Error(tr(data.error || data.detail || res.statusText));
    await afterRestore();
  } catch (e) { toast(e.message); }
};
$("#cabreset").onclick = () => { cabDraft = null; drawCabEditor(); $("#cabmsg").innerHTML = ""; };
async function applyCabs() {   // true when the layout was saved
  const b = $("#cabapply"); b.disabled = true; let ok = false;
  try {
    const res = await api("/api/layout", { method: "POST", body: { cabinets: cabEdits() } });
    if (!res.ok) {
      $("#cabmsg").innerHTML = `<div class="msg">${L("<b>Not possible yet:</b> these slots still hold spools and would be removed. Please move or remove these spools first:")}
        <ul>${res.blockers.map((x) => `<li><b>${esc(tr(x.slot))}</b> · ${esc(x.what)}</li>`).join("")}</ul></div>`;
      beep(false);
    } else {
      cabDraft = null; await refresh(); drawCabEditor();
      $("#cabmsg").innerHTML = `<p class="sub">${L("Applied: {0} slots renamed, {1} new, {2} removed. Backup: {3}", res.renamed, res.added, res.removed, esc(res.backup))}</p>`;
      toast(L("Storage updated")); ok = true;
    }
  } catch (e) { toast(e.message); }
  b.disabled = false;
  return ok;
}
$("#cabapply").onclick = () => applyCabs();
$("#saveMisc").onclick = () => saveSettings({ low_remain_pct: $("#setLow").value, tight_pct: $("#setTight").value, min_stock_all: $("#setMinAll").value,
  ams_hum_max: $("#setAmsHum").value, return_min: $("#setReturn").value }).then(() => refresh());
$("#setKeep").onchange = () => saveSettings({ backup_keep_days: $("#setKeep").value });
document.querySelectorAll("[data-spooldelta]").forEach((b) => (b.onclick = () => saveSettings({ empty_spools_delta: +b.dataset.spooldelta })));
// ------------------------------------------------------------ shareable spool card
const DEFAULTS = [  // typical values when the spool has no tag data yet
  [/^TPU/, { n: "220–240", b: 35, d: "70 °C · 8 h" }], [/^PETG|^PET/, { n: "230–260", b: 70, d: "65 °C · 8 h" }],
  [/^ABS|^ASA/, { n: "240–270", b: 90, d: "80 °C · 8 h" }], [/^Support/, { n: "190–220", b: 55, d: "55 °C · 8 h" }],
  [/^PLA/, { n: "190–230", b: 55, d: "55 °C · 8 h" }]];
function cardData(s) {
  let t = null; try { t = s.tag_json ? JSON.parse(s.tag_json) : null; } catch (e) {}
  if (t) return { nozzle: `${t.hotend_min_c}–${t.hotend_max_c} °C`, bed: `${t.bed_temp_c} °C`, dry: `${t.drying_temp_c} °C · ${t.drying_time_h} h`, approx: false };
  const d = (DEFAULTS.find(([re]) => re.test(s.line)) || [null, null])[1];
  return d ? { nozzle: `${d.n} °C`, bed: `${d.b} °C`, dry: d.d, approx: true } : { nozzle: "–", bed: "–", dry: "–", approx: true };
}
function shareCard(s) {
  const W = 1080, H = 1350, c = document.createElement("canvas"); c.width = W; c.height = H;
  const g = c.getContext("2d"), dark = "#1d1d1b", quiet = "#6b6a65";
  g.fillStyle = "#f6f5f2"; g.fillRect(0, 0, W, H);
  let cols = []; try { cols = JSON.parse(s.colors || "[]"); } catch (e) {}
  if (!cols.length) cols = [s.hex || "#cccccc"];
  // color area at the top
  const top = 560;
  cols.forEach((col, i) => { g.fillStyle = col.slice(0, 7); g.fillRect(i * W / cols.length, 0, W / cols.length + 1, top); });
  g.fillStyle = "rgba(255,255,255,.92)"; g.beginPath(); g.arc(W / 2, top, 150, 0, Math.PI * 2); g.fill();
  g.fillStyle = dark; g.beginPath(); g.arc(W / 2, top, 46, 0, Math.PI * 2); g.fill();
  g.textAlign = "center"; g.fillStyle = dark;
  g.font = "600 44px -apple-system, Helvetica, sans-serif"; g.fillText(s.line, W / 2, top + 230);
  g.font = "700 84px -apple-system, Helvetica, sans-serif"; g.fillText(cname(s), W / 2, top + 330);
  g.font = "500 40px -apple-system, Helvetica, sans-serif"; g.fillStyle = quiet;
  g.fillText([s.bambu_no, (s.hex || "").toUpperCase()].filter(Boolean).join("  ·  "), W / 2, top + 395);
  const d = cardData(s), rows = [[L("Nozzle"), d.nozzle], [L("Bed"), d.bed], [L("Drying"), d.dry],
    [L("Remaining"), s.remain_pct != null ? `${shownPct(s)} %` : (s.weight_g ? L("{0} g spool", s.weight_g) : "–")]];
  rows.forEach(([k, v], i) => {
    const x = 90 + (i % 2) * 470, y = top + 490 + Math.floor(i / 2) * 110;
    g.textAlign = "left"; g.fillStyle = quiet; g.font = "500 34px -apple-system, Helvetica, sans-serif"; g.fillText(k, x, y);
    g.fillStyle = dark; g.font = "700 46px -apple-system, Helvetica, sans-serif"; g.fillText(v, x, y + 52);
  });
  g.textAlign = "center"; g.fillStyle = quiet; g.font = "400 28px -apple-system, Helvetica, sans-serif";
  g.fillText("PixxelSpool by pixxelhoff", W / 2, H - 40);
  const url = c.toDataURL("image/png"), bin = atob(url.split(",")[1]), arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  const name = `${s.line} ${cname(s)}`.replace(/[^\w\-äöüÄÖÜß ]+/g, "").trim().replace(/ +/g, "-") + ".png";
  const file = new File([arr], name, { type: "image/png" });
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    navigator.share({ files: [file], title: `${s.line} ${cname(s)}` }).catch(() => {});
  } else {
    const a = document.createElement("a"); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  }
}

// ------------------------------------------------------------ project planner
let project = []; try { project = JSON.parse(pref("project", "[]")); } catch (e) {}
function spoolsOf(pid) { return (overview?.slots || []).flatMap((x) => x.spools).filter((s) => s.product_id === pid); }
function drawProject() {
  if (!products) return;
  const items = project.map((id) => products.find((p) => p.id === id)).filter(Boolean);
  const have = items.filter((p) => spoolsOf(p.id).length).length;
  $("#projsum").textContent = items.length ? L("{0}/{1} available", have, items.length) : "";
  $("#projlist").innerHTML = items.map((p) => {
    const sps = spoolsOf(p.id), main = sps.find((s) => s.ams_slot) || sps.find((s) => s.in_cabinet) || sps[0];
    const where = !main ? `<span class="bad">${L("missing")}</span>` :
      main.ams_slot ? `<b>${esc(amsWhere(main))}</b>` : `<b>${esc(main.slot_id ?? "–")}</b>${main.in_cabinet ? "" : " (" + L("reserve") + ")"}`;
    const rest = main && main.remain_pct != null ? ` · ${shownPct(main)} %` : "";
    const more = sps.length > 1 ? " · " + T("spools", sps.length) : "";
    return `<li ${main ? `data-spool="${main.id}"` : ""}>${sw(p)}<span class="grow">${esc(p.line)} ${esc(cname(p))} <span class="sub">${esc(p.bambu_no ?? "")}</span><br><span class="sub">${where}${rest}${more}</span></span>
      ${main ? "" : `<a class="btn small" href="${shopUrl(p)}" target="_blank" rel="noopener">${L("Shop")}</a>` + (isNoted(p.id)
        ? `<button class="small" data-projnote="${p.id}" data-on="0" title="${esc(L("Remove from shopping list"))}">✓ ${L("On the list")}</button>`
        : `<button class="small" data-projnote="${p.id}" data-on="1" title="${esc(L("Add to shopping list"))}">${L("To shopping list")}</button>`)}
      <button class="small" data-projdel="${p.id}" aria-label="${L("Remove")}">×</button></li>`;
  }).join("") || `<li class="sub">${L("No colors chosen yet.")}</li>`;
  $("#projlist").querySelectorAll("[data-projdel]").forEach((b) => (b.onclick = (e) => {
    e.stopPropagation(); project = project.filter((x) => x !== +b.dataset.projdel); setPref("project", JSON.stringify(project)); drawProject(); }));
  $("#projlist").querySelectorAll("[data-projnote]").forEach((b) => (b.onclick = async (e) => {
    e.stopPropagation(); await setNoted(+b.dataset.projnote, b.dataset.on === "1"); drawProject(); }));
  $("#projlist").querySelectorAll("li[data-spool]").forEach((li) => (li.onclick = async () => showSpool(await api(`/api/spools/${li.dataset.spool}`))));
}
$("#projclear").onclick = () => { project = []; setPref("project", "[]"); drawProject(); };
$("#projq").oninput = () => {
  const q = $("#projq").value.trim().toLowerCase(), r = $("#projres");
  if (!q || !products) { r.hidden = true; return; }
  const hits = products.filter((p) => `${p.line} ${p.name_de} ${p.name_en} ${p.bambu_no}`.toLowerCase().includes(q)).slice(0, 12);
  r.hidden = !hits.length;
  r.innerHTML = hits.map((p) => `<li data-addp="${p.id}">${sw(p)}<span>${esc(p.line)} ${esc(cname(p))}</span><span class="loc">${spoolsOf(p.id).length ? "✓" : L("missing")}</span></li>`).join("");
  r.querySelectorAll("[data-addp]").forEach((li) => (li.onclick = () => {
    const id = +li.dataset.addp; if (!project.includes(id)) project.push(id);
    setPref("project", JSON.stringify(project)); $("#projq").value = ""; r.hidden = true; drawProject(); }));
};

// ------------------------------------------------------------ guided stock check
let audit = { active: false, order: [], idx: 0, seen: {}, unknown: 0, last: null };
let auditReport = false;
const allSpools = () => (overview?.slots || []).flatMap((x) => x.spools);
// a reserve spool found on a storage slot while the same filament already has its own storage slot: it can't be booked there
function auditBlocked(sp, to) {
  const slot = (overview?.slots || []).find((x) => x.id === to);
  if (!slot || slot.kind !== "cabinet") return null;
  return allSpools().find((x) => x.id !== sp.id && x.product_id === sp.product_id && x.in_cabinet && x.slot_id !== to) || null;
}
function auditMisplaced(sp, at, short) {
  const twin = auditBlocked(sp, at);
  if (twin) return short ? `<span class="sub">${L("back to the reserve")}</span>`
    : `<div class="msg">${L("{0} is a reserve spool and belongs in the reserve (<b>{1}</b>). The same filament already has its slot on <b>{2}</b>, so put this spool back in the reserve.", title(sp), esc(sp.slot_id ?? "–"), esc(twin.slot_id))}</div>`;
  return short ? `<button class="small" data-arebook="${sp.id}">${L("Book to {0}", esc(at))}</button>`
    : `<div class="msg">${L("{0} belongs on <b>{1}</b> according to PixxelSpool, but is here on <b>{2}</b>.", title(sp), esc(sp.slot_id ?? "–"), esc(at))}
        <div class="actions"><button class="small" data-arebook="${sp.id}">${L("Book here ({0})", esc(at))}</button></div></div>`;
}
// taken out for printing (e.g. on the external holder): not on its slot, but not missing either
const auditOut = (sp) => !sp.ams_slot && sp.status === "in_use";
function auditSpool(sp, here) {
  const st = audit.seen[sp.id];
  const mark = sp.ams_slot ? `<span class="badge info">${L("in AMS {0}", esc(amsWhere(sp)))}</span>`
    : auditOut(sp) && !st ? `<span class="badge info">${esc(L("taken out"))}</span>`
    : st?.kind === "missing" ? `<span class="badge bad">${L("missing")}</span>`
    : st ? `<span class="badge ok">✓ ${st.kind === "misplaced" ? L("found on {0}", esc(st.found_at ?? "")) : L("here")}</span>` : "";
  const btn = sp.ams_slot ? "" : st ? `<button class="small" data-aundo="${sp.id}">${L("Undo")}</button>`
    : `<button class="small" data-aok="${sp.id}" data-at="${esc(here ?? "")}">${L("Lies here")}</button><button class="small" data-amiss="${sp.id}">${L("Missing")}</button>`;
  return `<li>${sw(sp)}<span class="grow">${title(sp)} <span class="sub">${esc(sp.bambu_no ?? "")}${sp.tray_uid ? "" : " · " + L("no chip")}</span><br>${mark}</span><span class="abtns">${btn}</span></li>`;
}
let auditAuto = false;   // set by a scan or a button on the current slot: when the slot is then complete, go on by itself
function drawAudit() {
  const box = $("#auditbox");
  $("#auditstart").hidden = audit.active;
  document.body.classList.toggle("auditing", !!audit.active);
  if (!audit.active) { if (!auditReport) box.innerHTML = ""; return; }
  const sps = allSpools();
  if (auditReport) return drawAuditReport();
  if (!audit.order.length) {   // nothing stored yet: nothing to walk through
    box.innerHTML = `<div class="auditnow"><p class="sub">${L("There are no spools in storage yet, so there is nothing to check.")}</p>
      <div class="actions"><button id="astop">${L("Close")}</button></div></div>`;
    bindAudit(); return;
  }
  const here = audit.order[audit.idx], n = audit.order.length, lastSlot = audit.idx >= n - 1;
  const exp = sps.filter((x) => x.slot_id === here);
  const open = exp.filter((x) => !x.ams_slot && !auditOut(x) && !audit.seen[x.id]);
  const last = audit.last;
  const what = exp.length === 1 ? L("the spool") : L("the spools");
  const hint = open.length ? L("Place {0} from <b>{1}</b> on the reader or tap “Lies here”. If a spool is not there, tap “Missing”.", what, esc(here ?? "–"))
    : exp.length ? (lastSlot ? L("All slots checked.") : L("Slot done, next slot …")) : L("Nothing should be here.");
  const lastHtml = !last ? ""
    : last.kind === "unknown" ? `<div class="msg">${L("This spool is unknown. Scan it normally once the check is done, then it will be stored.")}</div>`
    : last.kind === "ok" ? `<div class="msg okmsg">✓ ${L("{0} is in the right place.", title(last.spool))}</div>`
    : auditMisplaced(last.spool, last.found_at);
  const done = Object.keys(audit.seen).length;
  const fwd = lastSlot ? `<button class="primary" id="areport">${L("Evaluate")}</button>`
    : open.length ? `<button id="askip">${L("Skip")}</button>` : `<button class="primary" id="anext">${L("Next")}</button>`;
  box.innerHTML = `<div class="auditnow">
    <div class="auditprog"><b>${L("Slot {0} of {1}: {2}", audit.idx + 1, n, esc(here ?? "–"))}</b><span class="sub">${L("{0} checked", done)}${audit.unknown ? " · " + L("{0} unknown", audit.unknown) : ""}</span></div>
    <div class="bar"><i style="width:${n ? Math.round((audit.idx + (open.length ? 0 : 1)) / n * 100) : 0}%"></i></div>
    <ul class="shop audititems">${exp.map((sp) => auditSpool(sp, here)).join("") || `<li class="sub">${L("Nothing should be here.")}</li>`}</ul>
    <p class="sub">${hint}</p>
    ${lastHtml}
    <div class="actions">
      <button id="aprev" ${audit.idx ? "" : "disabled"}>${L("Back")}</button>
      ${fwd}
      <span class="grow"></span>
      ${lastSlot ? "" : `<button id="areport">${L("Evaluate now")}</button>`}
      <button id="astop">${L("Cancel")}</button>
    </div></div>`;
  bindAudit();
  // slot complete after a scan or a button: on to the next one by itself (not when only looking back)
  if (auditAuto && !open.length && exp.length && !lastSlot && (!last || last.kind === "ok")) {
    auditAuto = false;
    const at = audit.idx;
    setTimeout(async () => { if (audit.active && !auditReport && audit.idx === at) { audit = await api("/api/audit/goto", { method: "POST", body: { idx: at + 1 } }); drawAudit(); } }, 900);
  }
  auditAuto = false;
}
function drawAuditReport() {
  const sps = allSpools();
  const skipped = new Set(audit.skipped || []);
  const visited = new Set(audit.order.slice(0, audit.idx + 1).filter((x) => !skipped.has(x)));
  // not found: marked "Missing", or not seen on a slot that was checked (not skipped)
  const missing = sps.filter((x) => !x.ams_slot && (audit.seen[x.id]?.kind === "missing" || (visited.has(x.slot_id) && !auditOut(x) && !audit.seen[x.id])));
  const mis = sps.filter((x) => audit.seen[x.id]?.kind === "misplaced" && audit.seen[x.id].found_at !== x.slot_id);
  const ok = sps.filter((x) => audit.seen[x.id] && audit.seen[x.id].kind !== "missing" && !mis.includes(x)).length;
  const unchecked = [...skipped].filter((sl) => sps.some((x) => x.slot_id === sl && !x.ams_slot && !auditOut(x) && !audit.seen[x.id])).length;
  $("#auditbox").innerHTML = `<div class="auditnow">
    <div class="auditsum">
      <span class="${ok ? "ok" : ""}"><b>${ok}</b>${L("correct")}</span>
      <span class="${mis.length ? "warn" : ""}"><b>${mis.length}</b>${L("in the wrong place")}</span>
      <span class="${missing.length ? "bad" : ""}"><b>${missing.length}</b>${L("not found")}</span>
      ${unchecked ? `<span><b>${unchecked}</b>${L("skipped")}</span>` : ""}
      ${audit.unknown ? `<span><b>${audit.unknown}</b>${L("unknown tags")}</span>` : ""}</div>
    ${audit.idx < audit.order.length - 1 ? `<p class="sub">${L("Checked up to slot {0} ({1} of {2}).", esc(audit.order[audit.idx]), audit.idx + 1, audit.order.length)}</p>` : ""}
    ${mis.length ? `<h4>${L("In the wrong place")}</h4><ul class="shop">${mis.map((sp) => `<li>${sw(sp)}<span class="grow">${title(sp)}<br><span class="sub">${L("belongs on {0} · lies on {1}", `<b>${esc(sp.slot_id)}</b>`, `<b>${esc(audit.seen[sp.id].found_at)}</b>`)}</span></span>
      ${auditMisplaced(sp, audit.seen[sp.id].found_at, true)}</li>`).join("")}</ul>` : ""}
    ${missing.length ? `<h4>${L("Not found")}</h4><ul class="shop">${missing.map((sp) => `<li>${sw(sp)}<span class="grow">${title(sp)}<br><span class="sub">${L("should be on {0}", `<b>${esc(sp.slot_id)}</b>`)}</span></span>
      <button class="small" data-aok="${sp.id}" data-at="${esc(sp.slot_id)}">${L("Found it")}</button>
      <button class="small danger" data-aempty="${sp.id}">${L("Mark as empty")}</button></li>`).join("")}</ul>` : ""}
    ${!mis.length && !missing.length ? `<p>${L("Everything matches.")} 👍</p>` : ""}
    <div class="actions"><button id="aback">${L("Continue checking")}</button><button class="primary" id="astop">${L("Finish check")}</button></div></div>`;
  bindAudit();
}
function bindAudit() {
  const q = (sel, fn) => $("#auditbox").querySelectorAll(sel).forEach((b) => (b.onclick = () => fn(b)));
  const go = async (idx) => { audit = await api("/api/audit/goto", { method: "POST", body: { idx } }); drawAudit(); };
  q("#aprev", () => go(audit.idx - 1));
  q("#anext", () => go(audit.idx + 1));
  q("#askip", async () => { audit = await api("/api/audit/goto", { method: "POST", body: { idx: audit.idx + 1, skip: true } }); drawAudit(); });
  q("#areport", () => { auditReport = true; drawAudit(); });
  q("#aback", () => { auditReport = false; drawAudit(); });
  q("#astop", async () => { auditReport = false; audit = await api("/api/audit/stop", { method: "POST" }); drawAudit(); });
  q("[data-aok]", async (b) => { auditAuto = !auditReport; audit = await api("/api/audit/confirm", { method: "POST", body: { spool_id: +b.dataset.aok, found_at: b.dataset.at } }); drawAudit(); });
  q("[data-amiss]", async (b) => { auditAuto = true; audit = await api("/api/audit/confirm", { method: "POST", body: { spool_id: +b.dataset.amiss, missing: true } }); drawAudit(); });
  q("[data-aundo]", async (b) => { audit = await api("/api/audit/confirm", { method: "POST", body: { spool_id: +b.dataset.aundo, undo: true } }); drawAudit(); });
  q("[data-arebook]", async (b) => {
    const id = +b.dataset.arebook, to = audit.seen[id]?.found_at;
    // the slot may still belong to another spool (e.g. one that is in the AMS right now): then both swap places
    const holder = (overview?.slots || []).find((x) => x.id === to)?.spools.find((x) => x.in_cabinet && x.id !== id);
    try {
      let msg = L("Booked to {0}", to);
      if (holder) {
        const r = await api(`/api/spools/${id}/swapwith`, { method: "POST", body: { other: holder.id } });
        msg = L("Booked to {0}. {1} now belongs on {2}.", to, `${r.other.line} ${cname(r.other)}`, r.other.slot_id);
      } else await api(`/api/spools/${id}/move`, { method: "POST", body: { slot_id: to } });
      await api("/api/audit/confirm", { method: "POST", body: { spool_id: id, found_at: to } });
      toast(msg); await refresh(); audit = await api("/api/audit"); drawAudit();
    } catch (e) { toast(e.message || String(e)); }
  });
  q("[data-aempty]", async (b) => {
    if (!await askConfirm(esc(L("Mark spool as empty?")) + emptyHint(), { ok: L("Empty"), danger: true, html: true })) return;
    try { await api(`/api/spools/${b.dataset.aempty}/empty`, { method: "POST" }); await refresh(); drawAudit(); } catch (e) { toast(e.message || String(e)); }
  });
}
$("#auditstart").onclick = async () => { auditReport = false; audit = await api("/api/audit/start", { method: "POST" }); drawAudit(); };
api("/api/audit").then((a) => { audit = a; drawAudit(); }).catch(() => {});

// ------------------------------------------------------------ color from photo
let imgOpen = pref("imgFold", "0") === "1", imgMat = pref("imgMat", "all");
let imgEl = null, imgPts = [];
function hex2rgb(h) { h = (h || "").replace("#", ""); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); }
function rgb2lab([r, g, b]) {
  const f = (c) => { c /= 255; return c > 0.04045 ? ((c + 0.055) / 1.055) ** 2.4 : c / 12.92; };
  const R = f(r), G = f(g), B = f(b);
  let x = (R * 0.4124 + G * 0.3576 + B * 0.1805) / 0.95047, y = R * 0.2126 + G * 0.7152 + B * 0.0722, z = (R * 0.0193 + G * 0.1192 + B * 0.9505) / 1.08883;
  const t = (v) => (v > 0.008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116);
  x = t(x); y = t(y); z = t(z);
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)];
}
function dE00(l1, l2) { // CIEDE2000
  const [L1, a1, b1] = l1, [L2, a2, b2] = l2, rad = Math.PI / 180;
  const C1 = Math.hypot(a1, b1), C2 = Math.hypot(a2, b2), Cm = (C1 + C2) / 2;
  const G = 0.5 * (1 - Math.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7)));
  const a1p = a1 * (1 + G), a2p = a2 * (1 + G), C1p = Math.hypot(a1p, b1), C2p = Math.hypot(a2p, b2);
  const h = (b, a) => { const v = Math.atan2(b, a) / rad; return v < 0 ? v + 360 : v; };
  const h1p = h(b1, a1p), h2p = h(b2, a2p), dLp = L2 - L1, dCp = C2p - C1p;
  let dhp = C1p * C2p === 0 ? 0 : h2p - h1p; if (dhp > 180) dhp -= 360; else if (dhp < -180) dhp += 360;
  const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin((dhp / 2) * rad);
  const Lm = (L1 + L2) / 2, Cmp = (C1p + C2p) / 2;
  let hm = h1p + h2p; if (C1p * C2p !== 0) hm = Math.abs(h1p - h2p) > 180 ? (h1p + h2p + (h1p + h2p < 360 ? 360 : -360)) / 2 : (h1p + h2p) / 2;
  const T = 1 - 0.17 * Math.cos((hm - 30) * rad) + 0.24 * Math.cos(2 * hm * rad) + 0.32 * Math.cos((3 * hm + 6) * rad) - 0.2 * Math.cos((4 * hm - 63) * rad);
  const Sl = 1 + (0.015 * (Lm - 50) ** 2) / Math.sqrt(20 + (Lm - 50) ** 2), Sc = 1 + 0.045 * Cmp, Sh = 1 + 0.015 * Cmp * T;
  const Rt = -2 * Math.sqrt(Cmp ** 7 / (Cmp ** 7 + 25 ** 7)) * Math.sin(60 * Math.exp(-(((hm - 275) / 25) ** 2)) * rad);
  return Math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh));
}
const matOf = (line) => {
  const m = ((line || "").match(/(?:^|\s)(Support|TPU|PETG|PET|ABS|ASA|PLA)(?![a-z])/i) || [])[1]?.toUpperCase();
  return m === "SUPPORT" ? "SUP" : m === "PET" ? "PETG" : m === "ASA" ? "ABS" : m || "OTHER";
};
function bestMatches(rgb, n = 4) {
  const lab = rgb2lab(rgb), owned = $("#imgowned").checked;
  return (products || []).filter((p) => p.hex && /^#?[0-9a-f]{6}/i.test(p.hex) && matOf(p.line) !== "SUP"
      && (imgMat === "all" || matOf(p.line) === imgMat) && (!owned || spoolsOf(p.id).length))
    .map((p) => ({ p, d: dE00(lab, rgb2lab(hex2rgb(p.hex))) })).sort((a, b) => a.d - b.d).slice(0, n);
}
const dEText = (d) => L(d < 2 ? "almost identical" : d < 5 ? "very similar" : d < 10 ? "similar" : "rough");
function drawImgPick() {
  $("#imgpick").classList.toggle("open", imgOpen);
  $("#imgmat").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.mat === imgMat));
  $("#imgsum").textContent = imgPts.length ? Lp(imgPts.length, "{0} point", "{0} points") : "";
  $("#imgclear").hidden = !imgPts.length;
  $("#imgremove").hidden = !imgEl;
  const cv = $("#imgcv");
  if (imgEl) {
    const ctx = cv.getContext("2d");
    ctx.clearRect(0, 0, cv.width, cv.height);   // pictures with a transparent background would keep old markers otherwise
    ctx.drawImage(imgEl, 0, 0, cv.width, cv.height);
    const s = cv.width / 400;
    imgPts.forEach((pt, i) => {
      const x = pt.x * cv.width, y = pt.y * cv.height;
      ctx.lineWidth = 3 * s; ctx.strokeStyle = "#fff"; ctx.fillStyle = `rgb(${pt.rgb})`;
      ctx.beginPath(); ctx.arc(x, y, 11 * s, 0, 7); ctx.fill(); ctx.stroke();
      ctx.lineWidth = 1.2 * s; ctx.strokeStyle = "#000"; ctx.beginPath(); ctx.arc(x, y, 12.5 * s, 0, 7); ctx.stroke();
      ctx.font = `700 ${12 * s}px system-ui`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const lum = pt.rgb[0] * 0.3 + pt.rgb[1] * 0.59 + pt.rgb[2] * 0.11; ctx.fillStyle = lum > 140 ? "#000" : "#fff";
      ctx.fillText(String(i + 1), x, y + 0.5);
    });
  }
  $("#imgpoints").innerHTML = imgPts.map((pt, i) => {
    const hx = "#" + pt.rgb.map((v) => v.toString(16).padStart(2, "0")).join("").toUpperCase();
    const m = bestMatches(pt.rgb);
    return `<li><div class="imghead"><b>${i + 1}</b>${sw(hx)}<span class="sub">${hx}</span><button class="small" data-imgdel="${i}" aria-label="${L("Remove point")}">×</button></div>
      <ul class="shop">${m.map(({ p, d }) => { const sps = spoolsOf(p.id), sp = sps.find((s) => s.in_cabinet) || sps[0];
        return `<li ${sp ? `data-spool="${sp.id}"` : ""}>${sw(p)}<span class="grow">${esc(p.line)} ${esc(cname(p))} <span class="sub">${esc(p.bambu_no ?? "")}</span><br>
          <span class="sub">${dEText(d)} (ΔE ${d.toFixed(1)}) · ${sp ? L("in storage: <b>{0}</b>", esc(amsWhere(sp) || sp.slot_id || "–")) + refillHtml(refillInfo(sps)) : L("not in storage")}</span></span>
          ${sp ? "" : `<a class="btn small" href="${shopUrl(p)}" target="_blank" rel="noopener">${L("Shop")}</a>`}</li>`; }).join("") || `<li class="sub">${L("No matching color with this filter.")}</li>`}</ul></li>`;
  }).join("");
  $("#imgpoints").querySelectorAll("[data-imgdel]").forEach((b) => (b.onclick = () => { imgPts.splice(+b.dataset.imgdel, 1); drawImgPick(); }));
  $("#imgpoints").querySelectorAll("li[data-spool]").forEach((li) => (li.onclick = async () => showSpool(await api(`/api/spools/${li.dataset.spool}`))));
}
$("#imgfold").onclick = () => { imgOpen = !imgOpen; setPref("imgFold", imgOpen ? "1" : "0"); drawImgPick(); };
$("#imgmat").querySelectorAll("button").forEach((b) => (b.onclick = () => { imgMat = b.dataset.mat; setPref("imgMat", imgMat); drawImgPick(); }));
$("#imgowned").onchange = drawImgPick;
$("#imgclear").onclick = () => { imgPts = []; drawImgPick(); };
$("#imgremove").onclick = () => {
  imgEl = null; imgPts = []; $("#imgfile").value = ""; $("#imgwrap").hidden = true;
  const cv = $("#imgcv"); cv.width = cv.height = 0; drawImgPick();
};
$("#imgfile").onchange = () => {
  const f = $("#imgfile").files[0]; if (!f) return;
  const url = URL.createObjectURL(f), im = new Image();
  im.onload = () => {
    const max = 1600, k = Math.min(1, max / Math.max(im.naturalWidth, im.naturalHeight));
    const cv = $("#imgcv"); cv.width = Math.round(im.naturalWidth * k); cv.height = Math.round(im.naturalHeight * k);
    imgEl = im; imgPts = []; $("#imgwrap").hidden = false; drawImgPick();
  };
  im.src = url;
};
$("#imgcv").onclick = (e) => {
  if (!imgEl) return;
  const cv = $("#imgcv"), r = cv.getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
  // average over a small area of the original image (without markers)
  const tmp = document.createElement("canvas"); tmp.width = cv.width; tmp.height = cv.height;
  const tc = tmp.getContext("2d"); tc.drawImage(imgEl, 0, 0, cv.width, cv.height);
  const rad = Math.max(2, Math.round(cv.width / 200)), px = Math.round(x * cv.width), py = Math.round(y * cv.height);
  const d = tc.getImageData(Math.max(0, px - rad), Math.max(0, py - rad), rad * 2 + 1, rad * 2 + 1).data;
  const sum = [0, 0, 0]; let n = 0;
  for (let i = 0; i < d.length; i += 4) { if (d[i + 3] < 128) continue; sum[0] += d[i]; sum[1] += d[i + 1]; sum[2] += d[i + 2]; n++; }
  if (!n) return;
  imgPts.push({ x, y, rgb: sum.map((v) => Math.round(v / n)) }); drawImgPick();
};

// ------------------------------------------------------------ 3MF check
let tmf = null;
const FULL_G = 1000;
function gramsLeft(sp) { const full = sp.weight_g || sp.net_g || FULL_G; return sp.remain_pct != null ? Math.round(full * shownPct(sp) / 100) : sp.opened_at || sp.ams_slot ? null : full; }
// A refill comes without a spool of its own. If every stock spool of a colour is such a loose refill (not in the AMS),
// say so, and warn when no empty spool is left to put it on. Returns {text, blocked}.
function refillInfo(sps) {
  if (!sps.length || !sps.every((s) => s.is_refill && !s.ams_slot)) return { text: "", blocked: false };
  const free = SET().empty_spools ?? 0;
  return free ? { text: L("refill only, no spool"), blocked: false } : { text: L("refill only, no empty spool left"), blocked: true };
}
const refillHtml = (ri) => (ri.text ? ` · <span class="${ri.blocked ? "warnc" : ""}">${ri.blocked ? "⚠︎ " : ""}${ri.text}</span>` : "");
function tmfMatch(f) {
  const lab = rgb2lab(hex2rgb(f.hex)), mat = matOf(f.profile.replace(/^Bambu\s+/i, "") || f.type) ;
  const cands = (products || []).filter((p) => p.hex && /^#?[0-9a-f]{6}/i.test(p.hex))
    .map((p) => ({ p, d: dE00(lab, rgb2lab(hex2rgb(p.hex))) }));
  const same = cands.filter((c) => f.filament_id && c.p.material_id === f.filament_id).sort((a, b) => a.d - b.d);
  const exact = same.length && same[0].d < 3 ? same[0].p : null;
  // the file only has a colour code (the designer picked an own colour): name the closest colour of that line
  const near = !exact && same.length ? same[0] : null;
  const own = exact ? spoolsOf(exact.id) : [];
  // only real look-alikes: beyond ΔE 20 (e.g. black for white) it is a different color, not an alternative
  const alts = cands.filter((c) => c.p !== exact && c.d < 20 && matOf(c.p.line) === (mat === "OTHER" ? matOf(f.type) : mat) && spoolsOf(c.p.id).length)
    .sort((a, b) => a.d - b.d).slice(0, 3);
  return { exact, near, own, alts };
}
// price per gram for a 3MF filament: own spools first, then the line price, then the price set in the slicer
function tmfPrice(f, m) {
  const sp = m.own.find((x) => spoolPrice(x) != null);
  if (sp) return { pg: spoolPrice(sp) / (sp.weight_g || sp.net_g || FULL_G), src: "stock" };
  const p = m.exact || m.near?.p;
  if (p?.line_price != null) return { pg: p.line_price / (p.net_g || FULL_G), src: "line" };
  if (f.cost_kg) return { pg: f.cost_kg / 1000, src: "file" };
  return null;
}
const gText = (g) => (g > 0 && g < 1 ? L("under 1 g") : `${Math.round(g)} g`);   // tiny parts (a logo inlay) must not read "0 g"
function drawTmf() {
  const out = $("#tmfout");
  $("#tmfremove").hidden = !tmf;
  if (!tmf) { out.innerHTML = ""; return; }
  const used = tmf.filaments.filter((f) => f.used);
  const src = L(tmf.sliced ? "from the sliced file (exact)" : "estimated before slicing");
  let total = 0, totalG = 0, costKnown = true;
  const srcs = new Set();
  const rows = used.map((f) => {
    const need = f.exact_g ?? f.est_g, m = tmfMatch(f);
    const have = m.own.reduce((s, sp) => s + (gramsLeft(sp) ?? 0), 0), unknown = m.own.some((sp) => gramsLeft(sp) == null);
    const ri = refillInfo(m.own), ok = m.own.length && (have >= need * 1.1 || unknown) && !ri.blocked;
    const status = !m.own.length ? `<span class="bad">${L("not in storage")}</span>` : ri.blocked ? `<span class="warnc">⚠︎ ${ri.text}</span>` : ok ? `<span class="okc">✓ ${L("in storage")}</span>` : `<span class="warnc">⚠︎ ${L("may not be enough")}</span>`;
    const where = m.own.map((sp) => `<b>${esc(amsWhere(sp) || sp.slot_id || "–")}</b>${gramsLeft(sp) != null ? ` (~${gramsLeft(sp)} g)` : ""}`).join(", ");
    const alt = !ok && m.alts.length ? `<div class="sub tmfalt">${L("Alternatives from storage:")} ${m.alts.map(({ p, d }) => { const sp = spoolsOf(p.id)[0];
      return `<span class="altchip" data-spool="${sp.id}">${sw(p)} ${esc(p.line)} ${esc(cname(p))} · ${esc(amsWhere(sp) || sp.slot_id || "–")} · ${dEText(d)}</span>`; }).join(" ")}</div>` : "";
    const pr = need > 0 ? tmfPrice(f, m) : null, cost = pr ? need * pr.pg : null;
    if (need > 0) { totalG += need; if (cost != null) { total += cost; srcs.add(pr.src); } else costKnown = false; }
    const name = m.exact ? `${esc(m.exact.line)} <span class="tmfcol">${esc(cname(m.exact))}</span>${m.exact.bambu_no ? ` <span class="sub">${esc(m.exact.bambu_no)}</span>` : ""}`
      : `${esc(f.profile || f.type)} <span class="sub">${esc(f.hex)}</span>`;
    const nearTxt = m.near ? `<div class="sub tmfnear">${L("Own colour from the file, not a Bambu colour. Closest: {0} ({1})", `${sw(m.near.p)} <b>${esc(cname(m.near.p))}</b>`, dEText(m.near.d))}</div>` : "";
    const amount = f.support && !(need > 0) ? L("supports only, amount known after slicing")
      : `${tmf.sliced || need < 1 ? "" : L("approx.") + " "}${gText(need)}${f.support ? " " + L("+ supports") : ""}${f.exact_m ? ` · ${f.exact_m} m` : ""}${f.painted ? ` · <span title="${esc(L("Painted in the file"))}">🖌︎ ${L("painted")}</span>` : ""}`;
    return `<li><span class="tmfidx">${f.idx}</span>${sw(f.hex)}<span class="grow"><span class="tmfname">${name}</span>${nearTxt}
      <span class="sub tmfline">${amount} · ${status}${where ? ` · ${where}` : ""}${ri.blocked ? "" : refillHtml(ri)}</span>${alt}</span>
      <span class="tmfcost">${cost != null ? `${need < 1 || !tmf.sliced ? "~" : ""}${esc(money(cost))}` : need > 0 ? `<span class="sub">${L("no price")}</span>` : ""}</span>
      ${!m.own.length && (m.exact || m.near) && !(m.exact || m.near.p).discontinued ? `<a class="btn small" href="${shopUrl(m.exact || m.near.p)}" target="_blank" rel="noopener">${L("Shop")}</a>` : ""}</li>`;
  });
  const srcTxt = [...srcs].map((x) => L({ stock: "spool prices", line: "line prices", file: "prices from the file" }[x])).join(", ");
  out.innerHTML = `<p class="sub">${Lp(used.length, "{0} filament used", "{0} filaments used")} · ${L("amount {0}", src)}${tmf.printer ? ` · ${esc(tmf.printer)}` : ""}</p>
    <ul class="shop tmflist">${rows.join("") || `<li class="sub">${L("No printable objects found.")}</li>`}</ul>
    ${totalG > 0 ? `<div class="tmftotal"><span class="grow"><b>${L("Total")}</b><span class="sub">${srcTxt ? L("Cost from {0}", srcTxt) : L("No prices known yet")}${!costKnown && srcs.size ? " · " + L("not every filament has a price") : ""}</span></span>
      <b>${tmf.sliced ? "" : "~"}${gText(totalG)}</b><b class="tmfcost">${srcs.size ? `${tmf.sliced && costKnown ? "" : "~"}${esc(money(total))}` : "–"}</b></div>` : ""}
    ${tmf.sliced ? "" : `<p class="tmfnote"><b>${L("Estimate before slicing")}</b> ${L("from {0} cm³ model volume, {1} walls, {2} % infill and {3} mm layer height. It is usually within a few percent of the “Model” value in Bambu Studio.", tmf.total_volume_cm3, tmf.settings.walls, tmf.settings.infill_pct, tmf.settings.layer_height)}
      ${L("Not included: supports, brim and purge.")}${tmf.multicolor ? " " + L("Multi-colour prints often add 20–40 % for the prime tower and purging.") : ""}
      ${L("Exact values: slice in Bambu Studio, then File › Export › Export plate sliced file, and load the .gcode.3mf here.")}${tmf.painted ? " " + L("The file contains painted areas: their colours are listed, the amounts are a rough estimate from the painted surface.") : ""}</p>`}
    <details class="tmfobj"><summary>${Lp(tmf.objects.length, "{0} object", "{0} objects")}</summary><ul>${tmf.objects.map((o) => `<li>${esc(o.name)}${o.filament ? ` · Filament ${(o.paint_filaments?.length > 1 ? o.paint_filaments : [o.filament]).join(", ")}` : ""}${o.volume_cm3 != null ? ` · ${o.volume_cm3 > 0 && o.volume_cm3 < 0.1 ? "< 0.1" : o.volume_cm3} cm³` : ""}${o.est_g != null ? ` · ${o.est_g < 1 ? "" : L("approx.") + " "}${gText(o.est_g)}` : ""}</li>`).join("")}</ul></details>`;
  out.querySelectorAll("[data-spool]").forEach((el) => (el.onclick = async () => showSpool(await api(`/api/spools/${el.dataset.spool}`))));
}
// only .3mf files; iOS greys out unknown types, so it keeps the broad list and the name is checked instead
if (!(/iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1))) $("#tmffile").accept = ".3mf,model/3mf";
$("#tmfremove").onclick = () => { tmf = null; $("#tmfname").textContent = ""; drawTmf(); };
$("#tmffile").onchange = async () => {
  const f = $("#tmffile").files[0]; if (!f) return;
  if (!/\.3mf$/i.test(f.name)) { $("#tmffile").value = ""; return toast(L("Please choose a .3mf file (from Bambu Studio or Orca Slicer).")); }
  $("#tmfname").textContent = L("Analyzing {0} …", f.name); $("#tmfout").innerHTML = "";
  try {
    const res = await fetch("/api/3mf", { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: f });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(tr(data.error || data.detail || res.statusText));
    tmf = data; $("#tmfname").textContent = f.name; drawTmf();
  } catch (e) { tmf = null; $("#tmfname").textContent = ""; drawTmf(); toast(e.message); }
  $("#tmffile").value = "";
};

let products = null, manLines = [];
const BAMBU_BRAND = "Bambu Lab";
async function loadProducts() {
  products = await api("/api/products");
  try { manLines = (await api("/api/brands")).lines; } catch (e) { manLines = []; }
  const brands = [...new Set(manLines.map((l) => l.brand))].sort();
  const cur = $("#manBrand").value;
  $("#manBrand").innerHTML = [BAMBU_BRAND, ...brands].map((b) => `<option>${esc(b)}</option>`).join("");
  if ([BAMBU_BRAND, ...brands].includes(cur)) $("#manBrand").value = cur;
  $("#manBrandRow").hidden = $("#manBrand").hidden = !brands.length;     // only needed once other brands exist
  fillManLines(); drawProject(); drawImgPick();
}
function fillManLines() {
  const b = $("#manBrand").value, cur = $("#manLine").value;
  const lines = b === BAMBU_BRAND ? [...new Set(products.filter((p) => !p.brand).map((p) => p.line))].sort()
    : manLines.filter((l) => l.brand === b).map((l) => l.name).sort();
  $("#manLine").innerHTML = lines.map((l) => `<option>${esc(l)}</option>`).join("");
  if (lines.includes(cur)) $("#manLine").value = cur;
  fillManColors();
}
function fillManColors() {
  const l = $("#manLine").value, list = products.filter((p) => p.line === l);
  $("#manColor").innerHTML = list.length
    ? list.map((p) => `<option value="${p.id}">${esc(cname(p))}${p.bambu_no ? " · " + esc(p.bambu_no) : ""}</option>`).join("")
    : `<option value="">${esc(L("No colors yet – add them under Other brands"))}</option>`;
  manPrefill();
}
$("#manBrand").onchange = fillManLines;
$("#manLine").onchange = fillManColors;
$("#manColor").onchange = manPrefill;
async function manPrefill() {
  // the line's standard price (Statistics) as suggestion; a price the user typed is kept
  const inp = $("#manPrice"), pid = $("#manColor").value;
  if (!pid || (inp.value.trim() && inp.dataset.auto !== inp.value)) return;
  try { const r = await api(`/api/prices/last/${pid}?standard=1`); inp.value = r.price != null ? priceStr(r.price) : ""; inp.dataset.auto = inp.value; }
  catch (e) { /* no suggestion */ }
}
$("#manAdd").onclick = async () => {
  if (!$("#manColor").value) return toast(L("Please choose a color"));
  try {
    const sp = await api("/api/spools/manual", { method: "POST", body: { product_id: $("#manColor").value, reserve: $("#manWhere").value === "reserve", price: $("#manPrice").value.trim() } });
    await refresh(); showView("storage");
    showSpool(sp, null, L("Added manually. Slot: <b>{0}</b>. Just scan it later and the tag will be linked.", esc(sp.slot_id)));
  } catch (e) { ask(e.message, { title: L("Spool not added"), noCancel: true, warn: true }); }
};
loadProducts().catch(() => {});
let allLines = null;
api("/api/lines/all").then((l) => { allLines = l; fillSettings(); }).catch(() => {});
document.querySelectorAll("[data-dryon]").forEach((b) => (b.onclick = () => saveSettings({ dry_on: b.dataset.dryon === "1" }).then(() => refresh())));
$("#saveDry").onclick = () => saveSettings({ dry_weeks_dry: $("#setDryDry").value, dry_weeks_other: $("#setDryOther").value }).then(() => refresh());
$("#saveShop").onclick = () => saveSettings({ collect_lines: [...document.querySelectorAll("#collectlines input:checked")].map((i) => i.value) }).then(() => refresh());
let haCfg = null;
async function loadHaCfg() {
  try { const c = haCfg = await api("/api/ha/config"); if (document.activeElement !== $("#haUrl")) $("#haUrl").value = c.url;
    $("#haToken").placeholder = L(c.has_token ? "saved ✓ – enter a new one to change it" : "no token saved yet"); } catch (e) {}
}
async function connectHa() {
  const b = $("#saveHaCfg"); b.disabled = true; b.textContent = L("Checking …");
  let ok = false;
  try { await api("/api/ha/config", { method: "PUT", body: { url: $("#haUrl").value, token: $("#haToken").value } });
        $("#haToken").value = ""; toast(L("Connected and saved")); loadHaCfg(); setTimeout(loadSensors, 3000); ok = true;
        if (wiz.open && SET().ha_on === false) await saveSettings({ ha_on: true });   // the wizard has no on/off switch
        await refresh();
  } catch (e) { toast(e.message); }
  b.disabled = false; b.textContent = L("Test connection and save");
  return ok;
}
$("#saveHaCfg").onclick = () => connectHa();
["#haUrl", "#haToken"].forEach((id) => $(id).addEventListener("input", () => wizSync()));
loadHaCfg();
$("#saveHa").onclick = () => saveSettings({ ha_poll_seconds: $("#setPoll").value, climate: readClimateCfg() }).then(() => setTimeout(refresh, 1500));
$("#haSync").onclick = async () => {
  const b = $("#haSync"); b.disabled = true; b.textContent = L("Syncing …");
  try {
    const h = await api("/api/ha/sync", { method: "POST" });
    toast(h.status === "connected" ? L("Home Assistant synced") : L("Status: {0}", L({ off: "off", error: "Error", connected: "connected" }[h.status] || h.status)) + (h.detail ? " · " + tr(h.detail) : ""));
    await loadSensors(); refresh();
  } catch (e) { toast(e.message); }
  b.disabled = false; b.textContent = L("Sync now");
};
document.querySelectorAll("[data-haon]").forEach((b) => (b.onclick = async () => {
  const on = b.dataset.haon === "1";
  if (on === (SET().ha_on !== false)) return;
  if (!on && (haCfg?.url || haCfg?.has_token)) {
    const r = await askKeepData(L("Home Assistant"), L("Address, token and the sensor assignments of your storage units are still saved."));
    if (r === null) return;
    if (r === "delete") {
      try { await api("/api/ha/config", { method: "DELETE" }); overview.settings = await api("/api/settings"); await loadHaCfg(); fillSettings(); toast(L("Data deleted")); }
      catch (e) { toast(tr(e.message)); }
      return setTimeout(refresh, 800);
    }
  }
  saveSettings({ ha_on: on }).then(() => setTimeout(refresh, 1500));
}));
// a feature with saved data is switched off: keep the data (switch it on again later) or delete it.
// Resolves "keep", "delete" or null (cancelled).
async function askKeepData(name, what) {
  const r = await ask(esc(L("Keep the data of {0}?", name)) + `<span class="dlgnote">${esc(what)} ${esc(L("If you keep them, you only have to switch it on again later."))}</span>`,
    { html: true, warn: true, title: L("Turn off {0}", name), ok: L("Keep data"), extra: [{ label: L("Delete data"), value: "delete" }] });
  return r === true ? "keep" : r === "delete" ? "delete" : null;
}

// ------------------------------------------------------------ cabinet climate (Home Assistant sensors)
let haSensors = null, climData = null, climDays = +pref("climDays", "7"), climOpen = pref("climOpen", "1") === "1";
async function loadSensors() { try { haSensors = await api("/api/ha/sensors"); } catch (e) { haSensors = []; } drawClimateCfg(); }
function drawClimateCfg() {
  const box = $("#climatecfg"); if (!box || !overview) return;
  const cfg = SET().climate || {}, list = haSensors || [];
  if (!list.length) { box.innerHTML = `<p class="sub">${L(SET().ha_on === false ? "Home Assistant is switched off." : "No sensors found. Is Home Assistant connected?")}</p>`; return; }
  const opts = (kind, cur) => `<option value="">${L("none")}</option>` + list.filter((x) => x.kind === kind).map((x) =>
    `<option value="${esc(x.entity)}" ${x.entity === cur ? "selected" : ""}>${esc(x.name)} (${esc(x.state)} ${esc(x.unit)})</option>`).join("");
  box.innerHTML = CABS().map((c) => { const v = cfg[c.key] || {};
    return `<div class="climrow" data-cab="${esc(c.key)}"><b>${esc(cabTitle(c.key))}</b>
      <label>${L("Temperature")}<select data-k="temp">${opts("temperature", v.temp)}</select></label>
      <label>${L("Humidity")}<select data-k="hum">${opts("humidity", v.hum)}</select></label>
      <label>${L("Green range up to")}<span class="inline"><input data-k="ok_hum" type="number" min="5" max="94" inputmode="numeric" value="${v.ok_hum ?? (v.max_hum ?? 50) - 10}"> %</span></label>
      <label>${L("Warn above")}<span class="inline"><input data-k="max_hum" type="number" min="10" max="95" inputmode="numeric" value="${v.max_hum ?? 50}"> %</span></label></div>`; }).join("");
}
function readClimateCfg() {
  const out = {};
  document.querySelectorAll("#climatecfg .climrow").forEach((r) => {
    const g = (k) => r.querySelector(`[data-k="${k}"]`).value;
    if (g("temp") || g("hum")) out[r.dataset.cab] = { temp: g("temp"), hum: g("hum"), max_hum: +g("max_hum") || 50, ok_hum: +g("ok_hum") || undefined };
  });
  return out;
}
const fmt1 = (v) => v == null ? "–" : Number(v).toLocaleString(LOCALE, { maximumFractionDigits: 1 });
function climChip(key) {
  const c = overview?.ha?.climate?.[key];
  if (!c) return "";
  const warn = c.hum != null && c.hum >= c.max_hum;
  return ` <span class="climchip ${warn ? "warn" : ""}">${c.temp != null ? fmt1(c.temp) + " °C" : ""}${c.temp != null && c.hum != null ? " · " : ""}${c.hum != null ? fmt1(c.hum) + " %" : ""}</span>`;
}
let lastClimWarn = "";
function drawClimWarn() {
  const cl = overview?.ha?.climate || {}, el = $("#climwarn");
  const bad = CABS().filter((c) => cl[c.key]?.hum != null && cl[c.key].hum >= cl[c.key].max_hum);
  el.hidden = !bad.length;
  el.innerHTML = bad.map((c) => L("{0}: {1} % humidity (limit {2} %) – check the desiccant.", esc(cabTitle(c.key)), fmt1(cl[c.key].hum), cl[c.key].max_hum)).join("<br>");
  const sig = bad.map((c) => c.key).join();
  if (sig && sig !== lastClimWarn) { beep("note"); toast(L("Humidity in storage too high")); }
  lastClimWarn = sig;
}
async function loadClimate() {
  const el = $("#climate");
  if (!overview?.ha?.climate || !Object.keys(SET().climate || {}).length) { el.hidden = true; return; }
  try { climData = await api(`/api/climate?days=${climDays}`); } catch (e) { return; }
  drawClimate();
}
// monotone cubic path through points sorted by x (Fritsch–Carlson tangents)
function monoPath(P) {
  const n = P.length; if (n < 3) return P.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
  const d = [], m = [];
  for (let i = 0; i < n - 1; i++) d.push((P[i + 1][1] - P[i][1]) / ((P[i + 1][0] - P[i][0]) || 1));
  m.push(d[0]);
  for (let i = 1; i < n - 1; i++) m.push(d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2);
  m.push(d[n - 2]);
  for (let i = 0; i < n - 1; i++) {
    if (d[i] === 0) { m[i] = m[i + 1] = 0; continue; }
    const a = m[i] / d[i], b = m[i + 1] / d[i], h = a * a + b * b;
    if (h > 9) { const t = 3 / Math.sqrt(h); m[i] = t * a * d[i]; m[i + 1] = t * b * d[i]; }
  }
  let out = `M${P[0][0].toFixed(1)},${P[0][1].toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const dx = (P[i + 1][0] - P[i][0]) / 3;
    out += `C${(P[i][0] + dx).toFixed(1)},${(P[i][1] + m[i] * dx).toFixed(1)} ${(P[i + 1][0] - dx).toFixed(1)},${(P[i + 1][1] - m[i + 1] * dx).toFixed(1)} ${P[i + 1][0].toFixed(1)},${P[i + 1][1].toFixed(1)}`;
  }
  return out;
}
function climSvg(c, W = 600) {
  const pts = c.series.filter((p) => p[2] != null);
  if (pts.length < 2) {
    // older readings exist, but none in the chosen range: the sensor stopped reporting (not "too few readings")
    if (c.last && !c.series.length) return `<p class="sub">${L("No readings in this period. Last stored value: {0}. Check the sensor in Home Assistant.", esc(dateTimeShort(c.last)))}</p>`;
    return `<p class="sub">${L("Not enough readings yet. PixxelSpool stores a value every 10 minutes.")}</p>`;
  }
  const H = Math.round(Math.min(150, Math.max(110, W / 3))), pl = 30, pr = 8, pt = 8, pb = 20;
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0] || t0 + 1;
  const ok = Math.min(c.ok_hum ?? c.max_hum - 10, c.max_hum - 1);
  const hs = pts.map((p) => p[2]), lo = Math.max(0, Math.floor(Math.min(...hs, ok) / 10) * 10 - 5), hi = Math.min(100, Math.ceil(Math.max(...hs, c.max_hum) / 10) * 10 + 5);
  const x = (t) => pl + (W - pl - pr) * (t - t0) / (t1 - t0 || 1), y = (v) => pt + (H - pt - pb) * (1 - (v - lo) / (hi - lo || 1));
  // smooth: short moving average against the 1 % sensor steps, then a monotone cubic curve (no overshoot)
  const win = Math.max(1, Math.round(pts.length / 30));
  const sm = pts.map((p, i) => { const a = pts.slice(Math.max(0, i - win), i + win + 1); return [x(p[0]), y(a.reduce((n, q) => n + q[2], 0) / a.length)]; });
  const line = monoPath(sm);
  // color along the humidity: green up to the green range from the options, yellow up to the warning limit, red above it
  const gid = "cg" + Math.random().toString(36).slice(2, 8), off = (v) => Math.max(0, Math.min(1, (y(v) - pt) / (H - pt - pb)));
  const grad = `<defs><linearGradient id="${gid}" gradientUnits="userSpaceOnUse" x1="0" y1="${pt}" x2="0" y2="${H - pb}">
    <stop offset="${off(c.max_hum + 3)}" style="stop-color:var(--bad)"/><stop offset="${off(c.max_hum)}" style="stop-color:var(--warn)"/>
    <stop offset="${off((ok + c.max_hum) / 2)}" style="stop-color:var(--warn)"/><stop offset="${off(ok)}" style="stop-color:var(--good)"/></linearGradient></defs>`;
  const grid = [lo, Math.round((lo + hi) / 2), hi].map((v) => `<line x1="${pl}" x2="${W - pr}" y1="${y(v)}" y2="${y(v)}" class="cg"/><text x="${pl - 4}" y="${y(v) + 4}" class="ct" text-anchor="end">${v}</text>`).join("");
  const days = [], step = climDays <= 1 ? 6 * 3600 : 86400 * Math.ceil(climDays / 7);
  for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) {
    const d = new Date(t * 1000);   // timestamps are local time stored as if UTC
    const lab = climDays <= 1 ? `${String(d.getUTCHours()).padStart(2, "0")}:00` : `${d.getUTCDate()}.${d.getUTCMonth() + 1}.`;
    days.push(`<text x="${x(t)}" y="${H - 4}" class="ct" text-anchor="middle">${lab}</text>`);
  }
  return `<svg class="climsvg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(L("Humidity"))}">${grad}${grid}${days.join("")}
    <rect x="${pl}" width="${W - pl - pr}" y="${y(ok)}" height="${Math.max(0, H - pb - y(ok))}" class="cok"/>
    <line x1="${pl}" x2="${W - pr}" y1="${y(c.max_hum)}" y2="${y(c.max_hum)}" class="cmax"/>
    <path d="${line}" class="cline" style="stroke:url(#${gid})"/></svg>`;
}
function drawClimate() {
  const el = $("#climate"), d = climData;
  if (!d || !d.cabinets.length) { el.hidden = true; return; }
  el.hidden = false; el.classList.toggle("open", climOpen);
  const W = Math.max(240, Math.round((el.clientWidth || 640) - 34));   // drawn at its real width so labels keep their size
  const sum = d.cabinets.map((c) => c.now ? `${esc(c.name)} ${c.now.hum != null ? fmt1(c.now.hum) + " %" : fmt1(c.now.temp) + " °C"}` : "").filter(Boolean).join(" · ");
  el.innerHTML = foldHead("climfold", L("Climate"), sum) + `<div class="foldbody">
    <div class="seg on-always climrange">${[[1, "24 h"], [7, L("7 days")], [30, L("30 days")]].map(([v, t]) => `<button data-cd="${v}" class="${v === climDays ? "on" : ""}">${t}</button>`).join("")}</div>
    ${d.cabinets.map((c) => { const h = c.now?.hum, cls = h == null ? "" : h > c.max_hum ? "rbad" : h > (c.ok_hum ?? c.max_hum - 10) ? "rwarn" : "rok";
      return `<div class="climcab"><div class="climhead" title="${esc(L("limit {0} %", c.max_hum))}"><span class="cname">${esc(c.name)}</span>` +
        `<span class="climnow">${h != null ? `<b class="${cls}">${fmt1(h)} %</b>` : ""}${c.now?.temp != null ? `<span>${fmt1(c.now.temp)} °C</span>` : ""}${c.now ? "" : "–"}</span></div>${climSvg(c, W)}</div>`; }).join("")}</div>`;
  $("#climfold").onclick = () => { climOpen = !climOpen; setPref("climOpen", climOpen ? "1" : "0"); el.classList.toggle("open", climOpen); };
  el.querySelectorAll("[data-cd]").forEach((b) => (b.onclick = () => { climDays = +b.dataset.cd; setPref("climDays", String(climDays)); loadClimate(); }));
}
setInterval(() => { if (!document.hidden && view === "storage") loadClimate(); }, 600000);
let climT, climW = 0; addEventListener("resize", () => { clearTimeout(climT); climT = setTimeout(() => {
  const w = $("#climate").clientWidth; if (climData && w && Math.abs(w - climW) > 20) { climW = w; drawClimate(); } }, 200); });

// ------------------------------------------------------------ printer card (direct connection)
const PRINTER_SVG = `<svg class="printerpic" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <rect x="8" y="6" width="48" height="52" rx="4"/><path d="M8 14h48"/><rect x="13" y="18" width="38" height="30" rx="2"/>
  <path d="M16 24h32"/><rect x="27" y="22" width="10" height="7" rx="1.2"/><path d="M32 29v3"/>
  <path d="M18 43h28"/><path d="M26 43v-4h12v4"/><circle cx="14" cy="53" r="1.4"/><path d="M20 53h12"/></svg>`;
let printerData = null, rackOpen = pref("rackOpen", "0") === "1";
const LIGHT_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1.1 2V16h5v-.2c.1-.8.5-1.5 1.1-2A6 6 0 0 0 12 3z"/></svg>`;
async function loadPrinter() {
  try { printerData = await api("/api/printer"); } catch (e) { printerData = null; }
  drawPrinter(); wizSync();
  if (overview) drawAms();    // external spools move between AMS card and printer card
}
function pcheck(pid) {
  const j = (overview?.jobs || []).find((x) => x.printer === pid);
  if (!j || !j.rows?.length || !j.active) return "";
  const ST = { ok: ["✓", L("enough")], tight: ["⚠︎", L("tight")], short: ["✕", L("not enough")], unknown: ["?", L("remaining unknown")] };
  return `<ul class="pcheck">${j.rows.map((r) => {
    const sp = r.spool, bad = r.state === "tight" || r.state === "short";
    const spare = bad ? (r.spare ? ` · ${L("Spare:")} <b>${esc(r.spare.slot_id ?? "–")}</b>` : sp ? " · " + L("no spare spool") : "") : "";
    return `<li class="job-${r.state}" ${r.spare ? `data-spool="${r.spare.id}"` : ""}><span class="jobst">${ST[r.state][0]}</span>
      ${sp ? sw(sp) : ""}<span class="grow">${esc(r.slot.replace("AMS 1 · ", ""))} · ${ST[r.state][1]} <span class="sub">(${Math.round(r.need_g)} g${r.have_g != null ? " " + L("of approx. {0} g", r.have_g) : ""})</span>${spare}</span></li>`;
  }).join("")}</ul>`;
}
// remaining time or finishing time; a tap switches between them (remembered per device)
let etaClock = pref("etaClock", "0") === "1";
function etaHtml(min) {
  if (!etaClock) return `<button class="eta" data-eta title="${esc(L("Show finishing time"))}">${L("{0} left", fmtMin(min))}</button>`;
  const end = new Date(Date.now() + min * 60000), today = new Date(), tom = new Date(); tom.setDate(today.getDate() + 1);
  const t = fmtTime(end), lab = end.toDateString() === today.toDateString() ? L("done at {0}", t)
    : end.toDateString() === tom.toDateString() ? L("done tomorrow at {0}", t) : L("done on {0} at {1}", fmtDay(end), t);
  return `<button class="eta" data-eta title="${esc(L("Show remaining time"))}">${lab}</button>`;
}
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-eta]")) return;
  e.stopPropagation(); etaClock = !etaClock; setPref("etaClock", etaClock ? "1" : "0"); drawPrinter();
}, true);
function fmtMin(m) { return m == null ? "" : m >= 60 ? `${Math.floor(m / 60)} h ${Math.round(m % 60)} min` : `${Math.round(m)} min`; }
// camera image: its own element so the 10-second redraw does not interrupt the stream
const cam = { want: false, t: null, since: 0, open: false, pid: "", big: false, box: null };   // always collapsed when the page loads
function syncCam() {
  const box = $("#pcam"); if (!box) return;
  const img = box.querySelector("img");
  const p = shownPrinter();
  const avail = (SET().camera || "off") !== "off" && !!p?.connected && !$("#printer").hidden;
  const want = avail && cam.open && !document.hidden;
  const tg = $("#pcamtoggle");
  if (tg) { tg.hidden = !avail; tg.classList.toggle("open", cam.open); }
  box.hidden = !want;
  if (!want && cam.big) camBig(false);
  if (want && (!cam.want || cam.pid !== p.id || Date.now() - cam.since > 540000)) {   // reconnect after 9 minutes (the server ends the stream after 10)
    box.classList.remove("live"); cam.since = Date.now(); cam.pid = p.id;
    img.src = camSrc(p.id);
  } else if (!want && cam.want) {
    img.src = "data:,"; box.classList.remove("live");
  }
  cam.want = want;
}
// the large window asks for the printer's full resolution, the small preview for 640 px
const camSrc = (pid) => `/api/camera/stream?printer=${encodeURIComponent(pid)}${cam.big ? "&hd=1" : ""}&t=${Date.now()}`;
function camHd() {
  const img = $("#pcam img");
  if (img && cam.want) { cam.since = Date.now(); img.src = camSrc(cam.pid); }
}
function camToggle() {
  const b = document.createElement("button"); b.id = "pcamtoggle"; b.className = "pcamtoggle fold"; b.hidden = true;
  b.innerHTML = `<span class="camlab"><svg class="camico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="2.5" width="12" height="8.5" rx="1.8"/><path d="m14.5 5.5 6-2.5v7.5l-6-2.5"/><path d="M8.5 11v3.5"/><path d="M8.5 14.5 4.5 21.5"/><path d="m8.5 14.5 4 7"/></svg>${L("Camera")}</span> <span class="chev">›</span>`;
  b.onclick = () => { cam.open = !cam.open; syncCam(); };
  return b;
}
function camBox() {
  const box = document.createElement("div"); box.id = "pcam"; box.className = "pcam"; box.hidden = true;
  box.innerHTML = `<img alt=""><span class="sub">${L("Camera connecting …")}</span>`;
  const img = box.querySelector("img");
  img.onload = () => box.classList.add("live");
  img.onerror = () => { if (!cam.want) return; box.classList.remove("live"); clearTimeout(cam.t);
    cam.t = setTimeout(() => { cam.want = false; syncCam(); }, 5000); };
  box.onclick = () => camBig(true);
  cam.box = box;   // the one camera node: found again after the large window (which held it) is removed
  return box;
}
// tap on the camera: the same picture in a large dialog with an X (the stream keeps running, the node just moves)
function camBig(on) {
  const box = $("#pcam"), cur = $("#camdlg");
  if (!on) {
    if (!cur) return;
    cam.big = false; cur.classList.remove("in"); camHd();
    setTimeout(() => { cur.remove(); if (printerData) drawPrinter(); }, 180);
    return;
  }
  if (cur || !box || !box.classList.contains("live")) return;
  cam.big = true; camHd();
  const p = shownPrinter();
  const wrap = document.createElement("div"); wrap.className = "dlgwrap camwrap"; wrap.id = "camdlg";
  wrap.innerHTML = `<div class="dlg camdlg" role="dialog" aria-modal="true"><div class="camhead"><h3>${esc(L("Camera"))}${p ? ` <span class="sub">${esc(p.printer_name || ("Bambu Lab " + (p.model || "")))}</span>` : ""}</h3>
    <button class="camx" aria-label="${esc(L("Close"))}" title="${esc(L("Close"))}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button></div><div class="camhold"></div></div>`;
  wrap.querySelector(".camhold").append(box);
  wrap.onclick = (e) => { if (e.target === wrap || e.target.closest(".camx")) camBig(false); };
  document.body.append(wrap);
  requestAnimationFrame(() => wrap.classList.add("in"));
  wrap.querySelector(".camx").focus();
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && cam.big) camBig(false); });
document.addEventListener("visibilitychange", () => syncCam());
setInterval(syncCam, 30000);
// Several printers: one tile per printer, printing ones first; the opened one shows the full card.
let pOpen = pref("pOpen", "");
// a single printer: collapsible too; open by default on large screens (iPad, Mac), closed on phones
const SMALL_SCREEN = matchMedia("(max-width: 700px), (max-height: 500px)").matches;
let pSingleOpen = pref("pSingleOpen", SMALL_SCREEN ? "0" : "1") === "1";
const PACTIVE = ["running", "prepare", "pause", "slicing"];
function printersShown() {
  const all = printerData?.printers || [];
  const list = all.length > 1 ? all : all.filter((p) => p.connected);
  const rank = (p) => (p.connected ? 0 : 2) + (PACTIVE.includes(p.state) ? 0 : 1);
  return [...list].sort((a, b) => rank(a) - rank(b));
}
function shownPrinter() {
  const list = printersShown().filter((p) => p.connected);
  if (view === "printerview") return list.find((p) => p.id === pOpen) || list[0] || null;   // its own page: always unfolded
  return list.length === 1 ? (pSingleOpen ? list[0] : null) : list.find((p) => p.id === pOpen) || null;
}
function pcls(p) { return p.state === "failed" || (p.messages || []).length ? "bad" : p.state === "running" ? "ok" : p.state === "pause" ? "warn" : ""; }
function pfull(p) {
  const active = PACTIVE.includes(p.state);
  const temps = (p.temps || []).filter((t) => t.cur != null).map((t) =>
    `<span><span class="sub">${esc(tr(t.label))}</span><span>${Math.round(t.cur)}°${t.tar ? `<span class="sub">/${Math.round(t.tar)}°</span>` : ""}</span></span>`).join("");
  const air = p.air ? `<span><span class="sub">${L("Air")}</span><span>${esc(tr(p.air))}</span></span>` : "";
  const msgs = (p.messages || []).length ? `<ul class="pmsgs">${p.messages.map((m) => `<li class="${esc(m.level)}"><i class="nico ${esc(m.level)}">${NICON[m.level] || "!"}</i>
      <span class="grow">${m.text ? esc(m.text) : L("Unknown message, details on the printer or in the wiki.")}<span class="sub">${esc(m.code)} · <a href="${esc(m.url)}" target="_blank" rel="noopener">${L("Look it up in the Bambu wiki")}</a></span></span></li>`).join("")}</ul>` : "";
  const noz = (n) => n.empty ? `<li class="empty"><span class="rpos">${esc(tr(n.where))}</span><span class="sub">${L("empty")}</span></li>`
    : `<li><span class="rpos">${esc(tr(n.where))}</span><b>${n.diameter != null ? n.diameter.toFixed(1) : "?"} mm</b>
      <span class="sub">${esc([n.flow, n.material].filter(Boolean).map((x) => tr(x)).join(" · "))}</span>
      <span class="rfil">${n.color ? sw(n.color) : ""}<span class="sub">${esc(n.filament || "–")}</span></span>
      <span class="rh">${n.hours} h</span></li>`;
  const rack = (p.rack || []).length ? `<details class="rack" ${rackOpen ? "open" : ""}><summary>${L("Hotend-Rack")} <span class="sub">${L("{0} of {1} used", p.rack.filter((n) => !n.empty).length, p.rack.length)}</span></summary>
      <ul>${(p.mounted || []).map(noz).join("")}${p.rack.map(noz).join("")}</ul></details>` : "";
  return `${active || ((p.state === "finish" || p.state === "failed") && !p.job_done_old) ? `<div class="pjob"><div class="optrow"><b class="grow jobname${jobNameFull ? " full" : ""}" title="${esc(p.name || "")}" data-full="${esc(p.name || L("Print job"))}">${esc(p.name || L("Print job"))}</b><b>${p.progress != null ? Math.round(p.progress) + " %" : ""}</b></div>
      <div class="bar"><i style="width:${Math.max(0, Math.min(100, p.progress || 0))}%"></i></div>
      <div class="sub">${active ? [p.remaining_min != null ? etaHtml(p.remaining_min) : "", p.layers ? L("Layer {0}/{1}", Math.round(p.layer || 0), Math.round(p.layers)) : "", tr(p.speed)].filter(Boolean).join(" · ") : L(p.state === "finish" ? "Print finished" : "Print cancelled")}</div></div>` : ""}
    ${msgs}${pcheck(p.id)}<div class="ptemps">${temps}${air}</div>${pext(p)}${rack}`;
}
function pext(p) {
  const ext = (overview?.ams || []).filter((t) => isExt(t) && t.printer === p.id);
  return ext.length ? `<div class="ams open pext"><h3>${T("extTitle", ext.length)}</h3><ul>${ext.map(amsItem).join("")}</ul></div>` : "";
}
function pmini(p) {
  if (!p.connected) return `<div class="sub">${esc(tr(p.status === "off" ? (p.detail || "off") : p.status === "error" ? "Error" : "not connected"))}</div>`;
  if (!PACTIVE.includes(p.state)) return "";
  const j = (overview?.jobs || []).find((x) => x.printer === p.id && x.active);
  const bad = j ? j.rows.filter((r) => r.state === "tight" || r.state === "short").length : 0;
  return `<div class="pmini ${bad ? "warn" : ""}"><div class="bar"><i style="width:${Math.max(0, Math.min(100, p.progress || 0))}%"></i></div>
    <span class="sub">${p.progress != null ? Math.round(p.progress) + " %" : ""}${p.remaining_min != null ? " · " + etaHtml(p.remaining_min) : ""}${bad ? " · ⚠︎ " + L("Filament running low") : ""}</span></div>`;
}
function drawPrinter() {
  const el = $("#printer"), list = printersShown(), multi = (printerData?.printers || []).length > 1;
  el.hidden = !list.length;
  const nb = document.querySelector('#nav [data-view="printerview"]'); if (nb) nb.hidden = el.hidden;
  // keep the camera nodes alive across redraws (moving them does not interrupt the stream)
  const tg = $("#pcamtoggle") || camToggle(), big = cam.big && $("#camdlg");
  const box = big ? document.createElement("div") : $("#pcam") || cam.box || camBox();   // the large camera dialog keeps the real one
  tg.remove(); box.remove();
  if (el.hidden) { el.innerHTML = ""; el.append(tg); if (!big) el.append(box); else camBig(false); return syncCam(); }
  const open = shownPrinter();
  el.classList.toggle("multi", multi);
  el.innerHTML = list.map((p) => {
    const isOpen = open && p.id === open.id;
    const title = multi ? esc(p.printer_name) + (p.model && p.model !== p.printer_name ? ` <span class="sub">${esc(p.model)}</span>` : "") : `Bambu Lab ${esc(p.model || L("Printer"))}`;
    const pill = p.connected ? `<span class="pill ${pcls(p)}">${esc(tr(p.state_text))}</span>${(p.messages || []).length ? ` <span class="pill bad">${Lp(p.messages.length, "{0} message", "{0} messages")}</span>` : ""}` : "";
    const light = p.connected && p.light && (isOpen || !multi) && !PACTIVE.includes(p.state) ?   // hidden while printing: no accidental switch-off mid-print
       `<button class="plight ${p.light === "on" ? "on" : ""}" data-light="${esc(p.id)}" title="${esc(L(p.light === "on" ? "Turn light off" : "Turn light on"))}" aria-pressed="${p.light === "on"}">${LIGHT_SVG}<span class="vh">${L("Lamp")}</span></button>` : "";
    return `<div class="pcard ${isOpen ? "open" : ""} ${p.connected ? "" : "off"}" data-pid="${esc(p.id)}">
      <div class="phead ${p.connected ? "fold" : ""}">${PRINTER_SVG}<div class="grow"><b>${title}</b><div>${pill}</div></div>${light}${p.connected ? `<span class="chev">›</span>` : ""}</div>
      ${isOpen ? `<div class="pcamslot"></div><div class="pinfo">${pfull(p)}</div>` : pmini(p)}</div>`;
  }).join("");
  const slot = el.querySelector(".pcard.open .pcamslot");
  if (!big) { if (slot) slot.append(tg, box); else el.append(tg, box); } else if (slot) slot.append(tg); else el.append(tg);
  el.querySelectorAll(".phead.fold").forEach((h) => (h.onclick = (e) => {
    if (e.target.closest("[data-light]")) return;
    const id = h.parentElement.dataset.pid;
    if (multi) { pOpen = pOpen === id ? "" : id; setPref("pOpen", pOpen); }
    else { pSingleOpen = !pSingleOpen; setPref("pSingleOpen", pSingleOpen ? "1" : "0"); }
    drawPrinter();
  }));
  el.querySelectorAll("[data-light]").forEach((lb) => (lb.onclick = async (e) => {
    e.stopPropagation();
    const p = list.find((x) => x.id === lb.dataset.light), on = p.light !== "on"; lb.disabled = true;
    try { await api("/api/printer/light", { method: "POST", body: { on, printer: p.id } }); p.light = on ? "on" : "off"; drawPrinter(); setTimeout(loadPrinter, 2500); }
    catch (err) { toast(err.message); lb.disabled = false; }
  }));
  el.querySelectorAll(".pcheck li[data-spool]").forEach((li) => (li.onclick = async () => showSpool(await api(`/api/spools/${li.dataset.spool}`))));
  const d = el.querySelector("details.rack");
  if (d) d.ontoggle = () => { rackOpen = d.open; setPref("rackOpen", rackOpen ? "1" : "0"); };
  fitJobNames();
  syncCam();
}
setInterval(() => { if (!document.hidden && (view === "storage" || view === "printerview")) loadPrinter(); }, 10000);
// phones: the printer card has its own page in the menu instead of sitting in the storage view
// there everything is unfolded (card, camera, AMS); the camera stops again when the page is left
function placePrinter() {
  const el = $("#printer"), ams = $("#ams"), page = $("#printerview");
  if (view === "printerview") {
    if (el.parentElement !== page) { page.append(el, ams); cam.open = true; }
  } else if (el.parentElement === page) { $("#panel").after(el, ams); cam.open = false; }
  if (printerData) drawPrinter();
  if (overview) drawAms();
}
NARROW_STORAGE.addEventListener?.("change", (e) => { if (!e.matches && view === "printerview") showView("storage"); placeClimate(); });
// phones: the climate card sits below the cabinets instead of above them
function placeClimate() {
  const c = $("#climate");
  if (NARROW_STORAGE.matches) { if (c.parentElement !== $("#storage")) $("#logwrap").before(c); }
  else if (c.parentElement !== $(".side")) $(".side").append(c);
}
placeClimate();
loadPrinter();

// ------------------------------------------------------------ options: categories, search, collapsible sections
// Simple 24px stroke icons (drawn for PixxelSpool), used in the options navigation and section titles.
const ICONS = {
  box: '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  printer: '<rect x="3.5" y="3" width="17" height="18" rx="2.5"/><rect x="6.5" y="6" width="11" height="10" rx="1"/><path d="M10.5 6v2.2l1.5 1.3 1.5-1.3V6"/><path d="M8.5 14h7"/><path d="M7.5 18.5h3"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  server: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
  plus: '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
  tag: '<path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z"/><circle cx="8" cy="8" r="1.5"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
  check: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 13l2 2 4-4"/>',
  spool: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>',
  nfc: '<path d="M6 8a6 6 0 0 0 0 8M9.5 10a2.5 2.5 0 0 0 0 4M18 8a6 6 0 0 1 0 8M14.5 10a2.5 2.5 0 0 1 0 4"/>',
  home: '<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
  layout: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M12 9v12"/>',
  alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  drop: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  save: '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v5h7V3M8 21v-7h8v7"/>',
  cloud: '<path d="M7 18a5 5 0 1 1 1-9.9A6 6 0 0 1 19 10a4 4 0 0 1-1 8z"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14-5L4 8M4 4v4h4M4 13a8 8 0 0 0 14 5l2-2M20 20v-4h-4"/>',
  file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
  power: '<path d="M12 3v9"/><path d="M6.5 7a8 8 0 1 0 11 0"/>',
  scale: '<path d="M12 4v16M5 20h14M4 8h16"/><path d="m4 8-2 6a3 3 0 0 0 4 0zM20 8l-2 6a3 3 0 0 0 4 0z"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14"/>',
  code: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/>',
  bug: '<rect x="7" y="7" width="10" height="13" rx="5"/><path d="M12 7V4M9 4l1 3M15 4l-1 3M3 12h4M17 12h4M4 18l3-2M20 18l-3-2"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  cash: '<rect x="2.5" y="6" width="19" height="12" rx="2"/><circle cx="12" cy="12" r="2.6"/><path d="M6 12h.01M18 12h.01"/>',
  truck: '<path d="M2 6h12v10H2z"/><path d="M14 9h4l3 3.5V16h-7"/><circle cx="6" cy="17.5" r="2"/><circle cx="17" cy="17.5" r="2"/>',
  scan: '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><path d="M7 12h10"/>',
  shelf: '<path d="M4 3v18M20 3v18M4 11h16M4 20h16"/><circle cx="9" cy="8" r="2.2"/><circle cx="15" cy="8" r="2.2"/><circle cx="12" cy="17" r="2.2"/>',
  contrast: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" stroke="none"/>',
  heat: '<path d="M7 20c-2-3 2-5 0-8s2-5 0-8M12 20c-2-3 2-5 0-8s2-5 0-8M17 20c-2-3 2-5 0-8s2-5 0-8"/>',
  nas: '<rect x="4" y="3" width="16" height="12" rx="2"/><path d="M8 7h8M8 11h3M12 15v3M5 21h14M12 18v3"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M12 15h5"/>',
  download: '<path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/>',
  lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5M12 14.5v2.5"/>',
  heart: '<path d="M12 20s-7.5-4.6-9.2-9.4A4.9 4.9 0 0 1 12 6.3a4.9 4.9 0 0 1 9.2 4.3C19.5 15.4 12 20 12 20z"/>',
  cup: '<path d="M4 9h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z"/><path d="M17 10.5h1.5a2.5 2.5 0 0 1 0 5H17M8 3.5v2.5M12 3.5v2.5"/>',
  store: '<path d="M3 10 12 4l9 6"/><path d="M5 9.5V20h14V9.5"/><path d="M9 20v-5h6v5"/>',
};
const icon = (k) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[k] || ICONS.info}</svg>`;
const TOOL_ICONS = {
  manualtool: "plus", brandtool: "tag", pricetool: "cash", delivtool: "truck", batchtool: "scan", audittool: "check", spoolstool: "spool",
  bambutool: "printer", readertool: "nfc", hatool: "home", remotetool: "globe", pushtool: "bell",
  layouttool: "grid", warntool: "alert", shoptool: "list", viewtool: "contrast", langtool: "globe", helptool: "info",
  backuptool: "save", offsitetool: "nas", authtool: "lock", updatetool: "download", logtool: "terminal", systool: "power", resettool: "trash",
  abouttool: "info", legaltool: "scale", usedtool: "trash",
};
$("#donatebtn")?.addEventListener("click", () => showDonate(false));
document.querySelectorAll("#tools [data-ico]").forEach((el) => { if (el.classList.contains("ico")) el.innerHTML = icon(el.dataset.ico); });
document.querySelectorAll("#tools .optcat > .tool").forEach((tool) => {
  const h = tool.querySelector(":scope > h3");
  if (!h || tool.parentElement.querySelectorAll(":scope > .tool").length === 1) return;   // alone in its category: always open
  if (tool.classList.contains("nofold")) {   // always open, but with the same icon in the title
    h.classList.add("otitlerow");
    const t = document.createElement("span"); t.className = "otitle";
    while (h.firstChild) t.append(h.firstChild);
    h.append(t); h.insertAdjacentHTML("afterbegin", `<span class="oico">${icon(TOOL_ICONS[tool.id])}</span>`);
    if (h.dataset.t) { t.dataset.t = h.dataset.t; delete h.dataset.t; }
    return;
  }
  const body = document.createElement("div"); body.className = "foldbody";
  while (h.nextSibling) body.append(h.nextSibling);
  tool.append(body);
  tool.classList.add("foldbox", "optfold");
  h.classList.add("fold");
  const title = document.createElement("span"); title.className = "otitle";
  while (h.firstChild) title.append(h.firstChild);
  h.insertAdjacentHTML("afterbegin", `<span class="oico">${icon(TOOL_ICONS[tool.id])}</span>`);
  h.append(title);
  h.insertAdjacentHTML("beforeend", `<span class="sub foldsum"></span><span class="chev">›</span>`);
  // keep data-t on the title so translation still applies
  if (h.dataset.t) { title.dataset.t = h.dataset.t; delete h.dataset.t; }
  h.onclick = () => { tool.classList.toggle("open"); if (tool.id === "logtool" && tool.classList.contains("open")) loadLogs();
    if (tool.id === "usedtool" && tool.classList.contains("open")) loadUsedUp();
    if (tool.id === "systool" && tool.classList.contains("open")) loadSystem(); };
});
let optCat = "stock";
function drawOptNav() {
  $("#optnav").innerHTML = [...document.querySelectorAll("#tools .optcat")].map((c) =>
    `<button data-cat="${c.dataset.cat}" class="${c.dataset.cat === optCat ? "on" : ""}">${icon(c.dataset.ico)}<span>${esc(c.querySelector("h2").textContent)}</span></button>`).join("");
  $("#optnav").querySelectorAll("button").forEach((b) => (b.onclick = () => { optCat = b.dataset.cat; $("#optq").value = ""; filterOpts(); window.scrollTo(0, 0); }));
}
// Search: matches section titles, descriptions, labels and button texts across all categories.
function filterOpts() {
  const q = $("#optq").value.trim().toLowerCase();
  document.body.classList.toggle("optsearching", !!q);
  let hits = 0;
  document.querySelectorAll("#tools .optcat").forEach((c) => {
    let any = false;
    c.querySelectorAll(":scope > .tool").forEach((t) => {
      const hit = !q || t.textContent.toLowerCase().includes(q) || [...t.querySelectorAll("[placeholder]")].some((i) => i.placeholder.toLowerCase().includes(q));
      t.hidden = !hit; any = any || hit; if (hit && q) hits++;
    });
    c.hidden = q ? !any : c.dataset.cat !== optCat;
  });
  $("#optnone").hidden = !q || hits > 0;
  // a single hit opens right away
  if (q && hits === 1) document.querySelector("#tools .optcat:not([hidden]) > .tool:not([hidden])")?.classList.add("open");
  $("#optnav").querySelectorAll("button").forEach((b) => b.classList.toggle("on", !q && b.dataset.cat === optCat));
  // phones: keep the active chip visible in the scrolling row
  const on = $("#optnav button.on"), nav = $("#optnav");
  if (on && nav.scrollWidth > nav.clientWidth) nav.scrollLeft = on.offsetLeft - nav.offsetLeft - 10;
}
$("#optq").oninput = filterOpts;
$("#optq").onkeydown = (e) => { if (e.key === "Escape") { $("#optq").value = ""; filterOpts(); } };
// entering Options: every section starts collapsed, search cleared
function resetOpts() {
  document.querySelectorAll("#tools .tool.optfold").forEach((t) => t.classList.remove("open"));
  $("#optq").value = ""; drawOptNav(); filterOpts();
}
// jump to one section (e.g. from a notification): its category, opened and scrolled into view
function openOpt(id) {
  const t = document.getElementById(id);
  if (!t) return;
  showView("tools");
  optCat = t.closest(".optcat")?.dataset.cat || optCat; drawOptNav(); filterOpts();
  t.classList.add("open"); t.scrollIntoView({ block: "start" });
  if (id === "logtool") loadLogs();
}
resetOpts();

// ------------------------------------------------------------ app password (Options › System)
var authSt = null;   // var: drawOptSums() may run before this line
async function loadAuth() { try { authSt = await api("/api/auth"); } catch (e) { return; } drawAuth(); drawOptSums(); drawRemote(); }
function drawAuth() {
  const box = $("#authbox"); if (!box || !authSt) return;
  const pw = (id, ph, ac = "new-password") => `<input id="${id}" type="password" autocomplete="${ac}" placeholder="${esc(ph)}">`;
  box.innerHTML = authSt.enabled
    ? `<div class="optrow"><span>${L("Password")}</span><b>${L("On")}</b></div>
       <div class="actions"><button id="auCode">${L("New recovery code")}</button>
         <button id="auOut">${L("Sign out")}</button><button class="danger" id="auOff">${L("Turn off")}</button></div>
       <details class="auchange"><summary>${L("Change password")}</summary>
         <div class="authform">${pw("auCur", L("Current password"), "current-password")}${pw("auNew", L("New password"))}</div>
         <div class="actions"><button class="primary" id="auChange">${L("Change password")}</button></div></details>
       <div id="pkbox" class="pkbox"></div>`
    : `<div class="authform">${pw("auNew", L("New password (at least 6 characters)"))}${pw("auNew2", L("Repeat password"))}</div>
       <div class="actions"><button class="primary" id="auOn">${L("Turn on password")}</button></div>
       <p class="sub">${L("Once the password is on, you can also sign in with a passkey (fingerprint, face or device PIN). Only works with Tailscale switched on and PixxelSpool opened over https.")}</p>`;
  if (authSt.enabled) loadPasskeys();
  const post = (url, body) => api(url, { method: "POST", body });
  const cur = () => $("#auCur")?.value || "";
  if ($("#auOn")) $("#auOn").onclick = async () => {
    if ($("#auNew").value !== $("#auNew2").value) return toast(L("The two passwords are not the same"));
    try { const r = await post("/api/auth/password", { password: $("#auNew").value }); await showRecoveryCode(r.code); loadAuth(); toast(L("Password is on")); }
    catch (e) { toast(e.message); }
  };
  if ($("#auChange")) $("#auChange").onclick = async () => {
    try { const r = await post("/api/auth/password", { current: cur(), password: $("#auNew").value }); await showRecoveryCode(r.code); loadAuth(); toast(L("Password changed")); }
    catch (e) { toast(e.message); }
  };
  if ($("#auCode")) $("#auCode").onclick = async () => {
    const current = await askCurrentPw(L("New recovery code"), L("The old code stops working. Please enter your current password."));
    if (current == null) return;
    try { const r = await post("/api/auth/recovery-code", { current }); await showRecoveryCode(r.code); } catch (e) { toast(e.message); }
  };
  if ($("#auOut")) $("#auOut").onclick = async () => { await post("/api/auth/logout", {}).catch(() => {}); location.reload(); };
  if ($("#auOff")) $("#auOff").onclick = async () => {
    const current = await askCurrentPw(L("Turn off password"), L("Turn off the password? Then anyone in your network can open PixxelSpool again.") + " " + L("Passkeys are removed too."), { ok: L("Turn off"), danger: true });
    if (current == null) return;
    try { await post("/api/auth/off", { current }); loadAuth(); toast(L("Password is off")); } catch (e) { toast(e.message); }
  };
}
// asks for the current password right where it is needed (null = cancelled)
async function askCurrentPw(title, text, o = {}) {
  const v = await ask(text, { title, input: { type: "password", placeholder: L("Current password") }, ok: o.ok || L("OK"), danger: o.danger });
  if (v == null) return null;
  if (!v) { toast(L("Please enter your current password.")); return null; }
  return v;
}
loadAuth();

// passkeys in Options › System › Password (only while the password is on)
async function loadPasskeys() {
  const box = $("#pkbox"); if (!box) return;
  let d; try { d = await api("/api/auth/passkeys"); } catch (e) { d = null; }
  const list = d?.passkeys || [], here = d?.rp_id || location.hostname;
  const https = remoteSt?.https && remoteSt.url;
  const why = !authSt.passkey_lib ? L("Passkeys are not available: a package is missing. Please run the update again.")
    : !passkeyOK() ? L("Passkeys need a secure address (HTTPS). Open PixxelSpool via the Tailscale HTTPS address to add or use one – on this address the browser does not allow them.") : "";
  box.innerHTML = `<h4>${L("Passkeys")}</h4>
    <p class="sub">${L("Sign in with fingerprint, face or the device PIN instead of the password. The password and the recovery code keep working. A passkey only works on the address it was added on.")}</p>
    ${list.length ? `<ul class="pklist">${list.map((p) => `<li data-pk="${p.id}"><div><b>${esc(p.name || "Passkey")}</b>
        <span class="sub">${esc(L("added {0}", ago(p.created)))}${p.last_used ? " · " + esc(L("last used {0}", ago(p.last_used))) : ""}${p.rp_id !== here ? ` · <span translate="no">${esc(p.rp_id)}</span>` : ""}</span></div>
        <span class="grow"></span><button class="linkbtn" data-pkren>${L("Rename")}</button><button class="linkbtn" data-pkdel>${L("Remove")}</button></li>`).join("")}</ul>` : ""}
    ${why ? `<p class="sub pkwhy">${esc(why)}${!passkeyOK() && https ? ` <a href="${esc(https)}" translate="no">${esc(https.replace(/^https:\/\//, ""))}</a>` : ""}</p>`
      : `<div class="actions"><button id="pkAdd">${L("Add passkey")}</button></div>`}`;
  $("#pkAdd")?.addEventListener("click", async () => {
    const current = await askCurrentPw(L("Add passkey"), L("Please enter your current password. After that your device asks for fingerprint, face or PIN."));
    if (current == null) return;
    const b = $("#pkAdd"); b.disabled = true;
    try {
      const o = await api("/api/auth/passkeys/options", { method: "POST", body: { current } });
      const credential = await pkCreate(o.options);
      const name = await ask(L("Name for this passkey, e.g. the device it is on:"), { title: L("Passkey added"), input: { value: pkDeviceName() }, noCancel: true });
      await api("/api/auth/passkeys", { method: "POST", body: { ticket: o.ticket, credential, name: name || pkDeviceName() } });
      toast(L("Passkey added")); loadAuth();
    } catch (e) { toast(e.message); b.disabled = false; }
  });
  box.querySelectorAll("[data-pkdel]").forEach((btn) => btn.onclick = async () => {
    const li = btn.closest("li"), name = li.querySelector("b").textContent;
    if (!await askConfirm(L("Remove the passkey “{0}”? You can then no longer sign in with it; the password keeps working.", name), { ok: L("Remove"), danger: true })) return;
    try { await api(`/api/auth/passkeys/${li.dataset.pk}`, { method: "DELETE" }); toast(L("Passkey removed")); loadAuth(); } catch (e) { toast(e.message); }
  });
  box.querySelectorAll("[data-pkren]").forEach((btn) => btn.onclick = async () => {
    const li = btn.closest("li"), name = await ask(L("New name for the passkey:"), { input: { value: li.querySelector("b").textContent } });
    if (name == null || !name.trim()) return;
    try { await api(`/api/auth/passkeys/${li.dataset.pk}`, { method: "PATCH", body: { name } }); loadPasskeys(); } catch (e) { toast(e.message); }
  });
}

// ------------------------------------------------------------ log viewer
let logLvl = "";
async function loadLogs() {
  const box = $("#logbox");
  let j;
  try { j = await api(`/api/logs?level=${logLvl}&q=${encodeURIComponent($("#logq").value.trim())}&limit=400`); }
  catch (e) { box.innerHTML = `<p class="sub">${esc(e.message)}</p>`; return; }
  const t = (ts) => new Date(ts * 1000).toLocaleString(LANG, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: HOUR12() });
  box.innerHTML = j.lines.length ? j.lines.map((l) => `<div class="logline ${l.level.toLowerCase()}"><span class="lts">${t(l.ts)}</span><span class="llv">${esc(l.level)}</span><span class="lnm">${esc(l.name)}</span><span class="lmsg">${esc(l.msg)}</span></div>`).join("")
    : `<p class="sub">${L("No entries.")}</p>`;
  document.querySelectorAll("#loglvl button").forEach((b) => b.classList.toggle("on", b.dataset.lvl === logLvl));
}
document.querySelectorAll("#loglvl button").forEach((b) => (b.onclick = () => { logLvl = b.dataset.lvl; loadLogs(); }));
$("#logreload").onclick = loadLogs;
document.querySelectorAll("[data-logdet]").forEach((b) => (b.onclick = () => saveSettings({ log_detail: b.dataset.logdet === "1" }).then(loadLogs)));
$("#logq").oninput = () => { clearTimeout(loadLogs.t); loadLogs.t = setTimeout(loadLogs, 250); };

// ------------------------------------------------------------ remote access (Tailscale)
let remoteSt = null;
async function loadRemote() { try { remoteSt = await api("/api/remote"); } catch (e) { remoteSt = { installed: true, state: "error", detail: e.message }; } drawRemote(); drawOptSums(); if (overview) drawStats();  if (authSt?.enabled && !passkeyOK()) loadPasskeys(); }
// for the status menu: on start and then every 2 minutes
async function pollRemote() { try { remoteSt = await api("/api/remote"); } catch (e) { return; } if (overview) drawStats(); }
pollRemote(); setInterval(pollRemote, 120000);
async function remoteAct(action, btn) {
  if (action === "logout" && !await askConfirm(L("Sign out of remote access? You will have to sign in again afterwards."), { ok: L("Sign out"), danger: true })) return;
  if (btn) { btn.disabled = true; btn.textContent = L("One moment …"); }
  try { remoteSt = await api("/api/remote", { method: "POST", body: { action } }); } catch (e) { toast(tr(e.message)); }
  drawRemote(); drawOptSums();
}
function drawRemote() {
  const box = $("#remotebox"), r = remoteSt; if (!box || !r) return;
  const btn = (a, t, cls = "") => `<button class="${cls}" data-ra="${a}">${L(t)}</button>`;
  const sw = (on) => `<div class="optrow"><span>${L("Remote access")}</span><div class="seg on-always"><button data-ra="on" class="${on ? "on" : ""}">${L("On")}</button><button data-ra="off" class="${on ? "" : "on"}">${L("Off")}</button></div></div>`;
  let h = "";
  if (!r.installed) {
    h = overview?.host?.kind === "windows"
      ? `<p class="sub">${L("For access on the go, install Tailscale for Windows and sign in, then reload this page.")}</p><div class="actions"><a class="btn" href="https://tailscale.com/download/windows" target="_blank" rel="noopener">${L("Download Tailscale")}</a></div>`
      : overview?.host?.kind === "mac"
      ? `<p class="sub">${L("For access on the go, install Tailscale for Mac and sign in, then reload this page.")}</p><div class="actions"><a class="btn" href="https://tailscale.com/download/mac" target="_blank" rel="noopener">${L("Download Tailscale")}</a></div>`
      : `<p class="sub">${L("Tailscale is not installed on this Pi yet. Run this once on the Pi in the PixxelSpool folder:")}</p><pre class="cmd">./install.sh --remote</pre>`;
  } else if (r.state === "Running") {
    // reachable from every device in the tailnet: a password is strongly recommended
    const nopw = authSt && !authSt.enabled ? `<div class="pwhint"><p class="uperr">${L("Recommended: set a password. Every device in your Tailscale network (and everyone you share it with) can open PixxelSpool.")}</p><div class="actions"><button class="small" data-pwgo>${L("Set password")}</button></div></div>` : "";
    h = sw(true) + `<p class="sub">${L("Connected as {0}", esc(r.host || r.ip))}</p>` + nopw +
      (r.https ? `<p>${L("Address for on the go:")}<br><a href="${esc(r.url)}" target="_blank" rel="noopener"><b>${esc(r.url)}</b></a></p>
        <div class="rqr">${r.qr || ""}</div><p class="sub">${L("Scan it with the iPhone camera, open it and save it as an app via “Share → Add to Home Screen”.")}</p>
        <div class="actions">${btn("https_off", "Turn off HTTPS address")}${btn("logout", "Sign out", "danger")}</div>`
      : `<p class="sub">${L("No HTTPS address yet. You need it for the home screen app and for push notifications.")}</p>
        <p class="sub">${L("Allow it once in your Tailscale account first: under DNS, turn on “MagicDNS” and “HTTPS Certificates”.")} <a href="https://login.tailscale.com/admin/dns" target="_blank" rel="noopener">login.tailscale.com/admin/dns</a></p>
        <div class="actions">${btn("https_on", "Turn on HTTPS address", "primary")}${btn("logout", "Sign out", "danger")}</div>`);
  } else if (r.state === "Stopped") {
    h = sw(false) + `<p class="sub">${L("Switched off. The sign-in is kept.")}</p>`;
  } else if (r.state === "error") {
    h = `<p class="sub">${L("Status: {0}", L("Error"))} · ${esc(tr(r.detail || ""))}</p><div class="actions">${btn("reload", "Check again")}</div>`;
  } else if (r.auth_url) {
    h = `<p>${L("Now sign in to Tailscale, on this device or via QR code on your phone:")}<br><a href="${esc(r.auth_url)}" target="_blank" rel="noopener"><b>${L("Open sign-in link")}</b></a></p>
      <div class="rqr">${r.qr || ""}</div><p class="sub">${L("This page updates by itself after you sign in.")}</p>`;
  } else {
    h = `<p class="sub">${L("Not set up yet. You need a free Tailscale account; you can sign in with Google, Apple, GitHub or Microsoft.")}</p>
      <div class="actions">${btn("login", "Set up", "primary")}</div>`;
  }
  box.innerHTML = h;
  box.querySelector("[data-pwgo]")?.addEventListener("click", () => openOpt("authtool"));
  box.querySelectorAll("[data-ra]").forEach((b) => (b.onclick = () => {
    const a = b.dataset.ra;
    if (a === "reload") return loadRemote();
    if ((a === "on" && r.state === "Running") || (a === "off" && r.state === "Stopped")) return;
    remoteAct(a, b);
  }));
  clearTimeout(drawRemote.t);
  if (r.installed && r.state !== "Running" && r.auth_url && view === "tools") drawRemote.t = setTimeout(loadRemote, 4000);   // wait for the sign-in
}
// ------------------------------------------------------------ custom brands
let brandData = null, brandEdit = null, colorEdit = null;   // colorEdit: color being changed { id, line_id, ... }
const hexOk = (v) => /^#?[0-9a-fA-F]{6}$/.test(String(v).trim());
const hexNorm = (v) => "#" + String(v).trim().replace(/^#/, "").toUpperCase();
function colorRow(ln) {
  // one row per line to add a color, or to change the color picked above (color picker and HEX field stay in sync)
  const c = colorEdit?.line_id === ln.id ? colorEdit : null, hex = c?.hex || "#888888";
  return `<div class="inline addcolor${c ? " editing" : ""}"><input data-cname="${ln.id}" placeholder="${esc(L("Color name"))}" value="${esc(c?.color_name || "")}">
    <input type="color" data-chex="${ln.id}" value="${esc(hex.toLowerCase())}" aria-label="${esc(L("Color"))}"><input class="hexin" data-chext="${ln.id}" value="${esc(hex.toUpperCase())}" maxlength="7" autocapitalize="characters" spellcheck="false" aria-label="HEX">
    <input data-csku="${ln.id}" placeholder="${esc(L("Item no. (optional)"))}" value="${esc(c?.sku || "")}">
    ${c ? `<button class="small primary" data-cadd="${ln.id}">${L("Save color")}</button><button class="small" data-ccancel>${L("Cancel")}</button>` : `<button class="small" data-cadd="${ln.id}">+ ${L("Color")}</button>`}</div>`;
}
async function loadBrands() { try { brandData = await api("/api/brands"); } catch (e) { return; } drawBrands(); }
async function editBrandLine(lineId) {
  // jump to Options › Other brands with the line's form open (e.g. to enter the empty spool weight)
  panel = null; render(); highlight(null);
  openOpt("brandtool");
  if (!brandData) await loadBrands();
  const ln = brandData?.lines.find((x) => x.id == lineId);
  if (ln) { $(`[data-bedit="${ln.id}"]`)?.click(); }
  setTimeout(() => { const f = $("#bfSpool") || $("#brandtool"); f?.scrollIntoView({ block: "center", behavior: "smooth" }); f?.focus?.({ preventScroll: true }); }, 120);
}
// How own spools get an NFC sticker, in the order that works (shown after the first own line and via the help link)
function brandTagHelp() {
  ask(`<div class="cabhelp brandhelp">
    <p>${L("Spools from other brands usually have no tag PixxelSpool can read. With a cheap NFC sticker (NTAG213/215) they work just like Bambu spools: place them on the reader and PixxelSpool knows which spool it is.")}</p>
    <ol class="steps">
      <li>${L("<b>Add colors:</b> add the colors you have to the line you just created.")}</li>
      <li>${L("<b>Add the spool:</b> under “Add spool manually” choose brand, line and color. The spool gets its slot.")}</li>
      <li>${L("<b>Stick on a sticker:</b> put an NFC sticker on the spool, e.g. on the side.")}</li>
      <li>${L("<b>Link it:</b> place the sticker on the reader and pick the spool from the list. Or open the spool and tap “Add tag”.")}</li>
    </ol>
    <p class="sub">${L("From then on it's like a Bambu spool: place it on the reader to store it, take it out or see its details. Without a sticker, spools are simply managed by hand.")}</p>
  </div>`, { title: L("Own spools with NFC stickers"), block: true, noCancel: true, ok: L("Got it") });
}
function drawBrands() {
  const box = $("#brandbox"), d = brandData; if (!box || !d) return;
  const f = brandEdit;
  const form = f ? `<div class="brandform">
      <div class="optgrid">
        <span class="sub">${L("Brand")}</span><input id="bfBrand" value="${esc(f.brand || "")}" placeholder="${esc(L("e.g. Sunlu, eSun, Polymaker …"))}">
        <span class="sub">${L("Material")}</span><select id="bfMat">${d.materials.map((m) => `<option ${m === f.material ? "selected" : ""}>${esc(m)}</option>`).join("")}</select>
        <span class="sub">${L("Suffix (optional)")}</span><input id="bfExtra" value="${esc(f.extra || "")}" placeholder="${esc(L("e.g. Silk, Matte, HS"))}">
        <span class="sub">${L("Filament per spool")}</span><span class="inline"><input id="bfNet" type="number" inputmode="numeric" value="${f.net_g ?? 1000}"> g</span>
        <span class="sub">${L("Empty spool weight")}</span><span class="inline"><input id="bfSpool" type="number" inputmode="numeric" value="${f.spool_g ?? ""}" placeholder="${esc(L("e.g. 180"))}"> g</span>
        <span class="sub" title="${esc(L("Recommended retail price per spool"))}">${L("MSRP")}</span><span class="inline"><input id="bfPrice" inputmode="decimal" data-money value="${esc(priceStr(f.price))}" placeholder="19,99"> ${esc(SET().currency || "€")}</span>
        <span class="sub">${L("Drying")}</span><span class="inline"><input id="bfDryT" type="number" inputmode="numeric" value="${f.dry_temp ?? ""}" placeholder="55"> °C <input id="bfDryH" type="number" inputmode="numeric" value="${f.dry_hours ?? ""}" placeholder="8"> h</span>
        <span class="sub">${L("Shop link (optional)")}</span><input id="bfShop" value="${esc(f.shop_url || "")}" placeholder="https://…">
      </div>
      <div class="actions"><button class="primary" id="bfSave">${L("Save")}</button><button id="bfCancel">${L("Cancel")}</button></div></div>` : "";
  const lines = d.lines.map((ln) => `<div class="brandline" data-line="${ln.id}">
      <div class="optrow"><b class="grow">${esc(ln.name)}</b><span class="inline"><button class="small" data-bedit="${ln.id}">${L("Edit")}</button><button class="small danger" data-bdel="${ln.id}">×</button></span></div>
      <p class="sub">${[ln.net_g ? `${ln.net_g} g` : "", ln.spool_g != null ? L("spool {0} g", ln.spool_g) : "", ln.price != null ? L("MSRP {0}", money(ln.price)) : "", ln.dry_temp ? `${L("Drying")} ${ln.dry_temp} °C${ln.dry_hours ? "/" + ln.dry_hours + " h" : ""}` : ""].filter(Boolean).join(" · ")}</p>
      <div class="bcolors">${ln.colors.map((c) => `<span class="chip${colorEdit?.id === c.id ? " editing" : ""}"><button class="chipedit" data-cedit="${c.id}" data-cline="${ln.id}" title="${esc(L("Edit color"))}">${sw(c)}${esc(c.color_name)}${c.sku ? ` <span class="sub">${esc(c.sku)}</span>` : ""}</button>${c.spools ? ` <span class="sub">· ${c.spools}</span>` : ` <button class="xbtn" data-cdel="${c.id}" title="${esc(L("Delete color"))}">×</button>`}</span>`).join("")}</div>
      ${colorRow(ln)}
    </div>`).join("");
  box.innerHTML = (d.lines.length ? lines : `<p class="sub">${L("No other brands yet.")}</p>`) + form +
    (f ? "" : `<div class="actions"><button id="bfNew">+ ${L("Add line")}</button><button class="small" id="bfHelp">${L("How do NFC stickers work?")}</button></div>`);
  const bh = $("#bfHelp"); if (bh) bh.onclick = brandTagHelp;
  const nb = $("#bfNew"); if (nb) nb.onclick = () => { brandEdit = { net_g: 1000, material: "PLA" }; drawBrands(); $("#bfBrand").focus(); };
  if (f) {
    $("#bfCancel").onclick = () => { brandEdit = null; drawBrands(); };
    $("#bfSave").onclick = async () => {
      const body = { id: f.id, brand: $("#bfBrand").value, material: $("#bfMat").value, extra: $("#bfExtra").value, net_g: $("#bfNet").value,
        spool_g: $("#bfSpool").value, price: $("#bfPrice").value, dry_temp: $("#bfDryT").value, dry_hours: $("#bfDryH").value, shop_url: $("#bfShop").value };
      const first = !f.id && !d.lines.length;   // the very first own line: explain stickers once
      try { await api("/api/brands/line", { method: "POST", body }); brandEdit = null; await loadBrands(); loadProducts(); toast(L("Saved")); if (first) brandTagHelp(); }
      catch (e) { toast(tr(e.message)); }
    };
  }
  box.querySelectorAll("[data-bedit]").forEach((b) => (b.onclick = () => {
    const ln = d.lines.find((x) => x.id == b.dataset.bedit);
    const rest = ln.name.slice(ln.brand.length).trim(), mat = d.materials.filter((m) => rest === m || rest.startsWith(m + " ")).sort((a, z) => z.length - a.length)[0] || "Other";
    brandEdit = { ...ln, material: mat, extra: rest.slice(mat.length).trim() }; drawBrands();
  }));
  box.querySelectorAll("[data-bdel]").forEach((b) => (b.onclick = async () => {
    if (!await askConfirm(L("Delete the line with all its colors?"), { ok: L("Delete"), danger: true })) return;
    try { await api(`/api/brands/line/${b.dataset.bdel}`, { method: "DELETE" }); await loadBrands(); loadProducts(); } catch (e) { toast(tr(e.message)); }
  }));
  box.querySelectorAll("[data-chex]").forEach((pk) => {
    const txt = box.querySelector(`[data-chext="${pk.dataset.chex}"]`);
    pk.oninput = () => { txt.value = pk.value.toUpperCase(); txt.classList.remove("bad"); };
    txt.oninput = () => { const ok = hexOk(txt.value); txt.classList.toggle("bad", !!txt.value.trim() && !ok); if (ok) pk.value = hexNorm(txt.value).toLowerCase(); };
  });
  box.querySelectorAll("[data-cedit]").forEach((b) => (b.onclick = () => {
    const ln = d.lines.find((x) => x.id == b.dataset.cline), c = ln?.colors.find((x) => x.id == b.dataset.cedit); if (!c) return;
    colorEdit = colorEdit?.id === c.id ? null : { ...c, line_id: ln.id }; drawBrands();
    box.querySelector(`[data-cname="${ln.id}"]`)?.focus();
  }));
  box.querySelectorAll("[data-ccancel]").forEach((b) => (b.onclick = () => { colorEdit = null; drawBrands(); }));
  box.querySelectorAll("[data-cadd]").forEach((b) => (b.onclick = async () => {
    const id = b.dataset.cadd, name = box.querySelector(`[data-cname="${id}"]`).value, hx = box.querySelector(`[data-chext="${id}"]`).value;
    if (!hexOk(hx)) return toast(L("Please enter the color as HEX, e.g. #1A2B3C"));
    const body = { name, hex: hexNorm(hx), sku: box.querySelector(`[data-csku="${id}"]`).value };
    if (colorEdit?.line_id == id) body.id = colorEdit.id; else body.line_id = Number(id);
    try { await api("/api/brands/color", { method: "POST", body }); colorEdit = null; await loadBrands(); loadProducts(); toast(L("Saved")); }
    catch (e) { toast(tr(e.message)); }
  }));
  box.querySelectorAll("[data-cdel]").forEach((b) => (b.onclick = async () => {
    try { await api(`/api/brands/color/${b.dataset.cdel}`, { method: "DELETE" }); await loadBrands(); loadProducts(); } catch (e) { toast(tr(e.message)); }
  }));
}

// ------------------------------------------------------------ statistics
let statsData = null, priceRows = null, delivRows = null, delivAll = false;
const priceStr = (v) => v != null && v !== "" && isFinite(Number(v)) ? Number(v).toFixed(2).replace(".", LANG === "en" ? "." : ",") : (v ?? "");
// price fields: a whole number like "9" becomes "9,00" when the field is left (inputs marked with data-money)
document.addEventListener("focusout", (e) => {
  const i = e.target;
  if (!(i instanceof HTMLInputElement) || !i.hasAttribute("data-money")) return;
  const t = i.value.trim().replace(/\s|€/g, "");
  if (!/^\d+([.,]\d{0,2})?$/.test(t)) return;
  const f = priceStr(Number(t.replace(",", ".")));
  if (f !== i.value) { i.value = f; i.dispatchEvent(new Event("input", { bubbles: true })); }
});
async function loadStatsView() {
  try { statsData = await api("/api/stats"); } catch (e) { toast(e.message); return; }
  drawStatsView();
}
function bars(rows, key, fmtv, pick = false) {
  const max = Math.max(1, ...rows.map((m) => m[key] || 0));
  return `<div class="months${pick ? " pick" : ""}">${rows.map((m) => `<div class="mbar"${pick && m.prints ? ` data-month="${m.month}" role="button" tabindex="0"` : ""}><i style="height:${(100 * (m[key] || 0) / max).toFixed(0)}%"></i><b>${m[key] ? fmtv(m[key]) : ""}</b><span>${m.month.slice(5)}/${m.month.slice(2, 4)}</span></div>`).join("")}</div>`;
}
function drawStatsView() {
  const d = statsData, box = $("#statsbox"); if (!d || !box) return;
  const st = d.stock, pt = d.prints_total, kg = gkg;
  const m6 = d.months.slice(-6), costM = d.months.slice(-1)[0];
  const maxMat = Math.max(1, ...st.materials.map((m) => m.grams));
  box.innerHTML = `<div class="kpis">
      <div class="kpi"><span class="sub">${L("Spools in stock")}</span><b>${st.spools}</b></div>
      <div class="kpi"><span class="sub">${L("Filament in stock")}</span><b>${kg(st.grams)}</b></div>
      <div class="kpi"><span class="sub">${L("Stock value")}</span><b>${st.priced ? money(st.value) : "–"}</b>${st.priced < st.spools ? `<span class="sub">${L("{0} of {1} spools with a price", st.priced, st.spools)}</span>` : ""}</div>
      <div class="kpi"><span class="sub">${L("Usage this month")}</span><b>${gkg(costM.grams)}</b>${costM.cost ? `<span class="sub">${money(costM.cost)}</span>` : ""}</div>
      <div class="kpi"><span class="sub">${L("Prints recorded")}</span><b>${pt.count}</b>${pt.cost != null ? `<span class="sub">${money(pt.cost)}</span>` : ""}</div>
    </div>
    <div class="tool"><h3>${L("Usage per month")}</h3>${bars(d.months, "grams", gkg, true)}${pt.count ? `<p class="sub">${L("Tap a month to see its prints and remove a wrong value.")}</p>` : ""}</div>
    <div class="tool"><h3>${L("Cost per month")}</h3>${bars(d.months, "cost", (v) => Math.round(v) + " " + (SET().currency || "€"), true)}
      <p class="sub">${L("Filament used times the spool price.")}</p>
      <h4>${L("Spending on spools")}</h4>${bars(d.months, "spent", (v) => Math.round(v) + " " + (SET().currency || "€"))}
      <p class="sub">${L("Spool prices by month received.")}</p></div>
    ${(d.price_history || []).length ? `<div class="tool" id="pricehist"><h3>${L("Price history")}</h3>
      <div class="phhead"><select id="phline" aria-label="${esc(L("Line"))}">${d.price_history.map((h, i) => `<option value="${i}" ${i === phSel ? "selected" : ""}>${esc(h.line)}</option>`).join("")}</select>
      <span class="sub">${L("Paid per spool, by delivery day.")}</span></div><div id="phchart"></div></div>` : ""}
    <div class="tool"><h3>${L("Stock by material")}</h3><ul class="matbars">${st.materials.map((m) => `<li><span>${esc(m.material)}</span><span class="mb"><i style="width:${(100 * m.grams / maxMat).toFixed(0)}%"></i></span><b>${kg(m.grams)}</b><span class="sub">${Lp(m.spools, "{0} spool", "{0} spools")}</span></li>`).join("")}</ul></div>
    ${d.by_printer.length ? `<div class="tool"><h3>${L("By printer")}</h3><ul class="shop">${d.by_printer.map((b) => `<li><span class="grow">${esc(b.printer)}<span class="sub">${Lp(b.count, "{0} print", "{0} prints")}</span></span><b>${kg(b.grams)}</b><span class="pcost">${b.cost != null ? money(b.cost) : "–"}</span></li>`).join("")}</ul></div>` : ""}
    ${(d.projects || []).length ? `<div class="tool"><h3>${L("Projects")}</h3><p class="sub">${L("Prints you put into a project (open a print below), added up.")}</p>
      <ul class="shop projects">${d.projects.map((x) => `<li><span class="grow">${esc(x.name)}<span class="sub">${Lp(x.count, "{0} print", "{0} prints")} · ${esc(dateShort(x.first))}${x.first.slice(0, 10) !== x.last.slice(0, 10) ? " – " + esc(dateShort(x.last)) : ""}</span></span><b>${gkg(x.grams)}</b><span class="pcost">${x.cost != null ? money(x.cost) : "–"}</span></li>`).join("")}</ul></div>` : ""}
    <div class="tool"><h3>${L("Recent prints")}</h3>${d.prints.length ? `<p class="sub costnote">${L("Costs are estimates from the information available (filament used and spool prices). Electricity, purge waste (flushing) and the prime tower are not included.")}</p>` : ""}${d.prints.length ? `<ul class="shop prints">${d.prints.map((p) => printLi(p, d.by_printer.length)).join("")}</ul>`
      : `<p class="sub">${L("From now on every finished print is recorded with usage and cost (needs the direct printer connection).")}</p>`}</div>`;
  box.querySelectorAll(".months.pick [data-month]").forEach((b) => (b.onclick = b.onkeydown = (e) => {
    if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault(); monthPrints(b.dataset.month);
  }));
  box.querySelectorAll("ul.prints [data-pdel]").forEach((b) => (b.onclick = () => delPrint(b.closest("li"))));
  box.querySelectorAll("ul.prints [data-pren]").forEach((b) => (b.onclick = () => renamePrint(b.closest("li"))));
  bindPrintRows(box);
  if ($("#phline")) { $("#phline").onchange = () => { phSel = +$("#phline").value; drawPriceChart(); }; drawPriceChart(); }
}
// price history of one line: one line through the delivery prices, the line price as a dashed reference
let phSel = 0;
function drawPriceChart() {
  const h = statsData?.price_history?.[phSel] || statsData?.price_history?.[0], el = $("#phchart"); if (!h || !el) return;
  // F13: spools and refills are two lines, so a cheaper refill does not look like a price drop
  const series = [{ key: "spool", name: L("Spool"), pts: h.points || [] }, { key: "refill", name: L("Refill"), pts: h.refill_points || [] }].filter((s) => s.pts.length);
  const all = series.flatMap((s) => s.pts), W = 640, H = 200, pl = 48, pr = 12, pt = 12, pb = 28;
  const t = (d) => new Date(d + "T12:00").getTime(), days = all.map((p) => t(p.day)), t0 = Math.min(...days), t1 = Math.max(...days);
  const vals = all.map((p) => p.price).concat(h.line_price != null ? [h.line_price] : []);
  let lo = Math.min(...vals), hi = Math.max(...vals); const pad = Math.max(1, (hi - lo) * 0.15); lo = Math.max(0, Math.floor(lo - pad)); hi = Math.ceil(hi + pad);
  const x = (d) => pl + (t1 === t0 ? (W - pl - pr) / 2 : (t(d) - t0) / (t1 - t0) * (W - pl - pr)), y = (v) => pt + (hi - v) / (hi - lo || 1) * (H - pt - pb);
  const ticks = [lo, (lo + hi) / 2, hi];
  const cur = SET().currency || "€";
  const first = all.reduce((a, p) => (t(p.day) < t(a.day) ? p : a)), last = all.reduce((a, p) => (t(p.day) > t(a.day) ? p : a));
  const rows = series.flatMap((s) => s.pts.map((p) => ({ ...p, kind: s.name }))).sort((a, b) => t(a.day) - t(b.day));
  el.innerHTML = `${series.length > 1 ? `<div class="phlegend">${series.map((s) => `<span class="ph-${s.key}"><i></i>${esc(s.name)}</span>`).join("")}</div>` : ""}<svg class="phsvg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(L("Price history"))} ${esc(h.line)}">
    ${ticks.map((v) => `<line class="phgrid" x1="${pl}" x2="${W - pr}" y1="${y(v)}" y2="${y(v)}"/><text class="phax" x="${pl - 6}" y="${y(v) + 4}" text-anchor="end">${Math.round(v)} ${esc(cur)}</text>`).join("")}
    ${h.line_price != null ? `<line class="phref" x1="${pl}" x2="${W - pr}" y1="${y(h.line_price)}" y2="${y(h.line_price)}"/><text class="phax" x="${W - pr}" y="${y(h.line_price) - 5}" text-anchor="end">${esc(L("Line price"))} ${esc(money(h.line_price))}</text>` : ""}
    ${series.map((s, si) => `<g class="ph-${s.key}">${s.pts.length > 1 ? `<polyline class="phline" points="${s.pts.map((p) => `${x(p.day)},${y(p.price)}`).join(" ")}"/>` : ""}
      ${s.pts.map((p, i) => `<g class="phpt" data-s="${si}" data-i="${i}"><circle class="phhit" cx="${x(p.day)}" cy="${y(p.price)}" r="14"/><circle class="phdot" cx="${x(p.day)}" cy="${y(p.price)}" r="4.5"/></g>`).join("")}</g>`).join("")}
    <text class="phax" x="${pl}" y="${H - 8}">${esc(dateShort(first.day))}</text><text class="phax" x="${W - pr}" y="${H - 8}" text-anchor="end">${esc(dateShort(last.day))}</text>
  </svg><div class="phtip" hidden></div>
  <details class="phtable"><summary>${L("As a table")}</summary><table><tr><th>${L("Delivery")}</th>${series.length > 1 ? `<th></th>` : ""}<th>${L("Spools")}</th><th>${L("Price")}</th></tr>${rows.map((p) => `<tr><td>${esc(dateShort(p.day))}</td>${series.length > 1 ? `<td>${esc(p.kind)}</td>` : ""}<td>${p.spools}</td><td>${esc(money(p.price))}</td></tr>`).join("")}</table></details>`;
  const tip = el.querySelector(".phtip"), svg = el.querySelector("svg");
  el.querySelectorAll(".phpt").forEach((g) => {
    const show = () => {
      const s = series[+g.dataset.s], p = s.pts[+g.dataset.i], r = svg.getBoundingClientRect(), k = r.width / W;
      tip.innerHTML = `<b>${esc(money(p.price))}</b>${series.length > 1 ? ` · ${esc(s.name)}` : ""}<br><span class="sub">${esc(dateShort(p.day))} · ${esc(Lp(p.spools, "{0} spool", "{0} spools"))}</span>`;
      tip.hidden = false; tip.style.left = `${x(p.day) * k}px`; tip.style.top = `${y(p.price) * k}px`;
      el.querySelectorAll(".phpt").forEach((o) => o.classList.toggle("on", o === g));
    };
    g.addEventListener("pointerenter", show); g.addEventListener("click", show);
    g.addEventListener("pointerleave", () => { tip.hidden = true; g.classList.remove("on"); });
  });
}
// one recorded print; a click opens the filaments it used with grams and cost (detail rows from stats.py)
const printLi = (p, withPrinter) => `<li data-print="${p.id}" class="prow" tabindex="0" aria-expanded="false"><span class="grow">${esc(p.name || L("Print job"))}<span class="sub">${esc(dateShort(p.ts))}${withPrinter && p.printer ? " · " + esc(p.printer) : ""}${p.state === "failed" ? " · " + L("cancelled") : ""}${p.project ? ` · <span class="pprojtag">${esc(p.project)}</span>` : ""}</span></span>`
  + `<b${!p.grams ? ` title="${esc(L("No amounts were read from the print file"))}"` : ""}>${p.grams ? gkg(p.grams) : "–"}</b><span class="pcost">${p.cost != null ? money(p.cost) : "–"}</span>${prenBtn()}${pdelBtn()}</li>`;
function printDetail(p) {
  const rows = (p.detail || []).filter((x) => x.grams > 0);
  const names = [...new Set((statsData?.projects || []).map((x) => x.name))];
  const proj = `<div class="pproj"><span class="sub">${L("Project")}</span><input data-pproj="${p.id}" list="projnames" value="${esc(p.project || "")}" placeholder="${esc(L("e.g. Gift for Alex"))}" maxlength="80" autocomplete="off">
    <datalist id="projnames">${names.map((n) => `<option value="${esc(n)}">`).join("")}</datalist><button class="small" data-pprojsave="${p.id}">${L("Save")}</button></div>`;
  const fix = `<button class="small" data-pusage="${p.id}">${rows.length ? L("Change amounts") : L("Add amounts")}</button>`;
  if (!rows.length) return `<li class="pdet"><p class="sub">${esc(L("No amounts were read from the print file, so usage and cost are unknown."))} ${fix}</p>${proj}</li>`;
  return `<li class="pdet">${proj}${p.note === "hand" ? `<p class="sub">${L("Amounts entered by hand.")} ${fix}</p>` : ""}<ul>${rows.map((x) => `<li>${x.line ? sw(x) : sw("transparent", "none")}<span class="grow">${x.line ? `${esc(x.line)} ${esc(cname(x))}` : esc(L("Unknown spool"))}${x.slot ? `<span class="sub">${esc(tr(x.slot))}</span>` : ""}</span>`
    + `<b>${gkg(x.grams)}</b><span class="pcost">${x.cost != null ? money(x.cost) : `<span class="sub" title="${esc(L("No price set for this spool"))}">${L("no price")}</span>`}</span></li>`).join("")}</ul></li>`;
}
function bindPrintRows(box, list) {
  box.querySelectorAll("ul.prints li.prow").forEach((li) => (li.onclick = li.onkeydown = (e) => {
    if (e.target.closest("button")) return;
    if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    const nx = li.nextElementSibling;
    if (nx?.classList.contains("pdet")) { nx.remove(); li.setAttribute("aria-expanded", "false"); return; }
    const p = (list || statsData?.prints || []).find((x) => x.id === +li.dataset.print); if (!p) return;
    li.insertAdjacentHTML("afterend", printDetail(p)); li.setAttribute("aria-expanded", "true");
    const inp = li.nextElementSibling.querySelector("[data-pproj]"), btn = li.nextElementSibling.querySelector("[data-pprojsave]");
    const save = async () => {
      try { await api(`/api/prints/${p.id}`, { method: "PATCH", body: { project: inp.value.trim() } }); } catch (err) { toast(tr(err.message)); return; }
      p.project = inp.value.trim() || null; toast(L("Saved")); loadStatsView();
    };
    btn.onclick = save; inp.onkeydown = (ev) => { if (ev.key === "Enter") save(); };
    const fx = li.nextElementSibling.querySelector("[data-pusage]");
    if (fx) fx.onclick = () => usageEditor(li.nextElementSibling, p, list);
  }));
}
// F12: a print whose file could not be read gets its amounts by hand, or from the exported .gcode.3mf
function usageEditor(det, p, list) {
  const spools = allSpools().filter((s) => s.status !== "empty" || (p.detail || []).some((d) => d.spool_id === s.id))
    .sort((a, b) => (b.ams_slot ? 1 : 0) - (a.ams_slot ? 1 : 0) || title(a).localeCompare(title(b)));
  const opt = (sel) => `<option value="">${esc(L("Choose spool …"))}</option>` + spools.map((s) => `<option value="${s.id}"${s.id === sel ? " selected" : ""}>${esc(title(s))}${s.ams_slot ? " · " + esc(tr(s.ams_slot)) : s.slot_id ? " · " + esc(s.slot_id) : ""}</option>`).join("");
  const row = (sid, g) => `<div class="urow"><select>${opt(sid)}</select><input type="number" min="0" step="0.1" inputmode="decimal" value="${g ?? ""}" placeholder="g" aria-label="${esc(L("Grams"))}"><span>g</span><button class="small" data-urm aria-label="${esc(L("Remove"))}">×</button></div>`;
  const start = (p.detail || []).filter((d) => d.grams > 0);
  const box = document.createElement("div"); box.className = "ueditor";
  box.innerHTML = `<p class="sub">${L("Which spools did this print use, and how many grams? Bambu Studio shows the grams after slicing; or load the exported .gcode.3mf.")}</p>
    <div class="urows">${(start.length ? start : [{}]).map((d) => row(d.spool_id, d.grams)).join("")}</div>
    <div class="row"><button class="small" data-uadd>+ ${L("Filament")}</button><label class="btn small">${L("From .gcode.3mf")}<input type="file" accept=".3mf" hidden data-ufile></label>
    <span class="grow"></span><button class="small" data-ucancel>${L("Cancel")}</button><button class="small primary" data-usave>${L("Save")}</button></div>`;
  det.querySelector(".ueditor")?.remove(); det.appendChild(box);
  const rowsEl = box.querySelector(".urows");
  box.onclick = async (e) => {
    if (e.target.closest("[data-urm]")) { e.target.closest(".urow").remove(); if (!rowsEl.children.length) rowsEl.insertAdjacentHTML("beforeend", row()); }
    if (e.target.closest("[data-uadd]")) rowsEl.insertAdjacentHTML("beforeend", row());
    if (e.target.closest("[data-ucancel]")) box.remove();
    if (e.target.closest("[data-usave]")) {
      const rows = [...rowsEl.querySelectorAll(".urow")].map((r) => ({ spool_id: r.querySelector("select").value || null, grams: parseFloat(r.querySelector("input").value.replace(",", ".")) || 0 })).filter((r) => r.grams > 0);
      if (rows.some((r) => !r.spool_id) && !await askConfirm(L("Some amounts have no spool: they count for the grams, but without a price."))) return;
      try { await api(`/api/prints/${p.id}/usage`, { method: "PUT", body: { rows } }); } catch (err) { toast(tr(err.message)); return; }
      toast(L("Saved")); if (list) box.remove(); loadStatsView();
    }
  };
  box.querySelector("[data-ufile]").onchange = async (e) => {
    const f = e.target.files[0]; e.target.value = ""; if (!f) return;
    let data;
    try {
      const res = await fetch("/api/3mf", { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: f });
      data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(tr(data.error || data.detail || res.statusText));
    } catch (err) { toast(err.message); return; }
    if (!products) await loadProducts().catch(() => {});
    const used = (data.filaments || []).filter((x) => x.used && (x.exact_g || x.est_g) > 0);
    if (!used.length) { toast(L("No filament amounts in this file.")); return; }
    if (!data.sliced) toast(L("This file is not sliced: the amounts are an estimate."));
    rowsEl.innerHTML = used.map((x) => {
      const m = tmfMatch(x), sp = m.own.find((s) => s.ams_slot) || m.own[0];
      return row(sp?.id, Math.round((x.exact_g || x.est_g) * 10) / 10);
    }).join("");
  };
}
// rename a recorded print: the job name from the printer does not always fit
const prenBtn = () => `<button class="pdel pren" data-pren title="${esc(L("Rename"))}" aria-label="${esc(L("Rename"))}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/></svg></button>`;
async function renamePrint(li, list) {
  const p = (list || statsData?.prints || []).find((x) => x.id === +li.dataset.print); if (!p) return;
  const name = await ask(L("New name for this print:"), { title: L("Rename print"), ok: L("Save"), input: { value: p.name || "", placeholder: L("Print job") } });
  if (name == null || name.trim() === (p.name || "")) return;
  try { await api(`/api/prints/${p.id}`, { method: "PATCH", body: { name: name.trim() } }); } catch (e) { toast(tr(e.message)); return; }
  p.name = name.trim();
  const t = li.querySelector(".grow"); if (t?.firstChild) t.firstChild.textContent = p.name || L("Print job");
  if (!list) loadStatsView();
}
// remove a single recorded print from the statistics (a wrong value, a test print ...)
const pdelBtn = () => `<button class="pdel" data-pdel title="${esc(L("Delete"))}" aria-label="${esc(L("Delete"))}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button>`;
async function delPrint(li, list) {
  const p = (list || statsData?.prints || []).find((x) => x.id === +li.dataset.print); if (!p) return;
  if (!await askConfirm(L("Remove “{0}” ({1}, {2}) from the statistics? Usage and cost of this print no longer count. Your spools stay as they are.",
    p.name || L("Print job"), dateShort(p.ts), gkg(p.grams)), { ok: L("Delete"), danger: true, title: L("Remove print") })) return false;
  try { await api(`/api/prints/${p.id}`, { method: "DELETE" }); } catch (e) { toast(e.message); return false; }
  if (li.nextElementSibling?.classList.contains("pdet")) li.nextElementSibling.remove();
  li.remove(); toast(L("Print removed from the statistics"));
  loadStatsView();
  return true;
}
// all prints of one month (tap on a bar), each with its own delete button
async function monthPrints(month) {
  let list; try { list = await api(`/api/prints?month=${month}`); } catch (e) { toast(e.message); return; }
  const d = new Date(+month.slice(0, 4), +month.slice(5) - 1, 1);
  const wrap = document.createElement("div"); wrap.className = "dlgwrap";
  const rows = () => list.map((p) => printLi(p)).join("")
    || `<li class="sub">${esc(L("No prints recorded"))}</li>`;
  wrap.innerHTML = `<div class="dlg monthdlg" role="dialog" aria-modal="true"><h3>${esc(d.toLocaleDateString(LOCALE, { month: "long", year: "numeric" }))}</h3>
    <ul class="shop prints">${rows()}</ul><div class="actions"><span class="grow"></span><button class="primary" data-dok>${esc(L("Close"))}</button></div></div>`;
  const close = () => { wrap.classList.remove("in"); setTimeout(() => wrap.remove(), 180); };
  const bind = () => { wrap.querySelectorAll("[data-pdel]").forEach((b) => (b.onclick = async () => {
    const li = b.closest("li"), id = +li.dataset.print;
    if (await delPrint(li, list)) { list = list.filter((x) => x.id !== id); if (!list.length) wrap.querySelector("ul").innerHTML = rows(); }
  }));
    wrap.querySelectorAll("[data-pren]").forEach((b) => (b.onclick = async () => { await renamePrint(b.closest("li"), list); loadStatsView(); }));
    bindPrintRows(wrap, list); };
  wrap.onclick = (e) => { if (e.target === wrap || e.target.closest("[data-dok]")) close(); };
  wrap.onkeydown = (e) => { if (e.key === "Escape") close(); };
  document.body.append(wrap); bind();
  requestAnimationFrame(() => wrap.classList.add("in"));
  wrap.querySelector("[data-dok]").focus();
}
// ------------------------------------------------------------ prices (Options › Manage stock)
const delivEdit = {};   // unsaved delivery prices: "day|line_id" -> text
const dkey = (r) => `${r.day}|${r.line_id}|${r.refill ? 1 : 0}`;
async function loadPrices() {
  try { [priceRows, delivRows] = await Promise.all([api("/api/prices"), api("/api/deliveries")]); } catch (e) { return; }
  drawPrices(); drawOptSums();
}
function drawPrices() {
  const pb = $("#pricebox"), db = $("#delivbox"); if (!pb || !db || !priceRows) return;
  const cur = esc(SET().currency || "€");
  pb.innerHTML = priceRows.length ? `<div class="optgrid prices">${priceRows.map((r) => `<span>${esc(r.name)} <span class="sub">${Lp(r.spools, "{0} spool", "{0} spools")}${r.paid ? " · " + L("paid avg. {0}", money(r.avg_paid)) : ""}</span></span><span class="inline"><input data-price="${r.id}" inputmode="decimal" data-money value="${priceStr(r.price)}" placeholder="–"> ${cur}</span>`).join("")}</div>
      <div class="actions"><button class="primary" id="pricesave">${L("Save prices")}</button></div>` : `<p class="sub">${L("Lines appear here as soon as you have spools of them.")}</p>`;
  db.innerHTML = (delivRows || []).length ? `<div class="optgrid prices">${delivRows.slice(0, delivAll ? 999 : 8).map((r, i) => `<span>${esc(dateShort(r.day))} · ${esc(r.line)} <span class="sub">${Lp(r.spools, "{0} spool", "{0} spools")}${r.mixed ? " · " + L("different prices") : ""}</span> <button class="small rfbtn${r.refill ? " on" : ""}" data-delrf="${i}" aria-pressed="${r.refill}" title="${esc(L("Bought as refills (without spool)? Refills are compared separately in the price history."))}">${L("Refill")}</button></span><span class="inline"><input data-deliv="${i}" inputmode="decimal" data-money value="${esc(delivEdit[dkey(r)] ?? priceStr(r.price))}" placeholder="${r.mixed ? "…" : r.line_price != null ? esc(priceStr(r.line_price)) : "–"}"> ${cur}</span>`).join("")}</div>
      <div class="actions"><button class="primary" id="delivsave" ${Object.keys(delivEdit).length ? "" : "disabled"}>${L("Save prices")}</button>${delivRows.length > 8 ? `<button class="small" id="delivall">${delivAll ? L("Show less") : L("Show all {0}", delivRows.length)}</button>` : ""}</div>`
    : `<p class="sub">${L("No spools with a received date yet.")}</p>`;
  const da = $("#delivall"); if (da) da.onclick = () => { delivAll = !delivAll; drawPrices(); };
  db.querySelectorAll("[data-delrf]").forEach((b) => (b.onclick = async () => {
    const r = delivRows[Number(b.dataset.delrf)];
    try { await api("/api/deliveries", { method: "PUT", body: { day: r.day, line_id: r.line_id, refill: r.refill, set_refill: !r.refill } }); }
    catch (e) { toast(tr(e.message)); return; }
    toast(r.refill ? L("Marked as spools") : L("Marked as refills"));
    [delivRows, priceRows] = await Promise.all([api("/api/deliveries"), api("/api/prices")]); drawPrices();
  }));
  // edits are kept until "Save prices" (also across "Show all"), nothing is saved on leaving the field
  db.querySelectorAll("[data-deliv]").forEach((inp) => (inp.oninput = () => {
    const r = delivRows[Number(inp.dataset.deliv)], k = dkey(r);
    if (inp.value.trim() === priceStr(r.price)) delete delivEdit[k]; else delivEdit[k] = inp.value;
    $("#delivsave").disabled = !Object.keys(delivEdit).length;
  }));
  const dsv = $("#delivsave");
  if (dsv) dsv.onclick = async () => {
    dsv.disabled = true;
    let n = 0;
    try {
      for (const [k, price] of Object.entries(delivEdit)) {
        const r = delivRows.find((x) => dkey(x) === k);
        if (!r) { delete delivEdit[k]; continue; }
        const res = await api("/api/deliveries", { method: "PUT", body: { day: r.day, line_id: r.line_id, refill: r.refill, price: price.trim() } });
        n += res.updated; delete delivEdit[k];
      }
      toast(L("Price saved for {0}", Lp(n, "{0} spool", "{0} spools")));
    } catch (e) { toast(tr(e.message)); }
    [delivRows, priceRows] = await Promise.all([api("/api/deliveries"), api("/api/prices")]); drawPrices(); drawOptSums();
  };
  const ps = $("#pricesave");
  if (ps) ps.onclick = async () => {
    const items = [...pb.querySelectorAll("[data-price]")].map((i) => ({ id: Number(i.dataset.price), price: i.value.trim() }));
    try { priceRows = await api("/api/prices", { method: "PUT", body: { items } }); drawPrices(); drawOptSums(); toast(L("Saved")); }
    catch (e) { toast(tr(e.message)); }
  };
}

// ------------------------------------------------------------ push notifications
let pushSt = null, pushMine = null;   // pushMine: this device's subscription endpoint or null
const PUSH_KINDS = [["print", "Print finished, cancelled, paused"], ["printer", "Printer errors"], ["job", "Not enough filament for the print"],
  ["stock", "Spool almost empty"], ["newspool", "New Bambu Lab spool in the AMS"], ["removed", "Spool taken out of the AMS (with its storage slot)"], ["climate", "Humidity in storage"], ["dry", "Spools to dry"], ["update", "New version"]];
const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
async function loadPush() {
  try { pushSt = await api("/api/push"); } catch (e) { return; }
  pushMine = null;
  try {
    const reg = "serviceWorker" in navigator && await navigator.serviceWorker.getRegistration("/");
    const sub = reg && reg.pushManager && await reg.pushManager.getSubscription();
    if (sub) pushMine = sub.endpoint;
  } catch (e) { /* no push support in this browser */ }
  drawPush(); drawOptSums();
}
function pushBlocker() {
  if (!window.isSecureContext) {
    const url = remoteSt?.https && remoteSt.url;
    return L("Push only works via the HTTPS address.") + (url ? ` <a href="${esc(url)}">${esc(url)}</a>` : " " + L("Enable the HTTPS address under Remote access first."));
  }
  if (isIOS() && !isStandalone()) return L("On an iPhone: first add this page via “Share › Add to Home Screen” and open PixxelSpool from there.");
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return L("This browser does not support push notifications.");
  if (typeof Notification !== "undefined" && Notification.permission === "denied") return L("Notifications are blocked for PixxelSpool. Please allow them in your phone or browser settings.");
  return "";
}
function drawPush() {
  const box = $("#pushbox"), st = pushSt; if (!box || !st) return;
  const block = pushBlocker();
  const devs = st.devices.length ? `<ul class="shop">${st.devices.map((d) => `<li><span class="grow">${esc(d.name || L("Device"))}<span class="sub">${L("since {0}", dateShort(d.created))}${d.error ? " · " + esc(d.error) : d.last_ok ? " · " + L("last delivered {0}", dateShort(d.last_ok)) : ""}</span></span>
      <button class="small" data-ptest="${d.id}">${L("Test")}</button><button class="small danger" data-pdel="${d.id}">×</button></li>`).join("")}</ul>`
    : `<p class="sub">${L("No device registered yet.")}</p>`;
  box.innerHTML = `${block ? `<div class="msg">${block}</div>` : pushMine
      ? `<p>${L("This device receives push notifications.")}</p><div class="actions"><button id="pushoff">${L("Turn off on this device")}</button></div>`
      : `<div class="actions"><button class="primary" id="pushon">${L("Turn on for this device")}</button></div>`}
    <h4>${L("Registered devices")}</h4>${devs}
    <h4>${L("What should be sent?")}</h4>
    <div class="pushkinds">${PUSH_KINDS.filter(([k]) => k !== "dry" || SET().dry_on !== false).map(([k, t]) => `<label class="check"><input type="checkbox" data-pkind="${k}" ${st.kinds.includes(k) ? "checked" : ""}> ${L(t)}</label>`).join("")}</div>`;
  const on = $("#pushon"); if (on) on.onclick = pushEnable;
  const off = $("#pushoff"); if (off) off.onclick = pushDisable;
  box.querySelectorAll("[data-ptest]").forEach((b) => (b.onclick = async () => {
    try { pushSt = await api("/api/push/test", { method: "POST", body: { id: b.dataset.ptest } }); toast(L("Test message sent")); }
    catch (e) { toast(tr(e.message)); await loadPush(); return; }
    drawPush();
  }));
  box.querySelectorAll("[data-pdel]").forEach((b) => (b.onclick = async () => {
    pushSt = await api("/api/push/unsubscribe", { method: "POST", body: { id: b.dataset.pdel } }); loadPush();
  }));
  box.querySelectorAll("[data-pkind]").forEach((c) => (c.onchange = async () => {
    const kinds = [...box.querySelectorAll("[data-pkind]")].filter((x) => x.checked).map((x) => x.dataset.pkind);
    try { pushSt = await api("/api/push/kinds", { method: "PUT", body: { kinds } }); toast(L("Saved")); } catch (e) { toast(tr(e.message)); }
  }));
}
function deviceName() {
  const ua = navigator.userAgent;
  const dev = /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) || isIOS() ? "iPad" : /Android/.test(ua) ? "Android" : /Mac/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows" : "Browser";
  const br = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) && !/Edg/.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "";
  return dev + (br && !(isIOS() && isStandalone()) ? " · " + br : "");
}
async function pushEnable() {
  try {
    if ((await Notification.requestPermission()) !== "granted") { toast(L("Notifications were not allowed")); return drawPush(); }
    const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
    const key = Uint8Array.from(atob(pushSt.key.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - pushSt.key.length % 4) % 4)), (c) => c.charCodeAt(0));
    let sub = await reg.pushManager.getSubscription();
    if (sub && sub.options?.applicationServerKey && new Uint8Array(sub.options.applicationServerKey).toString() !== key.toString()) { await sub.unsubscribe(); sub = null; }
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
    const res = await api("/api/push/subscribe", { method: "POST", body: { subscription: sub.toJSON(), name: deviceName() } });
    pushSt = await api("/api/push/test", { method: "POST", body: { id: res.id } }).catch(() => res);
    toast(L("Push turned on. A test message is on its way."));
  } catch (e) { toast(L("Could not turn on push: {0}", e.message || String(e))); }
  loadPush();
}
async function pushDisable() {
  try {
    const reg = await navigator.serviceWorker.getRegistration("/");
    const sub = reg && await reg.pushManager.getSubscription();
    if (sub) { await api("/api/push/unsubscribe", { method: "POST", body: { endpoint: sub.endpoint } }); await sub.unsubscribe(); }
  } catch (e) { toast(e.message); }
  loadPush();
}

// ------------------------------------------------------------ network backup
let offData = null;
async function loadOffsite() { try { offData = await api("/api/offsite"); } catch (e) { return; } drawOffsite(); drawOptSums(); }
function drawOffsite() {
  const box = $("#offsitebox"), o = offData; if (!box || !o) return;
  const typ = o.type || "smb", last = o.last || {};
  const off = !!o.host && !o.on;   // switched off: only the switch is shown
  box.innerHTML = `<div class="optrow"><span>${L("Every night")}</span><div class="seg on-always"><button data-ofon="1" class="${off ? "" : "on"}">${L("On")}</button><button data-ofon="0" class="${off ? "on" : ""}">${L("Off")}</button></div></div>
    <div id="ofFields" ${off ? "hidden" : ""}><div class="optgrid">
      <span class="sub">${L("Type")}</span><select id="ofType"><option value="smb" ${typ === "smb" ? "selected" : ""}>${L("Network share (SMB)")}</option><option value="ftp" ${typ === "ftp" ? "selected" : ""}>FTP</option><option value="ftps" ${typ === "ftps" ? "selected" : ""}>FTPS</option></select>
      <span class="sub">${L("Server")}</span><input id="ofHost" value="${esc(o.host)}" placeholder="${esc(L("e.g. fritz.box or 192.168.1.10"))}">
      <span class="sub smbonly">${L("Share")}</span><input class="smbonly" id="ofShare" value="${esc(o.share)}" placeholder="${esc(L("e.g. FRITZ.NAS or backup"))}">
      <span class="sub">${L("Folder (optional)")}</span><input id="ofPath" value="${esc(o.path)}" placeholder="pixxelspool">
      <span class="sub">${L("User")}</span><input id="ofUser" value="${esc(o.user)}" autocomplete="off">
      <span class="sub">${L("Password")}</span><input id="ofPass" type="password" autocomplete="new-password" placeholder="${esc(o.has_password ? L("unchanged") : "")}">
      <span class="sub">${L("Keep")}</span><span class="inline"><input id="ofKeep" type="number" inputmode="numeric" min="1" max="365" value="${o.keep || 14}"> ${L("backups")}</span>
    </div>
    <p class="uperr" id="ofFtpWarn" hidden>${L("FTP sends the password and the backup unencrypted through the network. Better use FTPS or a network share (SMB).")}</p>
    <label class="check"><input type="checkbox" id="ofLock" ${o.encrypt ? "checked" : ""}> ${L("Protect the backups with a password")}</label>
    <div id="ofLockRow" ${o.encrypt ? "" : "hidden"}><div class="authform"><input id="ofLockPw" type="password" autocomplete="new-password" placeholder="${esc(o.has_enc_password ? L("unchanged") : L("Password for the backups (at least 6 characters)"))}"></div>
      <p class="sub">${L("Without this password the backups can't be restored. Write it down and keep it somewhere other than the Pi.")}</p></div>
    ${last.ts ? `<p class="${last.ok ? "sub" : "uperr"}">${last.ok ? "✓ " + L("Last backup: {0}", esc(dateShort(last.ts)) + " " + esc(String(last.ts).slice(11, 16))) + ` · ${esc(last.file || "")}` : L("Last attempt failed: {0}", esc(tr(last.error || "")))}</p>` : ""}
    <div class="actions"><button class="primary" id="ofSave">${L("Save")}</button>${o.host ? `<button id="ofRun">${L("Back up now")}</button><button class="danger" id="ofDel">${L("Remove")}</button>` : ""}</div></div>`;
  let on = o.on || !o.host;
  const smb = () => { box.querySelectorAll(".smbonly").forEach((e) => (e.hidden = $("#ofType").value !== "smb")); $("#ofFtpWarn").hidden = $("#ofType").value !== "ftp"; };
  smb(); $("#ofType").onchange = smb;
  $("#ofLock").onchange = () => { $("#ofLockRow").hidden = !$("#ofLock").checked; if ($("#ofLock").checked && !o.has_enc_password) $("#ofLockPw").focus(); };
  const body = () => ({ type: $("#ofType").value, host: $("#ofHost").value, share: $("#ofShare").value, path: $("#ofPath").value,
    user: $("#ofUser").value, password: $("#ofPass").value, keep: $("#ofKeep").value, on,
    encrypt: $("#ofLock").checked, enc_password: $("#ofLockPw").value });
  const store = async (msg = L("Saved")) => { try { offData = await api("/api/offsite", { method: "PUT", body: body() }); drawOffsite(); drawOptSums(); toast(msg); } catch (e) { toast(tr(e.message)); } };
  box.querySelectorAll("[data-ofon]").forEach((b) => (b.onclick = async () => {
    const want = b.dataset.ofon === "1"; if (want === on) return;
    if (!o.host) { on = want; $("#ofFields").hidden = !on; box.querySelectorAll("[data-ofon]").forEach((x) => x.classList.toggle("on", x === b)); return; }
    if (want) { on = true; return store(); }     // a saved setup goes back on right away
    const r = await askKeepData(L("Network backup"), L("Server, user and password of the network backup are still saved."));
    if (r === "keep") { on = false; return store(); }
    if (r === "delete") { offData = await api("/api/offsite", { method: "DELETE" }); drawOffsite(); drawOptSums(); toast(L("Data deleted")); }
  }));
  $("#ofSave").onclick = () => store();
  const run = $("#ofRun");
  if (run) run.onclick = async () => {
    run.disabled = true; run.textContent = L("One moment …");
    try { const r = await api("/api/offsite/run", { method: "POST" }); offData = r; drawOffsite(); toast(r.result.ok ? L("Backup uploaded") : tr(r.result.error)); }
    catch (e) { toast(tr(e.message)); run.disabled = false; }
  };
  const del = $("#ofDel");
  if (del) del.onclick = async () => { if (!await askConfirm(L("Remove the network backup? The files on the server stay."), { ok: L("Remove"), danger: true })) return; offData = await api("/api/offsite", { method: "DELETE" }); drawOffsite(); drawOptSums(); };
}

// ------------------------------------------------------------ Updates (GitHub)
let updSt = null;
document.querySelectorAll("[data-upc]").forEach((b) => (b.onclick = () => saveSettings({ update_check: b.dataset.upc === "1" })));
document.querySelectorAll("[data-upa]").forEach((b) => (b.onclick = () => saveSettings({ auto_security: b.dataset.upa === "1" })));
document.querySelectorAll("[data-upch]").forEach((b) => (b.onclick = async () => { await saveSettings({ update_channel: b.dataset.upch }); try { updSt = await api("/api/update", { method: "POST", body: { action: "check" } }); } catch (err) { /* shown by the next check */ } drawUpdate(); drawStats(); }));
async function loadUpdate() { try { updSt = await api("/api/update"); } catch (e) { updSt = null; } drawUpdate(); drawOptSums(); if (overview) drawStats(); }
async function updateAct(body, btn) {
  if (btn) { btn.disabled = true; btn.textContent = L("One moment …"); }
  try { updSt = await api("/api/update", { method: "POST", body }); } catch (e) { toast(tr(e.message)); }
  drawUpdate(); drawOptSums();
}
async function waitForRestart(version) {
  const t0 = Date.now();
  await new Promise((r) => setTimeout(r, 4000));
  while (Date.now() - t0 < 180000) {
    try {
      const r = await fetch("/api/update", { cache: "no-store" });
      if (r.ok) { const d = await r.json(); if (!version || d.current === version) { location.reload(); return; } }
    } catch (e) {}
    await new Promise((r) => setTimeout(r, 2000));
  }
  toast(L("PixxelSpool is not responding. Please reload the page."));
}
// Options › Raspberry Pi: live values, system version, automatic security updates, advice for a new major version
let sysSt = null;
async function loadSystem() {
  const box = $("#sysinfo"); if (!box || overview?.host?.kind !== "pi") return;
  try { sysSt = await api("/api/system"); } catch (e) { return; }
  drawSystem();
  clearTimeout(loadSystem.t);
  if (view === "tools" && $("#systool")?.classList.contains("open") && !document.hidden) loadSystem.t = setTimeout(loadSystem, 5000);
}
function drawSystem() {
  const box = $("#sysinfo"), s = sysSt; if (!box || !s || !s.pi) return;
  const st = s.stats || {}, gb = (b) => (b / 1073741824).toLocaleString(LOCALE, { maximumFractionDigits: 1 }) + " GB";
  const mb = (b) => Math.round(b / 1048576).toLocaleString(LOCALE) + " MB";
  const when = (ts) => new Date(ts * 1000).toLocaleString(LOCALE, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: HOUR12() });
  const row = (k, v, cls = "") => `<div class="optrow"><span>${L(k)}</span><span class="sysval ${cls}">${v}</span></div>`;
  const bar = (pct) => `<span class="sysbar"><i style="width:${Math.max(0, Math.min(100, pct))}%"></i></span>`;
  let h = "";
  if (st.cpu != null) h += row("CPU", `${bar(st.cpu)} ${Math.round(st.cpu)} %`, st.cpu > 85 ? "warnv" : "");
  if (st.mem_total) { const p = 100 * st.mem_used / st.mem_total; h += row("Memory", `${bar(p)} ${mb(st.mem_used)} / ${mb(st.mem_total)}`, p > 90 ? "warnv" : ""); }
  if (st.temp != null) h += row("Temperature", `${st.temp.toLocaleString(LOCALE)} °C`, st.temp >= 80 ? "badv" : st.temp >= 70 ? "warnv" : "");
  if (st.disk_total) { const p = 100 * st.disk_used / st.disk_total; h += row("Storage space", `${bar(p)} ${gb(st.disk_used)} / ${gb(st.disk_total)}`, p > 90 ? "warnv" : ""); }
  if (st.power) h += row("Power supply", L(st.power === "ok" ? "OK" : st.power === "now" ? "Too little voltage right now" : "Too little voltage since the last start"), st.power === "ok" ? "" : "badv");
  if (st.boot) h += row("Last restart of the Pi", when(st.boot));
  if (s.started) h += row("PixxelSpool running since", when(s.started));
  h += row("System", `${esc(s.name || "?")} · Python ${esc(s.python || "?")}`);
  if (s.auto_updates !== null && s.auto_updates !== undefined)
    h += row("Automatic system security updates", L(s.auto_updates ? "On" : "Off"), s.auto_updates ? "goodv" : "");
  if (s.auto_updates === false)
    h += `<div class="oscmd"><p class="sub">${L("To turn them on, run this command in a terminal on the Pi. Only security patches are installed, the Pi never restarts by itself:")}</p>` +
      `<pre class="cmd">${esc(s.command)}</pre><div class="actions"><button class="small" data-copy>${L("Copy")}</button></div></div>`;
  if (s.setup_done < s.setup_level)
    h += `<p class="uperr">${L("Please refresh the setup once: run ./install.sh again in the PixxelSpool folder on the Pi.")}</p>`;
  h += `<p class="sub">${L("A new major version of Raspberry Pi OS? It is best to set the Pi up fresh and restore your backup; upgrading the running system is more likely to cause trouble. If you upgrade anyway, run ./install.sh again in the PixxelSpool folder afterwards.")}</p>`;
  box.innerHTML = h;
  box.querySelector("[data-copy]")?.addEventListener("click", () => copyText(box.querySelector(".oscmd pre").textContent));
}
function copyText(text) {
  const done = () => toast(L("Copied"));
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(done).catch(() => {});
  const ta = document.createElement("textarea");   // plain http in the home network: the old way
  ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); done(); } catch (e) { /* the text stays selectable */ }
  ta.remove();
}
function drawUpdate() {
  const box = $("#updatebox"), u = updSt; if (!box) return;
  if (!u) { box.innerHTML = `<p class="sub">${L("Status: {0}", L("Error"))}</p>`; return; }
  const c = u.check, j = u.job || {};
  const idle = !j.running && !j.done;
  // installed version with the check button on the same row; the result goes right below it
  let h = `<div class="optrow uprow"><span>${L("Installed")} <b>${esc(u.current)}</b></span>${idle ? `<button class="small" data-ua="check">${L("Check for updates")}</button>` : ""}</div>`;
  if (j.running) {
    h += `<p class="upbusy"><span class="spin"></span> ${L("Updating to {0}: {1}", esc(j.target || ""), L(j.phase || ""))}</p><p class="sub">${L("Please keep this page open. PixxelSpool restarts afterwards.")}</p>`;
  } else if (j.done) {
    h += u.service ? `<p class="upbusy"><span class="spin"></span> ${L("Update to {0} done. PixxelSpool is restarting, back in a moment …", esc(j.version || ""))}</p>`
      : `<p>${L("Update to {0} done. Please restart PixxelSpool.", esc(j.version || ""))}</p>`;
  } else {
    if (j.error) h += `<p class="uperr">${L("Update failed: {0}", esc(tr(j.error)))}</p><p class="sub">${L("Nothing was changed.")}</p>`;
    if (c && c.error) h += `<p class="sub">${esc(tr(c.error))}</p>`;
    else if (c && c.available) {
      h += `<div class="optrow"><span>${L("New on GitHub")}</span><span>${c.security ? `<span class="upsec">${L("Security update")}</span> ` : ""}<b class="upnew">${esc(c.latest)}</b></span></div>` +
        (c.notes ? `<details class="upnotes" open><summary>${L("What's new?")}</summary><div class="upnotesbody">${mdNotes(c.notes)}</div></details>` : "");
    } else if (c) h += `<p class="sub">${L("You have the latest version.")} · ${L("checked {0}", new Date(c.ts * 1000).toLocaleString(LOCALE, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: HOUR12() }))}</p>`;
    if (c && c.available && (u.self_update !== false || c.download))
      h += `<div class="actions">` + (u.self_update !== false ? `<button class="primary" data-ua="install">${L("Install update to {0}", esc(c.latest))}</button>` : "") +
        // Windows / Mac app: download the new installer or disk image instead
        (c.download ? `<a class="btn primary" href="${esc(c.download)}" target="_blank" rel="noopener">${L(overview?.host?.kind === "mac" ? "Download version {0}" : "Download installer for {0}", esc(c.latest))}</a>` : "") + `</div>`;
    if (u.self_update !== false && u.rollback && u.rollback.length)
      h += `<div class="optrow"><span>${L("Go back to an earlier version")}</span><span class="inline"><select id="uprb">${u.rollback.map((v) => `<option>${esc(v)}</option>`).join("")}</select><button class="small" data-ua="rollback">${L("Back")}</button></span></div>`;
  }
  box.innerHTML = h;
  box.querySelectorAll("[data-ua]").forEach((b) => (b.onclick = async () => {
    const a = b.dataset.ua;
    if (a === "install" && !await askConfirm(L("Install the update to {0} now? PixxelSpool will be unavailable for about half a minute.", c.latest), { ok: L("Install") })) return;
    if (a === "rollback") {
      const v = $("#uprb").value;
      if (!await askConfirm(L("Go back to {0}? The database stays as it is and is backed up first.", v), { ok: L("Back") })) return;
      return updateAct({ action: "rollback", version: v }, b);
    }
    updateAct({ action: a }, b);
  }));
  clearTimeout(drawUpdate.t);
  if (j.running && view === "tools") drawUpdate.t = setTimeout(loadUpdate, 1500);
  if (j.done && u.service && !drawUpdate.waiting) { drawUpdate.waiting = true; waitForRestart(j.version); }
}
// Options › Used-up spools: spools marked as empty, newest first; tapping one opens it (with "Put back")
async function loadUsedUp() {
  const box = $("#usedbox"); if (!box) return;
  try {
    const list = await api("/api/usedup");
    box.innerHTML = list.length ? `<ul class="plainlist usedlist">${list.map((s) => `<li data-used="${s.id}">${sw(s)}<span class="grow">${title(s)}
      <span class="sub">${esc(s.bambu_no ?? s.brand ?? "")}${s.emptied_at || s.updated_at ? " · " + L("empty since {0}", esc(fmtDay(parseDay(s.emptied_at || s.updated_at)))) : ""}</span></span><span class="chev">›</span></li>`).join("")}</ul>`
      : `<p class="sub">${L("No used-up spools yet.")}</p>`;
    box.querySelectorAll("[data-used]").forEach((li) => (li.onclick = async () => {
      try { showSpool(await api(`/api/spools/${li.dataset.used}`)); } catch (e) { toast(e.message); }
    }));
  } catch (e) { box.innerHTML = `<p class="sub">${esc(e.message)}</p>`; }
}
function optSum(sel, text) { const el = document.querySelector(`${sel} .foldsum`); if (el) el.textContent = text || ""; }
function drawOptSums() {
  const st = SET(), r = overview?.reader || {}, bb = overview?.bambu || {}, ha = overview?.ha || {};
  const off = (x) => x.detail === "ausgeschaltet";
  const ps = overview?.printers || [];
  optSum("#bambutool", ps.length > 1 ? L("{0} printers · {1} connected", ps.length, ps.filter((p) => p.status === "connected").length)
    : L(bb.status === "connected" ? "connected" : bb.status === "error" ? "Error" : off(bb) ? "switched off" : "not set up"));
  optSum("#readertool", `${RMODE[st.reader || "auto"]} · ${L(r.status === "ready" ? "ready" : r.status === "starting" ? "starting" : "not found")}`);
  optSum("#hatool", L(ha.status === "connected" ? "connected" : ha.status === "error" ? "Error" : off(ha) ? "switched off" : "off"));
  optSum("#remotetool", !remoteSt ? "" : !remoteSt.installed ? L("not installed") : remoteSt.state === "Running" ? (remoteSt.https ? L("on") + " · HTTPS" : L("on")) : remoteSt.state === "Stopped" ? L("off") : L("not set up"));
  optSum("#authtool", !authSt ? "" : L(authSt.enabled ? "on" : "off"));
  optSum("#pushtool", !pushSt ? "" : pushSt.devices.length ? Lp(pushSt.devices.length, "{0} device", "{0} devices") : L("off"));
  if (priceRows) optSum("#pricetool", Lp(priceRows.length, "{0} line", "{0} lines"));
  if (delivRows) optSum("#delivtool", delivRows.length ? Lp(delivRows.length, "{0} delivery", "{0} deliveries") : "");
  optSum("#backuptool", !offData?.host || !offData.on ? "" : offData.last?.ok === false ? L("Network backup: {0}", L("Error")) : L("Network backup: {0}", (offData.type || "").toUpperCase()));
  optSum("#brandtool", brandData ? Lp(brandData.lines.length, "{0} line", "{0} lines") : "");
  optSum("#updatetool", !updSt ? "" : updSt.job?.running ? L("running …") : updSt.check?.available ? L("{0} available", updSt.check.latest) : updSt.current);
  optSum("#layouttool", Lp((st.cabinets || []).length, "{0} storage unit", "{0} storage units"));
  optSum("#shoptool", Lp((st.collect_lines || []).length, "{0} line", "{0} lines"));
  optSum("#spoolstool", `${st.empty_spools ?? 0}`);
}

// ------------------------------------------------------------ direct printer connection (Bambu Lab MQTT)
const BBSTATE = { connected: "✓ connected", error: "Error", off: "not set up" };
// Printers: list with on/off, edit and remove; the form adds a new one or edits one (bbEdit = "new" or id).
let bbCfg = { printers: [] }, bbEdit = null;
async function loadBambuCfg() {
  try { bbCfg = await api("/api/bambu/config"); } catch (e) { return; }
  drawBambuCfg();
}
function bbStatus(p) {
  const st = p.state || {};
  return !p.on ? L("switched off") : L(BBSTATE[st.status] || st.status || "–") + (st.detail && st.status === "error" ? " · " + tr(st.detail) : "");
}
function drawBambuCfg() {
  const ps = bbCfg.printers || [];
  if (!ps.length && !bbEdit) bbEdit = "new";
  $("#bbList").innerHTML = ps.map((p) => `<li data-pid="${esc(p.id)}"><span class="grow"><b>${esc(p.name)}</b>${p.model && p.model !== p.name ? ` <span class="sub">${esc(p.model)}</span>` : ""}
      <div class="sub">${esc(p.ip)} · ${esc(bbStatus(p))}</div></span>
      <span class="seg on-always"><button data-bbon="1" class="${p.on ? "on" : ""}">${L("On")}</button><button data-bbon="0" class="${p.on ? "" : "on"}">${L("Off")}</button></span>
      <button class="small" data-bbedit>${L("Edit")}</button><button class="small" data-bbdel>${L("Remove")}</button></li>`).join("");
  $("#bbList").hidden = !ps.length;
  $("#bbList").querySelectorAll("li").forEach((li) => {
    const p = ps.find((x) => x.id === li.dataset.pid);
    li.querySelectorAll("[data-bbon]").forEach((b) => (b.onclick = async () => {
      bbCfg = await api(`/api/bambu/printers/${encodeURIComponent(p.id)}/on`, { method: "POST", body: { on: b.dataset.bbon === "1" } });
      setTimeout(loadBambuCfg, 1500); drawBambuCfg(); setTimeout(refresh, 1500);
    }));
    li.querySelector("[data-bbedit]").onclick = () => { bbEdit = p.id; $("#bbOut").innerHTML = ""; drawBambuCfg(); fillBbForm(p); };
    li.querySelector("[data-bbdel]").onclick = async () => {
      if (!await askConfirm(L("Remove printer “{0}”? Spools in its AMS are marked to be put back.", p.name), { ok: L("Remove"), danger: true })) return;
      bbCfg = await api(`/api/bambu/config?printer=${encodeURIComponent(p.id)}`, { method: "DELETE" });
      if (bbEdit === p.id) bbEdit = null;
      drawBambuCfg(); refresh(); loadPrinter(); toast(L("Removed"));
    };
  });
  $("#bbForm").hidden = !bbEdit;
  $("#bbAddRow").hidden = !!bbEdit;
  $("#bbCancel").hidden = !ps.length;
  $("#bbFormTitle").textContent = bbEdit === "new" ? (ps.length ? L("Add another printer") : L("Set up printer")) : L("Edit printer");
}
function fillBbForm(p) {
  $("#bbName").value = p?.name || ""; $("#bbIp").value = p?.ip || ""; $("#bbSerial").value = p?.serial || ""; $("#bbCode").value = "";
  $("#bbCode").placeholder = L(p?.has_code ? "saved ✓ – enter a new one to change it" : "8 characters from the printer display");
}
// refresh the list when a printer's connection state changed (overview updates come often)
let bbSig = "";
function drawBambuInfo() {
  const sig = JSON.stringify((overview?.printers || []).map((p) => [p.id, p.status, p.detail]));
  if (sig === bbSig) return;
  bbSig = sig;
  if (view === "tools" || document.body.classList.contains("wizopen")) loadBambuCfg();
}
$("#bbAdd").onclick = () => { bbEdit = "new"; $("#bbOut").innerHTML = ""; fillBbForm(null); drawBambuCfg(); $("#bbName").focus(); };
$("#bbCancel").onclick = () => { bbEdit = null; drawBambuCfg(); };
$("#bbSave").onclick = async () => {
  const b = $("#bbSave"); b.disabled = true; b.textContent = L("Connecting …"); $("#bbOut").innerHTML = "";
  try {
    const r = await api("/api/bambu/config", { method: "PUT", body: { id: bbEdit === "new" ? null : bbEdit, name: $("#bbName").value,
      ip: $("#bbIp").value, serial: $("#bbSerial").value, code: $("#bbCode").value } });
    $("#bbCode").value = ""; toast(L("Printer connected"));
    const s = r.summary || {}, j = s.job || {};
    $("#bbOut").innerHTML = `<p class="sub">✓ ${L("Connected. {0} AMS with {1} slots", s.ams_units || 0, s.trays || 0)}${s.nozzle ? ` · ${L("Nozzle")} ${esc(s.nozzle)}` : ""}${j.state ? ` · ${L("Status: {0}", esc(j.state))}` : ""}${j.name ? ` · ${esc(j.name)}` : ""}</p>`;
    bbEdit = null; bbCfg = { printers: r.printers }; drawBambuCfg(); setTimeout(loadBambuCfg, 2000); setTimeout(loadPrinter, 2500);
  } catch (e) { $("#bbOut").innerHTML = `<p class="sub"><b>${L("Not connected:")}</b> ${esc(e.message)}</p>`; }
  b.disabled = false; b.textContent = L("Test connection and save");
};
fillBbForm(null);
loadBambuCfg();

// ------------------------------------------------------------ NFC reader
const RMODE = new Proxy({ auto: "Automatic", usb: "USB reader", pn532: "PN532 via I2C" }, { get: (o, k) => L(o[k] ?? k) });
const readerTest = { on: false, t: null };
const TESTED_READERS = /ACR122|ACR1252|PN532.*\(USB/i;   // readers confirmed to work (PN532 only via USB so far); add more after real tests
function drawReaderTool() {
  const mode = SET().reader || "auto", r = overview?.reader || {};
  document.querySelectorAll("[data-rmode]").forEach((b) => b.classList.toggle("on", b.dataset.rmode === mode));
  const st = L({ ready: "✓ ready", disconnected: "not found", missing: "not available", starting: "starting …", simulated: "Simulation" }[r.status] || r.status || "–");
  const kind = r.kind === "usb" ? L("USB reader") : r.kind === "pn532" ? "PN532" : "";
  $("#readerinfo").textContent = L("Selected: {0}. Status: {1}", RMODE[mode], st) + (kind ? " · " + kind : "") + (r.detail ? " · " + tr(r.detail) : "");
  if (r.status === "ready" && r.detail) {          // found reader: green if tested with PixxelSpool, yellow if not yet
    const ok = TESTED_READERS.test(r.detail);
    $("#readerinfo").insertAdjacentHTML("beforeend", ` <span class="rtag ${ok ? "ok" : "warn"}">${L(ok ? "tested" : "untested")}</span>`);
  }
}
document.querySelectorAll("[data-rmode]").forEach((b) => (b.onclick = () => saveSettings({ reader: b.dataset.rmode })));
$("#setScanPause").onchange = () => { const v = parseFloat(String($("#setScanPause").value).replace(",", ".")); if (!isNaN(v)) saveSettings({ scan_pause_ms: Math.round(v * 1000) }); };
$("#setLogRows").onchange = async () => { await saveSettings({ log_rows: $("#setLogRows").value }); drawLog(); };
$("#datefmt").onchange = async () => { await saveSettings({ date_fmt: $("#datefmt").value }); render(); drawPrinter?.(); };
document.querySelectorAll("[data-tf]").forEach((b) => (b.onclick = async () => { await saveSettings({ time_fmt: b.dataset.tf }); render(); drawPrinter(); }));
document.querySelectorAll("[data-cam]").forEach((b) => (b.onclick = async () => {
  const m = b.dataset.cam;
  if (m === "max" && (SET().camera || "off") !== "max" && !await askConfirm(esc(L("Max shows every camera frame, up to 30 per second. This needs much more computing power, so PixxelSpool may become slower. Turn it on anyway?")) + (overview?.host?.kind === "pi" ? `<span class="dlgnote">${esc(L("The Pi gets noticeably warmer. A heatsink with a fan (e.g. the official Active Cooler) is recommended, otherwise it throttles itself when hot."))}</span>` : ""), { ok: L("Turn on anyway"), warn: true, html: true, title: L("Needs more computing power") })) return;
  cam.want = false; await saveSettings({ camera: m }); syncCam();
}));
// While the setup assistant shows the reader step, scans are only shown there (nothing is booked into storage).
// There is no button for it: the reader is always active, the test mode is renewed until the step is left.
async function setReaderTest(on) {
  readerTest.on = on; clearTimeout(readerTest.t);
  try { await api("/api/reader/test", { method: "POST", body: { on } }); } catch (e) { toast(e.message); }
  const box = $("#readertest"); box.hidden = !on; box.classList.remove("hit");
  box.innerHTML = `<b>${L("Put a spool on the reader.")}</b> <span class="sub">${L("Nothing is booked into storage.")} ${T("tagUnderLogo")}</span>`;
  const renew = () => { readerTest.t = setTimeout(() => { if (readerTest.on) { api("/api/reader/test", { method: "POST", body: { on: true } }).catch(() => {}); renew(); } }, 100000); };
  if (on) renew();
}
function showTestScan(tag, err) {
  const box = $("#readertest"); box.hidden = false;
  if (!tag) { box.classList.remove("hit"); box.innerHTML = `<b>${L("Tag detected but not readable.")}</b> <span class="sub">${esc(tr(err || ""))} ${L("Place the spool steadily and centered.")} ${T("tagUnderLogo")}</span>`; return; }
  box.classList.add("hit");
  if (tag.plain) { box.innerHTML = `<p>✓ <b>${L("NFC sticker detected")}</b> <span class="sub">${L("ID {0}", esc(tag.uid))}</span></p><p class="sub">${L("The reader works.")}${wiz.open ? "" : " " + L("Link stickers in a spool's view with “Add tag”.")}</p>`; return; }
  const hex = "#" + String(tag.color_rgba || "888888").slice(0, 6);
  box.innerHTML = `<div class="optrow"><span><span class="swatch" style="background:${esc(hex)};display:inline-block;vertical-align:middle"></span>
    <b>${esc(tag.detailed_type || tag.filament_type || L("Spool"))}</b> ${esc(hex.toUpperCase())}</span><span class="sub">${esc(tag.weight_g || "")} g · ${esc(tag.variant_id || "")}</span></div>
    <p class="sub">✓ ${L("Reader works. Serial number {0}…", esc(String(tag.tray_uid || "").slice(0, 12)))}</p>`;
}

// ------------------------------------------------------------ setup wizard
const wiz = { open: false, i: 0, dir: 1, homes: new Map(), introStop: null };
const WIZICON = {   // stroke icons for the step headers
  reader: '<path d="M6 8.5a5 5 0 0 1 0 7M9.5 6a8.5 8.5 0 0 1 0 12M13 3.5a12 12 0 0 1 0 17"/>',
  storage: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 9h16M4 15h16"/>',
  printer: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M7 15h10M9 7h6"/>',
  ha: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M12 12a2.5 2.5 0 0 0 0 5"/>',
  privacy: '<path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
};
const wizHead = (ico, title, text) => `<div class="wizicon"><svg viewBox="0 0 24 24" aria-hidden="true">${WIZICON[ico]}</svg></div>
  <h2>${title}</h2><p class="sub">${text}</p>`;   // title, text already translated
const WIZ = [
  { title: "Welcome", enter: () => {
      $("#wizbody").querySelectorAll("[data-wlang]").forEach((b) => (b.onclick = () => setLang(b.dataset.wlang)));
      $("#wizbody").querySelector("[data-wrestore]").onclick = () => $("#bkrestore").click();
    },
    next: "Let's go",
    html: () => `<div class="wizwelcome"><img class="hero" src="/static/icon-512.png?v=5" alt="">
      <h1>${L("Welcome to PixxelSpool")}</h1><div class="wizby">by pixxelhoff</div>
      <div class="seg on-always wizlang">${[["de", "Deutsch"], ["en", "English"], ["es", "Español"]].map(([k, n]) =>
        `<button data-wlang="${k}" class="${k === LANG ? "on" : ""}">${n}</button>`).join("")}</div>
      <p class="sub legal">${L("PixxelSpool is an independent hobby project and is not affiliated with Bambu Lab. “Bambu Lab” and “AMS” are trademarks of their owners. More under Options › Legal notice.")}</p>
      <button class="linkbtn wizrestore" data-wrestore>${L("Restore from a backup")}</button></div>` },
  // animated tour of the principle (intro.js); stopped when the step is left or redrawn
  { title: "How it works", html: () => `<div id="wizintro"></div>`,
    enter: () => { wiz.introStop = mountIntro($("#wizintro")); }, leave: () => stopIntro() },
  { title: "Privacy", html: () => `${wizHead("privacy", L("Your data stays with you"), L("PixxelSpool runs entirely in your home."))}
      <ul class="wizpoints">
        <li><b>${L("Everything stays local")}</b><span>${L("Storage, settings and credentials stay on this device only. No account, no cloud.")}</span></li>
        <li><b>${L("No data collection")}</b><span>${L("No tracking, no ads, no usage statistics. No data about you or your storage is sent anywhere.")}</span></li>
        <li><b>${L("Online only when needed")}</b><span>${L("PixxelSpool asks GitHub for updates (you can turn this off). With a connected printer it loads the texts for printer error codes from Bambu Lab once a week.")}</span></li>
        <li><b>${L("Everything else is up to you")}</b><span>${L("Push notifications and remote access stay off until you turn them on.")}</span></li>
      </ul>` },
  { title: "NFC reader", borrow: "#readertool", ready: () => overview?.reader?.status === "ready",
    skipAsk: () => ask(L("PixxelSpool also works with the AMS alone: it recognizes Bambu Lab spools as soon as they go into the AMS. An NFC reader is still recommended: place a spool on it and PixxelSpool knows it right away and suggests a place in storage."),
      { title: L("Continue without a reader?"), ok: L("Next"), cancel: L("Back") }), enter: () => { setReaderTest(true); $("#readertool").querySelectorAll("details").forEach((d) => (d.open = false)); }, leave: () => setReaderTest(false),
    intro: () => wizHead("reader", L("NFC reader"), L("Plug in your reader and put a spool on it to test.")) },
  { title: "Storage", borrow: "#layouttool", enter: () => { blankCabDraft(); drawCabEditor(); },
    intro: () => wizHead("storage", L("Set up your storage"), L("Enter how many levels each storage has and how many spools fit on each level. Tap ? for examples.")),
    check: async () => {
      if (!cabDraft) return true;
      if (!cabDraft.every(cabFilled)) { await cabMissingAsk(); return false; }
      return applyCabs();
    } },   // "Weiter" applies unsaved changes
  { title: "Printer", borrow: "#bambutool", enter: () => loadBambuCfg(),
    ready: () => overview?.bambu?.status === "connected" || !!printerData?.printers?.some((p) => p.connected),
    intro: () => wizHead("printer", L("Connect your printer"), L("Connect your Bambu Lab printer: PixxelSpool then sees which spool is in which AMS slot, how much is left and whether it's enough for the running print.")) },
  { title: "Home Assistant", borrow: "#hatool", enter: () => { loadHaCfg(); loadSensors(); },
    // "Next" once connected or address and token are entered; it connects and saves the sensors (no separate save)
    ready: () => overview?.ha?.status === "connected" || !!($("#haUrl").value.trim() && $("#haToken").value.trim()),
    check: async () => {
      if (overview?.ha?.status !== "connected" && !(await connectHa())) return false;
      if ($("#climatecfg").children.length) await saveSettings({ ha_poll_seconds: $("#setPoll").value, climate: readClimateCfg() });
      return true;
    },
    intro: () => wizHead("ha", "Home Assistant", L("Only if you use Home Assistant with sensors in your storage: PixxelSpool then shows temperature and humidity and warns when it gets too damp. Otherwise just tap “Skip”.")) },
  { title: "Finished", next: "Let's go", html: () => {
      const s = SET(), r = overview?.reader || {};
      const row = (ok, label, value) => `<li class="${ok ? "ok" : ""}"><span class="dot"></span><b>${label}</b><span>${value}</span></li>`;
      return `<div class="wizdone"><div class="check"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></div>
        <h2>${L("All set up")}</h2>
        <ul class="wizsum">
        ${row(r.status === "ready", L("Reader"), L(r.status === "ready" ? "ready" : "not detected yet"))}
        ${row(true, L("Storage"), (s.cabinets || []).map((c) => esc(c.name)).join(", "))}
        ${row(overview?.bambu?.status === "connected", L("Printer"), L(overview?.bambu?.status === "connected" ? "connected" : "not connected"))}
        ${row(overview?.ha?.status === "connected", "Home Assistant", L(overview?.ha?.status === "connected" ? "connected" : "not connected"))}
        </ul></div>`; },
    finish: async () => { await api("/api/setup/done", { method: "POST" }); } },
];
function wizBorrow(sel) {
  const el = $(sel);
  if (!wiz.homes.has(sel)) { const ph = document.createComment(sel); el.before(ph); wiz.homes.set(sel, ph); }
  $("#wizbody").append(el);
}
function wizGiveBack() { wiz.homes.forEach((ph, sel) => ph.replaceWith($(sel))); wiz.homes.clear(); }
function stopIntro() { wiz.introStop?.(); wiz.introStop = null; }
function drawWizard() {
  const st = WIZ[wiz.i], body = $("#wizbody");
  stopIntro();
  wizGiveBack();
  $("#wizstep").textContent = L("Step {0} of {1}: {2}", wiz.i + 1, WIZ.length, L(st.title));
  $("#wizdots").innerHTML = WIZ.map((_, k) => `<span class="${k === wiz.i ? "on" : k < wiz.i ? "done" : ""}"></span>`).join("");
  $(".wizbox").classList.toggle("first", wiz.i === 0);
  body.innerHTML = st.html ? st.html() : st.intro ? st.intro() : "";
  if (st.borrow) { wizBorrow(st.borrow); $(st.borrow).classList.add("open"); }
  $("#wizback").style.visibility = wiz.i ? "visible" : "hidden";
  $("#wizskip").hidden = true;
  wizSync();
  st.enter?.();
  body.scrollTop = 0; wizMore(); setTimeout(wizMore, 600);
  body.classList.remove("in-fwd", "in-back"); void body.offsetWidth;    // restart the slide-in
  body.classList.add(wiz.dir < 0 ? "in-back" : "in-fwd");
  drawWizTheme();
}
// light/dark switch in the wizard's corner; a fresh install starts light
const isDark = () => document.documentElement.dataset.theme === "dark" ||
  (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
function drawWizTheme() {
  const b = $("#wiztheme"), d = isDark();
  b.classList.toggle("dark", d); b.setAttribute("aria-pressed", d ? "true" : "false");
}
$("#wiztheme").onclick = () => switchTheme(() => { setPref("theme", isDark() ? "light" : "dark"); applyTheme(); drawWizTheme(); });
function openWizard(step = 0) {
  if (pref("theme", "") === "") { setPref("theme", "light"); applyTheme(); }
  wiz.open = true; wiz.i = Math.max(0, Math.min(WIZ.length - 1, step)); wiz.dir = 1; $("#wizard").hidden = false; document.body.classList.add("wizopen"); drawWizard();
}
function closeWizard(animate = false) {
  wiz.open = false; const w = $("#wizard");
  stopIntro();
  document.body.classList.remove("wizopen");
  if (!animate) { wizGiveBack(); w.hidden = true; return; }
  w.classList.add("closing");                       // fade out over the now visible app, then hide
  setTimeout(() => { w.classList.remove("closing"); w.hidden = true; wizGiveBack(); }, 720);
}
async function wizGo(d, skip) {
  const st = WIZ[wiz.i];
  if (d > 0 && !skip && st.check && !(await st.check())) return;
  st.leave?.();
  if (d > 0 && st.finish) {
    try { await st.finish(); } catch (e) { toast(e.message); return; }
    await refresh(); showView("storage"); closeWizard(true); toast(L("PixxelSpool is set up"));
    setTimeout(() => startTour(true), 900); return;
  }
  wiz.dir = d; wiz.i = Math.max(0, Math.min(WIZ.length - 1, wiz.i + d)); drawWizard();
}
function wizMore() { const b = $("#wizbody"); b.classList.toggle("more", b.scrollHeight - b.scrollTop - b.clientHeight > 4); }
$("#wizbody").addEventListener("scroll", wizMore, { passive: true });
$("#wizbody").addEventListener("toggle", () => setTimeout(wizMore, 50), true);   // opened or closed <details>
addEventListener("resize", () => wiz.open && wizMore());
// steps that can be left out offer only one button: "Skip" until the part is set up, then "Next"
function wizSync() {
  if (!wiz.open) return;
  const st = WIZ[wiz.i], ready = st.ready ? st.ready() : true;
  $("#wiznext").textContent = L(st.ready ? (ready ? "Next" : "Skip") : st.next || "Next");
  $("#wiznext").dataset.skip = ready ? "" : "1";
}
$("#wiznext").onclick = async () => {
  const skip = !!$("#wiznext").dataset.skip, st = WIZ[wiz.i];
  if (skip && st.skipAsk && !(await st.skipAsk())) return;   // e.g. no reader: explain first that one is recommended
  wizGo(1, skip);
};
$("#wizback").onclick = () => wizGo(-1);
$("#wizskip").onclick = () => wizGo(1, true);
$("#wizopen").onclick = () => { closeNav?.(); openWizard(); };
// long print names (file names without spaces) are cut with "…"; a tap shows the whole name
let jobNameFull = false;
function fitJobNames() {   // cut to the available width with " …" (CSS text-overflow cannot add the space in Safari)
  document.querySelectorAll(".jobname").forEach((n) => {
    const full = n.dataset.full || "";
    n.textContent = full;
    if (jobNameFull || n.scrollWidth <= n.clientWidth) return;
    let lo = 0, hi = full.length;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      n.textContent = full.slice(0, mid).trimEnd() + " …";
      if (n.scrollWidth <= n.clientWidth) lo = mid; else hi = mid - 1;
    }
    n.textContent = full.slice(0, lo).trimEnd() + " …";
  });
}
let fitT; addEventListener("resize", () => { clearTimeout(fitT); fitT = setTimeout(fitJobNames, 120); });
document.addEventListener("click", (e) => {
  const n = e.target.closest(".jobname"); if (!n) return;
  jobNameFull = !jobNameFull; document.querySelectorAll(".jobname").forEach((x) => x.classList.toggle("full", jobNameFull));
  fitJobNames();
});
// ------------------------------------------------------------ short tour after the wizard
// A few spotlights on the main parts of the screen. Each step names candidate elements; the first visible one is
// highlighted, so the tour fits every navigation layout (hamburger, top bar, tab row, rail).
const TOUR = [
  { sel: ["#panel"], title: "Place a spool", text: "It all starts here: place a spool on the reader. PixxelSpool recognizes it and shows you where it belongs." },
  { sel: ["header .search"], title: "Search", text: "Type a color, number, line or place, and you instantly see where the matching spool is." },
  { sel: ["#cabs .slot", "#cabs"], title: "Your storage", text: "Every field is a place in your storage. Tap one to store a spool without a reader or to look at it." },
  { sel: ["#burger", "#nav"], title: "Menu", text: "Switch here between Storage, Print, Catalog, Statistics and Options." },
  { sel: ["#stats", "#bell"], multi: true, title: "Status and notices", text: "The status shows reader, printer and Home Assistant. The bell collects notices, for example when a spool is almost empty." },
];
let tour = null;
function tourTarget(step) {
  for (const sel of step.sel) {
    const el = $(sel);
    if (!el) continue;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden") return el;
  }
  return null;
}
// the area a step highlights: its first visible element, or all of its visible elements together (union)
function tourRect(step) {
  const first = tourTarget(step); if (!first) return null;
  if (!step.union) return first.getBoundingClientRect();
  const rs = step.sel.map((sel) => $(sel)).filter((el) => el && el.getBoundingClientRect().width > 0).map((el) => el.getBoundingClientRect());
  const top = Math.min(...rs.map((r) => r.top)), left = Math.min(...rs.map((r) => r.left));
  const bottom = Math.max(...rs.map((r) => r.bottom)), right = Math.max(...rs.map((r) => r.right));
  return { top, left, bottom, right, width: right - left, height: bottom - top };
}
function startTour(afterWizard = false) {
  if (tour) return;
  closeNav();
  if (view !== "storage") showView("storage");
  const box = document.createElement("div");
  box.id = "tour";
  box.innerHTML = `<svg class="tourmask" hidden><path fill-rule="evenodd"/></svg><div class="tourspot"></div><div class="tourspot extra nomask" hidden></div><div class="tourtip" role="dialog" aria-live="polite"><b></b><p></p>
    <div class="tourfoot"><span class="tourdots"></span><button class="small tourskip"></button><button class="small primary tournext"></button></div></div>`;
  document.body.appendChild(box);
  tour = { i: 0, box, afterWizard };
  box.querySelector(".tourskip").onclick = () => endTour();
  box.querySelector(".tournext").onclick = () => tourGo(1);
  box.onclick = (e) => { if (e.target === box) tourGo(1); };
  addEventListener("resize", placeTour); addEventListener("scroll", placeTour, true);
  addEventListener("keydown", tourKey);
  tourGo(0);
}
function tourKey(e) {
  if (e.key === "Escape") endTour();
  else if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); tourGo(1); }
  else if (e.key === "ArrowLeft") tourGo(-1);
}
function tourGo(d) {
  let i = tour.i + d;
  while (i >= 0 && i < TOUR.length && !tourTarget(TOUR[i])) i += d || 1;   // skip parts this layout does not show
  if (i < 0) i = tour.i;
  if (i >= TOUR.length) return endTour();
  tour.i = i;
  const st = TOUR[i], b = tour.box;
  b.querySelector(".tourtip b").textContent = L(st.title);
  b.querySelector(".tourtip p").textContent = L(st.text);
  b.querySelector(".tourdots").innerHTML = TOUR.map((_, k) => `<i class="${k === i ? "on" : ""}"></i>`).join("");
  b.querySelector(".tourskip").textContent = L("Skip");
  b.querySelector(".tourskip").hidden = i === TOUR.length - 1;
  b.querySelector(".tournext").textContent = i === TOUR.length - 1 ? L("Finished") : L("Next");
  const el = tourTarget(st), r = el.getBoundingClientRect();
  if (r.top < 0 || r.bottom > innerHeight) el.scrollIntoView({ block: "center", behavior: "smooth" });
  placeTour(); setTimeout(placeTour, 400);
}
function placeTour() {
  if (!tour) return;
  const step = TOUR[tour.i], r = tourRect(step); if (!r) return;
  const pad = 6, b = tour.box;
  const box = (q) => { const t = Math.max(4, q.top - pad), l = Math.max(4, q.left - pad);
    return { top: t, left: l, h: Math.min(q.bottom + pad, innerHeight - 4) - t, w: Math.min(q.right + pad, innerWidth - 4) - l }; };
  const px = (q) => ({ top: q.top + "px", left: q.left + "px", width: q.w + "px", height: q.h + "px" });
  // multi: each element gets its own spot (e.g. status and bell, without the menu between them)
  const parts = step.multi ? step.sel.map((sel) => $(sel)).filter((el) => el && el.getBoundingClientRect().width > 0).map((el) => box(el.getBoundingClientRect())) : [];
  const multi = parts.length > 1, spot = b.querySelector(".tourspot"), extra = b.querySelector(".tourspot.extra"), mask = b.querySelector(".tourmask");
  spot.classList.toggle("nomask", multi); extra.hidden = !multi; mask.toggleAttribute("hidden", !multi);
  const { top, left, h, w } = box(r);
  Object.assign(spot.style, px(multi ? parts[0] : { top, left, h, w }));
  if (multi) {
    Object.assign(extra.style, px(parts[1]));
    const rr = (q, k = 18) => `M${q.left + k},${q.top}h${q.w - 2 * k}a${k},${k} 0 0 1 ${k},${k}v${q.h - 2 * k}a${k},${k} 0 0 1 -${k},${k}h-${q.w - 2 * k}a${k},${k} 0 0 1 -${k},-${k}v-${q.h - 2 * k}a${k},${k} 0 0 1 ${k},-${k}z`;
    mask.setAttribute("viewBox", `0 0 ${innerWidth} ${innerHeight}`);
    mask.querySelector("path").setAttribute("d", `M0,0H${innerWidth}V${innerHeight}H0z` + parts.map((q) => rr(q, Math.min(18, q.h / 2, q.w / 2))).join(""));
  }
  const tip = b.querySelector(".tourtip"), tw = tip.offsetWidth, th = tip.offsetHeight, gap = 12;
  let y = top + h + gap;
  if (y + th > innerHeight - 8) y = top - th - gap;                   // not enough room below: above
  if (y < 8) y = Math.min(innerHeight - th - 8, Math.max(8, top + 16)); // large targets: over the target
  const x = Math.min(innerWidth - tw - 8, Math.max(8, left + w / 2 - tw / 2));
  Object.assign(tip.style, { top: y + "px", left: x + "px" });
}
function endTour() {
  if (!tour) return;
  setPref("tourdone", "1");
  removeEventListener("resize", placeTour); removeEventListener("scroll", placeTour, true); removeEventListener("keydown", tourKey);
  const b = tour.box, after = tour.afterWizard; tour = null;
  b.classList.add("closing"); setTimeout(() => b.remove(), 300);
  if (after) setTimeout(batchHint, 500);
}
// after the first tour: a hint on the bulk inventory for everyone with many spools to put away
async function batchHint() {
  const step = (n, t) => `<li><span class="bhn">${n}</span>${t}</li>`;
  const r = await ask(`<div class="bhint"><span class="bhico" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/></svg></span>
    <h3>${L("Many spools to put away?")}</h3>
    <p class="sub">${L("The bulk inventory saves you the work: scan all spools one after the other, PixxelSpool then suggests a slot for each.")}</p>
    <ol class="bhsteps">${step(1, L("Scan all spools"))}${step(2, L("Check the suggested slots"))}${step(3, L("Put them away"))}</ol>
    <div class="bhtips"><p>💡 ${T("batchLogo")}</p><p>📦 ${T("batchTip")}</p></div>
    <p class="sub bhlater">${L("You find it later under Options › Bulk inventory.")}</p></div>`,
    { block: true, ok: T("batchStart"), cancel: L("Later") });
  if (r === true) openOpt("batchtool");
}
$("#touropen").onclick = () => startTour();


document.body.dataset.view = view;
applyLang();
refresh().then(render);
api("/api/batch").then((b) => { batch = b; drawBatch(); });
connectLive();
// logo and name in the header lead back to the storage
document.querySelectorAll("header img.logo, header h1").forEach((el) => (el.onclick = () => {
  if (view !== "storage") showView("storage");
  window.scrollTo({ top: 0, behavior: "smooth" });
}));
// large colour preview from the swatch in the spool panel; closes with ×, Esc or a tap beside it
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-swzoom]") || panel?.kind !== "spool") return;
  const s = panel.spool, prev = document.activeElement;
  const box = document.createElement("div"); box.className = "swzoom"; box.setAttribute("role", "dialog"); box.setAttribute("aria-modal", "true");
  box.innerHTML = `<button class="swx" aria-label="${esc(T("close"))}">×</button>${sw(s)}
    <div class="swcap"><b>${title(s)}</b><span>${esc([s.bambu_no ? "Bambu " + s.bambu_no : s.sku, s.hex ? s.hex.toUpperCase() : ""].filter(Boolean).join(" · "))}</span></div>`;
  document.body.append(box); requestAnimationFrame(() => box.classList.add("in"));
  const close = () => { document.removeEventListener("keydown", key, true); box.classList.remove("in"); setTimeout(() => box.remove(), 200); prev?.focus?.(); };
  const key = (ev) => { if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); close(); } };
  document.addEventListener("keydown", key, true);
  box.onclick = (ev) => { if (!ev.target.closest(".swatch")) close(); };
  box.querySelector(".swx").focus();
});
