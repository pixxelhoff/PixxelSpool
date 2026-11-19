#!/usr/bin/env python3
"""Check translations: collects all English source texts and compares them with filament_tool/locales/*.json.

    python3 tools/i18n.py            # show missing and unused entries per language
    python3 tools/i18n.py --keys     # print all source texts

Source texts come from
  - static/app.js and static/intro.js: strings in L("…"), Lp(n, "…", "…") and in the I18N.en table, TOUR, LIST_SORTS/LIST_FLAGS and btn("…", "…")
  - static/index.html: static text and placeholder/title/aria-label
  - Python code: error and status messages (f-strings become {0}, {1} …)
  - EXTRA below: texts that only occur as data (history, printer state …)
An empty or missing entry means the English text is shown. English is the source language, so there is no en.json.
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "filament_tool"
LOCALES = ROOT / "locales"

# Texts that are not literals in the code (values from the database or the printer)
EXTRA = [
    "{0} {1} · slot {2}", "Level", "Rod", "No reader found",
    "(switch set to HSU/UART?)", "Error {0}", "Labels", "Network backup:", "No response from the printer", "PN532 not responding ({0})", "Reserve", "Tag not readable (not a Bambu tag, or slipped)", "The place has been taken in the meantime", "all", "{0} g · {1} g left", "{0} labels · QR opens {1}", "{0} products from {1}",
    "stored", "deleted", "taken out", "put back", "empty", "moved", "swapped", "to reserve", "to live stock", "into AMS", "out of AMS",
    "linked", "assignment", "assignment undone", "reset", "dried", "import", "opened", "Tag {0}", "{0} -> product {1}", "{0} spools removed",
    "{0} (taken over from AMS)", "{0} (manual, not scanned yet)", "Rod", "Level", "connected", "error", "off", "Error",
    "Automatic", "USB reader", "PN532 board", "✓ connected", "not set up", "Ready", "Preparing", "Printing", "Paused",
    "Finished", "Failed", "Starting", "Offline", "Nozzle", "Nozzle {0}", "Nozzle L", "Nozzle R", "Bed", "Chamber",
    "hardened steel", "stainless steel", "Standard", "High Flow", "Silent", "Sport", "Turbo", "External spool",
    "External spool {0}", "Extruder {0}", "Rack {0}", "Wrong access code", "Access code rejected",
    "Access denied (developer mode needed?)", "Connection refused ({0})", "{0} AMS slots", "Camera is switched off",
    "No camera image",
    "PixxelSpool is not allowed to control Tailscale. Run this once on the Pi: sudo tailscale set --operator=$USER",
    "HTTPS is still off in your Tailscale account. At https://login.tailscale.com/admin/dns turn on MagicDNS and click “Enable HTTPS” under “HTTPS Certificates”, then try again.",
    "Print finished, cancelled, paused", "Printer errors", "Not enough filament for the print", "Spool almost empty",
    "Spool taken out of the AMS (with its storage slot)", "Taken out of the AMS: {0} goes back to slot {1}",
    "Taken out of the AMS: {0} has no storage slot yet",
    "New Bambu Lab spool in the AMS", "New spool in the AMS: {0} in {1}. Add it to storage?",
    "Humidity in storage", "Spools to dry", "New version", "Push works", "This is how PixxelSpool messages look.",
    "Downloading", "Checking", "Backing up the database", "Backing up the current version", "Installing dependencies",
    "Replacing files", "Restarting", "Update source not found (repository private or renamed?)",
    "GitHub reported too many requests. Please check again in an hour.", "GitHub responded with error {0}",
    "Secure connection to GitHub failed: the certificate could not be checked. Is the date and time on this device correct?",
    "Secure connection to GitHub failed. A firewall or proxy may be blocking it.",
    "No internet connection: the address of GitHub could not be found.", "GitHub did not answer in time. Please try again later.",
    "The connection to GitHub was interrupted. A firewall or proxy may be blocking it.",
    "GitHub not reachable ({0}). Is this device connected to the internet?",
    "Download too large", "Archive contains invalid paths",
    "The archive is not a valid PixxelSpool package", "Dependencies could not be installed: {0}",
    "An update is already running", "You already have the latest version", "This version is not saved",
    "Files in the PixxelSpool folder were changed. Please update there yourself with git.",
    "Update available: PixxelSpool {0}", "CPU", "Memory", "Temperature", "Storage space", "Power supply", "Last restart of the Pi", "PixxelSpool running since", "System",
    "Automatic system security updates", "OK", "Too many wrong attempts. Please try again in {0}.", "Security update available: PixxelSpool {0}. Please install it soon.",
    "Installing security update {0} automatically …", "Please refresh the setup once: run ./install.sh again in the PixxelSpool folder on the Pi.", "Security update {0} was installed automatically.",
    "Version {0} did not start. PixxelSpool went back to {1} by itself; your data is unchanged.",
    "Version {0} had trouble starting and going back to {1} did not work. Please check the log.",
    "Print finished: {0}", "Print failed: {0}", "Print paused: {0}",
    "Printer reports {0} error(s) – please check the printer", "Printer error {0}: {1}",
    "Printer error {0} – please check the printer", "Cooling", "Heating", "Exhaust", "Full cooling", "weighed", "Support",
    "Other", "Please enter a number", "Value out of range", "Please enter a price like 19.99", "Please enter the brand",
    "Bambu Lab lines are already in the catalog", "Please choose a material", "Shop link must start with http:// or https://",
    "This line already exists", "Line not found", "There are still spools of this line", "Please enter a color name",
    "Invalid color", "Color not found", "This color already exists in the line", "There are still spools of this color",
    "Please enter the weight in grams", "Unknown type", "Please enter the server name or IP address", "Invalid port",
    "Please enter the share name", "Invalid folder", "Not set up yet",
    "SMB needs the pysmb package. Please update PixxelSpool or run ./install.sh again.", "Sign-in to the share was rejected",
    "Server not responding", "Server not reachable ({0})", "Sign-in failed: {0}", "Tag removed", "Invalid tag",
    "This spool already has a tag", "This tag already belongs to another spool", "Only added sticker tags can be removed",
    "Sticker tags don't work while storing several spools", "Not enough filament: {0} ({1})",
    "Filament running low: {0} ({1})", "Not enough filament: {0} ({1}) – spare is at {2}",
    "Filament running low: {0} ({1}) – spare is at {2}", "Refill on", "Refill off", "empty spools −1", "empty spools +1",
    "Print finished on {1}: {0}", "Print failed on {1}: {0}", "Print paused on {1}: {0}", "Printer error {0} ({2}): {1}",
    "Printer error {0} ({1}) – please check the printer", "Cabinet {0}: humidity {1} % (limit {2} %)",
    "Spool almost empty: {0} ({1} %), no spare in storage", "Drying recommended: {0}",
    "Not put back yet: {0} belongs on slot {1}", "Tailscale is not answering. Open the Tailscale app, sign in there and check again.", "AMS humidity {0} % (limit {1} %) – check the desiccant",
    "Drying recommended for {1} spools: {0}",
]
# Texts that stay the same in every language
SKIP = {"%", "%s", "+", ",", "0", "19,99", "192.168.1.50", "2-digit", "55", "8", "ABS", "ACS ACR122U", "ACS ACR1252U",
        "ACS ACR1552U", "Abhängigkeiten ließen sich nicht installieren: ", "Anmeldung fehlgeschlagen: ", "Bambu Lab", "DE",
        "Detail", "Deutsch", "EN", "ES", "English", "Español", "Extruder {0}", "FTP", "FTPS", "Filament-Check", "HA", "HA …",
        "HID Omnikey 5022 / 5427 CK", "HIPS", "High Flow", "Home Assistant", "Hotend-Rack", "Identiv uTrust 3700 F", "NFC",
        "Offline", "PA", "PC", "PETG", "PLA", "PLA+", "PN532 NFC Modul V3", "PVA", "Pi", "PixxelSpool", "Rack {0}",
        "Raspberry Pi", "Refill", "SL-123", "Server nicht erreichbar (", "Shop", "Simulation", "Sport", "Standard",
        "Status: {0}", "Sunlu", "System", "TPU", "Tag {0}", "Turbo", "Waveshare PN532 NFC HAT", "by pixxelhoff", "elSpool",
        "git: ", "git: {0}", "http://192.168.1.100:8123", "https://…", "import", "numeric", "pixxelspool", "reset", "short",
        "xx", "×", "–", "…", "−", "?",}

STR = r'"((?:[^"\\]|\\.)*)"'


def _unesc(s: str) -> str:
    return json.loads('"' + s + '"')


def _balanced(src: str, i: int) -> str:
    """Text from src[i] (after the opening parenthesis) up to the matching closing one."""
    depth, j, q = 1, i, None
    while j < len(src) and depth:
        c = src[j]
        if q:
            if c == "\\":
                j += 1
            elif c == q:
                q = None
        elif c in "\"'":
            q = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        j += 1
    return src[i:j - 1]


def js_keys() -> set:
    src = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    keys = set()
    intro = (ROOT / "static" / "intro.js").read_text(encoding="utf-8")   # the wizard's animated tour
    for m in re.finditer(r"\b(?:L|Lp)\(", intro):
        for sm in re.finditer(r'(===|!==)?\s*' + STR, _balanced(intro, m.end())):
            if not sm.group(1):
                keys.add(_unesc(sm.group(2)))
    for m in re.finditer(r"\b(?:L|Lp)\(", src):
        inner = _balanced(src, m.end())
        for sm in re.finditer(r'(===|!==)?\s*' + STR, inner):
            if not sm.group(1):
                keys.add(_unesc(sm.group(2)))
    w = src.index("const WIZ = [")
    for sm in re.finditer(r'\b(?:title|next): ' + STR, src[w:src.index("\n];", w)]):
        keys.add(_unesc(sm.group(1)))
    for name in ("TOUR", "LIST_SORTS", "LIST_FLAGS"):
        a = src.index("const %s = [" % name)
        blk = src[a:src.index("\n];" if name == "TOUR" else ";\n", a)]
        pat = r'\b(?:title|text): ' + STR if name == "TOUR" else r'\["\w+", ' + STR
        for sm in re.finditer(pat, blk):
            keys.add(_unesc(sm.group(1)))
    for sm in re.finditer(r'\bbtn\("\w+", ' + STR, src):
        keys.add(_unesc(sm.group(1)))
    a = src.index("const I18N = {")
    b = src.index("\n};", a)
    for sm in re.finditer(STR, src[a:b]):
        keys.add(_unesc(sm.group(1)))
    return keys


class _HTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.keys, self.skip = set(), 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "code", "title", "svg"):
            self.skip += 1
        for k, v in attrs:
            if k in ("placeholder", "title", "aria-label") and v:
                self.keys.add(v)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "code", "title", "svg"):
            self.skip -= 1

    def handle_data(self, data):
        t = data.strip()
        if t and not self.skip and re.search(r"[A-Za-zÄÖÜäöü]", t) and "__PM_" not in t:
            self.keys.add(t)


def html_keys() -> set:
    p = _HTML()
    p.feed((ROOT / "static" / "index.html").read_text(encoding="utf-8"))
    return p.keys


def _fstr(parts: str) -> str:
    """Python literal(s) like f"Platz {slot_id} ist belegt" -> "Platz {0} ist belegt"."""
    text = "".join(re.findall(r'f?"((?:[^"\\]|\\.)*)"', parts))
    n = iter(range(20))
    return re.sub(r"\{[^{}]*\}", lambda m: "{%d}" % next(n), text) if 'f"' in parts else text


def py_keys() -> set:
    keys = set()
    pat = re.compile(r'(?:Error|NoReader|InventoryError)\(\s*((?:f?"(?:[^"\\]|\\.)*"\s*)+)|detail=((?:f?"(?:[^"\\]|\\.)*"\s*))|'
                     r'_set\("\w+",\s*[^"\n]*((?:f?"(?:[^"\\]|\\.)*"))')
    import ast
    lt = re.search(r"^LABEL_TEXTS = (\[.*?\])\n\n", (ROOT / "main.py").read_text(encoding="utf-8"), re.S | re.M)
    if lt:                                  # texts of the label page (static/labels.html gets them from main.py)
        keys |= set(ast.literal_eval(lt.group(1)))
    for f in ROOT.glob("*.py"):
        for m in pat.finditer(f.read_text(encoding="utf-8")):
            raw = next(g for g in m.groups() if g)
            k = _fstr(raw)
            if re.search(r"[A-Za-zÄÖÜäöü]{3}", k):
                keys.add(k)
    return keys


def all_keys() -> set:
    return {k for k in (js_keys() | html_keys() | py_keys() | set(EXTRA)) if k not in SKIP and k.strip()}


def main():
    keys = all_keys()
    if "--keys" in sys.argv:
        print("\n".join(sorted(keys)))
        return
    bad = 0
    for f in sorted(LOCALES.glob("*.json")):   # de.json and es.json, keyed by the English source text
        data = json.loads(f.read_text(encoding="utf-8"))
        missing = sorted(k for k in keys if not data.get(k))
        extra = sorted(k for k in data if k not in keys)
        ph = sorted(k for k, v in data.items() if v and sorted(re.findall(r"\{\d\}", k)) != sorted(re.findall(r"\{\d\}", v)))
        print(f"{f.name}: {len(keys) - len(missing)}/{len(keys)} translated")
        for k in missing:
            print("  missing:    ", k)
        for k in extra:
            print("  unused:     ", k)
        for k in ph:
            print("  placeholder:", k)
        bad += len(missing) + len(ph)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
