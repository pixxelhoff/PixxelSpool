"""Push notifications to phones (Web Push, RFC 8030/8291/8292) without an account or a PixxelSpool cloud.

Flow: the phone opens PixxelSpool via the HTTPS address (Tailscale), subscribes at its vendor's push service
(Apple, Google, Mozilla) and sends the subscription to PixxelSpool. New bell notifications are then encrypted and
posted to that service, which delivers them even while Tailscale is off on the phone. The payload is end-to-end
encrypted; the push service only sees that a message arrives.

Implemented with `cryptography` only (no pywebpush). Keys and devices live in data/push.json (owner-readable only).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import struct
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from . import db, settings

log = logging.getLogger(__name__)

PATH = db.DATA_DIR / "push.json"
SUBJECT = "https://github.com/pixxelhoff"
_lock = threading.Lock()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _hmac(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


# ------------------------------------------------------------------ storage

def _load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    with open(os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    tmp.replace(PATH)


def _key():
    """VAPID key (P-256); generated on first use."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    with _lock:
        d = _load()
        if not d.get("vapid"):
            k = ec.generate_private_key(ec.SECP256R1())
            d["vapid"] = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()).decode()
            _save(d)
        return serialization.load_pem_private_key(d["vapid"].encode(), None)


def _raw_pub(k) -> bytes:
    from cryptography.hazmat.primitives import serialization
    return k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def public_key() -> str:
    return _b64(_raw_pub(_key()))


def devices() -> list:
    return [{"id": s["id"], "name": s.get("name", ""), "created": s.get("created", ""), "last_ok": s.get("last_ok", ""),
             "error": s.get("error", "")} for s in _load().get("subs", [])]


def subscribe(sub: dict, name: str = "") -> dict:
    """Store a browser PushSubscription (endpoint + keys). Re-subscribing replaces the old entry."""
    ep = str(sub.get("endpoint") or "")
    keys = sub.get("keys") or {}
    if not ep.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
        raise ValueError("Invalid push subscription")
    try:
        if len(_unb64(keys["p256dh"])) != 65 or len(_unb64(keys["auth"])) != 16:
            raise ValueError
    except Exception:
        raise ValueError("Invalid push subscription")
    with _lock:
        d = _load()
        subs = [s for s in d.get("subs", []) if s["endpoint"] != ep]
        entry = {"id": hashlib.sha1(ep.encode()).hexdigest()[:12], "endpoint": ep,
                 "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}, "name": str(name)[:60],
                 "created": datetime.now().isoformat(timespec="seconds")}
        subs.append(entry)
        d["subs"] = subs
        _save(d)
    return {"id": entry["id"]}


def unsubscribe(sub_id: str = "", endpoint: str = "") -> None:
    with _lock:
        d = _load()
        d["subs"] = [s for s in d.get("subs", []) if s["id"] != sub_id and s["endpoint"] != endpoint]
        _save(d)


# ------------------------------------------------------------------ encryption and delivery

def _encrypt(payload: bytes, p256dh: str, auth: str) -> bytes:
    """Encrypt a payload as aes128gcm according to RFC 8291 (single record)."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    ua_pub = _unb64(p256dh)
    secret = _unb64(auth)
    eph = ec.generate_private_key(ec.SECP256R1())
    as_pub = _raw_pub(eph)
    shared = eph.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub))
    ikm = _hmac(_hmac(secret, shared), b"WebPush: info\x00" + ua_pub + as_pub + b"\x01")
    salt = os.urandom(16)
    prk = _hmac(salt, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack("!IB", 4096, len(as_pub)) + as_pub + body


def _vapid(endpoint: str) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    k = _key()
    u = urlparse(endpoint)
    head = _b64(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = _b64(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": SUBJECT},
                             separators=(",", ":")).encode())
    r, s = decode_dss_signature(k.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
    token = f"{head}.{claims}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={token}, k={_b64(_raw_pub(k))}"


def _send_one(sub: dict, data: bytes, urgency: str) -> Optional[int]:
    req = urllib.request.Request(sub["endpoint"], data=_encrypt(data, sub["keys"]["p256dh"], sub["keys"]["auth"]),
                                 method="POST", headers={
                                     "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
                                     "TTL": "86400", "Urgency": urgency, "Authorization": _vapid(sub["endpoint"])})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def send(title: str, body: str = "", url: str = "/", tag: str = "", urgency: str = "normal", only: str = "") -> dict:
    """Send to all devices (or only one). Subscriptions the service reports as gone (404/410) are removed."""
    subs = [s for s in _load().get("subs", []) if not only or s["id"] == only]
    if not subs:
        return {"sent": 0, "failed": 0}
    data = json.dumps({"title": title, "body": body, "url": url, "tag": tag}, ensure_ascii=False).encode()
    ok = failed = 0
    gone, status = [], {}
    for s in subs:
        try:
            code = _send_one(s, data, urgency)
        except Exception as e:   # network down or similar
            code, err = None, str(e)[:120]
        else:
            err = "" if code and code < 300 else f"HTTP {code}"
        if code in (404, 410):
            gone.append(s["id"])
        elif code and code < 300:
            ok += 1
        else:
            failed += 1
        status[s["id"]] = err
    with _lock:
        d = _load()
        now = datetime.now().isoformat(timespec="seconds")
        for s in d.get("subs", []):
            if s["id"] in status:
                s["error"] = status[s["id"]]
                if not status[s["id"]]:
                    s["last_ok"] = now
        d["subs"] = [s for s in d.get("subs", []) if s["id"] not in gone]
        _save(d)
    if failed:
        log.info("Push: %d delivered, %d failed", ok, failed)
    return {"sent": ok, "failed": failed, "removed": len(gone)}


# ------------------------------------------------------------------ bell notifications as push

_dict_cache: dict = {}


def _tr(text: str) -> str:
    lang = settings.lang()
    if lang == "en":
        return text
    if lang not in _dict_cache:
        try:
            _dict_cache[lang] = json.loads((Path(__file__).parent / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _dict_cache[lang] = {}
    return _dict_cache[lang].get(text) or text


KINDS = ["print", "printer", "job", "stock", "newspool", "removed", "climate", "dry", "update"]
DEFAULT_OFF = {"removed", "newspool"}   # new kinds that start switched off


def kinds() -> list:
    k = _load().get("kinds")
    return [x for x in k if x in KINDS] if isinstance(k, list) else [x for x in KINDS if x not in DEFAULT_OFF]


def set_kinds(k: list) -> list:
    with _lock:
        d = _load()
        d["kinds"] = [x for x in KINDS if x in (k or [])]
        _save(d)
    return d["kinds"]


def notify(kind: str, title: str, args: Optional[list] = None, level: str = "info", link: str = "", key: str = "") -> None:
    """Send a bell notification as push in the background, if devices are registered and the kind is enabled."""
    d = _load()
    if not d.get("subs") or kind not in kinds():
        return
    try:
        text = _tr(title).format(*[_tr(a) if isinstance(a, str) else a for a in (args or [])])
    except (IndexError, KeyError, ValueError):
        text = title
    title, body = _split(kind, text, level, key)
    url = "/#" + link[5:] if link.startswith("slot:") else "/"
    threading.Thread(target=send, args=(title, body, url, key, "high" if level in ("bad", "warn") else "normal"),
                     daemon=True, name="push").start()


# symbol in front of the headline; the operating system already shows the app name next to it
ICONS = {"finish": "✅", "failed": "❌", "pause": "⏸️", "printer": "⚠️", "job": "🧵", "stock": "📦", "newspool": "🆕", "removed": "📤",
         "climate": "💧", "dry": "♨️", "update": "⬆️"}


def _split(kind: str, text: str, level: str = "info", key: str = "") -> tuple:
    """Bell text "Druck fertig: Benchy" -> push title "✅ Druck fertig" and body "Benchy"."""
    head, sep, rest = text.partition(": ")
    if not sep or not rest.strip():
        head, rest = text, ""
    sub = key.split(":", 1)[0] if kind == "print" else kind
    icon = ICONS.get(sub) or {"bad": "❌", "warn": "⚠️", "ok": "✅"}.get(level, "")
    return (f"{icon} {head}".strip(), rest.strip())
