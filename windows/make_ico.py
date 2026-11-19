"""Create the Windows icons from the app icon (build step, needs Pillow).

    windows/pixxelspool.ico         the app itself
    windows/pixxelspool-setup.ico   the installer: same icon with a download badge, so it is not mistaken for the app
"""
from pathlib import Path

from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent.parent
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img = Image.open(root / "filament_tool" / "static" / "icon-512.png").convert("RGBA").resize((512, 512), Image.LANCZOS)
img.save(root / "windows" / "pixxelspool.ico", sizes=SIZES)


def setup_icon(base: Image.Image) -> Image.Image:
    """Shrink the app icon a little and put a round badge with a download arrow on the lower right."""
    out = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    out.alpha_composite(base.resize((420, 420), Image.LANCZOS), (0, 0))
    d = ImageDraw.Draw(out)
    cx, cy, r = 372, 372, 140
    d.ellipse((cx - r - 14, cy - r - 14, cx + r + 14, cy + r + 14), fill=(255, 255, 255, 255))   # white ring
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(22, 128, 61, 255))                          # green badge
    w = 34                                                                                         # arrow
    d.rectangle((cx - w, cy - 88, cx + w, cy + 6), fill="white")
    d.polygon([(cx - 86, cy - 4), (cx + 86, cy - 4), (cx, cy + 82)], fill="white")
    d.rectangle((cx - 86, cy + 92, cx + 86, cy + 116), fill="white")                               # tray line
    return out


setup_icon(img).save(root / "windows" / "pixxelspool-setup.ico", sizes=SIZES)
print("icons written")
