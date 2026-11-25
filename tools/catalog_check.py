#!/usr/bin/env python3
"""Compare the color catalog (filament_tool/bambu_katalog.json) with Bambu Lab's current list and keep it up to date.

    python3 tools/catalog_check.py                         # report only: new colors, removed colors, discontinued
    python3 tools/catalog_check.py --apply                 # add new colors to bambu_katalog.json
    python3 tools/catalog_check.py --discontinued 30404,30504      # mark colors as no longer sold
    python3 tools/catalog_check.py --available 30404       # remove that mark again

Run it before every release. Source: filaments_color_codes.json from Bambu Studio on GitHub (the color list the
slicer uses). That list keeps colors Bambu Lab no longer sells, so "discontinued" is set by hand here after a look
at the Bambu Lab store. Discontinued colors are hidden in the catalog unless the user switches them on, never count
as missing and get no shop link.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

SOURCE = ("https://raw.githubusercontent.com/bambulab/BambuStudio/master/resources/profiles/BBL/filament/"
          "filaments_color_codes.json")
CATALOG = Path(__file__).resolve().parent.parent / "filament_tool" / "bambu_katalog.json"
KINDS = {"单色": "single", "多拼色": "multi", "渐变色": "gradient"}


def line_of(fila_type: str, kind: str) -> str:
    """Bambu Lab sells gradient and multi-color spools as lines of their own."""
    if fila_type == "PLA Basic" and kind == "gradient":
        return "PLA Basic Gradient"
    if fila_type == "PLA Silk" and kind in ("gradient", "multi"):
        return "PLA Silk Multi-Color"
    return fila_type


def entry(u: dict) -> dict:
    kind = KINDS.get(u.get("fila_color_type"), "single")
    names = u.get("fila_color_name") or {}
    fid = u.get("fila_id") or ""
    return {"bambu_no": u["fila_color_code"], "material_id": fid, "line": line_of(u.get("fila_type") or "", kind),
            "variant_id": f"{fid[2:]}-{u.get('color_code') or ''}", "name_en": names.get("en") or "",
            "name_de": names.get("de") or names.get("en") or "", "colors": [c[:7] for c in u.get("fila_color") or []],
            "kind": kind, "de_source": "bambu"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="add new colors to the catalog")
    ap.add_argument("--discontinued", default="", help="comma-separated Bambu numbers no longer sold")
    ap.add_argument("--available", default="", help="comma-separated Bambu numbers sold again")
    a = ap.parse_args()

    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    ours = {c["bambu_no"]: c for c in data["colors"]}
    changed = False

    for no in filter(None, (x.strip() for x in a.discontinued.split(","))):
        if no in ours:
            ours[no]["discontinued"] = True
            changed = True
        else:
            print(f"unknown Bambu number: {no}")
    for no in filter(None, (x.strip() for x in a.available.split(","))):
        if ours.get(no, {}).pop("discontinued", None):
            changed = True

    try:
        with urllib.request.urlopen(urllib.request.Request(SOURCE, headers={"User-Agent": "PixxelSpool catalog check"}),
                                    timeout=30) as r:
            up = {u["fila_color_code"]: u for u in json.load(r)["data"] if u.get("fila_color_code")}
    except (OSError, ValueError, KeyError) as e:
        print(f"Could not load the Bambu Studio color list: {e}")
        up = None

    if up is not None:
        new = [entry(u) for no, u in sorted(up.items()) if no not in ours]
        gone = [c for no, c in sorted(ours.items()) if no not in up]
        print(f"Bambu Studio list: {len(up)} colors, catalog: {len(ours)} colors")
        print(f"New at Bambu Lab ({len(new)}):")
        for c in new:
            print(f"  {c['bambu_no']}  {c['line']:<22} {c['name_en']} / {c['name_de']}")
        print(f"No longer in the Bambu Studio list ({len(gone)}), maybe discontinued:")
        for c in gone:
            print(f"  {c['bambu_no']}  {c['line']:<22} {c['name_en']}{'  [discontinued]' if c.get('discontinued') else ''}")
        if new and a.apply:
            data["colors"].extend(new)
            changed = True
        elif new:
            print("Add them with --apply.")
        data["fetched"] = data.get("fetched") if not a.apply else __import__("datetime").date.today().isoformat()

    disc = [c for c in data["colors"] if c.get("discontinued")]
    print(f"Marked as discontinued ({len(disc)}): " + ", ".join(f"{c['bambu_no']} {c['line']} {c['name_en']}" for c in disc))
    if changed:
        CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"Saved {CATALOG.name}. Check the colors in the app (Catalog) and note the change in both changelogs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
