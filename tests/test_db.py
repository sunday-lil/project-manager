"""数据库建表与 v1 → v2 迁移。"""
import sqlite3
from contextlib import closing

from app.core import backup, db


def test_init_creates_schema(isolated_db):
    with closing(sqlite3.connect(isolated_db)) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        task_cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
    assert version == db.SCHEMA_VERSION
    assert {"tasks", "repos", "settings"} <= tables
    assert "completed_at" in task_cols


def test_migrate_v1_backfills_completed_at(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript("""
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'todo',
                priority TEXT NOT NULL DEFAULT 'medium',
                due_date TEXT, tags TEXT DEFAULT '',
                repo_id INTEGER, issue_number INTEGER, issue_url TEXT,
                synced_at TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE repos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE NOT NULL,
                name TEXT DEFAULT '', remote_url TEXT DEFAULT '', owner_repo TEXT DEFAULT '',
                added_at TEXT, last_scanned_at TEXT
            );
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
            PRAGMA user_version = 1;
        """)
        conn.execute(
            "INSERT INTO tasks (title, status, created_at, updated_at) VALUES (?, 'done', ?, ?)",
            ("历史任务", "2026-10-01T10:00:00", "2026-10-02T11:00:00"))
        conn.commit()

    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setattr(backup, "DB_PATH", path)
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    db.init_db()

    with closing(sqlite3.connect(path)) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        completed = conn.execute("SELECT completed_at FROM tasks").fetchone()[0]
    assert version == 2
    assert completed == "2026-10-02T11:00:00"
    assert list((tmp_path / "backups").glob("pm-*.db")), "升级前应自动备份"
