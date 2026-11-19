"""Additional backup to a network share (SMB: NAS, Fritzbox, Windows) or an FTP/FTPS server.

Credentials live in data/offsite.json (readable by the owner only); the password is never sent to the UI.
The upload is a ZIP with the database and settings (no credentials) in the same format as the downloadable
backup, so it can be restored in PixxelSpool. With `encrypt` on it is password-protected like the downloadable
.pspbackup (auth.encrypt_file); that password is stored next to the share password. Older uploads beyond `keep` are deleted.
"""
from __future__ import annotations

import io
import json
import os
import socket
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import PurePosixPath
from typing import Optional

from . import db, host, settings

CONFIG = db.DATA_DIR / "offsite.json"
PREFIX = "pixxelspool-"
TYPES = ("smb", "ftp", "ftps")
EXT_LOCKED = ".pspbackup"     # password-protected upload


def load() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def public() -> dict:
    c = load()
    out = {k: c.get(k, "") for k in ("type", "host", "port", "share", "path", "user", "domain")}
    out.update(on=bool(c.get("on")), keep=int(c.get("keep") or 14), has_password=bool(c.get("password")),
               encrypt=bool(c.get("encrypt")), has_enc_password=bool(c.get("enc_password")), last=c.get("last") or {})
    return out


def save(data: dict) -> dict:
    """Validate and store the network backup settings. Returns the public view (without password)."""
    cur = load()
    typ = str(data.get("type") or "smb")
    if typ not in TYPES:
        raise ValueError("Unknown type")
    host = str(data.get("host") or "").strip()
    if not host or any(ch in host for ch in "/\\ @"):
        raise ValueError("Please enter the server name or IP address")
    try:
        port = int(data.get("port") or 0)
    except (TypeError, ValueError):
        raise ValueError("Invalid port")
    keep = max(1, min(365, int(data.get("keep") or 14)))
    new = {
        "type": typ, "host": host, "port": port if 0 < port < 65536 else 0,
        "share": str(data.get("share") or "").strip().strip("/\\"),
        "path": str(data.get("path") or "").strip().strip("/\\").replace("\\", "/"),
        "user": str(data.get("user") or "").strip(), "domain": str(data.get("domain") or "").strip(),
        "on": bool(data.get("on", True)), "keep": keep, "last": cur.get("last") or {},
        # only replace the password when a new one was entered
        "password": data["password"] if data.get("password") else cur.get("password", ""),
        "encrypt": bool(data.get("encrypt")),
        "enc_password": str(data["enc_password"]) if data.get("enc_password") else cur.get("enc_password", ""),
    }
    if new["encrypt"] and len(new["enc_password"]) < 6:
        raise ValueError("The password needs at least 6 characters")
    if typ == "smb" and not new["share"]:
        raise ValueError("Please enter the share name")
    if ".." in new["path"].split("/"):
        raise ValueError("Invalid folder")
    _write(new)
    return public()


def delete() -> None:
    if CONFIG.exists():
        CONFIG.unlink()


def _write(c: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".tmp")
    with open(os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
    tmp.replace(CONFIG)


def make_zip() -> tuple:
    """(file name, bytes) of the backup ZIP: database and settings, without credentials."""
    fd, tmpdb = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        src, dst = db.connect(), sqlite3.connect(tmpdb)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmpdb, "inventory.db")
            if settings.PATH.exists():
                z.write(settings.PATH, "settings.json")
            z.writestr("pixxelspool.json", json.dumps({"app": "PixxelSpool", "created": datetime.now().isoformat(timespec="seconds"),
                                                      "with_ha": False}))
    finally:
        os.unlink(tmpdb)
    return f"{PREFIX}{datetime.now():%Y-%m-%d-%H%M}.zip", buf.getvalue()


# ------------------------------------------------------------------ transports

class _Smb:
    def __init__(self, c: dict):
        try:
            from smb.SMBConnection import SMBConnection
        except ImportError:
            if host.KIND == "pi":
                raise ValueError("SMB needs the pysmb package. Please update PixxelSpool or run ./install.sh again.")
            raise ValueError("SMB needs the pysmb package. Please install the current version of PixxelSpool.")
        self.c = c
        self.conn = SMBConnection(c.get("user") or "guest", c.get("password") or "", "pixxelspool", c["host"],
                                  domain=c.get("domain") or "", use_ntlm_v2=True, is_direct_tcp=True)
        if not self.conn.connect(c["host"], c.get("port") or 445, timeout=20):
            raise ValueError("Sign-in to the share was rejected")
        self.share, self.base = c["share"], c.get("path") or ""

    def _p(self, name: str = "") -> str:
        return "/" + "/".join(x for x in (self.base, name) if x)

    def ensure_dir(self) -> None:
        part = ""
        for seg in [s for s in self.base.split("/") if s]:
            part = f"{part}/{seg}"
            try:
                self.conn.listPath(self.share, part)
            except Exception:
                self.conn.createDirectory(self.share, part)

    def put(self, name: str, data: bytes) -> None:
        self.conn.storeFile(self.share, self._p(name), io.BytesIO(data))

    def list(self) -> list:
        return [f.filename for f in self.conn.listPath(self.share, self._p() or "/") if not f.isDirectory]

    def remove(self, name: str) -> None:
        self.conn.deleteFiles(self.share, self._p(name))

    def close(self) -> None:
        self.conn.close()


class _Ftp:
    def __init__(self, c: dict):
        import ftplib
        self.ftp = ftplib.FTP_TLS(timeout=20) if c["type"] == "ftps" else ftplib.FTP(timeout=20)
        self.ftp.connect(c["host"], c.get("port") or 21)
        self.ftp.login(c.get("user") or "anonymous", c.get("password") or "")
        if c["type"] == "ftps":
            self.ftp.prot_p()
        self.base = c.get("path") or ""

    def ensure_dir(self) -> None:
        for seg in [s for s in self.base.split("/") if s]:
            try:
                self.ftp.cwd(seg)
            except Exception:
                self.ftp.mkd(seg)
                self.ftp.cwd(seg)

    def put(self, name: str, data: bytes) -> None:
        self.ftp.storbinary(f"STOR {name}", io.BytesIO(data))

    def list(self) -> list:
        return [PurePosixPath(n).name for n in self.ftp.nlst()]

    def remove(self, name: str) -> None:
        self.ftp.delete(name)

    def close(self) -> None:
        try:
            self.ftp.quit()
        except Exception:
            self.ftp.close()


def _connect(c: dict):
    try:
        return _Smb(c) if c["type"] == "smb" else _Ftp(c)
    except ValueError:
        raise
    except (socket.timeout, TimeoutError):
        raise ValueError("Server not responding")
    except OSError as e:
        raise ValueError(f"Server not reachable ({e.__class__.__name__})")
    except Exception as e:
        msg = str(e).strip().splitlines()[0][:160] if str(e).strip() else e.__class__.__name__
        raise ValueError(f"Sign-in failed: {msg}")


def run(force: bool = False) -> Optional[dict]:
    """Upload a backup and prune old ones. Returns None when not configured or switched off (unless forced)."""
    c = load()
    if not c.get("host") or (not c.get("on") and not force):
        return None
    result = {"ts": datetime.now().isoformat(timespec="seconds"), "ok": False}
    try:
        name, data = make_zip()
        if c.get("encrypt"):
            from . import auth
            name, data = name[:-4] + EXT_LOCKED, auth.encrypt_file(data, c.get("enc_password") or "")
        t = _connect(c)
        try:
            t.ensure_dir()
            t.put(name, data)
            mine = sorted((n for n in t.list() if n.startswith(PREFIX) and n.endswith((".zip", EXT_LOCKED))),
                          key=lambda n: n.rsplit(".", 1)[0])   # by date, whether protected or not
            removed = 0
            for old in mine[:-int(c.get("keep") or 14)]:
                try:
                    t.remove(old)
                    removed += 1
                except Exception:
                    pass
        finally:
            t.close()
        result.update(ok=True, file=name, size=len(data), removed=removed)
    except ValueError as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = (str(e).strip().splitlines() or [e.__class__.__name__])[0][:200]
    c = load()
    c["last"] = result
    _write(c)
    return result
