"""SQLite 备份：升级前自动快照，按数量滚动保留。"""
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from app.constants import BACKUP_DIR, DB_PATH

_MAX_BACKUPS = 10


def _latest_age_hours() -> float | None:
    files = sorted(BACKUP_DIR.glob("pm-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    newest = datetime.fromtimestamp(files[0].stat().st_mtime)
    return (datetime.now() - newest).total_seconds() / 3600


def backup_db(force: bool = False, min_interval_hours: float = 24.0) -> Path | None:
    """用 SQLite 在线备份接口复制数据库；force=False 时限制备份频率。

    返回备份文件路径；数据库不存在/备份失败返回 None（备份失败绝不应阻塞启动）。
    """
    if not DB_PATH.exists():
        return None
    if not force and (_latest_age_hours() or 1e9) < min_interval_hours:
        return None
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = BACKUP_DIR / f"pm-{stamp}.db"
        with closing(sqlite3.connect(DB_PATH)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
        _rotate()
        return target
    except (sqlite3.Error, OSError):
        return None


def _rotate() -> None:
    files = sorted(BACKUP_DIR.glob("pm-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[_MAX_BACKUPS:]:
        try:
            old.unlink()
        except OSError:
            pass


def last_backup() -> Path | None:
    files = sorted(BACKUP_DIR.glob("pm-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None
