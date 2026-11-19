"""Custom brands and colors (filament from other makers), weights, prices and weighing.

A custom line is a normal row in `lines` with `brand` set. Its name is built from brand, material and an optional
suffix ("Sunlu PETG", "eSun PLA+ Silk") so sorting, the dry zone and search work like for Bambu lines.
Colors are rows in `products` without a Bambu number.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Optional

from . import db, settings
from .logic import InventoryError, get_spool, log

MATERIALS = ["PLA", "PLA+", "PETG", "ABS", "ASA", "TPU", "PA", "PC", "PVA", "HIPS", "Other"]
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
BAMBU_SPOOL_G = 250        # empty weight of a Bambu plastic spool (approximate)
DEFAULT_NET_G = 1000


def _int(v, lo: int, hi: int) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        raise InventoryError("Please enter a number")
    if not lo <= n <= hi:
        raise InventoryError("Value out of range")
    return n


def _price(v) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        n = round(float(str(v).replace(",", ".")), 2)
    except ValueError:
        raise InventoryError("Please enter a price like 19.99")
    if not 0 <= n <= 10000:
        raise InventoryError("Value out of range")
    return n


def _text(v, maxlen: int = 40) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:maxlen]


# ------------------------------------------------------------------ lines and colors

def custom_lines(conn: sqlite3.Connection) -> list:
    out = []
    for r in conn.execute("SELECT * FROM lines WHERE brand IS NOT NULL ORDER BY brand, name"):
        ln = dict(r)
        ln["colors"] = [dict(c) for c in conn.execute(
            "SELECT p.id, p.color_name, p.hex, p.sku, "
            "  (SELECT COUNT(*) FROM spools s WHERE s.product_id = p.id) AS spools "
            "FROM products p WHERE p.line_id = ? ORDER BY p.color_name", (ln["id"],))]
        out.append(ln)
    return out


def save_line(conn: sqlite3.Connection, data: dict) -> dict:
    """Create or update a custom line (data["id"] set = update). Returns the saved row."""
    brand = _text(data.get("brand"), 30)
    mat = _text(data.get("material"), 12)
    extra = _text(data.get("extra"), 30)
    if not brand:
        raise InventoryError("Please enter the brand")
    if brand.lower().startswith("bambu"):
        raise InventoryError("Bambu Lab lines are already in the catalog")
    if mat not in MATERIALS:
        raise InventoryError("Please choose a material")
    name = " ".join(x for x in (brand, mat, extra) if x)
    vals = {
        "brand": brand, "name": name,
        "spool_g": _int(data.get("spool_g"), 0, 1500), "net_g": _int(data.get("net_g"), 100, 10000),
        "price": _price(data.get("price")), "dry_temp": _int(data.get("dry_temp"), 30, 120),
        "dry_hours": _int(data.get("dry_hours"), 1, 48), "shop_url": _text(data.get("shop_url"), 300) or None,
    }
    if vals["shop_url"] and not re.match(r"^https?://", vals["shop_url"]):
        raise InventoryError("Shop link must start with http:// or https://")
    lid = data.get("id")
    clash = conn.execute("SELECT id FROM lines WHERE name = ? AND id IS NOT ?", (name, lid)).fetchone()
    if clash:
        raise InventoryError("This line already exists")
    if lid:
        if not conn.execute("SELECT 1 FROM lines WHERE id = ? AND brand IS NOT NULL", (lid,)).fetchone():
            raise InventoryError("Line not found")
        conn.execute("UPDATE lines SET brand=:brand, name=:name, spool_g=:spool_g, net_g=:net_g, price=:price, "
                     "dry_temp=:dry_temp, dry_hours=:dry_hours, shop_url=:shop_url WHERE id=:id", {**vals, "id": lid})
    else:
        cur = conn.execute("INSERT INTO lines (brand, name, spool_g, net_g, price, dry_temp, dry_hours, shop_url, zone) "
                           "VALUES (:brand, :name, :spool_g, :net_g, :price, :dry_temp, :dry_hours, :shop_url, :zone)",
                           {**vals, "zone": db.DEFAULT_ZONE})
        lid = cur.lastrowid
    return dict(conn.execute("SELECT * FROM lines WHERE id = ?", (lid,)).fetchone())


def delete_line(conn: sqlite3.Connection, line_id: int) -> None:
    if not conn.execute("SELECT 1 FROM lines WHERE id = ? AND brand IS NOT NULL", (line_id,)).fetchone():
        raise InventoryError("Line not found")
    if conn.execute("SELECT 1 FROM spools s JOIN products p ON p.id = s.product_id WHERE p.line_id = ?",
                    (line_id,)).fetchone():
        raise InventoryError("There are still spools of this line")
    conn.execute("DELETE FROM products WHERE line_id = ?", (line_id,))
    conn.execute("DELETE FROM lines WHERE id = ?", (line_id,))


def save_color(conn: sqlite3.Connection, data: dict) -> dict:
    """Create (with line_id) or update (with id) a color of a custom line. Returns the product row."""
    name = _text(data.get("name"), 40)
    hexv = str(data.get("hex") or "").strip()
    sku = _text(data.get("sku"), 40) or None
    if not name:
        raise InventoryError("Please enter a color name")
    if hexv and not HEX.match(hexv):
        raise InventoryError("Invalid color")
    pid = data.get("id")
    if pid:
        row = conn.execute("SELECT p.line_id FROM products p JOIN lines l ON l.id = p.line_id "
                           "WHERE p.id = ? AND l.brand IS NOT NULL", (pid,)).fetchone()
        if not row:
            raise InventoryError("Color not found")
        conn.execute("UPDATE products SET color_name = ?, name_de = ?, name_en = ?, hex = ?, sku = ? WHERE id = ?",
                     (name, name, name, hexv or None, sku, pid))
    else:
        lid = data.get("line_id")
        if not conn.execute("SELECT 1 FROM lines WHERE id = ? AND brand IS NOT NULL", (lid,)).fetchone():
            raise InventoryError("Line not found")
        if conn.execute("SELECT 1 FROM products WHERE line_id = ? AND color_name = ?", (lid, name)).fetchone():
            raise InventoryError("This color already exists in the line")
        cur = conn.execute("INSERT INTO products (line_id, color_name, name_de, name_en, hex, sku, in_catalog) "
                           "VALUES (?, ?, ?, ?, ?, ?, 0)", (lid, name, name, name, hexv or None, sku))
        pid = cur.lastrowid
    return dict(conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone())


def delete_color(conn: sqlite3.Connection, product_id: int) -> None:
    row = conn.execute("SELECT 1 FROM products p JOIN lines l ON l.id = p.line_id WHERE p.id = ? AND l.brand IS NOT NULL",
                       (product_id,)).fetchone()
    if not row:
        raise InventoryError("Color not found")
    if conn.execute("SELECT 1 FROM spools WHERE product_id = ?", (product_id,)).fetchone():
        raise InventoryError("There are still spools of this color")
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))


# ------------------------------------------------------------------ prices for all lines (Bambu too)

def price_list(conn: sqlite3.Connection) -> list:
    """Lines that have (or had) spools, with estimated price, average price paid and weights."""
    return [dict(r) for r in conn.execute(
        "SELECT l.id, l.name, l.brand, l.price, l.net_g, l.spool_g, COUNT(s.id) AS spools, "
        "  ROUND(AVG(s.price), 2) AS avg_paid, COUNT(s.price) AS paid "
        "FROM lines l JOIN products p ON p.line_id = l.id JOIN spools s ON s.product_id = p.id "
        "GROUP BY l.id ORDER BY l.brand IS NOT NULL, l.name")]


# Standard prices of Bambu Lab lines: one spool (1 kg with spool) in the Bambu Lab EU store, euro incl. German VAT,
# as of SHOP_PRICES_AS_OF. Filled in once for lines without a price; users change them under Statistics.
SHOP_PRICES_AS_OF = "2026-11"
SHOP_PRICES = {
    "PLA Basic": 25.99, "PLA Matte": 25.99, "PETG HF": 25.99, "PETG Translucent": 25.99, "ABS": 25.99,
    "PLA Silk+": 25.99, "PLA Translucent": 27.99, "PLA Wood": 27.99, "PLA Sparkle": 27.99, "PLA Marble": 27.99,
    "PLA Metal": 27.99, "PLA Galaxy": 27.99, "PLA Glow": 27.99, "PLA Aero": 47.99, "PLA-CF": 29.99,
    "PETG-CF": 35.99, "ABS-GF": 31.99, "ASA": 24.99, "ASA-CF": 38.99, "ASA Aero": 51.99, "PC": 42.99,
    "PC FR": 56.99, "PA6-CF": 44.99, "PA6-GF": 62.99, "PAHT-CF": 53.99, "PET-CF": 48.99, "PPA-CF": 155.99,
    "TPU for AMS": 39.99, "TPU 95A HF": 34.99, "TPU 85A": 43.99, "TPU 90A": 43.99, "Support for PLA": 25.99,
}


def fill_shop_prices(conn: sqlite3.Connection) -> int:
    """Once per installation: give Bambu lines without a price the shop price (only for euro, the prices are in EUR)."""
    st = settings.load()
    if st.get("shop_prices"):
        return 0
    n = 0
    if str(st.get("currency") or "€").strip() in ("€", "EUR"):
        for name, price in SHOP_PRICES.items():
            n += conn.execute("UPDATE lines SET price = ? WHERE name = ? AND brand IS NULL AND price IS NULL",
                              (price, name)).rowcount
    settings.save({"shop_prices": SHOP_PRICES_AS_OF})
    return n


def line_price(conn: sqlite3.Connection, product_id: int) -> Optional[float]:
    """Standard price of the product's line (suggested when adding a spool by hand)."""
    r = conn.execute("SELECT l.price FROM lines l JOIN products p ON p.line_id = l.id WHERE p.id = ?", (product_id,)).fetchone()
    return r["price"] if r else None


def set_prices(conn: sqlite3.Connection, items: list) -> None:
    for it in items or []:
        conn.execute("UPDATE lines SET price = ? WHERE id = ?", (_price(it.get("price")), int(it["id"])))


def last_price(conn: sqlite3.Connection, product_id: int) -> Optional[float]:
    """Last price paid for a spool of this product's line, else the line's estimated price."""
    r = conn.execute(
        "SELECT s.price FROM spools s JOIN products p ON p.id = s.product_id "
        "WHERE p.line_id = (SELECT line_id FROM products WHERE id = ?) AND s.price IS NOT NULL "
        "ORDER BY COALESCE(s.received_at, '') DESC, s.id DESC LIMIT 1", (product_id,)).fetchone()
    if r:
        return r["price"]
    r = conn.execute("SELECT l.price FROM lines l JOIN products p ON p.line_id = l.id WHERE p.id = ?", (product_id,)).fetchone()
    return r["price"] if r else None


def deliveries(conn: sqlite3.Connection, limit: int = 40) -> list:
    """Spools grouped by day received and line, so the price of a delivery can be entered once."""
    out = []
    for r in conn.execute(
            "SELECT s.received_at AS day, l.id AS line_id, l.name AS line, COUNT(*) AS spools, COUNT(s.price) AS priced, "
            "  MIN(s.price) AS pmin, MAX(s.price) AS pmax, l.price AS line_price "
            "FROM spools s JOIN products p ON p.id = s.product_id JOIN lines l ON l.id = p.line_id "
            "WHERE s.received_at IS NOT NULL GROUP BY s.received_at, l.id "
            "ORDER BY s.received_at DESC, l.name LIMIT ?", (limit,)):
        d = dict(r)
        d["price"] = d["pmin"] if d["priced"] == d["spools"] and d["pmin"] == d["pmax"] else None
        d["mixed"] = d["priced"] > 0 and d["price"] is None
        out.append(d)
    return out


def set_delivery_price(conn: sqlite3.Connection, day: str, line_id: int, price) -> int:
    """Set the price of all spools of a line received on that day (empty = remove the price)."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(day or "")):
        raise InventoryError("Invalid date")
    cur = conn.execute(
        "UPDATE spools SET price = ? WHERE received_at = ? AND product_id IN (SELECT id FROM products WHERE line_id = ?)",
        (_price(price), day, int(line_id)))
    return cur.rowcount


def set_spool_price(conn: sqlite3.Connection, spool_id: int, price) -> dict:
    get_spool(conn, spool_id)
    conn.execute("UPDATE spools SET price = ? WHERE id = ?", (_price(price), spool_id))
    return get_spool(conn, spool_id)


# ------------------------------------------------------------------ weighing

def net_g(sp: dict) -> int:
    return int(sp.get("weight_g") or sp.get("net_g") or DEFAULT_NET_G)


def tare_g(sp: dict) -> int:
    if sp.get("spool_g") is not None:
        return int(sp["spool_g"])
    return int(settings.load().get("spool_g_default", BAMBU_SPOOL_G))


def weigh(conn: sqlite3.Connection, spool_id: int, gross) -> dict:
    """Spool weighed including the empty spool: rest = gross - tare, stored as percent of the net weight."""
    g = _int(gross, 0, 20000)
    if g is None:
        raise InventoryError("Please enter the weight in grams")
    sp = get_spool(conn, spool_id)
    rest = max(0, g - tare_g(sp))
    pct = max(0, min(100, round(rest * 100 / net_g(sp))))
    conn.execute("UPDATE spools SET remain_pct = ?, measured_g = ?, measured_at = datetime('now', 'localtime'), "
                 "opened_at = CASE WHEN ? < 98 THEN COALESCE(opened_at, date('now', 'localtime')) ELSE opened_at END, "
                 "updated_at = datetime('now', 'localtime') WHERE id = ?", (pct, g, pct, spool_id))
    conn.execute("INSERT INTO usage (spool_id, remain_pct) VALUES (?, ?)", (spool_id, pct))
    log(conn, spool_id, "weighed", f"{g} g · {rest} g left")
    return {"spool": get_spool(conn, spool_id), "rest_g": rest, "pct": pct, "tare_g": tare_g(sp)}
