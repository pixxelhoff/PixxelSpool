"""Start PixxelSpool.  Usage: python run.py [--port 8000] [--lan]"""
import argparse
import webbrowser
import threading

from filament_tool import guard

guard.on_start()     # after an update: go back to the old version if the new one keeps failing to start

import uvicorn  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8000)
ap.add_argument("--lan", action="store_true", help="auch im Heimnetz erreichbar (iPad)")
ap.add_argument("--no-browser", action="store_true")
a = ap.parse_args()

if not a.no_browser:
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{a.port}")).start()
uvicorn.run("filament_tool.main:app", host="0.0.0.0" if a.lan else "127.0.0.1", port=a.port)
