"""Token 加密存储与旧数据迁移。"""
import pytest

from app.constants import SETTING_GITHUB_TOKEN
from app.core import secrets
from app.core.settings import (
    SettingsStore,
    clear_github_token,
    get_github_token,
    set_github_token,
    token_status,
)

pytestmark = pytest.mark.skipif(not secrets.available(), reason="仅 Windows DPAPI")


def test_dpapi_roundtrip():
    token = "ghp_测试token_123"
    blob = secrets.protect(token)
    assert blob and token not in blob
    assert secrets.unprotect(blob) == token
    assert secrets.unprotect("not-base64!!!") is None


def test_set_get_clear_token(isolated_db):
    assert get_github_token() is None
    assert token_status() == {"configured": False, "encrypted": False}

    set_github_token("ghp_secret_value")
    assert get_github_token() == "ghp_secret_value"
    assert token_status() == {"configured": True, "encrypted": True}

    env_text = (isolated_db.parent / ".env").read_text(encoding="utf-8")
    assert "ghp_secret_value" not in env_text
    assert "GITHUB_TOKEN_DPAPI=" in env_text

    clear_github_token()
    assert get_github_token() is None
    assert token_status()["configured"] is False


def test_plaintext_env_migrates_to_dpapi(isolated_db):
    env_file = isolated_db.parent / ".env"
    env_file.write_text("# 注释保留\nGITHUB_TOKEN=ghp_legacy\nOTHER=1\n", encoding="utf-8")

    assert get_github_token() == "ghp_legacy"
    text = env_file.read_text(encoding="utf-8")
    assert "GITHUB_TOKEN=ghp_legacy" not in text
    assert "GITHUB_TOKEN_DPAPI=" in text
    assert "OTHER=1" in text and "注释保留" in text


def test_legacy_db_token_migrates(isolated_db):
    SettingsStore.set(SETTING_GITHUB_TOKEN, "ghp_from_db")
    assert get_github_token() == "ghp_from_db"
    assert SettingsStore.get(SETTING_GITHUB_TOKEN) == ""
    assert token_status()["encrypted"] is True
