import shutil
from datetime import datetime
from pathlib import Path
from db_adapter import USE_POSTGRES, SQLITE_DB_PATH

BACKUP_DIR = Path(__file__).parent / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

def create_backup() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not USE_POSTGRES:
        dest = BACKUP_DIR / f"microstock_backup_{ts}.db"
        shutil.copy2(SQLITE_DB_PATH, dest)
        return dest
    # Ako je PostgreSQL, ostaje tvoja postojeća pg_dump / SQL logika