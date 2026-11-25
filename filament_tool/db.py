"""SQLite database: schema, migrations, connections, slot layout and the initial stock import."""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import host

DATA_DIR = host.data_dir()          # repo/data on the Pi, %APPDATA%/PixxelSpool in the Windows app, ~/Library/Application Support/PixxelSpool on the Mac
DB_NAME = "inventory.db"
DB_PATH = DATA_DIR / DB_NAME

# "Reset PixxelSpool" (Options › System): the request only leaves this marker and restarts. On the next start, before
# anything opens the files, the data files are deleted (the user confirmed it and was advised to download a backup
# first), so PixxelSpool starts like a new installation with the setup assistant. The folder of automatic backups
# and the logs stay.
RESET_MARKER = DATA_DIR / "factory-reset.pending"
RESET_FILES = ("inventory.db", "inventory.db-wal", "inventory.db-shm", "settings.json", "bambu.json",
               "homeassistant.json", "auth.json", "push.json", "offsite.json")


def _factory_reset() -> None:
    if not RESET_MARKER.exists():
        return
    try:
        for name in RESET_FILES:
            if (DATA_DIR / name).exists():
                (DATA_DIR / name).unlink()
        RESET_MARKER.unlink()
        logging.getLogger("db").info("PixxelSpool reset: data files deleted")
    except OSError as e:
        logging.getLogger("db").warning("Reset not finished, will try again on the next start: %s", e)


_factory_reset()
# a catalog in data/ wins over the bundled one
CATALOG_JSON = DATA_DIR / "bambu_katalog.json"
if not CATALOG_JSON.exists():
    CATALOG_JSON = Path(__file__).resolve().parent / "bambu_katalog.json"

# The cabinet layout lives in data/settings.json ("cabinets"). These values are only the initial state:
# one small storage "1" (3 levels of 6 spools plus a shelf), that the setup wizard invites to adjust.
DEFAULT_CABINETS = [
    {"key": "L", "code": "S", "name": "1", "label": "", "unit": "level", "rows": 3, "per_row": 6,
     "numbering": "num", "shelves": 1, "dry": False, "lower_from": 0},
]
# Order of lines on the rods: common lines first, special ones last
LINE_ORDER = [
    "PLA Basic", "PLA Basic Gradient", "PLA Matte", "PLA Pure", "PLA Lite", "PLA Silk", "PLA Silk Multi-Color", "PLA Silk+", "PLA Translucent",
    "PLA Sparkle", "PLA Metal", "PLA Galaxy", "PLA Marble", "PLA Glow", "PLA Wood", "PLA Palette",
    "PLA Dynamic", "PLA Aero", "PLA Tough", "PLA Tough+", "PLA-CF",
    "PETG Basic", "PETG Matte", "PETG HF", "PETG Translucent", "PETG-CF",
    "ABS", "ABS-GF", "ASA", "ASA Aero", "ASA-CF",
    "TPU for AMS", "TPU 95A HF", "TPU 95A", "TPU 90A", "TPU 85A", "TPU 75A (2.85mm)",
]


def cabinets() -> list:
    from . import settings
    return settings.load()["cabinets"]


def cab_code(key: str) -> str:
    return next((c["code"] for c in cabinets() if c["key"] == key), key)


def cab_prefix(key: str) -> str:
    """Prefix of a cabinet's slot codes, e.g. 'L-'."""
    return cab_code(key) + "-"


def overflow_id(key: str, n: int = 1) -> str:
    return f"Ü-{cab_code(key)}{n}"


def overflow_prefix(key: str) -> str:
    return f"Ü-{cab_code(key)}"


def sort_key(line: str, bambu_no) -> tuple:
    """Sort key: line by LINE_ORDER (unknown lines alphabetically after), then Bambu number = color group."""
    rank = LINE_ORDER.index(line) if line in LINE_ORDER else len(LINE_ORDER)
    return (rank, line if rank == len(LINE_ORDER) else "", str(bambu_no or "~"))


_MAT = re.compile(r"^(PLA|PETG|PET|TPU|TPE|ABS|ASA|HIPS|PA\d*|PC|PPA|PPS|PVA|BVOH|SUPPORT|OTHER|SONSTIGES)(?![A-Z])")


def material(line: str) -> str:
    """Material of a line, also for other brands ("Sunlu PETG" -> PETG): the first word that is a material."""
    for word in (line or "").split():
        m = _MAT.match(word.upper())
        if m:
            return m.group(1)
    return ""


def is_dry(line: str) -> bool:
    """Does this line belong in the dry zone?"""
    mat = material(line)
    return bool(mat) and mat not in ("PLA",)


def home_cabinet(line: str) -> str:
    """Cabinet key a line belongs to: the dry zone for moisture-sensitive materials."""
    cabs = cabinets()
    want = is_dry(line)
    for c in cabs:
        if bool(c.get("dry")) == want:
            return c["key"]
    return cabs[0]["key"] if cabs else "L"

# Zones: which rows a line prefers (row 1 = top)
ZONES = {
    "PLA Basic": "A-1",
    "PLA Matte": "A-2",
    "PLA Pure": "A-2",
    "PETG Basic": "A-3,A-4",
    "PETG Matte": "A-4",
    "PLA Metal": "B-1",
    "PLA Galaxy": "B-2",
}
DEFAULT_ZONE = "B-3,B-4"

SCHEMA = """
CREATE TABLE IF NOT EXISTS lines (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    complete INTEGER NOT NULL DEFAULT 0,
    zone TEXT
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    line_id INTEGER NOT NULL REFERENCES lines(id),
    color_name TEXT NOT NULL,
    bambu_no TEXT UNIQUE,
    hex TEXT,
    swatch INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tag_map (
    variant_id TEXT PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id)
);
CREATE TABLE IF NOT EXISTS slots (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('cabinet', 'overflow')),
    cabinet TEXT NOT NULL,
    row INTEGER NOT NULL,
    pos INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS spools (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    tray_uid TEXT UNIQUE,
    tag_uid TEXT,
    is_refill INTEGER NOT NULL DEFAULT 0,
    weight_g INTEGER,
    production TEXT,
    status TEXT NOT NULL DEFAULT 'stored'
        CHECK (status IN ('stored', 'in_use', 'empty')),
    slot_id TEXT REFERENCES slots(id),
    in_cabinet INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
-- Core rule: at most one spool per filament in the cabinet, one spool per cabinet slot
CREATE UNIQUE INDEX IF NOT EXISTS one_per_product ON spools(product_id) WHERE in_cabinet = 1;
CREATE UNIQUE INDEX IF NOT EXISTS one_per_slot ON spools(slot_id) WHERE in_cabinet = 1;
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    spool_id INTEGER NOT NULL REFERENCES spools(id),
    remain_pct INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS climate (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    cabinet TEXT NOT NULL,
    temp REAL,
    hum REAL
);
CREATE INDEX IF NOT EXISTS climate_cab_ts ON climate (cabinet, ts);

CREATE TABLE IF NOT EXISTS notices (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    kind TEXT NOT NULL,
    key TEXT NOT NULL UNIQUE,
    level TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    args TEXT NOT NULL DEFAULT '[]',
    link TEXT NOT NULL DEFAULT '',
    read INTEGER NOT NULL DEFAULT 0,
    hidden INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS prints (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    task TEXT NOT NULL UNIQUE,
    name TEXT,
    state TEXT,
    grams REAL,
    cost REAL,
    detail TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    spool_id INTEGER REFERENCES spools(id),
    action TEXT NOT NULL,
    detail TEXT
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Backups before small, frequent actions (deleting a spool, finishing a stock check): one copy per series is enough.
# Within this many minutes after such a backup no new one is made, so it keeps the state before the first action.
SERIES_MIN = {"before-delete": 30, "before-audit": 30}
KEEP_EVENT_MIN = 10        # always keep at least this many backups before actions, even when they are old


def _event_backups(folder: Path) -> list:
    """(time, path) of the backups before actions (current naming), newest first."""
    from datetime import datetime
    out = []
    for p in folder.glob("inventory-????-??-??-??????-*.db"):
        try:
            out.append((datetime.strptime(p.name[10:27], "%Y-%m-%d-%H%M%S"), p))
        except ValueError:
            continue
    return sorted(out, reverse=True)


def prune_backups(keep_days: int) -> int:
    """Delete backups before actions that are older than keep_days (with their saved settings), always keeping the
    newest KEEP_EVENT_MIN. Nightly and update backups are handled elsewhere. Returns the number deleted."""
    from datetime import datetime, timedelta
    folder = DATA_DIR / "backups"
    if not folder.is_dir():
        return 0
    limit, n = datetime.now() - timedelta(days=max(1, keep_days)), 0
    for ts, p in _event_backups(folder)[KEEP_EVENT_MIN:]:
        if ts < limit:
            for f in (p, p.with_name(p.stem + "-settings.json")):
                try:
                    f.unlink()
                    n += f.suffix == ".db"
                except OSError:
                    pass
    return n


def backup(reason: str, series: bool = True) -> Path:
    """Write a consistent copy of the database to data/backups/ (name starts with date and time, then the reason).
    For frequent small actions (SERIES_MIN) a recent backup with the same reason is reused instead."""
    from datetime import datetime, timedelta
    folder = DATA_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    if series and reason in SERIES_MIN:
        since = datetime.now() - timedelta(minutes=SERIES_MIN[reason])
        recent = next((p for ts, p in _event_backups(folder) if ts >= since and p.name.endswith(f"-{reason}.db")), None)
        if recent is not None:
            return recent
    try:
        from . import settings
        prune_backups(int(settings.load().get("backup_keep_days", 30)))
    except Exception as e:      # pruning must never stop a backup
        logging.getLogger("db").warning("Old backups not pruned: %s", e)
    target = folder / f"inventory-{datetime.now():%Y-%m-%d-%H%M%S}-{reason}.db"
    src = connect()
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    return target


_BK_PATTERNS = (
    # (regex on the file name, how to read the time from it)
    (re.compile(r"^inventory-(\d{4}-\d{2}-\d{2})\.db$"), "%Y-%m-%d"),                                  # nightly
    (re.compile(r"^inventory-(\d{4}-\d{2}-\d{2}-\d{6})-(.+)\.db$"), "%Y-%m-%d-%H%M%S"),                  # current naming (date, time, reason)
)


def list_backups() -> list:
    """All automatic backups (nightly, before updates, before risky actions), newest first.
    Each: {"name": path relative to data/, "kind", "detail", "time": ISO, "size"}."""
    from datetime import datetime
    out = []
    for path in (DATA_DIR / "backups").glob("*.db"):
        name = path.name
        for rx, fmt in _BK_PATTERNS:
            m = rx.match(name)
            if not m:
                continue
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if fmt == "%Y-%m-%d":            # nightly: the file's own time is more exact than the date in the name
                named = datetime.strptime(m.group(1), fmt)
                ts, reason = (mtime if mtime.date() == named.date() else named), "nightly"
            else:
                try:
                    ts = datetime.strptime(m.group(1), fmt)
                except ValueError:
                    ts = mtime
                reason = m.group(2)
            kind, detail = reason, ""
            if reason.startswith("before-update-"):
                kind, detail = "before-update", reason[len("before-update-"):]
            out.append({"name": str(path.relative_to(DATA_DIR)), "kind": kind, "detail": detail,
                        "time": ts.isoformat(timespec="minutes"), "size": path.stat().st_size})
            break
    out.sort(key=lambda b: b["time"], reverse=True)
    return out


def row_label(cab: dict, row: int) -> str:
    if cab.get("numbering") == "alpha":
        return "".join(chr(65 + d) for d in _alpha(row))
    return str(row)


def _alpha(n: int) -> list:
    out = []
    while n > 0:
        n, r = divmod(n - 1, 26)
        out.insert(0, r)
    return out


def slot_label(cab: dict, row: int, pos: int) -> str:
    p = f"{pos:02d}" if cab["per_row"] >= 10 else str(pos)
    return f"{cab['code']}-{row_label(cab, row)}-{p}"


def desired_slots(cabs: list) -> dict:
    """(kind, key, row, position) -> slot id according to the configuration."""
    want = {}
    for c in cabs:
        for r in range(1, c["rows"] + 1):
            for p in range(1, c["per_row"] + 1):
                want[("cabinet", c["key"], r, p)] = slot_label(c, r, p)
        for b in range(1, c["shelves"] + 1):
            want[("overflow", c["key"], b, 0)] = f"Ü-{c['code']}{b}"
    return want


def apply_layout(conn: sqlite3.Connection, cabs: list) -> dict:
    """Adapt the slots to the configuration: rename, add, remove.

    Slots holding spools are never removed – in that case a list of errors is returned and nothing changes.
    """
    want = desired_slots(cabs)
    existing = [dict(r) for r in conn.execute("SELECT * FROM slots")]
    have = {(r["kind"], r["cabinet"], r["row"], r["pos"]): r["id"] for r in existing}
    gone = [sid for t, sid in have.items() if t not in want]
    blockers = []
    if gone:
        q = ",".join("?" * len(gone))
        for r in conn.execute("SELECT s.id, s.slot_id, l.name AS line, p.color_name FROM spools s "
                              "JOIN products p ON p.id = s.product_id JOIN lines l ON l.id = p.line_id "
                              f"WHERE s.status != 'empty' AND s.slot_id IN ({q})", gone):
            blockers.append({"spool_id": r["id"], "slot": r["slot_id"], "what": f"{r['line']} {r['color_name']}"})
    if blockers:
        return {"ok": False, "blockers": blockers}
    rename = {have[t]: nid for t, nid in want.items() if t in have and have[t] != nid}
    # rename in two steps so swapping codes (e.g. L <-> R) does not collide
    for step in ({o: f"~tmp~{o}" for o in rename}, {f"~tmp~{o}": n for o, n in rename.items()}):
        for old, new in step.items():
            row = conn.execute("SELECT kind, cabinet, row, pos FROM slots WHERE id = ?", (old,)).fetchone()
            conn.execute("INSERT INTO slots VALUES (?, ?, ?, ?, ?)", (new, row[0], row[1], row[2], row[3]))
            conn.execute("UPDATE spools SET slot_id = ? WHERE slot_id = ?", (new, old))
            conn.execute("DELETE FROM slots WHERE id = ?", (old,))
    if rename:
        pat = re.compile(r"(?<![\w-])(" + "|".join(re.escape(o) for o in sorted(rename, key=len, reverse=True)) + r")(?![\w-])")
        for ev in conn.execute("SELECT id, detail FROM events WHERE detail IS NOT NULL").fetchall():
            d = pat.sub(lambda m: rename[m.group(1)], ev["detail"])
            if d != ev["detail"]:
                conn.execute("UPDATE events SET detail = ? WHERE id = ?", (d, ev["id"]))
    added = 0
    for t, nid in want.items():
        if t not in have:
            conn.execute("INSERT OR IGNORE INTO slots VALUES (?, ?, ?, ?, ?)", (nid, t[0], t[1], t[2], t[3]))
            added += 1
    for sid in gone:
        conn.execute("UPDATE spools SET slot_id = NULL WHERE slot_id = ?", (sid,))
        conn.execute("DELETE FROM slots WHERE id = ?", (sid,))
    return {"ok": True, "renamed": len(rename), "added": added, "removed": len(gone)}


def init(path: Path | None = None) -> None:
    """Create the schema and the slots, update the color catalog."""
    (path or DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with session(path) as conn:
        conn.executescript(SCHEMA)
        _ensure_slots(conn)
        _migrate(conn)
        if CATALOG_JSON.exists():
            sync_catalog(conn, CATALOG_JSON)


def _ensure_slots(conn: sqlite3.Connection) -> None:
    """Create slots from the configuration; missing rows are added, nothing is deleted."""
    res = apply_layout(conn, cabinets())
    if not res["ok"]:   # configuration conflicts with occupied slots: only add what is missing
        for t, nid in desired_slots(cabinets()).items():
            if not conn.execute("SELECT 1 FROM slots WHERE kind = ? AND cabinet = ? AND row = ? AND pos = ?", t).fetchone():
                conn.execute("INSERT OR IGNORE INTO slots VALUES (?, ?, ?, ?, ?)", (nid, *t))


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced in later versions (existing data is kept)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(products)")}
    for name, typ in [("name_en", "TEXT"), ("name_de", "TEXT"), ("variant_id", "TEXT"),
                      ("material_id", "TEXT"), ("colors", "TEXT"), ("kind", "TEXT"),
                      ("in_catalog", "INTEGER NOT NULL DEFAULT 0"),
                      ("discontinued", "INTEGER NOT NULL DEFAULT 0")]:     # no longer sold by Bambu Lab
        if name not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {name} {typ}")
    if "sku" not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN sku TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS product_variant ON products(variant_id)")
    # lines: other brands (brand set), weights, price, drying, shop link
    lcols = {r["name"] for r in conn.execute("PRAGMA table_info(lines)")}
    for name, typ in [("brand", "TEXT"), ("spool_g", "INTEGER"), ("net_g", "INTEGER"), ("price", "REAL"),
                      ("dry_temp", "INTEGER"), ("dry_hours", "REAL"), ("shop_url", "TEXT")]:
        if name not in lcols:
            conn.execute(f"ALTER TABLE lines ADD COLUMN {name} {typ}")
    scols = {r["name"] for r in conn.execute("PRAGMA table_info(spools)")}
    for name, typ in [("received_at", "TEXT"), ("opened_at", "TEXT"), ("ams_slot", "TEXT"),
                      ("remain_pct", "INTEGER"), ("needs_return", "INTEGER NOT NULL DEFAULT 0"),
                      ("dried_at", "TEXT"), ("tag_json", "TEXT"), ("price", "REAL"),
                      ("measured_g", "INTEGER"), ("measured_at", "TEXT"), ("printer_id", "TEXT"),
                      ("manual_place", "INTEGER NOT NULL DEFAULT 0"),   # slot chosen by hand: "Reorganize" leaves it alone
                      ("refill_ask", "INTEGER NOT NULL DEFAULT 0"),     # refill went into the AMS: ask about the empty spool
                      ("ams_bound", "INTEGER NOT NULL DEFAULT 0"),      # assigned by hand to an AMS slot (no Bambu tag)
                      ("ams_prev", "TEXT")]:                            # status before that assignment (for "undo")
        if name not in scols:
            conn.execute(f"ALTER TABLE spools ADD COLUMN {name} {typ}")
    if "bought_refill" not in scols:     # beta.2: bought as a refill (stays when the refill later sits on a spool), for prices
        conn.execute("ALTER TABLE spools ADD COLUMN bought_refill INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE spools SET bought_refill = is_refill")
    pcols = {r["name"] for r in conn.execute("PRAGMA table_info(prints)")}
    if "printer" not in pcols:
        conn.execute("ALTER TABLE prints ADD COLUMN printer TEXT")
    if "project" not in pcols:          # beta.2: prints grouped into projects ("Evee for Alex") with total cost
        conn.execute("ALTER TABLE prints ADD COLUMN project TEXT")
    if "note" not in pcols:             # beta.2: "file" = the print file could not be read (amounts can be added by hand)
        conn.execute("ALTER TABLE prints ADD COLUMN note TEXT")
    # spools scanned before: received = day of the first scan
    conn.execute("UPDATE spools SET received_at = date(updated_at) "
                 "WHERE tray_uid IS NOT NULL AND received_at IS NULL")
    conn.execute("UPDATE products SET name_de = color_name WHERE name_de IS NULL")
    conn.execute("UPDATE products SET name_en = color_name WHERE name_en IS NULL")
    # opening a spool shows up in the history, whichever way it happens (taken out, into the AMS, weighed, by hand)
    conn.execute("CREATE TRIGGER IF NOT EXISTS spool_opened AFTER UPDATE OF opened_at ON spools "
                 "WHEN OLD.opened_at IS NULL AND NEW.opened_at IS NOT NULL "
                 "BEGIN INSERT INTO events (spool_id, action, detail) VALUES (NEW.id, 'opened', ''); END")
    conn.execute("CREATE INDEX IF NOT EXISTS usage_spool ON usage(spool_id, id)")
    # alpha.92: a spool assigned by hand to an AMS slot loses that assignment whenever it leaves the AMS, however it happens
    conn.execute("CREATE TRIGGER IF NOT EXISTS ams_unbound AFTER UPDATE OF ams_slot ON spools "
                 "WHEN NEW.ams_slot IS NULL AND NEW.ams_bound = 1 "
                 "BEGIN UPDATE spools SET ams_bound = 0, ams_prev = NULL WHERE id = NEW.id; END")


def sync_catalog(conn: sqlite3.Connection, path: Path) -> int:
    """Load the Bambu color catalog: update existing products, add missing ones."""
    with open(path, encoding="utf-8") as f:
        colors = json.load(f)["colors"]
    for c in colors:
        row = conn.execute("SELECT p.id, p.line_id, l.name FROM products p JOIN lines l ON l.id = p.line_id WHERE p.bambu_no = ?",
                           (c["bambu_no"],)).fetchone()
        new_line = not conn.execute("SELECT 1 FROM lines WHERE name = ?", (c["line"],)).fetchone()
        conn.execute("INSERT OR IGNORE INTO lines (name, zone) VALUES (?, ?)",
                     (c["line"], ZONES.get(c["line"], DEFAULT_ZONE)))
        line_id = conn.execute("SELECT id FROM lines WHERE name = ?", (c["line"],)).fetchone()[0]
        if row and row["line_id"] != line_id:
            # beta.2: gradient / multi-colour spools became lines of their own (e.g. "PLA Basic Gradient");
            # the new line takes over price, weights and drying of the line the colour came from
            if new_line:
                conn.execute("UPDATE lines SET price = o.price, net_g = o.net_g, spool_g = o.spool_g, dry_temp = o.dry_temp, "
                             "dry_hours = o.dry_hours FROM (SELECT * FROM lines WHERE id = ?) AS o WHERE lines.id = ?",
                             (row["line_id"], line_id))
            conn.execute("UPDATE products SET line_id = ? WHERE id = ?", (line_id, row["id"]))
        first = c["colors"][0] if c["colors"] else None
        # "#000000" also means transparent/natural in the catalog -> leave the color empty (real dark colors keep it)
        dark = "Black" in c["name_en"] or c["name_en"] in ("Charcoal", "Key")
        hex_color = first if first and (first != "#000000" or dark) else None
        args = (c["name_en"], c["name_de"], c["variant_id"], c["material_id"],
                json.dumps(c["colors"]), c["kind"])
        disc = 1 if c.get("discontinued") else 0
        if row:
            conn.execute("UPDATE products SET name_en = ?, name_de = ?, color_name = ?, variant_id = ?, "
                         "material_id = ?, colors = ?, kind = ?, in_catalog = 1, discontinued = ?, "
                         "hex = COALESCE(hex, ?) WHERE id = ?",
                         (args[0], args[1], args[1], *args[2:], disc, hex_color, row[0]))
        else:
            conn.execute("INSERT INTO products (line_id, color_name, bambu_no, hex, name_en, name_de, "
                         "variant_id, material_id, colors, kind, in_catalog, discontinued) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                         (line_id, c["name_de"], c["bambu_no"], hex_color, *args, disc))
    # lines left without any colour (all moved to a new line) are removed
    conn.execute("DELETE FROM lines WHERE brand IS NULL AND NOT EXISTS (SELECT 1 FROM products p WHERE p.line_id = lines.id)")
    return len(colors)
