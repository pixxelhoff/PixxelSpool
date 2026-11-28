"""Derived views on the stock: shopping list, drying hints and usage."""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from datetime import date, datetime, timedelta

from . import brands, db, settings
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
    """Shopping list: spools running low without a spare, used-up colors and colors below their minimum stock."""
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
    missing = []    # #57: "collection lines" removed, the minimum stock covers it
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


def _open(e: dict) -> bool:
    """#69: an entry that is not ordered yet; per color there is at most one, next to any number of ordered ones."""
    return e.get("state") != "ordered"


def _match(e: dict, product_id: int, order: Optional[str]) -> bool:
    """The entry of a color that a request means: the ordered one of that order, else the one not ordered yet."""
    return e["id"] == product_id and (e.get("state") == "ordered" and (e.get("order") or "") == order if order is not None else _open(e))


def _got(conn: sqlite3.Connection, lst: list) -> list:
    """#69: spools added since each entry was listed, per entry. A color can be on the list more than once (ordered
    twice, or ordered and noted again): every new spool counts once, for the oldest order first, then the next one,
    and for the entry not ordered yet last."""
    got = [0] * len(lst)
    by = {}
    for i, e in enumerate(lst):
        by.setdefault(e["id"], []).append(i)
    for pid, idx in by.items():
        if len(idx) == 1:
            e = lst[idx[0]]
            got[idx[0]] = conn.execute("SELECT COUNT(*) FROM spools WHERE product_id = ? AND created_at > ?", (pid, e["since"])).fetchone()[0]
            continue
        first = min(lst[i]["since"] for i in idx)
        new = [r[0] for r in conn.execute("SELECT created_at FROM spools WHERE product_id = ? AND created_at > ? ORDER BY created_at",
                                          (pid, first))]
        taken = [False] * len(new)
        for i in sorted(idx, key=lambda i: (_open(lst[i]), lst[i].get("order") or "", lst[i]["since"])):
            want, n = int(lst[i].get("qty") or 1), 0
            for j, c in enumerate(new):
                if n >= want:
                    break
                if not taken[j] and c > lst[i]["since"]:
                    taken[j], n = True, n + 1
            got[i] = n
    return got


def noted(conn: sqlite3.Connection, st: dict) -> list:
    """Colors put on the shopping list by hand. An entry is done once a new spool of that color has been added."""
    out, keep = [], []
    lst = st.get("shop_list") or []
    got = _got(conn, lst)
    orders = {o.get("id"): o for o in st.get("orders") or [] if isinstance(o, dict)}
    parcels = {x.get("id"): x for x in st.get("parcels") or []}
    for e, g in zip(lst, got):
        p = conn.execute("SELECT p.*, l.name AS line, l.brand, l.shop_url FROM products p JOIN lines l ON l.id = p.line_id "
                         "WHERE p.id = ?", (e["id"],)).fetchone()
        if not p:
            continue
        # an entry is done once as many new spools of that color were added as were wanted (F11: count per item)
        want = int(e.get("qty") or 1)
        if g >= want:
            continue
        keep.append(e)
        state = e.get("state") or ("cart" if e.get("cart") else "")
        o = orders.get(e.get("order")) if state == "ordered" else None
        out.append({**dict(p), "qty": want - g, "qty_total": want, "state": state, "refill": bool(e.get("refill")),
                    "price": e.get("price"), "order": e.get("order") or "", "price_hint": brands.last_price(conn, e["id"]),
                    **({"order_date": o.get("date"), "order_total": o.get("total")} if o else {}),
                    **({"parcel": parcels[e["parcel"]]} if state == "ordered" and e.get("parcel") in parcels else {})})
    if len(keep) != len(lst):
        settings.save({"shop_list": keep})
    return out


def toggle_noted(conn: sqlite3.Connection, product_id: int, on: bool, qty: Optional[int] = None, order: Optional[str] = None) -> None:
    """Put a color on the shopping list (qty spools, default 1) or take it off. With qty on a listed color only the
    number changes; spools added since it was listed still count. #69: without order this is the entry not ordered
    yet (a new one even if the color is already ordered), with order the ordered entry of that order."""
    if not conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone():
        raise ValueError("Color not found")
    cur = settings.load().get("shop_list") or []
    i = next((k for k, e in enumerate(cur) if _match(e, product_id, order)), None)
    if order is not None and i is None:
        raise ValueError("Color not found")
    got = _got(conn, cur)[i] if i is not None else 0
    lst = [e for k, e in enumerate(cur) if k != i]
    if on and (qty is None or qty > 0):
        old = cur[i] if i is not None else None
        e = dict(old) if old and qty is not None else {"id": product_id, "since": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        if qty is not None and old:
            e["qty"] = min(99, qty + got)       # qty is what is still to buy
        else:
            e["qty"] = min(99, qty or 1)
        if i is not None:
            lst.insert(i, e)                     # keeps its place (#68: sorted like the order)
        else:
            lst.append(e)
    settings.save({"shop_list": lst})


def set_entry(product_id: int, state: Optional[str] = None, refill: Optional[bool] = None, order: Optional[str] = None) -> None:
    """#58/#62: status of a noted color ("" noted, "cart" in the Bambu Lab shop cart, "ordered" on the way, "soldout" not available right now) and whether
    it is bought as a refill. Only notes for you, nothing is sent to the shop. A scanned new spool still counts down.
    #69: order picks an ordered entry; marked "ordered" by hand, an entry gets an order of its own (without prices),
    and an ordered entry set back joins the color's entry not ordered yet."""
    lst = settings.load().get("shop_list") or []
    i = next((k for k, e in enumerate(lst) if _match(e, product_id, order)), None)
    if i is None:
        raise ValueError("Color not found")
    e = {k: v for k, v in lst[i].items() if k != "cart"}
    if refill is not None:
        e["refill"] = bool(refill)
    if state is not None:
        new = state if state in ("cart", "ordered", "soldout") else ""
        if new == "ordered" and _open(e):
            e = {**{k: v for k, v in e.items() if k != "price"}, "order": "m" + datetime.now().strftime("%Y%m%d%H%M%S")}
        elif new != "ordered" and not _open(e):
            e = {k: v for k, v in e.items() if k not in ("order", "price")}
            j = next((k for k, x in enumerate(lst) if k != i and _match(x, product_id, None)), None)
            if j is not None:                    # the color is noted again already: one entry with both counts
                o = lst[j]
                lst[j] = {**o, "qty": min(99, int(o.get("qty") or 1) + int(e.get("qty") or 1)), "since": min(o["since"], e["since"])}
                settings.save({"shop_list": [x for k, x in enumerate(lst) if k != i]})
                return
        e["state"] = new
    lst[i] = e
    settings.save({"shop_list": lst})


CREDITS_PER_UNIT = 100      # Bambu Lab: 100 credits = 1 € (or 1 unit of the shop currency)


def _num(v, lo: float, hi: float, what: str) -> float:
    try:
        n = float(str(v if v not in (None, "") else 0).replace(",", "."))
    except ValueError:
        raise ValueError("Please enter a number")
    if not lo <= n <= hi:
        raise ValueError("Value out of range")
    return n


def record_order(conn: sqlite3.Connection, items: list, shipping=0, credits_used=0, credits_earned=0) -> dict:
    """#64: record a shop order for colors on the shopping list. items: [{id, qty, total, refill}] with the shop price
    of the line (all spools of that color). Shipping and the credits used are shared out over the spools by price, so each entry gets the price you
    really paid per spool; it is filled in when the new spool is scanned. The credits balance changes by
    earned − used. The entries become "ordered"."""
    ship, used, earned = _num(shipping, 0, 1000, "shipping"), int(_num(credits_used, 0, 10 ** 7, "credits")), int(_num(credits_earned, 0, 10 ** 7, "credits"))
    st = settings.load()
    lst = st.get("shop_list") or []
    by = {e["id"]: e for e in lst if _open(e)}      # #69: the entries not ordered yet
    rows = []
    for it in items or []:
        try:
            pid, qty = int(it["id"]), max(1, min(99, int(it.get("qty") or 1)))
        except (TypeError, ValueError, KeyError):
            continue
        if pid not in by:
            raise ValueError("Color not found")
        # #67: the price of the whole line as in the shop cart (2 spools with volume discount: 21.19 for both);
        # "price" per spool is still accepted
        total = brands._price(it.get("total")) if it.get("total") not in (None, "") else None
        if total is None and it.get("price") not in (None, ""):
            total = round(brands._price(it.get("price")) * qty, 2)
        rows.append({"id": pid, "qty": qty, "total": total, "price": round(total / qty, 4) if total is not None else None,
                     "refill": bool(it.get("refill"))})
    if not rows:
        raise ValueError("Nothing selected")
    subtotal = round(sum(r["total"] for r in rows if r["total"] is not None), 2)
    extra = ship - used / CREDITS_PER_UNIT
    oid = datetime.now().strftime("%Y%m%d%H%M%S")
    names = {}
    for r in rows:
        if r["price"] is not None:
            r["paid"] = round(max(0.0, r["price"] * (1 + extra / subtotal)), 2) if subtotal > 0 else round(r["price"], 2)
        else:
            r["paid"] = None
        p = conn.execute("SELECT p.*, l.name AS line FROM products p JOIN lines l ON l.id = p.line_id WHERE p.id = ?", (r["id"],)).fetchone()
        names[r["id"]] = f"{p['line']} {p['name_de'] or p['color_name'] or ''}".strip() if p else str(r["id"])
    new = []
    for e, got in zip(lst, _got(conn, lst)):
        r = next((x for x in rows if x["id"] == e["id"]), None) if _open(e) else None
        if r:
            e = {**{k: v for k, v in e.items() if k not in ("price", "cart")}, "state": "ordered", "qty": min(99, r["qty"] + got),
                 "refill": r["refill"], "order": oid, **({"price": r["paid"]} if r["paid"] is not None else {})}
        new.append(e)
    total = round(subtotal + ship - used / CREDITS_PER_UNIT, 2)
    order = {"id": oid, "date": datetime.now().strftime("%Y-%m-%d"), "shipping": round(ship, 2), "credits_used": used,
             "credits_earned": earned, "subtotal": subtotal, "total": total,
             "items": [{"id": r["id"], "name": names[r["id"]], "qty": r["qty"], "total": r["total"],
                       "price": round(r["price"], 2) if r["price"] is not None else None, "paid": r["paid"], "refill": r["refill"]} for r in rows]}
    settings.save({"shop_list": new, "orders": (st.get("orders") or []) + [order],
                   "credits": max(0, int(st.get("credits") or 0) - used + earned)})
    return order


def order_again(conn: sqlite3.Connection, oid: str) -> int:
    """#78: put the colors of a recorded order back on the shopping list (on top of what is noted already), with
    the same number of spools and refill choice. Returns the number of spools added."""
    o = next((x for x in settings.load().get("orders") or [] if x.get("id") == oid), None)
    if not o:
        raise ValueError("Order not found")
    n = 0
    for it in o.get("items") or []:
        try:
            pid, qty = int(it["id"]), max(1, min(99, int(it.get("qty") or 1)))
        except (TypeError, ValueError, KeyError):
            continue
        if not conn.execute("SELECT 1 FROM products WHERE id = ?", (pid,)).fetchone():
            continue
        cur = next((p for p in noted(conn, settings.load()) if p["id"] == pid and p["state"] != "ordered"), None)
        toggle_noted(conn, pid, True, min(99, (cur["qty"] if cur else 0) + qty))
        set_entry(pid, None, bool(it.get("refill")))
        n += qty
    return n


def spending(conn: sqlite3.Connection, frm: str = "", to: str = "") -> dict:
    """#77: what the spools cost: per month (by the day received), per line with the price per kg, and what the
    Bambu Lab credits saved. Uses the price paid per spool (entered per delivery, or filled in from an order).
    #86: frm/to (YYYY-MM-DD) limit it to a time range; without them the last 12 months with spools."""
    from .stats import period, _day
    custom = bool(_day(frm) or _day(to))
    frm, to = period(frm, to)
    lo, hi = frm or "0000-00-00", to
    day = "COALESCE(s.received_at, substr(s.created_at, 1, 10))"
    months = [dict(r) for r in conn.execute(
        f"SELECT substr({day}, 1, 7) AS month, COUNT(*) AS spools, ROUND(SUM(s.price), 2) AS total FROM spools s "
        f"WHERE s.price IS NOT NULL AND {day} >= ? AND {day} <= ? GROUP BY month ORDER BY month DESC LIMIT ?",
        (lo, hi, 120 if custom else 12))]
    if not custom and months:        # the 12 months shown are the range of the lines below too
        lo = months[-1]["month"] + "-01"
    lines = []
    for r in conn.execute(
            "SELECT l.name AS line, l.net_g, COUNT(*) AS spools, ROUND(SUM(s.price), 2) AS total, AVG(s.price) AS avg, "
            "SUM(CASE WHEN s.bought_refill = 1 THEN 1 ELSE 0 END) AS refills "
            "FROM spools s JOIN products p ON p.id = s.product_id JOIN lines l ON l.id = p.line_id "
            f"WHERE s.price IS NOT NULL AND {day} >= ? AND {day} <= ? GROUP BY l.id ORDER BY total DESC", (lo, hi)):
        d = dict(r)
        d["per_kg"] = round(d.pop("avg") * 1000 / (d.pop("net_g") or 1000), 2)
        lines.append(d)
    unpriced = conn.execute("SELECT COUNT(*) FROM spools WHERE price IS NULL").fetchone()[0]
    orders = [o for o in settings.load().get("orders") or [] if lo <= str(o.get("date") or "") <= hi]
    return {"months": list(reversed(months)), "lines": lines, "unpriced": unpriced,
            "total": round(sum(m["total"] or 0 for m in months), 2),
            "credits_used": sum(int(o.get("credits_used") or 0) for o in orders),
            "credits_earned": sum(int(o.get("credits_earned") or 0) for o in orders),
            "shipping": round(sum(float(o.get("shipping") or 0) for o in orders), 2), "orders": len(orders)}


CARRIERS = ("dhl", "dpd", "ups", "gls", "hermes", "fedex", "post_at", "other")


def set_parcel(order: str, ids: list, carrier: str = "", tracking: str = "", parcel: Optional[str] = None) -> None:
    """#71: Bambu Lab often ships one order in several parcels. Mark which colors of an order are in a parcel
    (ids = product ids) with the carrier and tracking number; a new parcel without parcel id, no ids = remove it."""
    st = settings.load()
    lst, parcels = st.get("shop_list") or [], list(st.get("parcels") or [])
    try:
        want = {int(x) for x in ids or []}
    except (TypeError, ValueError):
        raise ValueError("Color not found")
    order = str(order or "")
    if parcel and not any(x["id"] == parcel for x in parcels):
        raise ValueError("Parcel not found")
    pid = parcel or "p" + datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
    out = []
    for e in lst:
        if e.get("state") == "ordered" and (e.get("order") or "") == order:
            if e["id"] in want:
                e = {**e, "parcel": pid}
            elif e.get("parcel") == pid:
                e = {k: v for k, v in e.items() if k != "parcel"}
        out.append(e)
    used = {e.get("parcel") for e in out if e.get("parcel")}
    if want:
        p = {"id": pid, "order": order, "carrier": carrier if carrier in CARRIERS else "", "tracking": str(tracking or "").strip()[:60],
             "date": next((x["date"] for x in parcels if x["id"] == pid), datetime.now().strftime("%Y-%m-%d"))}
        parcels = [x for x in parcels if x["id"] != pid] + [p]
    parcels = [x for x in parcels if x["id"] in used]        # parcels whose spools have all arrived are dropped
    settings.save({"shop_list": out, "parcels": parcels})


def reorder(ids: list) -> None:
    """#68: sort the shopping list like the shop order (ids first in that order, the rest behind)."""
    lst = settings.load().get("shop_list") or []
    pos = {}
    for i, x in enumerate(ids or []):
        try:
            pos.setdefault(int(x), i)
        except (TypeError, ValueError):
            continue
    settings.save({"shop_list": sorted(lst, key=lambda e: pos.get(e["id"], len(pos)) if _open(e) else len(pos))})


def order_price(product_id: int) -> tuple:
    """#64: (price, refill) of an ordered color for the next scanned spool, or (None, None)."""
    for e in sorted(settings.load().get("shop_list") or [], key=lambda e: e.get("order") or ""):   # #69: oldest order first
        if e["id"] == product_id and e.get("state") == "ordered":
            return e.get("price"), bool(e.get("refill"))
    return None, None


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
    # #56: below the minimum stays visible until the noted spools cover the gap ("need" = still missing after the
    # noted ones); the button there puts exactly that number on the list
    qty = {}
    for p in mine:                          # #69: a color can be on the list more than once (ordered and noted again)
        qty[p["id"]] = qty.get(p["id"], 0) + int(p.get("qty") or 0)
    below = []
    for p in shop["below_min"]:
        need = p["want"] - p["have"] - qty.get(p["id"], 0)
        if need > 0:
            below.append({**p, "noted": qty.get(p["id"], 0), "need": need})
    shop = {"below_min": below,
            "low": [s for s in shop["low"] if s["product_id"] not in ids],
            "used_up": [p for p in shop["used_up"] if p["id"] not in ids],
            "missing": []}
    # #63: loose refills in storage (each needs an empty spool), for the spool balance at the top of the list
    refills = conn.execute("SELECT COUNT(*) FROM spools WHERE is_refill = 1 AND status = 'stored'").fetchone()[0]
    return {"shopping": {**shop, "noted": mine, "refills_stored": refills}, "drying": drying(conn, st), "usage": consumption(conn)}
