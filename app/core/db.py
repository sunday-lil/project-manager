"""SQLite 连接与建表。每次操作用短连接，杜绝跨线程共享连接。

迁移策略：PRAGMA user_version 逐级升级；升级前自动备份（见 backup.py）。
"""
import sqlite3
from contextlib import closing

from app.constants import DB_PATH, SCHEMA_VERSION
from app.core.backup import backup_db

_DDL = """
CREATE TABLE IF NOT EXISTS repos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT UNIQUE NOT NULL,
    name            TEXT DEFAULT '',
    remote_url      TEXT DEFAULT '',
    owner_repo      TEXT DEFAULT '',
    added_at        TEXT,
    last_scanned_at TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    description   TEXT DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'todo',
    priority      TEXT NOT NULL DEFAULT 'medium',
    due_date      TEXT,
    tags          TEXT DEFAULT '',
    repo_id       INTEGER REFERENCES repos(id) ON DELETE SET NULL,
    issue_number  INTEGER,
    issue_url     TEXT,
    synced_at     TEXT,
    completed_at  TEXT,
    created_at    TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status    ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_repo      ON tasks(repo_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due       ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_completed ON tasks(completed_at);
"""


def get_connection() -> sqlite3.Connection:
    """建立新的短连接，调用方负责关闭：with closing(get_connection()) as conn: ..."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    cols = _columns(conn, "tasks")
    if "completed_at" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
    # 老数据没有完成时间：用最后更新时间回填，让趋势图有基线
    conn.execute(
        "UPDATE tasks SET completed_at = COALESCE(updated_at, created_at) "
        "WHERE status = 'done' AND (completed_at IS NULL OR completed_at = '')"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_completed ON tasks(completed_at)")


def init_db() -> None:
    """建库建表 + 版本迁移。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(get_connection()) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        if DB_PATH.exists() and version > 0:
            backup_db(force=True)  # 升级前快照，失败不阻塞
        if version < 1:
            conn.executescript(_DDL)
        if version < 2:
            _migrate_to_v2(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
