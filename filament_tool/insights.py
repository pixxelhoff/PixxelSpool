"""Derived views on the stock: shopping list, drying hints and usage."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta

from . import db, settings
from .logic import SPOOL_SELECT


def _day(v):
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def drying(conn: sqlite3.Connection, st: dict) -> list:
    out = []
    if not st.get("dry_on", True):          # switched off in the options
        return out
    for r in conn.execute(SPOOL_SELECT + " WHERE s.status != 'empty' AND s.opened_at IS NOT NULL"):
        sp = dict(r)
        since = max(d for d in (_day(sp["opened_at"]), _day(sp.get("dried_at"))) if d) if _day(sp["opened_at"]) else None
        if not since:
            continue
        weeks = st["dry_weeks_dry"] if db.is_dry(sp["line"]) else st["dry_weeks_other"]
        days = (date.today() - since).days
        if days >= weeks * 7:
            sp["open_days"] = days
            out.append(sp)
    out.sort(key=lambda s: -s["open_days"])
    return out


def shopping(conn: sqlite3.Connection, st: dict) -> dict:
    """Shopping list: spools running low without a spare, and colors of the collection that are missing."""
    low = []
    for r in conn.execute(SPOOL_SELECT + " WHERE s.status != 'empty' AND s.remain_pct IS NOT NULL AND s.remain_pct <= ?",
                          (st["low_remain_pct"],)):
        sp = dict(r)
        spare = conn.execute("SELECT COUNT(*) FROM spools WHERE product_id = ? AND id != ? AND status = 'stored'",
                             (sp["product_id"], sp["id"])).fetchone()[0]
        if not spare:
            low.append(sp)
    used_up = [dict(r) for r in conn.execute(
        "SELECT p.*, l.name AS line, MAX(s.updated_at) AS emptied FROM spools s JOIN products p ON p.id = s.product_id "
        "JOIN lines l ON l.id = p.line_id WHERE s.status = 'empty' "
        "AND NOT EXISTS (SELECT 1 FROM spools x WHERE x.product_id = p.id AND x.status != 'empty') "
        "GROUP BY p.id ORDER BY emptied DESC")]
    lines = st.get("collect_lines") or []
    missing = []
    if lines:
        q = ",".join("?" * len(lines))
        missing = [dict(r) for r in conn.execute(
            f"SELECT p.*, l.name AS line FROM products p JOIN lines l ON l.id = p.line_id WHERE l.name IN ({q}) "
            "AND p.in_catalog = 1 AND p.discontinued = 0 AND NOT EXISTS (SELECT 1 FROM spools s WHERE s.product_id = p.id AND s.status != 'empty') "
            "ORDER BY l.name, p.bambu_no", lines)]
    # minimum stock per color: fewer spools (not empty) than wanted -> on the list, also before the last one is used up
    below = []
    for pid, want in (st.get("min_stock") or {}).items():
        p = conn.execute("SELECT p.*, l.name AS line, l.brand, l.shop_url, (SELECT COUNT(*) FROM spools s WHERE s.product_id = p.id "
                         "AND s.status != 'empty') AS have FROM products p JOIN lines l ON l.id = p.line_id WHERE p.id = ?",
                         (int(pid),)).fetchone()
        if p and p["have"] < want:
            below.append({**dict(p), "want": want})
    # the same for every color you have (or had) a spool of, unless the color has its own minimum
    dflt = int(st.get("min_stock_all") or 0)
    if dflt:
        own = {str(k) for k in (st.get("min_stock") or {})}
        for p in conn.execute("SELECT p.*, l.name AS line, l.brand, l.shop_url, (SELECT COUNT(*) FROM spools s WHERE s.product_id = p.id "
                              "AND s.status != 'empty') AS have FROM products p JOIN lines l ON l.id = p.line_id "
                              "WHERE EXISTS (SELECT 1 FROM spools s WHERE s.product_id = p.id)"):
            if str(p["id"]) not in own and p["have"] < dflt:
                below.append({**dict(p), "want": dflt})
    below.sort(key=lambda p: (p["line"], p.get("bambu_no") or ""))
    ids = {p["id"] for p in below}
    low = [s for s in low if s["product_id"] not in ids]
    used_up = [p for p in used_up if p["id"] not in ids]
    return {"low": low, "used_up": used_up, "missing": missing, "below_min": below}


def noted(conn: sqlite3.Connection, st: dict) -> list:
    """Colors put on the shopping list by hand. An entry is done once a new spool of that color has been added."""
    out, keep = [], []
    for e in st.get("shop_list") or []:
        p = conn.execute("SELECT p.*, l.name AS line, l.brand, l.shop_url FROM products p JOIN lines l ON l.id = p.line_id "
                         "WHERE p.id = ?", (e["id"],)).fetchone()
        if not p or conn.execute("SELECT 1 FROM spools WHERE product_id = ? AND created_at > ?", (e["id"], e["since"])).fetchone():
            continue
        keep.append(e)
        out.append(dict(p))
    if len(keep) != len(st.get("shop_list") or []):
        settings.save({"shop_list": keep})
    return out


def toggle_noted(conn: sqlite3.Connection, product_id: int, on: bool) -> None:
    if not conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone():
        raise ValueError("Color not found")
    lst = [e for e in settings.load().get("shop_list") or [] if e["id"] != product_id]
    if on:
        lst.append({"id": product_id, "since": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    settings.save({"shop_list": lst})


def set_min_stock(conn: sqlite3.Connection, product_id: int, n: int) -> None:
    """Minimum number of spools of one color (0 = no minimum: on the list only when the last one is used up)."""
    if not conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone():
        raise ValueError("Color not found")
    ms = dict(settings.load().get("min_stock") or {})
    ms.pop(str(product_id), None)
    if n > 0:
        ms[str(product_id)] = min(99, int(n))
    settings.save({"min_stock": ms})


REACH_DAYS = 60


def consumption(conn: sqlite3.Connection) -> dict:
    """Usage from the recorded prints (per spool and month). The remaining-percent history is not used: weighing and
    corrections would count as printed filament."""
    months: dict = {}
    per_product: dict = {}
    per60: dict = {}        # grams per color in the last REACH_DAYS days, for "lasts about …"
    since30 = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    since60 = (datetime.now() - timedelta(days=REACH_DAYS)).strftime("%Y-%m-%d")
    for r in conn.execute("SELECT ts, grams, detail FROM prints ORDER BY ts"):
        months[r["ts"][:7]] = months.get(r["ts"][:7], 0) + (r["grams"] or 0)
        if r["ts"][:10] < since60:
            continue
        try:
            detail = json.loads(r["detail"] or "[]")
        except ValueError:
            continue
        for d in detail:
            sp = conn.execute("SELECT product_id FROM spools WHERE id = ?", (d.get("spool_id"),)).fetchone() if d.get("spool_id") else None
            if sp:
                per60[sp["product_id"]] = per60.get(sp["product_id"], 0) + (d.get("grams") or 0)
                if r["ts"][:10] >= since30:
                    per_product[sp["product_id"]] = per_product.get(sp["product_id"], 0) + (d.get("grams") or 0)
    top = []
    for pid, g in sorted(per_product.items(), key=lambda x: -x[1])[:10]:
        p = conn.execute("SELECT p.*, l.name AS line FROM products p JOIN lines l ON l.id = p.line_id WHERE p.id = ?",
                         (pid,)).fetchone()
        if p:
            top.append({**dict(p), "grams": round(g)})
    first = conn.execute("SELECT MIN(ts) FROM prints").fetchone()[0]
    # usage per day: over the last REACH_DAYS days, or since the first print (at least two weeks, so one big
    # print on day one does not make a spool "last 2 days")
    days = REACH_DAYS
    if first:
        try:
            days = max(14, min(REACH_DAYS, (datetime.now() - datetime.fromisoformat(str(first)[:19])).days or 0))
        except ValueError:
            pass
    rate = {str(pid): round(g / days, 2) for pid, g in per60.items() if g > 0}
    return {"months": [{"month": m, "grams": round(g)} for m, g in sorted(months.items())][-12:],
            "top30": top, "since": first, "rate": rate, "rate_days": days}


def all_insights(conn: sqlite3.Connection) -> dict:
    st = settings.load()
    shop, mine = shopping(conn, st), noted(conn, st)
    # a color you put on the list yourself shows up there only, not a second time under low / used up / missing;
    # taken off the list again, it is back in its old place
    ids = {p["id"] for p in mine}
    shop = {"below_min": [p for p in shop["below_min"] if p["id"] not in ids],
            "low": [s for s in shop["low"] if s["product_id"] not in ids],
            "used_up": [p for p in shop["used_up"] if p["id"] not in ids],
            "missing": [p for p in shop["missing"] if p["id"] not in ids]}
    return {"shopping": {**shop, "noted": mine}, "drying": drying(conn, st), "usage": consumption(conn)}
