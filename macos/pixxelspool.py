"""Entry point of the Mac build (PyInstaller): starts the menu bar app from filament_tool/winapp.py."""
import os

os.environ.setdefault("PIXXELSPOOL_APP", "1")

# The bundled Python does not see the macOS certificate store: without this, every HTTPS request (update check,
# push messages, FTPS backup) fails with "certificate verify failed".
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

from filament_tool.winapp import main  # noqa: E402

if __name__ == "__main__":
    main()
