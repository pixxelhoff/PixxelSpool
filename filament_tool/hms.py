"""Printer error messages (HMS and print errors) as readable text.

The printer only reports numbers. Bambu Lab publishes the texts per printer model and language (the same source
Bambu Studio uses). They are fetched once a week and cached in data/hms-<model>-<lang>.json.
Without internet access the UI falls back to the code plus a link to the wiki.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.request

from . import db

log = logging.getLogger(__name__)

SOURCE = "https://e.bambulab.com/query.php?lang={lang}&d={dev}"
LINK = "https://e.bambulab.com/index.php?e={ecode}&d={dev}&s=device_hms&lang={lang}"
REFRESH = 7 * 24 * 3600
LANGS = {"de": "de", "en": "en", "es": "es"}
LEVEL = {1: "bad", 2: "bad", 3: "warn", 4: "info"}   # 1 fatal, 2 serious, 3 common, 4 info

_lock = threading.Lock()
_mem: dict = {}
_loading: set = set()


def _path(dev: str, lang: str):
    return db.DATA_DIR / f"hms-{dev}-{lang}.json"


def _fetch(dev: str, lang: str) -> None:
    try:
        req = urllib.request.Request(SOURCE.format(lang=lang, dev=dev), headers={"User-Agent": "PixxelSpool"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read(8 * 1024 * 1024))["data"]
        out = {"hms": {}, "err": {}}
        for key, src in (("hms", "device_hms"), ("err", "device_error")):
            block = data.get(src) or {}
            rows = block.get(lang) or block.get("en") or []
            out[key] = {str(r["ecode"]).upper(): r.get("intro", "").strip() for r in rows if r.get("ecode")}
        if out["hms"]:
            _path(dev, lang).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            with _lock:
                _mem[(dev, lang)] = (time.time(), out)
            log.info("HMS texts loaded: %s/%s (%d)", dev, lang, len(out["hms"]))
    except Exception as e:   # no internet: codes still work without texts
        log.info("HMS texts not loaded: %s", e)
    finally:
        with _lock:
            _loading.discard((dev, lang))


def _texts(dev: str, lang: str) -> dict:
    key = (dev, lang)
    with _lock:
        hit = _mem.get(key)
    if not hit:
        p = _path(dev, lang)
        try:
            hit = (p.stat().st_mtime, json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            hit = (0, {"hms": {}, "err": {}})
        with _lock:
            _mem[key] = hit
    if time.time() - hit[0] > REFRESH:
        with _lock:
            start = key not in _loading
            _loading.add(key)
        if start:
            threading.Thread(target=_fetch, args=key, daemon=True, name="hms").start()
    return hit[1]


def _dev(serial: str) -> str:
    s = re.sub(r"[^0-9A-Za-z]", "", serial or "")[:3].upper()
    return s or "0"


def decode(hms: list, print_error: int, serial: str, lang: str) -> list:
    """Current messages as a list of {code, ecode, text, level, url}."""
    lang = LANGS.get(lang, "en")
    dev = _dev(serial)
    t = _texts(dev, lang)
    out, seen = [], set()
    for h in hms or []:
        try:
            attr, code = int(h.get("attr", 0)), int(h.get("code", 0))
        except (TypeError, ValueError, AttributeError):
            continue
        ecode = f"{attr:08X}{code:08X}"
        if ecode in seen:
            continue
        seen.add(ecode)
        out.append({"code": "_".join(ecode[i:i + 4] for i in range(0, 16, 4)), "ecode": ecode,
                    "text": t["hms"].get(ecode, ""), "level": LEVEL.get(code >> 16, "bad"),
                    "url": LINK.format(ecode=ecode, dev=dev, lang=lang)})
    try:
        pe = int(print_error or 0)
    except (TypeError, ValueError):
        pe = 0
    if pe:
        ecode = f"{pe:08X}"
        if not any(e["ecode"].startswith(ecode[:4]) and e["ecode"].endswith(ecode[4:]) for e in out):
            out.append({"code": f"{ecode[:4]}_{ecode[4:]}", "ecode": ecode, "text": t["err"].get(ecode, ""),
                        "level": "bad", "url": LINK.format(ecode=ecode, dev=dev, lang=lang)})
    return out
