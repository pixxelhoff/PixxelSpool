"""App settings in data/settings.json, shared by all devices (browser-only preferences live in localStorage)."""
from __future__ import annotations

import copy
import json
import re
import threading

from . import __version__, db

PATH = db.DATA_DIR / "settings.json"
DEFAULTS = {
    "cabinets": db.DEFAULT_CABINETS,
    "low_remain_pct": 5,
    "tight_pct": 15,          # print check: "tight" when less than the need plus this many percent is left
    "ams_hum_max": 0,         # AMS humidity limit in % (0 = by the loaded material); above it a notice once a day
    "return_min": 0,          # remind after this many minutes that a spool taken out of the AMS is not back yet (0 = off)
    "min_stock_all": 0,       # minimum spools for every color you own (0 = off); min_stock per color wins
    "backup_keep_days": 30,
    "ha_poll_seconds": 30,
    "dry_weeks_dry": 4,       # PETG/TPU/ABS … (dry zone): suggest drying after x weeks opened
    "dry_weeks_other": 12,    # PLA
    "dry_on": True,           # False: no drying hints at all (notices, spool details, storage view)
    "empty_spools": 0,        # empty Bambu spools available for refills
    "reader": "auto",         # auto | usb | pn532
    "pn532_bus": 1,
    "pn532_addr": 0x24,
    "scan_pause_ms": 500,     # the reader rests this long after a scan (no double read, no error beep)
    "log_detail": False,      # detailed log (DEBUG) for troubleshooting
    "log_rows": 5,            # entries in the history card of the storage view
    "pn532_port": "",         # serial port of a USB PN532 ("" = find it), e.g. COM3 or /dev/ttyUSB0
    "setup_done": False,      # setup wizard finished
    "lang": "",               # UI language: de | en | es ("" = not chosen yet: follow the browser, fall back to English)
    "printer_on": True,       # direct printer connection (LAN) on/off, credentials are kept
    "ha_on": True,            # Home Assistant on/off, credentials are kept
    "climate": {},            # per cabinet: {"temp": entity_id, "hum": entity_id, "max_hum": 50}
    "camera": "off",          # camera in the printer card: off | eco (1 fps) | smooth (5 fps) | max (all frames)
    "update_check": True,
    "show_discontinued": False,   # catalog: also show colours Bambu Lab no longer sells
    "update_channel": "off",  # "off" = stable only, "beta" = also beta and rc, "alpha" = also alpha
    "pre_auto": False,        # the channel was set once automatically because a pre-release is installed
    "auto_security": True,    # Pi: install security releases by itself (daily check, rollback if it does not start)
    "spool_g_default": 250,   # empty Bambu spool weight for weighing; other brands set their own
    "currency": "€",
    "date_fmt": "auto",       # auto (by language) | dmy. | dmy/ | mdy/ | ymd-
    "time_fmt": "auto",       # auto (by language) | 24 | 12
    "collect_lines": [],      # lines to collect completely: their missing colors go on the shopping list
    "shop_list": [],          # colors put on the shopping list by hand: [{"id": product id, "since": "YYYY-MM-DD HH:MM:SS", "qty": n, "state": "cart"|"ordered"|"soldout", "refill": true}]
    "orders": [],             # #64: shop orders: date, items with prices, shipping, credits used / earned
    "credits": 0,             # #64: Bambu Lab credits you have (100 credits = 1 €)
    "parcels": [],            # #71: parcels of an order: [{"id", "order", "carrier", "tracking", "date"}]; shop_list entries point to one
    "min_stock": {},          # minimum number of spools per color: {"product id": n}; below it the color goes on the shopping list
    "shop_prices": "",        # date of the Bambu shop prices filled in as standard prices ("" = not yet)
    "use_minutes": 0,         # minutes the app was open and visible (counted until the donation note was shown)
    "donate_shown": False,    # one-time donation note already shown (never again after that)
}
DONATE_AFTER_MIN = 120        # the donation note appears once after two hours of use
_lock = threading.Lock()


def load() -> dict:
    """Settings merged over DEFAULTS (missing keys get their default)."""
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    out = copy.deepcopy(DEFAULTS)
    if "update_channel" not in data and data.get("update_pre"):
        data = {**data, "update_channel": "alpha"}      # before beta.1 the switch offered alpha and beta together
    for k, v in data.items():
        if k in out and k not in ("climate", "min_stock") and isinstance(out[k], dict) and isinstance(v, dict):
            out[k].update({kk: vv for kk, vv in v.items() if kk in out[k]})
        elif k in out:
            out[k] = v
    # running an alpha/beta/rc: the channel starts at that stage (once; changing it afterwards sticks)
    if not out["pre_auto"] and re.search(r"-(alpha|beta|rc)\b", __version__):
        out["update_channel"] = "alpha" if "-alpha" in __version__ else "beta"
        out["pre_auto"] = True
    if out["update_channel"] not in ("off", "beta", "alpha"):
        out["update_channel"] = "off"
    return out


UNITS = ("rod", "level")
LANGS = ("de", "en", "es")


def lang(accept: str = "") -> str:
    """UI language: the saved choice, else the best match from the browser's Accept-Language header, else English."""
    saved = load().get("lang")
    if saved in LANGS:
        return saved
    for part in (accept or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGS:
            return code
    return "en"


def clean_cabinets(raw) -> list:
    """Validate the cabinet layout coming from the UI. Raises ValueError with a user-facing message."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("There must be at least one storage unit")
    if len(raw) > 12:
        raise ValueError("At most 12 storage units")
    out, keys = [], set()
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            raise ValueError("Invalid storage data")
        code = str(c.get("code") or "").strip().upper()
        if not re.fullmatch(r"[A-ZÄÖ]{1,3}", code):
            raise ValueError(f"Code “{code or '–'}”: please use 1–3 letters (e.g. L, R, KE)")
        key = str(c.get("key") or "").strip()
        if not key or key in keys:
            key = "K" + str(max([int(k[1:]) for k in keys if re.fullmatch(r"K\d+", k)] + [2]) + 1)
        keys.add(key)
        name = _clean_text(c.get("name"), code)
        out.append({
            "key": key, "code": code, "name": name,
            "label": str(c.get("label") or "").strip()[:24],
            "unit": c.get("unit") if c.get("unit") in UNITS else "rod",
            "rows": _clamp(c.get("rows"), 1, 26, 5),
            "per_row": _clamp(c.get("per_row"), 1, 40, 5),
            "numbering": "alpha" if c.get("numbering") == "alpha" else "num",
            "shelves": _clamp(c.get("shelves"), 0, 9, 1),
            "dry": bool(c.get("dry")),
            "lower_from": _clamp(c.get("lower_from"), 0, 26, 0),
        })
    codes = [c["code"] for c in out]
    if len(set(codes)) != len(codes):
        raise ValueError("Each code may only be used once")
    for a in codes:
        for b in codes:
            if a != b and b.startswith(a):
                raise ValueError(f"Codes “{a}” and “{b}” are too similar (one starts like the other)")
    names = [c["name"].lower() for c in out]
    if len(set(names)) != len(names):
        raise ValueError("Every storage unit needs its own name")
    return out


def store_cabinets(cabs: list) -> dict:
    with _lock:
        cur = load()
        cur["cabinets"] = cabs
        cur.pop("cab_names", None); cur.pop("cab_labels", None)
        PATH.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        return cur


def _clean_text(v, fallback: str, n: int = 24) -> str:
    v = str(v or "").strip()[:n]
    return v or fallback


def _clamp(v, lo: int, hi: int, fallback: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return fallback


def save(patch: dict) -> dict:
    with _lock:
        cur = load()
        if "low_remain_pct" in patch:
            cur["low_remain_pct"] = _clamp(patch["low_remain_pct"], 0, 50, 5)
        for k, lo, hi, d in (("tight_pct", 0, 100, 15), ("ams_hum_max", 0, 90, 0), ("return_min", 0, 1440, 0), ("min_stock_all", 0, 9, 0)):
            if k in patch:
                cur[k] = _clamp(patch[k], lo, hi, d)
        if "backup_keep_days" in patch:
            cur["backup_keep_days"] = _clamp(patch["backup_keep_days"], 3, 365, 30)
        if "ha_poll_seconds" in patch:
            cur["ha_poll_seconds"] = _clamp(patch["ha_poll_seconds"], 10, 600, 30)
        if "dry_weeks_dry" in patch:
            cur["dry_weeks_dry"] = _clamp(patch["dry_weeks_dry"], 1, 104, 4)
        if "dry_weeks_other" in patch:
            cur["dry_weeks_other"] = _clamp(patch["dry_weeks_other"], 1, 104, 12)
        if "empty_spools" in patch:
            cur["empty_spools"] = _clamp(patch["empty_spools"], 0, 999, 0)
        if "empty_spools_delta" in patch:
            cur["empty_spools"] = _clamp(cur["empty_spools"] + int(patch["empty_spools_delta"]), 0, 999, 0)
        if patch.get("reader") in ("auto", "usb", "pn532"):
            cur["reader"] = patch["reader"]
        if "pn532_bus" in patch:
            cur["pn532_bus"] = _clamp(patch["pn532_bus"], 0, 20, 1)
        if "pn532_addr" in patch:
            cur["pn532_addr"] = _clamp(patch["pn532_addr"], 0x08, 0x77, 0x24)
        if "scan_pause_ms" in patch:
            cur["scan_pause_ms"] = _clamp(patch["scan_pause_ms"], 0, 5000, 500)
        if "log_rows" in patch:
            cur["log_rows"] = _clamp(patch["log_rows"], 1, 50, 5)
        if "pn532_port" in patch:
            port = str(patch["pn532_port"] or "").strip()[:64]
            cur["pn532_port"] = port if re.fullmatch(r"[\w./\\:-]*", port) else ""
        if patch.get("date_fmt") in ("auto", "dmy.", "dmy/", "mdy/", "ymd-"):
            cur["date_fmt"] = patch["date_fmt"]
        if str(patch.get("time_fmt")) in ("auto", "24", "12"):
            cur["time_fmt"] = str(patch["time_fmt"])
        if patch.get("update_channel") in ("off", "beta", "alpha"):
            cur["update_channel"] = patch["update_channel"]
        for k in ("printer_on", "ha_on", "update_check", "auto_security", "dry_on", "log_detail", "show_discontinued"):
            if k in patch:
                cur[k] = bool(patch[k])
        if isinstance(patch.get("climate"), dict):
            keys = {c["key"] for c in cur["cabinets"]}
            clean = {}
            for k, v in patch["climate"].items():
                if k in keys and isinstance(v, dict):
                    ent = lambda x: x if isinstance(x, str) and re.fullmatch(r"sensor\.[\w.]+", x or "") else ""
                    mx = _clamp(v.get("max_hum"), 10, 95, 50)
                    clean[k] = {"temp": ent(v.get("temp")), "hum": ent(v.get("hum")), "max_hum": mx,
                                # green range in the chart: up to ok_hum, yellow from there up to the warning limit
                                "ok_hum": _clamp(v.get("ok_hum"), 5, mx - 1, max(5, mx - 10))}
            cur["climate"] = clean
        if patch.get("camera") in ("off", "eco", "smooth", "max"):
            cur["camera"] = patch["camera"]
        if patch.get("lang") in LANGS:
            cur["lang"] = patch["lang"]
        if "setup_done" in patch:
            cur["setup_done"] = bool(patch["setup_done"])
        if isinstance(patch.get("collect_lines"), list):
            cur["collect_lines"] = [str(x)[:60] for x in patch["collect_lines"]][:100]
        if isinstance(patch.get("shop_prices"), str):
            cur["shop_prices"] = patch["shop_prices"][:10]
        if isinstance(patch.get("shop_list"), list):
            clean, seen = [], set()
            for e in patch["shop_list"]:
                try:
                    pid, since = int(e["id"]), str(e.get("since") or "")[:19]
                except (TypeError, ValueError, KeyError):
                    continue
                try:
                    qty = max(1, min(99, int(e.get("qty") or 1)))
                except (TypeError, ValueError):
                    qty = 1
                # state: "" = noted, "cart" = in the shop cart, "ordered" = on the way; refill = buy as refill
                state = e.get("state") if e.get("state") in ("cart", "ordered", "soldout") else ("cart" if e.get("cart") is True else "")
                # #69: a color can be on the list once not ordered yet and once per order
                key = (pid, str(e.get("order") or "")[:20] if state == "ordered" else None)
                if key not in seen and re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", since):
                    seen.add(key)
                    # #64: price per spool from a recorded order (shipping and credits included) and the order's id
                    try:
                        price = round(float(e["price"]), 2) if e.get("price") is not None and 0 <= float(e["price"]) <= 10000 else None
                    except (TypeError, ValueError):
                        price = None
                    order = str(e.get("order") or "")[:20]
                    parcel = str(e.get("parcel") or "")[:20] if state == "ordered" else ""    # #71: shipped in this parcel
                    clean.append({"id": pid, "since": since, "qty": qty, **({"state": state} if state else {}), **({"parcel": parcel} if parcel else {}),
                                  **({"refill": True} if e.get("refill") is True else {}),
                                  **({"price": price} if price is not None else {}), **({"order": order} if order else {})})
            cur["shop_list"] = clean[:300]
        # #64: recorded shop orders (written by insights.record_order) and the Bambu Lab credits balance
        if isinstance(patch.get("orders"), list):
            cur["orders"] = [o for o in patch["orders"] if isinstance(o, dict)][-100:]
        if "credits" in patch:
            cur["credits"] = _clamp(patch.get("credits"), 0, 10 ** 7, 0)
        if isinstance(patch.get("parcels"), list):
            cur["parcels"] = [{"id": str(x.get("id") or "")[:20], "order": str(x.get("order") or "")[:20],
                               "carrier": str(x.get("carrier") or "")[:20], "tracking": str(x.get("tracking") or "").strip()[:60],
                               "date": str(x.get("date") or "")[:10]} for x in patch["parcels"] if isinstance(x, dict) and x.get("id")][-100:]
        if isinstance(patch.get("min_stock"), dict):
            ms = {}
            for k, v in patch["min_stock"].items():
                try:
                    k, v = str(int(k)), int(v)
                except (TypeError, ValueError):
                    continue
                if 1 <= v <= 99:
                    ms[k] = v
            cur["min_stock"] = dict(list(ms.items())[:500])
        PATH.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        return cur


def count_use(minutes, ready: bool) -> dict:
    """Add minutes of use. Once two hours are reached and the browser is ready (no dialog open), the donation note is due, exactly once."""
    with _lock:
        cur = load()
        if cur.get("donate_shown"):
            return {"done": True, "show": False}
        cur["use_minutes"] = _clamp(cur.get("use_minutes"), 0, 10 ** 6, 0) + _clamp(minutes, 0, 5, 0)
        show = bool(ready) and cur["use_minutes"] >= DONATE_AFTER_MIN
        cur["donate_shown"] = show
        PATH.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"done": show, "show": show}
