# PyInstaller build of the Mac app:  pyinstaller macos/pixxelspool.spec  (run from the repository root, on a Mac)
# Result: dist/PixxelSpool.app. Not signed by a developer (only the ad-hoc signature PyInstaller adds), so macOS
# asks once before the first start (see README, "Mac app").
import re

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = SPECPATH + "/.."
VERSION = open(ROOT + "/VERSION", encoding="utf-8").read().strip()

hidden = (collect_submodules("filament_tool") + collect_submodules("uvicorn") + collect_submodules("smartcard") + collect_submodules("serial") + collect_submodules("webauthn")
          + ["pystray._darwin", "AppKit", "Foundation", "PyObjCTools.MachSignals", "certifi"])
datas = [
    (ROOT + "/filament_tool/static", "filament_tool/static"),
    (ROOT + "/filament_tool/locales", "filament_tool/locales"),
    (ROOT + "/filament_tool/bambu_katalog.json", "filament_tool"),
    (ROOT + "/VERSION", "."),
    (ROOT + "/CHANGELOG.md", "."),
    (ROOT + "/CHANGELOG.de.md", "."),     # "what's new" dialog after an update
    (ROOT + "/LICENSE", "."),
    (ROOT + "/NOTICE", "."),
] + collect_data_files("segno") + collect_data_files("certifi")   # CA certificates for HTTPS

a = Analysis([ROOT + "/macos/pixxelspool.py"], pathex=[ROOT], datas=datas, hiddenimports=hidden,
             excludes=["tkinter", "matplotlib", "numpy.tests"], noarchive=False)
pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PixxelSpool", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="PixxelSpool", upx=False)

short = re.match(r"\d+\.\d+\.\d+", VERSION).group(0)      # macOS wants plain numbers here
app = BUNDLE(
    coll,
    name="PixxelSpool.app",
    icon=ROOT + "/macos/PixxelSpool.icns",
    bundle_identifier="de.pixxelhoff.pixxelspool",
    version=VERSION,
    info_plist={
        "CFBundleName": "PixxelSpool",
        "CFBundleDisplayName": "PixxelSpool",
        "CFBundleShortVersionString": short,
        "CFBundleVersion": VERSION,
        "LSUIElement": True,                 # menu bar icon only, no Dock icon (like the Windows tray icon)
        "LSMinimumSystemVersion": "12.0",
        "NSHumanReadableCopyright": "pixxelhoff",
        "NSHighResolutionCapable": True,
        "NSLocalNetworkUsageDescription": "PixxelSpool talks to your Bambu Lab printer and to phones in your home network.",
    },
)
