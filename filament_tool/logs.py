"""Application log: an in-memory ring buffer for the log viewer plus a rotating file in data/logs/.

Secrets never leave this module unredacted: the printer access code, the Home Assistant token, the network
backup password (read from their config files) and anything that looks like a token or password is replaced
by "•••" before a line is stored. The full serial number of the printer is shortened as well.
"""
from __future__ import annotations

import collections
import json
import logging
import logging.handlers
import re
import threading
import time

from . import db

LOG_DIR = db.DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "pixxelspool.log"
BUFFER = 2000             # lines kept in memory
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MASK = "•••"

# config file -> keys whose values are secret
SECRET_FILES = {"bambu.json": ("code", "access_code"), "homeassistant.json": ("token",), "offsite.json": ("password", "enc_password")}
PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\1" + MASK),
    (re.compile(r"(?i)((?:access_?code|password|passwd|token|secret|auth|p256dh|key)[\"']?\s*[:=]\s*[\"']?)[^\s\"',;&}]+"), r"\1" + MASK),
    (re.compile(r"(login\.tailscale\.com/a/)[A-Za-z0-9]+"), r"\1" + MASK),
    (re.compile(r"(https://[^\s/]*push[^\s/]*/)\S+"), r"\1" + MASK),     # push endpoints identify a device
]

_lock = threading.Lock()
_lines: collections.deque = collections.deque(maxlen=BUFFER)
_secrets: list[str] = []
_secrets_ts = 0.0


def _load_secrets() -> list[str]:
    """Secret values from the config files, refreshed at most once a minute."""
    global _secrets, _secrets_ts
    if time.time() - _secrets_ts < 60:
        return _secrets
    found = []
    for name, keys in SECRET_FILES.items():
        try:
            cfg = json.loads((db.DATA_DIR / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for c in cfg.get("printers") or [cfg] if isinstance(cfg, dict) else []:   # bambu.json holds a list of printers
            found += [str(c[k]) for k in keys if len(str(c.get(k) or "")) >= 4]
            serial = str(c.get("serial") or "")
            if len(serial) > 6:
                found.append(serial[3:])     # keep the model prefix (e.g. 31B), hide the rest
    _secrets, _secrets_ts = sorted(set(found), key=len, reverse=True), time.time()
    return _secrets


def redact(text: str) -> str:
    for s in _load_secrets():
        text = text.replace(s, MASK)
    for rx, rep in PATTERNS:
        text = rx.sub(rep, text)
    return text


class _Redacting(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class _Ring(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = redact(record.getMessage())
            if record.exc_info:
                msg += "\n" + redact(logging.Formatter().formatException(record.exc_info))
            with _lock:
                _lines.append({"ts": record.created, "level": record.levelname, "name": record.name, "msg": msg})
        except Exception:      # logging must never raise
            pass


def setup() -> None:
    """Attach the ring buffer and the rotating file to the root logger (and to uvicorn's loggers)."""
    root = logging.getLogger()
    if any(isinstance(h, _Ring) for h in root.handlers):
        return
    ring = _Ring(level=logging.INFO)
    handlers: list[logging.Handler] = [ring]
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(_Redacting(FORMAT))
        fh.setLevel(logging.INFO)
        handlers.append(fh)
    except OSError as e:
        logging.getLogger("logs").warning("Log file not available: %s", e)
    for h in handlers:
        root.addHandler(h)
    # uvicorn's own loggers do not propagate; access logs are too noisy for the viewer
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        for h in handlers:
            lg.addHandler(h)
        lg.propagate = False


# loggers of PixxelSpool itself; "detailed" switches only these to DEBUG (libraries stay quiet)
OWN = ("bambu", "reader", "homeassistant", "db", "backup", "app", "logs", "api", "filament_tool")


def set_detail(on: bool) -> None:
    """Detailed log for troubleshooting: also record DEBUG messages (printer data, reader polls, API calls)."""
    lvl = logging.DEBUG if on else logging.INFO
    for h in logging.getLogger().handlers:
        if isinstance(h, (_Ring, logging.handlers.RotatingFileHandler)):
            h.setLevel(lvl)
    for name in OWN:
        logging.getLogger(name).setLevel(lvl)


def lines(level: str = "", q: str = "", limit: int = 500) -> list[dict]:
    """Newest first. level: "" (all), "WARNING" (warnings and errors) or "ERROR"."""
    order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    floor = order.get(level.upper(), 0)
    q = q.strip().lower()
    with _lock:
        items = list(_lines)
    out = []
    for it in reversed(items):
        if order.get(it["level"], 20) < floor:
            continue
        if q and q not in (it["msg"] + " " + it["name"]).lower():
            continue
        out.append(it)
        if len(out) >= limit:
            break
    return out


def export_text() -> str:
    """Log file content (older rotated files first), else the ring buffer. Already redacted."""
    parts = []
    for f in sorted(LOG_DIR.glob("pixxelspool.log.*"), reverse=True) + [LOG_FILE]:
        try:
            parts.append(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    if parts:
        return "".join(parts)
    with _lock:
        items = list(_lines)
    return "\n".join(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(i['ts']))} {i['level']} {i['name']}: {i['msg']}"
                     for i in items) + "\n"
