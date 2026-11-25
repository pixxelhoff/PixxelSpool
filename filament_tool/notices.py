"""Notifications (the bell): collect events with history and read/unread state.

Texts are stored as an English template plus arguments ({0}, {1} …) and translated in the browser.
Every notification has a key; the same key is never reported twice. New notifications are also sent as push.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import date
from typing import Callable, Optional

from . import db, insights, push, settings

log = logging.getLogger(__name__)

KEEP_DAYS = 90
CHECK_EVERY = 30        # seconds


def add(kind: str, key: str, title: str, args: Optional[list] = None, level: str = "info", link: str = "") -> bool:
    """Store a new notification. Returns False if the key already exists."""
    with db.session() as conn:
        cur = conn.execute("INSERT OR IGNORE INTO notices (kind, key, level, title, args, link) VALUES (?, ?, ?, ?, ?, ?)",
                           (kind, key, level, title, json.dumps(args or [], ensure_ascii=False), link))
        new = cur.rowcount > 0
    if new:
        push.notify(kind, title, args, level, link, key)
    return new


def listing(limit: int = 60) -> dict:
    with db.session() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM notices WHERE hidden = 0 ORDER BY id DESC LIMIT ?", (limit,))]
        unread = conn.execute("SELECT COUNT(*) FROM notices WHERE read = 0 AND hidden = 0").fetchone()[0]
    for r in rows:
        try:
            r["args"] = json.loads(r["args"] or "[]")
        except ValueError:
            r["args"] = []
    return {"unread": unread, "items": rows}


def unread() -> dict:
    with db.session() as conn:
        n = conn.execute("SELECT COUNT(*) FROM notices WHERE read = 0 AND hidden = 0").fetchone()[0]
        last = conn.execute("SELECT MAX(id) FROM notices WHERE hidden = 0").fetchone()[0] or 0
    return {"unread": n, "last": last}


def mark_read(ids: Optional[list] = None) -> None:
    with db.session() as conn:
        if ids:
            q = ",".join("?" * len(ids))
            conn.execute(f"UPDATE notices SET read = 1 WHERE id IN ({q})", [int(i) for i in ids])
        else:
            conn.execute("UPDATE notices SET read = 1 WHERE read = 0")


def hide(notice_id: int) -> None:
    """Hide one notification. Its key stays, so the same event does not come back."""
    with db.session() as conn:
        conn.execute("UPDATE notices SET read = 1, hidden = 1 WHERE id = ?", (notice_id,))


def clear() -> None:
    """Hide everything. Keys are remembered so nothing pops up again right away."""
    with db.session() as conn:
        conn.execute("UPDATE notices SET read = 1, hidden = 1")


def _spool_name(sp: dict) -> str:
    return " ".join(x for x in (sp.get("line"), sp.get("name_de") or sp.get("color_name") or sp.get("name_en")) if x)


class Watcher(threading.Thread):
    """Background thread: checks printer, stock and cabinet climate periodically and creates notifications."""

    def __init__(self, get_printers: Callable, get_pname: Callable, get_ha: Callable, get_job: Callable,
                 on_new: Callable[[], None]):
        """get_printers() -> {id: BambuThread}; get_pname(id) -> printer name or "" with a single printer;
        get_job(id) -> filament check of that printer's job."""
        super().__init__(daemon=True, name="notices")
        self.get_printers, self.get_pname, self.get_ha, self.get_job, self.on_new = get_printers, get_pname, get_ha, get_job, on_new
        self._job_state: dict = {}
        self._wake = threading.Event()
        self._last_daily = None

    def run(self) -> None:
        while True:
            self._wake.clear()
            try:
                if self.check():
                    self.on_new()
            except Exception as e:  # never let the thread die
                log.warning("Notifications: %s", e)
            self._wake.wait(CHECK_EVERY)

    def check(self) -> bool:
        """Run all checks once. Returns True if any new notification was created."""
        new = False
        for pid, b in self.get_printers().items():
            new |= self._printer(pid, b)
            new |= self._job(pid)
        new |= self._climate()
        new |= self._returns()
        new |= self._ams_humidity()
        new |= self._rollback()
        new |= self._setup()
        today = date.today().isoformat()
        if self._last_daily != today or new:
            new |= self._stock()
            new |= self._update()
            self._last_daily = today
            with db.session() as conn:
                conn.execute("DELETE FROM notices WHERE ts < datetime('now', 'localtime', ?)", (f"-{KEEP_DAYS} days",))
        return new

    # --- printer: print finished / failed, error messages
    def _printer(self, pid: str, b) -> bool:
        if not b or b.state.get("status") != "connected":
            return False
        from . import bambu
        j = bambu.job(b.snapshot())
        st, task, name = j["state"], j["task"] or j["name"], j["name"] or "Druck"
        pn = self.get_pname(pid)
        # with several printers the texts name the printer: "Print finished on {1}: {0}"
        on = (lambda tpl: tpl.replace(": {0}", " on {1}: {0}")) if pn else (lambda tpl: tpl)
        args = [name, pn] if pn else [name]
        new = False
        prev, self._job_state[pid] = self._job_state.get(pid), st
        if prev is not None and prev != st:
            # only a print PixxelSpool saw running is booked: after a restart (e.g. an update) the printer still
            # reports the last finished job, which must not be booked a second time
            if st in ("finish", "failed") and prev in ("prepare", "slicing", "running", "pause"):
                self._record(pid, task, name, st, j.get("progress") or 0)
            if st == "finish":
                new |= add("print", f"finish:{task}", on("Print finished: {0}"), args, "ok")
            elif st == "failed":
                new |= add("print", f"failed:{task}", on("Print failed: {0}"), args, "bad")
            elif st == "pause" and prev == "running":
                new |= add("print", f"pause:{task}:{int(j['progress'] or 0)}", on("Print paused: {0}"), args, "warn")
        from . import hms
        snap = b.snapshot().get("print") or {}
        msgs = hms.decode(snap.get("hms"), snap.get("print_error"), getattr(b, "_serial", ""), settings.lang())
        for m in msgs:   # every message once per print
            if m["text"]:
                tpl, a = ("Printer error {0} ({2}): {1}", [m["code"], m["text"], pn]) if pn else ("Printer error {0}: {1}", [m["code"], m["text"]])
            else:
                tpl, a = ("Printer error {0} ({1}) – please check the printer", [m["code"], pn]) if pn \
                    else ("Printer error {0} – please check the printer", [m["code"]])
            new |= add("printer", f"hms:{task}:{m['ecode']}", tpl, a, m["level"], "url:" + m["url"])
        return new

    def _record(self, pid: str, task: str, name: str, state: str, progress: float) -> None:
        """Record the print with usage and cost for the statistics (amount per AMS slot from the print file)."""
        from . import bambu, stats
        try:
            jv = self.get_job(pid) or {}
            rows = [{"slot": r.get("slot"), "spool_id": (r.get("spool") or {}).get("id"), "grams": r.get("need_g")}
                    for r in jv.get("rows") or []]
            with db.session() as conn:
                new = stats.record_print(conn, f"{task}|{date.today().isoformat()}", name, state, rows, progress,
                                         bambu.name_of(pid), "" if rows else "file")
            if new and not rows:
                add("print", f"nofile:{task}", "Print file of {0} could not be read: amounts unknown. "
                    "Add them in Statistics › Recent prints.", [name], "warn", "view:statsview")
        except Exception as e:
            log.warning("Print not recorded for statistics: %s", e)

    # --- filament check for the running print
    def _job(self, pid: str) -> bool:
        jv = self.get_job(pid)
        if not jv or not jv.get("active"):
            return False
        new = False
        for r in jv.get("rows") or []:
            if r["state"] not in ("tight", "short"):
                continue
            sp = r.get("spool") or {}
            what = _spool_name(sp) or r.get("label") or r["slot"]
            tpl = "Not enough filament: {0} ({1})" if r["state"] == "short" else "Filament running low: {0} ({1})"
            spare = r.get("spare")
            if spare:
                tpl += " – spare is at {2}"
            where = f"{jv['printer_name']} · {r['slot']}" if jv.get("printer_name") else r["slot"]
            new |= add("job", f"job:{pid}:{jv.get('name')}:{r['slot']}:{r['state']}", tpl,
                       [what, where, (spare or {}).get("slot_id", "")], "bad" if r["state"] == "short" else "warn",
                       f"spool:{sp['id']}" if sp.get("id") else "")
        return new

    # --- cabinet climate (Home Assistant)
    def _climate(self) -> bool:
        ha = self.get_ha()
        cl = (ha.state.get("climate") if ha else None) or {}
        if not cl:
            return False
        cabs = {c["key"]: c["name"] for c in settings.load().get("cabinets") or []}
        today = date.today().isoformat()
        new = False
        for key, v in cl.items():
            if v.get("hum") is not None and v["hum"] >= v.get("max_hum", 50):
                new |= add("climate", f"hum:{key}:{today}", "Cabinet {0}: humidity {1} % (limit {2} %)",
                           [cabs.get(key, key), round(v["hum"]), v.get("max_hum", 50)], "warn", "view:storage")
        return new

    # --- spool taken out of the AMS and not put back after a while (settings.return_min, off by default)
    def _returns(self) -> bool:
        mins = int(settings.load().get("return_min") or 0)
        if not mins:
            return False
        new = False
        with db.session() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT s.id, MAX(e.ts) AS since FROM spools s JOIN events e ON e.spool_id = s.id AND e.action = 'from_ams' "
                "WHERE s.needs_return = 1 AND s.ams_slot IS NULL GROUP BY s.id "
                "HAVING MAX(e.ts) < datetime('now', 'localtime', ?)", (f"-{mins} minutes",))]
            sps = {r["id"]: dict(conn.execute(insights.SPOOL_SELECT + " WHERE s.id = ?", (r["id"],)).fetchone()) for r in rows}
        for r in rows:
            sp = sps[r["id"]]
            new |= add("removed", f"ret:{sp['id']}:{r['since']}", "Not put back yet: {0} belongs on slot {1}",
                       [_spool_name(sp), sp.get("slot_id") or "–"], "info", f"spool:{sp['id']}")
        return new

    # --- AMS humidity above the limit from the options (settings.ams_hum_max, off by default), once a day per printer
    def _ams_humidity(self) -> bool:
        lim = int(settings.load().get("ams_hum_max") or 0)
        if not lim:
            return False
        new, today = False, date.today().isoformat()
        for pid, b in self.get_printers().items():
            if not b or b.state.get("status") != "connected":
                continue
            hums = [t.get("humidity") for t in b.state.get("trays") or [] if isinstance(t.get("humidity"), (int, float))]
            if hums and max(hums) > lim:
                new |= add("climate", f"amshum:{pid}:{today}", "AMS humidity {0} % (limit {1} %) – check the desiccant",
                           [round(max(hums)), lim], "warn", "view:printerview")
        return new

    # --- stock: spools almost empty, drying recommended (once per spool)
    def _stock(self) -> bool:
        st = settings.load()
        with db.session() as conn:
            low = insights.shopping(conn, st)["low"]
            dry = insights.drying(conn, st)
        new = False
        for sp in low:
            new |= add("stock", f"low:{sp['id']}", "Spool almost empty: {0} ({1} %), no spare in storage",
                       [_spool_name(sp), round(sp["remain_pct"])], "warn", f"spool:{sp['id']}")
        fresh = [sp for sp in dry if not _exists(f"dry:{sp['id']}:{sp.get('dried_at') or sp.get('opened_at')}")]
        if fresh:
            for sp in fresh:
                with db.session() as conn:   # remember the key without showing a separate entry
                    conn.execute("INSERT OR IGNORE INTO notices (kind, key, level, title, args, read, hidden) "
                                 "VALUES ('dry', ?, 'info', '', '[]', 1, 1)", (f"dry:{sp['id']}:{sp.get('dried_at') or sp.get('opened_at')}",))
            names = ", ".join(_spool_name(sp) for sp in fresh[:3]) + (" …" if len(fresh) > 3 else "")
            new |= add("dry", f"drygrp:{date.today().isoformat()}:{fresh[0]['id']}",
                       "Drying recommended: {0}" if len(fresh) == 1 else "Drying recommended for {1} spools: {0}",
                       [names, len(fresh)], "info", "view:storage")
        return new


    # --- new version on GitHub (once a day, can be switched off); security releases install themselves on the Pi
    def _update(self) -> bool:
        if not settings.load().get("update_check", True):
            return False
        from . import host, updater
        info = updater.check()
        if not info.get("available"):
            return False
        sec = info.get("security")
        if sec and host.KIND == "pi":
            try:
                if updater.auto_security(host.restart if host.can_restart() else None):
                    return add("update", f"autoupd:{sec}", "Installing security update {0} automatically …", [sec],
                               "info", "opt:updatetool")
            except ValueError as e:
                log.warning("Automatic security update: %s", e)
        if sec:
            return add("update", f"secupdate:{sec}", "Security update available: PixxelSpool {0}. Please install it soon.",
                       [info["latest"]], "warn", "opt:updatetool")
        return add("update", f"update:{info['latest']}", "Update available: PixxelSpool {0}", [info["latest"]],
                   "info", "opt:updatetool")

    # --- a new version needs a new system step from install.sh (host.SETUP_LEVEL)
    def _setup(self) -> bool:
        from . import host
        if host.KIND != "pi" or host.setup_level() >= host.SETUP_LEVEL:
            return False
        return add("update", f"setup:{host.SETUP_LEVEL}",
                   "Please refresh the setup once: run ./install.sh again in the PixxelSpool folder on the Pi.", [],
                   "warn", "opt:updatetool")

    # --- the update guard went back to the old version (guard.py)
    def _rollback(self) -> bool:
        from . import guard
        r = guard.rollback_result()
        if not r or r.get("seen"):
            return False
        guard.mark_seen()
        if r.get("ok"):
            return add("update", f"rollback:{r.get('to')}:{int(r.get('ts') or 0)}",
                       "Version {0} did not start. PixxelSpool went back to {1} by itself; your data is unchanged.",
                       [r.get("to"), r.get("from")], "warn", "opt:updatetool")
        return add("update", f"rollbackfail:{r.get('to')}:{int(r.get('ts') or 0)}",
                   "Version {0} had trouble starting and going back to {1} did not work. Please check the log.",
                   [r.get("to"), r.get("from")], "bad", "opt:updatetool")


def _exists(key: str) -> bool:
    with db.session() as conn:
        return conn.execute("SELECT 1 FROM notices WHERE key = ?", (key,)).fetchone() is not None
