"""Nightly database backup.  Usage: python -m filament_tool.daily_backup [--keep 30]

Writes a consistent copy to data/backups/inventory-YYYY-MM-DD.db, deletes copies older than --keep days and then
uploads to the network share if one is configured (see offsite.py). Run by the systemd timer from install.sh."""
import argparse
import sqlite3
from datetime import date, timedelta

from . import db


def run(keep: int = 30) -> str:
    """Back up the database for today and delete backups older than `keep` days. Returns the file path."""
    folder = db.DATA_DIR / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"inventory-{date.today():%Y-%m-%d}.db"
    src = db.connect()
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    db.prune_backups(keep)                          # backups before actions (deleting, stock check …)
    day = f"{date.today() - timedelta(days=keep):%Y-%m-%d}"
    for old in folder.glob("inventory-????-??-??.db"):
        if old.name < f"inventory-{day}.db":
            old.unlink()
    return target.name


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=None)
    keep = ap.parse_args().keep
    if keep is None:
        from . import settings
        keep = settings.load()["backup_keep_days"]
    print("Sicherung:", run(keep))
    from . import offsite
    res = offsite.run()
    if res is not None:
        print("Network backup:", res.get("file") if res.get("ok") else "Error: " + str(res.get("error")))
