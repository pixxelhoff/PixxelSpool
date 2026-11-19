"""Remote access via Tailscale: status, sign-in, HTTPS address, on/off.

The installer sets Tailscale up (./install.sh --remote) and makes the PixxelSpool user its operator
("tailscale set --operator"). This module only calls the command line tool and stores no credentials;
signing in happens through the link Tailscale shows in the browser.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from typing import Optional

from . import host

HOSTNAME = "pixxelspool"
_lock = threading.Lock()
_login: Optional[subprocess.Popen] = None


NOT_ANSWERING = "Tailscale is not answering. Open the Tailscale app, sign in there and check again."


def _ts() -> Optional[str]:
    found = shutil.which("tailscale")
    if not found and sys.platform == "darwin":    # Mac app: the command line tool sits inside Tailscale.app
        app = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
        found = app if os.path.exists(app) else None
    return found


# the Mac app's binary only acts as the command line tool when started from a terminal; without one it would
# start the app instead and print nothing. TAILSCALE_BE_CLI makes it a command line tool anyway.
_ENV = {**os.environ, "TAILSCALE_BE_CLI": "1"}


def _run(*args: str, timeout: float = 20) -> subprocess.CompletedProcess:
    return subprocess.run([_ts(), *args], capture_output=True, text=True, timeout=timeout, env=_ENV, stdin=subprocess.DEVNULL)


def _error(p: subprocess.CompletedProcess) -> str:
    msg = (p.stderr or p.stdout or "").strip().splitlines()
    text = msg[-1] if msg else f"Error {p.returncode}"
    if host.KIND == "pi" and ("access denied" in text.lower() or "operator" in text.lower()):   # set up by install.sh
        return "PixxelSpool is not allowed to control Tailscale. Run this once on the Pi: sudo tailscale set --operator=$USER"
    return text[:200]


def qr_svg(text: str, omitsize: bool = False) -> str:
    try:
        import segno
    except ImportError:
        return ""
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=5, border=2, dark="#000", light="#fff", xmldecl=False, svgns=True,
              omitsize=omitsize)
    return buf.getvalue().decode("utf-8")


def qr_label_svg(text: str, logo: bool = True, accent: str = "#d81b78") -> str:
    """QR code for printed labels: round dots, rounded corner markers in the accent color and, with `logo`, an empty
    round spot in the middle for the logo (error correction H keeps it readable). Coordinates are in modules."""
    try:
        import segno
    except ImportError:
        return ""
    qr = segno.make(text, error="h" if logo else "m", boost_error=False)
    m = [list(r) for r in qr.matrix]
    n = len(m)
    eyes = [(0, 0), (n - 7, 0), (0, n - 7)]
    in_eye = lambda x, y: any(ex <= x < ex + 7 and ey <= y < ey + 7 for ex, ey in eyes)
    c = n / 2
    hole = n * 0.13 if logo else 0                      # radius of the logo spot (about 26 % of the width)
    dots = []
    for y in range(n):
        for x in range(n):
            if m[y][x] and not in_eye(x, y) and (not hole or (x + .5 - c) ** 2 + (y + .5 - c) ** 2 > (hole + .9) ** 2):
                dots.append(f"M{x + .5:g} {y + .08:g}a.42.42 0 1 0 .001 0z")
    eye_svg = "".join(f'<rect x="{ex + .5}" y="{ey + .5}" width="6" height="6" rx="1.9" fill="none" stroke="{accent}" stroke-width="1"/>'
                      f'<rect x="{ex + 2}" y="{ey + 2}" width="3" height="3" rx=".9" fill="{accent}"/>' for ex, ey in eyes)
    b = 2                                                # quiet zone
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-b} {-b} {n + 2 * b} {n + 2 * b}">'
            f'<rect x="{-b}" y="{-b}" width="{n + 2 * b}" height="{n + 2 * b}" fill="#fff"/>'
            f'<path fill="#1a1a1a" d="{"".join(dots)}"/>{eye_svg}</svg>')


def serve_on() -> bool:
    p = _run("serve", "status", "--json")
    if p.returncode != 0:
        return False
    try:
        return bool((json.loads(p.stdout or "{}") or {}).get("TCP"))
    except ValueError:
        return False


def status() -> dict:
    """State for the options page: installed, state (NeedsLogin/Running/Stopped …), url, auth_url, qr."""
    if not _ts():
        return {"installed": False, "state": "missing"}
    try:
        p = _run("status", "--json", timeout=8)
    except (subprocess.SubprocessError, OSError) as e:
        return {"installed": True, "state": "error", "detail": str(e)[:160]}
    try:
        data = json.loads(p.stdout)
    except ValueError:   # no JSON: Tailscale not running or the CLI refused (e.g. the Mac app is closed)
        return {"installed": True, "state": "error", "detail": NOT_ANSWERING, "log": _error(p)}
    state = data.get("BackendState") or "NoState"
    me = data.get("Self") or {}
    dns = (me.get("DNSName") or "").rstrip(".")
    out = {"installed": True, "state": state, "host": dns, "tailnet": (data.get("CurrentTailnet") or {}).get("Name", ""),
           "ip": (me.get("TailscaleIPs") or [""])[0], "auth_url": data.get("AuthURL") or "",
           "https": False, "url": ""}
    if state == "Running":
        out["https"] = serve_on()
        out["url"] = f"https://{dns}" if out["https"] and dns else ""
    link = out["url"] or out["auth_url"]
    out["qr"] = qr_svg(link) if link else ""
    return out


def login() -> dict:
    """Start sign-in: `tailscale up` keeps running in the background until the link is confirmed in the browser."""
    global _login
    if not _ts():
        raise ValueError("Tailscale is not installed")
    with _lock:
        if _login is None or _login.poll() is not None:
            _login = subprocess.Popen([_ts(), "up", f"--hostname={HOSTNAME}", "--timeout=600s"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=_ENV)
    # wait briefly until Tailscale knows the sign-in link
    for _ in range(30):
        st = status()
        if st.get("auth_url") or st.get("state") == "Running":
            return st
        if _login.poll() is not None and _login.returncode:
            err = (_login.stderr.read() if _login.stderr else "") or ""
            raise ValueError(_error(subprocess.CompletedProcess([], _login.returncode, "", err)))
        threading.Event().wait(0.5)
    return status()


HTTPS_OFF = ("HTTPS is still off in your Tailscale account. At https://login.tailscale.com/admin/dns turn on MagicDNS and click “Enable HTTPS” under “HTTPS Certificates”, then try again."
             )


def enable_https(port: int) -> dict:
    """Serve PixxelSpool at https://<name>.ts.net (only reachable inside the user's own tailnet)."""
    p = _run("serve", "--bg", "--https=443", f"http://127.0.0.1:{port}", timeout=30)
    if p.returncode != 0:
        text = (p.stdout or "") + (p.stderr or "")
        m = re.search(r"https://login\.tailscale\.com/\S+", text)
        if m:   # HTTPS certificates are not enabled in the Tailscale account yet
            raise ValueError(f"First allow HTTPS in your Tailscale account: {m.group(0)}")
        if re.search(r"https|cert", text, re.I) and re.search(r"not enabled|disabled|not configured", text, re.I):
            raise ValueError(HTTPS_OFF)
        raise ValueError(_error(p))
    return status()


def disable_https() -> dict:
    p = _run("serve", "--https=443", "off")
    if p.returncode != 0:
        raise ValueError(_error(p))
    return status()


def set_on(on: bool) -> dict:
    p = _run("up", f"--hostname={HOSTNAME}", timeout=30) if on else _run("down")
    if p.returncode != 0:
        raise ValueError(_error(p))
    return status()


def logout() -> dict:
    p = _run("logout", timeout=30)
    if p.returncode != 0:
        raise ValueError(_error(p))
    return status()
