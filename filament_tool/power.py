"""Raspberry Pi: notice when the Pi lost power without being shut down.

While PixxelSpool runs, a marker file in the data folder is touched every minute. A clean stop (shutdown, reboot,
service restart, update) removes it. If the marker is still there at the next start and the system has booted
since its last touch, the Pi was switched off (or lost power) while running: the bell says so once.
A crash of PixxelSpool alone does not count (no new boot), neither does a stop of the service.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from . import db, host

log = logging.getLogger(__name__)

MARKER = db.DATA_DIR / "running.marker"
TOUCH_EVERY = 60        # seconds


def _boot_time() -> float | None:
    try:
        return time.time() - float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def check_and_start() -> None:
    """At startup: report an earlier power loss, then keep the marker fresh."""
    if host.KIND != "pi":
        return
    try:
        last = MARKER.stat().st_mtime if MARKER.exists() else None
        boot = _boot_time()
        if last is not None and boot is not None and boot > last + 5:
            from . import notices
            when = datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M")
            notices.add("system", f"powerloss:{int(last)}",
                        "The Raspberry Pi was switched off without shutting down (last sign of life: {0}). "
                        "Shut it down under Options › System first, otherwise the data and the memory card can be damaged.",
                        [when], "warn", "opt:systool")
            log.warning("Power loss detected: the Pi was switched off while PixxelSpool was running (last %s)", when)
    except OSError:
        pass
    threading.Thread(target=_touch_loop, daemon=True, name="power-marker").start()


def _touch_loop() -> None:
    while True:
        try:
            MARKER.touch()
        except OSError:
            pass
        time.sleep(TOUCH_EVERY)


def clean_stop() -> None:
    """At a regular stop (systemd sends SIGTERM on shutdown, reboot and restart)."""
    if host.KIND != "pi":
        return
    try:
        MARKER.unlink()
    except OSError:
        pass
