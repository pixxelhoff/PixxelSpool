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


def record_print(conn: sqlite3.Connection, task: str, name: str, state: str, rows: list, progress: float = 100,
                 printer: str = "") -> bool:
    """Record a finished or failed print once per task.

    rows: [{spool_id, slot, grams}] with the full amount from the print file; a failed print is scaled by progress.
    """
    if not task or conn.execute("SELECT 1 FROM prints WHERE task = ?", (task,)).fetchone():
        return False
    share = 1.0 if state == "finish" else max(0.0, min(1.0, (progress or 0) / 100))
    detail, grams, cost, known = [], 0.0, 0.0, True
    for r in rows:
        g = round(float(r.get("grams") or 0) * share, 1)
        pg = per_gram(conn, r["spool_id"]) if r.get("spool_id") else None
        c = round(g * pg, 2) if pg is not None else None
        known &= c is not None
        grams += g
        cost += c or 0
        detail.append({"slot": r.get("slot"), "spool_id": r.get("spool_id"), "grams": g, "cost": c})
    conn.execute("INSERT INTO prints (task, name, state, grams, cost, detail, printer) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (task, name, state, round(grams, 1), round(cost, 2) if known and rows else None, json.dumps(detail),
                  printer or None))
    # spools assigned by hand to the AMS (no Bambu tag): the AMS doesn't measure them, so the print uses them up here
    from .logic import use_grams
    for d in detail:
        if d["spool_id"] and d["grams"] > 0 and conn.execute(
                "SELECT 1 FROM spools WHERE id = ? AND ams_bound = 1", (d["spool_id"],)).fetchone():
            use_grams(conn, d["spool_id"], d["grams"])
    return True


def prints_of(conn: sqlite3.Connection, month: str) -> list:
    """Recorded prints of one month (YYYY-MM), newest first."""
    if len(month) != 7 or month[4] != "-" or not (month[:4] + month[5:]).isdigit():
        return []
    return [{k: r[k] for k in ("id", "ts", "name", "state", "grams", "cost")}
            for r in conn.execute("SELECT * FROM prints WHERE substr(ts, 1, 7) = ? ORDER BY ts DESC, id DESC", (month,))]


def rename_print(conn: sqlite3.Connection, print_id: int, name: str) -> bool:
    """Give a recorded print another name (the printer's job name does not always fit). Empty = "Print job"."""
    name = " ".join(str(name or "").split())[:120]
    return conn.execute("UPDATE prints SET name = ? WHERE id = ?", (name or None, print_id)).rowcount > 0


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
            p["detail"] = json.loads(p["detail"] or "[]")
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
        "by_printer": sorted(({**b, "grams": round(b["grams"])} for b in by_printer.values()), key=lambda b: -b["grams"])
        if len(by_printer) > 1 else [],
    }
