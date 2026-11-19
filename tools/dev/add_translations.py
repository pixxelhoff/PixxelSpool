#!/usr/bin/env python3
"""Add translations for new interface texts.

1. Add the new English texts to the interface, then run `python3 tools/i18n.py`: it lists them as "missing".
2. Put them into TRANSLATIONS below as  "English text": ("German", "Spanish"),  and run this script from the repo root.
   Texts that no longer exist in the code ("unused") are removed from the locale files automatically.
3. Run `python3 tools/i18n.py` again: de and es must both say N/N translated.
"""
import json
import subprocess
import sys
from pathlib import Path

LOCALES = Path("filament_tool/locales")
TRANSLATIONS = {
    # "New text": ("Neuer Text", "Texto nuevo"),
}

out = subprocess.run([sys.executable, "tools/i18n.py"], capture_output=True, text=True).stdout
for lang, idx in (("de", 0), ("es", 1)):
    path = LOCALES / f"{lang}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    section = out.split(f"{lang}.json")[1].split(".json:")[0]
    for line in section.splitlines():
        line = line.strip()
        if line.startswith("unused:"):
            data.pop(line.split("unused:", 1)[1].strip(), None)
        elif line.startswith("missing:"):
            key = line.split("missing:", 1)[1].strip()
            if key in TRANSLATIONS:
                data[key] = TRANSLATIONS[key][idx]
            else:
                print("NO TRANSLATION", lang, key)
    body = ",\n".join(f" {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}" for k, v in sorted(data.items()))
    path.write_text("{\n" + body + "\n}\n", encoding="utf-8")
