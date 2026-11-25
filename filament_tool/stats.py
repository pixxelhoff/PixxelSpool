"""Statistics tab: stock value, usage, cost and recorded prints.

Prices: the spool's own price (spools.price) wins, otherwise the line's estimated price (lines.price).
Price per gram = price / net weight. Usage comes from the remaining-percent history (AMS, weighing),
prints are recorded by notices.Watcher when a job finishes or fails.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta

from . import db
from .brands import DEFAULT_NET_G
from .logic import SPOOL_SELECT


def _net(sp: dict) -> float:
    return float(sp.get("weight_g") or sp.get("net_g") or DEFAULT_NET_G)


def _price(sp: dict):
    p = sp.get("price") if sp.get("price") is not None else sp.get("line_price")
    return float(p) if p is not None else None


def per_gram(conn: sqlite3.Connection, spool_id: int):
    """Price per gram of a spool, or None when no price is known."""
    r = conn.execute(SPOOL_SELECT + " WHERE s.id = ?", (spool_id,)).fetchone()
    if not r:
        return None
    sp = dict(r)
    p = _price(sp)
    return p / _net(sp) if p is not None else None


def _book(conn: sqlite3.Connection, rows: list, share: float = 1.0) -> tuple:
    """Detail rows, grams and cost (None while a spool has no price) for [{spool_id, slot, grams}]."""
    detail, grams, cost, known = [], 0.0, 0.0, True
    for r in rows:
        g = round(float(r.get("grams") or 0) * share, 1)
        pg = per_gram(conn, r["spool_id"]) if r.get("spool_id") else None
        c = round(g * pg, 2) if pg is not None else None
        known &= c is not None
        grams += g
        cost += c or 0
        detail.append({"slot": r.get("slot"), "spool_id": r.get("spool_id"), "grams": g, "cost": c})
    return detail, round(grams, 1), (round(cost, 2) if known and rows else None)


def _use_bound(conn: sqlite3.Connection, detail: list, sign: int = 1) -> None:
    """Spools assigned by hand to the AMS (no Bambu tag): the AMS doesn't measure them, so the print uses them up here."""
    from .logic import use_grams
    for d in detail:
        if d.get("spool_id") and (d.get("grams") or 0) > 0 and conn.execute(
                "SELECT 1 FROM spools WHERE id = ? AND ams_bound = 1", (d["spool_id"],)).fetchone():
            if sign > 0:
                use_grams(conn, d["spool_id"], d["grams"])
            else:   # amounts changed by hand: give back what was booked before
                s = conn.execute("SELECT remain_pct, weight_g, (SELECT net_g FROM products WHERE id = product_id) AS net_g "
                                 "FROM spools WHERE id = ?", (d["spool_id"],)).fetchone()
                if s and s["remain_pct"] is not None:
                    net = float(s["weight_g"] or s["net_g"] or 1000)
                    conn.execute("UPDATE spools SET remain_pct = ? WHERE id = ?",
                                 (round(min(100.0, float(s["remain_pct"]) + d["grams"] * 100 / net), 1), d["spool_id"]))


def record_print(conn: sqlite3.Connection, task: str, name: str, state: str, rows: list, progress: float = 100,
                 printer: str = "", note: str = "") -> bool:
    """Record a finished or failed print once per task.

    rows: [{spool_id, slot, grams}] with the full amount from the print file; a failed print is scaled by progress.
    note: "file" when the print file could not be read (no amounts).
    """
    if not task or conn.execute("SELECT 1 FROM prints WHERE task = ?", (task,)).fetchone():
        return False
    share = 1.0 if state == "finish" else max(0.0, min(1.0, (progress or 0) / 100))
    detail, grams, cost = _book(conn, rows, share)
    conn.execute("INSERT INTO prints (task, name, state, grams, cost, detail, printer, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (task, name, state, grams, cost, json.dumps(detail), printer or None, note or None))
    _use_bound(conn, detail)
    return True


def set_usage(conn: sqlite3.Connection, print_id: int, rows: list) -> bool:
    """Amounts entered by hand (or taken from a .gcode.3mf) for a print whose file could not be read.
    rows: [{spool_id, grams}]. Hand-assigned AMS spools are used up by the difference to what was booked before."""
    r = conn.execute("SELECT detail FROM prints WHERE id = ?", (print_id,)).fetchone()
    if not r:
        return False
    try:
        old = json.loads(r["detail"] or "[]")
    except ValueError:
        old = []
    clean = []
    for x in rows or []:
        g = float(x.get("grams") or 0)
        if g < 0 or g > 100000:
            raise ValueError()
        sid = int(x["spool_id"]) if x.get("spool_id") not in (None, "") else None
        if sid is not None and not conn.execute("SELECT 1 FROM spools WHERE id = ?", (sid,)).fetchone():
            raise ValueError()
        if g > 0:
            clean.append({"spool_id": sid, "grams": g, "slot": x.get("slot")})
    _use_bound(conn, old, -1)
    detail, grams, cost = _book(conn, clean)
    conn.execute("UPDATE prints SET detail = ?, grams = ?, cost = ?, note = ? WHERE id = ?",
                 (json.dumps(detail), grams, cost, "hand" if clean else None, print_id))
    _use_bound(conn, detail)
    return True


def fill_costs(conn: sqlite3.Connection) -> int:
    """Prints recorded before their spools had a price (e.g. delivery prices entered later, free spools at 0):
    compute the missing cost from the stored detail as soon as every spool used has a price. Returns the count."""
    n = 0
    for r in conn.execute("SELECT id, detail FROM prints WHERE cost IS NULL AND grams > 0").fetchall():
        try:
            detail = json.loads(r["detail"] or "[]")
        except ValueError:
            continue
        if not detail:
            continue
        total = 0.0
        for d in detail:
            if d.get("cost") is None:
                pg = per_gram(conn, d["spool_id"]) if d.get("spool_id") else None
                if pg is None:
                    break
                d["cost"] = round(float(d.get("grams") or 0) * pg, 2)
            total += d["cost"]
        else:
            conn.execute("UPDATE prints SET cost = ?, detail = ? WHERE id = ?", (round(total, 2), json.dumps(detail), r["id"]))
            n += 1
    return n


def _named(conn: sqlite3.Connection, detail: list) -> list:
    """Print detail rows with the spool's line, colour and swatch for the per-filament view."""
    out = []
    for d in detail:
        d = dict(d)
        if d.get("spool_id"):
            r = conn.execute(SPOOL_SELECT + " WHERE s.id = ?", (d["spool_id"],)).fetchone()
            if r:
                d.update({k: r[k] for k in ("line", "brand", "color_name", "name_en", "name_de", "hex", "colors", "swatch", "bambu_no")})
        out.append(d)
    return out


def prints_of(conn: sqlite3.Connection, month: str) -> list:
    """Recorded prints of one month (YYYY-MM), newest first."""
    if len(month) != 7 or month[4] != "-" or not (month[:4] + month[5:]).isdigit():
        return []
    out = []
    for r in conn.execute("SELECT * FROM prints WHERE substr(ts, 1, 7) = ? ORDER BY ts DESC, id DESC", (month,)).fetchall():
        p = {k: r[k] for k in ("id", "ts", "name", "state", "grams", "cost", "project", "note")}
        try:
            p["detail"] = _named(conn, json.loads(r["detail"] or "[]"))
        except ValueError:
            p["detail"] = []
        out.append(p)
    return out


def rename_print(conn: sqlite3.Connection, print_id: int, name: str) -> bool:
    """Give a recorded print another name (the printer's job name does not always fit). Empty = "Print job"."""
    name = " ".join(str(name or "").split())[:120]
    return conn.execute("UPDATE prints SET name = ? WHERE id = ?", (name or None, print_id)).rowcount > 0


def set_project(conn: sqlite3.Connection, print_id: int, project: str) -> bool:
    """Put a print into a project (several prints of one thing, a gift, an order). Empty = no project."""
    project = " ".join(str(project or "").split())[:80]
    return conn.execute("UPDATE prints SET project = ? WHERE id = ?", (project or None, print_id)).rowcount > 0


def price_history(conn: sqlite3.Connection) -> list:
    """Paid price per spool by delivery day, per line, spools and refills apart (F13). Free spools (0) are left out.
    Only lines with at least two deliveries with a price."""
    by: dict = {}
    for r in conn.execute("SELECT l.id AS line_id, l.name AS line, l.price AS line_price, s.received_at AS day, s.bought_refill AS rf, "
                          "AVG(s.price) AS price, COUNT(*) AS n FROM spools s JOIN products p ON p.id = s.product_id "
                          "JOIN lines l ON l.id = p.line_id WHERE s.price > 0 AND s.received_at IS NOT NULL "
                          "GROUP BY l.id, s.received_at, s.bought_refill ORDER BY s.received_at"):
        b = by.setdefault(r["line_id"], {"line": r["line"], "line_price": r["line_price"], "points": [], "refill_points": []})
        b["refill_points" if r["rf"] else "points"].append({"day": r["day"], "price": round(r["price"], 2), "spools": r["n"]})
    return sorted((b for b in by.values() if len(b["points"]) + len(b["refill_points"]) >= 2),
                  key=lambda b: -(len(b["points"]) + len(b["refill_points"])))


def projects(conn: sqlite3.Connection) -> list:
    """All projects with their prints counted together, newest first. cost is None if a print has no cost."""
    return [{"name": r["project"], "count": r["n"], "grams": round(r["g"] or 0), "cost": round(r["c"], 2) if r["c"] is not None and not r["unknown"] else None,
             "first": r["first"], "last": r["last"]}
            for r in conn.execute("SELECT project, COUNT(*) AS n, SUM(grams) AS g, SUM(cost) AS c, "
                                  "SUM(CASE WHEN cost IS NULL THEN 1 ELSE 0 END) AS unknown, MIN(ts) AS first, MAX(ts) AS last "
                                  "FROM prints WHERE project IS NOT NULL GROUP BY project ORDER BY MAX(ts) DESC")]


def delete_print(conn: sqlite3.Connection, print_id: int) -> bool:
    """Remove one recorded print (e.g. a wrong value). Prints are recorded once when the job ends,
    so a removed print does not come back."""
    return conn.execute("DELETE FROM prints WHERE id = ?", (print_id,)).rowcount > 0


def _months(n: int = 12) -> list:
    d = date.today().replace(day=1)
    out = []
    for _ in range(n):
        out.append(d.strftime("%Y-%m"))
        d = (d - timedelta(days=1)).replace(day=1)
    return out[::-1]


def overview(conn: sqlite3.Connection) -> dict:
    """Data for the statistics tab: stock, 12 months of usage/cost/spending, recent prints and totals."""
    fill_costs(conn)
    spools = [dict(r) for r in conn.execute(SPOOL_SELECT)]
    active = [s for s in spools if s["status"] != "empty"]
    by_mat: dict = {}
    rest_g = value = 0.0
    priced = 0
    for s in active:
        mat = {"SUPPORT": "Support", "SONSTIGES": "Other", "OTHER": "Other", "": "Other"}.get(db.material(s["line"]), db.material(s["line"]))
        frac = (s["remain_pct"] if s["remain_pct"] is not None else 100) / 100
        g = _net(s) * frac
        m = by_mat.setdefault(mat, {"material": mat, "spools": 0, "grams": 0.0})
        m["spools"] += 1
        m["grams"] += g
        rest_g += g
        p = _price(s)
        if p is not None:
            value += p * frac
            priced += 1
    # Usage per month (grams and cost) from the recorded prints. The remaining-percent history is not used here:
    # weighing, corrections and values reported when a spool is loaded would count as printed filament.
    # Months before PixxelSpool was used (no print recorded, no spool received yet) are left out, so a new
    # installation does not show a year of empty bars.
    first = [str(r[0])[:7] for r in conn.execute("SELECT MIN(ts) FROM prints UNION ALL SELECT MIN(received_at) FROM spools") if r[0]]
    start = min(first) if first else date.today().strftime("%Y-%m")
    months = {m: {"month": m, "grams": 0.0, "cost": 0.0, "spent": 0.0, "prints": 0} for m in _months() if m >= start}
    for r in conn.execute("SELECT substr(ts, 1, 7) AS m, COALESCE(SUM(grams), 0) AS g, COALESCE(SUM(cost), 0) AS c "
                          "FROM prints GROUP BY m"):
        if r["m"] in months:
            months[r["m"]]["grams"] += r["g"]
            months[r["m"]]["cost"] += r["c"]
    # Spending: spool prices by month received
    for s in spools:
        m = str(s.get("received_at") or "")[:7]
        p = _price(s)
        if m in months and p is not None:
            months[m]["spent"] += p
    for r in conn.execute("SELECT substr(ts, 1, 7) AS m, COUNT(*) AS n FROM prints GROUP BY m"):
        if r["m"] in months:
            months[r["m"]]["prints"] = r["n"]
    for m in months.values():
        for k in ("grams", "cost", "spent"):
            m[k] = round(m[k], 2 if k != "grams" else 0)
    prints = []
    for r in conn.execute("SELECT * FROM prints ORDER BY id DESC LIMIT 30"):
        p = dict(r)
        try:
            p["detail"] = _named(conn, json.loads(p["detail"] or "[]"))
        except ValueError:
            p["detail"] = []
        prints.append(p)
    tot = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(grams), 0) AS g, SUM(cost) AS c, "
                       "SUM(CASE WHEN state = 'finish' THEN 1 ELSE 0 END) AS ok FROM prints").fetchone()
    # per printer (prints without a printer belong to the first one)
    from . import bambu
    first = bambu.name_of("p1") if bambu.printers() else ""
    by_printer: dict = {}
    for r in conn.execute("SELECT printer, COUNT(*) AS n, COALESCE(SUM(grams), 0) AS g, SUM(cost) AS c FROM prints GROUP BY printer"):
        name = r["printer"] or first or "–"
        b = by_printer.setdefault(name, {"printer": name, "count": 0, "grams": 0.0, "cost": None})
        b["count"] += r["n"]
        b["grams"] += r["g"]
        if r["c"] is not None:
            b["cost"] = round((b["cost"] or 0) + r["c"], 2)
    for p in prints:
        p["printer"] = p.get("printer") or first
    since30 = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    used30 = sum(v["grams"] for k, v in months.items() if k >= since30[:7])
    return {
        "stock": {"spools": len(active), "grams": round(rest_g), "value": round(value, 2), "priced": priced,
                  "materials": sorted(({**m, "grams": round(m["grams"])} for m in by_mat.values()), key=lambda x: -x["grams"]),
                  "empty_total": sum(1 for s in spools if s["status"] == "empty")},
        "months": list(months.values()),
        "prints": prints,
        "prints_total": {"count": tot["n"], "ok": tot["ok"] or 0, "grams": round(tot["g"]), "cost": round(tot["c"], 2) if tot["c"] is not None else None},
        "used_month": round(used30),
        "projects": projects(conn),
        "price_history": price_history(conn),
        "by_printer": sorted(({**b, "grams": round(b["grams"])} for b in by_printer.values()), key=lambda b: -b["grams"])
        if len(by_printer) > 1 else [],
    }
