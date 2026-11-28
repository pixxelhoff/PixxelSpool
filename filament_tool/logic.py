"""Storage logic: slot assignment, scan handling and actions on spools."""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Optional

from . import db

SPOOL_SELECT = """
SELECT s.*, p.color_name, p.name_en, p.name_de, p.colors, p.kind, p.bambu_no, p.hex, p.swatch,
       p.line_id, l.name AS line, l.brand, l.spool_g, l.net_g, l.price AS line_price, l.shop_url,
       l.dry_temp, l.dry_hours, p.sku,
       sl.kind AS slot_kind
FROM spools s
JOIN products p ON p.id = s.product_id
JOIN lines l ON l.id = p.line_id
LEFT JOIN slots sl ON sl.id = s.slot_id
"""


class InventoryError(Exception):
    """Domain error shown to the user (English text, translated in the browser). Mapped to HTTP 409."""


def _row(r: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(r) if r is not None else None


def log(conn: sqlite3.Connection, spool_id: Optional[int], action: str, detail: str = "") -> None:
    conn.execute("INSERT INTO events (spool_id, action, detail) VALUES (?, ?, ?)",
                 (spool_id, action, detail))


def get_spool(conn: sqlite3.Connection, spool_id: int) -> dict:
    r = conn.execute(SPOOL_SELECT + " WHERE s.id = ?", (spool_id,)).fetchone()
    if r is None:
        raise InventoryError("Spool not found")
    return {**dict(r), "last_used": last_used(conn, spool_id).get(spool_id)}


def last_used(conn: sqlite3.Connection, spool_id: Optional[int] = None) -> dict:
    """When a spool was last used: the last time its remaining filament went down (reported by the AMS
    or found by weighing). {spool_id: "YYYY-MM-DD HH:MM:SS"}; spools never used are missing."""
    where = "WHERE spool_id = ?" if spool_id is not None else ""
    rows = conn.execute(
        "SELECT spool_id, MAX(ts) FROM (SELECT spool_id, ts, remain_pct, "
        "LAG(remain_pct) OVER (PARTITION BY spool_id ORDER BY id) AS prev FROM usage " + where + ") "
        "WHERE prev IS NOT NULL AND remain_pct < prev GROUP BY spool_id",
        (spool_id,) if spool_id is not None else ()).fetchall()
    return {r[0]: r[1] for r in rows}


def used_up(conn: sqlite3.Connection, limit: int = 200) -> list:
    """Spools marked as empty, most recently emptied first (for Options › Used-up spools)."""
    rows = conn.execute(
        SPOOL_SELECT.replace("FROM spools s", ", (SELECT MAX(e.ts) FROM events e WHERE e.spool_id = s.id AND e.action = 'empty') "
                             "AS emptied_at FROM spools s")
        + " WHERE s.status = 'empty' ORDER BY COALESCE(emptied_at, s.updated_at) DESC, s.id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def cabinet_spool(conn: sqlite3.Connection, product_id: int) -> Optional[dict]:
    return _row(conn.execute(SPOOL_SELECT + " WHERE s.product_id = ? AND s.in_cabinet = 1",
                             (product_id,)).fetchone())


def free_cabinet_slots(conn: sqlite3.Connection) -> list:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM slots WHERE kind = 'cabinet' AND id NOT IN "
        "(SELECT slot_id FROM spools WHERE in_cabinet = 1) ORDER BY cabinet, row, pos")]


def _line_of(conn: sqlite3.Connection, product_id: int) -> str:
    r = conn.execute("SELECT l.name FROM products p JOIN lines l ON l.id = p.line_id WHERE p.id = ?",
                     (product_id,)).fetchone()
    return r["name"] if r else ""


def propose_slot(conn: sqlite3.Connection, product_id: int) -> tuple:
    """(slot_id, in_cabinet) for a new spool of this product.

    Color already on a rod -> its cabinet's shelf (reserve). Else a free slot in the matching cabinet, then anywhere.
    """
    line = _line_of(conn, product_id)
    home = db.home_cabinet(line)
    if cabinet_spool(conn, product_id) is None:
        free = free_cabinet_slots(conn)
        for slot in [x for x in free if x.startswith(db.cab_prefix(home))] + free:
            return slot, 1
    return reserve_slot(conn, home), 0


def reserve_slot(conn: sqlite3.Connection, home: str) -> str:
    """The reserve slot of a storage (or, if it has none, of any other storage). Raises when no reserve exists,
    e.g. a storage set up without reserve: then a second spool of a color already on a rod has no place."""
    want = db.overflow_id(home)
    if conn.execute("SELECT 1 FROM slots WHERE id = ?", (want,)).fetchone():
        return want
    r = conn.execute("SELECT id FROM slots WHERE kind = 'overflow' ORDER BY cabinet, row LIMIT 1").fetchone()
    if r:
        return r["id"]
    raise InventoryError("A spool of this type is already in storage, and there is no reserve for further spools.")


def default_overflow(conn: sqlite3.Connection) -> str:
    r = conn.execute("SELECT id FROM slots WHERE kind = 'overflow' ORDER BY cabinet, row LIMIT 1").fetchone()
    if not r:
        raise InventoryError("A spool of this type is already in storage, and there is no reserve for further spools.")
    return r["id"]


def ideal_layout(conn: sqlite3.Connection) -> dict:
    """Ideal layout: every spool in its home cabinet; a spool keeps its slot where possible. Spools in use keep
    their slot."""
    spools = [dict(r) for r in conn.execute(SPOOL_SELECT + " WHERE s.in_cabinet = 1")]
    fixed = {s["slot_id"] for s in spools if s["status"] == "in_use"}
    target: dict = {}
    homeless = [s for s in spools if s["status"] != "in_use"]
    used = set(fixed)
    for s in homeless:   # keep the current slot if it stays free
        if s["slot_id"] not in used:
            target[s["id"]] = s["slot_id"]; used.add(s["slot_id"])
    for s in homeless:
        if s["id"] in target:
            continue
        home = db.home_cabinet(s["line"])
        cand = [x for x in free_slots_ordered(conn) if x not in used]
        pick = next((x for x in cand if x.startswith(db.cab_prefix(home))), cand[0] if cand else s["slot_id"])
        target[s["id"]] = pick; used.add(pick)
    return target


def free_slots_ordered(conn: sqlite3.Connection) -> list:
    return [r["id"] for r in conn.execute("SELECT id FROM slots WHERE kind = 'cabinet' ORDER BY cabinet, row, pos")]


def plan_moves(conn: sqlite3.Connection, target: dict) -> list:
    """Moves that can be carried out one after another. For circular swaps one spool is parked briefly on a
    free slot (or the shelf)."""
    spools = {s["id"]: dict(s) for s in conn.execute(SPOOL_SELECT + " WHERE s.in_cabinet = 1")}
    cur = {sid: s["slot_id"] for sid, s in spools.items()}
    occ = {slot: sid for sid, slot in cur.items()}
    all_slots = [r["id"] for r in conn.execute(
        "SELECT id FROM slots WHERE kind = 'cabinet' ORDER BY cabinet, row, pos")]
    pending = [sid for sid, t in sorted(target.items(), key=lambda x: all_slots.index(x[1]))
               if cur.get(sid) != t]
    steps = []

    def do(sid, to, temp=False):
        frm = cur[sid]
        occ.pop(frm, None)
        if not to.startswith("Ü-"):
            occ[to] = sid
        cur[sid] = to
        steps.append({"spool": spools[sid], "from": frm, "to": to, "temp": temp})

    guard = 0
    while pending and guard < 10000:
        guard += 1
        movable = [sid for sid in pending if target[sid] not in occ]
        if movable:
            for sid in movable:
                if target[sid] not in occ:
                    do(sid, target[sid]); pending.remove(sid)
            continue
        sid = pending[0]   # break up a circular swap
        spare = next((x for x in all_slots if x not in occ and x not in target.values()), None)
        do(sid, spare or db.overflow_id(db.home_cabinet(spools[sid]['line'])), temp=True)
    now_free = set(free_cabinet_slots(conn))
    seen = set()
    for st in steps:   # doable now: target is free and it is this spool's first step
        sid = st["spool"]["id"]
        st["ready"] = sid not in seen and (st["to"].startswith("Ü-") or st["to"] in now_free)
        seen.add(sid)
    return steps


def sort_plan(conn: sqlite3.Connection) -> list:
    return plan_moves(conn, ideal_layout(conn))


def reorg_plan(conn: sqlite3.Connection) -> list:
    """Required moves: spools that are not in their home cabinet. Reserve spools on the wrong shelf are included."""
    spools = [dict(r) for r in conn.execute(SPOOL_SELECT + " WHERE s.status != 'empty' AND s.slot_id IS NOT NULL")]
    occupied = {s["slot_id"] for s in spools if s["in_cabinet"]}
    target = {}
    for s in spools:
        if not s["in_cabinet"] or s["status"] == "in_use" or s.get("manual_place"):
            continue
        if not s["slot_id"].startswith(db.cab_prefix(db.home_cabinet(s["line"]))):
            home = db.home_cabinet(s["line"])
            bs_free = [x for x in free_slots_ordered(conn) if x.startswith(db.cab_prefix(home)) and x not in occupied
                       and x not in target.values()]
            if bs_free:
                target[s["id"]] = bs_free[0]
    steps = plan_moves(conn, {**{s["id"]: s["slot_id"] for s in spools if s["in_cabinet"]}, **target}) if target else []
    for s in spools:
        want = db.overflow_prefix(db.home_cabinet(s['line']))
        if not s["in_cabinet"] and not s.get("manual_place") and not s["slot_id"].startswith(want):
            steps.append({"spool": s, "from": s["slot_id"], "to": want + "1", "temp": False, "ready": True})
    return steps


# ---------------------------------------------------------------- scanning

def handle_scan(conn: sqlite3.Connection, tag: dict) -> dict:
    """Handle a scanned tag. Only changes data when the result is unambiguous."""
    known = conn.execute(SPOOL_SELECT + " WHERE s.tray_uid = ?", (tag["tray_uid"],)).fetchone()
    if known is not None:
        if not known["tag_json"] and "hotend_min_c" in tag:
            conn.execute("UPDATE spools SET tag_json = ? WHERE id = ?", (json.dumps(tag), known["id"]))
        return {"kind": "known", "tag": tag, "spool": dict(known)}

    m = conn.execute("SELECT product_id FROM tag_map WHERE variant_id = ?",
                     (tag["variant_id"],)).fetchone()
    if m is None:  # the Bambu catalog knows the tag's variant id
        m = conn.execute("SELECT id AS product_id FROM products WHERE variant_id = ?",
                         (tag["variant_id"],)).fetchone()
    if m is None:
        return {"kind": "unmapped", "tag": tag, "candidates": candidates_for(conn, tag)}

    product_id = m["product_id"]
    if tag.get("color_rgba"):
        conn.execute("UPDATE products SET hex = ? WHERE id = ? AND hex IS NULL",
                     ("#" + tag["color_rgba"][:6], product_id))

    # An unscanned spool from the initial stock? Then link it (rod spool first).
    # (not one assigned by hand to an AMS slot: that one sits in the printer, not on the reader)
    seed = conn.execute(
        "SELECT id FROM spools WHERE product_id = ? AND tray_uid IS NULL AND status != 'empty' AND ams_slot IS NULL "
        "ORDER BY in_cabinet DESC, is_refill, id LIMIT 1", (product_id,)).fetchone()
    if seed is not None:
        _apply_tag(conn, seed["id"], tag)
        log(conn, seed["id"], "linked", f"Tag {tag['tray_uid'][:8]}")
        return {"kind": "linked", "tag": tag, "spool": get_spool(conn, seed["id"])}

    product = dict(conn.execute(
        "SELECT p.*, l.name AS line FROM products p JOIN lines l ON l.id = p.line_id "
        "WHERE p.id = ?", (product_id,)).fetchone())
    try:
        slot, in_cab = propose_slot(conn, product_id)
    except InventoryError as e:     # same color already on a rod and no reserve to put this one on
        return {"kind": "duplicate", "tag": tag, "product": product, "msg": str(e)}
    return {"kind": "new", "tag": tag, "product": product,
            "proposal": {"slot_id": slot, "in_cabinet": in_cab}}


def _apply_tag(conn: sqlite3.Connection, spool_id: int, tag: dict) -> None:
    conn.execute(
        "UPDATE spools SET tray_uid = ?, tag_uid = ?, weight_g = ?, production = ?, "
        "tag_json = COALESCE(?, tag_json), "
        "received_at = COALESCE(received_at, date('now', 'localtime')), "
        "updated_at = datetime('now', 'localtime') WHERE id = ?",
        (tag["tray_uid"], tag.get("uid"), tag.get("weight_g"), tag.get("production"),
         json.dumps(tag) if "hotend_min_c" in tag else None, spool_id))


def candidates_for(conn: sqlite3.Connection, tag: dict) -> list:
    """Products that might match the tag: same line first, unmapped ones first."""
    rows = conn.execute(
        "SELECT p.id, p.color_name, p.name_en, p.name_de, p.bambu_no, p.hex, l.name AS line, "
        "  (SELECT COUNT(*) FROM tag_map t WHERE t.product_id = p.id) AS mapped "
        "FROM products p JOIN lines l ON l.id = p.line_id "
        "ORDER BY (l.name = ?) DESC, mapped, l.name, p.bambu_no",
        (tag.get("detailed_type", ""),)).fetchall()
    return [dict(r) for r in rows]


def map_variant(conn: sqlite3.Connection, variant_id: str, product_id: int) -> None:
    conn.execute("INSERT OR REPLACE INTO tag_map (variant_id, product_id) VALUES (?, ?)",
                 (variant_id, product_id))
    log(conn, None, "assigned", f"{variant_id} -> product {product_id}")


def create_product(conn: sqlite3.Connection, line: str, color_name: str,
                   bambu_no: Optional[str], hex_color: Optional[str]) -> int:
    """Create a product (and its line if needed). Returns the product id."""
    from .db import ZONES, DEFAULT_ZONE
    conn.execute("INSERT OR IGNORE INTO lines (name, zone) VALUES (?, ?)",
                 (line, ZONES.get(line, DEFAULT_ZONE)))
    line_id = conn.execute("SELECT id FROM lines WHERE name = ?", (line,)).fetchone()["id"]
    cur = conn.execute("INSERT INTO products (line_id, color_name, name_de, name_en, bambu_no, hex) "
                       "VALUES (?, ?, ?, ?, ?, ?)",
                       (line_id, color_name, color_name, color_name, bambu_no or None, hex_color))
    return cur.lastrowid


def store_new(conn: sqlite3.Connection, tag: dict, product_id: int, slot_id: str,
              is_refill: bool = False, price: Optional[float] = None, manual: bool = False) -> dict:
    """Store a new (scanned) spool. manual: the user picked another slot than the suggested one."""
    if conn.execute("SELECT 1 FROM spools WHERE tray_uid = ?", (tag["tray_uid"],)).fetchone():
        raise InventoryError("This spool is already registered")
    in_cab = _check_target(conn, product_id, slot_id, None)
    cur = conn.execute(
        "INSERT INTO spools (product_id, is_refill, bought_refill, slot_id, in_cabinet, price, manual_place) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (product_id, 1 if is_refill else 0, 1 if is_refill else 0, slot_id, in_cab, price, 1 if manual else 0))
    _apply_tag(conn, cur.lastrowid, tag)
    log(conn, cur.lastrowid, "stored", slot_id)
    return get_spool(conn, cur.lastrowid)


def _check_target(conn: sqlite3.Connection, product_id: int, slot_id: str,
                  spool_id: Optional[int]) -> int:
    slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if slot is None:
        raise InventoryError(f"Slot {slot_id} doesn't exist")
    if slot["kind"] == "overflow":
        return 0
    holder = conn.execute("SELECT id FROM spools WHERE slot_id = ? AND in_cabinet = 1",
                          (slot_id,)).fetchone()
    if holder is not None and holder["id"] != spool_id:
        raise InventoryError(f"Slot {slot_id} is occupied")
    same = cabinet_spool(conn, product_id)
    if same is not None and same["id"] != spool_id:
        raise InventoryError(f"This filament is already in the cabinet ({same['slot_id']}). Further spools belong on the shelves.")
    return 1


# ---------------------------------------------------------------- actions

def take(conn: sqlite3.Connection, spool_id: int) -> dict:
    """Take a spool out for printing; it keeps its slot and is marked as in use."""
    s = get_spool(conn, spool_id)
    if s["status"] == "empty":
        raise InventoryError("Spool is marked as empty")
    conn.execute("UPDATE spools SET status = 'in_use', updated_at = datetime('now','localtime'), "
                 "opened_at = COALESCE(opened_at, date('now','localtime')) WHERE id = ?", (spool_id,))
    log(conn, spool_id, "taken_out", s["slot_id"] or "")
    return get_spool(conn, spool_id)


def put_back(conn: sqlite3.Connection, spool_id: int) -> dict:
    """Put a spool back into storage; spools without a slot get a new one."""
    s = get_spool(conn, spool_id)
    _unempty(s)
    if s["status"] == "empty" or s["slot_id"] is None:
        slot, in_cab = propose_slot(conn, s["product_id"])
        conn.execute("UPDATE spools SET slot_id = ?, in_cabinet = ? WHERE id = ?",
                     (slot, in_cab, spool_id))
    conn.execute("UPDATE spools SET status = 'stored', needs_return = 0, ams_slot = NULL, "
                 "updated_at = datetime('now','localtime') WHERE id = ?", (spool_id,))
    s = get_spool(conn, spool_id)
    log(conn, spool_id, "put_back", s["slot_id"])
    return s


def _unempty(s: dict) -> None:
    """A spool marked as empty by mistake comes back: the empty spool counted then is taken back (mark_empty)."""
    if s["status"] == "empty" and not s["is_refill"]:
        from . import settings
        settings.save({"empty_spools_delta": -1})


def mark_empty(conn: sqlite3.Connection, spool_id: int) -> dict:
    """Spool used up: its slot becomes free. Returns a successor suggestion from the reserve."""
    s = get_spool(conn, spool_id)
    freed = s["slot_id"] if s["in_cabinet"] else None
    conn.execute("UPDATE spools SET status = 'empty', in_cabinet = 0, slot_id = NULL, needs_return = 0, ams_slot = NULL, "
                 "updated_at = datetime('now','localtime') WHERE id = ?", (spool_id,))
    log(conn, spool_id, "empty", s["slot_id"] or "")
    conn.execute("UPDATE spools SET refill_ask = 0 WHERE id = ?", (spool_id,))
    if s["status"] != "empty" and (not s["is_refill"] or s["ams_slot"]):   # a loose refill has no spool to give back
        from . import settings
        settings.save({"empty_spools_delta": 1})   # the empty spool can now take a refill
    successor = None
    if freed:
        r = conn.execute(SPOOL_SELECT + " WHERE s.product_id = ? AND s.in_cabinet = 0 "
                         "AND s.status = 'stored' ORDER BY s.is_refill, s.id LIMIT 1",
                         (s["product_id"],)).fetchone()
        successor = _row(r)
    return {"spool": get_spool(conn, spool_id), "freed_slot": freed, "successor": successor}


def move(conn: sqlite3.Connection, spool_id: int, slot_id: str, manual: bool = False) -> dict:
    """Move a spool to another slot (the target must be free or a shelf). manual: the user picked the slot
    on purpose, so "Reorganize" does not suggest moving it away again."""
    s = get_spool(conn, spool_id)
    in_cab = _check_target(conn, s["product_id"], slot_id, spool_id)
    _unempty(s)
    conn.execute("UPDATE spools SET slot_id = ?, in_cabinet = ?, manual_place = ?, "
                 "status = CASE status WHEN 'empty' THEN 'stored' ELSE status END, "
                 "updated_at = datetime('now','localtime') WHERE id = ?",
                 (slot_id, in_cab, 1 if manual else 0, spool_id))
    log(conn, spool_id, "moved", f"{s['slot_id']} -> {slot_id}")
    return get_spool(conn, spool_id)


def update_spool(conn: sqlite3.Connection, spool_id: int, fields: dict) -> dict:
    allowed = {"is_refill", "note", "received_at", "opened_at"}
    if "is_refill" in fields:
        before = get_spool(conn, spool_id)["is_refill"]
        now = 1 if fields["is_refill"] else 0
        if now != before:
            conn.execute("UPDATE spools SET refill_ask = 0 WHERE id = ?", (spool_id,))
            # only the way back (refill now on an empty spool from the stock) uses up an empty spool,
            # and only when the user says so (asked in the browser)
            used = bool(not now and fields.get("used_empty_spool"))
            if used:
                from . import settings
                settings.save({"empty_spools_delta": -1})
            # in the history, so a changed count of empty spools can be traced back
            log(conn, spool_id, "refill_on" if now else "refill_off", "empty spools −1" if used else "")
    for k, v in fields.items():
        if k in allowed:
            conn.execute(f"UPDATE spools SET {k} = ? WHERE id = ?", (v, spool_id))
    return get_spool(conn, spool_id)


# ---------------------------------------------------------------- queries

def overview(conn: sqlite3.Connection) -> dict:
    """Everything the storage view needs: slots with their spools, counts and spools to put back."""
    slots = [dict(r) for r in conn.execute("SELECT * FROM slots ORDER BY kind, cabinet, row, pos")]
    spools = [dict(r) for r in conn.execute(SPOOL_SELECT + " WHERE s.status != 'empty' "
                                            "ORDER BY l.name, p.bambu_no")]
    used = last_used(conn)
    by_slot: dict = {}
    for sp in spools:
        sp["last_used"] = used.get(sp["id"])
        if sp["slot_id"]:
            by_slot.setdefault(sp["slot_id"], []).append(sp)
    for sl in slots:
        sl["spools"] = by_slot.get(sl["id"], [])
    stats = {
        "cabinet_slots": sum(1 for s in slots if s["kind"] == "cabinet"),
        "cabinet_used": sum(1 for s in spools if s["in_cabinet"]),
        "spools": len(spools),
        "overflow": sum(1 for s in spools if not s["in_cabinet"] and s["slot_id"]),
        "unscanned": sum(1 for s in spools if not s["tray_uid"]),
        "to_return": sum(1 for s in spools if s.get("needs_return")),
        "in_ams": sum(1 for s in spools if s.get("ams_slot")),
        "in_use": sum(1 for s in spools if s["status"] == "in_use"),
    }
    return {"slots": slots, "stats": stats}


def search(conn: sqlite3.Connection, q: str) -> dict:
    """Search by color, number, line or slot. Returns own spools and matching products not in stock."""
    like = f"%{q.strip()}%"
    match = ("(p.name_de LIKE ? OR p.name_en LIKE ? OR p.bambu_no LIKE ? OR l.name LIKE ? "
             "OR (l.name || ' ' || p.name_de) LIKE ? OR (l.name || ' ' || p.name_en) LIKE ?)")
    spools = [dict(r) for r in conn.execute(
        SPOOL_SELECT + f" WHERE s.status != 'empty' AND ({match} OR s.slot_id LIKE ?) "
        "ORDER BY s.in_cabinet DESC, l.name, p.bambu_no", (like,) * 7)]
    missing = [dict(r) for r in conn.execute(
        "SELECT p.*, l.name AS line FROM products p JOIN lines l ON l.id = p.line_id "
        f"WHERE {match} AND NOT EXISTS (SELECT 1 FROM spools s WHERE s.product_id = p.id "
        "AND s.status != 'empty') ORDER BY l.name, p.bambu_no LIMIT 30", (like,) * 6)]
    return {"spools": spools, "missing": missing}


def catalog(conn: sqlite3.Connection) -> list:
    """All lines with all colors and the user's stock for each."""
    rows = conn.execute(
        "SELECT p.id, p.bambu_no, p.name_en, p.name_de, p.color_name, p.hex, p.colors, p.kind, "
        "  p.in_catalog, p.discontinued, l.name AS line, l.shop_url, l.brand, "
        "  (SELECT COUNT(*) FROM spools s WHERE s.product_id = p.id AND s.status != 'empty') AS owned, "
        "  (SELECT slot_id FROM spools s WHERE s.product_id = p.id AND s.in_cabinet = 1) AS cabinet_slot, "
        "  EXISTS (SELECT 1 FROM spools s WHERE s.product_id = p.id) AS ever "      # had a spool once: default minimum applies
        "FROM products p JOIN lines l ON l.id = p.line_id WHERE COALESCE(l.brand, '') = '' "   # Bambu Lab lines only
        "ORDER BY l.name, p.bambu_no").fetchall()
    lines: dict = {}
    for r in rows:
        lines.setdefault(r["line"], []).append(dict(r))
    out = []
    for name, products in lines.items():
        # colours Bambu Lab no longer sells do not count as missing (only shown when switched on in the options)
        active = [p for p in products if not p["discontinued"]]
        owned = sum(1 for p in active if p["owned"])
        out.append({"line": name, "total": len(active), "owned": owned,
                    "complete": owned == len(active), "products": products})
    out.sort(key=lambda x: (-x["owned"], x["line"]))
    return out


def lines_summary(conn: sqlite3.Connection) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT l.*, COUNT(DISTINCT p.id) AS products, "
        "  SUM(CASE WHEN s.status != 'empty' THEN 1 ELSE 0 END) AS spools "
        "FROM lines l LEFT JOIN products p ON p.line_id = l.id "
        "LEFT JOIN spools s ON s.product_id = p.id GROUP BY l.id ORDER BY l.name")]


def recent_events(conn: sqlite3.Connection, limit: int = 30) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT e.*, p.color_name, p.name_en, p.name_de, p.hex, p.colors, s.is_refill, l.name AS line FROM events e "
        "LEFT JOIN spools s ON s.id = e.spool_id LEFT JOIN products p ON p.id = s.product_id "
        "LEFT JOIN lines l ON l.id = p.line_id ORDER BY e.id DESC LIMIT ?", (limit,))]


# ---------------------------------------------------------------- reset, bulk inventory

RESET_WORD = "RESET"


def reset_storage(conn: sqlite3.Connection) -> int:
    """Remove all spools. Catalog, tag mappings and slots stay."""
    n = conn.execute("SELECT COUNT(*) FROM spools").fetchone()[0]
    conn.execute("UPDATE events SET spool_id = NULL")
    conn.execute("DELETE FROM spools")
    log(conn, None, "reset", f"{n} spools removed")
    return n


def batch_preview(conn: sqlite3.Connection, tag: dict) -> dict:
    """Like handle_scan but without changing anything (for the bulk inventory list)."""
    conn.execute("SAVEPOINT preview")
    try:
        r = handle_scan(conn, tag)
    finally:
        conn.execute("ROLLBACK TO preview")
        conn.execute("RELEASE preview")
    return r


def batch_commit(conn: sqlite3.Connection, tags: list, reserve: bool = False) -> list:
    """Store all collected spools, sorted by line and number so neighbours on the rods match.
    reserve: all new spools go to the reserve of their storage instead of a slot.
    Returns the placement list sorted by slot."""
    results = []
    previews = [(t, batch_preview(conn, t)) for t in tags]

    def order(item):
        r = item[1]
        prod = r.get("product") or r.get("spool") or {}
        return db.sort_key(prod.get("line") or "", prod.get("bambu_no"))

    for tag, _ in sorted(previews, key=order):
        r = handle_scan(conn, tag)
        if r["kind"] == "new":
            if reserve:
                slot = reserve_slot(conn, db.home_cabinet(r["product"].get("line") or _line_of(conn, r["product"]["id"])))
            else:
                slot, _cab = propose_slot(conn, r["product"]["id"])
            spool = store_new(conn, tag, r["product"]["id"], slot)
            results.append({"action": "new", "spool": spool})
        elif r["kind"] == "duplicate":
            results.append({"action": "duplicate", "tag": tag, "product": r["product"]})
        elif r["kind"] in ("linked", "known"):
            results.append({"action": "linked" if r["kind"] == "linked" else "known", "spool": r["spool"]})
        else:
            results.append({"action": "unknown", "tag": tag})

    def place(x):
        sid = (x.get("spool") or {}).get("slot_id") or "ZZZ"
        s = conn.execute("SELECT kind, cabinet, row, pos FROM slots WHERE id = ?", (sid,)).fetchone()
        return (0, s["cabinet"], s["row"], s["pos"]) if s and s["kind"] == "cabinet" else \
               (1, s["cabinet"], s["row"], 0) if s else (2, "", 0, 0)
    results.sort(key=place)
    return results


def _hex_dist(a: str, b: str) -> int:
    try:
        x, y = bytes.fromhex(a.lstrip("#")[:6]), bytes.fromhex(b.lstrip("#")[:6])
    except (ValueError, AttributeError):
        return 10 ** 6
    if len(x) != 3 or len(y) != 3:
        return 10 ** 6
    return sum((i - j) ** 2 for i, j in zip(x, y))


def ams_products(conn: sqlite3.Connection, tray: dict) -> list:
    """Products matching an AMS spool exactly (same Bambu material id and color)."""
    hexc = (tray.get("color") or "")[:7].lower()
    return [r["id"] for r in conn.execute(
        "SELECT p.id FROM products p WHERE p.material_id = ? AND lower(p.hex) = ? ORDER BY p.in_catalog DESC, p.id",
        (tray.get("filament_id"), hexc)).fetchall()]


def ams_candidates(conn: sqlite3.Connection, tray: dict, limit: int = 30) -> list:
    """Products to pick from when the AMS color is not in the catalog: same material first, then by color."""
    hexc = (tray.get("color") or "")[:7].lower()
    rows = [dict(r) for r in conn.execute(
        "SELECT p.id, p.color_name, p.name_en, p.name_de, p.bambu_no, p.hex, p.material_id, l.name AS line "
        "FROM products p JOIN lines l ON l.id = p.line_id WHERE p.in_catalog = 1 OR EXISTS "
        "(SELECT 1 FROM spools s WHERE s.product_id = p.id)").fetchall()]
    same = tray.get("filament_id") or ""
    typ = (tray.get("type") or "").upper()
    for r in rows:
        r["same"] = bool(same) and r["material_id"] == same
        r["dist"] = _hex_dist(r["hex"] or "", hexc)
    # nothing with the same material id: fall back to lines named like the AMS type (e.g. "PLA")
    if not any(r["same"] for r in rows) and typ:
        for r in rows:
            r["same"] = (r["line"] or "").upper().split(" ")[0] == typ.split(" ")[0]
    rows.sort(key=lambda r: (not r["same"], r["dist"]))
    return [{k: r[k] for k in ("id", "color_name", "name_en", "name_de", "bambu_no", "hex", "line", "same")}
            for r in rows[:limit]]


def adopt_ams(conn: sqlite3.Connection, tray: dict, product_id: Optional[int] = None) -> dict:
    """Take over a spool that sits in the AMS without scanning it (the AMS has read its Bambu tag).

    An unscanned spool of the same color already in storage is linked (no second spool). Otherwise a new spool
    is added with a storage slot. product_id: chosen by the user when the color is not in the catalog."""
    uuid = (tray.get("tray_uuid") or "").upper()
    if not uuid:
        raise InventoryError("There is no spool with a Bambu tag in this AMS slot")
    if conn.execute("SELECT 1 FROM spools WHERE tray_uid = ?", (uuid,)).fetchone():
        raise InventoryError("This spool is already in storage")
    if product_id is None:
        prods = ams_products(conn, tray)
        if not prods:
            hexc = (tray.get("color") or "")[:7].lower()
            raise InventoryError(f"Color {hexc} ({tray.get('label') or tray.get('type')}) not found in the catalog")
        product_id = prods[0]
    elif conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone() is None:
        raise InventoryError("Color not found")
    try:
        weight = int(float(tray.get("tray_weight") or 0)) or None
    except ValueError:
        weight = None
    tag = {"tray_uid": uuid, "uid": (tray.get("tag_uid") or "")[:8].upper() or None, "weight_g": weight, "production": None}
    # an unscanned spool of this color (added by hand or from the initial stock): link it, rod spool first
    seed = conn.execute(
        "SELECT id FROM spools WHERE product_id = ? AND tray_uid IS NULL AND status != 'empty' AND ams_slot IS NULL "
        "ORDER BY in_cabinet DESC, (opened_at IS NOT NULL) DESC, is_refill, id LIMIT 1", (product_id,)).fetchone()
    if seed is not None:
        sid = seed["id"]
        _apply_tag(conn, sid, tag)
        if not conn.execute("SELECT slot_id FROM spools WHERE id = ?", (sid,)).fetchone()["slot_id"]:
            slot, in_cab = propose_slot(conn, product_id)
            conn.execute("UPDATE spools SET slot_id = ?, in_cabinet = ? WHERE id = ?", (slot, in_cab, sid))
        log(conn, sid, "linked", f"Tag {uuid[:8]}")
        linked = True
    else:
        slot, in_cab = propose_slot(conn, product_id)
        cur = conn.execute("INSERT INTO spools (product_id, slot_id, in_cabinet) VALUES (?, ?, ?)",
                           (product_id, slot, in_cab))
        sid = cur.lastrowid
        _apply_tag(conn, sid, tag)
        log(conn, sid, "stored", f"{slot} (taken over from AMS)")
        linked = False
    remain = tray.get("remain")
    conn.execute("UPDATE spools SET status = 'in_use', ams_slot = ?, printer_id = ?, needs_return = 0, "
                 "opened_at = COALESCE(opened_at, date('now','localtime')), "
                 "remain_pct = COALESCE(?, remain_pct) WHERE id = ?",
                 (tray.get("name"), tray.get("printer") or "p1",
                  remain if isinstance(remain, (int, float)) and remain >= 0 else None, sid))
    if not linked:
        sib = cabinet_sibling(conn, sid)
        if sib and not sib["opened_at"] and sib["status"] == "stored":
            swap_with_cabinet(conn, sid)
    log(conn, sid, "to_ams", tray.get("name") or "")
    conn.execute("UPDATE spools SET refill_ask = 1 WHERE id = ? AND is_refill = 1", (sid,))
    return {**get_spool(conn, sid), "linked": linked}


def _no_tag_tray(tray: dict) -> bool:
    """An occupied AMS slot or external holder whose spool has no Bambu tag (the printer only knows the material
    set by hand). An AMS slot also counts when the AMS reports a spool but no material is set for it."""
    typ = (tray.get("type") or "").strip()
    name = str(tray.get("name") or "")
    if tray.get("tray_uuid") or not (name.startswith("AMS ") or name.startswith("External spool")):
        return False
    return (bool(typ) and typ.lower() != "empty") or (name.startswith("AMS ") and tray.get("occupied") is True)


def assign_candidates(conn: sqlite3.Connection, tray: dict) -> list:
    """Spools from storage that may sit in this AMS slot: not empty, not in an AMS. Spools without a Bambu tag first,
    then the same material (AMS type vs. line name), then the closest color."""
    hexc = (tray.get("color") or "")[:7].lower()
    typ = (tray.get("type") or "").upper().split(" ")[0]
    rows = [dict(r) for r in conn.execute(
        SPOOL_SELECT + " WHERE s.status != 'empty' AND s.ams_slot IS NULL").fetchall()]
    for r in rows:
        uid = r["tray_uid"] or ""
        r["chip"] = bool(uid) and not uid.startswith("NFC-")
        r["same"] = bool(typ) and typ in (r["line"] or "").upper().replace("-", " ").split(" ")
        r["dist"] = _hex_dist(r["hex"] or "", hexc)
    rows.sort(key=lambda r: (r["chip"], not r["same"], r["dist"], r["id"]))
    return [{k: r[k] for k in ("id", "line", "brand", "color_name", "name_en", "name_de", "hex", "colors", "slot_id",
                               "remain_pct", "status", "tray_uid", "same", "chip", "opened_at", "weight_g", "net_g")}
            for r in rows]


def assign_ams(conn: sqlite3.Connection, tray: dict, spool_id: int) -> dict:
    """Experimental: tell PixxelSpool which stored spool sits in an AMS slot without a Bambu tag. The spool then counts
    as in the AMS (its storage slot stays reserved) until the slot is empty again; finished prints use it up."""
    if not _no_tag_tray(tray):
        raise InventoryError("Only a spool without a Bambu tag in an AMS slot can be assigned")
    pid = tray.get("printer") or "p1"
    if conn.execute("SELECT 1 FROM spools WHERE ams_slot = ? AND printer_id = ? AND ams_bound = 1",
                    (tray["name"], pid)).fetchone():
        raise InventoryError("A spool is already assigned to this AMS slot")
    s = get_spool(conn, spool_id)
    if s["status"] == "empty":
        raise InventoryError("Spool is marked as empty")
    if s["ams_slot"]:
        raise InventoryError("This spool is already in the AMS")
    conn.execute("UPDATE spools SET ams_prev = CASE WHEN needs_return = 1 THEN 'return' ELSE status END, status = 'in_use', ams_slot = ?, printer_id = ?, ams_bound = 1, "
                 "needs_return = 0, updated_at = datetime('now','localtime') WHERE id = ?", (tray["name"], pid, spool_id))
    if s["slot_id"] is None:
        slot, in_cab = propose_slot(conn, s["product_id"])
        conn.execute("UPDATE spools SET slot_id = ?, in_cabinet = ? WHERE id = ?", (slot, in_cab, spool_id))
    log(conn, spool_id, "to_ams", tray["name"])
    return get_spool(conn, spool_id)


def unassign_ams(conn: sqlite3.Connection, spool_id: int) -> dict:
    """Undo a wrong assignment: the spool is back where it was before, no "put back" reminder."""
    s = get_spool(conn, spool_id)
    if not s["ams_bound"] or not s["ams_slot"]:
        raise InventoryError("This spool was not assigned by hand")
    prev = s["ams_prev"] if s["ams_prev"] in ("stored", "in_use", "return") else "stored"
    conn.execute("UPDATE spools SET status = ?, ams_slot = NULL, printer_id = NULL, needs_return = ?, "
                 "updated_at = datetime('now','localtime') WHERE id = ?",
                 ("in_use" if prev == "return" else prev, 1 if prev == "return" else 0, spool_id))
    log(conn, spool_id, "from_ams", "assignment undone")
    return get_spool(conn, spool_id)


def use_grams(conn: sqlite3.Connection, spool_id: int, grams: float) -> None:
    """A print used this many grams of a spool the AMS can't measure (no Bambu tag): lower its remaining percent.
    Unknown remaining amount counts as a full spool, like in the statistics."""
    s = get_spool(conn, spool_id)
    if grams <= 0 or s["status"] == "empty":
        return
    net = float(s["weight_g"] or s["net_g"] or 1000)
    base = float(s["remain_pct"]) if s["remain_pct"] is not None else 100.0
    pct = round(max(0.0, base - grams * 100 / net), 1)
    conn.execute("UPDATE spools SET remain_pct = ?, opened_at = COALESCE(opened_at, date('now','localtime')), "
                 "updated_at = datetime('now','localtime') WHERE id = ?", (pct, spool_id))
    conn.execute("INSERT INTO usage (spool_id, remain_pct) VALUES (?, ?)", (spool_id, pct))


def refill_on_spool(conn: sqlite3.Connection, spool_id: int, used_empty_spool: bool) -> dict:
    """A refill was found in the AMS, so it now sits on a spool: it is no longer a refill. used_empty_spool:
    the user took that spool from the stock of empty spools (counter −1)."""
    s = get_spool(conn, spool_id)
    conn.execute("UPDATE spools SET refill_ask = 0, is_refill = 0 WHERE id = ?", (spool_id,))
    if s["is_refill"]:
        if used_empty_spool:
            from . import settings
            settings.save({"empty_spools_delta": -1})
        log(conn, spool_id, "refill_off", "empty spools −1" if used_empty_spool else "")
    return get_spool(conn, spool_id)


def cabinet_sibling(conn: sqlite3.Connection, spool_id: int) -> Optional[dict]:
    s = get_spool(conn, spool_id)
    if s["in_cabinet"] or s["status"] == "empty":
        return None
    return _row(conn.execute(SPOOL_SELECT + " WHERE s.product_id = ? AND s.in_cabinet = 1 AND s.id != ?",
                             (s["product_id"], spool_id)).fetchone())


def swap_with_cabinet(conn: sqlite3.Connection, spool_id: int) -> dict:
    """Put this spool on the rod and the current rod spool of the same color in its place (e.g. the shelf)."""
    s = get_spool(conn, spool_id)
    other = cabinet_sibling(conn, spool_id)
    if other is None:
        raise InventoryError("No spool of the same color on a rod")
    cab_slot, my_slot = other["slot_id"], s["slot_id"] or default_overflow(conn)
    conn.execute("UPDATE spools SET slot_id = ?, in_cabinet = 0, updated_at = datetime('now','localtime') WHERE id = ?",
                 (my_slot, other["id"]))
    conn.execute("UPDATE spools SET slot_id = ?, in_cabinet = 1, updated_at = datetime('now','localtime') WHERE id = ?",
                 (cab_slot, spool_id))
    log(conn, spool_id, "swapped", f"{my_slot} -> {cab_slot}")
    log(conn, other["id"], "swapped", f"{cab_slot} -> {my_slot}")
    return {"spool": get_spool(conn, spool_id), "other": get_spool(conn, other["id"])}


def swap_spools(conn: sqlite3.Connection, spool_id: int, other_id: int) -> dict:
    """Exchange the places of two spools (moving a spool onto an occupied rod slot)."""
    a, b = get_spool(conn, spool_id), get_spool(conn, other_id)
    if a["id"] == b["id"] or not b["slot_id"]:
        raise InventoryError("Swapping only works with another spool in a place")
    a_slot, b_slot = a["slot_id"] or default_overflow(conn), b["slot_id"]
    if a_slot == b_slot:
        raise InventoryError("Both spools are already in the same place")
    kind = {r["id"]: r["kind"] for r in conn.execute("SELECT id, kind FROM slots WHERE id IN (?, ?)", (a_slot, b_slot))}
    for sp, slot in ((a, b_slot), (b, a_slot)):
        if kind.get(slot) == "cabinet":        # one rod spool per filament: a third spool of that color blocks it
            same = cabinet_spool(conn, sp["product_id"])
            if same is not None and same["id"] not in (a["id"], b["id"]):
                raise InventoryError(f"This filament is already in the cabinet ({same['slot_id']}). Further spools belong on the shelves.")
    # rod slots are unique: free the first one before the two spools change places
    conn.execute("UPDATE spools SET slot_id = NULL, in_cabinet = 0 WHERE id = ?", (a["id"],))
    for sp, slot in ((b, a_slot), (a, b_slot)):
        conn.execute("UPDATE spools SET slot_id = ?, in_cabinet = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                     (slot, 1 if kind.get(slot) == "cabinet" else 0, sp["id"]))
    log(conn, a["id"], "swapped", f"{a_slot} -> {b_slot}")
    log(conn, b["id"], "swapped", f"{b_slot} -> {a_slot}")
    return {"spool": get_spool(conn, a["id"]), "other": get_spool(conn, b["id"])}


def delete_spool(conn: sqlite3.Connection, spool_id: int) -> None:
    """Delete a spool completely (e.g. added by mistake). History entries are kept as text."""
    s = get_spool(conn, spool_id)
    conn.execute("DELETE FROM usage WHERE spool_id = ?", (spool_id,))
    conn.execute("UPDATE events SET spool_id = NULL WHERE spool_id = ?", (spool_id,))
    conn.execute("DELETE FROM spools WHERE id = ?", (spool_id,))
    log(conn, None, "deleted", f"{s['line']} {s.get('color_name') or ''} ({s['slot_id'] or '–'})".strip())


BULK_ACTIONS = ("price", "empty", "reserve", "dried", "delete")


def bulk(conn: sqlite3.Connection, ids: list, action: str, price=None) -> dict:
    """Apply one action to several spools. Spools where it is not possible are skipped and reported."""
    if action not in BULK_ACTIONS:
        raise InventoryError("Unknown action")
    if action == "price":
        from .brands import _price
        price = _price(price)
    done, skipped = 0, []
    undo = []           # what the action overwrote, so it can be taken back (price, dried, reserve)
    first_event = conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]
    for sid in dict.fromkeys(int(i) for i in ids or []):
        try:
            if action in ("price", "dried", "reserve"):
                before = get_spool(conn, sid)
                undo.append({"id": sid, "price": before.get("price"), "dried_at": before.get("dried_at"),
                             "slot_id": before.get("slot_id"), "in_cabinet": before.get("in_cabinet")})
            if action == "price":
                get_spool(conn, sid)
                conn.execute("UPDATE spools SET price = ? WHERE id = ?", (price, sid))
            elif action == "empty":
                mark_empty(conn, sid)
            elif action == "reserve":
                to_reserve(conn, sid)
            elif action == "dried":
                get_spool(conn, sid)
                conn.execute("UPDATE spools SET dried_at = date('now','localtime') WHERE id = ?", (sid,))
                log(conn, sid, "dried", "")
            elif action == "delete":
                delete_spool(conn, sid)
            done += 1
        except InventoryError as e:
            if undo and undo[-1]["id"] == sid:
                undo.pop()
            skipped.append({"id": sid, "error": str(e)})
    return {"done": done, "skipped": skipped, "undo": {"action": action, "items": undo, "after_event": first_event} if undo else None}


def bulk_undo(conn: sqlite3.Connection, data: dict) -> dict:
    """Take back the last bulk action: restore price / drying date, or move spools back from the reserve
    onto their rod if it is still free. The history entries the action wrote are removed again."""
    action, items, after = data["action"], data["items"], int(data.get("after_event") or 0)
    done, skipped = 0, []
    for it in items:
        sid = int(it["id"])
        if action == "price":
            conn.execute("UPDATE spools SET price = ? WHERE id = ?", (it["price"], sid))
        elif action == "dried":
            conn.execute("UPDATE spools SET dried_at = ? WHERE id = ?", (it["dried_at"], sid))
            conn.execute("DELETE FROM events WHERE id > ? AND spool_id = ? AND action = 'dried'", (after, sid))
        elif action == "reserve":
            busy = conn.execute("SELECT 1 FROM spools WHERE slot_id = ? AND in_cabinet = 1 AND id != ? AND status != 'empty'",
                                (it["slot_id"], sid)).fetchone()
            if busy:
                skipped.append({"id": sid, "error": "The place has been taken in the meantime"})
                continue
            conn.execute("UPDATE spools SET slot_id = ?, in_cabinet = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                         (it["slot_id"], it["in_cabinet"], sid))
            conn.execute("DELETE FROM events WHERE id > ? AND spool_id = ? AND action = 'to_reserve'", (after, sid))
        done += 1
    return {"done": done, "skipped": skipped}


def to_reserve(conn: sqlite3.Connection, spool_id: int) -> dict:
    """Move a spool from its rod to its cabinet's shelf (reserve); the rod slot becomes free."""
    s = get_spool(conn, spool_id)
    if not s["in_cabinet"]:
        raise InventoryError("Spool is already in the reserve")
    target = reserve_slot(conn, db.home_cabinet(s['line']))
    conn.execute("UPDATE spools SET slot_id = ?, in_cabinet = 0, updated_at = datetime('now','localtime') WHERE id = ?",
                 (target, spool_id))
    log(conn, spool_id, "to_reserve", f"{s['slot_id']} -> {target}")
    return {"spool": get_spool(conn, spool_id), "freed": s["slot_id"]}


def to_live(conn: sqlite3.Connection, spool_id: int) -> dict:
    """Move a spool from the reserve onto a rod: swaps with the same color or takes a free slot."""
    s = get_spool(conn, spool_id)
    if s["in_cabinet"]:
        raise InventoryError("Spool is already on a rod")
    if cabinet_sibling(conn, spool_id):
        return swap_with_cabinet(conn, spool_id)
    slot, in_cab = propose_slot(conn, s["product_id"])
    if not in_cab:
        raise InventoryError("No free rod found")
    conn.execute("UPDATE spools SET slot_id = ?, in_cabinet = 1, updated_at = datetime('now','localtime') WHERE id = ?",
                 (slot, spool_id))
    log(conn, spool_id, "to_live", f"{s['slot_id']} -> {slot}")
    return {"spool": get_spool(conn, spool_id), "other": None}


def add_manual(conn: sqlite3.Connection, product_id: int, reserve: bool = False, price: Optional[float] = None) -> dict:
    """Add a spool without scanning (e.g. still sealed in foil). When it is scanned later, handle_scan links
    the tag to it instead of creating a duplicate."""
    line = _line_of(conn, product_id)
    slot, in_cab = (reserve_slot(conn, db.home_cabinet(line)), 0) if reserve else propose_slot(conn, product_id)
    cur = conn.execute("INSERT INTO spools (product_id, slot_id, in_cabinet, note, received_at, price) "
                       "VALUES (?, ?, ?, 'manuell erfasst', date('now','localtime'), ?)", (product_id, slot, in_cab, price))
    log(conn, cur.lastrowid, "stored", f"{slot} (manual, not scanned yet)")
    return get_spool(conn, cur.lastrowid)


# ------------------------------------------------------------------ retrofitted tags (NTAG stickers)

def unlinked_spools(conn: sqlite3.Connection) -> list:
    """Spools without a tag that can get a sticker."""
    return [dict(r) for r in conn.execute(
        SPOOL_SELECT + " WHERE s.tray_uid IS NULL AND s.status != 'empty' ORDER BY l.name, p.color_name, s.id")]


def plain_scan(conn: sqlite3.Connection, tag: dict) -> dict:
    known = conn.execute(SPOOL_SELECT + " WHERE s.tray_uid = ?", (tag["tray_uid"],)).fetchone()
    if known is not None:
        return {"kind": "known", "tag": None, "spool": dict(known)}
    return {"kind": "plain", "tag": tag, "unlinked": unlinked_spools(conn)}


def link_plain(conn: sqlite3.Connection, spool_id: int, tag: dict) -> dict:
    """Link a retrofitted sticker (NFC-<UID>) to a spool without a tag."""
    uid = str(tag.get("uid") or "").upper()
    if not uid or not re.fullmatch(r"[0-9A-F]{8,20}", uid) or tag.get("tray_uid") != "NFC-" + uid:
        raise InventoryError("Invalid tag")
    sp = get_spool(conn, spool_id)
    if sp["tray_uid"]:
        raise InventoryError("This spool already has a tag")
    other = conn.execute("SELECT id FROM spools WHERE tray_uid = ?", (tag["tray_uid"],)).fetchone()
    if other is not None:
        raise InventoryError("This tag already belongs to another spool")
    conn.execute("UPDATE spools SET tray_uid = ?, tag_uid = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
                 (tag["tray_uid"], uid, spool_id))
    log(conn, spool_id, "linked", f"Tag {uid[:8]}")
    return get_spool(conn, spool_id)


def unlink_plain(conn: sqlite3.Connection, spool_id: int) -> dict:
    """Release a retrofitted sticker from its spool (Bambu tags cannot be released)."""
    sp = get_spool(conn, spool_id)
    if not str(sp["tray_uid"] or "").startswith("NFC-"):
        raise InventoryError("Only added sticker tags can be removed")
    conn.execute("UPDATE spools SET tray_uid = NULL, tag_uid = NULL, updated_at = datetime('now', 'localtime') WHERE id = ?",
                 (spool_id,))
    log(conn, spool_id, "tag_released", sp["tray_uid"][4:12])
    return get_spool(conn, spool_id)

