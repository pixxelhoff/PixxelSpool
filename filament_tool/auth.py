"""Optional password for the app (off by default).

data/auth.json (readable by the owner only) holds a scrypt hash of the password, a scrypt hash of the recovery code
and a random secret that signs the login cookies. Nothing of it is ever sent to the UI.

Forgotten password, without any mail server:
- the recovery code shown once when the password was set, or
- on the Pi:  cd ~/pixxelspool && .venv/bin/python -m filament_tool.auth reset
  (Windows app: tray menu, Mac app: menu bar icon, "Reset password"). Both remove the password and all
  passkeys; the data stays untouched.

Passkeys (WebAuthn) are an optional second way to sign in while the password is on. Browsers allow them only on a
secure address (HTTPS, e.g. the Tailscale address https://<name>.ts.net, or localhost). Each passkey is bound to the
address it was made on. The table "passkeys" in the database holds only public keys, never anything secret.

Usage: python -m filament_tool.auth status | reset
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time

from . import db

PATH = db.DATA_DIR / "auth.json"
COOKIE = "pixxelspool_auth"
DAYS = 30                     # "stay signed in": this long per device
_lock = threading.Lock()
_fails: list = []             # times of recent failed attempts (slows down guessing)
_locked_until = 0.0           # no attempt is checked before this time
FREE_TRIES = 5                # wrong attempts within WINDOW before the lock starts
WINDOW = 900                  # seconds
LOCK_FIRST = 30               # first lock in seconds, doubles with every further wrong attempt
LOCK_MAX = 900


class Locked(ValueError):
    pass


def _load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    with open(os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, PATH)


def _hash(text: str, salt: str) -> str:
    return hashlib.scrypt(text.encode("utf-8"), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32).hex()


def _check(text: str, stored: dict) -> bool:
    return bool(stored) and hmac.compare_digest(_hash(text, stored["salt"]), stored["hash"])


def _new(text: str) -> dict:
    salt = secrets.token_hex(16)
    return {"salt": salt, "hash": _hash(text, salt)}


def _norm_code(code: str) -> str:
    return "".join(ch for ch in str(code).upper() if ch.isalnum())


def enabled() -> bool:
    return bool(_load().get("password"))


def _new_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"            # no 0/O, 1/I
    raw = "".join(secrets.choice(alphabet) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def _throttle() -> None:
    """Brute-force protection for password and recovery code (all devices together): after 5 wrong attempts within
    15 minutes no attempt is checked for 30 seconds, after each further wrong one twice as long (at most 15 minutes).
    A device that is signed in stays signed in; the reset on the device itself always works."""
    with _lock:
        wait = _locked_until - time.time()
    if wait > 0:
        raise Locked(f"Too many wrong attempts. Please try again in {_wait_text(wait)}.")


def _wait_text(seconds: float) -> str:
    s = int(seconds + 0.999)
    return f"{s} s" if s < 90 else f"{(s + 59) // 60} min"


def _fail() -> None:
    global _locked_until
    now = time.time()
    with _lock:
        _fails[:] = [t for t in _fails if now - t < WINDOW] + [now]
        over = len(_fails) - FREE_TRIES
        if over >= 0:
            _locked_until = now + min(LOCK_MAX, LOCK_FIRST * 2 ** over)


def check_password(password: str) -> bool:
    _throttle()
    ok = _check(password or "", _load().get("password") or {})
    if not ok:
        _fail()
    else:
        with _lock:
            _fails.clear()
    return ok


# ------------------------------------------------------------------ login cookie
def token(days: int = DAYS) -> str:
    exp = int(time.time()) + days * 86400
    sig = hmac.new(bytes.fromhex(_load()["secret"]), str(exp).encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def valid(tok: str) -> bool:
    data = _load()
    if not data.get("password"):
        return True                       # no password set: everything is open, as before
    try:
        exp, sig = str(tok or "").split(".", 1)
        good = hmac.new(bytes.fromhex(data["secret"]), exp.encode(), hashlib.sha256).hexdigest()
        return int(exp) > time.time() and hmac.compare_digest(sig, good)
    except (ValueError, KeyError):
        return False


# ------------------------------------------------------------------ changes
def set_password(password: str) -> str:
    """Turn the password on or change it. Signs out all other devices. Returns a new recovery code."""
    if len(password or "") < 6:
        raise ValueError("The password needs at least 6 characters")
    code = _new_code()
    with _lock:
        _save({"password": _new(password), "recovery": _new(_norm_code(code)), "secret": secrets.token_hex(32),
               "since": time.strftime("%Y-%m-%d %H:%M")})
    return code


def new_recovery_code() -> str:
    code = _new_code()
    with _lock:
        data = _load()
        data["recovery"] = _new(_norm_code(code))
        _save(data)
    return code


def recover(code: str, password: str) -> str:
    """Forgotten password: the recovery code allows a new password (and gives a new code)."""
    _throttle()
    if not _check(_norm_code(code), _load().get("recovery") or {}):
        _fail()
        raise ValueError("The recovery code is not correct")
    return set_password(password)


def disable() -> None:
    """Password off (also the reset on the device): the passkeys go too, so nothing is left that opens the app."""
    with _lock:
        try:
            PATH.unlink()
        except FileNotFoundError:
            pass
    try:
        passkeys_clear()
    except Exception:   # database not there yet / locked: the password is off anyway
        pass


# ------------------------------------------------------------------ passkeys (WebAuthn)
RP_NAME = "PixxelSpool"
USER_ID = b"pixxelspool-owner"     # PixxelSpool has a single owner: all passkeys belong to it
CHALLENGE_TTL = 300                # seconds a sign-in or registration started in the browser stays valid
_challenges: dict = {}             # ticket -> (kind, challenge, rp_id, expires)

_PK_TABLE = """CREATE TABLE IF NOT EXISTS passkeys (
    id INTEGER PRIMARY KEY,
    cred_id TEXT NOT NULL UNIQUE,
    public_key BLOB NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    rp_id TEXT NOT NULL,
    name TEXT,
    transports TEXT,
    created TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    last_used TEXT
)"""


def passkeys_available() -> bool:
    """The WebAuthn library is installed (missing e.g. when an update could not install the new packages)."""
    try:
        import webauthn  # noqa: F401
        return True
    except Exception:
        return False


def _pk_db():
    conn = db.connect()
    conn.execute(_PK_TABLE)     # also after restoring a backup from before passkeys existed
    return conn


def passkeys_list() -> list:
    conn = _pk_db()
    try:
        rows = conn.execute("SELECT id, name, rp_id, created, last_used FROM passkeys ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def passkeys_count() -> int:
    try:
        conn = _pk_db()
    except Exception:
        return 0
    try:
        return conn.execute("SELECT COUNT(*) FROM passkeys").fetchone()[0]
    finally:
        conn.close()


def passkey_remove(pk_id: int) -> None:
    conn = _pk_db()
    try:
        conn.execute("DELETE FROM passkeys WHERE id = ?", (int(pk_id),))
        conn.commit()
    finally:
        conn.close()


def passkey_rename(pk_id: int, name: str) -> None:
    name = " ".join(str(name or "").split())[:60]
    if not name:
        raise ValueError("Please enter a name")
    conn = _pk_db()
    try:
        conn.execute("UPDATE passkeys SET name = ? WHERE id = ?", (name, int(pk_id)))
        conn.commit()
    finally:
        conn.close()


def passkeys_clear() -> None:
    conn = _pk_db()
    try:
        conn.execute("DELETE FROM passkeys")
        conn.commit()
    finally:
        conn.close()


def _origins(rp_id: str, host: str) -> list:
    """Origins the browser may report: always HTTPS; plain http only for localhost (a secure context, too)."""
    out = [f"https://{host}"]
    if rp_id in ("localhost", "127.0.0.1"):
        out.append(f"http://{host}")
    return out


def _ticket(kind: str, challenge: bytes, rp_id: str) -> str:
    now = time.time()
    tid = secrets.token_urlsafe(16)
    with _lock:
        for k in [k for k, v in _challenges.items() if v[3] < now]:
            del _challenges[k]
        if len(_challenges) > 50:                       # nobody starts that many at once: drop the oldest
            for k in sorted(_challenges, key=lambda k: _challenges[k][3])[:len(_challenges) - 50]:
                del _challenges[k]
        _challenges[tid] = (kind, challenge, rp_id, now + CHALLENGE_TTL)
    return tid


def _take(tid: str, kind: str, rp_id: str) -> bytes:
    with _lock:
        item = _challenges.pop(str(tid or ""), None)
    if not item or item[0] != kind or item[2] != rp_id or item[3] < time.time():
        raise ValueError("The passkey request has expired. Please try again.")
    return item[1]


def passkey_register_options(rp_id: str) -> dict:
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                                          ResidentKeyRequirement, UserVerificationRequirement)
    from webauthn.helpers import base64url_to_bytes
    conn = _pk_db()
    try:
        have = [r[0] for r in conn.execute("SELECT cred_id FROM passkeys WHERE rp_id = ?", (rp_id,))]
    finally:
        conn.close()
    opts = generate_registration_options(
        rp_id=rp_id, rp_name=RP_NAME, user_id=USER_ID, user_name="PixxelSpool", user_display_name="PixxelSpool",
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.REQUIRED,
                                                               user_verification=UserVerificationRequirement.REQUIRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c)) for c in have])
    return {"ticket": _ticket("reg", opts.challenge, rp_id), "options": json.loads(options_to_json(opts))}


def passkey_register(rp_id: str, host: str, ticket: str, credential: dict, name: str) -> dict:
    from webauthn import verify_registration_response
    from webauthn.helpers import bytes_to_base64url
    challenge = _take(ticket, "reg", rp_id)
    try:
        v = verify_registration_response(credential=credential, expected_challenge=challenge, expected_rp_id=rp_id,
                                         expected_origin=_origins(rp_id, host), require_user_verification=True)
    except Exception as e:
        raise ValueError(f"The passkey could not be checked: {e}")
    transports = (credential.get("response") or {}).get("transports") or []
    name = " ".join(str(name or "").split())[:60] or "Passkey"
    conn = _pk_db()
    try:
        cur = conn.execute("INSERT INTO passkeys (cred_id, public_key, sign_count, rp_id, name, transports) VALUES (?,?,?,?,?,?)",
                           (bytes_to_base64url(v.credential_id), v.credential_public_key, v.sign_count, rp_id, name,
                            json.dumps([str(t) for t in transports][:8])))
        conn.commit()
        return {"id": cur.lastrowid, "name": name}
    except Exception:
        raise ValueError("This passkey is already saved")
    finally:
        conn.close()


def passkey_login_options(rp_id: str) -> dict:
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import UserVerificationRequirement
    # no list of allowed keys: the browser offers the passkeys it has for this address (discoverable credentials)
    opts = generate_authentication_options(rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED)
    return {"ticket": _ticket("auth", opts.challenge, rp_id), "options": json.loads(options_to_json(opts))}


def passkey_login(rp_id: str, host: str, ticket: str, credential: dict) -> bool:
    from webauthn import verify_authentication_response
    challenge = _take(ticket, "auth", rp_id)
    cred_id = str((credential or {}).get("rawId") or (credential or {}).get("id") or "")
    conn = _pk_db()
    try:
        row = conn.execute("SELECT id, public_key, sign_count, rp_id FROM passkeys WHERE cred_id = ?", (cred_id,)).fetchone()
        if not row or row["rp_id"] != rp_id:
            raise ValueError("This passkey is not known to PixxelSpool (any more). Please sign in with the password.")
        try:
            v = verify_authentication_response(credential=credential, expected_challenge=challenge, expected_rp_id=rp_id,
                                               expected_origin=_origins(rp_id, host), credential_public_key=row["public_key"],
                                               credential_current_sign_count=row["sign_count"], require_user_verification=True)
        except Exception as e:
            raise ValueError(f"The passkey could not be checked: {e}")
        conn.execute("UPDATE passkeys SET sign_count = ?, last_used = datetime('now', 'localtime') WHERE id = ?",
                     (v.new_sign_count, row["id"]))
        conn.commit()
        with _lock:
            _fails.clear()
        return True
    finally:
        conn.close()


# ------------------------------------------------------------------ password-protected backup files
MAGIC = b"PXSPENC1"             # file starts with this, then salt (16), nonce (12), AES-GCM ciphertext


def _key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 15, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)


def encrypt_file(data: bytes, password: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if len(password or "") < 6:
        raise ValueError("The password needs at least 6 characters")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    return MAGIC + salt + nonce + AESGCM(_key(password, salt)).encrypt(nonce, data, MAGIC)


def decrypt_file(blob: bytes, password: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag
    salt, nonce, body = blob[8:24], blob[24:36], blob[36:]
    try:
        return AESGCM(_key(password or "", salt)).decrypt(nonce, body, MAGIC)
    except InvalidTag:
        raise ValueError("Wrong password for this backup")


if __name__ == "__main__":
    cmd = (sys.argv[1:] or ["status"])[0]
    if cmd == "reset":
        disable()
        print("Password and passkeys removed. PixxelSpool opens without a password again; set a new one in Options › System.")
        print("Restart is not needed.")
    elif cmd == "status":
        print("Password: " + ("on" if enabled() else "off"))
        print(f"Passkeys: {passkeys_count()}")
    else:
        print(__doc__)
        sys.exit(1)
