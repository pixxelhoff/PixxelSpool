"""Create the Mac app icon macos/PixxelSpool.icns from the app icon (build step, needs Pillow)."""
from pathlib import Path

from PIL import Image

root = Path(__file__).resolve().parent.parent
img = Image.open(root / "filament_tool" / "static" / "icon-512.png").convert("RGBA").resize((1024, 1024), Image.LANCZOS)
img.save(root / "macos" / "PixxelSpool.icns")
print("icon written")
