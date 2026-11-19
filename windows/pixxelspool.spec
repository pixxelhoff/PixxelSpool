# PyInstaller build of the Windows app:  pyinstaller windows/pixxelspool.spec  (run from the repository root)
# One folder (dist/PixxelSpool) instead of a single exe: starts faster and trips fewer virus scanners.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = SPECPATH + "/.."

hidden = (collect_submodules("filament_tool") + collect_submodules("uvicorn") + collect_submodules("smartcard") + collect_submodules("serial") + collect_submodules("webauthn")
          + ["pystray._win32"])
datas = [
    (ROOT + "/filament_tool/static", "filament_tool/static"),
    (ROOT + "/filament_tool/locales", "filament_tool/locales"),
    (ROOT + "/filament_tool/bambu_katalog.json", "filament_tool"),
    (ROOT + "/VERSION", "."),
    (ROOT + "/CHANGELOG.md", "."),
    (ROOT + "/CHANGELOG.de.md", "."),     # "what's new" dialog after an update
    (ROOT + "/LICENSE", "."),
    (ROOT + "/NOTICE", "."),
] + collect_data_files("segno")

a = Analysis([ROOT + "/windows/pixxelspool.py"], pathex=[ROOT], datas=datas, hiddenimports=hidden,
             excludes=["tkinter", "matplotlib", "numpy.tests"], noarchive=False)
pyz = PYZ(a.pure)

# file properties of PixxelSpool.exe (Explorer › Properties › Details): product, version, developer
try:   # never let the file properties break the build
    import re
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    _v = open(ROOT + "/VERSION", encoding="utf-8").read().strip()
    _n = tuple(int(x) for x in re.match(r"(\d+)\.(\d+)\.(\d+)", _v).groups()) + (int((re.search(r"patch\.?(\d+)", _v) or [0, 0])[1]),)
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=_n, prodvers=_n),
        kids=[StringFileInfo([StringTable("040704B0", [
            StringStruct("CompanyName", "pixxelhoff"), StringStruct("FileDescription", "PixxelSpool"),
            StringStruct("FileVersion", _v), StringStruct("ProductName", "PixxelSpool"),
            StringStruct("ProductVersion", _v), StringStruct("LegalCopyright", "pixxelhoff"),
            StringStruct("OriginalFilename", "PixxelSpool.exe")])]),
              VarFileInfo([VarStruct("Translation", [0x0407, 1200])])])
except Exception as e:
    print("no version resource:", e)
    version_info = None

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PixxelSpool", console=False,
          icon=ROOT + "/windows/pixxelspool.ico", version=version_info, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="PixxelSpool", upx=False)
