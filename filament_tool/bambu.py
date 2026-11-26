"""Direct connection to the Bambu Lab printer on the local network (MQTT over TLS, port 8883). Reads the state;
the only thing it changes on the printer so far is the chamber light (more controls are planned).

Access: IP address, serial number and LAN access code (shown on the printer's display), stored in
data/bambu.json (owner-readable only); the access code is never sent to the UI.

The printer publishes its state as JSON on device/<serial>/report. Some models only send changes, so everything
is merged into one full state (lists of objects are merged by their "id").
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import ssl
import threading
import time
from typing import Callable, Optional

from . import db

log = logging.getLogger("bambu")
CONFIG = db.DATA_DIR / "bambu.json"
PORT = 8883
USER = "bblp"
PUSHALL = {"pushing": {"sequence_id": "0", "command": "pushall", "version": 1, "push_target": 1}}
PUSHALL_EVERY = 300   # seconds: request the full state every now and then


# ---------------------------------------------------------------- configuration
# data/bambu.json: {"printers": [{"id", "name", "ip", "serial", "code", "on"}, ...]}
# Up to 1.18 the file held a single printer ({"ip", "serial", "code"}); it is read as printer "p1".

# first characters of the serial number -> model (used as the default name)
MODELS = {"00M": "X1 Carbon", "00W": "X1", "03W": "X1E", "01S": "P1P", "01P": "P1S", "030": "A1 mini", "039": "A1",
          "094": "H2D", "31B": "H2C"}
_cfg_lock = threading.Lock()


def model_name(serial: str) -> str:
    return MODELS.get((serial or "")[:3].upper(), "")


def _read() -> list:
    try:
        raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for p in (raw.get("printers") if isinstance(raw, dict) else None) or []:
        if isinstance(p, dict) and p.get("id"):
            p.setdefault("on", True)
            p["name"] = (p.get("name") or "").strip() or model_name(p.get("serial") or "") or "Printer"
            out.append(p)
    return out


def _write(printers: list) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps({"printers": printers}, indent=2, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(CONFIG)


def printers() -> list:
    """All configured printers, including the access code (server side only)."""
    return _read()


def get(pid: str) -> Optional[dict]:
    """One complete printer configuration, or None."""
    p = next((p for p in _read() if p["id"] == pid), None)
    return p if p and p.get("ip") and p.get("serial") and p.get("code") else None


def name_of(pid: str) -> str:
    return next((p["name"] for p in _read() if p["id"] == pid), pid or "")


def public_config() -> dict:
    """For the UI – without access codes."""
    return {"printers": [{"id": p["id"], "name": p["name"], "ip": p.get("ip") or "", "serial": p.get("serial") or "",
                          "has_code": bool(p.get("code")), "on": bool(p.get("on")), "model": model_name(p.get("serial") or "")}
                         for p in _read()]}


def _clean(ip: str, serial: str, code: str) -> tuple:
    ip = (ip or "").strip()
    serial = (serial or "").strip().upper()
    code = (code or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9.\-]{3,253}", ip):
        raise ValueError("Please enter the printer's IP address, e.g. 192.168.1.50")
    if not re.fullmatch(r"[A-Z0-9]{8,20}", serial):
        raise ValueError("The serial number consists of 8–20 letters and digits (printer › Settings › Device)")
    if not re.fullmatch(r"[A-Za-z0-9]{6,16}", code):
        raise ValueError("The access code has 8 characters (printer › Settings › Network › Access code)")
    return ip, serial, code


def save_printer(pid: Optional[str], name: str, ip: str, serial: str, code: Optional[str], test: bool = True) -> dict:
    """Add (pid None) or change a printer. An empty code keeps the stored one. The connection is tested first.
    Returns {"id", "summary"}."""
    with _cfg_lock:
        cur = _read()
    old = next((p for p in cur if p["id"] == pid), None) if pid else None
    if pid and old is None:
        raise ValueError("Printer not found")
    code = code or (old or {}).get("code") or ""
    ip, serial, code = _clean(ip, serial, code)
    if any(p.get("serial") == serial and p["id"] != pid for p in cur):
        raise ValueError("This printer is already set up")
    summary = test_connection(ip, serial, code) if test else {}
    name = (name or "").strip()[:40] or model_name(serial) or "Printer"
    if any(p["name"].lower() == name.lower() and p["id"] != pid for p in cur):
        raise ValueError("Another printer already has this name")
    with _cfg_lock:
        cur = _read()
        if old is not None:
            for p in cur:
                if p["id"] == pid:
                    p.update(name=name, ip=ip, serial=serial, code=code)
        else:
            n = 1
            while any(p["id"] == f"p{n}" for p in cur):
                n += 1
            pid = f"p{n}"
            cur.append({"id": pid, "name": name, "ip": ip, "serial": serial, "code": code, "on": True})
        _write(cur)
    return {"id": pid, "summary": summary}


def set_on(pid: str, on: bool) -> None:
    with _cfg_lock:
        cur = _read()
        for p in cur:
            if p["id"] == pid:
                p["on"] = bool(on)
        _write(cur)


def delete_printer(pid: str) -> None:
    with _cfg_lock:
        cur = [p for p in _read() if p["id"] != pid]
        if cur:
            _write(cur)
        else:
            try:
                CONFIG.unlink()
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------- MQTT

def _client(serial: str, code: str, on_message, on_connect=None, on_disconnect=None):
    import paho.mqtt.client as mqtt
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pixxelspool-{os.getpid()}-{int(time.time()) % 10000}",
                    protocol=mqtt.MQTTv311)
    c.username_pw_set(USER, code)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE   # the printer uses a self-signed certificate
    c.tls_set_context(ctx)
    c.on_message = on_message
    if on_connect:
        c.on_connect = on_connect
    if on_disconnect:
        c.on_disconnect = on_disconnect
    return c


def _rc_text(rc) -> str:
    v = getattr(rc, "value", rc)
    return {4: "Wrong access code", 5: "Access code rejected", 134: "Wrong access code",
            135: "Access denied (developer mode needed?)"}.get(v, f"Connection refused ({rc})")


def test_connection(ip: str, serial: str, code: str, timeout: float = 12) -> dict:
    """Connect once, request the full state and return a summary. Raises ValueError with a readable message."""
    got: dict = {}
    err: dict = {}
    done = threading.Event()

    def on_connect(c, _u, _f, rc, _p=None):
        if getattr(rc, "is_failure", False) or getattr(rc, "value", rc) != 0:
            err["msg"] = _rc_text(rc)
            done.set()
            return
        c.subscribe(f"device/{serial}/report")
        c.publish(f"device/{serial}/request", json.dumps(PUSHALL))

    def on_message(_c, _u, msg):
        try:
            data = json.loads(msg.payload)
        except ValueError:
            return
        merge(got, data)
        if "print" in got and (got["print"].get("ams") or got["print"].get("gcode_state")):
            done.set()

    c = _client(serial, code, on_message, on_connect)
    try:
        c.connect(ip, PORT, keepalive=30)
    except OSError as e:
        raise ValueError(f"Printer at {ip} not reachable ({e.strerror or e})")
    c.loop_start()
    try:
        if not done.wait(timeout):
            raise ValueError("Connected, but the printer sends no data. Is the serial number correct?")
        if err:
            raise ValueError(err["msg"])
    finally:
        c.loop_stop()
        try:
            c.disconnect()
        except Exception:
            pass
    return summarize(got)


def _tray_replaces(t: dict) -> bool:
    """An AMS tray report that describes the whole slot: an empty slot (only its id) or a complete spool.
    Merging those field by field would keep the previous spool's tray_uuid, so after moving a spool to
    another slot both slots showed the same spool."""
    return set(t) <= {"id", "state"} or "tray_uuid" in t or "tray_type" in t


def merge(dst: dict, src: dict) -> dict:
    """Merge a partial report into the full state. Lists of objects with 'id' are merged per id."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            merge(dst[k], v)
        elif (isinstance(v, list) and isinstance(dst.get(k), list) and v and all(isinstance(x, dict) and "id" in x for x in v)
              and all(isinstance(x, dict) and "id" in x for x in dst[k])):
            by_id = {x["id"]: x for x in dst[k]}
            for x in v:
                if x["id"] in by_id and k == "tray" and _tray_replaces(x):
                    by_id[x["id"]].clear()          # new spool or empty slot: drop what the old spool left behind
                    by_id[x["id"]].update(copy.deepcopy(x))
                elif x["id"] in by_id:
                    merge(by_id[x["id"]], x)
                else:
                    dst[k].append(copy.deepcopy(x))
        else:
            dst[k] = copy.deepcopy(v)
    return dst


# ---------------------------------------------------------------- interpretation

def _f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def trays(state: dict) -> list:
    """AMS slots (and external spools) in one uniform shape."""
    p = state.get("print") or {}
    ams = p.get("ams") or {}
    now = str(ams.get("tray_now", ""))
    out = []
    for unit in ams.get("ams") or []:
        uid = int(_f(unit.get("id"), 0))
        hum_raw = _f(unit.get("humidity_raw"))
        for t in unit.get("tray") or []:
            tid = int(_f(t.get("id"), 0))
            gid = _gid(uid, tid)
            t = t if _present(ams, gid) else {"id": t.get("id")}
            out.append({
                "ams": uid + 1, "slot": tid + 1, "name": _slot_name(uid, tid),
                "tray_uuid": (t.get("tray_uuid") or "").upper(), "tag_uid": t.get("tag_uid") or "",
                "type": t.get("tray_type") or "", "sub": t.get("tray_sub_brands") or "",
                "color": (t.get("tray_color") or "")[:6].upper(), "cols": [c[:6].upper() for c in t.get("cols") or []],
                "material_id": t.get("tray_info_idx") or "", "remain": _f(t.get("remain")),
                "weight": _f(t.get("tray_weight")), "active": now == str(gid),
                "humidity": int(_f(unit.get("humidity"), 0)) or None,
                "humidity_pct": hum_raw, "temp": _f(unit.get("temp")),
                "dry_time": _f(unit.get("dry_time")),
            })
    for i, ext in enumerate(_ext_trays(p)):
        out.append({
            "ams": 0, "slot": int(_f(ext.get("id"), 254 + i)), "name": _ext_name(ext.get("id"), i),
            "tray_uuid": (ext.get("tray_uuid") or "").upper(), "tag_uid": ext.get("tag_uid") or "",
            "type": ext.get("tray_type") or "", "sub": ext.get("tray_sub_brands") or "",
            "color": (ext.get("tray_color") or "")[:6].upper(), "cols": [],
            "material_id": ext.get("tray_info_idx") or "", "remain": _f(ext.get("remain")),
            "weight": _f(ext.get("tray_weight")), "active": now == str(ext.get("id")),
            "humidity": None, "humidity_pct": None, "temp": None, "dry_time": None,
        })
    return out


EMPTY_UUID = "0" * 32


def _ext_trays(p: dict) -> list:
    """External spool holders: H2 models report them in vir_slot (two holders), older models in vt_tray."""
    vir = [x for x in p.get("vir_slot") or [] if isinstance(x, dict)]
    return vir or ([p["vt_tray"]] if isinstance(p.get("vt_tray"), dict) else [])


def _ext_name(tid, i: int = 0) -> str:
    """Name of an external holder by its id (254, 255), the same names the print file mapping uses (job_weights)."""
    n = int(_f(tid, 254 + i))
    return "External spool 2" if n == 255 else "External spool"


HT_BASE = 128   # AMS HT units report ids 128-135, one slot each; tray_now and the print mapping use that id


def _gid(uid: int, tid: int) -> int:
    """Global slot number as tray_now and the print mapping use it: uid * 4 + slot, the unit id for an AMS HT."""
    return uid if uid >= HT_BASE else uid * 4 + tid


def _slot_name(uid: int, tid: int) -> str:
    return f"AMS HT {uid - HT_BASE + 1}" if uid >= HT_BASE else f"AMS {uid + 1} · Slot {tid + 1}"


def _map_name(m: int) -> str:
    """Slot name for a value of the print mapping (0-15 AMS, 128-135 AMS HT, 254/255 external holders)."""
    if m in (254, 255):
        return _ext_name(m)
    return _slot_name(m, 0) if m >= HT_BASE else _slot_name(m // 4, m % 4)


def _present(ams: dict, gid: int) -> bool:
    """Does the printer report a spool in this AMS slot? tray_exist_bits is a hex bit mask (bit = uid * 4 + slot);
    without it every slot counts as present."""
    bits = ams.get("tray_exist_bits")
    if gid >= HT_BASE:      # the bit mask only covers the 4-slot units: an AMS HT slot counts by its tray data
        return True
    try:
        return bool(int(str(bits), 16) >> gid & 1) if bits not in (None, "") else True
    except ValueError:
        return True


def ha_trays(state: dict) -> list:
    """Slots in the same shape as homeassistant.fetch_trays, so stock sync and display stay the same."""
    p = state.get("print") or {}
    ams = p.get("ams") or {}
    now = str(ams.get("tray_now", ""))
    out = []

    def one(t: dict, name: str, gid: str, unit: Optional[dict] = None) -> dict:
        """One AMS tray or external spool as a slot dict."""
        uuid = (t.get("tray_uuid") or "").upper()
        typ = t.get("tray_type") or ""
        sub = t.get("tray_sub_brands") or ""
        label = ("Bambu " + sub if sub and uuid and uuid != EMPTY_UUID else sub or typ) or "Empty"
        remain = t.get("remain")
        d = {
            "entity": f"bambu:{gid}", "name": name,
            "tray_uuid": uuid if uuid and uuid != EMPTY_UUID else None,
            "remain": remain if isinstance(remain, (int, float)) and uuid and uuid != EMPTY_UUID else -1,
            "active": now == gid, "type": typ or "Empty",
            "color": "#" + (t.get("tray_color") or "00000000").upper(),
            "filament_id": t.get("tray_info_idx") or "", "tag_uid": t.get("tag_uid") or "",
            "tray_weight": t.get("tray_weight") or 0, "label": label, "state": label,
        }
        if unit is not None:
            d.update(humidity=_f(unit.get("humidity_raw")), humidity_level=int(_f(unit.get("humidity"), 0)) or None,
                     ams_temp=_f(unit.get("temp")))
        return d

    for i, ext in enumerate(_ext_trays(p)):
        out.append(one(ext, _ext_name(ext.get("id"), i), str(ext.get("id", 254 + i))))
    for unit in ams.get("ams") or []:
        uid = int(_f(unit.get("id"), 0))
        for t in unit.get("tray") or []:
            tid = int(_f(t.get("id"), 0))
            gid = _gid(uid, tid)
            present = _present(ams, gid)
            if not present:
                t = {"id": t.get("id")}
            d = one(t, _slot_name(uid, tid), str(gid), unit)
            # the AMS reports a spool here (bit mask), but no material is set for it (no Bambu tag, not set on the
            # printer): occupied, not empty. Without the bit mask nothing is known about it.
            d["occupied"] = present if ams.get("tray_exist_bits") not in (None, "") and gid < HT_BASE else None
            if d["occupied"] and d["type"] == "Empty" and not d["tray_uuid"]:
                d.update(type="", label="", state="")
            out.append(d)
    return out


def job(state: dict) -> dict:
    p = state.get("print") or {}
    return {
        "state": (p.get("gcode_state") or "").lower(),          # idle, prepare, running, pause, finish, failed
        "progress": _f(p.get("mc_percent")),
        "remaining_min": _f(p.get("mc_remaining_time")),
        "layer": _f(p.get("layer_num")), "layers": _f(p.get("total_layer_num")),
        "name": p.get("subtask_name") or "", "file": p.get("gcode_file") or "",
        "errors": len(p.get("hms") or []), "print_error": p.get("print_error") or 0,
        "task": str(p.get("subtask_id") or p.get("task_id") or ""), "plate": int(_f(p.get("plate_idx"), 1) or 1),
        "mapping": [m for m in (p.get("mapping") or []) if isinstance(m, (int, float))],
        "slots": [_map_name(int(m)) for m in (p.get("mapping") or []) if isinstance(m, (int, float)) and int(m) >= 0 and int(m) != 65535],
    }


STATE_TEXT = {"idle": "Ready", "prepare": "Preparing", "slicing": "Preparing", "running": "Printing", "pause": "Paused",
            "finish": "Finished", "failed": "Failed", "init": "Starting", "offline": "Offline"}


def _temp(v):
    """H2 models pack current and target value into one number: (target << 16) | current."""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None, None
    return v & 0xFFFF, v >> 16


# air duct mode of the H2 series (device.airduct.modeCur), names as in Bambu Studio
AIR_MODES = {0: "Cooling", 1: "Heating", 2: "Exhaust", 3: "Full cooling"}


def printer_view(state: dict) -> dict:
    """Compact status for the printer card (including the hotend rack on the H2C)."""
    p = state.get("print") or {}
    dev = p.get("device") or {}
    jb = job(state)
    ext = ((dev.get("extruder") or {}).get("info")) or []
    noz = ((dev.get("nozzle") or {}).get("info")) or []
    rack_ids = sorted(int(n.get("id", -1)) for n in noz if int(n.get("id", -1)) >= 16)
    has_rack = bool(rack_ids)
    model = "H2C" if has_rack else "H2D" if len(ext) > 1 else ""
    temps = []
    if ext:
        # H2 series: extruder 0 is the right nozzle, 1 the left one; show left first
        for e in sorted(ext, key=lambda e: -int(e.get("id", 0))):
            cur, tar = _temp(e.get("temp"))
            if cur is not None:
                label = ("Nozzle R" if int(e.get("id", 0)) == 0 else "Nozzle L") if len(ext) > 1 else "Nozzle"
                temps.append({"label": label, "cur": cur, "tar": tar})
    else:
        temps.append({"label": "Nozzle", "cur": _f(p.get("nozzle_temper")), "tar": _f(p.get("nozzle_target_temper"))})
    temps.append({"label": "Bed", "cur": _f(p.get("bed_temper")), "tar": _f(p.get("bed_target_temper"))})
    ch = ((dev.get("ctc") or {}).get("info") or {}).get("temp")
    if ch is None:
        ch = p.get("chamber_temper")
    if ch is not None:
        temps.append({"label": "Chamber", "cur": _f(ch), "tar": None})

    def nozzle(n: dict) -> dict:
        typ = n.get("type") or ""
        return {"id": int(n.get("id", -1)), "diameter": _f(n.get("diameter")), "type": typ,
                "material": "hardened steel" if typ.startswith("H") else "stainless steel" if typ.startswith("S") else "",
                "flow": "High Flow" if typ.endswith("01") else "Standard" if typ.endswith("00") else "",
                "hours": round((_f(n.get("p_t"), 0) or 0) / 3600, 1), "filament_id": n.get("fila_id") or "",
                "color": "#" + (n.get("color_m") or "00000000")[:6] if (n.get("color_m") or "00000000")[6:8] not in ("00", "") else None,
                "sn": n.get("sn") if n.get("sn") not in (None, "N/A") else ""}
    mounted = [dict(nozzle(n), where=f"Extruder {int(n['id']) + 1}") for n in noz if int(n.get("id", -1)) < 16]
    rack = []
    if has_rack:
        by = {int(n.get("id")): n for n in noz}
        for pos in range(16, 22):
            n = by.get(pos)
            rack.append(dict(nozzle(n), where=f"Rack {pos - 15}") if n else {"id": pos, "where": f"Rack {pos - 15}", "empty": True})
    hms = p.get("hms") or []
    duct = dev.get("airduct") or {}
    air = AIR_MODES.get(duct.get("modeCur")) if isinstance(duct, dict) and duct.get("modeList") else None
    return {
        "model": model, "state": jb["state"], "state_text": STATE_TEXT.get(jb["state"], jb["state"] or "–"),
        "name": jb["name"], "progress": jb["progress"], "remaining_min": jb["remaining_min"],
        "layer": jb["layer"], "layers": jb["layers"], "temps": temps,
        "errors": len(hms), "print_error": jb["print_error"], "wifi": p.get("wifi_signal") or "",
        "light": next((l.get("mode") for l in p.get("lights_report") or [] if l.get("node") == "chamber_light"), None),
        "lights": [l.get("node") for l in p.get("lights_report") or [] if l.get("node")],
        "speed": {1: "Silent", 2: "Standard", 3: "Sport", 4: "Turbo"}.get(int(_f(p.get("spd_lvl"), 0) or 0), ""),
        "mounted": mounted, "rack": rack, "air": air,
    }


def summarize(state: dict) -> dict:
    p = state.get("print") or {}
    ts = trays(state)
    return {
        "printer": state.get("_model") or "",
        "job": job(state),
        "trays": len([t for t in ts if t["ams"]]),
        "ams_units": len((p.get("ams") or {}).get("ams") or []),
        "nozzle": f"{p.get('nozzle_diameter', '')} {p.get('nozzle_type', '')}".strip(),
        "firmware": (state.get("info") or {}).get("module", [{}])[0].get("sw_ver", "") if state.get("info") else "",
    }


# ---------------------------------------------------------------- print file via FTPS (grams per filament)

import ftplib


class _ImplicitFTP(ftplib.FTP_TLS):
    """FTPS with implicit TLS (port 990), as spoken by Bambu printers."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, session=self.sock.session)
        return conn, size


def _ftp(cfg: dict):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    f = _ImplicitFTP(context=ctx, timeout=60)
    f.connect(cfg["ip"], 990)
    f.login(USER, cfg["code"])
    f.prot_p()
    return f


def job_weights(cfg: dict, name: str, plate: int, mapping: list) -> dict:
    """Grams per AMS slot for the running print, read from the .3mf on the printer. {} if not found."""
    import io
    import zipfile
    import xml.etree.ElementTree as ET
    if not name:
        return {}
    f = _ftp(cfg)
    try:
        cands = []
        for d in ("/cache", "/"):
            try:
                for n in f.nlst(d):
                    base = n.rsplit("/", 1)[-1]
                    if base.lower().endswith(".3mf") and base.startswith(name):
                        exact = base in (f"{name}.gcode.3mf", f"{name}.3mf")
                        cands.append((exact, d == "/cache", n))
            except ftplib.Error:
                pass
        if not cands:
            return {}
        cands.sort(reverse=True)
        buf = io.BytesIO()
        f.retrbinary("RETR " + cands[0][2], buf.write)
    finally:
        try:
            f.quit()
        except Exception:
            pass
    z = zipfile.ZipFile(buf)
    root = ET.fromstring(z.read("Metadata/slice_info.config"))
    plates = root.findall("plate")
    pl = next((p for p in plates if any(m.get("key") == "index" and m.get("value") == str(plate) for m in p.findall("metadata"))),
              plates[0] if plates else None)
    if pl is None:
        return {}
    fils = pl.findall("filament")
    out = {}
    for i, fe in enumerate(fils):
        fid = int(fe.get("id") or 0)
        if len(mapping) == len(fils):
            m = mapping[i]
        elif 0 < fid <= len(mapping):
            m = mapping[fid - 1]
        else:
            continue
        try:
            m = int(m)
            g = float(fe.get("used_g") or 0)
        except (TypeError, ValueError):
            continue
        if m < 0 or m == 65535 or g <= 0:
            continue
        slot = _map_name(m)
        out[slot] = round(out.get(slot, 0) + g, 2)
    return out


# ---------------------------------------------------------------- persistent connection

class BambuThread(threading.Thread):
    """Keeps the connection, merges the state and reports changes (on_change)."""

    def __init__(self, pid: str, on_change: Callable[[str, dict], None]):
        super().__init__(daemon=True, name=f"bambu-{pid}")
        self.pid = pid
        self._notify = on_change
        self._stop = False
        self.state = {"status": "off", "detail": "not set up (optional)"}
        self.raw: dict = {}
        self._reload = threading.Event()
        self._lock = threading.Lock()
        self._sig = None
        self._fetching = False
        self._wtry = (None, 0, 0.0)  # print file: (task, failed attempts, next attempt not before)
        self._mqtt = None        # active client while connected
        self._serial = ""
        self._bits = None        # AMS presence/reading bits of the last report
        self._soon: list = []    # times at which to ask for the full state again (after a spool change)

    def command(self, payload: dict) -> None:
        """Send a command to the printer (only while connected)."""
        c = self._mqtt
        if c is None or self.state.get("status") != "connected":
            raise ValueError("Printer is not connected")
        info = c.publish(f"device/{self._serial}/request", json.dumps(payload))
        info.wait_for_publish(5)

    def set_light(self, on: bool) -> None:
        """Switch the chamber light on or off (all reported lights, e.g. chamber_light and chamber_light2)."""
        mode = "on" if on else "off"
        with self._lock:
            reps = self.raw.get("print", {}).get("lights_report") or []
            nodes = [l.get("node") for l in reps if str(l.get("node", "")).startswith("chamber_light")] or ["chamber_light"]
        for node in nodes:
            self.command({"system": {"sequence_id": "0", "command": "ledctrl", "led_node": node, "led_mode": mode,
                                     "led_on_time": 500, "led_off_time": 500, "loop_times": 0, "interval_time": 0}})
        with self._lock:   # show it right away; the printer's next report confirms it
            for l in reps:
                if l.get("node") in nodes:
                    l["mode"] = mode
        self._changed()

    def on_change(self, res: dict) -> None:
        self._notify(self.pid, res)

    def reload(self) -> None:
        self._reload.set()

    def stop(self) -> None:
        """End the thread (printer removed)."""
        self._stop = True
        self._reload.set()

    def _status(self, status: str, detail: str = "") -> None:
        if (status, detail) != (self.state.get("status"), self.state.get("detail")):
            self.state.update(status=status, detail=detail)
            self.on_change({"status": status})

    def run(self) -> None:
        while not self._stop:
            self._reload.clear()
            cfg = get(self.pid)
            if cfg is None:
                self._status("off", "not set up (optional)")
                self._reload.wait(30)
                continue
            if not cfg.get("on", True):
                self.raw = {}
                self.state = {"status": "off", "detail": "ausgeschaltet"}
                self.on_change({"status": "off"})
                self._reload.wait(3600)
                continue
            try:
                self._session(cfg)
            except Exception as e:
                log.warning("Bambu: %s", e)
                self._status("error", str(e)[:200])
            if self._reload.wait(15):
                continue

    def _session(self, cfg: dict) -> None:
        serial = cfg["serial"]
        connected = threading.Event()
        lost = threading.Event()
        fail: dict = {}

        def on_connect(c, _u, _f, rc, _p=None):
            if getattr(rc, "is_failure", False) or getattr(rc, "value", rc) != 0:
                fail["msg"] = _rc_text(rc)
                lost.set()
                return
            log.debug("MQTT connected, subscribing")
            c.subscribe(f"device/{serial}/report")
            c.publish(f"device/{serial}/request", json.dumps(PUSHALL))
            connected.set()

        def on_disconnect(*_a):
            lost.set()

        def on_message(_c, _u, msg):
            try:
                data = json.loads(msg.payload)
            except ValueError:
                return
            with self._lock:
                merge(self.raw, data)
            self._changed()

        c = _client(serial, cfg["code"], on_message, on_connect, on_disconnect)
        try:
            c.connect(cfg["ip"], PORT, keepalive=30)
        except OSError as e:
            raise ValueError(f"Printer at {cfg['ip']} not reachable ({e.strerror or e})")
        c.loop_start()
        try:
            if not connected.wait(15):
                raise ValueError(fail.get("msg") or "No response from the printer")
            self._mqtt, self._serial = c, serial
            self._status("connected", f"{cfg['ip']}")
            last_push = time.time()
            while not lost.is_set() and not self._reload.is_set() and not self._stop:
                time.sleep(1)
                due = [x for x in self._soon if x <= time.time()]
                if due or time.time() - last_push > PUSHALL_EVERY:
                    self._soon = [x for x in self._soon if x > time.time()]
                    c.publish(f"device/{serial}/request", json.dumps(PUSHALL))
                    last_push = time.time()
            if fail:
                raise ValueError(fail["msg"])
            if lost.is_set():
                raise ValueError("Connection to the printer lost (switched off?)")
        finally:
            self._mqtt = None
            c.loop_stop()
            try:
                c.disconnect()
            except Exception:
                pass

    def _changed(self) -> None:
        with self._lock:
            ts, jb, ht = trays(self.raw), job(self.raw), ha_trays(self.raw)
            a = (self.raw.get("print") or {}).get("ams") or {}
            bits = [a.get(k) for k in ("tray_exist_bits", "tray_read_done_bits", "tray_reading_bits", "tray_is_bbl_bits")]
        if bits != self._bits:
            log.debug("AMS bits (exist, read done, reading, bambu): %s", bits)
        if bits != self._bits and self._bits is not None and self._mqtt is not None:
            # a spool was inserted, removed or its tag read: fetch the full slot data right away instead of
            # waiting for the next periodic refresh (reading the tag takes a few seconds, so ask a few times)
            now = time.time()
            self._soon = [now + 1.5, now + 6, now + 15]
        self._bits = bits
        sig = json.dumps([[(t["name"], t["tray_uuid"], t["remain"], t["active"], t["humidity"], t["type"], t["color"])
                           for t in ts], bits, jb["state"], int(jb["progress"] or 0), jb["errors"]])
        if jb["state"] in ("prepare", "running", "pause") and jb["task"] and jb["name"] \
                and self.state.get("weights_task") != jb["task"] and not self._fetching \
                and not (self._wtry[0] == jb["task"] and time.time() < self._wtry[2]):
            self._fetching = True
            threading.Thread(target=self._fetch_weights, args=(dict(jb),), daemon=True).start()
        if sig != self._sig:
            log.debug("Printer %s: job %s %s %%, trays %s", self.pid, jb["state"], int(jb["progress"] or 0),
                      "; ".join(f'{t["name"]} {t["type"] or "-"} {t["color"] or ""} {t["remain"]} % uuid {(t["tray_uuid"] or "")[:8]}' for t in ts))
            self._sig = sig
            # a full report has arrived: printers without an AMS report an empty unit list, the external
            # holder is then all there is (main._direct)
            self.state.update(trays=ht, job=jb, ams_known=isinstance(a.get("ams"), list))
            self.on_change({"trays": True})

    def _fetch_weights(self, jb: dict) -> None:
        try:
            cfg = get(self.pid)
            w = job_weights(cfg, jb["name"], jb["plate"], jb["mapping"]) if cfg else {}
            self.state.update(weights=w, weights_task=jb["task"], weights_name=jb["name"])
            log.info("Print file %s: %s", jb["name"], w)
            self.on_change({"weights": True})
        except Exception as e:
            # the printer is busy while printing and its FTP sometimes times out: try again a few times
            n = (self._wtry[1] if self._wtry[0] == jb["task"] else 0) + 1
            if n < 4:
                self._wtry = (jb["task"], n, time.time() + 30 * n)
                log.info("Reading print file (attempt %d): %s, trying again", n, e)
            else:
                log.warning("Reading print file: %s", e)
                self.state.update(weights={}, weights_task=jb["task"])
        finally:
            self._fetching = False

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self.raw)


class MockPrinter(BambuThread):
    """Simulated printer for the test instance (FILAMENT_MOCK=1): replays a saved state from
    data/mock-printer-<id>.json or data/mock-printer.json and slowly advances the print progress."""

    def run(self) -> None:
        while not self._stop:
            self._reload.clear()
            cfg = get(self.pid) or next((p for p in printers() if p["id"] == self.pid), None)
            if cfg is None or not cfg.get("on", True):
                self.raw = {}
                self.state = {"status": "off", "detail": "switched off" if cfg else "not set up (optional)"}
                self.on_change({"status": "off"})
                self._reload.wait(3600)
                continue
            for f in (db.DATA_DIR / f"mock-printer-{self.pid}.json", db.DATA_DIR / "mock-printer.json"):
                if f.exists():
                    with self._lock:
                        self.raw = json.loads(f.read_text(encoding="utf-8"))
                    break
            self._serial = cfg.get("serial") or ""
            self._status("connected", cfg.get("ip") or "")
            self._changed()
            while not self._reload.wait(10) and not self._stop:
                with self._lock:
                    pr = self.raw.setdefault("print", {})
                    if pr.get("gcode_state") == "RUNNING":
                        pr["mc_percent"] = min(100, int(pr.get("mc_percent") or 0) + 1)
                self._changed()

    def command(self, payload: dict) -> None:
        pass

    def _fetch_weights(self, jb: dict) -> None:
        self.state.update(weights=self.raw.get("_mock_weights") or {}, weights_task=jb["task"], weights_name=jb["name"])
        self._fetching = False
        self.on_change({"weights": True})
