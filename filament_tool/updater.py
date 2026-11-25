"""Updates from GitHub: find a new version, download, install, roll back to an earlier version.

Versions are the repository's git tags (vX.Y.Z). An update downloads the release archive of the tag
(pixxelspool-X.Y.Z.tar.gz, made by the workflow .github/workflows/pi.yml), checks its SHA-256 checksum against
pixxelspool-X.Y.Z.tar.gz.sha256 of the same release, backs up the database and the current program files
(versionen/vX.Y.Z) and then swaps the program files.
For an install made with git clone the tag is fetched and checked out instead; the checked release archive must
name the same commit as the fetched tag.
data/ and .venv/ are never touched. Afterwards the process exits and systemd starts it again.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from . import __version__, db, guard, host

log = logging.getLogger(__name__)

REPO = os.environ.get("PIXXELSPOOL_REPO", "pixxelhoff/pixxelspool")
API = os.environ.get("PIXXELSPOOL_UPDATE_API", "https://api.github.com")
RAW = os.environ.get("PIXXELSPOOL_UPDATE_RAW", "https://raw.githubusercontent.com")
DL = os.environ.get("PIXXELSPOOL_UPDATE_DL", "https://github.com")          # release downloads
ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".update"
VERSIONS = ROOT / "versionen"
KEEP = {"data", ".venv", "versionen", "archiv", "archiv-mac", ".update", ".git"}   # never replaced
MAX_BYTES = 60 * 1024 * 1024
CACHE_SECONDS = 6 * 3600
UA = {"User-Agent": "PixxelSpool-Updater", "Accept": "application/vnd.github+json"}

_lock = threading.Lock()
_cache: dict = {}
_job: dict = {"running": False, "phase": "", "error": "", "done": False}


def _ver(s: str) -> Optional[tuple]:
    """'v1.19.0' -> (1, 19, 0, 1, 0); prereleases sort before the final and in the order alpha < beta < rc:
    '1.0.0-alpha.2' -> (1, 0, 0, 0, 2), '1.0.0-beta.1' -> (1, 0, 0, 0, 1001), '1.0.0-rc.1' -> (1, 0, 0, 0, 2001);
    Windows-only patches like '1.0.0-patch.1' -> (1, 0, 0, 2, 1) sort after the final (and before 1.0.1)."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-(?:(alpha|beta|rc)|(patch))\.?(\d+))?", (s or "").strip())
    if not m:
        return None
    a, b, c, pre, patch, n = m.groups()
    stage = {"alpha": 0, "beta": 1000, "rc": 2000}.get(pre or "", 0)
    return (int(a), int(b), int(c), 0 if pre else 2 if patch else 1, stage + int(n or 0))


def _prerelease(v: Optional[tuple]) -> bool:
    return bool(v) and v[3] == 0


class NotFound(ValueError):
    pass


def _get(url: str, timeout: float = 15, limit: int = 2 * 1024 * 1024) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NotFound("Update source not found (repository private or renamed?)")
        if e.code == 403:
            raise ValueError("GitHub reported too many requests. Please check again in an hour.")
        raise ValueError(f"GitHub responded with error {e.code}")
    except (urllib.error.URLError, OSError) as e:
        log.warning("GitHub request failed: %r", e)
        raise ValueError(_net_error(e)) from e
    if len(data) > limit:
        raise ValueError("Download too large")
    return data


def _net_error(e: Exception) -> str:
    """Plain-words reason why GitHub could not be reached (no internet, certificate, timeout ...)."""
    reason = getattr(e, "reason", e)
    if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason):
        return "Secure connection to GitHub failed: the certificate could not be checked. Is the date and time on this device correct?"
    if isinstance(reason, ssl.SSLError):
        return "Secure connection to GitHub failed. A firewall or proxy may be blocking it."
    if isinstance(reason, socket.gaierror):
        return "No internet connection: the address of GitHub could not be found."
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "GitHub did not answer in time. Please try again later."
    if isinstance(reason, (ConnectionRefusedError, ConnectionResetError)):
        return "The connection to GitHub was interrupted. A firewall or proxy may be blocking it."
    detail = getattr(reason, "strerror", None) or reason.__class__.__name__
    return f"GitHub not reachable ({detail}). Is this device connected to the internet?"


def changelog_name() -> str:
    """The changelog is written in English and German; Spanish (and everything else) reads the English one."""
    from . import settings
    return "CHANGELOG.de.md" if settings.lang() == "de" else "CHANGELOG.md"


SECTION = re.compile(r"## \[(\d+\.\d+\.\d+(?:-(?:alpha|beta|rc|patch)\.?\d+)?)\]")


def security_versions(changelog: str, current: tuple) -> list:
    """Versions newer than `current` whose changelog section has a "### Security" part (security releases)."""
    found, ver = [], None
    for line in changelog.splitlines():
        m = SECTION.match(line)
        if m:
            v = _ver(m.group(1))
            ver = m.group(1) if v and v > current else None
        elif ver and line.strip().lower().startswith("### security"):
            found.append(ver)
            ver = None
    return found


def _notes(tag: str, current: tuple) -> str:
    """CHANGELOG sections of the new version that are newer than the running one."""
    try:
        text = _get(f"{RAW}/{REPO}/{tag}/{changelog_name()}", limit=1024 * 1024).decode("utf-8", "replace")
    except ValueError:
        return ""
    out, keep = [], False
    for line in text.splitlines():
        m = re.match(r"## \[(\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.?\d+)?)\]", line)
        if m:
            keep = (_ver(m.group(1)) or (0,)) > current
        if keep:
            out.append(line)
    return "\n".join(out).strip()[:6000]


def local_notes(since: str) -> str:
    """CHANGELOG sections of the installed changelog newer than `since` (up to the running version),
    for the "what's new" dialog after an update."""
    low, cur = _ver(since), _ver(__version__)
    if not low or not cur or low >= cur:
        return ""
    try:
        path = ROOT / changelog_name()
        text = (path if path.exists() else ROOT / "CHANGELOG.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    out, keep = [], False
    for line in text.splitlines():
        m = re.match(r"## \[(\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.?\d+)?)\]", line)
        if m:
            v = _ver(m.group(1)) or (0,)
            keep = low < v <= cur
        if keep:
            out.append(line)
    return "\n".join(out).strip()[:8000]


def local_versions() -> list:
    """Versions to roll back to, newest first (without the running one): git tags or saved copies in versionen/."""
    cur = _ver(__version__)
    found = []
    if git_checkout():
        p = _git("tag", "-l", "v*", check=False)
        for name in p.stdout.split():
            v = _ver(name)
            if v and v < cur:
                found.append((v, name))
    elif VERSIONS.is_dir():
        for p in VERSIONS.iterdir():
            v = _ver(p.name)
            if v and v < cur and (p / "filament_tool" / "main.py").exists():
                found.append((v, p.name))
    return [n for _, n in sorted(found, reverse=True)][:12]


def git_checkout() -> bool:
    return (ROOT / ".git").exists() and shutil.which("git") is not None


def _git(*args: str, check: bool = True, timeout: float = 120) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if check and p.returncode != 0:
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-1:] or ["?"]
        raise ValueError("git: " + tail[0][:200])
    return p


def _run_git(tag: str, restart, auto: bool = False) -> None:
    """Install made with git clone: fetch and check out the tag (the working tree must be clean)."""
    try:
        if _git("status", "--porcelain", "--untracked-files=no").stdout.strip():
            raise ValueError("Files in the PixxelSpool folder were changed. Please update there yourself with git.")
        _phase("Downloading")
        _git("fetch", "--quiet", "--tags", "--force", "origin", timeout=300)
        _phase("Checking")
        blob = _download_verified(tag)
        if _archive_commit(blob) != _git("rev-parse", f"{tag}^{{commit}}").stdout.strip():
            raise ValueError("The version fetched with git does not match the checked release. Nothing was installed.")
        ver = _git("show", f"{tag}:VERSION").stdout.strip()
        if _ver(ver) != _ver(tag):
            raise ValueError("The archive is not a valid PixxelSpool package")
        _phase("Backing up the database")
        _backup_db(f"update-{ver}")
        new_req = _git("show", f"{tag}:requirements.txt", check=False)
        if new_req.returncode == 0:
            WORK.mkdir(parents=True, exist_ok=True)
            (WORK / "requirements.txt").write_text(new_req.stdout, encoding="utf-8")
            _requirements(WORK)
        _phase("Replacing files")
        _git("-c", "advice.detachedHead=false", "checkout", "--quiet", tag)
        shutil.rmtree(WORK, ignore_errors=True)
        _finish(ver, restart, "git", auto)
    except Exception as e:
        _fail(e)


def _finish(ver: str, restart, method: str = "", auto: bool = False) -> None:
    if method and restart and host.KIND == "pi":
        guard.arm(__version__, ver, method, auto)
    with _lock:
        _job.update(running=False, done=True, phase="Finished", version=ver)
        _cache.clear()
    if restart:
        _phase("Restarting")
        threading.Timer(1.5, restart).start()


def _fail(e: Exception) -> None:
    log.warning("Update failed: %s", e)
    with _lock:
        _job.update(running=False, done=False, error=str(e) or e.__class__.__name__)


def check(force: bool = False) -> dict:
    """Look up the newest version on GitHub. The result is cached for a few hours."""
    with _lock:
        if not force and _cache and time.time() - _cache.get("ts", 0) < CACHE_SECONDS:
            return dict(_cache)
    cur = _ver(__version__) or (0, 0, 0, 1, 0)
    res = {"current": __version__, "repo": REPO, "ts": time.time(), "latest": "", "available": False, "notes": "", "error": ""}
    try:
        tags = []
        for page in range(1, 6):      # 100 tags per page; more than 100 versions exist sooner or later
            part = json.loads(_get(f"{API}/repos/{REPO}/tags?per_page=100&page={page}"))
            tags += part
            if len(part) < 100:
                break

        # pre-releases only as far as the channel in the options allows (set to the running stage while a pre-release is installed)
        from . import settings
        channel = settings.load().get("update_channel")
        floor = {"alpha": 0, "beta": 1000}.get(channel)      # alpha < 1000 <= beta < 2000 <= rc (see _ver)

        def wanted(v: Optional[tuple]) -> bool:
            return (bool(v) and (not _prerelease(v) or (floor is not None and v[4] >= floor))
                    and (v[3] != 2 or host.DESKTOP_APP))     # -patch.N only for the Windows and Mac app

        # security releases are always offered: also with the switch on "Off" while a beta runs (beta.2: the
        # switch only decides about normal pre-releases, a beta installation still gets beta security fixes)
        stage = (cur[4] // 1000) * 1000 if _prerelease(cur) else None

        def wanted_sec(v: Optional[tuple]) -> bool:
            return wanted(v) or (bool(v) and stage is not None and _prerelease(v) and v[4] >= stage and v[3] != 2)
        best = max(((_ver(t.get("name", "")), t["name"]) for t in tags if wanted(_ver(t.get("name", "")))), default=None)
        if best:
            res["latest"] = best[1].lstrip("v")
            res["available"] = best[0] > cur
            if res["available"]:
                res["tag"] = best[1]
                res["notes"] = _notes(best[1], cur)
                if host.DESKTOP_APP:    # the app cannot replace itself: download the new installer / disk image
                    res["download"] = f"https://github.com/{REPO}/releases/tag/{best[1]}"
        # security releases (marked in the English changelog) between the running and the newest eligible version
        top_any = max(((_ver(t.get("name", "")), t["name"]) for t in tags if wanted_sec(_ver(t.get("name", "")))), default=None)
        if top_any and top_any[0] > cur:
            try:
                text = _get(f"{RAW}/{REPO}/{top_any[1]}/CHANGELOG.md", limit=1024 * 1024).decode("utf-8", "replace")
            except ValueError:
                text = ""
            names = {t.get("name", "") for t in tags}
            sec = [(_ver(v), "v" + v) for v in security_versions(text, cur) if "v" + v in names and wanted_sec(_ver(v))]
            if sec:
                top = max(sec)
                res["security"], res["security_tag"] = top[1].lstrip("v"), top[1]
                if not res["available"]:     # only a security release is new (switch on "Off" during the beta)
                    res["available"], res["latest"], res["tag"] = True, top[1].lstrip("v"), top[1]
                    res["notes"] = _notes(top[1], cur)
                    if host.DESKTOP_APP:
                        res["download"] = f"https://github.com/{REPO}/releases/tag/{top[1]}"
    except (ValueError, KeyError, TypeError) as e:
        res["error"] = str(e)
    with _lock:
        _cache.clear()
        _cache.update(res)
    return dict(res)


def status() -> dict:
    """State for the options page: running version, update job, cached check, rollback versions."""
    with _lock:
        out = {"current": __version__, "job": dict(_job), "check": dict(_cache) if _cache else None}
    out["rollback"] = local_versions()
    out["git"] = git_checkout()
    out["service"] = host.can_restart()
    out["self_update"] = host.SELF_UPDATE
    return out


# ------------------------------------------------------------------ installing

def _phase(text: str) -> None:
    with _lock:
        _job["phase"] = text
    log.info("Update: %s", text)


def _safe_extract(blob: bytes, dest: Path) -> Path:
    """Unpack the archive, allowing only regular files and folders inside dest. Returns the content folder."""
    dest.mkdir(parents=True)
    base = dest.resolve()
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for m in tar.getmembers():
            if not (m.isfile() or m.isdir()):
                continue
            target = (dest / m.name).resolve()
            if base not in target.parents and target != base:
                raise ValueError("Archive contains invalid paths")
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tar.extractfile(m)
                with open(target, "wb") as f:
                    shutil.copyfileobj(src, f)
                os.chmod(target, 0o755 if m.mode & 0o100 else 0o644)
    dirs = [p for p in dest.iterdir() if p.is_dir()]
    return dirs[0] if len(dirs) == 1 and not (dest / "filament_tool").exists() else dest


def _download_verified(tag: str) -> bytes:
    """The release archive of a tag, checked against the SHA-256 checksum published next to it."""
    ver = tag.lstrip("v")
    url = f"{DL}/{REPO}/releases/download/{tag}/pixxelspool-{ver}.tar.gz"
    try:
        sums = _get(url + ".sha256", limit=4096).decode("ascii", "replace")
    except NotFound:
        raise ValueError("The new version is still being prepared on GitHub. Please try again in a few minutes.")
    m = re.match(r"([0-9a-fA-F]{64})(?:\s|$)", sums.strip())
    if not m:
        raise ValueError("The checksum of the new version could not be read")
    blob = _get(url, timeout=120, limit=MAX_BYTES)
    if hashlib.sha256(blob).hexdigest() != m.group(1).lower():
        log.warning("Update %s: checksum mismatch", tag)
        raise ValueError("The download does not match its checksum. Nothing was installed.")
    return blob


def _archive_commit(blob: bytes) -> str:
    """Commit id that git archive writes into the archive header."""
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        tar.next()
        return str(tar.pax_headers.get("comment", "")).strip()


def _backup_db(label: str) -> None:
    if not db.DB_PATH.exists():
        return
    folder = db.DATA_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    target = folder / f"inventory-{datetime.now():%Y-%m-%d-%H%M%S}-before-{label}.db"
    src = sqlite3.connect(str(db.DB_PATH))
    try:
        dst = sqlite3.connect(str(target))
        with dst:
            src.backup(dst)
        dst.close()
    finally:
        src.close()


def _save_current() -> None:
    """Save the running program files to versionen/vX.Y.Z (for rollback) unless that copy exists already."""
    target = VERSIONS / f"v{__version__}"
    if (target / "filament_tool" / "main.py").exists():
        return
    tmp = VERSIONS / f".v{__version__}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for p in ROOT.iterdir():
        if p.name in KEEP or p.name.startswith("."):
            continue
        if p.is_dir():
            shutil.copytree(p, tmp / p.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(p, tmp / p.name)
    tmp.rename(target)


def _requirements(src: Path) -> None:
    new = (src / "requirements.txt")
    old = (ROOT / "requirements.txt")
    if not new.exists() or (old.exists() and old.read_bytes() == new.read_bytes()):
        return
    _phase("Installing dependencies")
    p = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", str(new)],
                       capture_output=True, text=True, timeout=900)
    if p.returncode != 0:
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-1:] or ["?"]
        raise ValueError(f"Dependencies could not be installed: {tail[0][:200]}")


def _swap(src: Path) -> None:
    """Swap the program files. Old entries move to .update/old and are moved back on failure."""
    old = WORK / "old"
    shutil.rmtree(old, ignore_errors=True)
    old.mkdir(parents=True)
    moved = []
    try:
        for p in sorted(src.iterdir()):
            if p.name in KEEP or p.name.startswith("."):
                continue
            dst = ROOT / p.name
            if dst.exists() or dst.is_symlink():
                dst.rename(old / p.name)
                moved.append(p.name)
            if p.is_dir():
                shutil.copytree(p, dst)
            else:
                shutil.copy2(p, dst)
    except Exception:
        for name in moved:   # roll back
            dst = ROOT / name
            if dst.is_dir():
                shutil.rmtree(dst, ignore_errors=True)
            elif dst.exists():
                dst.unlink()
            (old / name).rename(dst)
        raise


def _run(source: str, label: str, restart, auto: bool = False) -> None:
    try:
        shutil.rmtree(WORK, ignore_errors=True)
        WORK.mkdir(parents=True)
        if source == "github":
            _phase("Downloading")
            blob = _download_verified(label)
            _phase("Checking")
            src = _safe_extract(blob, WORK / "new")
        else:
            src = VERSIONS / source
        ver = (src / "VERSION").read_text(encoding="utf-8").strip() if (src / "VERSION").exists() else ""
        if not (src / "filament_tool" / "main.py").exists() or _ver(ver) != _ver(label):
            raise ValueError("The archive is not a valid PixxelSpool package")
        _phase("Backing up the database")
        _backup_db(f"update-{ver}")
        _phase("Backing up the current version")
        _save_current()
        _requirements(src)
        _phase("Replacing files")
        _swap(src)
        shutil.rmtree(WORK, ignore_errors=True)
        _finish(ver, restart, "copy" if source == "github" else "", auto)
    except Exception as e:
        _fail(e)


def start(target: str, restart, auto: bool = False) -> dict:
    """target: "latest" (GitHub), "security" (the newest security release on GitHub) or a folder name from
    versionen/ (roll back to that version)."""
    with _lock:
        if _job.get("running"):
            raise ValueError("An update is already running")
    if host.KIND == "windows":
        raise ValueError("On Windows please download and run the new installer")
    if host.KIND == "mac":
        raise ValueError("On the Mac please download the new version and replace the app")
    if host.KIND == "docker":
        raise ValueError("In Docker please pull the new image: docker compose pull && docker compose up -d")
    if target == "latest":
        info = check(force=True)
        if info.get("error"):
            raise ValueError(info["error"])
        if not info.get("available"):
            raise ValueError("You already have the latest version")
        source, label = "github", info["tag"]
    elif target == "security":
        info = check(force=True)
        if info.get("error"):
            raise ValueError(info["error"])
        if not info.get("security_tag"):
            raise ValueError("You already have the latest version")
        source, label = "github", info["security_tag"]
    else:
        if target not in local_versions():
            raise ValueError("This version is not saved")
        source, label = target, target
    with _lock:
        _job.clear()
        _job.update(running=True, done=False, error="", phase="Starting", target=label.lstrip("v"))
    if git_checkout():
        threading.Thread(target=_run_git, args=(label, restart, auto), daemon=True, name="update").start()
    else:
        threading.Thread(target=_run, args=(source, label, restart, auto), daemon=True, name="update").start()
    return status()


def auto_security(restart) -> str:
    """Daily, on the Pi with the option on: install the newest security release by itself.
    Returns the version that is being installed, or "" when there is nothing to do."""
    from . import settings
    st = settings.load()
    if (host.KIND != "pi" or not restart or not st.get("auto_security", True) or not st.get("update_check", True)
            or os.environ.get("FILAMENT_MOCK") == "1"):      # never on the test server
        return ""
    info = check()
    ver = info.get("security") or ""
    if not ver or ver == guard.failed_version():      # a version that did not start once is not tried again
        return ""
    with _lock:
        if _job.get("running"):
            return ""
    log.info("Installing security update %s automatically", ver)
    start("security", restart, auto=True)
    return ver
