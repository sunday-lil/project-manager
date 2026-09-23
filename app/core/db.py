"""SQLite 连接与建表。每次操作用短连接，杜绝跨线程共享连接。"""
import sqlite3
from contextlib import closing

from app.constants import DB_PATH, SCHEMA_VERSION

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
    created_at    TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_repo   ON tasks(repo_id);
"""


def get_connection() -> sqlite3.Connection:
    """建立新的短连接，调用方负责关闭：with closing(get_connection()) as conn: ..."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """建库建表（含 user_version 迁移占位）。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(get_connection()) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            conn.executescript(_DDL)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()
