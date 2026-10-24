"""pytest 公共夹具：每个测试用独立数据库 / .env，绝不碰真实用户数据。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from app.core import backup, db  # noqa: E402
from app.core import settings as settings_mod  # noqa: E402


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """把数据库、备份目录、.env 全部指向临时目录。"""
    db_path = tmp_path / "pm.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(backup, "DB_PATH", db_path)
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(settings_mod, "ENV_FILE", tmp_path / ".env")
    db.init_db()
    return db_path


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
