"""Create the README screenshots: python tools/screenshots.py docs/screenshots [http://host:8000]

Needs Playwright (pip install playwright && python -m playwright install chromium). The UI is forced to English;
the script only reads, nothing is changed.
"""
import sys
from playwright.sync_api import sync_playwright
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://pixxelspool.local:8000"
OUT = sys.argv[1]

def shot(p, name, view, theme, mobile):
    ctx = (p.new_context(**p_devices["iPhone 14"], color_scheme=theme) if mobile
           else p.new_context(viewport={"width": 1440, "height": 1150}, device_scale_factor=2, color_scheme=theme))
    ctx.add_init_script(f"try{{localStorage.setItem('theme','{theme}')}}catch(e){{}}")
    ctx.add_init_script("Object.defineProperty(window,'PS_LANG',{value:'en',writable:false});Object.defineProperty(window,'PS_DICT',{value:{},writable:false});")
    page = ctx.new_page()
    page.goto(BASE + "/", wait_until="load")
    page.wait_for_timeout(6000)
    if view != "storage":
        if mobile:
            page.evaluate(f"showView('{view}')")
        else:
            page.click(f'#nav [data-view="{view}"]')
        page.wait_for_timeout(1800)
    page.screenshot(path=f"{OUT}/{name}.png")
    ctx.close()

with sync_playwright() as pw:
    p_devices = pw.devices
    b = pw.chromium.launch()
    class P:  # context factory
        new_context = b.new_context
    for name, view, theme, mobile in [
        ("storage-light", "storage", "light", False), ("storage-dark", "storage", "dark", False),
        ("print", "print", "light", False), ("catalog", "catalog", "light", False),
        ("mobile-light", "storage", "light", True), ("mobile-dark", "storage", "dark", True)]:
        shot(P, name, view, theme, mobile)
        print("ok", name)
    b.close()
