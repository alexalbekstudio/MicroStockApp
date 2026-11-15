# backup.py
import os
import sys
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from db_adapter import USE_POSTGRES, SQLITE_DB_PATH, _database_url

# Folder za bekape uvijek stoji pored .exe fajla (ili u root-u projekta)
if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys.executable).parent
else:
    APP_ROOT = Path(__file__).parent

BACKUP_DIR = APP_ROOT / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def create_backup() -> Path:
    """Kreira bekap baze (kopira .db fajl za SQLite ili radi pg_dump za PostgreSQL)."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not USE_POSTGRES:
        dest = BACKUP_DIR / f"microstock_backup_{ts}.db"
        if SQLITE_DB_PATH.exists():
            shutil.copy2(SQLITE_DB_PATH, dest)
        else:
            dest.touch()
        return dest

    # PostgreSQL backup
    dest = BACKUP_DIR / f"microstock_pg_{ts}.sql"
    dsn = _database_url()
    try:
        subprocess.run(
            ["pg_dump", dsn, "-f", str(dest)],
            check=True,
            capture_output=True,
            text=True,
        )
        return dest
    except Exception as e:
        raise RuntimeError(f"pg_dump nije uspio: {e}")


def list_backups() -> list[dict]:
    """Vraća listu svih kreiranih bekapa sortiranu od najnovijeg."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(BACKUP_DIR.glob("microstock_*.*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_file():
            stat = p.stat()
            items.append({
                "name": p.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "path": str(p),
            })
    return items