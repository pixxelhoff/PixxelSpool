"""Web server (FastAPI): REST API, live updates via server-sent events, the single-page UI and background threads.

User-facing texts are English; the browser translates them with filament_tool/locales/*.json (de, es).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import settings, insights
from . import db, logic
from .reader import ReaderThread
from .homeassistant import HAThread
from . import auth, bambu, brands, camera, hms, host, logs, notices, offsite, push, remote, stats, updater

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logs.setup()
logs.set_detail(bool(settings.load().get("log_detail")))
STATIC = Path(__file__).parent / "static"
LOCALES = Path(__file__).parent / "locales"
MOCK = os.environ.get("FILAMENT_MOCK") == "1"
_started = time.time()

app = FastAPI(title="PixxelSpool")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def no_stale_cache(request: Request, call_next):
    """Make the iPhone home-screen app always load the new UI after an update."""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp

_OPEN_PATHS = ("/static/", "/api/auth")
_api_log = logging.getLogger("api")


@app.middleware("http")
async def log_calls(request: Request, call_next):
    """Detailed log only: every API call that changes something, and failed ones (path and status, never the body)."""
    if not _api_log.isEnabledFor(logging.DEBUG) or not request.url.path.startswith("/api/"):
        return await call_next(request)
    t0 = time.monotonic()
    resp = await call_next(request)
    if request.method != "GET" or resp.status_code >= 400:
        _api_log.debug("%s %s -> %d (%d ms)", request.method, request.url.path, resp.status_code, (time.monotonic() - t0) * 1000)
    return resp


@app.middleware("http")
async def require_login(request: Request, call_next):
    """With an app password (Options › System) everything except the page itself, its files and the login needs a
    valid login cookie. Without a password nothing changes."""
    path = request.url.path
    if path in ("/", "/sw.js", "/favicon.ico") or path.startswith(_OPEN_PATHS) or auth.valid(request.cookies.get(auth.COOKIE, "")):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"error": "login", "login": True}, status_code=401)
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/")


def _login_cookie(request: Request, resp, remember: bool = True):
    days = auth.DAYS if remember else 1
    resp.set_cookie(auth.COOKIE, auth.token(days), max_age=days * 86400 if remember else None, httponly=True,
                    samesite="lax", secure=(request.headers.get("x-forwarded-proto") or request.url.scheme) == "https")
    return resp


@app.get("/api/auth")
def auth_state(request: Request):
    on = auth.enabled()
    return {"enabled": on, "ok": auth.valid(request.cookies.get(auth.COOKIE, "")),
            "host": host.KIND,   # the sign-in screen shows only the reset way that fits this platform
            "passkeys": auth.passkeys_count() if on else 0, "passkey_lib": auth.passkeys_available()}


@app.post("/api/auth/login")
def auth_login(request: Request, payload: dict = Body(...)):
    if not auth.enabled():
        return {"ok": True}
    try:
        ok = auth.check_password(str(payload.get("password") or ""))
    except auth.Locked as e:
        raise logic.InventoryError(str(e))
    if not ok:
        raise logic.InventoryError("Wrong password")
    return _login_cookie(request, JSONResponse({"ok": True}), bool(payload.get("remember", True)))


@app.post("/api/auth/logout")
def auth_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE)
    return resp


def _auth_change_allowed(request: Request, payload: dict) -> None:
    """Changing the password needs a valid login and, when one is set, the current password."""
    try:
        if auth.enabled() and not (auth.valid(request.cookies.get(auth.COOKIE, "")) and auth.check_password(str(payload.get("current") or ""))):
            raise logic.InventoryError("Wrong password")
    except auth.Locked as e:
        raise logic.InventoryError(str(e))


@app.post("/api/auth/password")
def auth_password(request: Request, payload: dict = Body(...)):
    """Turn the password on or change it. Returns the new recovery code (shown once)."""
    _auth_change_allowed(request, payload)
    try:
        code = auth.set_password(str(payload.get("password") or ""))
    except ValueError as e:
        raise logic.InventoryError(str(e))
    return _login_cookie(request, JSONResponse({"ok": True, "code": code}))


@app.post("/api/auth/recovery-code")
def auth_recovery_code(request: Request, payload: dict = Body(...)):
    _auth_change_allowed(request, payload)
    return {"code": auth.new_recovery_code()}


@app.post("/api/auth/off")
def auth_off(request: Request, payload: dict = Body(...)):
    _auth_change_allowed(request, payload)
    auth.disable()
    return {"ok": True}


# ------------------------------------------------------------ passkeys (only while the password is on)
def _rp(request: Request) -> tuple:
    """The address the browser uses (e.g. pi.tail1234.ts.net behind Tailscale HTTPS): passkeys are bound to it."""
    hostport = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip().lower()
    name = hostport
    if name.startswith("["):
        name = name[1:].split("]", 1)[0]
    elif name.count(":") == 1:
        name = name.split(":", 1)[0]
    return name, hostport


def _passkeys_ready() -> None:
    if not auth.enabled():
        raise logic.InventoryError("Passkeys can only be used while the password is on")
    if not auth.passkeys_available():
        raise logic.InventoryError("Passkeys are not available: a package is missing. Please run the update again.")


def _need_login(request: Request) -> None:
    _passkeys_ready()
    if not auth.valid(request.cookies.get(auth.COOKIE, "")):
        raise logic.InventoryError("Please sign in first")


@app.post("/api/auth/passkey/options")
def auth_passkey_options(request: Request):
    """Sign-in with a passkey, step 1: a fresh challenge for the browser."""
    _passkeys_ready()
    return auth.passkey_login_options(_rp(request)[0])


@app.post("/api/auth/passkey/login")
def auth_passkey_login(request: Request, payload: dict = Body(...)):
    """Sign-in with a passkey, step 2: check the browser's answer, then the same login cookie as with the password."""
    _passkeys_ready()
    rp_id, hostport = _rp(request)
    try:
        auth.passkey_login(rp_id, hostport, str(payload.get("ticket") or ""), payload.get("credential") or {})
    except ValueError as e:
        raise logic.InventoryError(str(e))
    return _login_cookie(request, JSONResponse({"ok": True}), bool(payload.get("remember", True)))


@app.get("/api/auth/passkeys")
def auth_passkeys(request: Request):
    _need_login(request)
    return {"passkeys": auth.passkeys_list(), "rp_id": _rp(request)[0]}


@app.post("/api/auth/passkeys/options")
def auth_passkeys_add_options(request: Request, payload: dict = Body(...)):
    """Add a passkey, step 1: needs the current password, like every other change of the sign-in."""
    _need_login(request)
    _auth_change_allowed(request, payload)
    return auth.passkey_register_options(_rp(request)[0])


@app.post("/api/auth/passkeys")
def auth_passkeys_add(request: Request, payload: dict = Body(...)):
    """Add a passkey, step 2: the ticket from step 1 shows that the password was entered."""
    _need_login(request)
    rp_id, hostport = _rp(request)
    try:
        return auth.passkey_register(rp_id, hostport, str(payload.get("ticket") or ""), payload.get("credential") or {},
                                     str(payload.get("name") or ""))
    except ValueError as e:
        raise logic.InventoryError(str(e))


@app.patch("/api/auth/passkeys/{pk_id}")
def auth_passkeys_rename(request: Request, pk_id: int, payload: dict = Body(...)):
    _need_login(request)
    try:
        auth.passkey_rename(pk_id, str(payload.get("name") or ""))
    except ValueError as e:
        raise logic.InventoryError(str(e))
    return {"ok": True}


@app.delete("/api/auth/passkeys/{pk_id}")
def auth_passkeys_remove(request: Request, pk_id: int):
    _need_login(request)
    auth.passkey_remove(pk_id)
    return {"ok": True}


@app.post("/api/auth/recover")
def auth_recover(request: Request, payload: dict = Body(...)):
    """Forgotten password: recovery code plus a new password."""
    try:
        code = auth.recover(str(payload.get("code") or ""), str(payload.get("password") or ""))
    except ValueError as e:
        raise logic.InventoryError(str(e))
    return _login_cookie(request, JSONResponse({"ok": True, "code": code}))


_subscribers: "set[asyncio.Queue]" = set()
_loop: Optional[asyncio.AbstractEventLoop] = None
_watch = None
_reader_state = {"status": "simulated" if MOCK else "starting", "detail": "", "kind": None}
_reader: Optional[ReaderThread] = None
_last_scan: Optional[dict] = None


def broadcast(msg: dict) -> None:
    """Send an event to all open pages (thread-safe)."""
    data = json.dumps(msg, ensure_ascii=False, default=str)
    if _loop is None:
        return
    for q in list(_subscribers):
        _loop.call_soon_threadsafe(q.put_nowait, data)


_batch: dict = {"active": False, "tags": [], "items": []}
_ha = None
_printers: dict = {}      # printer id -> bambu.BambuThread (one connection per printer)
_job_done: dict = {}      # printer id -> ((state, job name), first time seen finished/failed)
JOB_DONE_HIDE_H = 12      # the printer card stops showing a finished/cancelled print after this many hours


def _sync_printers(reload: str = "") -> None:
    """Start threads for new printers, stop removed ones; reload one printer after its settings changed."""
    ids = [p["id"] for p in bambu.printers()]
    for pid in list(_printers):
        if pid not in ids:
            _printers.pop(pid).stop()
            _cameras.pop(pid, None)
    for pid in ids:
        if pid not in _printers:
            t = (bambu.MockPrinter if MOCK else bambu.BambuThread)(pid, _bambu_changed)
            t.start()
            _printers[pid] = t
        elif pid == reload:
            _printers[pid].reload()


def _multi() -> bool:
    return len(_printers) > 1


def _pname(pid: str) -> str:
    """Printer name for labels, empty with a single printer (the UI then shows no printer names)."""
    return bambu.name_of(pid) if _multi() else ""


_audit: dict = {"active": False, "order": [], "idx": 0, "seen": {}, "unknown": 0, "last": None, "skipped": []}


def _audit_state() -> dict:
    return {k: _audit[k] for k in ("active", "order", "idx", "seen", "unknown", "last", "skipped")}


def _audit_scan(tag: dict) -> None:
    with db.session() as conn:
        r = conn.execute(logic.SPOOL_SELECT + " WHERE s.tray_uid = ? AND s.status != 'empty'",
                         (tag.get("tray_uid"),)).fetchone()
    here = _audit["order"][_audit["idx"]] if _audit["order"] else None
    if r is None:
        _audit["unknown"] += 1
        _audit["last"] = {"kind": "unknown"}
    else:
        sp = dict(r)
        kind = "ok" if sp["slot_id"] == here else "misplaced"
        _audit["seen"][str(sp["id"])] = {"kind": kind, "found_at": here}
        _audit["last"] = {"kind": kind, "spool": sp, "found_at": here}
    broadcast({"type": "audit", **_audit_state()})


_reader_test = {"until": 0.0}
_link_next = {"spool_id": None, "until": 0.0}   # "retrofit tag": the next sticker placed belongs to this spool


def _plain_scan(tag: dict) -> None:
    """Retrofitted tag (NTAG sticker): show the linked spool, or offer to link it."""
    global _last_scan
    import time as _t
    if _batch["active"]:
        broadcast({"type": "toast", "text": "Sticker tags don't work while storing several spools"})
        return
    with db.session() as conn:
        sid = _link_next["spool_id"] if _t.time() < _link_next["until"] else None
        _link_next.update(spool_id=None, until=0.0)
        if sid is not None:
            try:
                result = {"kind": "linked", "tag": None, "spool": logic.link_plain(conn, sid, tag)}
            except logic.InventoryError as e:
                result = {**logic.plain_scan(conn, tag), "msg": str(e)}
        else:
            result = logic.plain_scan(conn, tag)
    _last_scan = result
    broadcast({"type": "scan", "result": result})
    if result["kind"] == "linked":
        broadcast({"type": "changed"})


def on_tag(tag: dict) -> None:
    global _last_scan
    import time as _t
    if _t.time() < _reader_test["until"] or not settings.load().get("setup_done"):
        # read test (options / setup): only show the result, do not touch the stock
        broadcast({"type": "testscan", "tag": tag})
        return
    if _audit["active"]:
        _audit_scan(tag)
        return
    if tag.get("plain"):
        _plain_scan(tag)
        return
    if _batch["active"]:
        if any(t["tray_uid"] == tag["tray_uid"] for t in _batch["tags"]):
            broadcast({"type": "batch", "dup": True, **_batch_state()})
            return
        with db.session() as conn:
            preview = logic.batch_preview(conn, tag)
        _batch["tags"].append(tag)
        _batch["items"].append(preview)
        broadcast({"type": "batch", **_batch_state()})
        return
    with db.session() as conn:
        result = logic.handle_scan(conn, tag)
    _last_scan = result
    broadcast({"type": "scan", "result": result})


def on_status(status: str, detail: str) -> None:
    if status == "read_error":  # short glitch while placing a spool, the reader stays ready
        broadcast({"type": "readerror", "detail": detail})
        return
    _reader_state.update(status=status, detail=detail, kind=_reader.kind if _reader else None)
    broadcast({"type": "reader", **_reader_state})


@app.on_event("startup")
async def startup() -> None:
    global _loop
    _loop = asyncio.get_running_loop()
    host.secure_data_dir()
    db.init()
    with db.session() as conn:
        brands.fill_shop_prices(conn)
    global _reader
    if not MOCK:
        _reader = ReaderThread(on_tag, on_status, settings.load)
        _reader.start()
    global _ha
    _ha = HAThread(lambda res: broadcast({"type": "changed"}))
    _ha.start()
    _sync_printers()
    if host.KIND != "pi":   # the Pi uses a systemd timer for this
        threading.Thread(target=_daily_backups, daemon=True, name="daily-backup").start()
    global _watch
    _watch = notices.Watcher(lambda: dict(_printers), _pname, lambda: _ha, _job_view,
                             lambda: broadcast({"type": "notices", **notices.unread()}))
    _watch.start()
    if host.KIND == "pi":
        threading.Thread(target=_confirm_update, daemon=True, name="update-guard").start()
    from . import power
    power.check_and_start()


@app.on_event("shutdown")
async def shutdown() -> None:
    from . import power
    power.clean_stop()


def _confirm_update() -> None:
    """A freshly updated version that runs for a while works: the update guard is no longer needed (guard.py)."""
    from . import __version__, guard
    time.sleep(guard.CONFIRM_AFTER)
    g = guard.confirm(__version__)
    if g and g.get("auto"):
        notices.add("update", f"autodone:{g.get('to')}", "Security update {0} was installed automatically.",
                    [g.get("to")], "info", "opt:updatetool")


def _daily_backups() -> None:
    """Nightly backup without systemd (Windows app, desktop): at 3:30, or soon after start when today's is missing."""
    from datetime import datetime, timedelta
    from . import daily_backup
    time.sleep(120)
    while True:
        try:
            if not (db.DATA_DIR / "backups" / f"inventory-{datetime.now():%Y-%m-%d}.db").exists():
                daily_backup.run(settings.load()["backup_keep_days"])
                offsite.run()
        except Exception as e:
            logging.getLogger("backup").warning("Daily backup failed: %s", e)
        now = datetime.now()
        nxt = now.replace(hour=3, minute=30, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        time.sleep(min((nxt - now).total_seconds(), 6 * 3600))


@app.exception_handler(logic.InventoryError)
async def inventory_error(_: Request, exc: logic.InventoryError):
    return JSONResponse({"error": str(exc)}, status_code=409)


# donation pages for the app (Options › About and the one-time note). Empty = no button.
DONATE_LINKS = {
    "github": "pixxelhoff",   # GitHub Sponsors user name -> https://github.com/sponsors/<name>
    "kofi": "pixxelhoff",   # Ko-fi page name -> https://ko-fi.com/<name>
}


@app.get("/")
def index(request: Request):
    from fastapi.responses import HTMLResponse
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    ver = str(int(max(f.stat().st_mtime for f in STATIC.iterdir())))
    from . import __version__
    html = html.replace("__PM_RELEASE__", __version__).replace("__PM_REPO__", updater.REPO)
    # language: inline the dictionary so the UI starts already translated
    lang = settings.lang(request.headers.get("accept-language", ""))
    words = {}
    if lang != "en":
        try:
            words = json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            lang, words = "en", {}
    donate = {k: v for k, v in DONATE_LINKS.items() if v}
    boot = "<script>window.PS_LANG=%s;window.PS_DICT=%s;window.PS_DONATE=%s;</script>" % (
        json.dumps(lang), json.dumps(words, ensure_ascii=False).replace("</", "<\\/"), json.dumps(donate))
    html = html.replace('<html lang="en">', f'<html lang="{lang}">').replace("<script src=\"/static/app.js", boot + "<script src=\"/static/app.js", 1)
    return HTMLResponse(html.replace("VERSION", ver), headers={"Cache-Control": "no-cache"})


LABEL_TEXTS = ["Labels", "Labels for your storage slots. The QR code opens the slot in PixxelSpool.", "Storage", "all",
               "Reserve areas too", "Size", "Custom", "Content", "Storage name", "Purpose / label", "Position (level and slot)",
               "QR code", "Logo in the QR code", "Look", "Colored strip", "Color", "Rounded corners", "Cut lines", "Sheet",
               "Gap between labels", "Page margin", "Skip fields at the start",
               "For a sheet that is already partly used: the first fields stay empty.", "Print",
               "In the print dialog choose: paper A4, scale 100 % (not “fit to page”), margins “none” and no headers and footers.",
               "Reset settings", "{0} labels · {1} per page · {2} pages · QR opens {3}",
               "Safari: switch off “Print headers and footers” in the print dialog, otherwise the labels do not fit on the page.",
               "QR code opens", "The .local name keeps working when the router gives PixxelSpool a new IP address."]


@app.get("/labels")
def labels(request: Request, cab: str = "", logo: int = 1, addr: str = ""):
    """Printable slot labels: a label designer with an A4 preview (static/labels.html), the QR codes come from here."""
    from fastapi.responses import HTMLResponse
    from html import escape
    addr_choice = addr
    addr = request.headers.get("host") or "pixxelspool.local:8000"
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    name, _, port = addr.partition(":") if addr.count(":") <= 1 else (addr, "", "")
    if name in ("localhost", "127.0.0.1"):   # opened on the PC or Mac itself: a phone can't reach that address
        addr = host.lan_ip() + (f":{port}" if port else "")
    here = f"{scheme}://{addr}/"
    # the QR code may also open the device's .local name: it stays valid when the router hands out a new IP address
    mdns = host.mdns_name()
    local = f"{scheme}://{mdns}" + (f":{port}" if port else "") + "/" if mdns and name != mdns else ""
    bases = [{"key": "", "url": here}] + ([{"key": "local", "url": local}] if local else [])
    base = local if addr_choice == "local" and local else here
    cabs = {c["key"]: c for c in settings.load()["cabinets"]}
    with db.session() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM slots ORDER BY cabinet, kind, row, pos")]
    _t = push._tr
    items = []
    for r in rows:
        c = cabs.get(r["cabinet"], {})
        if r["kind"] == "cabinet":
            unit = _t("Rod") if c.get("unit") == "rod" else _t("Level")
            where = _t("{0} {1} · slot {2}").format(unit, db.row_label(c, r["row"]) if c else r["row"], r["pos"])
        else:
            where = _t("Reserve")
        items.append({"id": r["id"], "cab": r["cabinet"], "cabName": str(c.get("name") or r["cabinet"]),
                      "purpose": str(c.get("label") or ""), "where": where, "res": r["kind"] != "cabinet",
                      "qr": remote.qr_label_svg(base + "#slot=" + r["id"], logo=bool(logo), accent="currentColor")})
    data = {"base": base, "bases": bases, "addr": "local" if base == local and local else "", "logo": bool(logo), "cab": cab if cab in cabs else "", "items": items,
            "cabs": [{"key": k, "name": str(c.get("name") or k)} for k, c in cabs.items()],
            "T": {k: _t(k) for k in LABEL_TEXTS}}
    page = (Path(__file__).parent / "static" / "labels.html").read_text(encoding="utf-8")
    page = (page.replace("__LANG__", settings.lang()).replace("__TITLE__", escape("PixxelSpool " + _t("Labels")))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


@app.get("/api/events")
async def events(request: Request):
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.add(q)

    async def stream():
        try:
            yield f"data: {json.dumps({'type': 'reader', **_reader_state})}\n\n"
            while not await request.is_disconnected():
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            _subscribers.discard(q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@app.get("/api/overview")
def overview():
    with db.session() as conn:
        data = logic.overview(conn)
    data["reader"] = _reader_state
    data["ha"] = {k: v for k, v in (_ha.state if _ha else {}).items() if k not in ("sensors",)}
    data["printers"] = [{"id": pid, "name": bambu.name_of(pid), "status": t.state.get("status"), "detail": t.state.get("detail")}
                        for pid, t in _printers.items()]
    # summary for the status menu: connected if any printer is
    conn_ = [p for p in data["printers"] if p["status"] == "connected"]
    data["bambu"] = {"status": "connected", "detail": ", ".join(p["detail"] for p in conn_)} if conn_ else \
        {k: v for k, v in (data["printers"][0] if data["printers"] else {"status": "off"}).items() if k in ("status", "detail")}
    data["ams"] = _ams_view()
    data["jobs"] = [j for j in (_job_view(pid) for pid in _printers) if j]
    data["job"] = next((j for j in data["jobs"] if j["active"]), data["jobs"][0] if data["jobs"] else None)
    data["settings"] = settings.load()
    data["notices"] = notices.unread()
    data["host"] = host.info()
    return data


@app.get("/api/remote")
def remote_status():
    return remote.status()


@app.post("/api/remote")
def remote_action(request: Request, payload: dict = Body(...)):
    """Remote access: {"action": "login" | "https_on" | "https_off" | "on" | "off" | "logout"}."""
    act = payload.get("action")
    try:
        if act == "login":
            return remote.login()
        if act == "https_on":
            return remote.enable_https((request.scope.get("server") or (None, 8000))[1] or 8000)
        if act == "https_off":
            return remote.disable_https()
        if act in ("on", "off"):
            return remote.set_on(act == "on")
        if act == "logout":
            return remote.logout()
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        raise logic.InventoryError(str(e))
    raise logic.InventoryError("Unknown action")


@app.get("/api/whatsnew")
def whatsnew(since: str = ""):
    """Release notes between the version a device saw last and the running one."""
    from . import __version__
    return {"version": __version__, "notes": updater.local_notes(since)}


@app.get("/api/system")
def system_info():
    """Raspberry Pi: system version, automatic security updates and live values (Options › Raspberry Pi)."""
    if host.KIND != "pi":
        return {"pi": False}
    return {"pi": True, "started": _started, **host.os_info(), "stats": host.system_stats()}


@app.get("/api/update")
def update_status():
    return updater.status()


@app.post("/api/update")
def update_action(payload: dict = Body(...)):
    """Updates: {"action": "check"} | {"action": "install"} | {"action": "rollback", "version": "v1.10.1"}."""
    act = payload.get("action")
    restart = host.restart if host.can_restart() else None
    try:
        if act == "check":
            updater.check(force=True)
            return updater.status()
        if act == "install":
            return updater.start("latest", restart)
        if act == "rollback":
            return updater.start(str(payload.get("version") or ""), restart)
    except (ValueError, OSError) as e:
        raise logic.InventoryError(str(e))
    raise logic.InventoryError("Unknown action")


# ------------------------------------------------------------------ brands, prices, weighing, statistics

@app.get("/api/brands")
def brands_list():
    with db.session() as conn:
        return {"lines": brands.custom_lines(conn), "materials": brands.MATERIALS}


@app.post("/api/brands/line")
def brands_line(payload: dict = Body(...)):
    with db.session() as conn:
        ln = brands.save_line(conn, payload)
    broadcast({"type": "changed"})
    return ln


@app.delete("/api/brands/line/{line_id}")
def brands_line_delete(line_id: int):
    with db.session() as conn:
        brands.delete_line(conn, line_id)
    broadcast({"type": "changed"})
    return {"ok": True}


@app.post("/api/brands/color")
def brands_color(payload: dict = Body(...)):
    with db.session() as conn:
        p = brands.save_color(conn, payload)
    broadcast({"type": "changed"})
    return p


@app.delete("/api/brands/color/{product_id}")
def brands_color_delete(product_id: int):
    with db.session() as conn:
        brands.delete_color(conn, product_id)
    broadcast({"type": "changed"})
    return {"ok": True}


@app.get("/api/prices")
def prices_get():
    with db.session() as conn:
        return brands.price_list(conn)


@app.put("/api/prices")
def prices_put(payload: dict = Body(...)):
    with db.session() as conn:
        brands.set_prices(conn, payload.get("items") or [])
        return brands.price_list(conn)


@app.get("/api/prices/last/{product_id}")
def price_last(product_id: int, standard: bool = False):
    """Last price paid for the line, or with standard=1 the line's standard price."""
    with db.session() as conn:
        return {"price": (brands.line_price if standard else brands.last_price)(conn, product_id)}


@app.get("/api/deliveries")
def deliveries_get():
    with db.session() as conn:
        return brands.deliveries(conn)


@app.put("/api/deliveries")
def deliveries_put(payload: dict = Body(...)):
    with db.session() as conn:
        if "set_refill" in payload:
            n = brands.set_delivery_refill(conn, payload.get("day"), payload.get("line_id"), bool(payload.get("refill")),
                                           bool(payload.get("set_refill")))
        else:
            rf = payload.get("refill")
            n = brands.set_delivery_price(conn, payload.get("day"), payload.get("line_id"), payload.get("price"),
                                          None if rf is None else bool(rf))
        out = brands.deliveries(conn)
    broadcast({"type": "changed"})
    return {"updated": n, "items": out}


@app.post("/api/spools/{spool_id}/price")
def spool_price(spool_id: int, payload: dict = Body(...)):
    with db.session() as conn:
        return brands.set_spool_price(conn, spool_id, payload.get("price"))


@app.post("/api/spools/{spool_id}/weigh")
def spool_weigh(spool_id: int, payload: dict = Body(...)):
    with db.session() as conn:
        res = brands.weigh(conn, spool_id, payload.get("gross_g"))
    broadcast({"type": "changed"})
    return res


@app.get("/api/stats")
def stats_get():
    with db.session() as conn:
        return stats.overview(conn)


@app.get("/api/prints")
def prints_get(month: str = ""):
    """Recorded prints of one month (YYYY-MM), e.g. to remove a wrong value from the statistics."""
    with db.session() as conn:
        return stats.prints_of(conn, month)


@app.patch("/api/prints/{print_id}")
def print_rename(print_id: int, payload: dict = Body(...)):
    """Rename one recorded print, or put it into a project (payload "project", empty = none)."""
    with db.session() as conn:
        if "name" in payload and not stats.rename_print(conn, print_id, payload.get("name")):
            raise logic.InventoryError("Print not found")
        if "project" in payload and not stats.set_project(conn, print_id, payload.get("project")):
            raise logic.InventoryError("Print not found")
    return {"ok": True}


@app.put("/api/prints/{print_id}/usage")
def print_usage(print_id: int, payload: dict = Body(...)):
    """Amounts per spool for a print whose print file could not be read: entered by hand or taken from a .gcode.3mf."""
    with db.session() as conn:
        try:
            ok = stats.set_usage(conn, print_id, payload.get("rows") or [])
        except (ValueError, KeyError, TypeError):
            raise logic.InventoryError("Invalid amounts")
        if not ok:
            raise logic.InventoryError("Print not found")
    return {"ok": True}


@app.delete("/api/prints/{print_id}")
def print_delete(print_id: int):
    """Remove one recorded print: its filament and cost no longer count in the statistics.
    The spools themselves are not changed."""
    with db.session() as conn:
        if not stats.delete_print(conn, print_id):
            raise logic.InventoryError("Print not found")
    return {"ok": True}


# ------------------------------------------------------------------ backup to a network share

@app.get("/api/offsite")
def offsite_get():
    return offsite.public()


@app.put("/api/offsite")
def offsite_put(payload: dict = Body(...)):
    try:
        return offsite.save(payload)
    except ValueError as e:
        raise logic.InventoryError(str(e))


@app.delete("/api/offsite")
def offsite_delete():
    offsite.delete()
    return offsite.public()


@app.post("/api/offsite/run")
def offsite_run():
    res = offsite.run(force=True)
    if res is None:
        raise logic.InventoryError("Not set up yet")
    return {**offsite.public(), "result": res}


@app.get("/api/logs")
def api_logs(level: str = "", q: str = "", limit: int = 500):
    """Recent log lines for the viewer in Options › System, newest first (secrets redacted)."""
    return {"lines": logs.lines(level, q, max(1, min(limit, 2000)))}


def _diag() -> dict:
    """Facts for a bug report: version, platform, printer models, reader. No names, addresses, codes or tokens."""
    import platform
    from . import __version__
    try:
        models = [p.get("model") or "?" for p in bambu.printers()]
    except Exception:       # noqa: BLE001 - a broken printer config must not break the bug report
        models = []
    st = settings.load()
    return {"version": __version__, "platform": host.KIND, "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "python": platform.python_version(), "printers": models, "reader": _reader_state.get("kind") or "",
            "reader_status": _reader_state.get("status") or "", "lang": st.get("lang") or "",
            "update_channel": st.get("update_channel"), "ha": bool(st.get("ha_on")), "mock": MOCK}


@app.get("/api/export/{what}.csv")
def api_export(what: str):
    """Spools or prints as a CSV file for Excel / Numbers (semicolon, decimal comma for German, UTF-8 with BOM)."""
    import csv
    import io
    from fastapi.responses import Response
    de = settings.lang() in ("de", "es")
    num = (lambda v: "" if v is None else (f"{v:.2f}".replace(".", ",") if de else f"{v:.2f}")) 
    out = io.StringIO()
    w = csv.writer(out, delimiter=";" if de else ",")
    with db.session() as conn:
        if what == "spools":
            w.writerow(["id", "brand", "line", "color", "bambu_no", "status", "slot", "ams", "remaining_pct", "price", "received", "opened", "refill"])
            for r in conn.execute(logic.SPOOL_SELECT + " ORDER BY l.name, p.bambu_no, s.id"):
                name = (r["name_de"] if settings.lang() == "de" else r["name_en"]) or r["color_name"]
                w.writerow([r["id"], r["brand"] or "Bambu Lab", r["line"], name, r["bambu_no"] or "", r["status"], r["slot_id"] or "",
                            r["ams_slot"] or "", "" if r["remain_pct"] is None else r["remain_pct"],
                            num(r["price"] if r["price"] is not None else r["line_price"]), r["received_at"] or "", r["opened_at"] or "",
                            1 if r["is_refill"] else 0])
        elif what == "prints":
            w.writerow(["id", "date", "name", "state", "printer", "project", "grams", "cost"])
            for r in conn.execute("SELECT * FROM prints ORDER BY ts"):
                w.writerow([r["id"], r["ts"], r["name"] or "", r["state"] or "", r["printer"] or "", r["project"] or "",
                            num(r["grams"]), num(r["cost"])])
        else:
            return JSONResponse({"error": "Not found"}, status_code=404)
    name = f"pixxelspool-{what}-{time.strftime('%Y%m%d')}.csv"
    return Response("\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/diag")
def api_diag():
    return _diag()


@app.get("/api/logs/download")
def api_logs_download():
    """The log file as plain text for support requests (secrets redacted), with the facts of _diag() on top."""
    from fastapi.responses import PlainTextResponse
    from . import __version__
    d = _diag()
    head = (f"# PixxelSpool {__version__} · {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            + "".join(f"# {k}: {', '.join(v) if isinstance(v, list) else v}\n" for k, v in d.items() if k != "version") + "\n")
    name = f"pixxelspool-log-{time.strftime('%Y%m%d-%H%M')}.txt"
    return PlainTextResponse(head + logs.export_text(), headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/sw.js")
def service_worker():
    """Service worker for push notifications; served from the root so its scope covers the whole app."""
    return FileResponse(STATIC / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


def _push_state() -> dict:
    return {"key": push.public_key(), "devices": push.devices(), "kinds": push.kinds()}


@app.get("/api/push")
def push_get():
    return _push_state()


@app.post("/api/push/subscribe")
def push_subscribe(payload: dict = Body(...)):
    try:
        res = push.subscribe(payload.get("subscription") or {}, payload.get("name") or "")
    except ValueError as e:
        raise logic.InventoryError(str(e))
    return {**_push_state(), "id": res["id"]}


@app.post("/api/push/unsubscribe")
def push_unsubscribe(payload: dict = Body(...)):
    push.unsubscribe(str(payload.get("id") or ""), str(payload.get("endpoint") or ""))
    return _push_state()


@app.post("/api/push/test")
def push_test(payload: dict = Body(default={})):
    res = push.send("✅ " + push._tr("Push works"), push._tr("This is how PixxelSpool messages look."), "/", "test", "normal",
                    str(payload.get("id") or ""))
    if not res["sent"]:
        raise logic.InventoryError("The message could not be delivered")
    return {**_push_state(), "result": res}


@app.put("/api/push/kinds")
def push_kinds(payload: dict = Body(...)):
    push.set_kinds(payload.get("kinds") or [])
    return _push_state()


@app.get("/api/notices")
def get_notices(limit: int = 60):
    return notices.listing(max(1, min(limit, 200)))


@app.post("/api/notices/read")
def read_notices(payload: dict = Body(default={})):
    notices.mark_read(payload.get("ids"))
    return notices.unread()


@app.delete("/api/notices")
def clear_notices():
    notices.clear()
    return notices.unread()


@app.delete("/api/notices/{notice_id}")
def delete_notice(notice_id: int):
    notices.hide(notice_id)
    return notices.unread()


ACTIVE_JOB = {"prepare", "running", "pause", "slicing", "init"}


def _direct(pid: str) -> bool:
    """Is this printer connected directly and are AMS data available? A printer without an AMS counts once its
    full report has arrived (only the external holder), so its prints are checked and recorded as well."""
    t = _printers.get(pid)
    trays = (t.state.get("trays") or []) if t else []
    return bool(t and t.state.get("status") == "connected" and trays
                and (t.state.get("ams_known") or any(x["name"].startswith("AMS") for x in trays)))


def _bambu_changed(pid: str, res: dict) -> None:
    if res.get("trays") and _direct(pid):
        from .homeassistant import apply as apply_trays
        try:
            with db.session() as conn:
                r = apply_trays(conn, _printers[pid].state["trays"], pid, _pname(pid))
            if r["removed"]:
                t = threading.Timer(REMOVED_PUSH_DELAY, _push_removed, args=(r["removed"],))
                t.daemon = True
                t.start()
            _push_new_spools(pid)
        except Exception as e:
            logging.getLogger("bambu").warning("Stock sync (%s): %s", pid, e)
    broadcast({"type": "changed"})


REMOVED_PUSH_DELAY = 30   # seconds: a spool only moved to another AMS slot is back (and its tag read) before that


_new_seen: set = set()   # Bambu tags already announced as "new spool in the AMS" since the start


def _push_new_spools(pid: str) -> None:
    """Push "new spool in the AMS" once per unknown Bambu tag (the app shows its own dialog)."""
    for t in _ams_view(pid):
        uuid = t.get("tray_uuid")
        if not uuid or t.get("spool") or uuid in _new_seen:
            continue
        _new_seen.add(uuid)
        m = t.get("match")
        name = f"{m['line']} {m['color']}".strip() if m else t.get("label") or t.get("type") or ""
        push.notify("newspool", "New spool in the AMS: {0} in {1}. Add it to storage?", [name, t["name"]],
                    key=f"newspool:{uuid}")


def _push_removed(ids: list) -> None:
    """Push "taken out of the AMS" with the storage slot the spool belongs to (push kind "removed", off by default)."""
    if "removed" not in push.kinds():
        return
    de = settings.lang() == "de"
    with db.session() as conn:
        for sid in ids:
            r = conn.execute(logic.SPOOL_SELECT + " WHERE s.id = ?", (sid,)).fetchone()
            if not r or r["ams_slot"] or not r["needs_return"]:
                continue   # back in the AMS (moved to another slot) or already put back
            color = (r["name_de"] if de else r["name_en"]) or r["color_name"] or ""
            name = " ".join(x for x in (r["line"], color) if x)
            if r["slot_id"]:
                push.notify("removed", "Taken out of the AMS: {0} goes back to slot {1}", [name, r["slot_id"]],
                            link="slot:" + r["slot_id"], key=f"removed:{sid}")
            else:
                push.notify("removed", "Taken out of the AMS: {0} has no storage slot yet", [name], key=f"removed:{sid}")


def _current_job(pid: str) -> Optional[dict]:
    """Print job from the printer: state, progress and grams per slot (from the print file)."""
    if not _direct(pid):
        return None
    st = _printers[pid].state
    j = st.get("job") or {}
    weights = st.get("weights") or {}
    if not weights or st.get("weights_task") != j.get("task"):
        return None
    return {"weights": weights, "status": j.get("state"), "progress": j.get("progress"),
            "name": j.get("name"), "remaining_min": j.get("remaining_min"), "layer": j.get("layer"), "layers": j.get("layers")}


def _job_view(pid: str) -> Optional[dict]:
    """Check this printer's job against the filament left in its AMS and suggest a replacement spool when short."""
    job = _current_job(pid)
    if not job or not job.get("weights"):
        return None
    active = job.get("status") in ACTIVE_JOB
    prog = (job.get("progress") or 0) if active else 0
    by_name = {t["name"]: t for t in _ams_view(pid)}
    tight = 1 + settings.load().get("tight_pct", 15) / 100
    rows = []
    with db.session() as conn:
        for slot, grams in job["weights"].items():
            t = by_name.get(slot) or {}
            need = round(grams * (1 - min(max(prog, 0), 100) / 100), 1)
            remain = t.get("remain") if isinstance(t.get("remain"), (int, float)) and t.get("remain") >= 0 else None
            try:
                full = float(t.get("tray_weight") or 0) or 1000.0
            except (TypeError, ValueError):
                full = 1000.0
            bound = t.get("spool") if (t.get("spool") or {}).get("ams_bound") else None
            if remain is None and bound:   # assigned by hand: the AMS can't measure it, PixxelSpool counts along
                remain = bound["remain_pct"] if bound["remain_pct"] is not None else 100
                full = float(bound["weight_g"] or bound["net_g"] or 1000)
            have = round(full * remain / 100) if remain is not None else None
            state = "unknown" if have is None else "ok" if have >= need * tight + 5 else "tight" if have >= need else "short"
            sp = t.get("spool")
            spare = None
            if sp and state in ("tight", "short"):
                r = conn.execute(logic.SPOOL_SELECT + " WHERE s.product_id = ? AND s.id != ? AND s.status = 'stored' "
                                 "ORDER BY s.in_cabinet DESC, s.id LIMIT 1", (sp["product_id"], sp["id"])).fetchone()
                spare = dict(r) if r else None
            rows.append({"slot": slot, "need_g": need, "have_g": have, "state": state, "spool": sp,
                         "label": t.get("label"), "spare": spare})
    return {"printer": pid, "printer_name": _pname(pid), "status": job.get("status"), "progress": job.get("progress"),
            "active": active, "rows": rows, "name": job.get("name"), "remaining_min": job.get("remaining_min"),
            "layer": job.get("layer"), "layers": job.get("layers")}


def _ams_match(conn, tray: dict) -> Optional[dict]:
    prods = logic.ams_products(conn, tray)
    if not prods:
        return None
    p = conn.execute("SELECT p.id, p.color_name, p.name_en, p.name_de, p.bambu_no, l.name AS line FROM products p "
                     "JOIN lines l ON l.id = p.line_id WHERE p.id = ?", (prods[0],)).fetchone()
    seed = conn.execute("SELECT slot_id FROM spools WHERE product_id = ? AND tray_uid IS NULL AND status != 'empty' "
                        "AND ams_slot IS NULL ORDER BY in_cabinet DESC, (opened_at IS NOT NULL) DESC, is_refill, id LIMIT 1",
                        (p["id"],)).fetchone()
    de = settings.lang() == "de"
    return {"product_id": p["id"], "line": p["line"], "bambu_no": p["bambu_no"],
            "color": (p["name_de"] if de else p["name_en"]) or p["color_name"] or "",
            "color_name": p["color_name"], "name_en": p["name_en"], "name_de": p["name_de"],
            "seed_slot": seed["slot_id"] if seed else None, "has_seed": seed is not None}


def _ams_view(only: str = "") -> list:
    """AMS slots of all connected printers (or only one), each with the spool from the stock if known."""
    out = []
    with db.session() as conn:
        for pid, t in list(_printers.items()):
            if (only and pid != only) or not _direct(pid):
                continue
            name = _pname(pid)
            for tr in t.state.get("trays") or []:
                sp = None
                extra = {}
                if tr.get("tray_uuid"):
                    r = conn.execute(logic.SPOOL_SELECT + " WHERE s.tray_uid = ?", (tr["tray_uuid"],)).fetchone()
                    sp = dict(r) if r else None
                    if sp is None:   # unknown Bambu spool: which color it is and whether an unscanned spool waits for it
                        extra = {"match": _ams_match(conn, tr)}
                elif logic._no_tag_tray(tr):   # no Bambu tag: a spool assigned by hand?
                    r = conn.execute(logic.SPOOL_SELECT + " WHERE s.ams_bound = 1 AND s.ams_slot = ? AND s.printer_id = ? "
                                     "AND s.status != 'empty'", (tr["name"], pid)).fetchone()
                    sp = dict(r) if r else None
                    extra = {"assignable": sp is None}
                out.append({**tr, "spool": sp, "printer": pid, "printer_name": name, **extra})
    return out


@app.get("/api/search")
def search(q: str = ""):
    with db.session() as conn:
        return logic.search(conn, q) if q.strip() else {"spools": [], "missing": []}


@app.get("/api/ha")
def ha_status():
    return _ha.state if _ha else {"status": "off", "trays": []}


@app.get("/api/reorg")
def reorg(mode: str = "zones"):
    with db.session() as conn:
        return logic.sort_plan(conn) if mode == "sort" else logic.reorg_plan(conn)


@app.get("/api/catalog")
def catalog():
    with db.session() as conn:
        return logic.catalog(conn)


@app.get("/api/lines")
def lines():
    with db.session() as conn:
        return logic.lines_summary(conn)


@app.get("/api/events/recent")
def recent():
    with db.session() as conn:
        return logic.recent_events(conn)


@app.get("/api/products")
def products():
    with db.session() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT p.*, l.name AS line, l.brand, l.shop_url, l.net_g, l.price AS line_price FROM products p JOIN lines l ON l.id = p.line_id "
            "ORDER BY l.name, p.bambu_no")]


@app.get("/api/usedup")
def used_up():
    """Spools marked as empty, newest first (Options › Used-up spools)."""
    with db.session() as conn:
        return logic.used_up(conn)


@app.get("/api/spools/{spool_id}")
def spool(spool_id: int):
    with db.session() as conn:
        return logic.get_spool(conn, spool_id)


@app.post("/api/map")
def map_variant(payload: dict = Body(...)):
    """Map a variant id to a product (or create a new product) and handle the scan again."""
    tag = payload["tag"]
    with db.session() as conn:
        product_id = payload.get("product_id")
        if not product_id:
            np = payload["new_product"]
            product_id = logic.create_product(conn, np["line"], np["color_name"],
                                              np.get("bambu_no"), "#" + tag["color_rgba"][:6])
        logic.map_variant(conn, tag["variant_id"], int(product_id))
        result = logic.handle_scan(conn, tag)
    broadcast({"type": "scan", "result": result})
    return result


@app.post("/api/spools")
def store(payload: dict = Body(...)):
    with db.session() as conn:
        s = logic.store_new(conn, payload["tag"], int(payload["product_id"]),
                            payload["slot_id"], bool(payload.get("is_refill")), brands._price(payload.get("price")),
                            bool(payload.get("manual")))
    broadcast({"type": "changed"})
    return s


def _action(fn, spool_id: int, *args):
    with db.session() as conn:
        res = fn(conn, spool_id, *args)
    broadcast({"type": "changed"})
    return res


@app.post("/api/spools/{spool_id}/take")
def take(spool_id: int):
    return _action(logic.take, spool_id)


@app.post("/api/spools/{spool_id}/return")
def put_back(spool_id: int):
    return _action(logic.put_back, spool_id)


@app.post("/api/spools/{spool_id}/empty")
def empty(spool_id: int):
    return _action(logic.mark_empty, spool_id)


@app.delete("/api/spools/{spool_id}")
def delete_spool(spool_id: int):
    """Remove a single spool for good (added by mistake, given away ...). Unlike "empty",
    the counter of empty spools stays as it is. The database is backed up first."""
    with db.session() as conn:
        logic.get_spool(conn, spool_id)          # 404-style error if it does not exist
    db.backup("before-delete")
    with db.session() as conn:
        logic.delete_spool(conn, spool_id)
    broadcast({"type": "changed"})
    return {"ok": True}


@app.post("/api/spools/{spool_id}/move")
def move(spool_id: int, payload: dict = Body(...)):
    return _action(logic.move, spool_id, payload["slot_id"], bool(payload.get("manual")))


@app.post("/api/spools/{spool_id}/refill-on-spool")
def refill_on_spool(spool_id: int, payload: dict = Body(...)):
    return _action(logic.refill_on_spool, spool_id, bool(payload.get("used_empty_spool")))


@app.patch("/api/spools/{spool_id}")
def patch(spool_id: int, payload: dict = Body(...)):
    return _action(logic.update_spool, spool_id, payload)


def _batch_state() -> dict:
    return {"active": _batch["active"], "items": _batch["items"]}


@app.get("/api/batch")
def batch_get():
    return _batch_state()


@app.post("/api/batch/start")
def batch_start():
    _batch.update(active=True, tags=[], items=[])
    broadcast({"type": "batch", **_batch_state()})
    return _batch_state()


@app.post("/api/batch/cancel")
def batch_cancel():
    _batch.update(active=False, tags=[], items=[])
    broadcast({"type": "batch", **_batch_state()})
    return _batch_state()


@app.post("/api/batch/finish")
def batch_finish(payload: dict = Body(default={})):
    db.backup("before-audit")
    with db.session() as conn:
        result = logic.batch_commit(conn, _batch["tags"], bool((payload or {}).get("reserve")))
    _batch.update(active=False, tags=[], items=[])
    broadcast({"type": "changed"})
    broadcast({"type": "batch", **_batch_state()})
    return result


@app.post("/api/ha/sync")
def ha_sync():
    """Poll Home Assistant now instead of waiting for the next interval."""
    if _ha is None:
        raise logic.InventoryError("Home Assistant is not active")
    before = _ha.state.get("polled")
    _ha.reload()
    end = time.time() + 15
    while time.time() < end and _ha.state.get("polled") == before:
        time.sleep(0.2)
    return {k: v for k, v in _ha.state.items() if k != "sensors"}


@app.get("/api/ha/sensors")
def ha_sensors():
    """Temperature and humidity sensors from Home Assistant for assigning them to cabinets."""
    return (_ha.state.get("sensors") if _ha else None) or []


@app.get("/api/climate")
def climate(days: int = 7):
    from . import homeassistant
    with db.session() as conn:
        series = homeassistant.history(conn, days)
        last = dict(conn.execute("SELECT cabinet, MAX(ts) FROM climate GROUP BY cabinet").fetchall())
    now = (_ha.state.get("climate") if _ha else None) or {}
    st = settings.load()
    out = []
    for c in st["cabinets"]:
        cfg = (st.get("climate") or {}).get(c["key"]) or {}
        if not (cfg.get("temp") or cfg.get("hum")) and c["key"] not in series:
            continue
        out.append({"key": c["key"], "name": c["name"], "max_hum": cfg.get("max_hum", 50),
                    "ok_hum": cfg.get("ok_hum", cfg.get("max_hum", 50) - 10),
                    "now": now.get(c["key"]), "series": series.get(c["key"], []), "last": last.get(c["key"])})
    return {"days": days, "cabinets": out}


@app.get("/api/ha/config")
def ha_config_get():
    from . import homeassistant
    return homeassistant.public_config()


@app.put("/api/ha/config")
async def ha_config_put(payload: dict = Body(...)):
    from . import homeassistant
    try:
        res = await asyncio.to_thread(homeassistant.save_config, payload.get("url"), payload.get("token"))
    except ValueError as e:
        raise logic.InventoryError(str(e))
    broadcast({"type": "changed"})
    return res


@app.delete("/api/ha/config")
def ha_config_delete():
    """Home Assistant switched off with "Delete data": address, token and sensor assignments go, the switch stays off."""
    from . import homeassistant
    homeassistant.delete_config()
    settings.save({"ha_on": False, "climate": {}})
    if _ha:
        _ha.reload()
    broadcast({"type": "changed"})
    return homeassistant.public_config()


@app.post("/api/3mf")
async def threemf_analyze(request: Request):
    from . import threemf
    blob = await request.body()
    if not blob:
        raise logic.InventoryError("No file received")
    if len(blob) > 150 * 1024 * 1024:
        raise logic.InventoryError("The file is too large (max. 150 MB)")
    try:
        return await asyncio.to_thread(threemf.analyze, blob)
    except threemf.ThreeMFError as e:
        raise logic.InventoryError(str(e))
    except Exception as e:  # broken or unusual file
        raise logic.InventoryError(f"Could not read the file ({type(e).__name__})")


# --- 3MF analysis as a background job with progress (large models take a while, above all on a Pi)
_tmf_jobs: dict = {}
_tmf_lock = threading.Lock()


def _tmf_run(job: dict, blob: bytes) -> None:
    from . import threemf

    def prog(frac: float) -> None:
        if job["cancel"]:
            raise threemf.Cancelled("Cancelled")
        job["progress"] = round(frac, 3)
    try:
        job["result"] = threemf.analyze(blob, prog)
    except threemf.Cancelled:
        job["error"] = "Cancelled"
    except threemf.ThreeMFError as e:
        job["error"] = str(e)
    except MemoryError:
        job["error"] = "Not enough free memory on this device for such a large model. Slice it in Bambu Studio and load the .gcode.3mf instead: it is much smaller."
    except Exception as e:  # broken or unusual file
        logging.getLogger("3mf").warning("3MF analysis failed: %r", e)
        job["error"] = f"Could not read the file ({type(e).__name__})"
    finally:
        job["progress"], job["done"], job["ended"] = 1.0, True, time.time()


@app.post("/api/3mf/jobs")
async def threemf_job_start(request: Request):
    blob = await request.body()
    if not blob:
        raise logic.InventoryError("No file received")
    if len(blob) > 150 * 1024 * 1024:
        raise logic.InventoryError("The file is too large (max. 150 MB)")
    with _tmf_lock:
        for jid, j in list(_tmf_jobs.items()):
            if not j["done"]:
                j["cancel"] = True        # one analysis at a time: a new file replaces the running one
            elif time.time() - j["ended"] > 600:
                _tmf_jobs.pop(jid, None)
        jid = secrets.token_hex(8)
        job = _tmf_jobs[jid] = {"progress": 0.0, "done": False, "cancel": False, "result": None, "error": None, "ended": 0}
    threading.Thread(target=_tmf_run, args=(job, blob), daemon=True, name="3mf").start()
    return {"id": jid}


@app.get("/api/3mf/jobs/{jid}")
def threemf_job_get(jid: str):
    job = _tmf_jobs.get(jid)
    if not job:
        raise logic.InventoryError("Unknown job")
    out = {"progress": job["progress"], "done": job["done"]}
    if job["done"]:
        out["error"], out["result"] = job["error"], job["result"]
        _tmf_jobs.pop(jid, None)
    return out


@app.delete("/api/3mf/jobs/{jid}")
def threemf_job_cancel(jid: str):
    job = _tmf_jobs.pop(jid, None)
    if job:
        job["cancel"] = True
    return {"ok": True}


@app.get("/api/audit")
def audit_get():
    return _audit_state()


@app.post("/api/audit/start")
def audit_start():
    with db.session() as conn:
        rows = conn.execute("SELECT DISTINCT s.slot_id FROM spools s JOIN slots sl ON sl.id = s.slot_id "
                            "WHERE s.status != 'empty' ORDER BY sl.kind, sl.cabinet, sl.row, sl.pos").fetchall()
    _batch.update(active=False, tags=[], items=[])
    broadcast({"type": "batch", **_batch_state()})     # the blue bulk inventory bar must go away on every screen
    _audit.update(active=True, order=[r[0] for r in rows], idx=0, seen={}, unknown=0, last=None, skipped=[])
    broadcast({"type": "audit", **_audit_state()})
    return _audit_state()


@app.post("/api/audit/goto")
def audit_goto(payload: dict = Body(...)):
    """Go to a slot. skip=true: the current slot stays unchecked (not counted as missing in the result)."""
    cur = _audit["order"][_audit["idx"]] if _audit["order"] else None
    if payload.get("skip") and cur and cur not in _audit["skipped"]:
        _audit["skipped"].append(cur)
    elif not payload.get("skip") and cur in _audit["skipped"] and int(payload.get("idx", 0)) > _audit["idx"]:
        _audit["skipped"].remove(cur)
    _audit["idx"] = max(0, min(int(payload.get("idx", 0)), max(len(_audit["order"]) - 1, 0)))
    _audit["last"] = None
    broadcast({"type": "audit", **_audit_state()})
    return _audit_state()


@app.post("/api/audit/confirm")
def audit_confirm(payload: dict = Body(...)):
    sid = str(int(payload["spool_id"]))
    if payload.get("undo"):
        _audit["seen"].pop(sid, None)
    elif payload.get("missing"):      # "Missing": the spool is not on its slot
        _audit["seen"][sid] = {"kind": "missing", "found_at": None, "manual": True}
    else:
        _audit["seen"][sid] = {"kind": "ok", "found_at": payload.get("found_at"), "manual": True}
    broadcast({"type": "audit", **_audit_state()})
    return _audit_state()


@app.post("/api/audit/stop")
def audit_stop():
    _audit.update(active=False, order=[], idx=0, seen={}, unknown=0, last=None, skipped=[])
    broadcast({"type": "audit", **_audit_state()})
    return _audit_state()


@app.post("/api/reset")
def reset(payload: dict = Body(...)):
    if payload.get("confirm") != logic.RESET_WORD:
        raise logic.InventoryError(f"Please type {logic.RESET_WORD} to confirm")
    backup = db.backup("before-reset")
    with db.session() as conn:
        n = logic.reset_storage(conn)
    broadcast({"type": "changed"})
    return {"removed": n, "backup": backup.name}


@app.post("/api/factory-reset")
def factory_reset(payload: dict = Body(...)):
    """Reset PixxelSpool to a new installation: the data files are deleted on the next start (db._factory_reset).
    No backup is made; the interface recommends downloading one first."""
    if payload.get("confirm") != logic.RESET_WORD:
        raise logic.InventoryError(f"Please type {logic.RESET_WORD} to confirm")
    db.RESET_MARKER.write_text("reset requested\n", encoding="utf-8")
    if host.can_restart():
        threading.Timer(1.0, host.restart).start()
        return {"restart": True}
    return {"restart": False}


@app.post("/api/simulate")
def simulate(tag: dict = Body(...)):
    """Trigger a scan without a reader (test server only)."""
    if not MOCK:
        return JSONResponse({"error": "Not found"}, status_code=404)
    on_tag(tag)
    return _last_scan


@app.post("/api/system")
def system_action(payload: dict = Body(...)):
    """Shut down or reboot the Pi, or only restart PixxelSpool (Linux only)."""
    import subprocess
    action = payload.get("action")
    if action not in ("poweroff", "reboot", "restart"):
        raise logic.InventoryError("Unknown action")
    if action == "restart":
        # systemd (Pi) or the Windows app start PixxelSpool again
        if not host.can_restart():
            raise logic.InventoryError("Restart only works when PixxelSpool runs as a service")
        threading.Timer(1.0, host.restart).start()
        return {"ok": True}
    if host.KIND != "pi":
        raise logic.InventoryError("Only works on the Raspberry Pi")
    try:
        from . import daily_backup
        daily_backup.run()
    except Exception:
        pass
    subprocess.Popen(["systemctl", action])
    return {"ok": True}


@app.post("/api/usage")
def count_usage(payload: dict = Body(...)):
    """The browser reports each minute it is open and visible; after two hours it gets the donation note once."""
    return settings.count_use(payload.get("minutes", 1), payload.get("ready", False))


@app.get("/api/settings")
def get_settings():
    return settings.load()


@app.put("/api/settings")
def put_settings(payload: dict = Body(...)):
    old = settings.load()
    cur = settings.save(payload)
    if cur.get("log_detail") != old.get("log_detail"):
        logs.set_detail(bool(cur.get("log_detail")))
        logging.getLogger("logs").info("Detailed log %s", "on" if cur.get("log_detail") else "off")
    if _ha and any(cur.get(k) != old.get(k) for k in ("ha_on", "climate", "ha_poll_seconds")):
        _ha.reload()
    if _reader and any(cur.get(k) != old.get(k) for k in ("reader", "pn532_bus", "pn532_addr", "pn532_port")):
        _reader_state.update(status="starting", detail="Switching reader …")
        broadcast({"type": "reader", **_reader_state})
        _reader.reload()
    broadcast({"type": "changed"})
    return cur


@app.get("/api/backup/download")
def backup_download(ha: int = 0):
    """Backup as ZIP: database and settings (Home Assistant credentials only on request)."""
    from datetime import datetime
    from starlette.background import BackgroundTask
    tmpzip = _backup_zip(ha)
    return FileResponse(tmpzip, media_type="application/zip", filename=_backup_name(datetime.now(), ".zip"),
                        background=BackgroundTask(os.unlink, tmpzip))


@app.post("/api/backup/download")
def backup_download_locked(payload: dict = Body(...)):
    """Same backup, encrypted with a password of the user's choice (file ending .pspbackup)."""
    from datetime import datetime
    from fastapi.responses import Response
    tmpzip = _backup_zip(int(bool(payload.get("ha"))))
    try:
        blob = auth.encrypt_file(Path(tmpzip).read_bytes(), str(payload.get("password") or ""))
    except ValueError as e:
        raise logic.InventoryError(str(e))
    finally:
        os.unlink(tmpzip)
    return Response(blob, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{_backup_name(datetime.now(), ".pspbackup")}"'})


def _backup_name(now, ext: str) -> str:
    word = {"de": "Sicherung", "es": "copia"}.get(settings.lang(), "backup")   # file name says what and when
    return f"PixxelSpool-{word}-{now:%Y-%m-%d_%H-%M}{ext}"


def _backup_zip(ha: int) -> str:
    """Write the backup ZIP to a temporary file and return its path."""
    import sqlite3, tempfile, zipfile
    from datetime import datetime
    fd, tmpdb = tempfile.mkstemp(suffix=".db"); os.close(fd)
    src, dst = db.connect(), sqlite3.connect(tmpdb)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    fd, tmpzip = tempfile.mkstemp(suffix=".zip"); os.close(fd)
    with zipfile.ZipFile(tmpzip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmpdb, "inventory.db")
        if settings.PATH.exists():
            z.write(settings.PATH, "settings.json")
        ha_file = db.DATA_DIR / "homeassistant.json"
        if ha and ha_file.exists():
            z.write(ha_file, "homeassistant.json")
        if ha and bambu.CONFIG.exists():
            z.write(bambu.CONFIG, "bambu.json")
        z.writestr("pixxelspool.json", json.dumps({"app": "PixxelSpool", "created": datetime.now().isoformat(timespec="seconds"),
                                                  "with_ha": bool(ha and ha_file.exists())}))
    os.unlink(tmpdb)
    return tmpzip


@app.post("/api/backup/restore")
async def backup_restore(request: Request):
    """Restore a backup (ZIP from above, its password-protected form or a single .db). The current state is backed up first."""
    import io, zipfile
    from urllib.parse import unquote
    blob = await request.body()
    if not blob or len(blob) > 200 * 1024 * 1024:
        raise logic.InventoryError("No file or file too large")
    files = {}
    if blob[:8] == auth.MAGIC:                     # password-protected backup
        pw = request.headers.get("x-backup-password", "")
        if not pw:
            return JSONResponse({"error": "This backup is protected with a password.", "need_password": True}, status_code=409)
        try:
            blob = auth.decrypt_file(blob, unquote(pw))
        except ValueError as e:
            raise logic.InventoryError(str(e))
    if blob[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for name in ("inventory.db", "settings.json", "homeassistant.json", "bambu.json"):
                    if name in z.namelist():
                        files[name] = z.read(name)
        except zipfile.BadZipFile:
            raise logic.InventoryError("The ZIP file is damaged")
    elif blob[:16] == b"SQLite format 3\x00":
        files["inventory.db"] = blob
    return _restore(files)


@app.get("/api/backups")
def backups_list():
    """Automatic backups on this device (nightly, before updates and before risky actions), newest first."""
    return db.list_backups()


@app.post("/api/backups/restore")
def backups_restore(payload: dict = Body(...)):
    """Restore one of the automatic backups listed above (by its name from the list, nothing else)."""
    name = str(payload.get("name") or "")
    if name not in {b["name"] for b in db.list_backups()}:
        raise logic.InventoryError("Backup not found")
    path = db.DATA_DIR / name
    files = {"inventory.db": path.read_bytes()}
    companion = path.with_name(path.stem + "-settings.json")   # settings saved next to a "before-restore" copy
    if companion.exists():
        files["settings.json"] = companion.read_bytes()
    return _restore(files)


def _restore(files: dict) -> dict:
    """Replace database (and settings/credentials if given) with the files of a backup. The current state is backed up first."""
    import sqlite3, tempfile
    if "inventory.db" not in files:
        raise logic.InventoryError("This is not a PixxelSpool backup (inventory.db missing)")
    fd, tmp = tempfile.mkstemp(suffix=".db"); os.close(fd)
    Path(tmp).write_bytes(files["inventory.db"])
    try:
        chk = sqlite3.connect(tmp)
        tables = {r[0] for r in chk.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        ok = chk.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        chk.close()
        if not {"spools", "slots", "products"} <= tables or not ok:
            raise logic.InventoryError("The database in the backup is incomplete or damaged")
        for name in ("settings.json", "homeassistant.json", "bambu.json"):
            if name in files:
                json.loads(files[name])
        pre = db.backup("before-restore")
        if settings.PATH.exists():
            pre.with_name(f"{pre.stem}-settings.json").write_bytes(settings.PATH.read_bytes())
        srcc, dstc = sqlite3.connect(tmp), db.connect()
        try:
            srcc.backup(dstc)
        finally:
            srcc.close(); dstc.close()
        if "settings.json" in files:
            settings.PATH.write_bytes(files["settings.json"])
        if "homeassistant.json" in files:
            ha_file = db.DATA_DIR / "homeassistant.json"
            ha_file.write_bytes(files["homeassistant.json"]); ha_file.chmod(0o600)
        if "bambu.json" in files:
            bambu.CONFIG.write_bytes(files["bambu.json"]); bambu.CONFIG.chmod(0o600)
            for t in _printers.values():
                t.reload()
            _sync_printers()
        db.init()
    except ValueError:
        raise logic.InventoryError("The settings in the backup are damaged")
    finally:
        os.unlink(tmp)
    broadcast({"type": "changed"})
    return {"ok": True, "restored": sorted(files), "previous": pre.name}


@app.get("/api/setup")
def setup_info():
    """For the setup wizard: what is connected and what is configured."""
    usb = []
    try:
        from smartcard.System import readers
        from .reader import usable_readers
        usb = usable_readers([str(r) for r in readers()])
    except Exception:
        pass
    cfg = settings.load()
    from .homeassistant import public_config
    return {
        "setup_done": cfg["setup_done"], "reader": cfg["reader"], "state": _reader_state,
        "usb_readers": usb, "i2c": os.path.exists(f"/dev/i2c-{cfg['pn532_bus']}"),
        "ha": public_config(),
    }


@app.post("/api/reader/test")
def reader_test(payload: dict = Body(...)):
    import time as _t
    _reader_test["until"] = _t.time() + 120 if payload.get("on") else 0.0
    return {"on": bool(payload.get("on"))}


@app.post("/api/setup/done")
def setup_done():
    cur = settings.save({"setup_done": True})
    broadcast({"type": "changed"})
    return cur


@app.get("/api/bambu/config")
def bambu_config_get():
    """Configured printers (without access codes) with their connection state."""
    cfg = bambu.public_config()
    for p in cfg["printers"]:
        st = _printers[p["id"]].state if p["id"] in _printers else {}
        p["state"] = {k: v for k, v in st.items() if k in ("status", "detail")}
    return cfg


@app.put("/api/bambu/config")
def bambu_config_put(payload: dict = Body(...)):
    """Add a printer (no "id") or change one: {"id"?, "name", "ip", "serial", "code"}. The connection is tested first."""
    try:
        res = bambu.save_printer(payload.get("id") or None, payload.get("name") or "", payload.get("ip"),
                                 payload.get("serial"), payload.get("code"), test=not MOCK)
    except ValueError as e:
        raise logic.InventoryError(str(e))
    _cameras.pop(res["id"], None)
    _sync_printers(reload=res["id"])
    broadcast({"type": "changed"})
    return {"ok": True, **res, **bambu.public_config()}


@app.post("/api/bambu/printers/{pid}/on")
def bambu_printer_on(pid: str, payload: dict = Body(...)):
    """Switch the connection to one printer on or off; credentials are kept."""
    bambu.set_on(pid, bool(payload.get("on")))
    _sync_printers(reload=pid)
    broadcast({"type": "changed"})
    return bambu.public_config()


@app.delete("/api/bambu/config")
def bambu_config_delete(printer: str = ""):
    """Remove a printer (default: the only one). Spools in its AMS are marked 'to be put back'."""
    pid = printer or next(iter(_printers), "")
    bambu.delete_printer(pid)
    with db.session() as conn:
        conn.execute("UPDATE spools SET ams_slot = NULL, printer_id = NULL, needs_return = 1 "
                     "WHERE printer_id = ? AND ams_slot IS NOT NULL", (pid,))
    _sync_printers()
    broadcast({"type": "changed"})
    return {"ok": True, **bambu.public_config()}


# ------------------------------------------------------------ camera (opt-in, Options › Printer)
_cameras: dict = {}       # printer id -> camera.Camera, created on first use


def _pid(printer: str) -> str:
    """Printer id from a request parameter; empty means the first printer."""
    return printer if printer in _printers else next(iter(_printers), "")


def _cam(pid: str) -> camera.Camera:
    if pid not in _cameras:
        _cameras[pid] = camera.Camera(lambda: (lambda c: c if c and c.get("on", True) else None)(bambu.get(pid)),
                                      lambda: settings.load().get("camera", "off"))
    return _cameras[pid]


@app.get("/api/camera")
def camera_info(printer: str = ""):
    return {**_cam(_pid(printer)).info(), "mode": settings.load().get("camera", "off")}


@app.get("/api/camera/snapshot")
def camera_snapshot(printer: str = ""):
    from fastapi.responses import Response
    cam = _cam(_pid(printer))
    seq, jpg = cam.seq, cam.frame
    end = time.time() + 12
    while not jpg and time.time() < end:
        seq, jpg = cam.wait(seq, timeout=2)
    if not jpg:
        return JSONResponse({"error": cam.detail or "No camera image"}, status_code=503)
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/camera/stream")
def camera_stream(printer: str = "", hd: int = 0):
    """MJPEG stream for an <img>. Ends after 10 minutes; the page reconnects. hd=1: full resolution (large window)."""
    pid = _pid(printer)
    cfg = bambu.get(pid)
    if settings.load().get("camera", "off") == "off" or not cfg or not cfg.get("on", True):
        return JSONResponse({"error": "Camera is switched off"}, status_code=404)
    cam = _cam(pid)

    def gen():
        start = time.time()
        seq = -1
        while time.time() < start + 600:
            new, jpg = cam.wait(seq, timeout=5, hd=bool(hd))
            fresh = new != seq and jpg
            seq = new
            if not fresh:
                if cam.status == "off" and time.time() > start + 5:
                    return
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/api/printer/light")
def printer_light(payload: dict = Body(...)):
    """Switch a printer's chamber light: {"on": true|false, "printer": id}."""
    t = _printers.get(_pid(payload.get("printer") or ""))
    if not t:
        raise logic.InventoryError("Printer is not connected")
    try:
        t.set_light(bool(payload.get("on")))
    except ValueError as e:
        raise logic.InventoryError(str(e))
    return {"ok": True, "light": "on" if payload.get("on") else "off"}


def _printer_card(pid: str, t) -> dict:
    head = {"id": pid, "printer_name": bambu.name_of(pid), "status": t.state.get("status", "off"), "detail": t.state.get("detail", "")}
    if t.state.get("status") != "connected":
        return {**head, "connected": False}
    snap = t.snapshot()
    pv = bambu.printer_view(snap)
    pr = snap.get("print") or {}
    pv["messages"] = hms.decode(pr.get("hms"), pr.get("print_error"), t._serial, settings.lang())
    ids = {n["filament_id"] for n in pv["mounted"] + pv["rack"] if n.get("filament_id")}
    if ids:
        with db.session() as conn:
            names = {}
            for fid in ids:
                r = conn.execute("SELECT l.name FROM products p JOIN lines l ON l.id = p.line_id WHERE p.material_id = ? LIMIT 1",
                                 (fid,)).fetchone()
                if r:
                    names[fid] = r["name"]
        for n in pv["mounted"] + pv["rack"]:
            n["filament"] = names.get(n.get("filament_id"), n.get("filament_id") or "")
    pv["model"] = pv.get("model") or bambu.model_name(t._serial)
    # a finished or cancelled print stays on the printer until the next one starts; hide it after a while
    if pv.get("state") in ("finish", "failed"):
        key = (pv["state"], pv.get("name") or "")
        seen = _job_done.get(pid)
        if not seen or seen[0] != key:
            seen = _job_done[pid] = (key, time.time())
        pv["job_done_old"] = time.time() - seen[1] > JOB_DONE_HIDE_H * 3600
    else:
        _job_done.pop(pid, None)
    return {**head, "connected": True, **pv}


@app.get("/api/printer")
def printer_status():
    """Printer cards: one entry per configured printer (details only while connected)."""
    return {"printers": [_printer_card(pid, t) for pid, t in list(_printers.items())]}


@app.get("/api/bambu/raw")
def bambu_raw(printer: str = ""):
    """A printer's full state as reported (for debugging)."""
    t = _printers.get(_pid(printer))
    return t.snapshot() if t else {}


@app.get("/api/layout")
def layout_get():
    return {"cabinets": settings.load()["cabinets"]}


@app.post("/api/layout")
def layout_apply(payload: dict = Body(...)):
    try:
        cabs = settings.clean_cabinets(payload.get("cabinets"))
    except ValueError as e:
        raise logic.InventoryError(str(e))
    pre = db.backup("before-layout-change")
    with db.session() as conn:
        res = db.apply_layout(conn, cabs)
        if not res["ok"]:
            conn.rollback()
            pre.unlink(missing_ok=True)
            return res
        settings.store_cabinets(cabs)
    broadcast({"type": "changed"})
    return {**res, "backup": pre.name, "cabinets": cabs}


@app.get("/api/insights")
def get_insights():
    with db.session() as conn:
        return insights.all_insights(conn)


@app.post("/api/shoplist")
def shoplist_toggle(payload: dict = Body(...)):
    """Put a color on the shopping list by hand or take it off again."""
    try:
        pid = int(payload.get("product_id"))
    except (TypeError, ValueError):
        raise logic.InventoryError("Color not found")
    with db.session() as conn:
        try:
            q = payload.get("qty")
            insights.toggle_noted(conn, pid, bool(payload.get("on", True)), int(q) if q is not None else None)
        except ValueError as e:
            raise logic.InventoryError(str(e))
        res = insights.all_insights(conn)
    broadcast({"type": "changed"})
    return res


@app.post("/api/minstock")
def min_stock(payload: dict = Body(...)):
    """Set the minimum stock of a color: {"product_id": id, "n": spools (0 = none)}."""
    try:
        pid, n = int(payload.get("product_id")), int(payload.get("n") or 0)
    except (TypeError, ValueError):
        raise logic.InventoryError("Color not found")
    with db.session() as conn:
        try:
            insights.set_min_stock(conn, pid, max(0, n))
        except ValueError as e:
            raise logic.InventoryError(str(e))
        res = insights.all_insights(conn)
    broadcast({"type": "changed"})
    return res


@app.post("/api/spools/{spool_id}/dried")
def dried(spool_id: int):
    with db.session() as conn:
        conn.execute("UPDATE spools SET dried_at = date('now','localtime') WHERE id = ?", (spool_id,))
        logic.log(conn, spool_id, "dried", "")
        sp = logic.get_spool(conn, spool_id)
    broadcast({"type": "changed"})
    return sp


@app.get("/api/lines/all")
def all_lines():
    with db.session() as conn:
        return [r["name"] for r in conn.execute(
            "SELECT DISTINCT l.name FROM lines l JOIN products p ON p.line_id = l.id WHERE p.in_catalog = 1 ORDER BY l.name")]


@app.post("/api/ams/adopt")
def ams_adopt(payload: dict = Body(...)):
    trays = _ams_view()
    tray = next((t for t in trays if t.get("entity") == payload.get("entity")
                 and (not payload.get("printer") or t["printer"] == payload["printer"])), None)
    if tray is None:
        raise logic.InventoryError("AMS slot not found")
    pid = payload.get("product_id")
    with db.session() as conn:
        sp = logic.adopt_ams(conn, tray, int(pid) if pid else None)
    broadcast({"type": "changed"})
    return sp


@app.get("/api/ams/assign")
def ams_assign_list(entity: str, printer: str = ""):
    """Experimental: spools from storage to choose from for an AMS slot without a Bambu tag."""
    tray = next((t for t in _ams_view() if t.get("entity") == entity and (not printer or t["printer"] == printer)), None)
    if tray is None:
        raise logic.InventoryError("AMS slot not found")
    with db.session() as conn:
        return {"tray": tray, "spools": logic.assign_candidates(conn, tray)}


@app.post("/api/ams/assign")
def ams_assign(payload: dict = Body(...)):
    tray = next((t for t in _ams_view() if t.get("entity") == payload.get("entity")
                 and (not payload.get("printer") or t["printer"] == payload["printer"])), None)
    if tray is None:
        raise logic.InventoryError("AMS slot not found")
    with db.session() as conn:
        sp = logic.assign_ams(conn, tray, int(payload.get("spool_id") or 0))
    broadcast({"type": "changed"})
    return sp


@app.post("/api/spools/{spool_id}/unassign")
def ams_unassign(spool_id: int):
    with db.session() as conn:
        sp = logic.unassign_ams(conn, spool_id)
    broadcast({"type": "changed"})
    return {"spool": sp}


@app.get("/api/ams/candidates")
def ams_candidates(entity: str, printer: str = ""):
    """Colors to choose from when an AMS spool's color is not in the catalog."""
    tray = next((t for t in _ams_view() if t.get("entity") == entity and (not printer or t["printer"] == printer)), None)
    if tray is None:
        raise logic.InventoryError("AMS slot not found")
    with db.session() as conn:
        return {"tray": tray, "candidates": logic.ams_candidates(conn, tray)}


@app.post("/api/spools/{spool_id}/swapwith")
def swap_with(spool_id: int, body: dict):
    with db.session() as conn:
        res = logic.swap_spools(conn, spool_id, int(body.get("other") or 0))
    broadcast({"type": "changed"})
    return res


@app.post("/api/spools/{spool_id}/swap")
def swap(spool_id: int):
    with db.session() as conn:
        res = logic.swap_with_cabinet(conn, spool_id)
    broadcast({"type": "changed"})
    return res


@app.post("/api/spools/{spool_id}/reserve")
def reserve(spool_id: int):
    with db.session() as conn:
        res = logic.to_reserve(conn, spool_id)
    broadcast({"type": "changed"})
    return res


@app.post("/api/spools/{spool_id}/live")
def live(spool_id: int):
    with db.session() as conn:
        res = logic.to_live(conn, spool_id)
    broadcast({"type": "changed"})
    return res


@app.post("/api/spools/{spool_id}/linktag")
def link_tag(spool_id: int, payload: dict = Body(default={})):
    """With "tag": link this sticker. Without: the next sticker placed within 90 s belongs to the spool."""
    import time as _t
    with db.session() as conn:
        if payload.get("tag"):
            sp = logic.link_plain(conn, spool_id, payload["tag"])
            broadcast({"type": "changed"})
            return {"spool": sp}
        sp = logic.get_spool(conn, spool_id)
        if sp["tray_uid"]:
            raise logic.InventoryError("This spool already has a tag")
    _link_next.update(spool_id=spool_id, until=_t.time() + 90)
    return {"waiting": True, "seconds": 90}


@app.post("/api/linktag/cancel")
def link_tag_cancel():
    _link_next.update(spool_id=None, until=0.0)
    return {"ok": True}


@app.post("/api/spools/{spool_id}/unlinktag")
def unlink_tag(spool_id: int):
    with db.session() as conn:
        sp = logic.unlink_plain(conn, spool_id)
    broadcast({"type": "changed"})
    return {"spool": sp}


@app.post("/api/spools/bulk")
def spools_bulk(payload: dict = Body(...)):
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise logic.InventoryError("No spools selected")
    if payload.get("action") == "delete":
        db.backup("before-delete", series=False)      # several spools at once: always a fresh backup
    global _bulk_undo
    with db.session() as conn:
        res = logic.bulk(conn, ids, str(payload.get("action") or ""), payload.get("price"))
    # the undo data stays on the server; the page only gets a token for the "Rückgängig" button
    undo = res.pop("undo", None)
    _bulk_undo = {"token": secrets.token_hex(8), "ts": time.time(), **undo} if undo else None
    res["undo_token"] = _bulk_undo["token"] if _bulk_undo else None
    broadcast({"type": "changed"})
    return res


_bulk_undo: Optional[dict] = None
UNDO_SECONDS = 600


@app.post("/api/spools/bulk/undo")
def spools_bulk_undo(payload: dict = Body(...)):
    global _bulk_undo
    u = _bulk_undo
    if not u or payload.get("token") != u["token"] or time.time() - u["ts"] > UNDO_SECONDS:
        raise logic.InventoryError("Nothing left to undo")
    with db.session() as conn:
        res = logic.bulk_undo(conn, u)
    _bulk_undo = None
    broadcast({"type": "changed"})
    return res


@app.post("/api/spools/manual")
def add_manual(payload: dict = Body(...)):
    with db.session() as conn:
        sp = logic.add_manual(conn, int(payload["product_id"]), bool(payload.get("reserve")), brands._price(payload.get("price")))
    broadcast({"type": "changed"})
    return sp
