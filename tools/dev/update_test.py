#!/usr/bin/env python3
"""Offline test of the updater against a fake GitHub made from this git repository (no network needed).

    .devenv/bin/python tools/dev/update_test.py

The fake serves the tag list, CHANGELOG.md of a tag and the release files (pixxelspool-X.tar.gz + .sha256, made
with git archive like .github/workflows/pi.yml) from a throw-away clone with two made-up newer versions: N+1 is a
security release, N+2 a normal one. Checked: the download check (good, tampered, not yet published), finding the
security release, a full update of an install without git into N+1 and the way back by the update guard (guard.py)
when the new version keeps failing to start.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = Path(tempfile.mkdtemp(prefix="pxrepo-")) / "repo"
REPO = "test/pixxelspool"
STATE = {"tamper": False, "missing": set(), "changelog": {}}
_cache = {}


def git(*args) -> bytes:
    return subprocess.run(["git", "-C", str(REPO_DIR), *args], capture_output=True, check=True).stdout


def archive(tag: str) -> bytes:
    if tag not in _cache:
        _cache[tag] = git("archive", "--format=tar.gz", f"--prefix=pixxelspool-{tag[1:]}/", tag)
    return _cache[tag]


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body: bytes, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == f"/api/repos/{REPO}/tags":
            tags = git("tag", "-l", "v*").decode().split()
            return self.send(json.dumps([{"name": t} for t in tags]).encode())
        if p.startswith(f"/raw/{REPO}/"):
            tag, name = p[len(f"/raw/{REPO}/"):].split("/", 1)
            if name == "CHANGELOG.md" and tag in STATE["changelog"]:
                return self.send(STATE["changelog"][tag].encode())
            try:
                return self.send(git("show", f"{tag}:{name}"))
            except subprocess.CalledProcessError:
                return self.send(b"", 404)
        if p.startswith(f"/dl/{REPO}/releases/download/"):
            tag, name = p[len(f"/dl/{REPO}/releases/download/"):].split("/", 1)
            if tag in STATE["missing"]:
                return self.send(b"", 404)
            blob = archive(tag)
            if name.endswith(".sha256"):
                digest = hashlib.sha256(blob + (b"x" if STATE["tamper"] else b"")).hexdigest()
                return self.send(f"{digest}  {name[:-7]}\n".encode())
            return self.send(blob)
        self.send(b"", 404)


def bump(n: int, security: bool) -> str:
    """Commit a made-up version N+n in the throw-away clone and tag it."""
    import re
    cur = (REPO_DIR / "VERSION").read_text().strip()
    m = re.fullmatch(r"(.*?)(\d+)", cur)
    new = f"{m.group(1)}{int(m.group(2)) + 1}"
    (REPO_DIR / "VERSION").write_text(new + "\n")
    init = REPO_DIR / "filament_tool" / "__init__.py"
    init.write_text(init.read_text().replace(cur, new))
    log = REPO_DIR / "CHANGELOG.md"
    text = log.read_text()
    i = text.index("\n## [")
    part = "### Security\n- Test fix.\n" if security else "### Fixed\n- Test change.\n"
    log.write_text(text[:i + 1] + f"## [{new}] – 2099-01-0{n}\n\n{part}\n" + text[i + 1:])
    git("commit", "-qam", f"test {new}")
    git("tag", f"v{new}")
    return new


def main() -> int:
    subprocess.run(["git", "clone", "-q", str(SRC_DIR), str(REPO_DIR)], check=True)
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "test")
    # the clone gets the working tree as it is now (uncommitted changes too), tagged as the running version
    files = subprocess.run(["git", "-C", str(SRC_DIR), "ls-files", "-co", "--exclude-standard", "-z"],
                           capture_output=True, check=True).stdout.decode().split("\0")
    for name in filter(None, files):
        if (SRC_DIR / name).is_file():
            (REPO_DIR / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SRC_DIR / name, REPO_DIR / name)
    git("add", "-A")
    git("commit", "-qm", "working tree", "--allow-empty")
    start = (REPO_DIR / "VERSION").read_text().strip()
    head_tag = f"v{start}"
    git("tag", "-f", head_tag)
    sec_ver = bump(1, True)
    new_ver = bump(2, False)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    os.environ.update(PIXXELSPOOL_REPO=REPO, PIXXELSPOOL_UPDATE_API=base + "/api", PIXXELSPOOL_UPDATE_RAW=base + "/raw",
                      PIXXELSPOOL_UPDATE_DL=base + "/dl", PIXXELSPOOL_DATA=tempfile.mkdtemp(prefix="pxupd-"))
    sys.path.insert(0, str(SRC_DIR))
    from filament_tool import updater

    fails = []

    def expect(name, cond):
        print(("ok    " if cond else "FAIL  ") + name)
        if not cond:
            fails.append(name)

    tag = f"v{new_ver}"
    blob = updater._download_verified(tag)
    expect("download with matching checksum", blob == archive(tag))
    expect("archive names the tag's commit", updater._archive_commit(blob) == git("rev-parse", f"{tag}^{{commit}}").decode().strip())
    STATE["tamper"] = True
    try:
        updater._download_verified(tag)
        expect("tampered download is refused", False)
    except ValueError as e:
        expect("tampered download is refused", "checksum" in str(e))
    STATE["tamper"] = False
    STATE["missing"].add(tag)
    try:
        updater._download_verified(tag)
        expect("release not published yet", False)
    except ValueError as e:
        expect("release not published yet", "still being prepared" in str(e))
    STATE["missing"].clear()

    found = updater.security_versions(git("show", f"{tag}:CHANGELOG.md").decode(), updater._ver(start))
    expect("security release found in the changelog", found == [sec_ver])
    info = updater.check(force=True)
    expect("check: newest version", info.get("latest") == new_ver and info.get("available"))
    expect("check: security release", info.get("security") == sec_ver)

    # full update of an install without git (files swapped, guard armed), then three failed starts -> way back
    inst = Path(tempfile.mkdtemp(prefix="pxinst-"))
    subprocess.run(f"git -C '{REPO_DIR}' archive {head_tag} | tar -x -C '{inst}'", shell=True, check=True)
    (inst / ".probe.py").write_text("from filament_tool import guard\nguard.on_start()\nprint(open('VERSION').read().strip())\n")
    env = {**os.environ, "INVOCATION_ID": "test", "PIXXELSPOOL_DATA": str(inst / "data"), "PYTHONDONTWRITEBYTECODE": "1"}
    code = ("import time\nfrom filament_tool import updater\n"
            "updater.start('security', lambda: None, auto=True)\n"
            "while updater._job.get('running'): time.sleep(0.2)\n"
            "print(updater._job)\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=inst, env=env, capture_output=True, text=True)
    guard_file = inst / "data" / "update-guard.json"
    expect("update to the security release", (inst / "VERSION").read_text().strip() == sec_ver)
    if (inst / "VERSION").read_text().strip() != sec_ver:
        print(out.stdout[-800:], out.stderr[-1500:])
    expect("old version saved for going back", (inst / "versionen" / head_tag / "filament_tool" / "main.py").exists())
    expect("update guard armed", guard_file.exists() and json.loads(guard_file.read_text()).get("auto") is True)
    runs = [subprocess.run([sys.executable, ".probe.py"], cwd=inst, env=env, capture_output=True, text=True).stdout.strip()
            for _ in range(3)]
    expect("two failed starts keep the new version", runs[:2] == [sec_ver, sec_ver])
    expect("third start goes back to the old version", runs[2] == start and (inst / "VERSION").read_text().strip() == start)
    res = json.loads((inst / "data" / "update-rollback.json").read_text())
    expect("way back recorded", res.get("ok") and res.get("to") == sec_ver and not guard_file.exists())
    # install made with git clone: fetch, compare with the checked release, check out; the guard goes back with git
    gi = Path(tempfile.mkdtemp(prefix="pxgit-")) / "inst"
    subprocess.run(["git", "clone", "-q", "--branch", head_tag, str(REPO_DIR), str(gi)], check=True, capture_output=True)
    (gi / ".git" / "info" / "exclude").write_text(".probe.py\ndata/\n")
    (gi / ".probe.py").write_text((inst / ".probe.py").read_text())
    genv = {**env, "PIXXELSPOOL_DATA": str(gi / "data")}
    out = subprocess.run([sys.executable, "-c", code], cwd=gi, env=genv, capture_output=True, text=True)
    expect("git install: update to the security release", (gi / "VERSION").read_text().strip() == sec_ver)
    if (gi / "VERSION").read_text().strip() != sec_ver:
        print(out.stdout[-800:], out.stderr[-1500:])
    runs = [subprocess.run([sys.executable, ".probe.py"], cwd=gi, env=genv, capture_output=True, text=True).stdout.strip()
            for _ in range(3)]
    expect("git install: third failed start goes back", runs == [sec_ver, sec_ver, start])

    import importlib
    os.environ["PIXXELSPOOL_DATA"] = str(inst / "data")
    from filament_tool import guard
    importlib.reload(guard)
    expect("failed version is skipped next time", guard.failed_version() == sec_ver)

    print("\n" + ("all passed" if not fails else f"{len(fails)} failed"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
