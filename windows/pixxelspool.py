"""Entry point of the Windows build (PyInstaller): starts the tray app from filament_tool/winapp.py."""
import os

os.environ.setdefault("PIXXELSPOOL_APP", "1")

from filament_tool.winapp import main  # noqa: E402

if __name__ == "__main__":
    main()
