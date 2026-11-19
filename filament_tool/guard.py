"""Safety net after an update on the Raspberry Pi: if the new version does not start, go back to the one before.

The updater arms it (data/update-guard.json) right before it restarts into the new version. run.py calls on_start()
before anything else is imported, the running app calls confirm() once it has run for a while. If the new version
is started for the third time without a confirm (it crashed twice and systemd keeps restarting it), the program
files of the old version come back, data/update-rollback.json records what happened and the process starts again as
the old version. The database is never touched (it was backed up before the update).

Only the Python standard library is used here, so a broken or missing package cannot block the way back.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from . import host

ROOT = Path(__file__).resolve().parent.parent
GUARD = "update-guard.json"
RESULT = "update-rollback.json"
MAX_STARTS = 3          # the third start without a confirm goes back
CONFIRM_AFTER = 90      # seconds the new version has to run before it counts as working
KEEP = {"data", ".venv", "versionen", "archiv", "archiv-mac", ".update", ".git"}   # same as updater.KEEP


def _file(name: str) -> Path:
    return host.data_dir() / name


def _read(name: str) -> Optional[dict]:
    try:
        data = json.loads(_file(name).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write(name: str, data: dict) -> None:
    path = _file(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _drop(name: str) -> None:
    try:
        _file(name).unlink()
    except OSError:
        pass


def _say(text: str) -> None:
    print(f"PixxelSpool update guard: {text}", file=sys.stderr, flush=True)


def _version_on_disk() -> str:
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def arm(old: str, new: str, method: str, auto: bool = False) -> None:
    """Called by the updater just before the restart into `new` (method "git" or "copy")."""
    _write(GUARD, {"from": old, "to": new, "method": method, "auto": auto, "starts": 0, "ts": time.time()})


def on_start() -> None:
    """First thing in run.py: count the start of a freshly updated version, go back after too many failed starts."""
    g = _read(GUARD)
    if not g:
        return
    if _version_on_disk() != g.get("to"):      # changed by hand in the meantime: nothing to watch any more
        _drop(GUARD)
        return
    g["starts"] = int(g.get("starts") or 0) + 1
    _write(GUARD, g)
    if g["starts"] < MAX_STARTS:
        return
    _say(f"version {g.get('to')} did not start, going back to {g.get('from')}")
    try:
        _restore(g)
    except Exception as e:      # keep starting the new version; the log shows why the way back failed
        _say(f"going back failed: {e!r}")
        _drop(GUARD)
        _write(RESULT, {"from": g.get("from"), "to": g.get("to"), "ts": time.time(), "ok": False, "error": str(e)[:300], "seen": False})
        return
    _drop(GUARD)
    _write(RESULT, {"from": g.get("from"), "to": g.get("to"), "ts": time.time(), "ok": True, "seen": False})
    os.execv(sys.executable, [sys.executable] + sys.argv)     # start again, now as the old version


def _restore(g: dict) -> None:
    old = str(g.get("from") or "")
    new_req = _bytes(ROOT / "requirements.txt")
    if g.get("method") == "git":
        p = subprocess.run(["git", "-C", str(ROOT), "-c", "advice.detachedHead=false", "checkout", "--quiet", f"v{old}"],
                           capture_output=True, text=True, timeout=120, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if p.returncode != 0:
            raise RuntimeError((p.stderr or p.stdout or "git checkout failed").strip()[-200:])
    else:
        src = ROOT / "versionen" / f"v{old}"
        if not (src / "filament_tool" / "main.py").exists():
            raise RuntimeError(f"no saved copy of v{old}")
        broken = ROOT / ".update" / f"broken-{g.get('to')}"
        shutil.rmtree(broken, ignore_errors=True)
        broken.mkdir(parents=True)
        for p in sorted(ROOT.iterdir()):      # move the new program files aside (data/, .venv/ ... stay)
            if p.name in KEEP or p.name.startswith("."):
                continue
            p.rename(broken / p.name)
        for p in sorted(src.iterdir()):
            if p.name in KEEP or p.name.startswith("."):
                continue
            if p.is_dir():
                shutil.copytree(p, ROOT / p.name)
            else:
                shutil.copy2(p, ROOT / p.name)
    old_req = _bytes(ROOT / "requirements.txt")
    if old_req and old_req != new_req:      # best effort: the packages of the old version
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r",
                            str(ROOT / "requirements.txt")], capture_output=True, timeout=900)
        except (OSError, subprocess.SubprocessError) as e:
            _say(f"packages of the old version could not be installed: {e!r}")


def _bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def confirm(version: str) -> Optional[dict]:
    """The running version works: drop the guard. Returns the guard (with "auto") if one was confirmed."""
    g = _read(GUARD)
    if not g or g.get("to") != version:
        return None
    _drop(GUARD)
    return g


def rollback_result() -> Optional[dict]:
    """What the last automatic way back did (or None)."""
    return _read(RESULT)


def mark_seen() -> None:
    r = _read(RESULT)
    if r and not r.get("seen"):
        r["seen"] = True
        _write(RESULT, r)


def failed_version() -> str:
    """The version that had to be rolled back: automatic security updates skip it."""
    r = _read(RESULT)
    return str(r.get("to") or "") if r else ""
