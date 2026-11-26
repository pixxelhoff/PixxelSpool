"""PixxelSpool as a Windows or Mac app: runs the web server in the background with an icon in the notification area
(Windows) or the menu bar (Mac).

    PixxelSpool.exe [--port 8000] [--no-browser] [--restarted]

- Only one copy runs at a time; starting it again just opens the browser.
- The server listens on all interfaces so phones in the home network can connect (Windows asks once whether to
  allow that in the firewall).
- PixxelSpool opens in its own app window (Microsoft Edge or Chrome in app mode, without address bar and tabs);
  if neither is found, the default browser is used.
- Tray icon: double-click opens PixxelSpool. Menu: open, address for the phone, GitHub, check for updates, start
  with Windows, restart, quit.
- Data lives in %APPDATA%\\PixxelSpool (see host.py), logs in its logs\\ folder.
- Mac: the same with a menu bar icon and no Dock icon (LSUIElement). The window is Chrome or Edge in app mode only
  if that is the default browser, otherwise PixxelSpool opens in the default browser (e.g. Safari). Start at login through a LaunchAgent. Data lives in
  ~/Library/Application Support/PixxelSpool.

Started without a tray library (e.g. for testing) it simply runs the server in the foreground.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("PIXXELSPOOL_APP", "1")       # host.py reads this on import

import argparse
import logging
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

APP_NAME = "PixxelSpool"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
IS_MAC = sys.platform == "darwin"
AGENT = "de.pixxelhoff.pixxelspool"                 # Mac: LaunchAgent label (start at login)
TEXTS = {
    "de": {"open": "PixxelSpool öffnen", "phone": "Im Heimnetz: {0}", "autostart": "Mit Windows starten",
           "restart": "Neu starten", "quit": "Beenden", "running": "PixxelSpool läuft", "github": "PixxelSpool auf GitHub",
           "update": "Nach Updates suchen", "uptodate": "PixxelSpool {0} ist aktuell.",
           "available": "Version {0} ist verfügbar. Die Download-Seite wird geöffnet.",
           "upfail": "Suche nach Updates fehlgeschlagen: {0}",
           "pwreset": "Kennwort zurücksetzen", "pwnone": "Es ist kein Kennwort gesetzt.", "autostart_mac": "Bei der Anmeldung starten",
           "pwdone": "Das Kennwort wurde entfernt. Ein neues legst du in den Optionen unter System fest."},
    "en": {"open": "Open PixxelSpool", "phone": "In your network: {0}", "autostart": "Start with Windows",
           "restart": "Restart", "quit": "Quit", "running": "PixxelSpool is running", "github": "PixxelSpool on GitHub",
           "update": "Check for updates", "uptodate": "PixxelSpool {0} is up to date.",
           "available": "Version {0} is available. Opening the download page.",
           "upfail": "Update check failed: {0}",
           "pwreset": "Reset password", "pwnone": "No password is set.", "autostart_mac": "Open at login",
           "pwdone": "The password was removed. Set a new one in Options › System."},
    "es": {"open": "Abrir PixxelSpool", "phone": "En tu red: {0}", "autostart": "Iniciar con Windows",
           "restart": "Reiniciar", "quit": "Salir", "running": "PixxelSpool está en marcha", "github": "PixxelSpool en GitHub",
           "update": "Buscar actualizaciones", "uptodate": "PixxelSpool {0} está actualizado.",
           "available": "La versión {0} está disponible. Se abre la página de descarga.",
           "upfail": "No se pudo buscar actualizaciones: {0}",
           "pwreset": "Restablecer contraseña", "pwnone": "No hay ninguna contraseña.", "autostart_mac": "Abrir al iniciar sesión",
           "pwdone": "Se ha quitado la contraseña. Define una nueva en Opciones › Sistema."},
}


def _quiet_std() -> None:
    """A windowed exe has no console: give print()/logging somewhere to write."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def _resource(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)


def lan_ip() -> str:
    """Address of this PC in the home network (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


# ---------------------------------------------------------------- app window

def _mac_default_browser() -> str:
    """Bundle id of the browser macOS opens web links with (e.g. "com.apple.safari"), "" if unknown."""
    import plistlib
    f = Path.home() / "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
    try:
        with open(f, "rb") as fh:
            handlers = plistlib.load(fh).get("LSHandlers") or []
    except (OSError, ValueError, plistlib.InvalidFileException):
        return ""
    for h in handlers:
        if h.get("LSHandlerURLScheme") in ("https", "http"):
            return str(h.get("LSHandlerRoleAll") or "").lower()
    return ""


def _app_browser() -> str:
    """Edge (part of Windows 10/11) or Chrome, for a window without address bar and tabs."""
    if IS_MAC:   # only when it is the default browser: an app window in another browser surprises people
        rel = {"com.google.chrome": "Google Chrome.app/Contents/MacOS/Google Chrome",
               "com.microsoft.edgemac": "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"}.get(_mac_default_browser())
        for base in (Path("/Applications"), Path.home() / "Applications"):
            if rel and (base / rel).exists():
                return str(base / rel)
        return ""
    if sys.platform != "win32":
        return ""
    for name in ("msedge", "chrome"):
        try:                                   # App Paths is where installers register the full path
            import winreg
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(root, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{name}.exe") as k:
                        path = winreg.QueryValue(k, None)
                        if path and Path(path).exists():
                            return path
                except OSError:
                    pass
        except ImportError:
            pass
        found = shutil.which(name)
        if found:
            return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
            if base and (Path(base) / rel).exists():
                return str(Path(base) / rel)
    return ""


def open_window(url: str) -> None:
    """Show PixxelSpool in its own window. A separate browser profile keeps it apart from the user's browser
    (own taskbar entry, remembered window size) and leaves their tabs and logins alone."""
    exe = _app_browser()
    if exe:
        try:
            from filament_tool import host
            profile = host.data_dir() / "window"
            subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1280,860",
                              "--no-first-run", "--no-default-browser-check", "--disable-sync"],
                             close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
                             start_new_session=IS_MAC)
            return
        except OSError as e:
            logging.getLogger("app").warning("App window not available (%s), using the browser", e)
    webbrowser.open(url)


# ---------------------------------------------------------------- single instance (named mutex / lock file)

_mutex = None


def _mac_lock(wait: float) -> bool:
    """Mac: an exclusive lock on a file in the data folder; the system releases it when the process ends."""
    global _mutex
    import fcntl
    from filament_tool import host
    folder = host.data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    f = open(folder / "app.lock", "w")
    end = time.time() + wait
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _mutex = f
            return True
        except OSError:
            if time.time() >= end:
                f.close()
                return False
            time.sleep(0.5)


def single_instance(wait: float = 0) -> bool:
    """True if this is the only running copy. With wait, keep trying (after a restart the old copy is exiting)."""
    global _mutex
    if IS_MAC:
        return _mac_lock(wait)
    if sys.platform != "win32":
        return True
    import ctypes
    kernel = ctypes.windll.kernel32
    end = time.time() + wait
    while True:
        h = kernel.CreateMutexW(None, False, "Local\\PixxelSpool-App")
        if kernel.GetLastError() != 183:          # ERROR_ALREADY_EXISTS
            _mutex = h
            return True
        kernel.CloseHandle(h)
        if time.time() >= end:
            return False
        time.sleep(0.5)


# ---------------------------------------------------------------- autostart (HKCU Run key / Mac LaunchAgent)

def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --no-browser'
    return f'"{sys.executable}" -m filament_tool.winapp --no-browser'


def _agent_file() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{AGENT}.plist"


def _mac_set_autostart(on: bool) -> None:
    """A LaunchAgent starts PixxelSpool when the user logs in. The packaged app is started through `open`, so
    macOS treats it as the app (not as a loose program inside it)."""
    f = _agent_file()
    if not on:
        try:
            f.unlink()
        except OSError:
            pass
        return
    import plistlib
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False) and exe.parent.name == "MacOS":
        args = ["/usr/bin/open", "-a", str(exe.parents[2]), "--args", "--no-browser"]
    else:
        args = [sys.executable, "-m", "filament_tool.winapp", "--no-browser"]
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(plistlib.dumps({"Label": AGENT, "ProgramArguments": args, "RunAtLoad": True, "ProcessType": "Interactive"}))


def autostart_on() -> bool:
    if IS_MAC:
        return _agent_file().exists()
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(on: bool) -> None:
    if IS_MAC:
        _mac_set_autostart(on)
        return
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


# ---------------------------------------------------------------- tray icon

WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x0202, 0x0203


def _tray_class(pystray):
    """On Windows pystray opens the default menu item on a single click; PixxelSpool opens on a double click
    like most tray apps (a single click does nothing, the right click still shows the menu)."""
    base = pystray.Icon
    if sys.platform != "win32" or not hasattr(base, "_on_notify"):
        return base

    import ctypes
    dbl = ctypes.windll.user32.GetDoubleClickTime() / 1000

    class DoubleClickIcon(base):
        _last_up = 0.0
        _opened = 0.0

        def _open(self):
            if time.time() - self._opened > 1:      # the shell may report a double click both ways
                self._opened = time.time()
                self()                               # runs the default menu item

        def _on_notify(self, wparam, lparam):
            if lparam == WM_LBUTTONDBLCLK:
                self._open()
            elif lparam == WM_LBUTTONUP:             # second click in time also counts as a double click
                now = time.time()
                if now - self._last_up <= dbl:
                    self._open()
                self._last_up = now
            else:
                super()._on_notify(wparam, lparam)
    return DoubleClickIcon


# ---------------------------------------------------------------- Mac: open the window when the app is started again

_reopen = None


def _mac_reopen(show) -> None:
    """Double-clicking PixxelSpool.app while it runs does not start a second copy; macOS sends the running one a
    "reopen" message instead. Answer it by showing the window."""
    global _reopen
    try:
        import AppKit

        class ReopenDelegate(AppKit.NSObject):
            def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _flag):
                show()
                return True

        _reopen = ReopenDelegate.alloc().init()
        AppKit.NSApplication.sharedApplication().setDelegate_(_reopen)
    except Exception as e:           # nice to have only
        logging.getLogger("app").info("Reopen handler not available: %s", e)


# ---------------------------------------------------------------- main

def main() -> None:
    _quiet_std()
    ap = argparse.ArgumentParser(prog="PixxelSpool")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PIXXELSPOOL_PORT") or 8000))
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--restarted", action="store_true")
    a = ap.parse_args()
    url = f"http://localhost:{a.port}"

    if not single_instance(wait=20 if a.restarted else 0):
        open_window(url)              # already running: just show it
        return
    if a.restarted:                   # the old copy may still hold the port for a moment
        end = time.time() + 20
        while not port_free(a.port) and time.time() < end:
            time.sleep(0.5)

    import uvicorn
    from filament_tool import host, settings
    from filament_tool.main import app
    log = logging.getLogger("app")
    log.info("PixxelSpool app starting, data in %s", host.data_dir())

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=a.port, log_config=None, access_log=False))
    t = threading.Thread(target=server.run, daemon=True, name="server")
    t.start()
    if not a.no_browser and not a.restarted:
        threading.Timer(2.0, lambda: open_window(url)).start()

    try:
        import pystray
        from PIL import Image
    except ImportError:               # no tray (development): run in the foreground until Ctrl+C
        try:
            while t.is_alive():
                t.join(1)
        except KeyboardInterrupt:
            server.should_exit = True
        return

    tx = TEXTS.get(settings.lang(), TEXTS["en"])
    phone = f"http://{lan_ip()}:{a.port}"

    def quit_app(icon, _item=None):
        server.should_exit = True
        icon.stop()
        threading.Timer(3.0, lambda: os._exit(0)).start()

    def restart(icon, _item=None):
        icon.stop()
        server.should_exit = True
        t.join(5)
        host.restart()

    def toggle_autostart(icon, _item):
        set_autostart(not autostart_on())
        if IS_MAC:                    # the Mac menu is built once: rebuild it for the check mark
            icon.update_menu()

    def pw_on(_item=None):
        from filament_tool import auth
        return auth.enabled()

    def reset_password(icon, _item=None):
        """Forgotten app password: whoever sits at this PC may remove it (like the terminal command on the Pi)."""
        from filament_tool import auth
        if auth.enabled():
            auth.disable()
        elif IS_MAC:                  # the Mac menu always shows this item
            icon.notify(tx["pwnone"], APP_NAME)
            return
        icon.notify(tx["pwdone"], APP_NAME)

    def check_updates(icon, _item=None):
        def run():
            from filament_tool import updater
            try:
                res = updater.check(force=True)
                if res.get("error"):
                    raise RuntimeError(res["error"])
            except Exception as e:
                icon.notify(tx["upfail"].format(e), APP_NAME)
                return
            if res.get("available"):
                icon.notify(tx["available"].format(res["latest"]), APP_NAME)
                webbrowser.open(res.get("download") or f"https://github.com/{updater.REPO}/releases")
            else:
                icon.notify(tx["uptodate"].format(res.get("current", "")), APP_NAME)
        threading.Thread(target=run, daemon=True, name="update-check").start()

    from filament_tool import updater
    menu = pystray.Menu(
        pystray.MenuItem(tx["open"], lambda *_: open_window(url), default=True),
        pystray.MenuItem(tx["phone"].format(phone), lambda *_: webbrowser.open(phone)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(tx["github"], lambda *_: webbrowser.open(f"https://github.com/{updater.REPO}")),
        pystray.MenuItem(tx["update"], check_updates),
        pystray.MenuItem(tx["pwreset"], reset_password, visible=True if IS_MAC else pw_on),   # Mac menu is not re-evaluated
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(tx["autostart_mac" if IS_MAC else "autostart"], toggle_autostart, checked=lambda _i: autostart_on()),
        pystray.MenuItem(tx["restart"], restart),
        pystray.MenuItem(tx["quit"], quit_app),
    )
    image = Image.open(_resource("filament_tool", "static", "icon-512.png"))
    icon = _tray_class(pystray)(APP_NAME, image, tx["running"], menu)
    if IS_MAC:
        _mac_reopen(lambda: open_window(url))
    try:
        icon.run()
    except Exception as e:            # no notification area (e.g. a service session): keep serving
        log.warning("Tray icon not available: %s", e)
        while t.is_alive():
            t.join(1)


if __name__ == "__main__":
    main()
