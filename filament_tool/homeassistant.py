"""Home Assistant: temperature and humidity sensors per cabinet (read-only).

Since 1.7.0 the Bambu data (AMS, print job) comes straight from the printer (bambu.py).
apply() below syncs AMS slots with the stock and is used from there.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from . import db

log = logging.getLogger("homeassistant")
CONFIG = db.DATA_DIR / "homeassistant.json"
POLL_SECONDS = 30


def load_config() -> Optional[dict]:
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not cfg.get("token") or not cfg.get("url"):
        return None
    return cfg


def public_config() -> dict:
    """For the UI: address and whether a token is stored – never the token itself."""
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    return {"url": cfg.get("url") or "", "has_token": bool(cfg.get("token"))}


def test_connection(url: str, token: str) -> None:
    req = urllib.request.Request(url.rstrip("/") + "/api/", headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            if r.status != 200:
                raise ValueError(f"Home Assistant responds with {r.status}")
    except urllib.error.HTTPError as e:
        raise ValueError("Token rejected by Home Assistant" if e.code == 401 else f"Home Assistant responds with {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise ValueError(f"Home Assistant not reachable ({getattr(e, 'reason', e)})")


def save_config(url: Optional[str], token: Optional[str]) -> dict:
    """Check and save address/token. An empty token keeps the stored one."""
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    new_url = (url or cfg.get("url") or "").strip()
    if new_url and not re.match(r"^https?://", new_url, re.I):
        new_url = "http://" + new_url                      # "192.168.1.100:8123" without http:// is meant the same way
    new_token = (token or "").strip() or cfg.get("token") or ""
    if not re.match(r"^https?://[^\s/]+", new_url):
        raise ValueError("Please enter an address like http://192.168.1.100:8123")
    if not new_token:
        raise ValueError("Please enter a token")
    try:
        test_connection(new_url, new_token)
    except Exception:
        # an address without a port usually means Home Assistant's default port 8123
        m = re.match(r"^(https?://[^\s/:]+)/?$", new_url, re.I)
        if not m:
            raise
        try:
            test_connection(m.group(1) + ":8123", new_token)
        except Exception:
            test_connection(new_url, new_token)            # report the error of the address as entered
        new_url = m.group(1) + ":8123"
    if CONFIG.exists():
        bak = CONFIG.with_suffix(".json.bak")
        bak.write_bytes(CONFIG.read_bytes())
        bak.chmod(0o600)
    cfg.update(url=new_url.rstrip("/"), token=new_token)
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(CONFIG)
    return public_config()


def delete_config() -> None:
    """Forget address and token (the user turned Home Assistant off and chose "Delete data")."""
    for f in (CONFIG, CONFIG.with_suffix(".json.bak")):
        try:
            f.unlink()
        except FileNotFoundError:
            pass


def fetch_states(cfg: dict) -> list:
    req = urllib.request.Request(cfg["url"].rstrip("/") + "/api/states",
                                 headers={"Authorization": "Bearer " + cfg["token"]})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def apply(conn, trays: list, printer_id: str = "p1", label: str = "") -> dict:
    """Mark spools found in this printer's AMS as in use, and spools that left it as 'to be put back' (removed).
    label: printer name for the history ("H2C · AMS 1 Slot 3"), empty with a single printer."""
    from .logic import _no_tag_tray
    seen, changed, removed = set(), [], []
    for t in trays:
        if not t["tray_uuid"]:
            continue
        sp = conn.execute("SELECT id, status, ams_slot, remain_pct, printer_id, is_refill FROM spools WHERE tray_uid = ?",
                          (t["tray_uuid"],)).fetchone()
        if sp is None or sp["id"] in seen:   # the same spool in two slots: keep the first
            continue
        seen.add(sp["id"])
        remain = t["remain"] if isinstance(t["remain"], (int, float)) and t["remain"] >= 0 else None
        if remain is not None and remain != sp["remain_pct"]:
            conn.execute("INSERT INTO usage (spool_id, remain_pct) VALUES (?, ?)", (sp["id"], int(remain)))
        if sp["ams_slot"] != t["name"] or sp["status"] != "in_use" or sp["printer_id"] != printer_id:
            changed.append(sp["id"])
            conn.execute("INSERT INTO events (spool_id, action, detail) VALUES (?, 'to_ams', ?)",
                         (sp["id"], f"{label} · {t['name']}" if label else t["name"]))
            if sp["is_refill"] and not sp["ams_slot"]:
                # a refill only fits the AMS on a spool: the browser asks whether it took an empty one from the stock
                conn.execute("UPDATE spools SET refill_ask = 1 WHERE id = ?", (sp["id"],))
        conn.execute(
            "UPDATE spools SET status = 'in_use', ams_slot = ?, printer_id = ?, remain_pct = COALESCE(?, remain_pct), "
            "needs_return = 0, opened_at = COALESCE(opened_at, date('now','localtime')), "
            "updated_at = datetime('now','localtime') WHERE id = ?",
            (t["name"], printer_id, remain, sp["id"]))
    # spools assigned by hand (no Bambu tag): they stay while their slot holds a spool without a tag
    by_name = {t["name"]: t for t in trays}
    for sp in conn.execute("SELECT id, ams_slot, status FROM spools WHERE ams_bound = 1 AND ams_slot IS NOT NULL "
                           "AND (printer_id = ? OR printer_id IS NULL)", (printer_id,)).fetchall():
        if sp["id"] in seen:          # its Bambu tag was read after all: from now on the tag counts
            conn.execute("UPDATE spools SET ams_bound = 0, ams_prev = NULL WHERE id = ?", (sp["id"],))
            continue
        t = by_name.get(sp["ams_slot"]) or {}
        if t and _no_tag_tray(t) and sp["status"] != "empty":
            seen.add(sp["id"])
    for sp in conn.execute("SELECT id FROM spools WHERE ams_slot IS NOT NULL AND (printer_id = ? OR printer_id IS NULL)",
                           (printer_id,)).fetchall():
        if sp["id"] not in seen:
            changed.append(sp["id"])
            removed.append(sp["id"])
            conn.execute("UPDATE spools SET ams_slot = NULL, printer_id = NULL, needs_return = 1 WHERE id = ?", (sp["id"],))
            conn.execute("INSERT INTO events (spool_id, action, detail) VALUES (?, 'from_ams', 'to put back')",
                         (sp["id"],))
    return {"matched": len(seen), "changed": changed, "removed": removed}


CLIMATE_EVERY = 600   # seconds between two stored climate readings
CLIMATE_KEEP_DAYS = 180


def sensors(states: list) -> list:
    """All temperature and humidity sensors, for the picker in the options."""
    out = []
    for st in states:
        a = st.get("attributes") or {}
        kind = a.get("device_class")
        if not st["entity_id"].startswith("sensor.") or kind not in ("temperature", "humidity"):
            continue
        out.append({"entity": st["entity_id"], "name": a.get("friendly_name") or st["entity_id"], "kind": kind,
                    "state": st.get("state"), "unit": a.get("unit_of_measurement") or ""})
    return sorted(out, key=lambda x: (x["kind"], x["name"].lower()))


def _num(states_by_id: dict, entity: str) -> Optional[float]:
    try:
        return round(float(states_by_id[entity]["state"]), 1)
    except (KeyError, TypeError, ValueError):
        return None


class HAThread(threading.Thread):
    """Polls Home Assistant and keeps the current cabinet values; stores a reading every 10 minutes."""

    def __init__(self, on_change: Callable[[dict], None]):
        super().__init__(daemon=True, name="homeassistant")
        self.on_change = on_change
        self.state = {"status": "off", "detail": "not set up (optional)", "climate": {}, "sensors": []}
        self._wake = threading.Event()
        self._saved = 0.0

    def reload(self) -> None:
        self._wake.set()

    def run(self) -> None:
        from . import settings
        while True:
            self._wake.clear()
            before = (self.state["status"], json.dumps(self.state.get("climate"), sort_keys=True))
            st = settings.load()
            cfg = load_config()
            if cfg is None:
                self.state.update(status="off", detail="not set up (optional)", climate={}, sensors=[])
            elif not st.get("ha_on", True):
                self.state.update(status="off", detail="switched off", climate={}, sensors=[])
            else:
                try:
                    states = fetch_states(cfg)
                    by_id = {x["entity_id"]: x for x in states}
                    climate = {}
                    for key, c in (st.get("climate") or {}).items():
                        t, h = _num(by_id, c.get("temp") or ""), _num(by_id, c.get("hum") or "")
                        if t is not None or h is not None:
                            climate[key] = {"temp": t, "hum": h, "max_hum": c.get("max_hum", 50)}
                    sens = sensors(states)
                    self.state.update(status="connected", detail=f"{len(sens)} sensors", climate=climate, sensors=sens)
                    log.debug("Home Assistant: %d states, %d sensors, climate %s", len(states), len(sens), climate)
                    if climate and time.time() - self._saved >= CLIMATE_EVERY:
                        self._saved = time.time()
                        with db.session() as conn:
                            conn.executemany("INSERT INTO climate (cabinet, temp, hum) VALUES (?, ?, ?)",
                                             [(k, v["temp"], v["hum"]) for k, v in climate.items()])
                            conn.execute("DELETE FROM climate WHERE ts < datetime('now', 'localtime', ?)",
                                         (f"-{CLIMATE_KEEP_DAYS} days",))
                except Exception as e:  # network, token, ...
                    log.warning("Home Assistant: %s", e)
                    self.state.update(status="error", detail=str(e)[:200])
            self.state["polled"] = time.time()
            if (self.state["status"], json.dumps(self.state.get("climate"), sort_keys=True)) != before:
                self.on_change({"changed": []})
            try:
                wait = settings.load()["ha_poll_seconds"]
            except Exception:
                wait = POLL_SECONDS
            self._wake.wait(wait)


def history(conn, days: int = 7, points: int = 168) -> dict:
    """Readings per cabinet for the last days, averaged down to at most `points` values."""
    days = max(1, min(int(days), CLIMATE_KEEP_DAYS))
    bucket = max(600, days * 86400 // points)
    rows = conn.execute(
        "SELECT cabinet, CAST(strftime('%s', ts) AS INTEGER) / ? * ? AS b, AVG(temp), AVG(hum) FROM climate "
        "WHERE ts >= datetime('now', 'localtime', ?) GROUP BY cabinet, b ORDER BY b",
        (bucket, bucket, f"-{days} days")).fetchall()
    out: dict = {}
    for cab, b, t, h in rows:
        out.setdefault(cab, []).append([b, None if t is None else round(t, 1), None if h is None else round(h, 1)])
    return out
