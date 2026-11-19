#!/usr/bin/env python3
"""Next version for an automatic security release (used by .github/workflows/dependabot-security.yml).

    python3 tools/ci/security_release.py "cryptography 50.0.3, h11 0.16.1"     # prints the new version

Raises the version (1.0.0-alpha.7 -> 1.0.0-alpha.8, 1.0.0 -> 1.0.1), writes VERSION and filament_tool/__init__.py
and adds a "Security" section to both changelogs, which marks the version as a security release for the updater.
"""
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
pkgs = (sys.argv[1] if len(sys.argv) > 1 else "").strip()

cur = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc|patch)\.?(\d+))?", cur)
if not m:
    sys.exit(f"unknown version {cur!r}")
a, b, c, pre, n = m.groups()
if pre in ("alpha", "beta", "rc"):
    new = f"{a}.{b}.{c}-{pre}.{int(n) + 1}"
else:                                           # a final version (or an app-only -patch.N): next patch version
    new = f"{a}.{b}.{int(c) + 1}"

(ROOT / "VERSION").write_text(new + "\n", encoding="utf-8")
init = ROOT / "filament_tool" / "__init__.py"
init.write_text(re.sub(r'__version__ = ".*"', f'__version__ = "{new}"', init.read_text(encoding="utf-8")), encoding="utf-8")

day = datetime.date.today().isoformat()
texts = {
    "CHANGELOG.md": "### Security\n- Automatic security update of the Python packages" + (f": {pkgs}" if pkgs else "")
                    + " (found by Dependabot, tested before it was released).",
    "CHANGELOG.de.md": "### Sicherheit\n- Automatisches Sicherheitsupdate der Python-Pakete" + (f": {pkgs}" if pkgs else "")
                       + " (von Dependabot gefunden, vor der Veröffentlichung getestet).",
}
for name, body in texts.items():
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    i = text.index("\n## [")
    path.write_text(text[:i + 1] + f"## [{new}] – {day}\n\n{body}\n\n" + text[i + 1:], encoding="utf-8")
print(new)
