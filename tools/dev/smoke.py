#!/usr/bin/env python3
"""Click through the interface of the mock server in a headless browser and report JavaScript errors.

    pip install playwright && playwright install chromium     # once, in any Python environment
    tools/dev/mock.sh
    python3 tools/dev/smoke.py [http://localhost:8135]

Phone and desktop widths are tested; screenshots land in .devdata/shots/.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8135"
SHOTS = Path(".devdata/shots")
SHOTS.mkdir(parents=True, exist_ok=True)
VIEWS = ["storage", "printerview", "catalog", "statsview", "tools"]   # ids as used by showView() in app.js

with sync_playwright() as p:
    browser = p.chromium.launch()
    problems = []
    for name, (w, h) in {"phone": (390, 844), "desktop": (1280, 900)}.items():
        page = browser.new_page(viewport={"width": w, "height": h})
        page.on("pageerror", lambda e: problems.append(f"{name}: {e}"))
        page.on("console", lambda m: problems.append(f"{name}: {m.text}") if m.type == "error" else None)
        page.goto(URL)
        page.evaluate("localStorage.setItem('seenVersion', '99.0.0')")      # no "what's new" dialog in the way
        page.reload()
        page.wait_for_timeout(1500)
        for view in VIEWS:
            try:
                page.evaluate(f"showView('{view}')")
                page.wait_for_timeout(400)
                page.screenshot(path=str(SHOTS / f"{name}-{view}.png"))
            except Exception as e:                                          # a view that does not exist (yet)
                problems.append(f"{name}: view {view}: {e}")
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        if overflow > 0:
            problems.append(f"{name}: page is {overflow}px too wide")
        page.close()
    browser.close()
print("\n".join(problems) or "OK: no JavaScript errors, no horizontal overflow")
sys.exit(1 if problems else 0)
