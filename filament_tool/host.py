"""Where PixxelSpool runs: Raspberry Pi / Linux service, Windows app, Mac app or a plain desktop start.

    pi       Linux, started by systemd (install.sh): power buttons, Tailscale setup, file-swapping updates
    windows  the Windows app (winapp.py, packaged with PyInstaller): tray icon, restart through the app itself,
             updates by downloading the new installer, data in %APPDATA%\\PixxelSpool
    mac      the Mac app (same winapp.py, packaged as PixxelSpool.app): menu bar icon, updates by downloading the
             new .dmg, data in ~/Library/Application Support/PixxelSpool
    docker   the Docker image (PIXXELSPOOL_DOCKER=1): data in the /data volume, restart = the container restarts
             (restart policy), updates by pulling the new image
    desktop  anything else (python run.py on a Mac or PC for development)

The data folder can always be overridden with the environment variable PIXXELSPOOL_DATA.
"""
from __future__ import annotations

import os
import shlex
import socket
import subprocess
import sys
from pathlib import Path
from typing import Optional

FROZEN = bool(getattr(sys, "frozen", False))          # packaged by PyInstaller
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
IS_MAC = sys.platform == "darwin"
SERVICE = bool(os.environ.get("INVOCATION_ID"))        # started by systemd
APP = os.environ.get("PIXXELSPOOL_APP") == "1"         # started by winapp.py
DOCKER = os.environ.get("PIXXELSPOOL_DOCKER") == "1"   # the Docker image
KIND = ("docker" if DOCKER else "pi" if IS_LINUX and SERVICE else "windows" if IS_WINDOWS and (APP or FROZEN)
        else "mac" if IS_MAC and (APP or FROZEN) else "desktop")
DESKTOP_APP = KIND in ("windows", "mac")               # packaged app: updates come as a new installer / disk image
SELF_UPDATE = KIND in ("pi", "desktop")                # can replace its own files (Docker: a new image instead)

# Level of the system setup that install.sh does (packages, rights, services). Raise it when a new version needs a
# new system step on existing installations: the Pi then asks once to run ./install.sh again ("refresh the setup").
# install.sh writes the level it set up into data/setup.json; installations from before have level 1.
SETUP_LEVEL = 1



def data_dir() -> Path:
    env = os.environ.get("PIXXELSPOOL_DATA")
    if env:
        return Path(env).expanduser().resolve()
    if KIND == "windows":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "PixxelSpool"
    if KIND == "mac":
        return Path.home() / "Library" / "Application Support" / "PixxelSpool"
    return Path(__file__).resolve().parent.parent / "data"


def can_restart() -> bool:
    return SERVICE or APP or DOCKER      # Docker: the container's restart policy starts it again


def restart() -> None:
    """Restart PixxelSpool. systemd starts the service again by itself (Restart=always); the Windows and Mac app
    start a new copy of themselves, which waits until this process has released the port."""
    if APP and not SERVICE:
        keep = [a for a in sys.argv[1:] if a != "--restarted"]     # e.g. --port
        args = [sys.executable] + ([] if FROZEN else ["-m", "filament_tool.winapp"]) + keep + ["--restarted"]
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(args, creationflags=flags, close_fds=True, start_new_session=not IS_WINDOWS)
    os._exit(0)


def mdns_name() -> str:
    """The device's name on the local network ("pixxelspool.local"), where it answers to one: the Pi (avahi), the Mac
    (Bonjour) and Linux with avahi. Empty where it is not reliable (Windows, Docker)."""
    if KIND not in ("pi", "mac") and not (IS_LINUX and Path("/run/avahi-daemon").exists()):
        return ""
    name = socket.gethostname().split(".")[0].strip().lower()
    return f"{name}.local" if name and name != "localhost" else ""


def lan_ip() -> str:
    """Address of this computer in the home network (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def os_info() -> dict:
    """The Pi's system for Options › About: name and version, Python, automatic security updates on or off."""
    out = {"name": "", "codename": "", "python": "%d.%d.%d" % sys.version_info[:3], "auto_updates": None,
           "command": f"cd {shlex.quote(str(Path(__file__).resolve().parent.parent))} && ./install.sh --os-updates", "setup_level": SETUP_LEVEL, "setup_done": setup_level()}
    try:
        rel = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
        out["name"] = rel.get("PRETTY_NAME", "").strip('"')
        out["codename"] = rel.get("VERSION_CODENAME", "").strip('"')
    except OSError:
        pass
    try:
        p = subprocess.run(["apt-config", "shell", "X", "APT::Periodic::Unattended-Upgrade"],
                           capture_output=True, text=True, timeout=10)
        on = p.returncode == 0 and "'1'" in p.stdout
        out["auto_updates"] = bool(on and Path("/usr/bin/unattended-upgrade").exists())
    except (OSError, subprocess.SubprocessError):
        pass
    return out


_cpu_last: list = []


def _cpu_percent() -> Optional[float]:
    """CPU load in percent since the last call (first call: over a short moment)."""
    def read():
        f = [int(x) for x in Path("/proc/stat").read_text().split("\n", 1)[0].split()[1:]]
        return sum(f), f[3] + (f[4] if len(f) > 4 else 0)       # total, idle + iowait
    try:
        if not _cpu_last:
            _cpu_last[:] = read()
            import time
            time.sleep(0.3)
        total, idle = read()
        dt, di = total - _cpu_last[0], idle - _cpu_last[1]
        _cpu_last[:] = [total, idle]
        return round(100 * (dt - di) / dt, 1) if dt > 0 else None
    except (OSError, ValueError, IndexError):
        return None


def system_stats() -> dict:
    """Live values of the Pi for Options › Raspberry Pi: CPU, memory, temperature, storage, uptime, power supply."""
    import time
    out: dict = {"cpu": _cpu_percent(), "cores": os.cpu_count()}
    try:
        out["load"] = [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]]
    except (OSError, ValueError):
        pass
    try:
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            mem[k] = int(v.split()[0]) * 1024
        out["mem_total"], out["mem_used"] = mem["MemTotal"], mem["MemTotal"] - mem.get("MemAvailable", mem.get("MemFree", 0))
    except (OSError, ValueError, KeyError):
        pass
    try:
        out["temp"] = round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
    except (OSError, ValueError):
        pass
    try:
        up = float(Path("/proc/uptime").read_text().split()[0])
        out["boot"] = time.time() - up
    except (OSError, ValueError):
        pass
    try:
        import shutil as _sh
        du = _sh.disk_usage(str(data_dir()))
        out["disk_total"], out["disk_used"] = du.total, du.used
    except OSError:
        pass
    try:
        p = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=5)
        flags = int(p.stdout.strip().split("=")[1], 16)
        out["power"] = "now" if flags & 0x1 else "earlier" if flags & 0x10000 else "ok"
        out["throttled"] = bool(flags & 0x6) or bool(flags & 0x60000)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return out


def setup_level() -> int:
    """Level of the system setup that install.sh did last (data/setup.json)."""
    import json
    try:
        return int(json.loads((data_dir() / "setup.json").read_text(encoding="utf-8")).get("level", 1))
    except (OSError, ValueError, TypeError, AttributeError):
        return 1


def secure_data_dir() -> None:
    """data/ holds tokens, access codes and backups: only the own user may read it (Linux and Mac)."""
    if IS_WINDOWS:
        return
    import stat
    d = data_dir()
    try:
        if d.is_dir() and stat.S_IMODE(d.stat().st_mode) & 0o077:
            os.chmod(d, 0o700)
    except OSError:
        pass


def info() -> dict:
    """For the UI: which platform features exist here."""
    return {"kind": KIND, "power": KIND == "pi", "restart": can_restart(), "pn532": IS_LINUX,   # PN532 over I2C (Pi); USB boards run as "USB reader"
            "tailscale_setup": KIND == "pi", "self_update": SELF_UPDATE}
